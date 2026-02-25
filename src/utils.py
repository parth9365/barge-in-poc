"""Utility functions: structured logging and retry decorator."""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Callable, TypeVar

from src.config import PipelineConfig

_T = TypeVar("_T")

_LOG_FORMAT = "%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s | %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured logging for the application.

    Args:
        level: Logging level (e.g. logging.DEBUG, logging.INFO).
    """
    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        datefmt=_LOG_DATE_FORMAT,
    )


def with_retry(
    fn: Callable[..., Any] | None = None,
    *,
    config: PipelineConfig | None = None,
) -> Any:
    """Decorator that retries async functions on transient OpenAI API errors.

    Uses exponential backoff. **Never** catches ``asyncio.CancelledError`` --
    it is always re-raised immediately so that task cancellation (barge-in)
    propagates correctly.

    Can be used bare (``@with_retry``) or with options
    (``@with_retry(config=PipelineConfig(max_retries=5))``).

    Args:
        fn: The async function to wrap (supplied automatically by the decorator).
        config: Override default retry settings.
    """
    if fn is None:
        # Called with arguments: @with_retry(config=...)
        return functools.partial(with_retry, config=config)

    cfg = config or PipelineConfig()

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        last_exc: BaseException | None = None
        for attempt in range(1, cfg.max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except asyncio.CancelledError:
                # Never swallow cancellation -- always re-raise.
                raise
            except Exception as exc:
                last_exc = exc
                _is_transient = _check_transient(exc)
                if not _is_transient or attempt == cfg.max_retries:
                    raise
                delay = cfg.retry_base_delay * (2 ** (attempt - 1))
                logger = logging.getLogger(fn.__module__)
                logger.warning(
                    "Retry %d/%d for %s after %.1fs: %s",
                    attempt,
                    cfg.max_retries,
                    fn.__qualname__,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
        # Should not reach here, but satisfy the type checker.
        raise last_exc  # type: ignore[misc]

    return wrapper


def _check_transient(exc: BaseException) -> bool:
    """Return True if *exc* looks like a transient OpenAI API error."""
    # Import lazily so the module works even if openai is not yet installed.
    try:
        from openai import APITimeoutError, RateLimitError
    except ImportError:
        return False
    return isinstance(exc, (APITimeoutError, RateLimitError))

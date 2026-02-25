"""Conversation history manager for the LLM context window."""

from __future__ import annotations

import logging

from src.config import ConversationConfig

logger = logging.getLogger(__name__)


class ConversationHistory:
    """Maintains the message list sent to the LLM on each turn.

    The system prompt is always the first message and is never dropped.
    When the history exceeds ``max_messages``, the oldest non-system
    messages are removed.

    Usage::

        history = ConversationHistory()
        history.add_user_message("Hello")
        history.add_assistant_message("Hi there!")
        messages = history.get_messages()
    """

    def __init__(self, config: ConversationConfig | None = None) -> None:
        self._config = config or ConversationConfig()
        self._system_message: dict[str, str] = {
            "role": "system",
            "content": self._config.system_prompt,
        }
        self._messages: list[dict[str, str]] = []

    def add_user_message(self, text: str) -> None:
        """Append a user message and trim if needed."""
        self._messages.append({"role": "user", "content": text})
        self._trim()
        logger.debug("Added user message: %.60s...", text)

    def add_assistant_message(self, text: str) -> None:
        """Append a complete assistant message and trim if needed."""
        self._messages.append({"role": "assistant", "content": text})
        self._trim()
        logger.debug("Added assistant message: %.60s...", text)

    def add_partial_assistant_message(self, text: str) -> None:
        """Save an interrupted assistant response with an ``[interrupted]`` marker.

        Called during barge-in to preserve partial context for the LLM.
        """
        if not text:
            return
        content = text + " [interrupted]"
        self._messages.append({"role": "assistant", "content": content})
        self._trim()
        logger.debug("Added partial assistant message: %.60s...", content)

    def get_messages(self) -> list[dict[str, str]]:
        """Return the full message list (system + history) for the LLM."""
        return [self._system_message] + list(self._messages)

    def _trim(self) -> None:
        """Drop oldest non-system messages to stay within max_messages."""
        # max_messages includes the system message, so the history list
        # can hold at most (max_messages - 1) entries.
        max_history = self._config.max_history_messages - 1
        if len(self._messages) > max_history:
            dropped = len(self._messages) - max_history
            self._messages = self._messages[dropped:]
            logger.debug("Trimmed %d oldest messages from history", dropped)

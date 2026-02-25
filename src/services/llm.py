"""LLM service: streaming chat completions via OpenAI GPT-4o."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from src.config import APIConfig

logger = logging.getLogger(__name__)


class LLMService:
    """Streams text responses from the OpenAI chat completions API.

    Cancellation-safe: ``asyncio.CancelledError`` propagates through the
    ``async for`` loop, closing the HTTP connection.

    Usage::

        llm = LLMService(client)
        async for token in llm.stream_response(messages):
            print(token, end="")
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        config: APIConfig | None = None,
    ) -> None:
        self._client = client
        self._config = config or APIConfig()

    async def stream_response(
        self,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        """Stream text deltas from the LLM.

        Args:
            messages: Conversation history in OpenAI message format.

        Yields:
            Text delta strings as they arrive from the API.
        """
        stream = await self._client.chat.completions.create(
            model=self._config.llm_model,
            messages=messages,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

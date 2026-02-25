"""Text-to-speech service: streaming PCM audio via OpenAI TTS."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from src.config import APIConfig
from src.types import PCMBytes

logger = logging.getLogger(__name__)


class TTSService:
    """Streams raw PCM audio bytes from the OpenAI TTS API.

    Output format is int16 LE mono at 24 kHz (``response_format="pcm"``).

    Cancellation-safe: ``asyncio.CancelledError`` propagates through the
    streaming response, closing the HTTP connection.

    Usage::

        tts = TTSService(client)
        async for pcm_chunk in tts.stream_speech("Hello!"):
            playback_queue.put_nowait(pcm_chunk)
    """

    _CHUNK_SIZE = 4096  # bytes per iteration of aiter_bytes

    def __init__(
        self,
        client: AsyncOpenAI,
        config: APIConfig | None = None,
    ) -> None:
        self._client = client
        self._config = config or APIConfig()

    async def stream_speech(self, text: str) -> AsyncIterator[PCMBytes]:
        """Convert text to streaming PCM audio.

        Args:
            text: The text to synthesize.

        Yields:
            Raw PCM byte chunks (int16 LE, mono, 24 kHz).
        """
        async with self._client.audio.speech.with_streaming_response.create(
            model=self._config.tts_model,
            voice=self._config.tts_voice,
            input=text,
            response_format=self._config.tts_response_format,
        ) as response:
            async for chunk in response.iter_bytes(chunk_size=self._CHUNK_SIZE):
                yield chunk

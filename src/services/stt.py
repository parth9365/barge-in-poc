"""Speech-to-text service using the OpenAI Whisper API."""

from __future__ import annotations

import io
import logging
import wave

import numpy as np
from openai import AsyncOpenAI

from src.config import APIConfig
from src.types import AudioChunk
from src.utils import with_retry

logger = logging.getLogger(__name__)


class STTService:
    """Transcribes audio chunks via the OpenAI Whisper API.

    Usage::

        stt = STTService(client)
        text = await stt.transcribe(audio_chunk, sample_rate=16000)
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        config: APIConfig | None = None,
    ) -> None:
        self._client = client
        self._config = config or APIConfig()

    @with_retry
    async def transcribe(self, audio: AudioChunk, sample_rate: int) -> str:
        """Convert a float32 audio chunk to text via Whisper.

        Args:
            audio: Float32 mono PCM samples (numpy array).
            sample_rate: Sample rate of *audio* in Hz.

        Returns:
            Transcribed text (stripped of whitespace), or empty string.
        """
        wav_bytes = _float32_to_wav_bytes(audio, sample_rate)

        transcription = await self._client.audio.transcriptions.create(
            model=self._config.stt_model,
            file=("audio.wav", wav_bytes, "audio/wav"),
            language="en",
        )

        text = transcription.text.strip()
        if text:
            logger.info("STT result: %s", text)
        else:
            logger.debug("STT returned empty text")
        return text


def _float32_to_wav_bytes(audio: AudioChunk, sample_rate: int) -> bytes:
    """Encode a float32 numpy array as in-memory WAV bytes (int16 PCM).

    Args:
        audio: 1-D float32 array with values in [-1.0, 1.0].
        sample_rate: Sample rate in Hz.

    Returns:
        Complete WAV file contents as bytes.
    """
    # Clip and convert to int16.
    clipped = np.clip(audio, -1.0, 1.0)
    int16_data = (clipped * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(int16_data.tobytes())
    return buf.getvalue()

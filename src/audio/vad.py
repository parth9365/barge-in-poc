"""Voice Activity Detection using Silero VAD."""

from __future__ import annotations

import logging
import time

import numpy as np
import torch

from src.config import AudioConfig, VADConfig
from src.types import AudioChunk, VADEvent

logger = logging.getLogger(__name__)


class VADProcessor:
    """Wraps the Silero VAD model for speech start/end detection.

    Tracks internal state (``_was_speaking``, silence timer) so that
    ``process_chunk`` returns discrete ``speech_started`` / ``speech_ended``
    events rather than raw probabilities.

    Usage::

        vad = VADProcessor()
        event = vad.process_chunk(chunk)
        if event.speech_started:
            ...
        if event.speech_ended:
            ...
        vad.reset()  # call on barge-in to clear state
    """

    def __init__(
        self,
        audio_config: AudioConfig | None = None,
        vad_config: VADConfig | None = None,
    ) -> None:
        self._audio_config = audio_config or AudioConfig()
        self._vad_config = vad_config or VADConfig()

        # Load Silero VAD via torch.hub (cached after first download).
        self._model, _utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
        logger.info("Silero VAD model loaded")

        # Internal state for edge detection.
        self._was_speaking: bool = False
        self._silence_start: float | None = None

    def process_chunk(self, chunk: AudioChunk) -> VADEvent:
        """Run VAD on one audio chunk and return start/end events.

        Args:
            chunk: Float32 mono audio at the configured capture sample rate.

        Returns:
            A ``VADEvent`` with speech_started, speech_ended, and probability.
        """
        tensor = torch.from_numpy(chunk)
        probability: float = self._model(
            tensor,
            self._audio_config.capture_sample_rate,
        ).item()

        is_speech = probability >= self._vad_config.threshold
        if probability > 0.1:
            logger.debug("VAD prob=%.3f (threshold=%.2f)", probability, self._vad_config.threshold)
        speech_started = False
        speech_ended = False

        if is_speech:
            self._silence_start = None
            if not self._was_speaking:
                speech_started = True
                self._was_speaking = True
                logger.debug("Speech started (prob=%.3f)", probability)
        else:
            # Not speech.
            if self._was_speaking:
                now = time.monotonic()
                if self._silence_start is None:
                    self._silence_start = now

                elapsed_ms = (now - self._silence_start) * 1000
                if elapsed_ms >= self._vad_config.min_silence_duration_ms:
                    speech_ended = True
                    self._was_speaking = False
                    self._silence_start = None
                    logger.debug(
                        "Speech ended (silence=%.0fms, prob=%.3f)",
                        elapsed_ms,
                        probability,
                    )

        return VADEvent(
            speech_started=speech_started,
            speech_ended=speech_ended,
            probability=probability,
        )

    def reset(self) -> None:
        """Clear internal state.  Call on barge-in or when restarting detection."""
        self._was_speaking = False
        self._silence_start = None
        self._model.reset_states()
        logger.debug("VAD state reset")

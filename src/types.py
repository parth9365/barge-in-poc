"""Shared type aliases, enums, and dataclasses for the voice conversation pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import numpy as np
import numpy.typing as npt

# -- Type aliases --

AudioChunk = npt.NDArray[np.float32]
"""Raw PCM samples from the microphone (float32, mono)."""

PCMBytes = bytes
"""Raw PCM bytes for speaker playback (int16 LE, mono)."""


# -- Enums --

class ConversationState(Enum):
    """States of the voice conversation state machine."""

    IDLE = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    THINKING = auto()
    SPEAKING = auto()
    BARGE_IN = auto()


# -- Dataclasses --

@dataclass
class VADEvent:
    """Result of processing one audio chunk through VAD.

    Attributes:
        speech_started: True on the chunk where speech is first detected.
        speech_ended: True on the chunk where silence is confirmed after speech.
        probability: Raw speech probability from the VAD model (0.0 - 1.0).
    """

    speech_started: bool
    speech_ended: bool
    probability: float


@dataclass
class PipelineContext:
    """Tracks the asyncio tasks that make up the current response pipeline.

    All fields are None when no pipeline is active. During barge-in, each
    non-None task is cancelled in order: playback -> TTS -> LLM.

    Attributes:
        llm_task: The task streaming text from the LLM.
        tts_task: The task converting text to speech.
        playback_task: The task feeding PCM bytes to the audio output.
        partial_response: Accumulated LLM text so far (for interrupted saves).
    """

    llm_task: Optional[asyncio.Task] = field(default=None)  # noqa: UP007
    tts_task: Optional[asyncio.Task] = field(default=None)  # noqa: UP007
    playback_task: Optional[asyncio.Task] = field(default=None)  # noqa: UP007
    partial_response: str = ""

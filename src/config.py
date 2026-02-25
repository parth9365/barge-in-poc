"""Configuration constants for the voice conversation pipeline.

All config objects are frozen dataclasses -- immutable after creation.
Override by constructing new instances with desired values.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioConfig:
    """Audio capture and playback parameters.

    Attributes:
        capture_sample_rate: Mic sample rate in Hz (must be 16000 for Silero VAD).
        capture_chunk_samples: Samples per capture callback (512 = 32ms at 16kHz).
        capture_queue_maxsize: Max items in the capture asyncio.Queue before dropping.
        playback_sample_rate: Speaker sample rate in Hz (24000 matches OpenAI TTS PCM).
        playback_channels: Number of output channels (mono).
    """

    capture_sample_rate: int = 16_000
    capture_chunk_samples: int = 512
    capture_queue_maxsize: int = 100
    playback_sample_rate: int = 24_000
    playback_channels: int = 1


@dataclass(frozen=True)
class VADConfig:
    """Silero VAD tuning parameters.

    Attributes:
        threshold: Speech probability above which a chunk is considered speech.
        min_silence_duration_ms: Consecutive silence required to fire speech_ended.
        speech_pad_ms: Padding added around speech segments (Silero internal).
    """

    threshold: float = 0.3
    min_silence_duration_ms: int = 300
    speech_pad_ms: int = 30


@dataclass(frozen=True)
class APIConfig:
    """OpenAI API model identifiers and settings.

    Attributes:
        stt_model: Whisper model for speech-to-text.
        llm_model: Chat model for response generation.
        tts_model: Text-to-speech model.
        tts_voice: Voice preset for TTS.
        tts_response_format: Audio format returned by TTS (pcm = raw int16 LE).
    """

    stt_model: str = "whisper-1"
    llm_model: str = "gpt-4o"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "coral"
    tts_response_format: str = "pcm"


@dataclass(frozen=True)
class PipelineConfig:
    """Controls for the LLM -> TTS -> Playback pipeline.

    Attributes:
        sentence_buffer_max_chars: Max chars to buffer before flushing to TTS.
        max_retries: Max retry attempts for transient API errors.
        retry_base_delay: Base delay in seconds for exponential backoff.
    """

    sentence_buffer_max_chars: int = 200
    max_retries: int = 3
    retry_base_delay: float = 0.5


@dataclass(frozen=True)
class ConversationConfig:
    """Conversation history settings.

    Attributes:
        system_prompt: System message prepended to every LLM request.
        max_history_messages: Max messages kept in history (oldest dropped first).
    """

    system_prompt: str = (
        "You are a helpful voice assistant. "
        "Keep responses concise and conversational."
    )
    max_history_messages: int = 50

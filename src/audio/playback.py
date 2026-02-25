"""Speaker playback: feeds PCM bytes from an asyncio.Queue to sounddevice."""

from __future__ import annotations

import asyncio
import collections
import logging
import threading
from typing import Optional

import sounddevice as sd

from src.config import AudioConfig
from src.types import PCMBytes

logger = logging.getLogger(__name__)


class AudioPlayback:
    """Plays PCM audio through the default output device.

    Uses a ``sounddevice.RawOutputStream`` with a callback that reads from
    an internal ``collections.deque[bytes]`` protected by a
    ``threading.Lock``.  The stream runs continuously -- it outputs silence
    when the buffer is empty, avoiding audible pops from stream start/stop.

    Thread safety:
        ``hard_stop()`` and the sounddevice callback both access ``_buffer``
        under ``_lock``.  ``hard_stop()`` may be called from any thread.

    Usage::

        playback = AudioPlayback()
        playback.start()
        await playback.play_chunks(pcm_queue)  # consumes until None sentinel
        playback.hard_stop()                   # barge-in: clear buffer instantly
        playback.stop()                        # shutdown
    """

    # Size of a single silent frame block written to the device when the
    # buffer is empty.  2 bytes per sample (int16) * 1 channel.
    _SILENCE_FRAME_BYTES = 2

    def __init__(self, config: AudioConfig | None = None) -> None:
        self._config = config or AudioConfig()
        self._buffer: collections.deque[bytes] = collections.deque()
        self._lock = threading.Lock()
        self._stream: Optional[sd.RawOutputStream] = None  # noqa: UP007

    # -- public API --

    def start(self) -> None:
        """Open the speaker stream (runs continuously until ``stop()``)."""
        if self._stream is not None:
            return
        self._stream = sd.RawOutputStream(
            samplerate=self._config.playback_sample_rate,
            channels=self._config.playback_channels,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()
        logger.info(
            "Audio playback started: %d Hz, %d ch",
            self._config.playback_sample_rate,
            self._config.playback_channels,
        )

    def stop(self) -> None:
        """Stop and close the speaker stream (call only on shutdown)."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("Audio playback stopped")

    async def play_chunks(self, pcm_queue: asyncio.Queue[PCMBytes | None]) -> None:
        """Consume PCM chunks from *pcm_queue* until a ``None`` sentinel.

        Each chunk is appended to the internal buffer where the sounddevice
        callback picks it up.  This coroutine is cancellation-safe: on
        ``CancelledError`` it re-raises without cleanup (the caller should
        call ``hard_stop()`` to clear residual audio).
        """
        while True:
            chunk = await pcm_queue.get()
            if chunk is None:
                break
            with self._lock:
                self._buffer.append(chunk)

    def hard_stop(self) -> None:
        """Clear the playback buffer instantly.  Thread-safe.

        Called during barge-in to silence the speaker without
        stopping/restarting the stream (which would cause audible pops).
        """
        with self._lock:
            self._buffer.clear()
        logger.debug("Playback buffer cleared (hard_stop)")

    # -- internal --

    def _callback(
        self,
        outdata: memoryview,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        """sounddevice callback -- runs on the audio thread.

        Reads from ``_buffer`` under ``_lock``.  Writes silence when
        the buffer is empty.
        """
        if status:
            logger.warning("Playback callback status: %s", status)

        bytes_needed = frames * self._SILENCE_FRAME_BYTES * self._config.playback_channels
        data = bytearray()

        with self._lock:
            while len(data) < bytes_needed and self._buffer:
                chunk = self._buffer.popleft()
                data.extend(chunk)

        if len(data) < bytes_needed:
            # Pad with silence.
            data.extend(b"\x00" * (bytes_needed - len(data)))
        elif len(data) > bytes_needed:
            # Put the excess back.
            excess = bytes(data[bytes_needed:])
            data = data[:bytes_needed]
            with self._lock:
                self._buffer.appendleft(excess)

        outdata[:] = bytes(data)

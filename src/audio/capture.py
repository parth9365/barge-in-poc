"""Microphone capture: bridges sounddevice callback thread to an asyncio.Queue."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import numpy as np
import sounddevice as sd

from src.config import AudioConfig
from src.types import AudioChunk

logger = logging.getLogger(__name__)


class AudioCapture:
    """Captures audio from the default input device.

    Produces ``AudioChunk`` (float32, mono, 16 kHz) objects into an
    ``asyncio.Queue``.  The sounddevice callback runs on a separate
    OS thread, so ``loop.call_soon_threadsafe`` is used to safely
    enqueue data into the asyncio world.

    Usage::

        capture = AudioCapture()
        capture.start()
        queue = capture.get_queue()
        chunk = await queue.get()
        ...
        capture.stop()
    """

    def __init__(
        self,
        config: AudioConfig | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._config = config or AudioConfig()
        self._loop = loop or asyncio.get_event_loop()
        self._queue: asyncio.Queue[AudioChunk] = asyncio.Queue(
            maxsize=self._config.capture_queue_maxsize,
        )
        self._stream: Optional[sd.InputStream] = None  # noqa: UP007

    # -- public API --

    def start(self) -> None:
        """Open the microphone stream and begin pushing chunks to the queue."""
        if self._stream is not None:
            return
        self._stream = sd.InputStream(
            samplerate=self._config.capture_sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self._config.capture_chunk_samples,
            callback=self._callback,
        )
        self._stream.start()
        logger.info(
            "Audio capture started: %d Hz, %d samples/chunk",
            self._config.capture_sample_rate,
            self._config.capture_chunk_samples,
        )

    def stop(self) -> None:
        """Stop and close the microphone stream."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("Audio capture stopped")

    def get_queue(self) -> asyncio.Queue[AudioChunk]:
        """Return the queue that receives captured audio chunks."""
        return self._queue

    # -- internal --

    def _enqueue(self, chunk: AudioChunk) -> None:
        """Enqueue a chunk on the event loop thread, dropping on overflow.

        This runs inside the event loop (scheduled by ``call_soon_threadsafe``),
        so ``QueueFull`` is caught here rather than leaking to the event loop's
        unhandled-exception handler.
        """
        try:
            self._queue.put_nowait(chunk)
        except asyncio.QueueFull:
            logger.warning("Capture queue full -- dropping chunk")

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        """sounddevice callback -- runs on a C-level audio thread.

        IMPORTANT: ``indata`` is reused by sounddevice after this callback
        returns, so we must copy it before enqueuing.
        """
        if status:
            logger.warning("Capture callback status: %s", status)

        # Copy the buffer -- sounddevice reuses indata on the next callback.
        chunk: AudioChunk = indata[:, 0].copy()

        self._loop.call_soon_threadsafe(self._enqueue, chunk)

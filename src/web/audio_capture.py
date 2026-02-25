"""WebSocket-based audio capture: receives PCM from the browser over WebSocket.

Drop-in replacement for ``AudioCapture`` -- the controller calls the same
``start()``, ``stop()``, ``get_queue()`` interface without knowing that audio
is arriving from a browser rather than a local microphone.
"""

from __future__ import annotations

import asyncio
import logging

import numpy as np

from src.config import AudioConfig
from src.types import AudioChunk

logger = logging.getLogger(__name__)


class WebSocketAudioCapture:
    """Receives browser audio over a WebSocket and exposes it as an asyncio.Queue.

    The server pushes raw binary WebSocket messages (float32 PCM, 16 kHz,
    mono) into this adapter via :meth:`push_audio`.  The conversation
    controller reads chunks from :meth:`get_queue` -- identical to the
    sounddevice-based ``AudioCapture``.
    """

    def __init__(self, config: AudioConfig | None = None) -> None:
        self._config = config or AudioConfig()
        self._queue: asyncio.Queue[AudioChunk] = asyncio.Queue(
            maxsize=self._config.capture_queue_maxsize,
        )
        self._running = False

    # -- Public API (matches AudioCapture interface) --------------------------

    def start(self) -> None:
        """Mark the capture as active.  No hardware to open."""
        self._running = True
        logger.info("WebSocket audio capture started")

    def stop(self) -> None:
        """Mark the capture as stopped."""
        self._running = False
        logger.info("WebSocket audio capture stopped")

    def get_queue(self) -> asyncio.Queue[AudioChunk]:
        """Return the queue that the controller reads from."""
        return self._queue

    # -- WebSocket bridge -----------------------------------------------------

    def push_audio(self, data: bytes) -> None:
        """Decode a binary WebSocket message and enqueue as AudioChunk.

        The browser sends raw float32 PCM bytes (16 kHz, mono).
        Each message may contain multiple samples.
        """
        if not self._running:
            return

        chunk: AudioChunk = np.frombuffer(data, dtype=np.float32).copy()

        try:
            self._queue.put_nowait(chunk)
        except asyncio.QueueFull:
            logger.warning("WebSocket capture queue full -- dropping chunk")

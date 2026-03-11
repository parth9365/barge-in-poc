"""WebSocket-based audio playback: sends PCM bytes to the browser over WebSocket.

Drop-in replacement for ``AudioPlayback`` -- the controller calls the same
``start()``, ``stop()``, ``play_chunks()``, ``hard_stop()`` interface.
Instead of driving a speaker, audio goes out as binary WebSocket messages.
"""

from __future__ import annotations

import asyncio
import logging

from starlette.websockets import WebSocket, WebSocketState

from src.types import PCMBytes

logger = logging.getLogger(__name__)


class WebSocketAudioPlayback:
    """Sends TTS audio as binary WebSocket messages to the browser.

    Each PCM chunk (int16 LE, 24 kHz, mono) from the TTS pipeline is sent
    as-is over the WebSocket.  On ``hard_stop()``, the playback queue is
    drained and a JSON ``{"type": "audio_stop"}`` message tells the browser
    to clear its audio buffers immediately.
    """

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws
        self._running = False
        self._muted = False
        self._stopped = asyncio.Event()
        self._current_queue: asyncio.Queue[PCMBytes | None] | None = None

    # -- Public API (matches AudioPlayback interface) -------------------------

    def start(self) -> None:
        """Mark playback as active.  No hardware to open."""
        self._running = True
        self._muted = False
        self._stopped.clear()
        logger.info("WebSocket audio playback started")

    def stop(self) -> None:
        """Mark playback as stopped."""
        self._running = False
        self._stopped.set()
        logger.info("WebSocket audio playback stopped")

    async def play_chunks(self, pcm_queue: asyncio.Queue[PCMBytes | None]) -> None:
        """Read PCM chunks from *pcm_queue* and send as binary WebSocket messages.

        Runs until a ``None`` sentinel is received.  Cancellation-safe:
        re-raises ``CancelledError`` so the controller can manage shutdown.
        """
        self._muted = False  # Reset mute from any previous barge-in.
        self._current_queue = pcm_queue
        try:
            while True:
                chunk = await pcm_queue.get()
                if chunk is None:
                    break
                if self._muted:
                    continue
                if self._ws.client_state == WebSocketState.CONNECTED:
                    await self._ws.send_bytes(chunk)
        except asyncio.CancelledError:
            raise
        finally:
            self._current_queue = None

    def hard_stop(self) -> None:
        """Stop audio playback immediately.

        Sets a mute flag so ``play_chunks()`` drops any remaining chunks,
        drains the queue, and sends an ``audio_stop`` event to the browser.
        """
        self._muted = True

        # Drain any chunks already sitting in the queue.
        if self._current_queue is not None:
            while True:
                try:
                    self._current_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._send_stop())
        except RuntimeError:
            pass

    async def _send_stop(self) -> None:
        """Send the stop event to the browser."""
        try:
            if self._ws.client_state == WebSocketState.CONNECTED:
                await self._ws.send_json({"type": "audio_stop"})
        except Exception:
            logger.debug("Failed to send audio_stop (client may have disconnected)")

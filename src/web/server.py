"""FastAPI server for the voice conversation web UI.

Serves the static frontend and provides a WebSocket endpoint that bridges
browser audio to the conversation controller.  Each WebSocket connection
creates its own conversation session with independent state.

WebSocket protocol:
    Browser -> Server:
        binary  = raw float32 PCM audio (16 kHz, mono)
        text    = JSON commands: {"type": "start"} or {"type": "stop"}

    Server -> Browser:
        binary  = raw int16 LE PCM audio (24 kHz, mono)
        text    = JSON events:
            {"type": "state", "state": "LISTENING"}
            {"type": "transcript", "role": "user", "text": "..."}
            {"type": "transcript", "role": "assistant", "text": "..."}
            {"type": "barge_in"}
            {"type": "audio_stop"}
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from starlette.responses import FileResponse
from starlette.websockets import WebSocketState

from src.audio.vad import VADProcessor
from src.config import (
    APIConfig,
    AudioConfig,
    ConversationConfig,
    PipelineConfig,
    VADConfig,
)
from src.controller import ConversationController
from src.conversation import ConversationHistory
from src.services.llm import LLMService
from src.services.stt import STTService
from src.services.tts import TTSService
from src.types import ConversationState
from src.web.audio_capture import WebSocketAudioCapture
from src.web.audio_playback import WebSocketAudioPlayback

logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Voice Conversation POC")

# Serve the frontend from src/web/static/.
_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    """Serve the main page."""
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Handle one voice conversation session over WebSocket."""
    await ws.accept()
    logger.info("WebSocket connected")

    # -- Build a fresh session ------------------------------------------------
    client = AsyncOpenAI()
    audio_config = AudioConfig()
    vad_config = VADConfig()
    api_config = APIConfig()
    pipeline_config = PipelineConfig()
    conversation_config = ConversationConfig()

    capture = WebSocketAudioCapture(config=audio_config)
    playback = WebSocketAudioPlayback(ws)
    vad = VADProcessor(audio_config=audio_config, vad_config=vad_config)
    stt = STTService(client=client, config=api_config)
    llm = LLMService(client=client, config=api_config)
    tts = TTSService(client=client, config=api_config)
    history = ConversationHistory(config=conversation_config)

    # -- Event callbacks (sync; bridge to async WebSocket sends) --------------

    loop = asyncio.get_running_loop()

    def on_state_change(
        old: ConversationState, new: ConversationState,
    ) -> None:
        loop.create_task(_send_json_safe(ws, {
            "type": "state",
            "state": new.name,
        }))

    def on_transcript(role: str, text: str) -> None:
        loop.create_task(_send_json_safe(ws, {
            "type": "transcript",
            "role": role,
            "text": text,
        }))

    def on_barge_in() -> None:
        loop.create_task(_send_json_safe(ws, {
            "type": "barge_in",
        }))

    controller = ConversationController(
        capture=capture,
        playback=playback,
        vad=vad,
        stt=stt,
        llm=llm,
        tts=tts,
        history=history,
        audio_config=audio_config,
        pipeline_config=pipeline_config,
        on_state_change=on_state_change,
        on_transcript=on_transcript,
        on_barge_in=on_barge_in,
    )

    controller_task: asyncio.Task | None = None

    try:
        while True:
            message = await ws.receive()

            if message["type"] == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"]:
                # Binary message = audio data from the browser.
                capture.push_audio(message["bytes"])

            elif "text" in message and message["text"]:
                try:
                    cmd = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                if cmd.get("type") == "start":
                    if controller_task is None or controller_task.done():
                        controller_task = asyncio.create_task(
                            controller.run(),
                        )
                        logger.info("Controller started via WebSocket command")

                elif cmd.get("type") == "stop":
                    controller.request_shutdown()
                    logger.info("Controller stop requested via WebSocket")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception:
        logger.exception("WebSocket error")
    finally:
        # Graceful shutdown.
        controller.request_shutdown()
        if controller_task is not None and not controller_task.done():
            controller_task.cancel()
            try:
                await controller_task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("Session cleaned up")


async def _send_json_safe(ws: WebSocket, data: dict) -> None:
    """Send JSON to the WebSocket, silently ignoring errors if disconnected."""
    try:
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.send_json(data)
    except Exception:
        pass

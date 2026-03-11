"""Entry point for the Voice Conversation POC with Barge-In Support.

Wires all components together and runs the conversation controller.

Usage::

    python -m src.main
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv
from openai import AsyncOpenAI

from src.audio.capture import AudioCapture
from src.audio.playback import AudioPlayback
from src.audio.vad import VADProcessor
from src.config import (
    APIConfig,
    AudioConfig,
    ConversationConfig,
    PipelineConfig,
    RAGConfig,
    VADConfig,
)
from src.controller import ConversationController
from src.conversation import ConversationHistory
from src.services.llm import LLMService
from src.services.rag import KnowledgeBase
from src.services.stt import STTService
from src.services.tools import TOOL_DEFINITIONS, ToolExecutor
from src.services.tts import TTSService
from src.utils import setup_logging

logger = logging.getLogger(__name__)

_BANNER = """\

Voice Conversation POC with Barge-In Support
=============================================
Using headphones is recommended to avoid echo feedback.
Speak to start a conversation. Press Ctrl+C to exit.
"""


async def main() -> None:
    """Create all components, wire them into the controller, and run."""
    # -- Environment & logging --
    load_dotenv()
    setup_logging()

    # -- OpenAI client --
    client = AsyncOpenAI()

    # -- Configuration --
    audio_config = AudioConfig()
    vad_config = VADConfig()
    api_config = APIConfig()
    pipeline_config = PipelineConfig()
    conversation_config = ConversationConfig()
    rag_config = RAGConfig()

    # -- RAG knowledge base --
    knowledge_base = KnowledgeBase(config=rag_config, client=client)
    await knowledge_base.initialize()
    tool_executor = ToolExecutor(knowledge_base)

    # -- Components --
    loop = asyncio.get_running_loop()
    capture = AudioCapture(config=audio_config, loop=loop)
    playback = AudioPlayback(config=audio_config)
    vad = VADProcessor(audio_config=audio_config, vad_config=vad_config)
    stt = STTService(client=client, config=api_config)
    llm = LLMService(
        client=client,
        config=api_config,
        tools=TOOL_DEFINITIONS,
        tool_executor=tool_executor,
    )
    tts = TTSService(client=client, config=api_config)
    history = ConversationHistory(config=conversation_config)

    # -- Controller --
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
    )

    # -- Startup banner --
    print(_BANNER)

    # -- Signal handlers --
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, controller.request_shutdown)

    # -- Run --
    logger.info("Starting voice conversation controller")
    await controller.run()
    logger.info("Session ended")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Clean exit on Ctrl+C if signal handler didn't catch it.
        sys.exit(0)

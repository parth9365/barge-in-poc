"""Conversation controller: state machine, pipeline orchestration, and barge-in.

This is the brain of the voice conversation system. It owns the state machine,
manages asyncio Tasks for the LLM -> TTS -> Playback pipeline, and implements
barge-in cancellation so the user can interrupt the assistant mid-speech.

State machine::

    IDLE --[speech_started]--> LISTENING
    LISTENING --[speech_ended]--> TRANSCRIBING
    TRANSCRIBING --[STT done]--> THINKING
    THINKING --[first TTS audio]--> SPEAKING
    SPEAKING --[playback done]--> IDLE
    THINKING/SPEAKING --[speech_started]--> BARGE_IN --> LISTENING

BARGE_IN is transient: it executes cancellation and immediately becomes LISTENING.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from typing import Optional

import numpy as np

from src.audio.capture import AudioCapture
from src.audio.playback import AudioPlayback
from src.audio.vad import VADProcessor
from src.config import AudioConfig, PipelineConfig
from src.conversation import ConversationHistory
from src.services.llm import LLMService
from src.services.stt import STTService
from src.services.tts import TTSService
from src.types import AudioChunk, ConversationState, PipelineContext, VADEvent

logger = logging.getLogger(__name__)

# Sentence boundary: punctuation followed by whitespace.
_SENTENCE_BOUNDARY = re.compile(r"[.!?]\s")


class ConversationController:
    """Orchestrates the voice conversation loop with barge-in support.

    The controller reads audio chunks from the capture queue, runs them
    through VAD, and drives the state machine.  When the user finishes
    speaking, it launches a pipeline of three concurrent asyncio Tasks
    (LLM -> TTS -> Playback) connected by queues.  If the user speaks
    during THINKING or SPEAKING, barge-in cancels the pipeline and
    silences playback within ~50 ms.

    Optional callbacks (``on_state_change``, ``on_transcript``,
    ``on_barge_in``) allow a web UI to observe events without polling.
    They default to ``None`` so CLI mode works without them.
    """

    def __init__(
        self,
        capture: AudioCapture,
        playback: AudioPlayback,
        vad: VADProcessor,
        stt: STTService,
        llm: LLMService,
        tts: TTSService,
        history: ConversationHistory,
        audio_config: AudioConfig | None = None,
        pipeline_config: PipelineConfig | None = None,
        *,
        on_state_change: Callable[[ConversationState, ConversationState], None] | None = None,
        on_transcript: Callable[[str, str], None] | None = None,
        on_barge_in: Callable[[], None] | None = None,
    ) -> None:
        self._capture = capture
        self._playback = playback
        self._vad = vad
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._history = history
        self._audio_config = audio_config or AudioConfig()
        self._pipeline_config = pipeline_config or PipelineConfig()

        # Optional event callbacks (for web UI integration).
        self._on_state_change = on_state_change
        self._on_transcript = on_transcript
        self._on_barge_in = on_barge_in

        # Internal state.
        self._state = ConversationState.IDLE
        self._pipeline_ctx = PipelineContext()
        self._speech_buffer: list[AudioChunk] = []
        self._sentence_buffer: str = ""
        self._shutdown = False
        self._pipeline_task: Optional[asyncio.Task] = None  # noqa: UP007

        # True while VAD is tracking an active speech segment.
        # Used to continue buffering during TRANSCRIBING.
        self._speech_active = False

    # -- Public API -------------------------------------------------------

    async def run(self) -> None:
        """Main loop: read audio chunks, process VAD, drive state machine.

        Blocks until ``request_shutdown()`` is called or the task is
        cancelled.  On exit it cancels any active pipeline and stops
        the audio streams.
        """
        self._capture.start()
        self._playback.start()
        audio_queue = self._capture.get_queue()
        logger.info("Controller started -- state: IDLE")

        try:
            while not self._shutdown:
                try:
                    chunk = await asyncio.wait_for(
                        audio_queue.get(), timeout=0.5,
                    )
                except asyncio.TimeoutError:
                    # No audio arrived -- re-check shutdown flag.
                    continue
                vad_event = self._vad.process_chunk(chunk)
                await self._handle_vad_event(vad_event, chunk)
        except asyncio.CancelledError:
            logger.info("Controller cancelled")
        finally:
            await self._shutdown_pipeline()
            self._capture.stop()
            self._playback.stop()
            logger.info("Controller stopped")

    def request_shutdown(self) -> None:
        """Signal the main loop to exit.  Safe to call from signal handlers."""
        self._shutdown = True

    # -- State helpers ----------------------------------------------------

    def _set_state(self, new_state: ConversationState) -> None:
        """Transition to *new_state*, log it, and fire the callback."""
        old = self._state
        if old == new_state:
            return
        self._state = new_state
        logger.info("State: %s -> %s", old.name, new_state.name)
        if self._on_state_change is not None:
            self._on_state_change(old, new_state)

    # -- VAD event handling (state machine) -------------------------------

    async def _handle_vad_event(
        self, event: VADEvent, chunk: AudioChunk,
    ) -> None:
        """Process one VAD event and drive state transitions."""
        # Track speech-segment activity for buffering during TRANSCRIBING.
        if event.speech_started:
            self._speech_active = True
        if event.speech_ended:
            self._speech_active = False

        state = self._state

        if state == ConversationState.IDLE:
            if event.speech_started:
                self._speech_buffer.clear()
                self._speech_buffer.append(chunk)
                self._set_state(ConversationState.LISTENING)

        elif state == ConversationState.LISTENING:
            # Always buffer during LISTENING (speech + brief silences).
            self._speech_buffer.append(chunk)
            if event.speech_ended:
                audio_buffer = list(self._speech_buffer)
                self._speech_buffer.clear()
                self._set_state(ConversationState.TRANSCRIBING)
                self._pipeline_task = asyncio.create_task(
                    self._process_utterance(audio_buffer),
                )

        elif state == ConversationState.TRANSCRIBING:
            # Buffer speech during transcription (rapid re-speaking).
            if self._speech_active:
                self._speech_buffer.append(chunk)

        elif state in (ConversationState.THINKING, ConversationState.SPEAKING):
            if event.speech_started:
                await self._execute_barge_in()
                # Begin buffering the new speech.
                self._speech_buffer.clear()
                self._speech_buffer.append(chunk)
                self._set_state(ConversationState.LISTENING)

    # -- Pipeline ---------------------------------------------------------

    async def _process_utterance(
        self, audio_buffer: list[AudioChunk],
    ) -> None:
        """Run the full STT -> LLM -> TTS -> Playback pipeline.

        Launched as an ``asyncio.Task`` from ``_handle_vad_event``.
        On barge-in the inner tasks are cancelled externally; this method
        catches ``CancelledError`` and returns (cleanup is handled by
        ``_execute_barge_in``).
        """
        try:
            # -- STT --
            audio = np.concatenate(audio_buffer)
            text = await self._stt.transcribe(
                audio, self._audio_config.capture_sample_rate,
            )
            if not text:
                logger.info("Empty transcription -- returning to IDLE")
                self._set_state(ConversationState.IDLE)
                return

            self._history.add_user_message(text)
            if self._on_transcript is not None:
                self._on_transcript("user", text)
            logger.info("User: %s", text)

            # -- Launch pipeline --
            self._set_state(ConversationState.THINKING)

            tts_text_queue: asyncio.Queue[str | None] = asyncio.Queue()
            pcm_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

            self._pipeline_ctx = PipelineContext()
            self._sentence_buffer = ""

            llm_task = asyncio.create_task(self._run_llm(tts_text_queue))
            tts_task = asyncio.create_task(
                self._run_tts(tts_text_queue, pcm_queue),
            )
            playback_task = asyncio.create_task(self._run_playback(pcm_queue))

            self._pipeline_ctx.llm_task = llm_task
            self._pipeline_ctx.tts_task = tts_task
            self._pipeline_ctx.playback_task = playback_task

            await asyncio.gather(llm_task, tts_task, playback_task)

            # -- Pipeline completed normally --
            full_response = self._pipeline_ctx.partial_response
            if full_response:
                self._history.add_assistant_message(full_response)
                if self._on_transcript is not None:
                    self._on_transcript("assistant", full_response)
                logger.info("Assistant: %s", full_response)

            self._pipeline_ctx = PipelineContext()
            self._set_state(ConversationState.IDLE)

            # If speech was buffered during the pipeline (rapid re-speaking),
            # process it immediately rather than waiting for a new VAD event.
            if self._speech_buffer:
                pending = list(self._speech_buffer)
                self._speech_buffer.clear()
                self._set_state(ConversationState.TRANSCRIBING)
                self._pipeline_task = asyncio.create_task(
                    self._process_utterance(pending),
                )

        except asyncio.CancelledError:
            # Barge-in -- cleanup handled by _execute_barge_in.
            return

    # -- Pipeline stage tasks ---------------------------------------------

    async def _run_llm(
        self, tts_text_queue: asyncio.Queue[str | None],
    ) -> None:
        """Stream LLM text, buffer into sentences, push to TTS queue."""
        try:
            messages = self._history.get_messages()
            async for token in self._llm.stream_response(messages):
                self._pipeline_ctx.partial_response += token
                self._sentence_buffer += token

                # Flush any complete sentences to TTS.
                while True:
                    sentence = self._extract_sentence()
                    if sentence is None:
                        break
                    await tts_text_queue.put(sentence)

            # Flush remaining text.
            remaining = self._sentence_buffer.strip()
            if remaining:
                await tts_text_queue.put(remaining)
            self._sentence_buffer = ""

            # Signal TTS that the LLM stream is finished.
            await tts_text_queue.put(None)
        except asyncio.CancelledError:
            raise

    async def _run_tts(
        self,
        tts_text_queue: asyncio.Queue[str | None],
        pcm_queue: asyncio.Queue[bytes | None],
    ) -> None:
        """Read sentences from the text queue, stream PCM to playback queue."""
        try:
            first_audio = True
            while True:
                sentence = await tts_text_queue.get()
                if sentence is None:
                    break
                async for pcm_chunk in self._tts.stream_speech(sentence):
                    if first_audio:
                        self._set_state(ConversationState.SPEAKING)
                        first_audio = False
                    await pcm_queue.put(pcm_chunk)

            # Signal playback that TTS is finished.
            await pcm_queue.put(None)
        except asyncio.CancelledError:
            raise

    async def _run_playback(
        self, pcm_queue: asyncio.Queue[bytes | None],
    ) -> None:
        """Feed PCM chunks to the audio playback device."""
        try:
            await self._playback.play_chunks(pcm_queue)
        except asyncio.CancelledError:
            raise

    # -- Sentence buffering -----------------------------------------------

    def _extract_sentence(self) -> str | None:
        """Pop one complete sentence from ``_sentence_buffer``, or ``None``.

        A sentence boundary is ``.``, ``!``, or ``?`` followed by
        whitespace.  If no boundary is found but the buffer exceeds
        ``sentence_buffer_max_chars``, the whole buffer is flushed to
        prevent latency buildup.
        """
        match = _SENTENCE_BOUNDARY.search(self._sentence_buffer)
        if match:
            # Include the punctuation, skip the trailing space.
            idx = match.start() + 1
            sentence = self._sentence_buffer[:idx].strip()
            self._sentence_buffer = self._sentence_buffer[idx:]
            return sentence if sentence else None

        max_chars = self._pipeline_config.sentence_buffer_max_chars
        if len(self._sentence_buffer) >= max_chars:
            sentence = self._sentence_buffer.strip()
            self._sentence_buffer = ""
            return sentence if sentence else None

        return None

    # -- Barge-in ---------------------------------------------------------

    async def _execute_barge_in(self) -> None:
        """Cancel the active pipeline.  Target: <50 ms.

        Order matters for perceived latency:

        1. ``hard_stop()`` playback (user hears silence immediately).
        2. Cancel LLM task (stop generating text / save API cost).
        3. Cancel TTS task (stop generating audio).
        4. Cancel playback task (stop queue consumer).
        5. Save partial response to history with ``[interrupted]`` marker.
        6. Reset pipeline context, VAD state, sentence buffer.
        """
        t0 = time.monotonic()
        self._set_state(ConversationState.BARGE_IN)

        if self._on_barge_in is not None:
            self._on_barge_in()

        # 1. Silence the speaker immediately.
        self._playback.hard_stop()

        # 2-4. Cancel pipeline tasks upstream-to-downstream.
        ctx = self._pipeline_ctx
        for label, task in [
            ("LLM", ctx.llm_task),
            ("TTS", ctx.tts_task),
            ("Playback", ctx.playback_task),
        ]:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
                logger.debug("Cancelled %s task", label)

        # Cancel the outer pipeline task as well.
        if self._pipeline_task is not None and not self._pipeline_task.done():
            self._pipeline_task.cancel()
            try:
                await self._pipeline_task
            except (asyncio.CancelledError, Exception):
                pass

        # 5. Save partial response.
        if ctx.partial_response:
            self._history.add_partial_assistant_message(ctx.partial_response)
            if self._on_transcript is not None:
                self._on_transcript(
                    "assistant",
                    ctx.partial_response + " [interrupted]",
                )
            logger.info(
                "Saved partial response (%d chars): %.60s...",
                len(ctx.partial_response),
                ctx.partial_response,
            )

        # 6. Reset.
        self._pipeline_ctx = PipelineContext()
        self._pipeline_task = None
        self._vad.reset()
        self._sentence_buffer = ""
        self._speech_active = False

        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info("Barge-in completed in %.1fms", elapsed_ms)

    # -- Graceful shutdown ------------------------------------------------

    async def _shutdown_pipeline(self) -> None:
        """Cancel any active pipeline during graceful shutdown."""
        if self._pipeline_task is None or self._pipeline_task.done():
            return

        self._playback.hard_stop()

        ctx = self._pipeline_ctx
        for task in (ctx.llm_task, ctx.tts_task, ctx.playback_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        self._pipeline_task.cancel()
        try:
            await self._pipeline_task
        except (asyncio.CancelledError, Exception):
            pass

        self._pipeline_ctx = PipelineContext()
        self._pipeline_task = None
        logger.info("Pipeline shut down")

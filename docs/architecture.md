# Architecture

This document describes the internal architecture of the Voice Conversation system with barge-in support and RAG-powered knowledge base.

## System Overview

```
+------------------------------- Voice Conversation System -------------------------------+
|                                                                                         |
|   +-----------+     +-----+     +-----+     +----------+     +-----+     +----------+   |
|   |   Audio   | --> | VAD | --> | STT | --> |   LLM    | --> | TTS | --> |  Audio   |   |
|   |  Capture  |     |     |     |     |     | (+ Tools)|     |     |     | Playback |   |
|   +-----------+     +-----+     +-----+     +----------+     +-----+     +----------+   |
|         ^                                        |                            |          |
|         |                                   +----v----+                       |          |
|         |                                   |   RAG   |                       |          |
|         |                                   | ChromaDB|                       |          |
|         |                                   +---------+                       |          |
|         |                                                                     |          |
|         +------ BARGE-IN: user speaks during THINKING/SPEAKING ----cancel-----+          |
|                                                                                         |
|   +-----------------------------  Controller (State Machine)  --------------------------+|
+-----------------------------------------------------------------------------------------+
```

The system runs as a single asyncio event loop. Audio capture feeds a VAD (Voice Activity Detection) processor. When speech is detected, the pipeline (STT -> LLM -> TTS -> Playback) is launched as concurrent asyncio Tasks connected by queues. If the user speaks during an active response, barge-in cancels the pipeline within ~50ms.

## State Machine

```
                    +------+
          +-------->| IDLE |<---------+
          |         +--+---+          |
          |            |              |
          |     [speech_started]      |
          |            |              |
          |         +--v-------+      |
          |         | LISTENING|      |
          |         +--+-------+      |
          |            |              |
          |     [speech_ended]   [playback done]
          |            |              |
          |      +-----v------+       |
          |      |TRANSCRIBING|       |
          |      +-----+------+       |
          |            |              |
          |       [STT done]          |
          |            |              |
          |       +----v---+     +----+----+
          |       |THINKING+---->|SPEAKING |
          |       +---+----+     +----+----+
          |           |               |
          |    [speech_started]  [speech_started]
          |           |               |
          |       +---v---------------v---+
          |       |       BARGE_IN        |
          |       |  (transient ~50ms)    |
          |       +-----------+-----------+
          |                   |
          +---[LISTENING]<----+
```

**States:**
- **IDLE** -- Waiting for the user to speak.
- **LISTENING** -- Buffering audio while the user speaks.
- **TRANSCRIBING** -- Sending buffered audio to STT (Whisper).
- **THINKING** -- LLM is generating a response (may include tool calls).
- **SPEAKING** -- TTS audio is being played back to the user.
- **BARGE_IN** -- Transient state: cancels the active pipeline, clears audio, then immediately transitions to LISTENING.

## Pipeline Architecture

When the user finishes speaking, three concurrent tasks are launched:

```
                  asyncio.Queue<str>            asyncio.Queue<bytes>
  +----------+                      +----------+                     +----------+
  |  LLM     |  --- sentences --->  |   TTS    |  --- PCM chunks --> | Playback |
  |  Task    |                      |   Task   |                     |   Task   |
  +----------+                      +----------+                     +----------+
       |
       |  (internal tool-call loop)
       v
  +---------+
  |   RAG   |
  | ChromaDB|
  +---------+
```

**Sentence buffering:** LLM tokens are accumulated until a sentence boundary (`.` `!` `?` + whitespace) is found. Complete sentences are pushed to the TTS queue. This reduces perceived latency -- TTS starts generating audio as soon as the first sentence is ready, while the LLM continues streaming.

**Tool calling:** When the LLM emits a tool call (e.g. `search_knowledge_base`), the tool-call loop happens entirely inside `LLMService.stream_response()`. The controller sees only text deltas -- tool calling is transparent.

## Dual Interface Architecture

The system supports two modes with the same controller logic:

```
  CLI Mode                              Web Mode
  --------                              --------

  +------------+                        +--------------+
  | sounddevice|                        |   Browser    |
  | microphone |                        |  (WebSocket) |
  +-----+------+                        +------+-------+
        |                                      |
  +-----v----------+                    +------v-----------+
  | AudioCapture   |                    | WebSocketAudio   |
  | (sounddevice)  |                    | Capture          |
  +-----+----------+                    +------+-----------+
        |     same interface                   |
        +----------+     +--------------------+
                   |     |
              +----v-----v----+
              |  Controller   |
              | (state machine|
              |  + pipeline)  |
              +----+-----+----+
                   |     |
        +----------+     +--------------------+
        |     same interface                   |
  +-----v----------+                    +------v-----------+
  | AudioPlayback  |                    | WebSocketAudio   |
  | (sounddevice)  |                    | Playback         |
  +-----+----------+                    +------+-----------+
        |                                      |
  +-----v------+                        +------v-------+
  | sounddevice|                        |   Browser    |
  | speaker    |                        |  (WebSocket) |
  +------------+                        +--------------+
```

Both audio implementations share the same interface:
- `start()` / `stop()` -- lifecycle
- `get_queue()` -- returns `asyncio.Queue[AudioChunk]` (capture)
- `play_chunks(queue)` -- consumes `asyncio.Queue[PCMBytes]` (playback)
- `hard_stop()` -- immediate silence for barge-in

## Barge-In Mechanism

Barge-in is the ability for the user to interrupt the assistant mid-response. It must be fast (<50ms perceived latency).

```
  Timeline during barge-in:

  t=0ms    VAD detects speech_started during SPEAKING
  t=0ms    Controller enters BARGE_IN state
  t=0ms    on_barge_in callback fires (notifies browser)
  t=0ms    playback.hard_stop():
              - Sets _muted flag (server stops sending audio)
              - Drains PCM queue
              - Sends audio_stop JSON to browser
  t=1ms    Cancel LLM task (stops token generation)
  t=2ms    Cancel TTS task (stops audio generation)
  t=3ms    Cancel Playback task
  t=5ms    Save partial response with [interrupted] marker
  t=5ms    Reset VAD state, sentence buffer
  t=5ms    Transition to LISTENING (start buffering new speech)

  Browser side (on receiving barge_in / LISTENING state):
  t=10ms   stopPlayback() -- cancel all scheduled AudioBufferSourceNodes
  t=10ms   Set playbackMuted flag -- drop any in-flight binary chunks
```

**Server-side (WebSocketAudioPlayback):**
- `hard_stop()` sets a `_muted` flag that `play_chunks()` checks before each `send_bytes()`.
- The PCM queue is drained synchronously so no buffered chunks leak through.

**Browser-side:**
- `stopPlayback()` calls `.stop()` on all scheduled Web Audio API sources.
- `playbackMuted` flag causes `playPCM()` to drop any binary chunks that arrive after barge-in.
- Triggered on both `barge_in` events and `LISTENING` state (covers the case where the server finished but the browser still has buffered audio).

## RAG Pipeline

```
  Indexing (on startup):

  data/knowledge_base/*.md
        |
        v
  +-----+------+
  | Chunk by   |  Split at H2 (##) headers, max 800 chars
  | sections   |
  +-----+------+
        |
        v
  +-----+--------+
  | Embed with   |  OpenAI text-embedding-3-small
  | OpenAI API   |
  +-----+--------+
        |
        v
  +-----+---------+
  | Store in      |  ChromaDB PersistentClient
  | ChromaDB      |  at data/chroma_db/
  +---------+-----+
            |
        (skip re-index if SHA-256 hash unchanged)


  Query (during conversation):

  User question
        |
        v
  +-----+------+
  |  LLM emits |  search_knowledge_base(query="...")
  |  tool call  |
  +-----+------+
        |
        v
  +-----+--------+
  | Embed query  |  Same embedding model
  +-----+--------+
        |
        v
  +-----+---------+
  | ChromaDB      |  Cosine similarity search, top 5
  | vector search |
  +-----+---------+
        |
        v
  +-----+--------+
  | Return chunks|  With source file, section, score
  | as JSON      |
  +-----+--------+
        |
        v
  +-----+------+
  | LLM uses   |  Generates answer citing sources
  | results to |  Suggests 2-3 follow-up questions
  | respond    |
  +-----+------+
```

**Tools available to the LLM:**
1. `search_knowledge_base(query)` -- Semantic search over the knowledge base.
2. `get_source_details(document_id)` -- Return metadata about a specific source document.

**Guardrails (system prompt):**
- Always search before answering NovaTech questions.
- Don't fabricate facts -- say "I don't know" if not in KB.
- Cite source documents naturally.
- Suggest 2-3 follow-up questions after each answer.

## WebSocket Protocol

```
  Browser                          Server
    |                                |
    |---- binary (float32 PCM) ---->|  Microphone audio (16 kHz, mono)
    |                                |
    |---- {"type": "start"} ------->|  Begin conversation
    |---- {"type": "stop"} -------->|  End conversation
    |                                |
    |<--- binary (int16 PCM) -------|  TTS audio (24 kHz, mono)
    |                                |
    |<-- {"type":"state",      -----|  State machine transitions
    |     "state":"LISTENING"}       |
    |                                |
    |<-- {"type":"transcript",  ----|  User/assistant text
    |     "role":"user",             |
    |     "text":"Hello"}            |
    |                                |
    |<-- {"type":"barge_in"}    ----|  User interrupted
    |                                |
    |<-- {"type":"audio_stop"}  ----|  Clear audio buffers
    |                                |
```

Each WebSocket connection gets its own `ConversationController` instance with independent state. The RAG knowledge base is shared (read-only) across all sessions, initialized once at server startup.

## Directory Structure

```
barge-in-poc/
├── src/
│   ├── main.py                  # CLI entry point
│   ├── web_main.py              # Web server entry point (uvicorn)
│   ├── controller.py            # State machine + pipeline orchestration
│   ├── config.py                # Frozen dataclass configurations
│   ├── types.py                 # Shared types (AudioChunk, ConversationState, etc.)
│   ├── conversation.py          # Message history with auto-trimming
│   ├── utils.py                 # Retry decorator, logging setup
│   ├── audio/
│   │   ├── capture.py           # Mic input via sounddevice (CLI)
│   │   ├── playback.py          # Speaker output via sounddevice (CLI)
│   │   └── vad.py               # Silero VAD wrapper
│   ├── services/
│   │   ├── stt.py               # Whisper speech-to-text
│   │   ├── llm.py               # GPT-4o streaming + tool calling
│   │   ├── tts.py               # OpenAI TTS streaming PCM
│   │   ├── rag.py               # ChromaDB knowledge base
│   │   └── tools.py             # Tool definitions + executor
│   └── web/
│       ├── server.py            # FastAPI + WebSocket endpoint
│       ├── audio_capture.py     # Browser audio → asyncio.Queue
│       ├── audio_playback.py    # asyncio.Queue → browser WebSocket
│       └── static/index.html    # Single-page frontend
├── data/
│   └── knowledge_base/          # Markdown docs (NovaTech sample dataset)
├── docs/                        # Documentation
├── pyproject.toml               # Dependencies and build config
└── CLAUDE.md                    # Developer reference
```

## Key Design Decisions

1. **Asyncio-first** -- All I/O is async. sounddevice callbacks bridge to asyncio via `loop.call_soon_threadsafe()`. No threads are used for pipeline logic.

2. **CancelledError propagation** -- `CancelledError` is never caught (only re-raised). This ensures clean barge-in cancellation through the entire pipeline. The `@with_retry` decorator also re-raises it.

3. **Sentence buffering** -- Instead of sending each LLM token to TTS individually, tokens are buffered into complete sentences. This reduces TTS API calls and produces more natural-sounding speech.

4. **Interface-based audio** -- CLI and web modes use the same controller by swapping AudioCapture/AudioPlayback implementations. No `if web_mode:` conditionals in the controller.

5. **Tool calling encapsulation** -- The LLM's tool-call loop (call tool -> get result -> re-query LLM) is fully contained within `LLMService.stream_response()`. The controller sees only text deltas, making RAG transparent to the pipeline.

6. **Shared knowledge base** -- In web mode, the ChromaDB knowledge base is initialized once at startup and shared read-only across all WebSocket sessions. Each session gets its own `ToolExecutor` pointing to the shared KB.

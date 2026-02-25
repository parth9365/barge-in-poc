# Voice Conversation with Barge-In Support

A real-time voice conversation system that lets users interrupt the assistant mid-response. The assistant stops speaking immediately (<50ms) and begins listening to the new input.

Two interfaces are available: a **CLI mode** (local microphone and speaker) and a **Web mode** (browser-based via WebSocket).

## How It Works

### Pipeline

```
Mic → VAD (Silero) → STT (Whisper) → LLM (GPT-4o-mini streaming) → TTS (streaming PCM) → Speaker
```

1. **Audio Capture** — Microphone input is captured at 16kHz in 32ms chunks.
2. **Voice Activity Detection** — Each chunk is passed through Silero VAD to detect when the user starts and stops speaking.
3. **Speech-to-Text** — Once speech ends, the buffered audio is sent to OpenAI Whisper for transcription.
4. **LLM Response** — The transcript is streamed to GPT-4o-mini. Tokens are buffered into complete sentences before being sent to TTS to reduce perceived latency.
5. **Text-to-Speech** — Each sentence is streamed through OpenAI TTS, producing raw PCM audio.
6. **Playback** — PCM audio is played back at 24kHz through the speaker (or sent to the browser over WebSocket).

### Barge-In

If the user speaks while the assistant is in the **THINKING** or **SPEAKING** state, barge-in is triggered:

1. Playback is hard-stopped (user hears silence immediately).
2. The LLM, TTS, and playback tasks are cancelled.
3. The partial response is saved to conversation history with an `[interrupted]` marker.
4. VAD state is reset and the system begins listening to the new utterance.

The entire cancellation completes in under 50ms.

### State Machine

```
IDLE → LISTENING → TRANSCRIBING → THINKING → SPEAKING → IDLE
                                       ↑          ↑
                                       └── BARGE_IN ──→ LISTENING
```

`BARGE_IN` is a transient state — it executes cancellation and immediately transitions to `LISTENING`.

## Configuring VAD and Barge-In

VAD behavior is controlled through `VADConfig` in `src/config.py`:

| Parameter | Default | Description |
|---|---|---|
| `threshold` | `0.3` | Speech probability (0.0–1.0) above which a chunk is classified as speech. Lower values make detection more sensitive — better for quiet environments. Higher values reduce false triggers in noisy settings. |
| `min_silence_duration_ms` | `300` | Milliseconds of consecutive silence required before `speech_ended` fires. Lower values make the system more responsive but may split a single utterance into multiple segments. Higher values tolerate natural pauses. |
| `speech_pad_ms` | `30` | Padding added around speech segments internally by Silero. |

To override defaults, construct a `VADConfig` with your values and pass it to `VADProcessor`:

```python
from src.config import VADConfig

vad_config = VADConfig(
    threshold=0.5,              # less sensitive, fewer false triggers
    min_silence_duration_ms=500, # wait longer before ending speech
)
```

**Barge-in requires no separate configuration.** It activates automatically whenever VAD detects `speech_started` during the `THINKING` or `SPEAKING` states. The speed of barge-in depends on VAD sensitivity — a lower `threshold` means the system detects interruptions faster.

## Running Locally

### Prerequisites

- Python 3.11+
- An OpenAI API key
- A working microphone and speaker (for CLI mode)

### Setup

```bash
# Clone the repository
git clone <repo-url>
cd barge-in-poc

# Install in editable mode
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

### CLI Mode

Uses your local microphone and speaker directly:

```bash
python -m src.main
```

Speak into your microphone. The assistant will respond through your speaker. Interrupt at any time by speaking again.

### Web Mode

Runs a FastAPI server with a browser-based UI:

```bash
python -m src.web_main
```

Open `http://localhost:8000` in your browser. Click to start, then speak. Audio streams over WebSocket — each connection gets its own conversation session.

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run a specific test
pytest tests/test_specific.py::test_name
```

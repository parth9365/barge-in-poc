"""Entry point for the web-based Voice Conversation POC.

Starts a FastAPI/uvicorn server that serves the browser UI and handles
audio streaming over WebSocket.

Usage::

    python -m src.web_main
"""

from __future__ import annotations

import uvicorn

from src.utils import setup_logging


def main() -> None:
    setup_logging()
    print(
        "\nVoice Conversation POC -- Web UI\n"
        "================================\n"
        "Open http://localhost:8000 in your browser\n"
        "Using headphones is recommended to avoid echo feedback.\n"
    )
    uvicorn.run(
        "src.web.server:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()

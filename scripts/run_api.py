"""Run the HTTP API with uvicorn.

    python scripts/run_api.py

Reads API_HOST / API_PORT from .env (or environment). Defaults: 0.0.0.0:8000.
Set API_KEYS to a comma-separated list of accepted keys before starting:

    API_KEYS=key-for-caller-A,key-for-caller-B

For production, prefer running uvicorn directly with --workers > 1 after
moving the JobManager out of in-memory storage (otherwise jobs visible to
one worker are invisible to another).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow `python scripts/run_api.py` without editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

import uvicorn  # noqa: E402


def main() -> None:
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))

    if not os.getenv("API_KEYS", "").strip():
        raise SystemExit(
            "API_KEYS env var is empty. Put at least one key in your .env file, "
            "e.g. API_KEYS=" + os.urandom(16).hex()
        )

    uvicorn.run(
        "insta_batch.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()

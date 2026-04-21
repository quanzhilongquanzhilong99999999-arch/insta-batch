"""Rich-backed structured logging."""
from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler

from insta_batch.core.config import LOGS_DIR


def setup_logging(level: str = "INFO", log_file: str | None = "insta_batch.log") -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [
        RichHandler(rich_tracebacks=True, show_time=True, show_path=False)
    ]
    if log_file:
        fh = logging.FileHandler(LOGS_DIR / log_file, encoding="utf-8")
        fh.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        handlers.append(fh)

    logging.basicConfig(
        level=level.upper(),
        format="%(message)s",
        datefmt="[%X]",
        handlers=handlers,
        force=True,
    )

    for noisy in ("aiohttp.access", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

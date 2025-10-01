"""Logging configuration helper."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"


def configure_logging(level: int = logging.INFO, max_bytes: int = 1_000_000, backups: int = 5) -> None:
    """Configure a rotating file handler for application logging."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(LOG_FILE, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)


__all__ = ["configure_logging", "LOG_FILE"]

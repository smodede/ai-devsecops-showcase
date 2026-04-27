"""
Shared utilities for AI DevSecOps Showcase.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone


def configure_logging(level: str | None = None) -> None:
    """Configure root logger with a consistent format."""
    level = level or os.environ.get("LOG_LEVEL", "INFO")
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def truncate(text: str, max_chars: int = 500) -> str:
    """Truncate a string to max_chars, adding an ellipsis if needed."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


def chunk_list(lst: list, size: int) -> list[list]:
    """Split a list into chunks of at most `size` items."""
    return [lst[i : i + size] for i in range(0, len(lst), size)]


def parse_pipeline_ids(raw: str) -> list[int]:
    """
    Parse a comma-separated string of pipeline IDs into a list of ints.

    Empty string or whitespace-only input returns an empty list.
    """
    if not raw or not raw.strip():
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]

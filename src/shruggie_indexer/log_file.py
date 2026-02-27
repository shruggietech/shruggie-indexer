"""Persistent log file support for shruggie-indexer.

Resolves the platform-appropriate log directory and provides a factory
for creating ``logging.FileHandler`` instances with the correct format.

See spec SS11.1 — Logging Architecture.
"""

from __future__ import annotations

import logging
import os
import platform
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "get_default_log_dir",
    "make_file_handler",
]


def get_default_log_dir() -> Path:
    """Return the platform-appropriate log directory.

    | Platform | Directory |
    |----------|-----------|
    | Windows  | ``%LOCALAPPDATA%\\ShruggieTech\\shruggie-indexer\\logs\\`` |
    | macOS    | ``~/Library/Application Support/ShruggieTech/shruggie-indexer/logs/`` |
    | Linux    | ``~/.local/share/shruggie-indexer/logs/`` |
    """
    system = platform.system()
    if system == "Windows":
        base = Path(
            os.environ.get(
                "LOCALAPPDATA",
                Path.home() / "AppData" / "Local",
            ),
        )
        return base / "ShruggieTech" / "shruggie-indexer" / "logs"
    if system == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "ShruggieTech"
            / "shruggie-indexer"
            / "logs"
        )
    # Linux and other POSIX
    base = Path(
        os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"),
    )
    return base / "shruggie-indexer" / "logs"


def _generate_log_filename() -> str:
    """Generate a log filename from the current UTC time: ``YYYY-MM-DD_HHMMSS.log``."""
    now = datetime.now(tz=UTC).astimezone()
    return now.strftime("%Y-%m-%d_%H%M%S") + ".log"


def make_file_handler(
    log_path: Path | None = None,
    *,
    session_id: str = "",
) -> logging.FileHandler:
    """Create a ``FileHandler`` for persistent log file output.

    Args:
        log_path: Explicit path for the log file.  When ``None``, the
            default app data directory is used with an auto-generated
            timestamped filename.
        session_id: Session identifier included in the log format.

    Returns:
        A configured ``logging.FileHandler`` ready to be attached to a
        logger.
    """
    if log_path is None:
        log_dir = get_default_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / _generate_log_filename()
    else:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(log_path, encoding="utf-8")

    # Format matches the CLI's verbose stderr format with session ID
    if session_id:
        fmt = f"%(asctime)s  {session_id}  %(levelname)-9s %(name)s  %(message)s"
    else:
        fmt = "%(asctime)s  %(levelname)-9s %(name)s  %(message)s"

    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    return handler

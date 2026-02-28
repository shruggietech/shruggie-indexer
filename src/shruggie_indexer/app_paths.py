"""Canonical application data paths for shruggie-indexer.

Every module that needs to read or write to the application data
directory MUST import from this module.  Do not resolve paths
independently.

See spec §3.3 for the full specification.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

__all__ = [
    "get_app_data_dir",
    "get_log_dir",
]

_ECOSYSTEM_DIR = "shruggie-tech"
_TOOL_DIR = "shruggie-indexer"


def get_app_data_dir() -> Path:
    """Return the canonical application data directory.

    All tool-generated data (session files, configuration, logs)
    lives under this directory or its subdirectories.

    | Platform | Path |
    |----------|------|
    | Windows  | ``%LOCALAPPDATA%\\shruggie-tech\\shruggie-indexer`` |
    | macOS    | ``~/Library/Application Support/shruggie-tech/shruggie-indexer`` |
    | Linux    | ``~/.config/shruggie-tech/shruggie-indexer`` |
    """
    system = platform.system()
    if system == "Windows":
        base = Path(
            os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"),
        )
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"),
        )
    return base / _ECOSYSTEM_DIR / _TOOL_DIR


def get_log_dir() -> Path:
    """Return the log file directory: ``<app_data_dir>/logs/``."""
    return get_app_data_dir() / "logs"

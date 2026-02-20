"""Progress reporting event type for shruggie-indexer.

The ``ProgressEvent`` dataclass is the communication contract between the
core engine (``build_directory_entry``) and its callers (CLI, GUI, API).
It is part of the public API surface (spec section 9.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["ProgressEvent"]


@dataclass
class ProgressEvent:
    """Progress report emitted during directory indexing (spec section 9.4).

    Attributes:
        phase: One of ``"discovery"``, ``"processing"``, ``"output"``,
            ``"cleanup"``.
        items_total: Total items discovered.  ``None`` during the initial
            discovery phase before counts are known.
        items_completed: Number of items processed so far (0 during discovery).
        current_path: Item currently being processed, or ``None``.
        message: Optional human-readable log message.
        level: Log level hint: ``"info"``, ``"warning"``, ``"error"``,
            ``"debug"``.
    """

    phase: str
    items_total: int | None
    items_completed: int
    current_path: Path | None
    message: str | None
    level: str

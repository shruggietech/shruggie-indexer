"""Filesystem timestamp extraction for shruggie-indexer.

Extracts filesystem timestamps from ``os.stat_result`` objects and produces
both Unix-millisecond integers and ISO 8601 formatted strings for each of
the three standard timestamp types: accessed, created, and modified.

The output populates the ``timestamps`` field of the v2 schema
(``TimestampsObject`` containing three ``TimestampPair`` values).

See spec §6.5 and §15.5 for full behavioral guidance.

Deviation from original (DEV-07): Unix timestamps are derived directly from
``os.stat()`` float values — no intermediate string representation, no
round-trip parsing, and ``Date2UnixTime`` is eliminated entirely.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os

from shruggie_indexer.models.schema import TimestampPair, TimestampsObject

__all__ = [
    "extract_timestamps",
]

logger = logging.getLogger(__name__)

# Track whether we've already logged the st_birthtime fallback warning.
_birthtime_fallback_logged: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_creation_time(stat_result: os.stat_result) -> float:
    """Return the best available creation timestamp.

    Attempts ``st_birthtime`` first (available on Windows, macOS, and
    Linux kernel 4.11+ with Python 3.12+).  Falls back to ``st_ctime``
    (which is the inode change time on Linux/macOS, but the creation time
    on Windows).

    See §15.5 — Creation Time Portability.
    """
    global _birthtime_fallback_logged

    try:
        return stat_result.st_birthtime  # type: ignore[attr-defined]
    except AttributeError:
        if not _birthtime_fallback_logged:
            logger.debug(
                "st_birthtime unavailable on this platform; "
                "using st_ctime as creation time approximation"
            )
            _birthtime_fallback_logged = True
        return stat_result.st_ctime


def _stat_to_iso(timestamp_float: float) -> str:
    """Convert a stat timestamp float to an ISO 8601 string.

    Produces a string with microsecond precision and local timezone offset,
    e.g. ``2024-03-15T14:30:22.123456-04:00``.

    The original's .NET format produces 7-digit fractional seconds; Python's
    ``datetime`` provides 6 digits (microseconds).  This is an acceptable
    deviation — the 7th digit is always zero in practice for filesystem
    timestamps.
    """
    dt = datetime.fromtimestamp(timestamp_float, tz=UTC).astimezone()
    return dt.isoformat(timespec="microseconds")


def _stat_to_unix_ms(timestamp_float: float) -> int:
    """Convert a stat timestamp float (seconds) to integer milliseconds."""
    return int(timestamp_float * 1000)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_timestamps(
    stat_result: os.stat_result,
    *,
    is_symlink: bool = False,
) -> TimestampsObject:
    """Derive all timestamps from an ``os.stat_result``.

    Returns a :class:`~shruggie_indexer.models.schema.TimestampsObject`
    containing accessed, created, and modified
    :class:`~shruggie_indexer.models.schema.TimestampPair` values, each
    with both ISO 8601 and Unix millisecond representations.

    Args:
        stat_result: The stat result, from ``os.stat()`` (regular items) or
            ``os.lstat()`` (symlinks).
        is_symlink: Informational flag indicating the stat_result originates
            from ``os.lstat()``.  Currently unused but reserved for future
            symlink-specific timestamp handling.

    Returns:
        A fully populated ``TimestampsObject``.
    """
    creation_time = _get_creation_time(stat_result)

    accessed = TimestampPair(
        iso=_stat_to_iso(stat_result.st_atime),
        unix=_stat_to_unix_ms(stat_result.st_atime),
    )
    created = TimestampPair(
        iso=_stat_to_iso(creation_time),
        unix=_stat_to_unix_ms(creation_time),
    )
    modified = TimestampPair(
        iso=_stat_to_iso(stat_result.st_mtime),
        unix=_stat_to_unix_ms(stat_result.st_mtime),
    )

    return TimestampsObject(
        accessed=accessed,
        created=created,
        modified=modified,
    )

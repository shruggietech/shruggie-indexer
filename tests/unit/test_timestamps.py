"""Unit tests for core/timestamps.py — §6.5 Filesystem Timestamps.

6 test cases per §14.2.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from types import SimpleNamespace

from shruggie_indexer.core.timestamps import extract_timestamps

# ISO 8601 pattern: YYYY-MM-DDTHH:MM:SS with optional fractional seconds
# and timezone offset.
_ISO_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)$"
)


def _make_stat(
    *,
    st_atime: float = 1700000000.0,
    st_mtime: float = 1700000000.0,
    st_ctime: float = 1700000000.0,
    st_birthtime: float | None = None,
) -> os.stat_result:
    """Build a mock stat_result with the given timestamp values.

    On Windows, real ``os.stat_result`` always has ``st_birthtime``.
    We simulate platform differences by conditionally adding the attribute.
    """
    # os.stat_result cannot be directly instantiated with keyword args in all
    # contexts.  We create a surrogate object that behaves identically for
    # timestamp access.
    fields = {
        "st_atime": st_atime,
        "st_mtime": st_mtime,
        "st_ctime": st_ctime,
    }
    if st_birthtime is not None:
        fields["st_birthtime"] = st_birthtime

    # Use a SimpleNamespace as a duck-type replacement.
    return SimpleNamespace(**fields)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtractTimestamps:
    """Tests for extract_timestamps()."""

    def test_mtime_extraction(self, sample_file: Path) -> None:
        """modified.unix == int(st_mtime * 1000)."""
        stat = os.stat(sample_file)
        result = extract_timestamps(stat)
        assert result.modified.unix == int(stat.st_mtime * 1000)
        assert _ISO_PATTERN.match(result.modified.iso)

    def test_atime_extraction(self, sample_file: Path) -> None:
        """accessed.unix and accessed.iso consistent with st_atime."""
        stat = os.stat(sample_file)
        result = extract_timestamps(stat)
        assert result.accessed.unix == int(stat.st_atime * 1000)
        assert _ISO_PATTERN.match(result.accessed.iso)

    def test_creation_time_present(self) -> None:
        """When st_birthtime exists, created timestamp uses it."""
        stat = _make_stat(st_birthtime=1600000000.5, st_ctime=1700000000.0)
        result = extract_timestamps(stat)
        assert result.created.unix == int(1600000000.5 * 1000)

    def test_creation_time_fallback(self) -> None:
        """When st_birthtime is absent, falls back to st_ctime."""
        stat = _make_stat(st_ctime=1700000000.0)  # no st_birthtime
        result = extract_timestamps(stat)
        assert result.created.unix == int(1700000000.0 * 1000)

    def test_iso_format(self) -> None:
        """ISO strings match YYYY-MM-DDTHH:MM:SS pattern with timezone."""
        stat = _make_stat(st_birthtime=1700000000.123)
        result = extract_timestamps(stat)
        assert _ISO_PATTERN.match(result.accessed.iso)
        assert _ISO_PATTERN.match(result.created.iso)
        assert _ISO_PATTERN.match(result.modified.iso)

    def test_unix_milliseconds(self) -> None:
        """st_mtime=1700000000.123 -> unix=1700000000123 (integer ms)."""
        stat = _make_stat(st_mtime=1700000000.123, st_birthtime=1700000000.0)
        result = extract_timestamps(stat)
        assert result.modified.unix == 1700000000123

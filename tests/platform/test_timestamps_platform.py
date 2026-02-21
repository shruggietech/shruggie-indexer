"""Platform-specific timestamp tests for shruggie-indexer.

Validates that the creation-time extraction strategy described in §15.5
behaves correctly on each target platform.  Uses the double-marker pattern
from §14.5: a pytest marker for CI filtering *and* a ``skipif`` guard for
auto-skip on non-applicable platforms.
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shruggie_indexer.core.timestamps import _get_creation_time, extract_timestamps

is_windows = sys.platform == "win32"
is_linux = sys.platform == "linux"
is_macos = sys.platform == "darwin"


# ---------------------------------------------------------------------------
# Test 1: st_birthtime availability on macOS / Windows
# ---------------------------------------------------------------------------


@pytest.mark.platform_macos
@pytest.mark.skipif(not is_macos, reason="macOS-only: st_birthtime always available on APFS/HFS+")
def test_birthtime_available_macos(tmp_path: Path) -> None:
    """On macOS, ``st_birthtime`` must be a real attribute of stat results."""
    p = tmp_path / "probe.txt"
    p.write_text("macos birthtime probe", encoding="utf-8")
    stat = p.stat()
    assert hasattr(stat, "st_birthtime"), "st_birthtime missing on macOS"
    # The creation time should be a positive float.
    assert stat.st_birthtime > 0


@pytest.mark.platform_windows
@pytest.mark.skipif(not is_windows, reason="Windows-only: st_birthtime available on Python 3.12+")
def test_birthtime_available_windows(tmp_path: Path) -> None:
    """On Windows with Python 3.12+, ``st_birthtime`` is available.

    Even on older Python where ``st_birthtime`` might not exist, Windows
    ``st_ctime`` IS the creation time (NTFS semantics), so the fallback
    is semantically identical.
    """
    p = tmp_path / "probe.txt"
    p.write_text("windows birthtime probe", encoding="utf-8")
    stat = p.stat()
    # On Python 3.12+ / Windows, st_birthtime should exist.
    # On older Python, st_ctime is semantically equivalent on NTFS.
    creation = _get_creation_time(stat)
    assert creation > 0
    # Whichever source was used, the value must be close to st_ctime on
    # Windows (they're the same underlying NTFS field).
    assert abs(creation - stat.st_ctime) < 1.0


# ---------------------------------------------------------------------------
# Test 2: st_ctime fallback on Linux
# ---------------------------------------------------------------------------


@pytest.mark.platform_linux
@pytest.mark.skipif(not is_linux, reason="Linux-only: st_birthtime may be unavailable")
def test_ctime_fallback_linux(tmp_path: Path) -> None:
    """On Linux, ``_get_creation_time`` should return a value even when
    ``st_birthtime`` is unavailable (e.g. on tmpfs, older kernels, or
    Python < 3.12).

    The returned value is guaranteed non-zero regardless of whether the
    platform provides true birth time or falls back to inode change time.
    """
    p = tmp_path / "probe.txt"
    p.write_text("linux ctime probe", encoding="utf-8")
    stat = p.stat()
    creation = _get_creation_time(stat)
    assert creation > 0
    # On Linux, if st_birthtime is missing, we get st_ctime.
    # Both are valid positive floats — no further semantic assertion is
    # possible without knowing the kernel/FS combination.
    assert isinstance(creation, float)


# ---------------------------------------------------------------------------
# Test 3: Creation time accuracy
# ---------------------------------------------------------------------------


def test_creation_time_accuracy(tmp_path: Path) -> None:
    """The extracted creation time must be within 2 seconds of ``now``.

    This is a cross-platform sanity check: the file is created during the
    test, so its creation time should be extremely close to the current
    wall-clock time.  A 2-second tolerance accounts for filesystem flush
    delays and test runner overhead.
    """
    before = time.time()
    p = tmp_path / "accuracy.txt"
    p.write_text("accuracy probe", encoding="utf-8")
    after = time.time()

    stat = p.stat()
    creation = _get_creation_time(stat)
    assert before - 1.0 <= creation <= after + 1.0, (
        f"Creation time {creation} not within tolerance of "
        f"[{before - 1.0}, {after + 1.0}]"
    )


# ---------------------------------------------------------------------------
# Test 4: Timezone handling
# ---------------------------------------------------------------------------


def test_timestamp_timezone_handling(tmp_path: Path) -> None:
    """ISO timestamps produced by ``extract_timestamps`` must include a
    timezone offset (not be naive) and the Unix millisecond values must
    be positive integers.
    """
    p = tmp_path / "tz_probe.txt"
    p.write_text("timezone probe", encoding="utf-8")
    stat = p.stat()
    ts = extract_timestamps(stat)

    for pair_name in ("accessed", "created", "modified"):
        pair = getattr(ts, pair_name)
        # ISO string must contain a timezone offset ('+' or '-' or 'Z').
        iso = pair.iso
        assert ("+" in iso or "-" in iso[10:] or iso.endswith("Z")), (
            f"timestamps.{pair_name}.iso missing timezone offset: {iso}"
        )
        # Unix ms must be a positive integer.
        assert isinstance(pair.unix, int)
        assert pair.unix > 0, f"timestamps.{pair_name}.unix is not positive: {pair.unix}"

    # Cross-check: created ISO should parse to a datetime close to the
    # Unix ms value (within 1 second tolerance).
    created_dt = datetime.fromisoformat(ts.created.iso)
    created_from_unix = datetime.fromtimestamp(ts.created.unix / 1000, tz=UTC)
    delta = abs((created_dt - created_from_unix).total_seconds())
    assert delta < 1.0, f"ISO/Unix mismatch for created: delta={delta}s"

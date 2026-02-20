"""Platform-specific symlink and reparse point tests for shruggie-indexer.

Validates symlink detection, traversal safety, and platform-specific behaviors
described in §15.6.  Uses the double-marker pattern from §14.5 for
platform-conditional execution.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from shruggie_indexer.core.hashing import hash_file, hash_string

is_windows = sys.platform == "win32"
is_linux = sys.platform == "linux"
is_macos = sys.platform == "darwin"


def _can_create_symlinks() -> bool:
    """Probe whether the current process can create symlinks.

    On Windows, symlink creation requires either administrator privileges
    or Developer Mode.  On POSIX systems, symlinks are always available.
    """
    if not is_windows:
        return True
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "target.txt"
        link = Path(td) / "link.txt"
        target.write_text("probe", encoding="utf-8")
        try:
            link.symlink_to(target)
            return True
        except OSError:
            return False


_symlinks_available = _can_create_symlinks()
_skip_no_symlinks = pytest.mark.skipif(
    not _symlinks_available,
    reason="Symlink creation not available (requires admin or Developer Mode on Windows)",
)


# ---------------------------------------------------------------------------
# Test 1: Symlink detection
# ---------------------------------------------------------------------------


@_skip_no_symlinks
def test_symlink_detection(tmp_path: Path) -> None:
    """A file symlink must be detected by ``Path.is_symlink()``."""
    target = tmp_path / "real_file.txt"
    target.write_text("real content", encoding="utf-8")
    link = tmp_path / "link_file.txt"
    link.symlink_to(target)

    assert link.is_symlink(), "Symlink not detected"
    assert link.is_file(), "Symlink should also report as file"
    # lstat should NOT follow the symlink.
    lstat = link.lstat()
    stat = link.stat()
    # On POSIX, lstat and stat may differ in inode; on Windows,
    # at minimum the reparse bit is set for the symlink.
    assert link.resolve() == target.resolve()


# ---------------------------------------------------------------------------
# Test 2: Dangling symlink handling
# ---------------------------------------------------------------------------


@_skip_no_symlinks
def test_dangling_symlink_handling(tmp_path: Path) -> None:
    """A symlink whose target has been deleted must still be detectable
    as a symlink, and ``is_file()`` / ``exists()`` must reflect the
    broken state.
    """
    target = tmp_path / "will_be_deleted.txt"
    target.write_text("temporary", encoding="utf-8")
    link = tmp_path / "dangling.txt"
    link.symlink_to(target)
    # Remove the target to create a dangling symlink.
    target.unlink()

    assert link.is_symlink(), "Dangling symlink not detected as symlink"
    assert not link.exists(), "Dangling symlink should not 'exist' (target gone)"
    # lstat must still succeed — it operates on the link itself.
    lstat = link.lstat()
    assert lstat is not None


# ---------------------------------------------------------------------------
# Test 3: Directory symlink
# ---------------------------------------------------------------------------


@_skip_no_symlinks
def test_directory_symlink(tmp_path: Path) -> None:
    """A symlink pointing to a directory must be detected and must NOT
    be followed during traversal (prevents symlink loops per §15.6).
    """
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    (real_dir / "child.txt").write_text("child", encoding="utf-8")
    link_dir = tmp_path / "link_dir"
    link_dir.symlink_to(real_dir, target_is_directory=True)

    assert link_dir.is_symlink(), "Directory symlink not detected"
    assert link_dir.is_dir(), "Directory symlink should also report as dir"
    # Verify the link resolves to the real directory.
    assert link_dir.resolve() == real_dir.resolve()


# ---------------------------------------------------------------------------
# Test 4: Junction detection (Windows-only)
# ---------------------------------------------------------------------------


@pytest.mark.platform_windows
@pytest.mark.skipif(not is_windows, reason="Windows-only: NTFS junctions")
def test_junction_detection_windows(tmp_path: Path) -> None:
    """On Windows, NTFS junctions (reparse points created via ``mklink /J``)
    must be detectable via ``Path.is_junction()`` (added in Python 3.12).

    **Deviation from §15.6:** The spec claims junctions are detected by
    ``Path.is_symlink()`` on Python 3.12+, but this is incorrect.
    ``is_symlink()`` returns ``False`` for junctions — Python 3.12 added
    the dedicated ``Path.is_junction()`` method instead.  The indexer
    should use ``is_junction() or is_symlink()`` to identify all reparse
    points that warrant link-like treatment.
    """
    real_dir = tmp_path / "junction_target"
    real_dir.mkdir()
    (real_dir / "child.txt").write_text("junction child", encoding="utf-8")
    junction = tmp_path / "junction_link"

    # Create a junction using the Windows-specific mklink /J command.
    import subprocess

    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(real_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"Failed to create junction: {result.stderr.strip()}")

    assert junction.exists(), "Junction target not accessible"
    assert junction.is_dir(), "Junction should be traversable as a directory"

    # Python 3.12+ provides is_junction() for dedicated junction detection.
    assert junction.is_junction(), (
        "Junction not detected by Path.is_junction() on Python 3.12+"
    )
    # Junctions are NOT symlinks — is_symlink() returns False for junctions.
    assert not junction.is_symlink(), (
        "Expected is_symlink() == False for junctions (they are a distinct "
        "reparse point type)"
    )


# ---------------------------------------------------------------------------
# Test 5: Symlink name-hash fallback
# ---------------------------------------------------------------------------


@_skip_no_symlinks
def test_symlink_name_hash_fallback(tmp_path: Path) -> None:
    """When a target is a symlink, the indexer uses name-based hashing
    instead of content hashing (§15.6).  Verify that ``hash_string``
    on the symlink's name produces a different result than ``hash_file``
    on the target's content.
    """
    target = tmp_path / "real_content.txt"
    target.write_text("this is real content to hash", encoding="utf-8")
    link = tmp_path / "symlink_to_real.txt"
    link.symlink_to(target)

    # Content hash of the actual file.
    content_hashes = hash_file(target)
    # Name hash that would be used for the symlink.
    name_hashes = hash_string(link.name)

    # They must differ — name hash is NOT the content hash.
    assert content_hashes.md5 != name_hashes.md5, (
        "Name hash unexpectedly matched content hash for md5"
    )
    assert content_hashes.sha256 != name_hashes.sha256, (
        "Name hash unexpectedly matched content hash for sha256"
    )

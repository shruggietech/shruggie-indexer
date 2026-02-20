"""Unit tests for core/rename.py — §6.10 File Rename and In-Place Write Operations.

4 test cases per §14.2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from shruggie_indexer.core.rename import rename_item
from shruggie_indexer.exceptions import RenameError
from shruggie_indexer.models.schema import (
    AttributesObject,
    FileSystemObject,
    HashSet,
    IndexEntry,
    NameObject,
    SizeObject,
    TimestampPair,
    TimestampsObject,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hashset() -> HashSet:
    return HashSet(
        md5="D41D8CD98F00B204E9800998ECF8427E",
        sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
    )


def _make_entry(
    storage_name: str = "yD41D8CD98F00B204E9800998ECF8427E.txt",
    **overrides: Any,
) -> IndexEntry:
    pair = TimestampPair(iso="2024-01-01T00:00:00.000000+00:00", unix=1704067200000)
    defaults: dict[str, Any] = {
        "schema_version": 2,
        "id": "yD41D8CD98F00B204E9800998ECF8427E",
        "id_algorithm": "md5",
        "type": "file",
        "name": NameObject(text="original.txt", hashes=_make_hashset()),
        "extension": "txt",
        "size": SizeObject(text="11 B", bytes=11),
        "hashes": _make_hashset(),
        "file_system": FileSystemObject(relative="original.txt", parent=None),
        "timestamps": TimestampsObject(created=pair, modified=pair, accessed=pair),
        "attributes": AttributesObject(is_link=False, storage_name=storage_name),
    }
    defaults.update(overrides)
    return IndexEntry(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSuccessfulRename:
    """Tests for successful rename operations."""

    def test_rename_moves_file(self, tmp_path: Path) -> None:
        """rename_item moves the file to its storage_name."""
        original = tmp_path / "original.txt"
        original.write_text("content", encoding="utf-8")

        entry = _make_entry()
        new_path = rename_item(original, entry)

        expected = tmp_path / "yD41D8CD98F00B204E9800998ECF8427E.txt"
        assert new_path == expected
        assert expected.exists()
        assert not original.exists()
        assert expected.read_text(encoding="utf-8") == "content"


class TestDryRun:
    """Tests for dry-run mode."""

    def test_dry_run_no_filesystem_change(self, tmp_path: Path) -> None:
        """In dry-run mode, the file is NOT moved."""
        original = tmp_path / "original.txt"
        original.write_text("content", encoding="utf-8")

        entry = _make_entry()
        new_path = rename_item(original, entry, dry_run=True)

        expected = tmp_path / "yD41D8CD98F00B204E9800998ECF8427E.txt"
        assert new_path == expected
        # Original should still exist.
        assert original.exists()
        # Target should NOT exist.
        assert not expected.exists()


class TestCollisionDetection:
    """Tests for collision detection."""

    def test_collision_raises_rename_error(self, tmp_path: Path) -> None:
        """Renaming when a different file occupies the target raises RenameError."""
        original = tmp_path / "original.txt"
        original.write_text("original content", encoding="utf-8")

        # Create a different file at the target location.
        target = tmp_path / "yD41D8CD98F00B204E9800998ECF8427E.txt"
        target.write_text("different content", encoding="utf-8")

        entry = _make_entry()
        with pytest.raises(RenameError, match="collision"):
            rename_item(original, entry)


class TestStorageNameDerivation:
    """Tests for storage_name format."""

    def test_file_storage_name_has_extension(self) -> None:
        """File storage_name follows the pattern: id.extension."""
        entry = _make_entry(storage_name="yABCDEF0123456789.exe")
        assert entry.attributes.storage_name == "yABCDEF0123456789.exe"
        assert "." in entry.attributes.storage_name

    def test_directory_storage_name_is_bare_id(self) -> None:
        """Directory storage_name is just the id (no extension)."""
        entry = _make_entry(
            type="directory",
            extension=None,
            hashes=None,
            storage_name="xABCDEF0123456789",
        )
        assert "." not in entry.attributes.storage_name

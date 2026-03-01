"""Integration tests — Provenance-Preserving De-Duplication with Rename.

Covers: same-directory dedup, cross-directory dedup, dry-run output,
provenance preservation round-trip.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.dedup import (
    DedupRegistry,
    apply_dedup,
    cleanup_duplicate_files,
    scan_tree,
)
from shruggie_indexer.core.entry import index_path
from shruggie_indexer.core.serializer import serialize_entry


def _cfg(**overrides: object):
    return load_config(overrides=overrides)


@pytest.fixture()
def same_dir_duplicates(tmp_path: Path) -> Path:
    """Create a directory with two identical files (same content)."""
    root = tmp_path / "same_dir"
    root.mkdir()
    content = b"identical content for dedup testing"
    (root / "original.txt").write_bytes(content)
    (root / "copy.txt").write_bytes(content)
    return root


@pytest.fixture()
def cross_dir_duplicates(tmp_path: Path) -> Path:
    """Create a tree with identical files in different directories."""
    root = tmp_path / "cross_dir"
    root.mkdir()
    dir_a = root / "dir_a"
    dir_b = root / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()
    content = b"cross-directory duplicate content"
    (dir_a / "file.txt").write_bytes(content)
    (dir_b / "file_copy.txt").write_bytes(content)
    return root


@pytest.fixture()
def no_duplicates(tmp_path: Path) -> Path:
    """Create a directory with two different files."""
    root = tmp_path / "no_dup"
    root.mkdir()
    (root / "file1.txt").write_bytes(b"content A")
    (root / "file2.txt").write_bytes(b"content B")
    return root


class TestSameDirDedup:
    """Same-directory de-duplication scenarios."""

    def test_scan_finds_duplicate(
        self, same_dir_duplicates: Path, mock_exiftool: None,
    ) -> None:
        """scan_tree detects same-dir duplicates."""
        config = _cfg(rename=True, output_inplace=True)
        entry = index_path(same_dir_duplicates, config)
        registry = DedupRegistry()
        actions = scan_tree(entry, registry)
        assert len(actions) == 1
        stats = registry.stats
        assert stats.duplicates_found == 1

    def test_apply_removes_from_items(
        self, same_dir_duplicates: Path, mock_exiftool: None,
    ) -> None:
        """apply_dedup removes the duplicate from the parent's items."""
        config = _cfg(rename=True, output_inplace=True)
        entry = index_path(same_dir_duplicates, config)
        assert entry.items is not None
        original_count = len(entry.items)
        registry = DedupRegistry()
        actions = scan_tree(entry, registry)
        apply_dedup(actions)
        assert entry.items is not None
        assert len(entry.items) == original_count - 1

    def test_provenance_preserved_in_output(
        self, same_dir_duplicates: Path, mock_exiftool: None,
    ) -> None:
        """The canonical entry's serialized output contains duplicates."""
        config = _cfg(rename=True, output_inplace=True)
        entry = index_path(same_dir_duplicates, config)
        registry = DedupRegistry()
        actions = scan_tree(entry, registry)
        apply_dedup(actions)
        json_str = serialize_entry(entry)
        parsed = json.loads(json_str)
        # Find the canonical file entry
        canonical = None
        for item in parsed.get("items", []):
            if item.get("duplicates"):
                canonical = item
                break
        assert canonical is not None, "No entry with duplicates found"
        assert len(canonical["duplicates"]) == 1
        dup = canonical["duplicates"][0]
        assert dup["name"]["text"] is not None
        assert dup["file_system"]["relative"] is not None
        assert dup["size"]["bytes"] > 0
        assert dup["hashes"] is not None

    def test_cleanup_deletes_file(
        self, same_dir_duplicates: Path, mock_exiftool: None,
    ) -> None:
        """cleanup_duplicate_files removes the duplicate from disk."""
        config = _cfg(rename=True, output_inplace=True)
        entry = index_path(same_dir_duplicates, config)
        registry = DedupRegistry()
        actions = scan_tree(entry, registry)
        apply_dedup(actions)
        # Verify the duplicate file still exists before cleanup
        dup_path = same_dir_duplicates.parent / actions[0].duplicate_relative_path
        assert dup_path.exists()
        cleanup_duplicate_files(actions, same_dir_duplicates)
        assert not dup_path.exists()


class TestCrossDirDedup:
    """Cross-directory de-duplication scenarios."""

    def test_scan_finds_cross_dir_duplicate(
        self, cross_dir_duplicates: Path, mock_exiftool: None,
    ) -> None:
        """scan_tree detects cross-directory duplicates."""
        config = _cfg(rename=True, output_inplace=True, recursive=True)
        entry = index_path(cross_dir_duplicates, config)
        registry = DedupRegistry()
        actions = scan_tree(entry, registry)
        assert len(actions) == 1

    def test_cross_dir_provenance(
        self, cross_dir_duplicates: Path, mock_exiftool: None,
    ) -> None:
        """Cross-dir duplicate preserves provenance from different directory."""
        config = _cfg(rename=True, output_inplace=True, recursive=True)
        entry = index_path(cross_dir_duplicates, config)
        registry = DedupRegistry()
        actions = scan_tree(entry, registry)
        apply_dedup(actions)
        # Verify canonical has duplicate with path from different dir
        action = actions[0]
        canonical = action.canonical_entry
        assert canonical.duplicates is not None
        assert len(canonical.duplicates) == 1
        dup = canonical.duplicates[0]
        # The duplicate's relative path should differ from canonical's
        assert dup.file_system.relative != canonical.file_system.relative

    def test_cross_dir_cleanup(
        self, cross_dir_duplicates: Path, mock_exiftool: None,
    ) -> None:
        """cleanup_duplicate_files deletes cross-dir duplicate."""
        config = _cfg(rename=True, output_inplace=True, recursive=True)
        entry = index_path(cross_dir_duplicates, config)
        registry = DedupRegistry()
        actions = scan_tree(entry, registry)
        apply_dedup(actions)
        dup_path = cross_dir_duplicates.parent / actions[0].duplicate_relative_path
        assert dup_path.exists()
        cleanup_duplicate_files(actions, cross_dir_duplicates)
        assert not dup_path.exists()


class TestDryRunDedup:
    """Dry-run interaction with de-duplication."""

    def test_dry_run_no_deletion(
        self, same_dir_duplicates: Path, mock_exiftool: None,
    ) -> None:
        """In dry-run mode, files are not deleted."""
        config = _cfg(rename=True, output_inplace=True, dry_run=True)
        entry = index_path(same_dir_duplicates, config)
        registry = DedupRegistry()
        actions = scan_tree(entry, registry)
        apply_dedup(actions)
        # All files should still exist
        for f in same_dir_duplicates.iterdir():
            assert f.exists()
        # Cleanup with dry_run=True should not delete
        cleanup_duplicate_files(actions, same_dir_duplicates, dry_run=True)
        for f in same_dir_duplicates.iterdir():
            assert f.exists()

    def test_dry_run_output_contains_duplicates(
        self, same_dir_duplicates: Path, mock_exiftool: None,
    ) -> None:
        """Dry-run output still contains duplicates array."""
        config = _cfg(rename=True, output_inplace=True, dry_run=True)
        entry = index_path(same_dir_duplicates, config)
        registry = DedupRegistry()
        actions = scan_tree(entry, registry)
        apply_dedup(actions)
        json_str = serialize_entry(entry)
        parsed = json.loads(json_str)
        # Find canonical with duplicates
        canonical = None
        for item in parsed.get("items", []):
            if item.get("duplicates"):
                canonical = item
                break
        assert canonical is not None


class TestNoDuplicates:
    """No duplicates — verify no false positives."""

    def test_no_actions_when_no_duplicates(
        self, no_duplicates: Path, mock_exiftool: None,
    ) -> None:
        """No duplicates means no actions."""
        config = _cfg(rename=True, output_inplace=True)
        entry = index_path(no_duplicates, config)
        registry = DedupRegistry()
        actions = scan_tree(entry, registry)
        assert actions == []

    def test_no_duplicates_field_in_output(
        self, no_duplicates: Path, mock_exiftool: None,
    ) -> None:
        """Output has no 'duplicates' key when there are none."""
        config = _cfg(rename=True, output_inplace=True)
        entry = index_path(no_duplicates, config)
        json_str = serialize_entry(entry)
        parsed = json.loads(json_str)
        for item in parsed.get("items", []):
            assert "duplicates" not in item


class TestProvenanceRoundTrip:
    """Verify all fields survive the dedup merge round-trip."""

    def test_all_fields_preserved(
        self, same_dir_duplicates: Path, mock_exiftool: None,
    ) -> None:
        """Every IndexEntry field in the duplicate is preserved."""
        config = _cfg(rename=True, output_inplace=True)
        entry = index_path(same_dir_duplicates, config)
        registry = DedupRegistry()
        actions = scan_tree(entry, registry)
        # Capture duplicate's fields before merge
        dup = actions[0].duplicate_entry
        dup_name = dup.name.text
        dup_relative = dup.file_system.relative
        dup_size = dup.size.bytes
        dup_md5 = dup.hashes.md5 if dup.hashes else None
        apply_dedup(actions)
        # Verify all fields survived in the canonical's duplicates
        canonical = actions[0].canonical_entry
        assert canonical.duplicates is not None
        merged = canonical.duplicates[0]
        assert merged.name.text == dup_name
        assert merged.file_system.relative == dup_relative
        assert merged.size.bytes == dup_size
        if dup_md5 is not None:
            assert merged.hashes is not None
            assert merged.hashes.md5 == dup_md5
        # Verify through serialization round-trip
        d = merged.to_dict() if hasattr(merged, "to_dict") else None
        if d is not None:
            assert d["name"]["text"] == dup_name
            assert d["file_system"]["relative"] == dup_relative

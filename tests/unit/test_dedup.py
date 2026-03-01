"""Unit tests for core/dedup.py — Provenance-Preserving De-Duplication.

Covers: registry population, duplicate detection, canonical selection, merge
behavior, stats calculation, empty-tree edge case, single-file edge case.
"""

from __future__ import annotations

from typing import Any

import pytest

from shruggie_indexer.core.dedup import (
    DedupRegistry,
    apply_dedup,
    format_bytes,
    scan_tree,
)
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


def _make_hashset(md5: str = "D41D8CD98F00B204E9800998ECF8427E") -> HashSet:
    return HashSet(
        md5=md5,
        sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
    )


def _make_ts() -> TimestampsObject:
    pair = TimestampPair(iso="2026-01-01T00:00:00.000000+00:00", unix=1767225600000)
    return TimestampsObject(created=pair, modified=pair, accessed=pair)


def _make_file_entry(
    name: str = "file.txt",
    storage_name: str = "yD41D8CD98F00B204E9800998ECF8427E.txt",
    relative: str = "file.txt",
    size_bytes: int = 100,
    md5: str = "D41D8CD98F00B204E9800998ECF8427E",
) -> IndexEntry:
    return IndexEntry(
        schema_version=2,
        id=f"y{md5}",
        id_algorithm="md5",
        type="file",
        name=NameObject(text=name, hashes=_make_hashset(md5)),
        extension=name.rsplit(".", 1)[-1] if "." in name else None,
        size=SizeObject(text=f"{size_bytes} B", bytes=size_bytes),
        hashes=_make_hashset(md5),
        file_system=FileSystemObject(relative=relative, parent=None),
        timestamps=_make_ts(),
        attributes=AttributesObject(is_link=False, storage_name=storage_name),
    )


def _make_dir_entry(
    name: str = "root",
    items: list[IndexEntry] | None = None,
) -> IndexEntry:
    return IndexEntry(
        schema_version=2,
        id="x0000000000000000000000000000000",
        id_algorithm="md5",
        type="directory",
        name=NameObject(text=name, hashes=_make_hashset()),
        extension=None,
        size=SizeObject(text="0 B", bytes=0),
        hashes=None,
        file_system=FileSystemObject(relative=name, parent=None),
        timestamps=_make_ts(),
        attributes=AttributesObject(is_link=False, storage_name=f"x0000000000000000000000000000000"),
        items=items,
    )


# ---------------------------------------------------------------------------
# DedupRegistry tests
# ---------------------------------------------------------------------------


class TestDedupRegistry:
    """Registry population, check, and stats."""

    def test_first_file_is_canonical(self) -> None:
        """First file with a given hash is not a duplicate."""
        registry = DedupRegistry()
        entry = _make_file_entry()
        result = registry.check(entry)
        assert not result.is_duplicate
        assert result.canonical_entry is None

    def test_second_file_is_duplicate(self) -> None:
        """Second file with the same hash is a duplicate."""
        registry = DedupRegistry()
        entry1 = _make_file_entry(name="a.txt", relative="a.txt")
        entry2 = _make_file_entry(name="b.txt", relative="b.txt")
        registry.check(entry1)
        result = registry.check(entry2)
        assert result.is_duplicate
        assert result.canonical_entry is entry1

    def test_different_hash_not_duplicate(self) -> None:
        """Files with different hashes are not duplicates."""
        registry = DedupRegistry()
        entry1 = _make_file_entry(
            name="a.txt",
            storage_name="yAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA.txt",
            md5="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        )
        entry2 = _make_file_entry(
            name="b.txt",
            storage_name="yBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB.txt",
            md5="BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
        )
        result1 = registry.check(entry1)
        result2 = registry.check(entry2)
        assert not result1.is_duplicate
        assert not result2.is_duplicate

    def test_same_hash_different_extension_not_duplicate(self) -> None:
        """Files with same hash but different extensions are distinct."""
        registry = DedupRegistry()
        entry1 = _make_file_entry(
            name="photo.jpg",
            storage_name="yD41D8CD98F00B204E9800998ECF8427E.jpg",
        )
        entry2 = _make_file_entry(
            name="photo.jpeg",
            storage_name="yD41D8CD98F00B204E9800998ECF8427E.jpeg",
        )
        result1 = registry.check(entry1)
        result2 = registry.check(entry2)
        assert not result1.is_duplicate
        assert not result2.is_duplicate

    def test_stats_empty(self) -> None:
        """Stats on empty registry."""
        registry = DedupRegistry()
        stats = registry.stats
        assert stats.total_files_scanned == 0
        assert stats.unique_files == 0
        assert stats.duplicates_found == 0
        assert stats.bytes_reclaimed == 0

    def test_stats_with_duplicates(self) -> None:
        """Stats reflect scan results."""
        registry = DedupRegistry()
        entry1 = _make_file_entry(name="a.txt", relative="a.txt", size_bytes=500)
        entry2 = _make_file_entry(name="b.txt", relative="b.txt", size_bytes=500)
        registry.check(entry1)
        registry.check(entry2)
        stats = registry.stats
        assert stats.total_files_scanned == 2
        assert stats.unique_files == 1
        assert stats.duplicates_found == 1
        assert stats.bytes_reclaimed == 500

    def test_register_pre_populates(self) -> None:
        """register() pre-populates without counting stats."""
        registry = DedupRegistry()
        entry_pre = _make_file_entry(name="pre.txt", relative="pre.txt")
        registry.register(entry_pre)
        entry_new = _make_file_entry(name="new.txt", relative="new.txt")
        result = registry.check(entry_new)
        assert result.is_duplicate
        assert result.canonical_entry is entry_pre

    def test_merge(self) -> None:
        """merge() appends to canonical's duplicates."""
        registry = DedupRegistry()
        canonical = _make_file_entry(name="canon.txt", relative="canon.txt")
        duplicate = _make_file_entry(name="dup.txt", relative="dup.txt")
        assert canonical.duplicates is None
        registry.merge(canonical, duplicate)
        assert canonical.duplicates is not None
        assert len(canonical.duplicates) == 1
        assert canonical.duplicates[0] is duplicate


# ---------------------------------------------------------------------------
# scan_tree tests
# ---------------------------------------------------------------------------


class TestScanTree:
    """Tree scanning for duplicates."""

    def test_empty_directory(self) -> None:
        """Empty directory produces no actions."""
        root = _make_dir_entry(items=[])
        registry = DedupRegistry()
        actions = scan_tree(root, registry)
        assert actions == []

    def test_single_file(self) -> None:
        """Single file produces no actions."""
        entry = _make_file_entry()
        root = _make_dir_entry(items=[entry])
        registry = DedupRegistry()
        actions = scan_tree(root, registry)
        assert actions == []

    def test_same_dir_duplicates(self) -> None:
        """Two files in same directory with same hash → one action."""
        entry1 = _make_file_entry(name="a.txt", relative="root/a.txt")
        entry2 = _make_file_entry(name="b.txt", relative="root/b.txt")
        root = _make_dir_entry(items=[entry1, entry2])
        registry = DedupRegistry()
        actions = scan_tree(root, registry)
        assert len(actions) == 1
        assert actions[0].duplicate_entry is entry2
        assert actions[0].canonical_entry is entry1
        assert actions[0].parent_entry is root

    def test_cross_dir_duplicates(self) -> None:
        """Files in different directories with same hash → one action."""
        entry1 = _make_file_entry(name="a.txt", relative="dir_a/a.txt")
        entry2 = _make_file_entry(name="b.txt", relative="dir_b/b.txt")
        subdir1 = _make_dir_entry(name="dir_a", items=[entry1])
        subdir2 = _make_dir_entry(name="dir_b", items=[entry2])
        root = _make_dir_entry(items=[subdir1, subdir2])
        registry = DedupRegistry()
        actions = scan_tree(root, registry)
        assert len(actions) == 1
        assert actions[0].duplicate_entry is entry2
        assert actions[0].canonical_entry is entry1
        assert actions[0].parent_entry is subdir2

    def test_three_duplicates(self) -> None:
        """Three files with same hash → two actions."""
        entry1 = _make_file_entry(name="a.txt", relative="root/a.txt")
        entry2 = _make_file_entry(name="b.txt", relative="root/b.txt")
        entry3 = _make_file_entry(name="c.txt", relative="root/c.txt")
        root = _make_dir_entry(items=[entry1, entry2, entry3])
        registry = DedupRegistry()
        actions = scan_tree(root, registry)
        assert len(actions) == 2
        assert all(a.canonical_entry is entry1 for a in actions)

    def test_no_duplicates(self) -> None:
        """Files with different hashes produce no actions."""
        entry1 = _make_file_entry(
            name="a.txt",
            storage_name="yAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA.txt",
            md5="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            relative="root/a.txt",
        )
        entry2 = _make_file_entry(
            name="b.txt",
            storage_name="yBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB.txt",
            md5="BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
            relative="root/b.txt",
        )
        root = _make_dir_entry(items=[entry1, entry2])
        registry = DedupRegistry()
        actions = scan_tree(root, registry)
        assert actions == []

    def test_file_root_entry(self) -> None:
        """Root entry that is a single file (not a directory)."""
        entry = _make_file_entry()
        registry = DedupRegistry()
        actions = scan_tree(entry, registry)
        assert actions == []


# ---------------------------------------------------------------------------
# apply_dedup tests
# ---------------------------------------------------------------------------


class TestApplyDedup:
    """Merge and tree mutation behavior."""

    def test_merge_populates_duplicates(self) -> None:
        """apply_dedup() merges duplicate into canonical's duplicates."""
        entry1 = _make_file_entry(name="a.txt", relative="root/a.txt")
        entry2 = _make_file_entry(name="b.txt", relative="root/b.txt")
        root = _make_dir_entry(items=[entry1, entry2])
        registry = DedupRegistry()
        actions = scan_tree(root, registry)
        apply_dedup(actions)
        assert entry1.duplicates is not None
        assert len(entry1.duplicates) == 1
        assert entry1.duplicates[0] is entry2

    def test_removes_from_parent_items(self) -> None:
        """apply_dedup() removes duplicate from parent's items."""
        entry1 = _make_file_entry(name="a.txt", relative="root/a.txt")
        entry2 = _make_file_entry(name="b.txt", relative="root/b.txt")
        root = _make_dir_entry(items=[entry1, entry2])
        registry = DedupRegistry()
        actions = scan_tree(root, registry)
        apply_dedup(actions)
        assert root.items is not None
        assert len(root.items) == 1
        assert root.items[0] is entry1

    def test_cross_dir_removes_from_correct_parent(self) -> None:
        """apply_dedup() removes duplicate from its specific parent."""
        entry1 = _make_file_entry(name="a.txt", relative="dir_a/a.txt")
        entry2 = _make_file_entry(name="b.txt", relative="dir_b/b.txt")
        subdir1 = _make_dir_entry(name="dir_a", items=[entry1])
        subdir2 = _make_dir_entry(name="dir_b", items=[entry2])
        root = _make_dir_entry(items=[subdir1, subdir2])
        registry = DedupRegistry()
        actions = scan_tree(root, registry)
        apply_dedup(actions)
        assert subdir1.items is not None
        assert len(subdir1.items) == 1
        assert subdir2.items is not None
        assert len(subdir2.items) == 0
        assert entry1.duplicates is not None
        assert entry1.duplicates[0] is entry2

    def test_no_actions_no_mutation(self) -> None:
        """apply_dedup() with empty actions does nothing."""
        entry = _make_file_entry()
        root = _make_dir_entry(items=[entry])
        apply_dedup([])
        assert entry.duplicates is None
        assert root.items is not None
        assert len(root.items) == 1

    def test_duplicates_absent_when_not_set(self) -> None:
        """to_dict() omits duplicates when None."""
        entry = _make_file_entry()
        d = entry.to_dict()
        assert "duplicates" not in d

    def test_duplicates_present_in_to_dict(self) -> None:
        """to_dict() includes duplicates when populated."""
        entry1 = _make_file_entry(name="a.txt", relative="root/a.txt")
        entry2 = _make_file_entry(name="b.txt", relative="root/b.txt")
        root = _make_dir_entry(items=[entry1, entry2])
        registry = DedupRegistry()
        actions = scan_tree(root, registry)
        apply_dedup(actions)
        d = entry1.to_dict()
        assert "duplicates" in d
        assert len(d["duplicates"]) == 1
        assert d["duplicates"][0]["name"]["text"] == "b.txt"

    def test_provenance_fields_preserved(self) -> None:
        """All identity fields survive the merge into duplicates."""
        entry1 = _make_file_entry(name="canon.txt", relative="root/canon.txt")
        entry2 = _make_file_entry(
            name="dup.txt",
            relative="root/dup.txt",
            size_bytes=42,
        )
        root = _make_dir_entry(items=[entry1, entry2])
        registry = DedupRegistry()
        actions = scan_tree(root, registry)
        apply_dedup(actions)
        dup_dict = entry1.to_dict()["duplicates"][0]
        assert dup_dict["name"]["text"] == "dup.txt"
        assert dup_dict["file_system"]["relative"] == "root/dup.txt"
        assert dup_dict["size"]["bytes"] == 42
        assert dup_dict["hashes"]["md5"] == "D41D8CD98F00B204E9800998ECF8427E"


# ---------------------------------------------------------------------------
# format_bytes tests
# ---------------------------------------------------------------------------


class TestFormatBytes:
    def test_bytes(self) -> None:
        assert format_bytes(999) == "999 B"

    def test_kilobytes(self) -> None:
        assert "KB" in format_bytes(1500)

    def test_megabytes(self) -> None:
        assert "MB" in format_bytes(5_000_000)

    def test_zero(self) -> None:
        assert format_bytes(0) == "0 B"

"""Integration tests — recursive directory indexing.

4 test cases per §14.3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.entry import build_directory_entry
from shruggie_indexer.models.schema import IndexEntry


def _cfg(**overrides: object):
    return load_config(overrides=overrides)


class TestRecursiveDirectoryIndexing:
    """Tests for recursive directory traversal."""

    def test_recursive_traversal_depth(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """Recursive mode populates nested items for subdirectories."""
        config = _cfg()
        entry = build_directory_entry(sample_tree, config, recursive=True)

        assert entry.items is not None
        subdirs = [i for i in entry.items if i.type == "directory"]
        assert len(subdirs) >= 1
        # Subdirectory should have its own nested items.
        subdir = subdirs[0]
        assert subdir.items is not None
        assert len(subdir.items) >= 1

    def test_nested_directory_has_own_id(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """Nested directories have their own unique 'x'-prefixed IDs."""
        config = _cfg()
        entry = build_directory_entry(sample_tree, config, recursive=True)

        assert entry.items is not None
        subdirs = [i for i in entry.items if i.type == "directory"]
        for subdir in subdirs:
            assert subdir.id.startswith("x")
            assert subdir.id != entry.id

    def test_parent_references_populated(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """Nested file entries have non-null parent references."""
        config = _cfg()
        entry = build_directory_entry(sample_tree, config, recursive=True)

        assert entry.items is not None
        subdirs = [i for i in entry.items if i.type == "directory"]
        assert len(subdirs) >= 1
        subdir = subdirs[0]
        if subdir.items:
            for child in subdir.items:
                assert child.file_system is not None
                assert child.file_system.parent is not None
                assert child.file_system.parent.id.startswith("x")

    def test_items_contain_expected_files(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """All expected files from the tree appear in the recursive output."""
        config = _cfg()
        entry = build_directory_entry(sample_tree, config, recursive=True)

        all_names = _collect_names(entry)
        assert "file_a.txt" in all_names
        assert "file_b.jpg" in all_names
        assert "nested.txt" in all_names


def _collect_names(entry: IndexEntry) -> set[str]:
    """Recursively collect all name texts from an entry tree."""
    names = set()
    if entry.name.text:
        names.add(entry.name.text)
    if entry.items:
        for child in entry.items:
            names.update(_collect_names(child))
    return names

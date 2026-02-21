"""Integration tests — flat directory indexing.

3 test cases per §14.3.
"""

from __future__ import annotations

from pathlib import Path

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.entry import build_directory_entry


def _cfg(**overrides: object):
    return load_config(overrides=overrides)


class TestFlatDirectoryIndexing:
    """Tests for non-recursive directory indexing."""

    def test_flat_directory_indexing(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """Flat indexing of a directory produces a valid directory entry."""
        config = _cfg()
        entry = build_directory_entry(sample_tree, config, recursive=False)

        assert entry.type == "directory"
        assert entry.items is not None

    def test_item_count_matches(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """Number of items matches the count of immediate children.

        sample_tree has: file_a.txt, file_b.jpg, subdir/ → 3 items.
        """
        config = _cfg()
        entry = build_directory_entry(sample_tree, config, recursive=False)

        assert entry.items is not None
        assert len(entry.items) == 3

    def test_child_files_are_typed_file(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """File children have type='file'."""
        config = _cfg()
        entry = build_directory_entry(sample_tree, config, recursive=False)

        assert entry.items is not None
        file_entries = [i for i in entry.items if i.type == "file"]
        assert len(file_entries) == 2
        for fe in file_entries:
            assert fe.type == "file"
            assert fe.hashes is not None

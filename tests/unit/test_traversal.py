"""Unit tests for core/traversal.py — §6.1 Filesystem Traversal and Discovery.

9 test cases per §14.2.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import IndexerConfig
from shruggie_indexer.core.traversal import list_children

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(**overrides: object) -> IndexerConfig:
    """Quick config builder for traversal tests."""
    return load_config(overrides=overrides)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlatListing:
    """Tests for flat (non-recursive) directory listing."""

    def test_flat_listing_returns_files_and_dirs(self, sample_tree: Path) -> None:
        """list_children returns separate sorted lists of files and dirs."""
        config = _cfg()
        files, directories = list_children(sample_tree, config)

        file_names = [p.name for p in files]
        dir_names = [p.name for p in directories]

        assert "file_a.txt" in file_names
        assert "file_b.jpg" in file_names
        assert "subdir" in dir_names

    def test_flat_listing_does_not_recurse(self, sample_tree: Path) -> None:
        """Nested files (subdir/nested.txt) are NOT in the immediate listing."""
        config = _cfg()
        files, _ = list_children(sample_tree, config)
        file_names = [p.name for p in files]
        assert "nested.txt" not in file_names


class TestExclusionFilters:
    """Tests for filesystem exclusion filters."""

    def test_name_exclusion(self, tmp_path: Path) -> None:
        """Items in filesystem_excludes are omitted from results."""
        (tmp_path / "normal.txt").write_text("ok", encoding="utf-8")
        (tmp_path / ".git").mkdir()
        (tmp_path / "$recycle.bin").mkdir()

        config = _cfg()
        files, directories = list_children(tmp_path, config)
        all_names = {p.name for p in files} | {p.name for p in directories}

        assert "normal.txt" in all_names
        assert ".git" not in all_names
        assert "$recycle.bin" not in all_names

    def test_glob_exclusion(self, tmp_path: Path) -> None:
        """Items matching filesystem_exclude_globs are omitted."""
        (tmp_path / ".trash-1000").mkdir()
        (tmp_path / "keep_me").mkdir()

        config = _cfg()
        _, directories = list_children(tmp_path, config)
        dir_names = {p.name for p in directories}

        assert "keep_me" in dir_names
        assert ".trash-1000" not in dir_names


class TestSymlinks:
    """Tests for symlink classification."""

    @pytest.mark.skipif(
        sys.platform == "win32" and not os.environ.get("CI"),
        reason="Symlink creation may require elevated privileges on Windows",
    )
    def test_symlink_to_file_classified_as_file(self, tmp_path: Path) -> None:
        """A symlink pointing to a file appears in the files list."""
        target = tmp_path / "real.txt"
        target.write_text("real", encoding="utf-8")
        link = tmp_path / "link.txt"
        link.symlink_to(target)

        config = _cfg()
        files, _ = list_children(tmp_path, config)
        file_names = {p.name for p in files}
        assert "link.txt" in file_names


class TestEdgeCases:
    """Tests for empty dirs, hidden files, sort order, mixed types."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory returns two empty lists."""
        config = _cfg()
        files, directories = list_children(tmp_path, config)
        assert files == []
        assert directories == []

    def test_hidden_files_included(self, tmp_path: Path) -> None:
        """Dotfiles that are not in the exclusion set are returned."""
        (tmp_path / ".hidden_note.txt").write_text("secret", encoding="utf-8")
        config = _cfg()
        files, _ = list_children(tmp_path, config)
        file_names = [p.name for p in files]
        assert ".hidden_note.txt" in file_names

    def test_sort_order_case_insensitive(self, tmp_path: Path) -> None:
        """Files are sorted case-insensitively by name."""
        for name in ("Zebra.txt", "apple.txt", "Mango.txt"):
            (tmp_path / name).write_text(name, encoding="utf-8")

        config = _cfg()
        files, _ = list_children(tmp_path, config)
        sorted_names = [p.name for p in files]
        assert sorted_names == ["apple.txt", "Mango.txt", "Zebra.txt"]

    def test_mixed_file_and_directory_classification(self, tmp_path: Path) -> None:
        """Files and directories are correctly separated."""
        (tmp_path / "readme.md").write_text("# Hi", encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "setup.py").write_text("", encoding="utf-8")

        config = _cfg()
        files, directories = list_children(tmp_path, config)
        file_names = {p.name for p in files}
        dir_names = {p.name for p in directories}

        assert file_names == {"readme.md", "setup.py"}
        assert dir_names == {"src", "tests"}

    def test_deeply_nested_is_not_visible(self, tmp_path: Path) -> None:
        """Only immediate children are returned, not deeply nested items."""
        d = tmp_path / "a" / "b" / "c"
        d.mkdir(parents=True)
        (d / "deep.txt").write_text("deep", encoding="utf-8")

        config = _cfg()
        files, directories = list_children(tmp_path, config)
        all_names = {p.name for p in files} | {p.name for p in directories}
        assert "deep.txt" not in all_names
        assert "a" in all_names

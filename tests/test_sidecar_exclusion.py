"""Unit tests for sidecar discovery, exclusion, and merge behavior.

Validates that the traversal and sidecar modules correctly identify which
files to exclude from the item list, without running the full indexing
pipeline.

Batch 6, Section 5.3.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from shruggie_indexer.config.defaults import (
    DEFAULT_METADATA_EXCLUDE_PATTERNS,
    DEFAULT_METADATA_IDENTIFY,
)
from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.entry import index_path
from shruggie_indexer.core.traversal import list_children

# ── Fixture paths ───────────────────────────────────────────────────────
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SIDECAR_TESTBED = FIXTURES_DIR / "sidecar-testbed"


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def sidecar_testbed(tmp_path: Path) -> Path:
    """Create a disposable copy of the sidecar-testbed fixture."""
    dest = tmp_path / "sidecar-testbed"
    shutil.copytree(SIDECAR_TESTBED, dest)
    return dest


@pytest.fixture()
def default_config():
    """Default config (no MetaMerge)."""
    return load_config()


@pytest.fixture()
def meta_merge_config():
    """Config with MetaMerge enabled."""
    return load_config(overrides={"meta_merge": True})


# ── Test 1: metadata_exclude_patterns correctly match indexer output ────


@pytest.mark.sidecar
class TestExcludePatterns:
    """Validate that metadata_exclude_patterns match indexer output artifacts."""

    patterns = DEFAULT_METADATA_EXCLUDE_PATTERNS

    def test_exclude_patterns_match_v1_meta(self) -> None:
        """_meta.json files match metadata_exclude_patterns."""
        assert any(p.search("video.mp4_meta.json") for p in self.patterns)
        assert any(p.search("123.nfo_meta.json") for p in self.patterns)

    def test_exclude_patterns_match_v2_meta(self) -> None:
        """_meta2.json files match metadata_exclude_patterns."""
        assert any(p.search("video.mp4_meta2.json") for p in self.patterns)
        assert any(p.search("nested.txt_meta2.json") for p in self.patterns)

    def test_exclude_patterns_match_v1_directorymeta(self) -> None:
        """_directorymeta.json files match metadata_exclude_patterns."""
        assert any(p.search("_directorymeta.json") for p in self.patterns)

    def test_exclude_patterns_match_v2_directorymeta(self) -> None:
        """_directorymeta2.json files match metadata_exclude_patterns."""
        assert any(p.search("_directorymeta2.json") for p in self.patterns)

    def test_exclude_patterns_do_not_match_content_files(self) -> None:
        """Content files like video.mp4, photo.jpg do not match exclusion patterns."""
        content_files = [
            "video.mp4", "photo.jpg", "data.csv", "content.txt",
            "standalone.pdf", "nested.txt",
        ]
        for name in content_files:
            assert not any(p.search(name) for p in self.patterns), (
                f"{name} should NOT match metadata_exclude_patterns"
            )

    def test_exclude_patterns_do_not_match_info_json(self) -> None:
        """Sidecar files like video.mp4.info.json do not match metadata_exclude_patterns.

        These are handled by metadata_identify, not the exclude list.
        """
        sidecar_files = [
            "video.mp4.info.json",
            "video.mp4.description",
            "photo.jpg.md5",
            "nested.txt.yaml",
        ]
        for name in sidecar_files:
            assert not any(p.search(name) for p in self.patterns), (
                f"{name} should NOT match metadata_exclude_patterns"
            )


# ── Test 2: list_children respects metadata_exclude_patterns ────────────


@pytest.mark.sidecar
class TestListChildrenExcludePatterns:
    """Validate that list_children() filters indexer output artifacts."""

    def test_list_children_excludes_meta_json(
        self, sidecar_testbed: Path, default_config,
    ) -> None:
        """list_children() does not return files matching metadata_exclude_patterns."""
        files, _dirs = list_children(sidecar_testbed, default_config)
        file_names = {f.name for f in files}

        # These indexer output artifacts must be excluded.
        assert "video.mp4_meta.json" not in file_names
        assert "video.mp4_meta2.json" not in file_names

    def test_list_children_excludes_directorymeta2_json(
        self, sidecar_testbed: Path, default_config,
    ) -> None:
        """list_children() does not return _directorymeta2.json."""
        files, _dirs = list_children(sidecar_testbed, default_config)
        file_names = {f.name for f in files}

        assert "_directorymeta2.json" not in file_names

    def test_list_children_subdir_excludes_meta_json(
        self, sidecar_testbed: Path, default_config,
    ) -> None:
        """list_children() in subdirectory also excludes _meta.json."""
        subdir = sidecar_testbed / "subdir"
        files, _dirs = list_children(subdir, default_config)
        file_names = {f.name for f in files}

        assert "nested.txt_meta.json" not in file_names
        assert "_directorymeta2.json" not in file_names
        # Content file and sidecar should remain.
        assert "nested.txt" in file_names


# ── Test 3: MetaMerge sidecar exclusion (Layer 2) ──────────────────────


def _collect_all_names(entry) -> set[str]:
    """Recursively collect all item names from an IndexEntry tree."""
    names: set[str] = set()
    if entry.name and entry.name.text:
        names.add(entry.name.text)
    if entry.items:
        for child in entry.items:
            names.update(_collect_all_names(child))
    return names


@pytest.mark.sidecar
class TestListChildrenMetaMergeExclusion:
    """Validate Layer 2: when MetaMerge is active, recognized sidecar files
    are excluded from the indexed item tree (filtering happens in
    build_directory_entry, not list_children, so that sidecars remain
    available as siblings for sidecar discovery)."""

    def test_list_children_meta_merge_excludes_sidecars(
        self, sidecar_testbed: Path, meta_merge_config,
    ) -> None:
        """When MetaMerge is active, sidecar files do not appear as indexed items."""
        entry = index_path(sidecar_testbed, meta_merge_config)
        names = _collect_all_names(entry)

        # All sidecar identification matches should be excluded from the index.
        assert "video.mp4.info.json" not in names
        assert "video.mp4.description" not in names
        assert "video.mp4_screen.jpg" not in names
        assert "photo.jpg.md5" not in names

    def test_list_children_meta_merge_keeps_non_sidecars(
        self, sidecar_testbed: Path, meta_merge_config,
    ) -> None:
        """When MetaMerge is active, content files remain in the index."""
        entry = index_path(sidecar_testbed, meta_merge_config)
        names = _collect_all_names(entry)

        assert "content.txt" in names
        assert "video.mp4" in names
        assert "photo.jpg" in names
        assert "data.csv" in names

    def test_non_sidecar_with_similar_name_not_excluded(
        self, sidecar_testbed: Path, meta_merge_config,
    ) -> None:
        """standalone_notes.txt is NOT excluded even though 'standalone' appears
        in its name."""
        # Index the no-sidecars subdirectory directly.
        no_sidecars_dir = sidecar_testbed / "no-sidecars"
        entry = index_path(no_sidecars_dir, meta_merge_config)
        names = _collect_all_names(entry)

        assert "standalone_notes.txt" in names
        assert "standalone.pdf" in names

    def test_meta_merge_subdir_excludes_yaml_sidecar(
        self, sidecar_testbed: Path, meta_merge_config,
    ) -> None:
        """When MetaMerge is active, nested.txt.yaml is excluded as a sidecar."""
        subdir = sidecar_testbed / "subdir"
        entry = index_path(subdir, meta_merge_config)
        names = _collect_all_names(entry)

        assert "nested.txt.yaml" not in names
        assert "nested.txt" in names

    def test_no_meta_merge_keeps_sidecars_in_list(
        self, sidecar_testbed: Path, default_config,
    ) -> None:
        """Without MetaMerge, sidecar files remain in the item list (minus
        indexer output artifacts excluded by Layer 1)."""
        files, _dirs = list_children(sidecar_testbed, default_config)
        file_names = {f.name for f in files}

        # Layer 1 excludes these always:
        assert "video.mp4_meta.json" not in file_names
        assert "video.mp4_meta2.json" not in file_names

        # But Layer 2 is inactive, so sidecar-identifiable files remain:
        assert "video.mp4.info.json" in file_names
        assert "video.mp4.description" in file_names
        assert "photo.jpg.md5" in file_names

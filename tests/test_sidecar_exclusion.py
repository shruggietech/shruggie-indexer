"""Integration-style tests for v4 sidecar discovery behavior.

Phase 3 removes sidecar exclusion from entry building. Sidecar-like files
must be indexed as first-class entries, with relationships annotated by
the rule engine.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

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
    """Default config (relationship detection enabled)."""
    return load_config()


@pytest.fixture()
def no_sidecar_detection_config():
    """Config that disables relationship classification."""
    return load_config(overrides={"no_sidecar_detection": True})


# ── Helpers ─────────────────────────────────────────────────────────────

def _collect_entries(entry):
    entries = [entry]
    if entry.items:
        for child in entry.items:
            entries.extend(_collect_entries(child))
    if entry.duplicates:
        for child in entry.duplicates:
            entries.extend(_collect_entries(child))
    return entries


def _by_name(entry):
    return {item.name.text: item for item in _collect_entries(entry) if item.name.text is not None}


# ── Test 2: list_children respects metadata_exclude_patterns ────────────


@pytest.mark.sidecar
class TestListChildrenExcludePatterns:
    """Validate that list_children() filters indexer output artifacts."""

    def test_list_children_excludes_meta_json(
        self, sidecar_testbed: Path, default_config,
    ) -> None:
        """Legacy indexer output artifacts are excluded at traversal time."""
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
        # Content and sidecar-like files remain.
        assert "nested.txt" in file_names
        assert "nested.txt.yaml" in file_names


# ── Test 3: v4 all-files-included discovery and relationships ──────────


@pytest.mark.sidecar
class TestV4DiscoveryAndRelationships:
    """Validate all-files-included behavior and relationship annotation."""

    def test_index_includes_sidecar_like_files(
        self, sidecar_testbed: Path, default_config,
    ) -> None:
        entry = index_path(sidecar_testbed, default_config)
        by_name = _by_name(entry)

        assert "video.mp4" in by_name
        assert "video.mp4.info.json" in by_name
        assert "video.mp4.description" in by_name
        assert "video.mp4_screen.jpg" in by_name
        assert "photo.jpg" in by_name
        assert "photo.jpg.md5" in by_name

    def test_relationships_are_populated_for_matched_rules(
        self, sidecar_testbed: Path, default_config,
    ) -> None:
        entry = index_path(sidecar_testbed, default_config)
        by_name = _by_name(entry)

        video_id = by_name["video.mp4"].id
        info_rel = by_name["video.mp4.info.json"].relationships
        desc_rel = by_name["video.mp4.description"].relationships
        hash_rel = by_name["photo.jpg.md5"].relationships

        assert info_rel is not None and len(info_rel) == 1
        assert info_rel[0].target_id == video_id
        assert info_rel[0].type == "json_metadata"

        assert desc_rel is not None and len(desc_rel) == 1
        assert desc_rel[0].target_id == video_id
        assert desc_rel[0].type == "description"

        assert hash_rel is not None and len(hash_rel) == 1
        assert hash_rel[0].target_id == by_name["photo.jpg"].id
        assert hash_rel[0].type == "hash"

    def test_no_sidecar_detection_disables_relationships(
        self, sidecar_testbed: Path, no_sidecar_detection_config,
    ) -> None:
        entry = index_path(sidecar_testbed, no_sidecar_detection_config)
        for child in _collect_entries(entry):
            assert child.relationships is None

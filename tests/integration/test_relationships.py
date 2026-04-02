"""Integration tests for v4 relationship classification in the indexing pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.entry import index_path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
SIDECAR_TESTBED = FIXTURES_DIR / "sidecar-testbed"


def _cfg(**overrides: object):
    return load_config(overrides=overrides)


def _copy_testbed(tmp_path: Path) -> Path:
    dest = tmp_path / "sidecar-testbed"
    shutil.copytree(SIDECAR_TESTBED, dest)
    return dest


def _walk_entries(entry):
    entries = [entry]
    if entry.items:
        for child in entry.items:
            entries.extend(_walk_entries(child))
    if entry.duplicates:
        for child in entry.duplicates:
            entries.extend(_walk_entries(child))
    return entries


def _by_name(entry):
    return {item.name.text: item for item in _walk_entries(entry) if item.name.text is not None}


class TestRelationshipPipeline:
    def test_sidecar_like_files_are_indexed_and_annotated(self, tmp_path: Path) -> None:
        root = _copy_testbed(tmp_path)
        entry = index_path(root, _cfg())
        by_name = _by_name(entry)

        assert "video.mp4" in by_name
        assert "video.mp4.info.json" in by_name
        assert "video.mp4.description" in by_name
        assert "photo.jpg.md5" in by_name

        video_id = by_name["video.mp4"].id
        rel = by_name["video.mp4.info.json"].relationships
        assert rel is not None and len(rel) == 1
        assert rel[0].target_id == video_id
        assert rel[0].rule_source == "builtin"
        assert rel[0].confidence in {1, 2, 3}

    def test_no_sidecar_detection_mode_omits_relationships(self, tmp_path: Path) -> None:
        root = _copy_testbed(tmp_path)
        entry = index_path(root, _cfg(no_sidecar_detection=True))

        for item in _walk_entries(entry):
            assert item.relationships is None

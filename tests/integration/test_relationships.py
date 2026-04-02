"""Integration tests for v4 relationship classification in the indexing pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.entry import index_path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
SIDECAR_TESTBED = FIXTURES_DIR / "v4_sidecar_testbed"


def _cfg(**overrides: object):
    return load_config(overrides=overrides)


def _copy_testbed(tmp_path: Path) -> Path:
    dest = tmp_path / "v4_sidecar_testbed"
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
        entry = index_path(root, _cfg(filesystem_excludes=()))
        by_name = _by_name(entry)

        assert "video.mp4" in by_name
        assert "video.mp4.info.json" in by_name
        assert "video.mp4.description" in by_name
        assert "video.mp4.en.vtt" in by_name
        assert "video.mp4_screen.jpg" in by_name
        assert "photo.jpg.md5" in by_name
        assert "download.torrent" in by_name
        assert "bookmarks.url" in by_name
        assert "desktop.ini" in by_name
        assert "shortcut.lnk" in by_name
        assert "standalone.txt" in by_name

        video_id = by_name["video.mp4"].id

        rel = by_name["video.mp4.info.json"].relationships
        assert rel is not None and len(rel) == 1
        assert rel[0].target_id == video_id
        assert rel[0].type == "json_metadata"
        assert rel[0].rule_source == "builtin"
        assert rel[0].confidence == 3

        subtitle_rel = by_name["video.mp4.en.vtt"].relationships
        assert subtitle_rel is not None and len(subtitle_rel) == 1
        assert subtitle_rel[0].target_id == video_id
        assert subtitle_rel[0].type == "subtitles"
        assert subtitle_rel[0].confidence == 1
        assert len(subtitle_rel[0].predicates) > 0
        assert subtitle_rel[0].predicates[0].name == "requires_sibling_any"

        thumb_rel = by_name["video.mp4_screen.jpg"].relationships
        assert thumb_rel is not None and len(thumb_rel) == 1
        assert thumb_rel[0].target_id == video_id
        assert thumb_rel[0].type == "screenshot"
        assert thumb_rel[0].confidence == 3

        # Standalone files must not gain accidental relationship metadata.
        assert by_name["standalone.txt"].relationships is None

    def test_no_sidecar_detection_mode_omits_relationships(self, tmp_path: Path) -> None:
        root = _copy_testbed(tmp_path)
        entry = index_path(root, _cfg(no_sidecar_detection=True))

        for item in _walk_entries(entry):
            assert item.relationships is None

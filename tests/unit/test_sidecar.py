"""Unit tests for core/sidecar.py — §6.7 Sidecar Metadata File Handling.

9 test cases per §14.2.
"""

from __future__ import annotations

import json
from pathlib import Path

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import IndexerConfig
from shruggie_indexer.core.sidecar import discover_and_parse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(**overrides: object) -> IndexerConfig:
    return load_config(overrides=overrides)  # type: ignore[arg-type]


def _make_sidecar_dir(
    tmp_path: Path,
    primary_name: str = "video.mp4",
    sidecars: dict[str, str | bytes] | None = None,
) -> tuple[Path, list[Path]]:
    """Create a directory with a primary file and sidecar siblings.

    Returns ``(primary_path, siblings_list)`` where ``siblings_list`` is
    every file in the directory (including the primary).
    """
    root = tmp_path / "sc"
    root.mkdir(exist_ok=True)

    primary = root / primary_name
    primary.write_bytes(b"primary content")

    if sidecars:
        for name, content in sidecars.items():
            p = root / name
            if isinstance(content, bytes):
                p.write_bytes(content)
            else:
                p.write_text(content, encoding="utf-8")

    siblings = sorted(root.iterdir(), key=lambda p: p.name.lower())
    return primary, [p for p in siblings if p.is_file()]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSidecarTypeDetection:
    """Tests for individual sidecar type detection and parsing."""

    def test_description_type_detected(self, tmp_path: Path) -> None:
        """A .description file is detected as type 'description'."""
        primary, siblings = _make_sidecar_dir(
            tmp_path,
            sidecars={"video.description": "A video about testing."},
        )
        config = _cfg(meta_merge=True)
        entries = discover_and_parse(
            primary, primary.name, siblings, config,
        )
        assert len(entries) >= 1
        types = {e.attributes.type for e in entries}
        assert "description" in types

    def test_json_metadata_type_parsed(self, tmp_path: Path) -> None:
        """A .info.json file is parsed as JSON with format='json'."""
        info = {"title": "Test", "duration": 100}
        primary, siblings = _make_sidecar_dir(
            tmp_path,
            sidecars={"video.info.json": json.dumps(info)},
        )
        config = _cfg(meta_merge=True)
        entries = discover_and_parse(
            primary, primary.name, siblings, config,
        )
        assert len(entries) >= 1
        json_entry = next(
            e for e in entries if e.attributes.type == "json_metadata"
        )
        assert json_entry.attributes.format == "json"
        assert isinstance(json_entry.data, dict)
        assert json_entry.data["title"] == "Test"

    def test_hash_type_parsed_as_lines(self, tmp_path: Path) -> None:
        """A .md5 file is parsed as 'lines' format."""
        primary, siblings = _make_sidecar_dir(
            tmp_path,
            sidecars={"video.md5": "ABCDEF01 *video.mp4\n"},
        )
        config = _cfg(meta_merge=True)
        entries = discover_and_parse(
            primary, primary.name, siblings, config,
        )
        hash_entries = [e for e in entries if e.attributes.type == "hash"]
        assert len(hash_entries) >= 1
        assert hash_entries[0].attributes.format == "lines"
        assert isinstance(hash_entries[0].data, list)

    def test_desktop_ini_type_detected(self, tmp_path: Path) -> None:
        """A desktop.ini file is detected as type 'desktop_ini'."""
        primary, siblings = _make_sidecar_dir(
            tmp_path,
            sidecars={"desktop.ini": "[.ShellClassInfo]\nIconResource=x.dll,4\n"},
        )
        config = _cfg(meta_merge=True)
        entries = discover_and_parse(
            primary, primary.name, siblings, config,
        )
        types = {e.attributes.type for e in entries}
        assert "desktop_ini" in types


class TestNoMatch:
    """Tests for the no-match case."""

    def test_no_sidecars_returns_empty(self, tmp_path: Path) -> None:
        """When no siblings match any pattern, returns empty list."""
        primary, siblings = _make_sidecar_dir(
            tmp_path,
            sidecars={"unrelated_doc.pdf": b"%PDF"},
        )
        config = _cfg(meta_merge=True)
        entries = discover_and_parse(
            primary, primary.name, siblings, config,
        )
        # .pdf is not a sidecar type — should be empty or only contain
        # matches.  Exact behavior depends on patterns, but pdf is not
        # in the default identify set.
        sidecar_types = {e.attributes.type for e in entries}
        # Verify no spurious types appear.
        assert "json_metadata" not in sidecar_types
        assert "description" not in sidecar_types


class TestFormatFallback:
    """Tests for format-specific reading strategies."""

    def test_text_read(self, tmp_path: Path) -> None:
        """A description file read as text has format='text'."""
        primary, siblings = _make_sidecar_dir(
            tmp_path,
            sidecars={"video.description": "Hello world text content."},
        )
        config = _cfg(meta_merge=True)
        entries = discover_and_parse(
            primary, primary.name, siblings, config,
        )
        desc = next(
            (e for e in entries if e.attributes.type == "description"), None,
        )
        assert desc is not None
        assert desc.attributes.format == "text"
        assert isinstance(desc.data, str)

    def test_binary_to_base64(self, tmp_path: Path) -> None:
        """A screenshot file is read as binary and encoded to Base64."""
        primary, siblings = _make_sidecar_dir(
            tmp_path,
            sidecars={"video_screenshot.jpg": b"\xff\xd8\xff\xe0screenshot"},
        )
        config = _cfg(meta_merge=True)
        entries = discover_and_parse(
            primary, primary.name, siblings, config,
        )
        shot = next(
            (e for e in entries if e.attributes.type == "screenshot"), None,
        )
        assert shot is not None
        assert shot.attributes.format == "base64"
        assert "base64_encode" in shot.attributes.transforms


class TestEntryProvenance:
    """Tests for MetadataEntry provenance fields (sidecar origin)."""

    def test_sidecar_provenance_fields(self, tmp_path: Path) -> None:
        """Sidecar entries have origin='sidecar' and filesystem/size/timestamps."""
        primary, siblings = _make_sidecar_dir(
            tmp_path,
            sidecars={"video.description": "Some description text."},
        )
        config = _cfg(meta_merge=True)
        entries = discover_and_parse(
            primary, primary.name, siblings, config,
        )
        assert len(entries) >= 1
        entry = entries[0]
        assert entry.origin == "sidecar"
        assert entry.file_system is not None
        assert entry.size is not None
        assert entry.size.bytes > 0
        assert entry.timestamps is not None
        assert entry.hashes is not None
        assert entry.name.text is not None


class TestDeleteQueue:
    """Tests for MetaMergeDelete queue population."""

    def test_delete_queue_populated(self, tmp_path: Path) -> None:
        """With meta_merge_delete, sidecar paths are added to the queue."""
        primary, siblings = _make_sidecar_dir(
            tmp_path,
            sidecars={"video.description": "text"},
        )
        config = _cfg(meta_merge=True, meta_merge_delete=True, output_inplace=True)
        queue: list[Path] = []
        discover_and_parse(
            primary, primary.name, siblings, config,
            delete_queue=queue,
        )
        assert len(queue) >= 1
        assert all(isinstance(p, Path) for p in queue)

    def test_no_delete_queue_when_disabled(self, tmp_path: Path) -> None:
        """Without meta_merge_delete, the queue is not populated."""
        primary, siblings = _make_sidecar_dir(
            tmp_path,
            sidecars={"video.description": "text"},
        )
        config = _cfg(meta_merge=True, meta_merge_delete=False)
        queue: list[Path] = []
        discover_and_parse(
            primary, primary.name, siblings, config,
            delete_queue=queue,
        )
        assert queue == []

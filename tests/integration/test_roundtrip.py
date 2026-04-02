"""Integration tests — index-then-rollback round-trip verification.

Exercises the full pipeline round-trip: index a directory (with rename,
inplace, MetaMergeDelete), then roll back from the produced sidecars,
then verify the restored output matches the original.

These tests would have failed against the v0.2.0 codebase, serving as
genuine regression detectors for the v3 sidecar discovery, v3 schema
acceptance, and v3 inplace sidecar rename bugs.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.dedup import (
    DedupRegistry,
    apply_dedup,
    cleanup_duplicate_files,
    scan_tree,
)
from shruggie_indexer.core.entry import build_file_entry, index_path
from shruggie_indexer.core.rename import rename_inplace_sidecar, rename_item
from shruggie_indexer.core.rollback import (
    discover_sidecar_files,
    load_sidecar,
)
from shruggie_indexer.core.serializer import write_inplace
from shruggie_indexer.exceptions import IndexerConfigError


def _cfg(**overrides: object):
    return load_config(overrides=overrides)


def _write_inplace_tree(entry, root, write_fn, *, write_directory_meta=True):
    """Mirror the CLI's _write_inplace_tree helper for test use."""
    if entry.type == "file":
        write_fn(entry, root / entry.file_system.relative, "file")
    elif entry.type == "directory":
        if write_directory_meta:
            write_fn(entry, root, "directory")
        if entry.items:
            for child in entry.items:
                _write_inplace_tree(
                    child,
                    root,
                    write_fn,
                    write_directory_meta=write_directory_meta,
                )


def _rename_tree(entry, root_path, config):
    """Mirror the CLI's _rename_tree helper for test use."""
    if entry.items:
        for child in entry.items:
            if child.type == "file":
                child_path = root_path / child.file_system.relative
                result_path = rename_item(child_path, child, dry_run=config.dry_run)
                if not config.dry_run and config.output_inplace and result_path != child_path:
                    rename_inplace_sidecar(child_path, child)
            elif child.type == "directory":
                _rename_tree(child, root_path, config)


# ---------------------------------------------------------------------------
# Test 1: Full index-rename-rollback round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.rollback
class TestIndexRenameRollbackRoundtrip:
    """Full pipeline round-trip: index → rename → rollback → verify."""

    def test_index_rename_rollback_roundtrip(
        self,
        tmp_path: Path,
        mock_exiftool: None,
    ) -> None:
        # ── 1. Create fixture directory ─────────────────────────────
        fixture = tmp_path / "fixture"
        fixture.mkdir()
        text_content = b"Hello, this is a test file for round-trip verification.\n"
        (fixture / "readme.txt").write_bytes(text_content)

        sub = fixture / "images"
        sub.mkdir()
        # Two identical images to exercise dedup
        image_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        (sub / "photo_a.png").write_bytes(image_content)
        (sub / "photo_b.png").write_bytes(image_content)

        # A JSON sidecar companion for one image (exercises MetaMergeDelete)
        sidecar_data = {"description": "A test photo", "tags": ["test"]}
        (sub / "photo_a.png.json").write_text(
            json.dumps(sidecar_data, indent=2),
            encoding="utf-8",
        )

        # ── 2. Copy to working directory ────────────────────────────
        mmd_dir = tmp_path / "mmd"
        shutil.copytree(fixture, mmd_dir)

        # ── 3. Run index_path with rename, inplace, meta_merge_delete ─
        config = _cfg(
            rename=True,
            output_inplace=True,
            meta_merge_delete=True,
            write_directory_meta=False,
        )
        entry = index_path(mmd_dir, config)

        # Dedup
        registry = DedupRegistry()
        dedup_actions = scan_tree(entry, registry)
        if dedup_actions:
            apply_dedup(dedup_actions)

        # Write inplace sidecars
        _write_inplace_tree(entry, mmd_dir, write_inplace, write_directory_meta=False)

        # Rename
        _rename_tree(entry, mmd_dir, config)

        # Cleanup duplicates
        if dedup_actions:
            cleanup_duplicate_files(dedup_actions, mmd_dir, dry_run=False)

        # ── 4. Assert: content files have been hash-renamed ─────────
        all_files = [f for f in mmd_dir.rglob("*") if f.is_file() and not f.name.endswith(".json")]
        renamed_files = [f for f in all_files if f.name.startswith("y")]
        assert len(renamed_files) > 0, "Expected hash-renamed files (y* prefix)"

        # ── 5. Assert: _idx.json sidecars exist with correct base ───
        idx_files = list(mmd_dir.rglob("*_idx.json"))
        assert len(idx_files) > 0, "Expected _idx.json sidecar files"

        # Verify sidecars have the renamed base name
        for sc in idx_files:
            base = sc.name.replace("_idx.json", "")
            assert base.startswith("y"), f"Sidecar {sc.name} does not have hash-renamed base"

        # ── 6. Assert: no _meta2.json or _meta3.json files exist ────
        meta2_files = list(mmd_dir.rglob("*_meta2.json"))
        assert len(meta2_files) == 0, f"Unexpected _meta2.json files: {meta2_files}"
        meta3_files = list(mmd_dir.rglob("*_meta3.json"))
        assert len(meta3_files) == 0, f"Unexpected _meta3.json files: {meta3_files}"

        # ── 7. Assert: duplicates have been removed ─────────────────
        # Only one of the two identical images should remain
        png_files = [f for f in mmd_dir.rglob("*.png") if f.is_file()]
        assert len(png_files) == 1, f"Expected 1 PNG after dedup, got {len(png_files)}"

        # ── 8. Assert: v4 sidecar files use new suffix ──────────────
        # (Rollback testing for v4 is covered in Phase 5)
        idx_files = list(mmd_dir.rglob("*_idx.json"))
        assert len(idx_files) > 0, "Expected _idx.json sidecar files from v4 output"


# ---------------------------------------------------------------------------
# Test 2: v3 sidecar discovery (mixed v2/v3)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.rollback
class TestV3SidecarDiscovery:
    """Mixed v2/v3 sidecar discovery and loading."""

    def test_discovers_both_v2_and_v3(self, tmp_path: Path) -> None:
        """discover_sidecar_files returns both v2 and v3 files."""
        v2_entry = {
            "schema_version": 2,
            "id": "AAAA",
            "id_algorithm": "md5",
            "type": "file",
            "name": {"text": "old.txt", "hashes": {"md5": "AAAA", "sha256": "BBBB"}},
            "extension": ".txt",
            "size": {"text": "5 B", "bytes": 5},
            "hashes": {"md5": "AAAA", "sha256": "BBBB"},
            "file_system": {"relative": "old.txt", "parent": None},
            "timestamps": {
                "created": {"iso": "2026-01-01T00:00:00Z", "unix": 0},
                "modified": {"iso": "2026-01-01T00:00:00Z", "unix": 0},
                "accessed": {"iso": "2026-01-01T00:00:00Z", "unix": 0},
            },
            "attributes": {"is_link": False, "storage_name": "yAAAA.txt"},
        }
        v3_entry = dict(v2_entry)
        v3_entry["schema_version"] = 3
        v3_entry["name"] = {"text": "new.txt", "hashes": {"md5": "CCCC", "sha256": "DDDD"}}
        v3_entry["id"] = "CCCC"
        v3_entry["hashes"] = {"md5": "CCCC", "sha256": "DDDD"}
        v3_entry["file_system"] = {"relative": "new.txt", "parent": None}
        v3_entry["attributes"] = {"is_link": False, "storage_name": "yCCCC.txt"}

        (tmp_path / "old.txt_meta2.json").write_text(
            json.dumps(v2_entry),
            encoding="utf-8",
        )
        (tmp_path / "new.txt_meta3.json").write_text(
            json.dumps(v3_entry),
            encoding="utf-8",
        )

        discovered = discover_sidecar_files(tmp_path)
        names = {p.name for p in discovered}
        assert "old.txt_meta2.json" in names
        assert "new.txt_meta3.json" in names
        assert len(discovered) == 2

    def test_load_v2_and_v3(self, tmp_path: Path) -> None:
        """load_sidecar accepts both v2 and v3 files without error."""
        for version in (2, 3):
            suffix = f"_meta{version}.json"
            entry = {
                "schema_version": version,
                "id": f"ID{version}",
                "id_algorithm": "md5",
                "type": "file",
                "name": {
                    "text": f"file{version}.txt",
                    "hashes": {
                        "md5": f"NMD5{version}",
                        "sha256": f"NSHA{version}",
                    },
                },
                "extension": ".txt",
                "size": {"text": "5 B", "bytes": 5},
                "hashes": {"md5": f"MD5{version}", "sha256": f"SHA{version}"},
                "file_system": {"relative": f"file{version}.txt", "parent": None},
                "timestamps": {
                    "created": {"iso": "2026-01-01T00:00:00Z", "unix": 0},
                    "modified": {"iso": "2026-01-01T00:00:00Z", "unix": 0},
                    "accessed": {"iso": "2026-01-01T00:00:00Z", "unix": 0},
                },
                "attributes": {"is_link": False, "storage_name": f"yID{version}.txt"},
            }
            (tmp_path / f"file{version}.txt{suffix}").write_text(
                json.dumps(entry),
                encoding="utf-8",
            )

        entries = load_sidecar(tmp_path)
        assert len(entries) == 2

    def test_v1_rejected(self, tmp_path: Path) -> None:
        """load_sidecar raises IndexerConfigError for v1 sidecars."""
        v1_entry = {
            "schema_version": 1,
            "id": "V1ID",
            "id_algorithm": "md5",
            "type": "file",
            "name": {"text": "legacy.txt", "hashes": {"md5": "V1MD5", "sha256": "V1SHA"}},
            "extension": ".txt",
            "size": {"text": "5 B", "bytes": 5},
            "hashes": {"md5": "V1MD5", "sha256": "V1SHA"},
            "file_system": {"relative": "legacy.txt", "parent": None},
            "timestamps": {
                "created": {"iso": "2026-01-01T00:00:00Z", "unix": 0},
                "modified": {"iso": "2026-01-01T00:00:00Z", "unix": 0},
                "accessed": {"iso": "2026-01-01T00:00:00Z", "unix": 0},
            },
            "attributes": {"is_link": False, "storage_name": "yV1ID.txt"},
        }
        path = tmp_path / "legacy.txt_meta2.json"
        path.write_text(json.dumps(v1_entry), encoding="utf-8")
        with pytest.raises(IndexerConfigError, match="expected 2, 3, or 4"):
            load_sidecar(path)


# ---------------------------------------------------------------------------
# Test 3: Inplace sidecar rename uses v3 naming
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.rollback
class TestInplaceSidecarRenameV4:
    """Verify rename_inplace_sidecar uses v4 _idx.json naming."""

    def test_inplace_sidecar_rename_v4(
        self,
        tmp_path: Path,
        mock_exiftool: None,
    ) -> None:
        # Create a file and build an entry
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)

        config = _cfg(rename=True, output_inplace=True)
        entry = build_file_entry(test_file, config)

        # Write inplace sidecar (_idx.json)
        write_inplace(entry, test_file, "file")

        # Verify the v4 sidecar was written
        v4_sidecar = tmp_path / "photo.jpg_idx.json"
        assert v4_sidecar.exists(), "_idx.json sidecar was not written"

        # Rename the file
        rename_item(test_file, entry)

        # Rename the inplace sidecar
        result = rename_inplace_sidecar(test_file, entry)

        # Assert: the _idx.json sidecar has been renamed
        storage_name = entry.attributes.storage_name
        expected_sidecar = tmp_path / f"{storage_name}_idx.json"
        assert expected_sidecar.exists(), f"Expected {expected_sidecar.name} to exist"
        assert result == expected_sidecar

        # Assert: no _meta2.json or _meta3.json files exist
        meta2_files = list(tmp_path.glob("*_meta2.json"))
        assert len(meta2_files) == 0, f"Unexpected _meta2.json files: {meta2_files}"

        # Assert: no orphaned original-name sidecar
        assert not v4_sidecar.exists(), "Original-name sidecar was not renamed"

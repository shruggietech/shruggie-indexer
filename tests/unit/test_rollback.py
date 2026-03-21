"""Unit tests for core/rollback.py — Rollback Engine.

Covers: meta2 loading (per-file sidecar, aggregate tree, directory discovery,
v1 rejection, malformed JSON, duplicate extraction), source resolution,
rollback planning (renamed, non-renamed, duplicates, sidecars, conflicts,
path traversal, flat mode, mixed sessions), rollback execution (dry-run,
file copy, timestamp restoration, sidecar decoding, cancellation), and
hash verification.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from shruggie_indexer.core.rollback import (
    LocalSourceResolver,
    RollbackAction,
    RollbackPlan,
    RollbackResult,
    RollbackStats,
    _entry_from_dict,
    discover_meta2_files,
    execute_rollback,
    load_meta2,
    plan_rollback,
    verify_file_hash,
)
from shruggie_indexer.exceptions import IndexerConfigError, IndexerTargetError
from shruggie_indexer.models.schema import (
    AttributesObject,
    FileSystemObject,
    HashSet,
    IndexEntry,
    MetadataAttributes,
    MetadataEntry,
    NameObject,
    SizeObject,
    TimestampPair,
    TimestampsObject,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "rollback-testbed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hashset(md5: str = "D41D8CD98F00B204E9800998ECF8427E") -> HashSet:
    return HashSet(
        md5=md5,
        sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
    )


def _make_ts(
    created_unix: int = 1771165697408,
    modified_unix: int = 1691106464000,
    accessed_unix: int = 1771165698109,
) -> TimestampsObject:
    return TimestampsObject(
        created=TimestampPair(iso="2026-02-15T09:28:17.408-05:00", unix=created_unix),
        modified=TimestampPair(iso="2023-08-03T19:47:44.000-04:00", unix=modified_unix),
        accessed=TimestampPair(iso="2026-02-15T09:28:18.109-05:00", unix=accessed_unix),
    )


def _make_file_entry(
    name: str = "file.txt",
    storage_name: str | None = None,
    relative: str = "file.txt",
    md5: str = "D41D8CD98F00B204E9800998ECF8427E",
    session_id: str | None = None,
    metadata: list[MetadataEntry] | None = None,
    duplicates: list[IndexEntry] | None = None,
) -> IndexEntry:
    if storage_name is None:
        storage_name = f"y{md5}.{name.rsplit('.', 1)[-1]}"
    return IndexEntry(
        schema_version=2,
        id=f"y{md5}",
        id_algorithm="md5",
        type="file",
        name=NameObject(text=name, hashes=_make_hashset(md5)),
        extension=name.rsplit(".", 1)[-1] if "." in name else None,
        size=SizeObject(text="100 B", bytes=100),
        hashes=_make_hashset(md5),
        file_system=FileSystemObject(relative=relative, parent=None),
        timestamps=_make_ts(),
        attributes=AttributesObject(is_link=False, storage_name=storage_name),
        session_id=session_id,
        metadata=metadata,
        duplicates=duplicates,
    )


def _make_sidecar_metadata(
    name: str = "file.txt.info.json",
    relative: str = "file.txt.info.json",
    fmt: str = "json",
    data: object = None,
) -> MetadataEntry:
    if data is None:
        data = {"key": "value"}
    return MetadataEntry(
        id="zSIDECAR0000000000000000000000000",
        origin="sidecar",
        name=NameObject(text=name, hashes=_make_hashset()),
        hashes=_make_hashset(),
        attributes=MetadataAttributes(
            type="generic_metadata",
            format=fmt,
            transforms=[],
        ),
        data=data,
        file_system=FileSystemObject(relative=relative, parent=None),
        size=SizeObject(text="50 B", bytes=50),
        timestamps=_make_ts(),
    )


# ===========================================================================
# TestLoadMeta2
# ===========================================================================


class TestLoadMeta2:
    """Loading _meta2.json files: sidecars, aggregates, directories."""

    def test_per_file_sidecar(self) -> None:
        """Load a single per-file sidecar (renamed file)."""
        path = FIXTURES / "renamed" / "y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe_meta2.json"
        entries = load_meta2(path)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.type == "file"
        assert entry.name.text == "flashplayer.exe"
        assert entry.attributes.storage_name == "y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe"
        assert entry.file_system.relative == "testdir/flashplayer.exe"
        assert entry.schema_version == 2

    def test_aggregate_tree_flattening(self) -> None:
        """Load an aggregate directory meta2 and flatten to file entries."""
        path = FIXTURES / "aggregate" / "photos_directorymeta2.json"
        entries = load_meta2(path)
        assert len(entries) == 2
        names = {e.name.text for e in entries}
        assert "flashplayer.exe" in names
        assert "testfile.txt" in names
        for e in entries:
            assert e.type == "file"

    def test_directory_discovery_non_recursive(self) -> None:
        """Discover sidecars in a directory (non-recursive)."""
        entries = load_meta2(FIXTURES / "renamed")
        assert len(entries) == 2

    def test_directory_discovery_recursive(self) -> None:
        """Recursive discovery finds sidecars in subdirectories."""
        # The mixed-sessions directory has 3 sidecars
        entries = load_meta2(FIXTURES / "mixed-sessions", recursive=True)
        assert len(entries) == 3

    def test_v1_rejection(self) -> None:
        """v1 sidecar (no schema_version) raises IndexerConfigError."""
        path = FIXTURES / "v1" / "legacy_meta.json"
        with pytest.raises(IndexerConfigError, match="Unsupported schema version"):
            load_meta2(path)

    def test_malformed_json(self) -> None:
        """Invalid JSON raises IndexerConfigError."""
        path = FIXTURES / "malformed" / "bad_meta2.json"
        with pytest.raises(IndexerConfigError, match="Invalid JSON"):
            load_meta2(path)

    def test_nonexistent_path(self) -> None:
        """Non-existent path raises IndexerTargetError."""
        path = FIXTURES / "does_not_exist_meta2.json"
        with pytest.raises(IndexerTargetError, match="does not exist"):
            load_meta2(path)

    def test_duplicate_extraction(self) -> None:
        """Duplicates from duplicates[] are extracted with annotations."""
        path = FIXTURES / "deduplicated" / "y2FFA202F241801EF7FF9C7212EBBC693.jpg_meta2.json"
        entries = load_meta2(path)
        # Should have canonical + 1 duplicate = 2 entries
        assert len(entries) == 2
        canonical = entries[0]
        assert canonical.name.text == "photo.jpg"
        duplicate = entries[1]
        assert duplicate.name.text == "photo_copy.jpg"

    def test_sidecar_metadata_preserved(self) -> None:
        """Metadata entries (including sidecar origin) are preserved."""
        path = FIXTURES / "deduplicated" / "y2FFA202F241801EF7FF9C7212EBBC693.jpg_meta2.json"
        entries = load_meta2(path)
        canonical = entries[0]
        assert canonical.metadata is not None
        assert len(canonical.metadata) == 1
        meta = canonical.metadata[0]
        assert meta.origin == "sidecar"
        assert meta.name.text == "photo.jpg.info.json"


class TestDiscoverMeta2Files:
    """discover_meta2_files() behavior."""

    def test_non_recursive(self) -> None:
        files = discover_meta2_files(FIXTURES / "renamed")
        assert len(files) == 2
        assert all(f.name.endswith("_meta2.json") for f in files)
        # Should be sorted
        assert files == sorted(files)

    def test_recursive(self) -> None:
        """Recursive discovers files in subdirectories."""
        # Running recursive on the entire rollback-testbed should find all meta2 files
        files = discover_meta2_files(FIXTURES, recursive=True)
        assert len(files) >= 7  # at least the known fixtures

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory returns empty list."""
        files = discover_meta2_files(tmp_path)
        assert files == []


# ===========================================================================
# TestLocalSourceResolver
# ===========================================================================


class TestLocalSourceResolver:
    """LocalSourceResolver: file location strategies."""

    def test_storage_name_match(self) -> None:
        """Finds file by storage_name (renamed file)."""
        resolver = LocalSourceResolver(verify_hash=False)
        entry = _make_file_entry(
            name="flashplayer.exe",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        result = resolver.resolve(entry, FIXTURES / "renamed")
        assert result is not None
        assert result.name == "y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe"

    def test_original_name_match(self) -> None:
        """Finds file by original name (non-renamed file)."""
        resolver = LocalSourceResolver(verify_hash=False)
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="ySOMETHINGELSE.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
        )
        result = resolver.resolve(entry, FIXTURES / "non-renamed")
        assert result is not None
        assert result.name == "readme.txt"

    def test_not_found(self) -> None:
        """Returns None when file cannot be found."""
        resolver = LocalSourceResolver(verify_hash=False)
        entry = _make_file_entry(
            name="doesnotexist.txt",
            storage_name="yNONEXISTENT.txt",
        )
        result = resolver.resolve(entry, FIXTURES / "renamed")
        assert result is None

    def test_none_search_dir(self) -> None:
        """Returns None when search_dir is None."""
        resolver = LocalSourceResolver(verify_hash=False)
        entry = _make_file_entry()
        result = resolver.resolve(entry, None)
        assert result is None

    def test_hash_verification_pass(self) -> None:
        """Hash verification passes for matching content."""
        resolver = LocalSourceResolver(verify_hash=True)
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="yNONEXISTENT.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
        )
        # The file exists and hash should match
        result = resolver.resolve(entry, FIXTURES / "non-renamed")
        assert result is not None

    def test_hash_verification_mismatch_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Hash verification mismatch logs a warning but still returns path."""
        resolver = LocalSourceResolver(verify_hash=True)
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="yNONEXISTENT.txt",
            md5="FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF",  # Wrong hash
        )
        import logging
        with caplog.at_level(logging.WARNING, logger="shruggie_indexer.core.rollback"):
            result = resolver.resolve(entry, FIXTURES / "non-renamed")
        assert result is not None  # Still returns the path
        assert any("Hash mismatch" in r.message for r in caplog.records)


# ===========================================================================
# TestPlanRollback
# ===========================================================================


class TestPlanRollback:
    """plan_rollback() for various scenarios."""

    def test_renamed_file_structured(self, tmp_path: Path) -> None:
        """Renamed file restores to structured path."""
        entry = _make_file_entry(
            name="flashplayer.exe",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="testdir/flashplayer.exe",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "renamed",
            verify=False,
        )
        restores = [a for a in plan.actions if a.action_type == "restore" and not a.skip_reason]
        assert len(restores) == 1
        assert restores[0].target_path == tmp_path / "testdir" / "flashplayer.exe"
        assert plan.stats.files_to_restore == 1

    def test_non_renamed_file(self, tmp_path: Path) -> None:
        """Non-renamed file found by original name."""
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
        )
        restores = [a for a in plan.actions if a.action_type == "restore" and not a.skip_reason]
        assert len(restores) == 1

    def test_source_not_found(self, tmp_path: Path) -> None:
        """Missing source file produces skipped action."""
        entry = _make_file_entry(
            name="ghost.txt",
            storage_name="yNONEXISTENT.txt",
            relative="ghost.txt",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=tmp_path,
            verify=False,
        )
        skipped = [a for a in plan.actions if a.skip_reason]
        assert len(skipped) == 1
        assert skipped[0].skip_reason == "Source file not found"
        assert plan.stats.skipped_unresolvable == 1

    def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Path with .. segments is rejected."""
        entry = _make_file_entry(
            name="evil.txt",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="../../../etc/evil.txt",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "renamed",
            verify=False,
        )
        skipped = [a for a in plan.actions if a.skip_reason == "Path traversal rejected"]
        assert len(skipped) == 1

    def test_conflict_same_hash(self, tmp_path: Path) -> None:
        """Target exists with same hash → skipped as already exists."""
        # Create target file with same content
        target = tmp_path / "readme.txt"
        target.write_bytes(b"README content for non-renamed rollback test.\n")

        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=True,
        )
        skipped = [a for a in plan.actions if a.skip_reason]
        assert len(skipped) == 1
        assert "Already exists (same content)" in skipped[0].skip_reason
        assert plan.stats.skipped_already_exists == 1

    def test_conflict_different_hash_no_force(self, tmp_path: Path) -> None:
        """Target exists with different hash, no force → skipped."""
        target = tmp_path / "readme.txt"
        target.write_text("different content", encoding="utf-8")

        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=True,
            force=False,
        )
        skipped = [a for a in plan.actions if a.skip_reason]
        assert len(skipped) == 1
        assert "Already exists (different content)" in skipped[0].skip_reason
        assert plan.stats.skipped_conflict == 1

    def test_conflict_force_overwrites(self, tmp_path: Path) -> None:
        """Target exists, force=True → not skipped."""
        target = tmp_path / "readme.txt"
        target.write_text("different content", encoding="utf-8")

        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=True,
            force=True,
        )
        restores = [a for a in plan.actions if a.action_type == "restore" and not a.skip_reason]
        assert len(restores) == 1

    def test_skip_duplicates_flag(self, tmp_path: Path) -> None:
        """skip_duplicates=True excludes duplicate entries."""
        entries = load_meta2(
            FIXTURES / "deduplicated" / "y2FFA202F241801EF7FF9C7212EBBC693.jpg_meta2.json",
        )
        assert len(entries) == 2  # canonical + duplicate

        plan = plan_rollback(
            entries,
            target_dir=tmp_path,
            source_dir=FIXTURES / "deduplicated",
            verify=False,
            skip_duplicates=True,
        )
        dup_actions = [a for a in plan.actions if a.action_type == "duplicate_restore"]
        assert len(dup_actions) == 0

    def test_sidecar_restoration_planned(self, tmp_path: Path) -> None:
        """Sidecar metadata with origin=sidecar creates sidecar_restore action."""
        meta = _make_sidecar_metadata()
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
            metadata=[meta],
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
        )
        sidecar_actions = [a for a in plan.actions if a.action_type == "sidecar_restore"]
        assert len(sidecar_actions) == 1
        assert sidecar_actions[0].sidecar_data is not None

    def test_no_sidecar_restoration_when_disabled(self, tmp_path: Path) -> None:
        """restore_sidecars=False suppresses sidecar restoration."""
        meta = _make_sidecar_metadata()
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
            metadata=[meta],
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
            restore_sidecars=False,
        )
        sidecar_actions = [a for a in plan.actions if a.action_type == "sidecar_restore"]
        assert len(sidecar_actions) == 0

    def test_directory_actions_created(self, tmp_path: Path) -> None:
        """Structured mode creates mkdir actions for subdirectories."""
        entry = _make_file_entry(
            name="flashplayer.exe",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="testdir/flashplayer.exe",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "renamed",
            verify=False,
        )
        mkdir_actions = [a for a in plan.actions if a.action_type == "mkdir"]
        assert len(mkdir_actions) >= 1
        assert plan.stats.directories_to_create >= 1


# ===========================================================================
# TestPlanRollbackFlat
# ===========================================================================


class TestPlanRollbackFlat:
    """Flat mode planning."""

    def test_flat_target_path(self, tmp_path: Path) -> None:
        """Flat mode uses name.text directly in target_dir."""
        entry = _make_file_entry(
            name="flashplayer.exe",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="deeply/nested/path/flashplayer.exe",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "renamed",
            verify=False,
            flat=True,
        )
        restores = [a for a in plan.actions if a.action_type == "restore" and not a.skip_reason]
        assert len(restores) == 1
        assert restores[0].target_path == tmp_path / "flashplayer.exe"

    def test_flat_no_mkdir(self, tmp_path: Path) -> None:
        """Flat mode does not create mkdir actions."""
        entry = _make_file_entry(
            name="flashplayer.exe",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="deeply/nested/path/flashplayer.exe",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "renamed",
            verify=False,
            flat=True,
        )
        mkdir_actions = [a for a in plan.actions if a.action_type == "mkdir"]
        assert len(mkdir_actions) == 0

    def test_flat_collision(self, tmp_path: Path) -> None:
        """Flat mode collision: same name.text from different entries."""
        entry1 = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="dir1/readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
        )
        entry2 = _make_file_entry(
            name="readme.txt",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="dir2/readme.txt",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        plan = plan_rollback(
            [entry1, entry2],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
            flat=True,
        )
        collisions = [a for a in plan.actions if a.skip_reason == "Flat restore collision"]
        assert len(collisions) == 1
        assert plan.stats.skipped_conflict >= 1


# ===========================================================================
# TestPlanRollbackMixedSessions
# ===========================================================================


class TestPlanRollbackMixedSessions:
    """Mixed-session warnings."""

    def test_mixed_sessions_warning_structured(self, tmp_path: Path) -> None:
        """Structured mode with mixed session_ids emits warning."""
        entry1 = _make_file_entry(
            name="beach.jpg",
            storage_name="y2D5109B8C84BDA94C4D47F034AABA7EA.jpg",
            relative="vacation/beach.jpg",
            md5="2D5109B8C84BDA94C4D47F034AABA7EA",
            session_id="aaaa1111-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
        )
        entry2 = _make_file_entry(
            name="drone.mp4",
            storage_name="yA4139F8B18A54766AC5FFBEEBF3AC064.mp4",
            relative="media/clips/drone.mp4",
            md5="A4139F8B18A54766AC5FFBEEBF3AC064",
            session_id="bbbb2222-bbbb-4bbb-bbbb-bbbbbbbbbbbb",
        )
        plan = plan_rollback(
            [entry1, entry2],
            target_dir=tmp_path,
            source_dir=FIXTURES / "mixed-sessions",
            verify=False,
        )
        assert len(plan.warnings) == 1
        assert "distinct indexing sessions" in plan.warnings[0]

    def test_no_warning_in_flat_mode(self, tmp_path: Path) -> None:
        """Flat mode with mixed sessions does NOT emit warning."""
        entry1 = _make_file_entry(
            name="beach.jpg",
            storage_name="y2D5109B8C84BDA94C4D47F034AABA7EA.jpg",
            relative="vacation/beach.jpg",
            md5="2D5109B8C84BDA94C4D47F034AABA7EA",
            session_id="aaaa1111-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
        )
        entry2 = _make_file_entry(
            name="drone.mp4",
            storage_name="yA4139F8B18A54766AC5FFBEEBF3AC064.mp4",
            relative="media/clips/drone.mp4",
            md5="A4139F8B18A54766AC5FFBEEBF3AC064",
            session_id="bbbb2222-bbbb-4bbb-bbbb-bbbbbbbbbbbb",
        )
        plan = plan_rollback(
            [entry1, entry2],
            target_dir=tmp_path,
            source_dir=FIXTURES / "mixed-sessions",
            verify=False,
            flat=True,
        )
        assert len(plan.warnings) == 0

    def test_no_warning_single_session(self, tmp_path: Path) -> None:
        """Single session does not emit warning."""
        entry1 = _make_file_entry(
            name="flashplayer.exe",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="testdir/flashplayer.exe",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
            session_id="same-session-id",
        )
        entry2 = _make_file_entry(
            name="testfile.txt",
            storage_name="y1EC051B0043B6D653CC431DE3F2EE2F1.txt",
            relative="testdir/testfile.txt",
            md5="1EC051B0043B6D653CC431DE3F2EE2F1",
            session_id="same-session-id",
        )
        plan = plan_rollback(
            [entry1, entry2],
            target_dir=tmp_path,
            source_dir=FIXTURES / "renamed",
            verify=False,
        )
        assert len(plan.warnings) == 0


# ===========================================================================
# TestTargetDefault
# ===========================================================================


class TestTargetDefault:
    """Core engine always receives explicit target_dir."""

    def test_target_dir_is_required(self) -> None:
        """plan_rollback() signature requires target_dir (not optional)."""
        import inspect
        sig = inspect.signature(plan_rollback)
        param = sig.parameters["target_dir"]
        assert param.default is inspect.Parameter.empty


# ===========================================================================
# TestExecuteRollback
# ===========================================================================


class TestExecuteRollback:
    """Execute rollback: dry-run, file copy, timestamps, sidecars, cancel."""

    def test_dry_run_no_writes(self, tmp_path: Path) -> None:
        """Dry run logs actions but does not create files."""
        entry = _make_file_entry(
            name="flashplayer.exe",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="testdir/flashplayer.exe",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "renamed",
            verify=False,
        )
        result = execute_rollback(plan, dry_run=True)
        assert result.restored >= 1
        assert result.failed == 0
        # File should NOT exist
        assert not (tmp_path / "testdir" / "flashplayer.exe").exists()

    def test_file_copy_and_timestamps(self, tmp_path: Path) -> None:
        """File is copied and timestamps are set from sidecar."""
        entry = _make_file_entry(
            name="flashplayer.exe",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="testdir/flashplayer.exe",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "renamed",
            verify=False,
        )
        result = execute_rollback(plan)
        assert result.restored == 1
        assert result.failed == 0

        restored = tmp_path / "testdir" / "flashplayer.exe"
        assert restored.exists()

        # Verify timestamps BEFORE read_bytes (reading updates atime)
        stat = restored.stat()
        expected_mtime = 1691106464000 / 1000  # Convert ms → s
        expected_atime = 1771165698109 / 1000
        assert abs(stat.st_mtime - expected_mtime) < 2
        assert abs(stat.st_atime - expected_atime) < 2

        assert restored.read_bytes() == b"This is a test executable file content for rollback testing.\n"

    def test_directory_creation(self, tmp_path: Path) -> None:
        """Directories are created for structured restore."""
        entry = _make_file_entry(
            name="flashplayer.exe",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="deep/nested/dir/flashplayer.exe",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "renamed",
            verify=False,
        )
        result = execute_rollback(plan)
        assert result.restored == 1
        assert (tmp_path / "deep" / "nested" / "dir" / "flashplayer.exe").exists()

    def test_duplicate_copy(self, tmp_path: Path) -> None:
        """Duplicate files are copied from canonical source."""
        entries = load_meta2(
            FIXTURES / "deduplicated" / "y2FFA202F241801EF7FF9C7212EBBC693.jpg_meta2.json",
        )
        plan = plan_rollback(
            entries,
            target_dir=tmp_path,
            source_dir=FIXTURES / "deduplicated",
            verify=False,
        )
        result = execute_rollback(plan)
        assert result.restored >= 1
        # The canonical should be restored
        canonical_path = tmp_path / "images" / "photo.jpg"
        assert canonical_path.exists()

    def test_sidecar_json_restore(self, tmp_path: Path) -> None:
        """Sidecar with format=json is restored correctly."""
        meta = _make_sidecar_metadata(
            name="file.info.json",
            relative="file.info.json",
            fmt="json",
            data={"camera": "Canon", "iso": 400},
        )
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
            metadata=[meta],
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
        )
        result = execute_rollback(plan)
        assert result.sidecars_restored == 1

        sidecar_path = tmp_path / "file.info.json"
        assert sidecar_path.exists()
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert data["camera"] == "Canon"
        assert data["iso"] == 400

    def test_sidecar_text_restore(self, tmp_path: Path) -> None:
        """Sidecar with format=text is restored correctly."""
        meta = _make_sidecar_metadata(
            name="notes.txt",
            relative="notes.txt",
            fmt="text",
            data="These are my notes about this file.",
        )
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
            metadata=[meta],
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
        )
        result = execute_rollback(plan)
        assert result.sidecars_restored == 1
        assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "These are my notes about this file."

    def test_sidecar_base64_restore(self, tmp_path: Path) -> None:
        """Sidecar with format=base64 is restored as binary."""
        import base64
        original_bytes = b"\x89PNG\r\n\x1a\nfake png data"
        encoded = base64.b64encode(original_bytes).decode("ascii")

        meta = _make_sidecar_metadata(
            name="thumb.png",
            relative="thumb.png",
            fmt="base64",
            data=encoded,
        )
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
            metadata=[meta],
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
        )
        result = execute_rollback(plan)
        assert result.sidecars_restored == 1
        assert (tmp_path / "thumb.png").read_bytes() == original_bytes

    def test_sidecar_lines_restore(self, tmp_path: Path) -> None:
        """Sidecar with format=lines is restored as joined lines."""
        meta = _make_sidecar_metadata(
            name="subtitles.srt",
            relative="subtitles.srt",
            fmt="lines",
            data=["1", "00:00:00,000 --> 00:00:02,000", "Hello"],
        )
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
            metadata=[meta],
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
        )
        result = execute_rollback(plan)
        assert result.sidecars_restored == 1
        content = (tmp_path / "subtitles.srt").read_text(encoding="utf-8")
        assert content == "1\n00:00:00,000 --> 00:00:02,000\nHello"

    def test_sidecar_url_restore_functional(self, tmp_path: Path) -> None:
        """Sidecar with .url content restores as a functional Windows shortcut."""
        url_content = "[InternetShortcut]\nURL=https://example.com\n"
        meta = _make_sidecar_metadata(
            name="bookmark.url",
            relative="bookmark.url",
            fmt="text",
            data=url_content,
        )
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
            metadata=[meta],
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
        )
        result = execute_rollback(plan)
        assert result.sidecars_restored == 1
        restored = (tmp_path / "bookmark.url").read_text(encoding="utf-8")
        assert "[InternetShortcut]" in restored
        assert "URL=https://example.com" in restored

    def test_sidecar_lnk_restore_byte_perfect(self, tmp_path: Path) -> None:
        """Sidecar with .lnk base64 restores as byte-perfect binary copy."""
        import base64 as b64
        original_bytes = b"\x4c\x00\x00\x00" + b"\x00" * 72 + b"lnk_payload"
        encoded = b64.b64encode(original_bytes).decode("ascii")
        meta = _make_sidecar_metadata(
            name="shortcut.lnk",
            relative="shortcut.lnk",
            fmt="base64",
            data=encoded,
        )
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
            metadata=[meta],
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
        )
        result = execute_rollback(plan)
        assert result.sidecars_restored == 1
        assert (tmp_path / "shortcut.lnk").read_bytes() == original_bytes

    def test_sidecar_json_compact_restore(self, tmp_path: Path) -> None:
        """JSON sidecar with json_style='compact' restores as compact JSON."""
        meta = _make_sidecar_metadata(
            name="file.info.json",
            relative="file.info.json",
            fmt="json",
            data={"camera": "Canon", "iso": 400},
        )
        meta.attributes.json_style = "compact"
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
            metadata=[meta],
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
        )
        result = execute_rollback(plan)
        assert result.sidecars_restored == 1
        content = (tmp_path / "file.info.json").read_text(encoding="utf-8")
        # Compact: no whitespace between keys/values
        assert "\n" not in content
        assert " " not in content or content.count(" ") == 0
        parsed = json.loads(content)
        assert parsed["camera"] == "Canon"

    def test_sidecar_json_pretty_restore(self, tmp_path: Path) -> None:
        """JSON sidecar with json_style='pretty' restores as indented JSON."""
        meta = _make_sidecar_metadata(
            name="file.info.json",
            relative="file.info.json",
            fmt="json",
            data={"camera": "Canon", "iso": 400},
        )
        meta.attributes.json_style = "pretty"
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
            metadata=[meta],
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
        )
        result = execute_rollback(plan)
        assert result.sidecars_restored == 1
        content = (tmp_path / "file.info.json").read_text(encoding="utf-8")
        # Pretty: has newlines and indentation
        assert "\n" in content
        parsed = json.loads(content)
        assert parsed["camera"] == "Canon"

    def test_sidecar_json_no_style_defaults_compact(self, tmp_path: Path) -> None:
        """JSON sidecar without json_style defaults to compact (backward compat)."""
        meta = _make_sidecar_metadata(
            name="file.info.json",
            relative="file.info.json",
            fmt="json",
            data={"key": "value"},
        )
        # json_style is None (default) — should restore as compact
        assert meta.attributes.json_style is None
        entry = _make_file_entry(
            name="readme.txt",
            storage_name="y0654CDF77702945DA87A8B4E72E98EEE.txt",
            relative="readme.txt",
            md5="0654CDF77702945DA87A8B4E72E98EEE",
            metadata=[meta],
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "non-renamed",
            verify=False,
        )
        result = execute_rollback(plan)
        assert result.sidecars_restored == 1
        content = (tmp_path / "file.info.json").read_text(encoding="utf-8")
        # Should be compact (no whitespace)
        assert "\n" not in content

    def test_cancellation(self, tmp_path: Path) -> None:
        """Cancellation stops processing and returns partial result."""
        entry1 = _make_file_entry(
            name="flashplayer.exe",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="flashplayer.exe",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        entry2 = _make_file_entry(
            name="testfile.txt",
            storage_name="y1EC051B0043B6D653CC431DE3F2EE2F1.txt",
            relative="testfile.txt",
            md5="1EC051B0043B6D653CC431DE3F2EE2F1",
        )
        plan = plan_rollback(
            [entry1, entry2],
            target_dir=tmp_path,
            source_dir=FIXTURES / "renamed",
            verify=False,
        )
        cancel = threading.Event()
        cancel.set()  # Pre-set → immediate cancellation

        result = execute_rollback(plan, cancel_event=cancel)
        # Should have stopped early — total restored + failed < total planned
        assert result.restored + result.failed < 2

    def test_error_handling_copy_failure(self, tmp_path: Path) -> None:
        """Copy failure is caught and recorded."""
        entry = _make_file_entry(
            name="flashplayer.exe",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="flashplayer.exe",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "renamed",
            verify=False,
        )

        # Mock shutil.copy2 to raise
        with patch("shruggie_indexer.core.rollback.shutil.copy2", side_effect=OSError("disk full")):
            result = execute_rollback(plan)
        assert result.failed == 1
        assert len(result.errors) == 1
        assert "disk full" in result.errors[0]

    def test_flat_mode_execution(self, tmp_path: Path) -> None:
        """Flat mode places files directly in target directory."""
        entry = _make_file_entry(
            name="flashplayer.exe",
            storage_name="y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe",
            relative="deeply/nested/flashplayer.exe",
            md5="0EA30B0C7E392876DAAA2D55EF6AEA3E",
        )
        plan = plan_rollback(
            [entry],
            target_dir=tmp_path,
            source_dir=FIXTURES / "renamed",
            verify=False,
            flat=True,
        )
        result = execute_rollback(plan)
        assert result.restored == 1
        # Should be directly in tmp_path, not in subdirectory
        assert (tmp_path / "flashplayer.exe").exists()
        assert not (tmp_path / "deeply").exists()


# ===========================================================================
# TestVerifyFileHash
# ===========================================================================


class TestVerifyFileHash:
    """Hash verification helper."""

    def test_matching_hash(self) -> None:
        """Correct hash returns True."""
        path = FIXTURES / "non-renamed" / "readme.txt"
        expected = HashSet(
            md5="0654CDF77702945DA87A8B4E72E98EEE",
            sha256="0CB544DD1D4A81D757E5BDBFE8474C2303377608B091A672A57D38FEE2A27440",
        )
        assert verify_file_hash(path, expected, "md5") is True

    def test_non_matching_hash(self) -> None:
        """Wrong hash returns False."""
        path = FIXTURES / "non-renamed" / "readme.txt"
        expected = HashSet(
            md5="FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF",
            sha256="FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF",
        )
        assert verify_file_hash(path, expected, "md5") is False

    def test_missing_algorithm(self) -> None:
        """Missing algorithm in HashSet returns False."""
        path = FIXTURES / "non-renamed" / "readme.txt"
        expected = HashSet(md5="0654CDF77702945DA87A8B4E72E98EEE", sha256="X")
        # sha512 is None by default → requesting sha512 should return False
        assert verify_file_hash(path, expected, "sha512") is False


# ===========================================================================
# TestOriginDirAnnotation
# ===========================================================================

RECURSIVE_FIXTURES = FIXTURES / "recursive-testbed"


class TestOriginDirAnnotation:
    """Origin-dir annotations for recursive rollback."""

    def test_recursive_load_annotates_origin_dirs(self) -> None:
        """load_meta2(recursive=True) annotates each entry with its meta2 origin directory."""
        from shruggie_indexer.core.rollback import _get_origin_dir

        entries = load_meta2(RECURSIVE_FIXTURES, recursive=True)
        assert len(entries) >= 2

        # Every entry should have an origin dir annotation
        for entry in entries:
            origin = _get_origin_dir(entry)
            assert origin is not None, f"Entry {entry.id} has no origin dir annotation"

        # Entries from the root should have RECURSIVE_FIXTURES as origin
        root_entries = [e for e in entries if "/" not in (e.file_system.relative or "")]
        for entry in root_entries:
            assert _get_origin_dir(entry) == RECURSIVE_FIXTURES

        # Entries from subdir should have subdir as origin
        sub_entries = [e for e in entries if (e.file_system.relative or "").startswith("subdir/")]
        for entry in sub_entries:
            assert _get_origin_dir(entry) == RECURSIVE_FIXTURES / "subdir"

    def test_non_recursive_load_annotates_origin_dirs(self) -> None:
        """load_meta2(recursive=False) still annotates origin dirs."""
        from shruggie_indexer.core.rollback import _get_origin_dir

        entries = load_meta2(RECURSIVE_FIXTURES, recursive=False)
        # Should only find root-level entries
        for entry in entries:
            origin = _get_origin_dir(entry)
            assert origin is not None

    def test_single_file_annotates_origin_dir(self) -> None:
        """load_meta2 on a single file annotates origin dir."""
        from shruggie_indexer.core.rollback import _get_origin_dir

        meta2_files = sorted(RECURSIVE_FIXTURES.glob("*_meta2.json"))
        assert len(meta2_files) >= 1
        entries = load_meta2(meta2_files[0])
        for entry in entries:
            assert _get_origin_dir(entry) == RECURSIVE_FIXTURES


class TestLocalSourceResolverOriginFallback:
    """LocalSourceResolver strategy 3 — origin-dir fallback."""

    def test_origin_dir_fallback_finds_subdir_file(self, tmp_path: Path) -> None:
        """Resolver uses origin-dir fallback when file is not in search_dir."""
        from shruggie_indexer.core.rollback import _origin_dirs

        resolver = LocalSourceResolver(verify_hash=False)
        entry = _make_file_entry(
            name="subfile.txt",
            storage_name="yAA3FB09A0C23165E716723DB24CB945E.txt",
            md5="AA3FB09A0C23165E716723DB24CB945E",
        )

        # Without origin annotation, fails to find in root dir
        result = resolver.resolve(entry, RECURSIVE_FIXTURES)
        assert result is None

        # With origin annotation pointing to subdir, finds it
        _origin_dirs[id(entry)] = RECURSIVE_FIXTURES / "subdir"
        try:
            result = resolver.resolve(entry, RECURSIVE_FIXTURES)
            assert result is not None
            assert result.name == "yAA3FB09A0C23165E716723DB24CB945E.txt"
        finally:
            _origin_dirs.pop(id(entry), None)

    def test_recursive_rollback_resolves_subdir_files(self, tmp_path: Path) -> None:
        """Full recursive rollback pipeline finds content files in subdirectories."""
        entries = load_meta2(RECURSIVE_FIXTURES, recursive=True)
        target = tmp_path / "restored"

        plan = plan_rollback(
            entries,
            target_dir=target,
            source_dir=RECURSIVE_FIXTURES,
            verify=False,
        )

        # All entries should be resolvable (none skipped as unresolvable)
        unresolvable = [a for a in plan.actions if a.skip_reason == "Source file not found"]
        assert len(unresolvable) == 0, (
            f"Expected 0 unresolvable entries, got {len(unresolvable)}: "
            f"{[a.entry.name.text for a in unresolvable]}"
        )

        # Execute and verify
        result = execute_rollback(plan)
        assert result.restored == len(entries)
        assert result.failed == 0


# ===========================================================================
# TestPlanRollbackLogging
# ===========================================================================


class TestPlanRollbackLogging:
    """Verify that plan_rollback emits parameter summary at INFO level."""

    def test_parameter_summary_logged(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """plan_rollback logs all resolved parameters at INFO level."""
        import logging

        entry = _make_file_entry()

        with caplog.at_level(logging.INFO, logger="shruggie_indexer.core.rollback"):
            plan_rollback(
                [entry],
                target_dir=tmp_path,
                source_dir=tmp_path,
                verify=True,
                force=False,
                flat=True,
                skip_duplicates=True,
                restore_sidecars=False,
            )

        param_records = [r for r in caplog.records if "Rollback plan:" in r.message]
        assert len(param_records) == 1
        msg = param_records[0].message
        assert "entries=1" in msg
        assert str(tmp_path) in msg
        assert "verify=True" in msg
        assert "flat=True" in msg
        assert "skip_duplicates=True" in msg
        assert "restore_sidecars=False" in msg


# ===========================================================================
# TestSetWindowsCreationTime
# ===========================================================================


class TestSetWindowsCreationTime:
    """ctypes-based ctime restoration."""

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_sets_creation_time_on_windows(self, tmp_path: Path) -> None:
        """Verify _set_windows_creation_time sets ctime on Windows."""
        from shruggie_indexer.core.rollback import _set_windows_creation_time

        test_file = tmp_path / "ctime_test.txt"
        test_file.write_text("ctime test content")

        # Set creation time to 2020-01-01 00:00:00 UTC
        target_ctime = 1577836800.0
        ok = _set_windows_creation_time(test_file, target_ctime)
        assert ok is True

        # Verify via os.stat
        import stat as stat_mod

        st = os.stat(test_file)
        # On Windows, st_ctime is the creation time
        # Allow 2-second tolerance for filesystem rounding
        assert abs(st.st_ctime - target_ctime) < 2.0

    @pytest.mark.skipif(os.name == "nt", reason="Non-Windows only")
    def test_noop_on_non_windows(self, tmp_path: Path) -> None:
        """On non-Windows, _set_windows_creation_time is a no-op."""
        from shruggie_indexer.core.rollback import _set_windows_creation_time

        test_file = tmp_path / "ctime_test.txt"
        test_file.write_text("ctime test content")
        ok = _set_windows_creation_time(test_file, 1577836800.0)
        assert ok is False


# ===========================================================================
# TestContentHashCollisionDetection
# ===========================================================================


class TestContentHashCollisionDetection:
    """Session-ID-based deduplication of content-hash collisions."""

    def test_no_collision_preserves_all(self) -> None:
        """Entries with different hashes are all preserved."""
        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        e1 = _make_file_entry(name="a.txt", relative="a.txt", md5="AAAA0000AAAA0000AAAA0000AAAA0000")
        e2 = _make_file_entry(name="b.txt", relative="b.txt", md5="BBBB0000BBBB0000BBBB0000BBBB0000")
        result = _deduplicate_by_content_hash([e1, e2])
        assert len(result) == 2

    def test_same_hash_same_relative_no_dedup(self) -> None:
        """Same hash, same relative → no dedup needed."""
        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        e1 = _make_file_entry(
            name="a.txt", relative="dir/a.txt", md5="AAAA0000AAAA0000AAAA0000AAAA0000",
            session_id="session-1",
        )
        e2 = _make_file_entry(
            name="a.txt", relative="dir/a.txt", md5="AAAA0000AAAA0000AAAA0000AAAA0000",
            session_id="session-2",
        )
        result = _deduplicate_by_content_hash([e1, e2])
        assert len(result) == 2

    def test_collision_majority_session_wins(self) -> None:
        """Two entries, same hash, different sessions → majority session kept."""
        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        majority_sid = "aaaa1111-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
        minority_sid = "bbbb2222-bbbb-4bbb-bbbb-bbbbbbbbbbbb"

        # 3 entries with majority session, 1 with minority
        e_majority_1 = _make_file_entry(
            name="file1.txt", relative="file1.txt",
            md5="1111000011110000111100001111AAAA", session_id=majority_sid,
        )
        e_majority_2 = _make_file_entry(
            name="file2.txt", relative="file2.txt",
            md5="2222000022220000222200002222AAAA", session_id=majority_sid,
        )
        e_majority_3 = _make_file_entry(
            name="file3.txt", relative="file3.txt",
            md5="3333000033330000333300003333AAAA", session_id=majority_sid,
        )
        # Colliding entry from minority session — same hash as e_majority_1
        # but different relative
        e_minority = _make_file_entry(
            name="file1.txt", relative="old/file1.txt",
            md5="1111000011110000111100001111AAAA", session_id=minority_sid,
        )

        result = _deduplicate_by_content_hash(
            [e_majority_1, e_majority_2, e_majority_3, e_minority],
        )
        assert len(result) == 3
        assert e_majority_1 in result
        assert e_minority not in result

    def test_collision_session_over_no_session(self) -> None:
        """Entry with session_id preferred over entry without."""
        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        e_with = _make_file_entry(
            name="file.7z", relative="file.7z",
            md5="AAAA0000AAAA0000AAAA0000AAAA0000",
            session_id="session-1",
        )
        e_without = _make_file_entry(
            name="file.7z", relative="data/file.7z",
            md5="AAAA0000AAAA0000AAAA0000AAAA0000",
        )
        result = _deduplicate_by_content_hash([e_without, e_with])
        assert len(result) == 1
        assert e_with in result

    def test_collision_no_sessions_keeps_first(self) -> None:
        """Neither entry has session_id → first encountered kept."""
        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        e1 = _make_file_entry(
            name="file.7z", relative="file.7z",
            md5="AAAA0000AAAA0000AAAA0000AAAA0000",
        )
        e2 = _make_file_entry(
            name="file.7z", relative="data/file.7z",
            md5="AAAA0000AAAA0000AAAA0000AAAA0000",
        )
        result = _deduplicate_by_content_hash([e1, e2])
        assert len(result) == 1
        assert e1 in result

    def test_collision_same_session_different_relative(self) -> None:
        """Same session_id, different relative → first encountered kept."""
        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        sid = "aaaa1111-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
        e1 = _make_file_entry(
            name="file.7z", relative="file.7z",
            md5="AAAA0000AAAA0000AAAA0000AAAA0000",
            session_id=sid,
        )
        e2 = _make_file_entry(
            name="file.7z", relative="data/file.7z",
            md5="AAAA0000AAAA0000AAAA0000AAAA0000",
            session_id=sid,
        )
        result = _deduplicate_by_content_hash([e1, e2])
        assert len(result) == 1
        assert e1 in result

    def test_collision_warning_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Collision detection logs WARNING with hash and paths."""
        import logging

        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        e1 = _make_file_entry(
            name="file.7z", relative="file.7z",
            md5="AAAA0000AAAA0000AAAA0000AAAA0000",
            session_id="session-1",
        )
        e2 = _make_file_entry(
            name="file.7z", relative="data/file.7z",
            md5="AAAA0000AAAA0000AAAA0000AAAA0000",
        )
        with caplog.at_level(logging.WARNING, logger="shruggie_indexer.core.rollback"):
            _deduplicate_by_content_hash([e1, e2])

        warning_records = [
            r for r in caplog.records
            if "Duplicate content hash" in r.message
        ]
        assert len(warning_records) == 1
        assert "Keeping" in warning_records[0].message
        assert "Discarding" in warning_records[0].message

    def test_empty_entries(self) -> None:
        """Empty entries list returns empty."""
        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        result = _deduplicate_by_content_hash([])
        assert result == []

    def test_entries_without_hashes_pass_through(self) -> None:
        """Entries with hashes=None are never discarded."""
        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        e1 = _make_file_entry(name="a.txt", relative="a.txt", md5="AAAA0000AAAA0000AAAA0000AAAA0000")
        e1_no_hash = IndexEntry(
            schema_version=2,
            id="xDIR",
            id_algorithm="md5",
            type="directory",
            name=NameObject(text="dir", hashes=_make_hashset()),
            extension=None,
            size=SizeObject(text="0 B", bytes=0),
            hashes=None,
            file_system=FileSystemObject(relative=".", parent=None),
            timestamps=_make_ts(),
            attributes=AttributesObject(is_link=False, storage_name="dir"),
        )
        result = _deduplicate_by_content_hash([e1, e1_no_hash])
        assert len(result) == 2

    def test_collision_in_plan_rollback(self, tmp_path: Path) -> None:
        """plan_rollback integrates collision detection end-to-end."""
        majority_sid = "aaaa1111-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
        minority_sid = "bbbb2222-bbbb-4bbb-bbbb-bbbbbbbbbbbb"

        # Create source file
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "yAAAA0000AAAA0000AAAA0000AAAA0000.7z").write_bytes(b"archive")

        # Majority-session entry
        e_keep = _make_file_entry(
            name="FeedsExport.7z", relative="FeedsExport.7z",
            storage_name="yAAAA0000AAAA0000AAAA0000AAAA0000.7z",
            md5="AAAA0000AAAA0000AAAA0000AAAA0000",
            session_id=majority_sid,
        )
        # Another majority entry (establishes majority)
        e_other = _make_file_entry(
            name="other.txt", relative="other.txt",
            storage_name="yBBBB0000BBBB0000BBBB0000BBBB0000.txt",
            md5="BBBB0000BBBB0000BBBB0000BBBB0000",
            session_id=majority_sid,
        )
        (source_dir / "yBBBB0000BBBB0000BBBB0000BBBB0000.txt").write_bytes(b"other")

        # Minority-session entry — same hash, different relative
        e_stale = _make_file_entry(
            name="FeedsExport.7z", relative="data/FeedsExport.7z",
            storage_name="yAAAA0000AAAA0000AAAA0000AAAA0000.7z",
            md5="AAAA0000AAAA0000AAAA0000AAAA0000",
            session_id=minority_sid,
        )

        target_dir = tmp_path / "restored"
        plan = plan_rollback(
            [e_keep, e_other, e_stale],
            target_dir=target_dir,
            source_dir=source_dir,
            verify=False,
        )

        # The stale entry should be gone — no restore action for data/FeedsExport.7z
        target_paths = {
            a.target_path for a in plan.actions
            if a.action_type == "restore" and not a.skip_reason
        }
        assert target_dir / "FeedsExport.7z" in target_paths
        assert target_dir / "data" / "FeedsExport.7z" not in target_paths

    def test_same_hash_different_storage_name_no_collision(self) -> None:
        """Same content hash but different storage names → distinct files, no collision.

        This is the slippers.gif/slippers.png scenario: byte-identical files
        with different extensions receive different storage names during MMD
        and must both survive rollback.
        """
        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        sid = "aaaa1111-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
        shared_md5 = "B4ADC74442D00EE0953105C01D42B72B"

        e_gif = _make_file_entry(
            name="slippers.gif", relative="images/slippers.gif",
            storage_name=f"y{shared_md5}.gif",
            md5=shared_md5, session_id=sid,
        )
        e_png = _make_file_entry(
            name="slippers.png", relative="images/slippers.png",
            storage_name=f"y{shared_md5}.png",
            md5=shared_md5, session_id=sid,
        )

        result = _deduplicate_by_content_hash([e_gif, e_png])
        assert len(result) == 2
        assert e_gif in result
        assert e_png in result

    def test_same_hash_different_storage_name_no_warning(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Same hash, different storage names → no WARNING emitted."""
        import logging

        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        sid = "aaaa1111-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
        shared_md5 = "B4ADC74442D00EE0953105C01D42B72B"

        e_gif = _make_file_entry(
            name="slippers.gif", relative="images/slippers.gif",
            storage_name=f"y{shared_md5}.gif",
            md5=shared_md5, session_id=sid,
        )
        e_png = _make_file_entry(
            name="slippers.png", relative="images/slippers.png",
            storage_name=f"y{shared_md5}.png",
            md5=shared_md5, session_id=sid,
        )

        with caplog.at_level(logging.WARNING, logger="shruggie_indexer.core.rollback"):
            _deduplicate_by_content_hash([e_gif, e_png])

        collision_warnings = [
            r for r in caplog.records
            if "Duplicate content hash" in r.message
        ]
        assert len(collision_warnings) == 0

    def test_same_hash_different_storage_name_plan_rollback(
        self, tmp_path: Path,
    ) -> None:
        """plan_rollback preserves both files when hash matches but storage names differ."""
        sid = "aaaa1111-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
        shared_md5 = "B4ADC74442D00EE0953105C01D42B72B"

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / f"y{shared_md5}.gif").write_bytes(b"image-data")
        (source_dir / f"y{shared_md5}.png").write_bytes(b"image-data")

        e_gif = _make_file_entry(
            name="slippers.gif", relative="images/slippers.gif",
            storage_name=f"y{shared_md5}.gif",
            md5=shared_md5, session_id=sid,
        )
        e_png = _make_file_entry(
            name="slippers.png", relative="images/slippers.png",
            storage_name=f"y{shared_md5}.png",
            md5=shared_md5, session_id=sid,
        )

        target_dir = tmp_path / "restored"
        plan = plan_rollback(
            [e_gif, e_png],
            target_dir=target_dir,
            source_dir=source_dir,
            verify=False,
        )

        restore_targets = {
            a.target_path for a in plan.actions
            if a.action_type == "restore" and not a.skip_reason
        }
        assert target_dir / "images" / "slippers.gif" in restore_targets
        assert target_dir / "images" / "slippers.png" in restore_targets

    def test_collision_warning_cross_session(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Cross-session collision → message says 'found in multiple sessions'."""
        import logging

        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        shared_md5 = "AAAA0000AAAA0000AAAA0000AAAA0000"
        shared_storage = f"y{shared_md5}.7z"

        e1 = _make_file_entry(
            name="file.7z", relative="file.7z",
            storage_name=shared_storage,
            md5=shared_md5, session_id="session-1",
        )
        e2 = _make_file_entry(
            name="file.7z", relative="old/file.7z",
            storage_name=shared_storage,
            md5=shared_md5, session_id="session-2",
        )

        with caplog.at_level(logging.WARNING, logger="shruggie_indexer.core.rollback"):
            _deduplicate_by_content_hash([e1, e2])

        warning_records = [
            r for r in caplog.records
            if "Duplicate content hash" in r.message
        ]
        assert len(warning_records) == 1
        assert "found in multiple sessions" in warning_records[0].message

    def test_collision_warning_intra_session(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Intra-session collision → message says 'with conflicting paths in session'."""
        import logging

        from shruggie_indexer.core.rollback import _deduplicate_by_content_hash

        sid = "aaaa1111-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
        shared_md5 = "AAAA0000AAAA0000AAAA0000AAAA0000"
        shared_storage = f"y{shared_md5}.7z"

        e1 = _make_file_entry(
            name="file.7z", relative="file.7z",
            storage_name=shared_storage,
            md5=shared_md5, session_id=sid,
        )
        e2 = _make_file_entry(
            name="file.7z", relative="old/file.7z",
            storage_name=shared_storage,
            md5=shared_md5, session_id=sid,
        )

        with caplog.at_level(logging.WARNING, logger="shruggie_indexer.core.rollback"):
            _deduplicate_by_content_hash([e1, e2])

        warning_records = [
            r for r in caplog.records
            if "Duplicate content hash" in r.message
        ]
        assert len(warning_records) == 1
        assert "with conflicting paths in session" in warning_records[0].message
        assert sid in warning_records[0].message


# ===========================================================================
# TestLegacyPrefixDetection
# ===========================================================================


class TestLegacyPrefixDetection:
    """Legacy file_system.relative prefix stripping."""

    def test_legacy_prefix_stripped(self) -> None:
        """Entries with common first component have prefix stripped."""
        from shruggie_indexer.core.rollback import _strip_legacy_prefix

        e1 = _make_file_entry(name="slippers.gif", relative="data/images/slippers.gif")
        e2 = _make_file_entry(name="123.nfo", relative="data/123.nfo")
        e3 = _make_file_entry(name="readme.txt", relative="data/docs/readme.txt")

        _strip_legacy_prefix([e1, e2, e3], source_dir=Path("data"))

        assert e1.file_system.relative == "images/slippers.gif"
        assert e2.file_system.relative == "123.nfo"
        assert e3.file_system.relative == "docs/readme.txt"

    def test_current_format_unchanged(self) -> None:
        """Entries without legacy prefix pass through unchanged."""
        from shruggie_indexer.core.rollback import _strip_legacy_prefix

        e1 = _make_file_entry(name="slippers.gif", relative="images/slippers.gif")
        e2 = _make_file_entry(name="123.nfo", relative="123.nfo")

        _strip_legacy_prefix([e1, e2], source_dir=Path("somedir"))

        # e2 is a single-component relative → no stripping
        assert e1.file_system.relative == "images/slippers.gif"
        assert e2.file_system.relative == "123.nfo"

    def test_dot_relative_no_stripping(self) -> None:
        """Entry with relative='.' prevents stripping."""
        from shruggie_indexer.core.rollback import _strip_legacy_prefix

        e1 = _make_file_entry(name="a.txt", relative=".")
        e2 = _make_file_entry(name="b.txt", relative="sub/b.txt")

        _strip_legacy_prefix([e1, e2])

        assert e1.file_system.relative == "."
        assert e2.file_system.relative == "sub/b.txt"

    def test_source_dir_mismatch_no_stripping(self) -> None:
        """When prefix doesn't match source_dir name, no stripping."""
        from shruggie_indexer.core.rollback import _strip_legacy_prefix

        e1 = _make_file_entry(name="a.txt", relative="images/a.txt")
        e2 = _make_file_entry(name="b.txt", relative="images/b.txt")

        _strip_legacy_prefix([e1, e2], source_dir=Path("other_dir"))

        assert e1.file_system.relative == "images/a.txt"
        assert e2.file_system.relative == "images/b.txt"

    def test_mixed_first_components_no_stripping(self) -> None:
        """Different first components → no stripping."""
        from shruggie_indexer.core.rollback import _strip_legacy_prefix

        e1 = _make_file_entry(name="a.txt", relative="dir1/a.txt")
        e2 = _make_file_entry(name="b.txt", relative="dir2/b.txt")

        _strip_legacy_prefix([e1, e2])

        assert e1.file_system.relative == "dir1/a.txt"
        assert e2.file_system.relative == "dir2/b.txt"

    def test_single_component_no_stripping(self) -> None:
        """Single-component relative (filename only) → no stripping."""
        from shruggie_indexer.core.rollback import _strip_legacy_prefix

        e1 = _make_file_entry(name="file.txt", relative="file.txt")
        e2 = _make_file_entry(name="other.txt", relative="other.txt")

        _strip_legacy_prefix([e1, e2])

        assert e1.file_system.relative == "file.txt"
        assert e2.file_system.relative == "other.txt"

    def test_prefix_detection_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Legacy prefix detection logs INFO message."""
        import logging

        from shruggie_indexer.core.rollback import _strip_legacy_prefix

        e1 = _make_file_entry(name="a.txt", relative="mydata/a.txt")
        e2 = _make_file_entry(name="b.txt", relative="mydata/sub/b.txt")

        with caplog.at_level(logging.INFO, logger="shruggie_indexer.core.rollback"):
            _strip_legacy_prefix([e1, e2], source_dir=Path("mydata"))

        info_records = [
            r for r in caplog.records
            if "legacy relative path prefix" in r.message.lower()
        ]
        assert len(info_records) == 1
        assert "'mydata'" in info_records[0].message

    def test_empty_entries_no_error(self) -> None:
        """Empty entries list → no error."""
        from shruggie_indexer.core.rollback import _strip_legacy_prefix

        _strip_legacy_prefix([])  # Should not raise

    def test_legacy_prefix_in_plan_rollback(self, tmp_path: Path) -> None:
        """plan_rollback integrates legacy prefix stripping end-to-end."""
        source_dir = tmp_path / "data"
        source_dir.mkdir()
        (source_dir / "yAAAA0000AAAA0000AAAA0000AAAA0000.gif").write_bytes(b"gif")
        (source_dir / "yBBBB0000BBBB0000BBBB0000BBBB0000.nfo").write_bytes(b"nfo")

        e1 = _make_file_entry(
            name="slippers.gif", relative="data/images/slippers.gif",
            storage_name="yAAAA0000AAAA0000AAAA0000AAAA0000.gif",
            md5="AAAA0000AAAA0000AAAA0000AAAA0000",
        )
        e2 = _make_file_entry(
            name="123.nfo", relative="data/123.nfo",
            storage_name="yBBBB0000BBBB0000BBBB0000BBBB0000.nfo",
            md5="BBBB0000BBBB0000BBBB0000BBBB0000",
        )

        target_dir = tmp_path / "restored"
        plan = plan_rollback(
            [e1, e2],
            target_dir=target_dir,
            source_dir=source_dir,
            verify=False,
        )

        target_paths = {
            a.target_path for a in plan.actions
            if a.action_type == "restore" and not a.skip_reason
        }
        # Should be under target_dir directly, NOT target_dir/data/
        assert target_dir / "images" / "slippers.gif" in target_paths
        assert target_dir / "123.nfo" in target_paths
        assert target_dir / "data" / "images" / "slippers.gif" not in target_paths

    def test_root_entry_relative_becomes_dot(self) -> None:
        """If an entry's relative equals the legacy prefix, it becomes '.'."""
        from shruggie_indexer.core.rollback import _strip_legacy_prefix

        e_root = _make_file_entry(name="root.txt", relative="data/root.txt")
        e_sub = _make_file_entry(name="sub.txt", relative="data/sub/sub.txt")

        _strip_legacy_prefix([e_root, e_sub], source_dir=Path("data"))

        assert e_root.file_system.relative == "root.txt"
        assert e_sub.file_system.relative == "sub/sub.txt"


# ---------------------------------------------------------------------------
# Encoding-Aware Restoration Tests (§7.2.F)
# ---------------------------------------------------------------------------


class TestBomRestoration:
    """Tests for BOM restoration during sidecar rollback."""

    def test_utf8_bom_prepended(self) -> None:
        """Text sidecar with encoding.bom='utf-8' produces EF BB BF prefix."""
        from shruggie_indexer.core.rollback import _apply_text_encoding
        from shruggie_indexer.models.schema import EncodingObject

        enc = EncodingObject(bom="utf-8", line_endings="lf")
        result = _apply_text_encoding("hello\nworld", enc)
        assert isinstance(result, bytes)
        assert result.startswith(b"\xef\xbb\xbf")
        assert result == b"\xef\xbb\xbfhello\nworld"

    def test_utf16_le_bom_prepended(self) -> None:
        """Text sidecar with encoding.bom='utf-16-le' produces FF FE prefix."""
        from shruggie_indexer.core.rollback import _apply_text_encoding
        from shruggie_indexer.models.schema import EncodingObject

        enc = EncodingObject(bom="utf-16-le", detected_encoding="utf-16-le")
        result = _apply_text_encoding("hi", enc)
        assert result.startswith(b"\xff\xfe")

    def test_no_bom_when_none(self) -> None:
        """Text sidecar without BOM produces no BOM prefix."""
        from shruggie_indexer.core.rollback import _apply_text_encoding
        from shruggie_indexer.models.schema import EncodingObject

        enc = EncodingObject(line_endings="lf")
        result = _apply_text_encoding("hello", enc)
        assert not result.startswith(b"\xef\xbb\xbf")
        assert result == b"hello"


class TestCrlfRestoration:
    """Tests for CRLF line-ending restoration during sidecar rollback."""

    def test_crlf_restored(self) -> None:
        """Text sidecar with encoding.line_endings='crlf' produces \\r\\n."""
        from shruggie_indexer.core.rollback import _apply_text_encoding
        from shruggie_indexer.models.schema import EncodingObject

        enc = EncodingObject(line_endings="crlf")
        result = _apply_text_encoding("line1\nline2\nline3", enc)
        assert result == b"line1\r\nline2\r\nline3"

    def test_lf_preserved(self) -> None:
        """Text sidecar with encoding.line_endings='lf' preserves LF."""
        from shruggie_indexer.core.rollback import _apply_text_encoding
        from shruggie_indexer.models.schema import EncodingObject

        enc = EncodingObject(line_endings="lf")
        result = _apply_text_encoding("line1\nline2", enc)
        assert result == b"line1\nline2"

    def test_no_encoding_preserves_lf(self) -> None:
        """Null encoding (v2-era) preserves LF line endings."""
        from shruggie_indexer.core.rollback import _apply_text_encoding

        result = _apply_text_encoding("line1\nline2", None)
        assert result == b"line1\nline2"


class TestEncodingRestoration:
    """Tests for source encoding restoration during sidecar rollback."""

    def test_windows_1252_encoding(self) -> None:
        """Text sidecar with detected_encoding='windows-1252' encodes correctly."""
        from shruggie_indexer.core.rollback import _apply_text_encoding
        from shruggie_indexer.models.schema import EncodingObject

        enc = EncodingObject(detected_encoding="windows-1252")
        # The euro sign (€) is 0x80 in Windows-1252 but multi-byte in UTF-8
        result = _apply_text_encoding("\u20ac", enc)
        assert result == b"\x80"

    def test_utf8_default_when_no_encoding(self) -> None:
        """Null encoding falls back to UTF-8."""
        from shruggie_indexer.core.rollback import _apply_text_encoding

        result = _apply_text_encoding("café", None)
        assert result == "café".encode("utf-8")

    def test_fallback_to_utf8_on_bad_encoding(self) -> None:
        """Unrecognized encoding name falls back to UTF-8."""
        from shruggie_indexer.core.rollback import _apply_text_encoding
        from shruggie_indexer.models.schema import EncodingObject

        enc = EncodingObject(detected_encoding="nonexistent-codec-xyz")
        result = _apply_text_encoding("hello", enc)
        assert result == b"hello"


class TestJsonIndentRestoration:
    """Tests for JSON indent-aware restoration during sidecar rollback."""

    def test_four_space_indent(self) -> None:
        """JSON sidecar with json_indent='    ' (4 spaces) uses 4-space indent."""
        from shruggie_indexer.core.rollback import _restore_json
        from shruggie_indexer.models.schema import MetadataAttributes

        attrs = MetadataAttributes(
            type="json_metadata", format="json", transforms=[],
            json_style="pretty", json_indent="    ",
        )
        result = _restore_json({"key": "value"}, attrs)
        assert '    "key"' in result

    def test_tab_indent(self) -> None:
        """JSON sidecar with json_indent='\\t' uses tab indent."""
        from shruggie_indexer.core.rollback import _restore_json
        from shruggie_indexer.models.schema import MetadataAttributes

        attrs = MetadataAttributes(
            type="json_metadata", format="json", transforms=[],
            json_style="pretty", json_indent="\t",
        )
        result = _restore_json({"key": "value"}, attrs)
        assert '\t"key"' in result

    def test_two_space_indent_default(self) -> None:
        """JSON sidecar with json_style='pretty' but no json_indent uses 2-space."""
        from shruggie_indexer.core.rollback import _restore_json
        from shruggie_indexer.models.schema import MetadataAttributes

        attrs = MetadataAttributes(
            type="json_metadata", format="json", transforms=[],
            json_style="pretty",
        )
        result = _restore_json({"key": "value"}, attrs)
        assert '  "key"' in result
        assert '    "key"' not in result

    def test_compact_json(self) -> None:
        """JSON sidecar with json_style=None uses compact formatting."""
        from shruggie_indexer.core.rollback import _restore_json
        from shruggie_indexer.models.schema import MetadataAttributes

        attrs = MetadataAttributes(
            type="json_metadata", format="json", transforms=[],
        )
        result = _restore_json({"key": "value"}, attrs)
        assert result == '{"key":"value"}'


class TestLegacyV2SidecarRestoration:
    """Tests for backward compatibility with v2-era sidecar entries."""

    def test_v2_text_sidecar_unchanged(self) -> None:
        """v2-era text sidecar (no encoding) restores as UTF-8 with LF."""
        from shruggie_indexer.core.rollback import _decode_sidecar_data

        meta = MetadataEntry(
            id="yABCDEF0123456789ABCDEF0123456789",
            origin="sidecar",
            name=NameObject(text="video.description", hashes=_make_hashset()),
            hashes=_make_hashset(),
            attributes=MetadataAttributes(
                type="description", format="text", transforms=[],
            ),
            data="hello\nworld",
        )
        data, is_binary = _decode_sidecar_data(meta)
        assert isinstance(data, bytes)
        assert data == b"hello\nworld"

    def test_v2_json_sidecar_pretty_default(self) -> None:
        """v2-era JSON sidecar with json_style='pretty' uses 2-space indent."""
        from shruggie_indexer.core.rollback import _decode_sidecar_data

        meta = MetadataEntry(
            id="yABCDEF0123456789ABCDEF0123456789",
            origin="sidecar",
            name=NameObject(text="video.info.json", hashes=_make_hashset()),
            hashes=_make_hashset(),
            attributes=MetadataAttributes(
                type="json_metadata", format="json", transforms=[],
                json_style="pretty",
            ),
            data={"title": "Test"},
        )
        data, is_binary = _decode_sidecar_data(meta)
        assert isinstance(data, bytes)
        text = data.decode("utf-8")
        assert '  "title"' in text


class TestFullRoundTrip:
    """End-to-end round-trip test: encode → restore → compare bytes."""

    def test_bom_crlf_roundtrip(self) -> None:
        """Ingest a text sidecar with BOM + CRLF, restore, compare bytes."""
        from shruggie_indexer.core.rollback import _decode_sidecar_data

        original_bytes = b"\xef\xbb\xbfline1\r\nline2\r\n"

        # Simulate what the sidecar pipeline would produce:
        # - BOM detected, line_endings=crlf, text decoded as UTF-8
        from shruggie_indexer.models.schema import EncodingObject

        enc = EncodingObject(
            bom="utf-8",
            line_endings="crlf",
            detected_encoding="utf-8",
            confidence=0.99,
        )

        # The sidecar pipeline would have stripped the BOM and
        # normalized CRLF to LF during Python text-mode decode.
        text_content = "line1\nline2\n"

        meta = MetadataEntry(
            id="yABCDEF0123456789ABCDEF0123456789",
            origin="sidecar",
            name=NameObject(text="test.description", hashes=_make_hashset()),
            hashes=_make_hashset(),
            attributes=MetadataAttributes(
                type="description", format="text", transforms=[],
            ),
            data=text_content,
            encoding=enc,
        )

        restored_data, is_binary = _decode_sidecar_data(meta)
        assert isinstance(restored_data, bytes)
        assert restored_data == original_bytes

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

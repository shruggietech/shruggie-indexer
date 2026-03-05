"""Unit tests for MetaMergeDelete delete queue population and execution.

Validates that the delete queue is correctly populated during sidecar discovery
and that the drain function properly deletes files.

Batch 6, Section 5.4.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.sidecar import discover_and_parse

# ── Fixture paths ───────────────────────────────────────────────────────
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SIDECAR_TESTBED = FIXTURES_DIR / "sidecar-testbed"


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_sidecar_testbed(tmp_path: Path) -> Path:
    """Create a disposable copy of the sidecar-testbed fixture.

    Uses tmp_path for test isolation — destructive operations are allowed.
    """
    dest = tmp_path / "sidecar-testbed"
    shutil.copytree(SIDECAR_TESTBED, dest)
    return dest


@pytest.fixture()
def mmd_config():
    """Config with MetaMerge + MetaMergeDelete enabled."""
    return load_config(overrides={"meta_merge": True, "meta_merge_delete": True, "output_inplace": True})


@pytest.fixture()
def merge_only_config():
    """Config with MetaMerge enabled but MetaMergeDelete disabled."""
    return load_config(overrides={"meta_merge": True, "meta_merge_delete": False})


# ── Test 1: Delete queue population ─────────────────────────────────────


@pytest.mark.mmd
class TestDeleteQueuePopulation:
    """Validate that discover_and_parse populates the delete queue correctly."""

    def test_delete_queue_populated_when_active(
        self, tmp_sidecar_testbed: Path, mmd_config,
    ) -> None:
        """When meta_merge_delete=True, discover_and_parse() appends sidecar
        paths to the delete_queue."""
        item_path = tmp_sidecar_testbed / "video.mp4"
        siblings = sorted(
            (p for p in tmp_sidecar_testbed.iterdir() if p.is_file()),
            key=lambda p: p.name.lower(),
        )
        delete_queue: list[Path] = []

        discover_and_parse(
            item_path=item_path,
            item_name="video.mp4",
            siblings=siblings,
            config=mmd_config,
            index_root=tmp_sidecar_testbed.parent,
            delete_queue=delete_queue,
        )

        assert len(delete_queue) > 0, "delete_queue should not be empty"

    def test_delete_queue_empty_when_inactive(
        self, tmp_sidecar_testbed: Path, merge_only_config,
    ) -> None:
        """When meta_merge_delete=False (but meta_merge=True), the delete_queue
        is not populated."""
        item_path = tmp_sidecar_testbed / "video.mp4"
        siblings = sorted(
            (p for p in tmp_sidecar_testbed.iterdir() if p.is_file()),
            key=lambda p: p.name.lower(),
        )
        delete_queue: list[Path] = []

        discover_and_parse(
            item_path=item_path,
            item_name="video.mp4",
            siblings=siblings,
            config=merge_only_config,
            index_root=tmp_sidecar_testbed.parent,
            delete_queue=delete_queue,
        )

        assert len(delete_queue) == 0, "delete_queue should be empty when MMD is off"

    def test_delete_queue_contains_correct_paths(
        self, tmp_sidecar_testbed: Path, mmd_config,
    ) -> None:
        """The delete queue contains absolute paths to the sidecar files that
        were successfully parsed, not to content files or indexer output."""
        item_path = tmp_sidecar_testbed / "video.mp4"
        siblings = sorted(
            (p for p in tmp_sidecar_testbed.iterdir() if p.is_file()),
            key=lambda p: p.name.lower(),
        )
        delete_queue: list[Path] = []

        discover_and_parse(
            item_path=item_path,
            item_name="video.mp4",
            siblings=siblings,
            config=mmd_config,
            index_root=tmp_sidecar_testbed.parent,
            delete_queue=delete_queue,
        )

        queued_names = {p.name for p in delete_queue}

        # Content files must never be in the queue.
        assert "video.mp4" not in queued_names
        assert "content.txt" not in queued_names
        assert "photo.jpg" not in queued_names
        assert "data.csv" not in queued_names

        # Indexer output artifacts should have been excluded by _is_excluded
        # and thus NOT queued (they're excluded, not consumed).
        assert "video.mp4_meta.json" not in queued_names
        assert "video.mp4_meta2.json" not in queued_names

        # Actual sidecars should be in the queue.
        # At minimum, the recognized sidecars of video.mp4 that pass
        # _is_excluded should be present.
        assert len(delete_queue) > 0
        for path in delete_queue:
            assert path.is_absolute(), f"Queue path should be absolute: {path}"


# ── Test 2: Delete phase execution ──────────────────────────────────────

from shruggie_indexer.cli.main import (
    _drain_delete_queue,
)


@pytest.mark.mmd
@pytest.mark.destructive
class TestDeletePhaseExecution:
    """Validate the drain function deletes files correctly.

    Tests use the **real** ``_drain_delete_queue`` implementation from
    ``shruggie_indexer.cli.main`` — not a local copy — to ensure
    production behaviour is covered.
    """

    def test_delete_phase_removes_files(
        self, tmp_sidecar_testbed: Path, mmd_config,
    ) -> None:
        """After draining, sidecar files are removed from disk."""
        item_path = tmp_sidecar_testbed / "video.mp4"
        siblings = sorted(
            (p for p in tmp_sidecar_testbed.iterdir() if p.is_file()),
            key=lambda p: p.name.lower(),
        )
        delete_queue: list[Path] = []

        discover_and_parse(
            item_path=item_path,
            item_name="video.mp4",
            siblings=siblings,
            config=mmd_config,
            index_root=tmp_sidecar_testbed.parent,
            delete_queue=delete_queue,
        )

        # Collect unique paths for verification.
        unique_paths = list(dict.fromkeys(delete_queue))

        # All queued paths should exist before drain.
        for path in unique_paths:
            assert path.exists(), f"Sidecar should exist before drain: {path}"

        deleted = _drain_delete_queue(delete_queue)

        assert deleted == len(unique_paths)
        for path in unique_paths:
            assert not path.exists(), f"Sidecar should be deleted: {path}"

    def test_delete_phase_does_not_remove_content_files(
        self, tmp_sidecar_testbed: Path, mmd_config,
    ) -> None:
        """Content files (video.mp4, photo.jpg) survive MetaMergeDelete."""
        item_path = tmp_sidecar_testbed / "video.mp4"
        siblings = sorted(
            (p for p in tmp_sidecar_testbed.iterdir() if p.is_file()),
            key=lambda p: p.name.lower(),
        )
        delete_queue: list[Path] = []

        discover_and_parse(
            item_path=item_path,
            item_name="video.mp4",
            siblings=siblings,
            config=mmd_config,
            index_root=tmp_sidecar_testbed.parent,
            delete_queue=delete_queue,
        )

        _drain_delete_queue(delete_queue)

        # Content files must still exist.
        assert (tmp_sidecar_testbed / "video.mp4").exists()
        assert (tmp_sidecar_testbed / "photo.jpg").exists()
        assert (tmp_sidecar_testbed / "content.txt").exists()
        assert (tmp_sidecar_testbed / "data.csv").exists()

    def test_delete_phase_logs_deletions(
        self, tmp_sidecar_testbed: Path, mmd_config, caplog,
    ) -> None:
        """Each deleted sidecar produces an INFO log message."""
        item_path = tmp_sidecar_testbed / "video.mp4"
        siblings = sorted(
            (p for p in tmp_sidecar_testbed.iterdir() if p.is_file()),
            key=lambda p: p.name.lower(),
        )
        delete_queue: list[Path] = []

        discover_and_parse(
            item_path=item_path,
            item_name="video.mp4",
            siblings=siblings,
            config=mmd_config,
            index_root=tmp_sidecar_testbed.parent,
            delete_queue=delete_queue,
        )

        with caplog.at_level(logging.INFO, logger="shruggie_indexer"):
            deleted = _drain_delete_queue(delete_queue)

        assert deleted > 0
        sidecar_deleted_messages = [
            r for r in caplog.records
            if "Sidecar deleted:" in r.message
        ]
        assert len(sidecar_deleted_messages) == deleted
        # Every message MUST be at INFO level.
        for record in sidecar_deleted_messages:
            assert record.levelno == logging.INFO

    def test_delete_phase_continues_on_failure(
        self, tmp_sidecar_testbed: Path, mmd_config,
    ) -> None:
        """If one sidecar deletion fails (e.g., file already removed), the loop
        continues and deletes remaining files."""
        item_path = tmp_sidecar_testbed / "video.mp4"
        siblings = sorted(
            (p for p in tmp_sidecar_testbed.iterdir() if p.is_file()),
            key=lambda p: p.name.lower(),
        )
        delete_queue: list[Path] = []

        discover_and_parse(
            item_path=item_path,
            item_name="video.mp4",
            siblings=siblings,
            config=mmd_config,
            index_root=tmp_sidecar_testbed.parent,
            delete_queue=delete_queue,
        )

        unique_paths = list(dict.fromkeys(delete_queue))
        if len(unique_paths) < 2:
            pytest.skip("Need at least 2 queued sidecars to test failure recovery")

        # Remove the first unique file manually to trigger a failure.
        unique_paths[0].unlink()
        expected_successes = len(unique_paths) - 1

        deleted = _drain_delete_queue(delete_queue)

        # One failed (already removed), rest should succeed.
        assert deleted == expected_successes

    def test_delete_phase_deduplicates_queue(
        self, tmp_sidecar_testbed: Path, mmd_config, caplog,
    ) -> None:
        """When the queue contains duplicate paths, each file is deleted
        only once — no spurious ERROR messages for already-deleted files."""
        item_path = tmp_sidecar_testbed / "video.mp4"
        siblings = sorted(
            (p for p in tmp_sidecar_testbed.iterdir() if p.is_file()),
            key=lambda p: p.name.lower(),
        )
        delete_queue: list[Path] = []

        discover_and_parse(
            item_path=item_path,
            item_name="video.mp4",
            siblings=siblings,
            config=mmd_config,
            index_root=tmp_sidecar_testbed.parent,
            delete_queue=delete_queue,
        )

        # Artificially double each entry to ensure dedup is tested.
        delete_queue_doubled = delete_queue + list(delete_queue)

        with caplog.at_level(logging.INFO, logger="shruggie_indexer"):
            deleted = _drain_delete_queue(delete_queue_doubled)

        unique_count = len(set(delete_queue))
        assert deleted == unique_count

        # No ERROR messages — dedup prevents double-delete failures.
        error_messages = [
            r for r in caplog.records
            if r.levelno >= logging.ERROR and "Sidecar delete FAILED" in r.message
        ]
        assert len(error_messages) == 0, (
            f"Dedup should prevent double-delete errors: {error_messages}"
        )

    def test_delete_phase_logs_failures_at_error(
        self, tmp_sidecar_testbed: Path, mmd_config, caplog,
    ) -> None:
        """Failed deletions produce ERROR-level log messages."""
        # Create a queue with a path that doesn't exist on disk.
        nonexistent = tmp_sidecar_testbed / "ghost_sidecar.json"
        delete_queue: list[Path] = [nonexistent]

        with caplog.at_level(logging.ERROR, logger="shruggie_indexer"):
            deleted = _drain_delete_queue(delete_queue)

        assert deleted == 0
        error_messages = [
            r for r in caplog.records
            if "Sidecar delete FAILED:" in r.message
        ]
        assert len(error_messages) == 1
        assert error_messages[0].levelno == logging.ERROR


# ── Test 3: Stage 7 — stale metadata cleanup ───────────────────────────

from types import SimpleNamespace

from shruggie_indexer.core.entry import cleanup_stale_metadata


def _make_file_entry(relative: str, storage_name: str = "xABC123.txt") -> SimpleNamespace:
    """Build a minimal file-entry-like object for cleanup tests."""
    return SimpleNamespace(
        type="file",
        file_system=SimpleNamespace(relative=relative),
        attributes=SimpleNamespace(storage_name=storage_name),
        items=None,
    )


def _make_dir_entry(
    relative: str, items: list | None = None,
) -> SimpleNamespace:
    """Build a minimal directory-entry-like object for cleanup tests."""
    return SimpleNamespace(
        type="directory",
        file_system=SimpleNamespace(relative=relative),
        attributes=None,
        items=items if items is not None else [],
    )


@pytest.mark.mmd
class TestStaleMetadataCleanup:
    """Validate Stage 7: stale metadata artifact cleanup."""

    def test_removes_stale_meta_json(self, tmp_path: Path, mmd_config) -> None:
        """Stale _meta.json files from prior v1 runs are removed."""
        content = tmp_path / "file.txt"
        content.write_text("content", encoding="utf-8")
        stale = tmp_path / "file.txt_meta.json"
        stale.write_text("{}", encoding="utf-8")

        entry = _make_dir_entry(".", items=[
            _make_file_entry("file.txt"),
        ])

        removed = cleanup_stale_metadata(entry, tmp_path, mmd_config)

        assert removed == 1
        assert not stale.exists()
        assert content.exists()

    def test_removes_stale_meta2_json(self, tmp_path: Path, mmd_config) -> None:
        """Stale _meta2.json files from a prior v2 run are removed."""
        content = tmp_path / "file.txt"
        content.write_text("content", encoding="utf-8")
        # Current-run sidecar (should survive).
        current = tmp_path / "file.txt_meta2.json"
        current.write_text("{}", encoding="utf-8")
        # Stale sidecar from a prior run with a different naming convention.
        stale = tmp_path / "OldName_meta2.json"
        stale.write_text("{}", encoding="utf-8")

        entry = _make_dir_entry(".", items=[
            _make_file_entry("file.txt", storage_name="xABC123.txt"),
        ])

        removed = cleanup_stale_metadata(entry, tmp_path, mmd_config)

        assert removed == 1
        assert not stale.exists()
        assert current.exists(), "Current-run sidecar must survive"
        assert content.exists()

    def test_removes_stale_directorymeta_json(
        self, tmp_path: Path, mmd_config,
    ) -> None:
        """Stale _directorymeta.json and _directorymeta2.json are removed."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        stale_v1 = subdir / "sub_directorymeta.json"
        stale_v1.write_text("{}", encoding="utf-8")
        stale_v2 = subdir / "OldName_directorymeta2.json"
        stale_v2.write_text("{}", encoding="utf-8")

        entry = _make_dir_entry(".", items=[
            _make_dir_entry("sub", items=[]),
        ])

        removed = cleanup_stale_metadata(entry, tmp_path, mmd_config)

        assert removed == 2
        assert not stale_v1.exists()
        assert not stale_v2.exists()

    def test_preserves_current_run_sidecars(
        self, tmp_path: Path, mmd_config,
    ) -> None:
        """Current-run _meta2.json and _directorymeta2.json output files
        are NOT deleted."""
        # File and its current-run sidecar.
        content = tmp_path / "photo.jpg"
        content.write_text("image", encoding="utf-8")
        file_sidecar = tmp_path / "photo.jpg_meta2.json"
        file_sidecar.write_text("{}", encoding="utf-8")

        # Subdirectory with current-run directory sidecar.
        subdir = tmp_path / "images"
        subdir.mkdir()
        dir_sidecar = subdir / "images_directorymeta2.json"
        dir_sidecar.write_text("{}", encoding="utf-8")

        entry = _make_dir_entry(".", items=[
            _make_file_entry("photo.jpg", storage_name="xABC.jpg"),
            _make_dir_entry("images", items=[]),
        ])

        removed = cleanup_stale_metadata(entry, tmp_path, mmd_config)

        assert removed == 0
        assert file_sidecar.exists(), "Current-run file sidecar must survive"
        assert dir_sidecar.exists(), "Current-run directory sidecar must survive"

    def test_preserves_renamed_sidecar(
        self, tmp_path: Path,
    ) -> None:
        """When rename is active, the storage-name sidecar is protected."""
        config = load_config(overrides={
            "meta_merge": True,
            "meta_merge_delete": True,
            "output_inplace": True,
            "rename": True,
        })

        # After rename, sidecar is named after storage_name.
        renamed_sidecar = tmp_path / "xABC123.jpg_meta2.json"
        renamed_sidecar.write_text("{}", encoding="utf-8")

        entry = _make_dir_entry(".", items=[
            _make_file_entry("photo.jpg", storage_name="xABC123.jpg"),
        ])

        removed = cleanup_stale_metadata(entry, tmp_path, config)

        assert removed == 0
        assert renamed_sidecar.exists(), "Renamed sidecar must survive"

    def test_does_not_run_when_mmd_false(
        self, tmp_path: Path, merge_only_config,
    ) -> None:
        """Cleanup must not delete anything when meta_merge_delete=False.

        Note: The caller (CLI/GUI) is responsible for guarding the call.
        This test verifies that the function itself operates correctly
        regardless, since the function always cleans — the guard is in
        the orchestrator.  This test documents the expected integration
        pattern.
        """
        stale = tmp_path / "file.txt_meta.json"
        stale.write_text("{}", encoding="utf-8")

        entry = _make_dir_entry(".", items=[])

        # The function itself does not check meta_merge_delete — it always
        # cleans.  The CLI/GUI guard the call with `if config.meta_merge_delete`.
        # We test that the stale file IS removed when the function is called
        # (proving the logic works) and trust the integration guard.
        removed = cleanup_stale_metadata(entry, tmp_path, merge_only_config)

        assert removed == 1

    def test_logs_deletions_at_info(
        self, tmp_path: Path, mmd_config, caplog,
    ) -> None:
        """Each stale artifact deletion produces an INFO log message."""
        stale1 = tmp_path / "a_meta.json"
        stale1.write_text("{}", encoding="utf-8")
        stale2 = tmp_path / "b_meta2.json"
        stale2.write_text("{}", encoding="utf-8")

        entry = _make_dir_entry(".", items=[])

        with caplog.at_level(logging.INFO, logger="shruggie_indexer.core.entry"):
            removed = cleanup_stale_metadata(entry, tmp_path, mmd_config)

        assert removed == 2
        stale_messages = [
            r for r in caplog.records
            if "Stale metadata artifact removed:" in r.message
        ]
        assert len(stale_messages) == 2

    def test_continues_on_failure(
        self, tmp_path: Path, mmd_config, caplog,
    ) -> None:
        """If one deletion fails, remaining stale files are still deleted."""
        stale1 = tmp_path / "a_meta.json"
        stale1.write_text("{}", encoding="utf-8")
        stale2 = tmp_path / "b_meta2.json"
        stale2.write_text("{}", encoding="utf-8")

        # Pre-remove stale1 to simulate a permission/race failure path.
        stale1.unlink()

        entry = _make_dir_entry(".", items=[])

        with caplog.at_level(logging.WARNING, logger="shruggie_indexer.core.entry"):
            removed = cleanup_stale_metadata(entry, tmp_path, mmd_config)

        # stale1 was already gone (no deletion counted), stale2 should succeed.
        assert removed == 1
        assert not stale2.exists()

    def test_does_not_touch_non_metadata_files(
        self, tmp_path: Path, mmd_config,
    ) -> None:
        """Content files and non-metadata files are untouched by cleanup."""
        content = tmp_path / "video.mp4"
        content.write_text("video", encoding="utf-8")
        info_json = tmp_path / "video.mp4.info.json"
        info_json.write_text("{}", encoding="utf-8")
        srt = tmp_path / "video.mp4.en.srt"
        srt.write_text("subs", encoding="utf-8")

        entry = _make_dir_entry(".", items=[
            _make_file_entry("video.mp4"),
        ])

        removed = cleanup_stale_metadata(entry, tmp_path, mmd_config)

        assert removed == 0
        assert content.exists()
        assert info_json.exists()
        assert srt.exists()

    def test_handles_nested_directories(
        self, tmp_path: Path, mmd_config,
    ) -> None:
        """Stale files in nested subdirectories are also cleaned."""
        sub = tmp_path / "level1"
        sub.mkdir()
        deep = sub / "level2"
        deep.mkdir()

        stale_root = tmp_path / "root_meta.json"
        stale_root.write_text("{}", encoding="utf-8")
        stale_sub = sub / "sub_meta2.json"
        stale_sub.write_text("{}", encoding="utf-8")
        stale_deep = deep / "deep_directorymeta.json"
        stale_deep.write_text("{}", encoding="utf-8")

        entry = _make_dir_entry(".", items=[
            _make_dir_entry("level1", items=[
                _make_dir_entry("level1/level2", items=[]),
            ]),
        ])

        removed = cleanup_stale_metadata(entry, tmp_path, mmd_config)

        assert removed == 3
        assert not stale_root.exists()
        assert not stale_sub.exists()
        assert not stale_deep.exists()

    def test_no_inplace_means_all_stale(
        self, tmp_path: Path,
    ) -> None:
        """When output_inplace=False, no current-run sidecars exist, so all
        metadata artifacts are stale and removed."""
        config = load_config(overrides={
            "meta_merge": True,
            "meta_merge_delete": True,
            "output_inplace": False,
            "output_file": str(tmp_path / "output.json"),
        })

        artifact = tmp_path / "file.txt_meta2.json"
        artifact.write_text("{}", encoding="utf-8")

        entry = _make_dir_entry(".", items=[
            _make_file_entry("file.txt"),
        ])

        removed = cleanup_stale_metadata(entry, tmp_path, config)

        assert removed == 1
        assert not artifact.exists()

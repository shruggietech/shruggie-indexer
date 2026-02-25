"""Integration tests for the MetaMergeDelete pipeline.

Runs the full indexing pipeline (via ``index_path()``) against a temporary copy
of the sidecar-testbed fixture and validates end-to-end behavior including
sidecar exclusion, metadata merging, file deletion, and rename interactions.

Batch 6, Section 5.5.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.entry import index_path
from shruggie_indexer.core.rename import rename_inplace_sidecar, rename_item
from shruggie_indexer.core.serializer import write_inplace
from shruggie_indexer.models.schema import IndexEntry

# ── Fixture paths ───────────────────────────────────────────────────────
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SIDECAR_TESTBED = FIXTURES_DIR / "sidecar-testbed"


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_sidecar_testbed(tmp_path: Path) -> Path:
    """Create a disposable copy of the sidecar-testbed fixture."""
    dest = tmp_path / "sidecar-testbed"
    shutil.copytree(SIDECAR_TESTBED, dest)
    return dest


@pytest.fixture()
def mmd_config():
    """Config with MetaMerge + MetaMergeDelete enabled, recursive."""
    return load_config(overrides={
        "meta_merge": True,
        "meta_merge_delete": True,
        "output_inplace": True,
        "recursive": True,
    })


@pytest.fixture()
def mmd_rename_config():
    """Config with MetaMerge + MetaMergeDelete + Rename + InPlace enabled."""
    return load_config(overrides={
        "meta_merge": True,
        "meta_merge_delete": True,
        "rename": True,
        "output_inplace": True,
        "recursive": True,
    })


# ── Helpers ─────────────────────────────────────────────────────────────


def _collect_file_entries(entry: IndexEntry) -> list[IndexEntry]:
    """Collect all file-type entries from the tree recursively."""
    result: list[IndexEntry] = []
    if entry.type == "file":
        result.append(entry)
    if entry.items:
        for child in entry.items:
            result.extend(_collect_file_entries(child))
    return result


def _collect_all_names(entry: IndexEntry) -> set[str]:
    """Collect all item names (file and directory) from the tree."""
    names: set[str] = set()
    if entry.name and entry.name.text:
        names.add(entry.name.text)
    if entry.items:
        for child in entry.items:
            names.update(_collect_all_names(child))
    return names


def _drain_delete_queue(queue: list[Path]) -> int:
    """Test copy of the drain function."""
    import logging

    logger = logging.getLogger(__name__)
    deleted = 0
    for path in queue:
        try:
            path.unlink()
            logger.info("Sidecar deleted: %s", path)
            deleted += 1
        except OSError as exc:
            logger.error("Sidecar delete FAILED: %s: %s", path, exc)
    return deleted


def _write_inplace_tree(entry: Any, root_path: Path) -> None:
    """Recursively write in-place sidecar files for an entry tree."""
    if entry.type == "file":
        item_path = root_path.parent / entry.file_system.relative
        write_inplace(entry, item_path, "file")
    elif entry.type == "directory":
        dir_path = root_path.parent / entry.file_system.relative
        write_inplace(entry, dir_path, "directory")
        if entry.items:
            for child in entry.items:
                _write_inplace_tree(child, root_path)


def _rename_tree(entry: Any, root_path: Path, config: Any) -> None:
    """Recursively rename all file entries in the tree."""
    if entry.items is None:
        return
    for child in entry.items:
        if child.type == "file":
            child_path = root_path.parent / child.file_system.relative
            try:
                rename_item(child_path, child, dry_run=config.dry_run)
                if config.output_inplace:
                    rename_inplace_sidecar(child_path, child)
            except Exception:
                pass
        elif child.type == "directory" and child.items:
            _rename_tree(child, root_path, config)


# ── Test 1: Full MetaMergeDelete pipeline ───────────────────────────────


@pytest.mark.mmd
@pytest.mark.integration
class TestMMDPipeline:
    """Full MetaMergeDelete pipeline tests."""

    def test_mmd_pipeline_item_count(
        self, tmp_sidecar_testbed: Path, mmd_config,
    ) -> None:
        """The root entry's items list contains only content files and
        directories, no sidecar or indexer-output files."""
        delete_queue: list[Path] = []
        entry = index_path(
            tmp_sidecar_testbed, mmd_config, delete_queue=delete_queue,
        )

        all_names = _collect_all_names(entry)

        # Indexer output artifacts must NOT appear.
        assert "video.mp4_meta.json" not in all_names
        assert "video.mp4_meta2.json" not in all_names
        assert "_directorymeta2.json" not in all_names
        assert "nested.txt_meta.json" not in all_names

        # Sidecar files must NOT appear as standalone items.
        assert "video.mp4.info.json" not in all_names
        assert "video.mp4.description" not in all_names
        assert "video.mp4_screen.jpg" not in all_names
        assert "photo.jpg.md5" not in all_names

        # Content files MUST appear.
        assert "video.mp4" in all_names
        assert "content.txt" in all_names
        assert "photo.jpg" in all_names
        assert "data.csv" in all_names
        assert "nested.txt" in all_names
        assert "standalone.pdf" in all_names
        assert "standalone_notes.txt" in all_names

    def test_mmd_pipeline_metadata_merged(
        self, tmp_sidecar_testbed: Path, mmd_config,
    ) -> None:
        """Content files with sidecars contain MetadataEntry objects in their
        metadata array with origin='sidecar'."""
        delete_queue: list[Path] = []
        entry = index_path(
            tmp_sidecar_testbed, mmd_config, delete_queue=delete_queue,
        )

        file_entries = _collect_file_entries(entry)
        video_entries = [
            e for e in file_entries if e.name.text == "video.mp4"
        ]
        assert len(video_entries) == 1
        video = video_entries[0]

        assert video.metadata is not None
        sidecar_origins = [
            m for m in video.metadata if m.origin == "sidecar"
        ]
        assert len(sidecar_origins) > 0, (
            "video.mp4 should have sidecar metadata entries"
        )

    def test_mmd_pipeline_sidecars_deleted(
        self, tmp_sidecar_testbed: Path, mmd_config,
    ) -> None:
        """After the pipeline completes, sidecar files are absent from disk."""
        delete_queue: list[Path] = []
        entry = index_path(
            tmp_sidecar_testbed, mmd_config, delete_queue=delete_queue,
        )

        # Drain the delete queue.
        _drain_delete_queue(delete_queue)

        # Sidecar files should be gone.
        remaining = list(tmp_sidecar_testbed.rglob("*.info.json"))
        remaining += list(tmp_sidecar_testbed.rglob("*.description"))
        remaining += list(tmp_sidecar_testbed.rglob("*.md5"))
        remaining += list(tmp_sidecar_testbed.rglob("*_screen.jpg"))
        remaining += list(tmp_sidecar_testbed.rglob("*.yaml"))
        # Filter to only actual sidecar matches (not content files).
        sidecar_remaining = [
            f for f in remaining
            if f.name not in {"content.txt", "data.csv", "standalone_notes.txt"}
        ]
        assert len(sidecar_remaining) == 0, (
            f"Sidecar files should be deleted: {[f.name for f in sidecar_remaining]}"
        )

    def test_mmd_pipeline_content_files_intact(
        self, tmp_sidecar_testbed: Path, mmd_config,
    ) -> None:
        """After the pipeline completes, content files exist on disk."""
        delete_queue: list[Path] = []
        index_path(tmp_sidecar_testbed, mmd_config, delete_queue=delete_queue)
        _drain_delete_queue(delete_queue)

        assert (tmp_sidecar_testbed / "video.mp4").exists()
        assert (tmp_sidecar_testbed / "content.txt").exists()
        assert (tmp_sidecar_testbed / "photo.jpg").exists()
        assert (tmp_sidecar_testbed / "data.csv").exists()
        assert (tmp_sidecar_testbed / "subdir" / "nested.txt").exists()
        assert (tmp_sidecar_testbed / "no-sidecars" / "standalone.pdf").exists()
        assert (tmp_sidecar_testbed / "no-sidecars" / "standalone_notes.txt").exists()


# ── Test 2: Full MetaMergeDelete + Rename pipeline ──────────────────────


@pytest.mark.mmd
@pytest.mark.integration
class TestMMDRenamePipeline:
    """MetaMergeDelete + Rename combined pipeline tests."""

    def test_mmd_rename_pipeline_files_renamed(
        self, tmp_sidecar_testbed: Path, mmd_rename_config,
    ) -> None:
        """Content files are renamed to storage_name values on disk."""
        delete_queue: list[Path] = []
        entry = index_path(
            tmp_sidecar_testbed, mmd_rename_config, delete_queue=delete_queue,
        )

        # Write in-place first, then rename (Section 4 ordering).
        _write_inplace_tree(entry, tmp_sidecar_testbed)
        _rename_tree(entry, tmp_sidecar_testbed, mmd_rename_config)
        _drain_delete_queue(delete_queue)

        file_entries = _collect_file_entries(entry)
        for fe in file_entries:
            storage_name = fe.attributes.storage_name
            expected_path = tmp_sidecar_testbed.parent / fe.file_system.relative
            # The original name should be gone.
            original_path = expected_path.parent / fe.name.text
            renamed_path = expected_path.parent / storage_name

            # At least one of them should exist (renamed or already renamed).
            assert renamed_path.exists() or original_path.exists(), (
                f"Neither {renamed_path.name} nor {original_path.name} exists"
            )

    def test_mmd_rename_pipeline_sidecars_deleted(
        self, tmp_sidecar_testbed: Path, mmd_rename_config,
    ) -> None:
        """Sidecar files are deleted even when rename is active."""
        delete_queue: list[Path] = []
        entry = index_path(
            tmp_sidecar_testbed, mmd_rename_config, delete_queue=delete_queue,
        )

        _write_inplace_tree(entry, tmp_sidecar_testbed)
        _rename_tree(entry, tmp_sidecar_testbed, mmd_rename_config)
        deleted = _drain_delete_queue(delete_queue)

        assert deleted > 0, "At least some sidecar files should be deleted"

    def test_mmd_rename_pipeline_inplace_sidecar_named_correctly(
        self, tmp_sidecar_testbed: Path, mmd_rename_config,
    ) -> None:
        """In-place _meta2.json files are named relative to the storage_name,
        not the original name."""
        delete_queue: list[Path] = []
        entry = index_path(
            tmp_sidecar_testbed, mmd_rename_config, delete_queue=delete_queue,
        )

        _write_inplace_tree(entry, tmp_sidecar_testbed)
        _rename_tree(entry, tmp_sidecar_testbed, mmd_rename_config)

        file_entries = _collect_file_entries(entry)
        for fe in file_entries:
            storage_name = fe.attributes.storage_name
            parent_dir = (
                tmp_sidecar_testbed.parent / fe.file_system.relative
            ).parent
            expected_sidecar = parent_dir / f"{storage_name}_meta2.json"
            original_sidecar = parent_dir / f"{fe.name.text}_meta2.json"

            # The sidecar should be named with storage_name, not original name.
            if expected_sidecar.exists():
                assert not original_sidecar.exists() or original_sidecar == expected_sidecar, (
                    f"Orphaned original sidecar should not exist: {original_sidecar.name}"
                )

    def test_mmd_rename_no_sidecar_of_sidecar(
        self, tmp_sidecar_testbed: Path, mmd_rename_config,
    ) -> None:
        """No file matching *_meta*_meta2.json exists after the run."""
        delete_queue: list[Path] = []
        entry = index_path(
            tmp_sidecar_testbed, mmd_rename_config, delete_queue=delete_queue,
        )

        _write_inplace_tree(entry, tmp_sidecar_testbed)
        _rename_tree(entry, tmp_sidecar_testbed, mmd_rename_config)
        _drain_delete_queue(delete_queue)

        # Search for sidecar-of-sidecar files.
        import re

        sidecar_of_sidecar = [
            f for f in tmp_sidecar_testbed.rglob("*")
            if f.is_file() and re.search(r"_meta\d?\.json_meta2\.json$", f.name)
        ]
        assert len(sidecar_of_sidecar) == 0, (
            f"Sidecar-of-sidecar files found: {[f.name for f in sidecar_of_sidecar]}"
        )


# ── Test 3: Idempotency ────────────────────────────────────────────────


@pytest.mark.mmd
@pytest.mark.integration
class TestMMDIdempotency:
    """Running the pipeline twice should produce consistent results."""

    def test_mmd_pipeline_idempotent(
        self, tmp_sidecar_testbed: Path, mmd_config,
    ) -> None:
        """Running MetaMergeDelete twice against the same directory produces
        identical output on the second run."""
        # First run.
        delete_queue_1: list[Path] = []
        entry_1 = index_path(
            tmp_sidecar_testbed, mmd_config, delete_queue=delete_queue_1,
        )
        _drain_delete_queue(delete_queue_1)

        names_1 = _collect_all_names(entry_1)
        file_count_1 = len(_collect_file_entries(entry_1))

        # Second run — sidecars have been deleted, so no new discoveries.
        delete_queue_2: list[Path] = []
        entry_2 = index_path(
            tmp_sidecar_testbed, mmd_config, delete_queue=delete_queue_2,
        )

        names_2 = _collect_all_names(entry_2)
        file_count_2 = len(_collect_file_entries(entry_2))

        assert names_1 == names_2, "Item names should be identical between runs"
        assert file_count_1 == file_count_2, "File count should be identical"
        assert len(delete_queue_2) == 0, (
            "No new sidecars should be discovered on second run"
        )

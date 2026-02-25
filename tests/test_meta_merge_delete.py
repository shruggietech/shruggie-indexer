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


@pytest.mark.mmd
@pytest.mark.destructive
class TestDeletePhaseExecution:
    """Validate the drain function deletes files correctly."""

    @staticmethod
    def _drain_delete_queue(queue: list[Path]) -> int:
        """Local copy of the drain function for testing."""
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

        # All queued paths should exist before drain.
        for path in delete_queue:
            assert path.exists(), f"Sidecar should exist before drain: {path}"

        deleted = self._drain_delete_queue(delete_queue)

        assert deleted == len(delete_queue)
        for path in delete_queue:
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

        self._drain_delete_queue(delete_queue)

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

        with caplog.at_level(logging.INFO):
            deleted = self._drain_delete_queue(delete_queue)

        assert deleted > 0
        sidecar_deleted_messages = [
            r for r in caplog.records
            if "Sidecar deleted:" in r.message
        ]
        assert len(sidecar_deleted_messages) == deleted

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

        if len(delete_queue) < 2:
            pytest.skip("Need at least 2 queued sidecars to test failure recovery")

        # Remove the first file manually to trigger a failure.
        delete_queue[0].unlink()
        original_count = len(delete_queue)

        deleted = self._drain_delete_queue(delete_queue)

        # One failed (already removed), rest should succeed.
        assert deleted == original_count - 1

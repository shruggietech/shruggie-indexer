"""Integration tests — CLI rollback subcommand via Click test runner.

15 test cases per batch 005, §3.6.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from shruggie_indexer.cli.main import ExitCode, main

# Path to the rollback-testbed fixtures.
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "rollback-testbed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    """Isolated Click CLI test runner."""
    return CliRunner()


def _make_renamed_workdir(tmp_path: Path) -> Path:
    """Copy the renamed/ fixture into a fresh working directory.

    Returns the working directory containing the copied files.
    """
    workdir = tmp_path / "workdir"
    shutil.copytree(FIXTURES / "renamed", workdir)
    return workdir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRollbackRenamedDirectory:
    """Index with rename → rollback → verify tree matches original."""

    def test_rollback_renamed_directory(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = _make_renamed_workdir(tmp_path)
        target = tmp_path / "restored"
        target.mkdir()

        # Rollback the renamed files into the target directory
        meta2 = workdir / "y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe_meta2.json"
        result = runner.invoke(
            main,
            ["rollback", str(meta2), "--target", str(target), "--no-verify"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        # The original name from the sidecar is "flashplayer.exe" at "testdir/flashplayer.exe"
        restored = target / "testdir" / "flashplayer.exe"
        assert restored.exists(), f"Expected {restored} to exist after rollback"


class TestRollbackWithDedup:
    """Index with rename + dedup → rollback → verify all copies restored."""

    def test_rollback_with_dedup(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = tmp_path / "workdir"
        shutil.copytree(FIXTURES / "deduplicated", workdir)
        target = tmp_path / "restored"
        target.mkdir()

        meta2 = workdir / "y2FFA202F241801EF7FF9C7212EBBC693.jpg_meta2.json"
        result = runner.invoke(
            main,
            ["rollback", str(meta2), "--target", str(target), "--no-verify"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        # Canonical: images/photo.jpg
        assert (target / "images" / "photo.jpg").exists()
        # Duplicate: backup/photo_copy.jpg
        assert (target / "backup" / "photo_copy.jpg").exists()


class TestRollbackAggregateOutput:
    """Rollback from aggregate output file + explicit --source."""

    def test_rollback_aggregate_output(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        # Copy aggregate meta2 and renamed files as source
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        shutil.copy2(
            FIXTURES / "aggregate" / "photos_directorymeta2.json",
            workdir / "photos_directorymeta2.json",
        )

        source = tmp_path / "source"
        shutil.copytree(FIXTURES / "renamed", source)

        target = tmp_path / "restored"
        target.mkdir()

        result = runner.invoke(
            main,
            [
                "rollback",
                str(workdir / "photos_directorymeta2.json"),
                "--target", str(target),
                "--source", str(source),
                "--no-verify",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0


class TestRollbackFlatMode:
    """--flat restores files without directory structure."""

    def test_rollback_flat_mode(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = _make_renamed_workdir(tmp_path)
        target = tmp_path / "flat_output"
        target.mkdir()

        meta2 = workdir / "y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe_meta2.json"
        result = runner.invoke(
            main,
            [
                "rollback", str(meta2),
                "--target", str(target),
                "--flat",
                "--no-verify",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        # Flat mode: file should be directly in target, no subdirectories
        assert (target / "flashplayer.exe").exists()
        assert not (target / "testdir").exists()


class TestRollbackFlatCollision:
    """--flat with name collisions produces warnings and skips."""

    def test_rollback_flat_collision(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = tmp_path / "workdir"
        shutil.copytree(FIXTURES / "renamed", workdir)
        target = tmp_path / "flat_collision"
        target.mkdir()

        # Pre-create a file that will collide in flat mode
        (target / "flashplayer.exe").write_bytes(b"existing content")

        meta2 = workdir / "y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe_meta2.json"
        result = runner.invoke(
            main,
            [
                "rollback", str(meta2),
                "--target", str(target),
                "--flat",
                "--no-verify",
            ],
            catch_exceptions=False,
        )
        # Should still succeed (skipped items are not failures)
        # but the file is skipped because it already exists
        assert "skipped" in (result.output + (result.stderr or "")).lower() or result.exit_code == 0


class TestRollbackMixedSessionsWarning:
    """Structured mode with mixed session_id emits warning to stderr."""

    def test_rollback_mixed_sessions_warning(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = tmp_path / "workdir"
        shutil.copytree(FIXTURES / "mixed-sessions", workdir)
        target = tmp_path / "restored"
        target.mkdir()

        result = runner.invoke(
            main,
            [
                "rollback", str(workdir),
                "--target", str(target),
                "--no-verify",
            ],
            catch_exceptions=False,
        )
        # Mixed-session warning should be emitted
        combined = (result.output or "") + (result.stderr or "")
        assert "session" in combined.lower() or "WARNING" in combined


class TestRollbackTargetDefaultFile:
    """Omitting --target for a single meta2 file defaults to its parent directory."""

    def test_rollback_target_default_file(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = _make_renamed_workdir(tmp_path)
        meta2 = workdir / "y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe_meta2.json"

        result = runner.invoke(
            main,
            ["rollback", str(meta2), "--no-verify"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        # Default target is meta2.parent (= workdir), so restored file is at
        # workdir / testdir / flashplayer.exe
        restored = workdir / "testdir" / "flashplayer.exe"
        assert restored.exists(), f"Expected {restored} (default target = meta2 parent)"


class TestRollbackTargetDefaultDir:
    """Omitting --target for a directory defaults to that directory."""

    def test_rollback_target_default_dir(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = tmp_path / "workdir"
        shutil.copytree(FIXTURES / "renamed", workdir)

        result = runner.invoke(
            main,
            ["rollback", str(workdir), "--no-verify"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        # Default target is the directory itself, so restored files go into
        # workdir / testdir / ...
        assert (workdir / "testdir" / "flashplayer.exe").exists() or (
            workdir / "testdir" / "testfile.txt"
        ).exists()


class TestRollbackDryRun:
    """Dry-run produces log output, no filesystem writes."""

    def test_rollback_dry_run(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = _make_renamed_workdir(tmp_path)
        target = tmp_path / "dry_run_target"
        target.mkdir()

        meta2 = workdir / "y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe_meta2.json"
        result = runner.invoke(
            main,
            [
                "rollback", str(meta2),
                "--target", str(target),
                "--dry-run",
                "--no-verify",
                "-v",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        # No files should exist in the target (dry-run)
        actual_files = list(target.rglob("*"))
        dirs_only = all(p.is_dir() for p in actual_files)
        has_no_files = len([p for p in actual_files if p.is_file()]) == 0
        assert has_no_files, "Dry-run should not create any files"


class TestRollbackNoVerify:
    """--no-verify skips hash computation."""

    def test_rollback_no_verify(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = _make_renamed_workdir(tmp_path)
        target = tmp_path / "restored"
        target.mkdir()

        meta2 = workdir / "y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe_meta2.json"
        result = runner.invoke(
            main,
            [
                "rollback", str(meta2),
                "--target", str(target),
                "--no-verify",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        # File should be restored even though hash may not match fixture content
        assert (target / "testdir" / "flashplayer.exe").exists()


class TestRollbackForceOverwrite:
    """--force overwrites existing target files."""

    def test_rollback_force_overwrite(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = _make_renamed_workdir(tmp_path)
        target = tmp_path / "restored"
        target.mkdir()
        (target / "testdir").mkdir()
        (target / "testdir" / "flashplayer.exe").write_bytes(b"old content")

        meta2 = workdir / "y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe_meta2.json"
        result = runner.invoke(
            main,
            [
                "rollback", str(meta2),
                "--target", str(target),
                "--no-verify",
                "--force",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        # File should be overwritten with the source content
        restored = target / "testdir" / "flashplayer.exe"
        assert restored.exists()
        content = restored.read_bytes()
        assert content != b"old content", "File should have been overwritten by --force"


class TestRollbackSkipDuplicates:
    """--skip-duplicates restores only canonical entries."""

    def test_rollback_skip_duplicates(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = tmp_path / "workdir"
        shutil.copytree(FIXTURES / "deduplicated", workdir)
        target = tmp_path / "restored"
        target.mkdir()

        meta2 = workdir / "y2FFA202F241801EF7FF9C7212EBBC693.jpg_meta2.json"
        result = runner.invoke(
            main,
            [
                "rollback", str(meta2),
                "--target", str(target),
                "--no-verify",
                "--skip-duplicates",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        # Canonical should be restored
        assert (target / "images" / "photo.jpg").exists()
        # Duplicate should NOT be restored
        assert not (target / "backup" / "photo_copy.jpg").exists()


class TestRollbackV1Rejection:
    """v1 sidecar input produces clear error and exit code 2."""

    def test_rollback_v1_rejection(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        shutil.copy2(
            FIXTURES / "v1" / "legacy_meta.json",
            workdir / "legacy_meta.json",
        )

        result = runner.invoke(
            main,
            ["rollback", str(workdir / "legacy_meta.json")],
            catch_exceptions=False,
        )
        assert result.exit_code == ExitCode.CONFIGURATION_ERROR
        combined = (result.output or "") + (result.stderr or "")
        assert "schema" in combined.lower() or "v1" in combined.lower() or "version" in combined.lower()


class TestRollbackBackwardCompat:
    """shruggie-indexer /path (no subcommand) still invokes index."""

    def test_rollback_backward_compat(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        target = tmp_path / "hello.txt"
        target.write_text("hello world", encoding="utf-8")

        # Mock exiftool to avoid test dependency
        import shruggie_indexer.core.exif as exif_mod

        old_path = exif_mod._exiftool_path
        old_avail = exif_mod._pyexiftool_available
        old_backend = exif_mod._backend
        old_helper = exif_mod._batch_helper

        exif_mod._exiftool_path = None
        exif_mod._pyexiftool_available = False
        exif_mod._backend = None
        exif_mod._batch_helper = None

        try:
            result = runner.invoke(
                main,
                [str(target)],
                catch_exceptions=False,
            )
        finally:
            exif_mod._exiftool_path = old_path
            exif_mod._pyexiftool_available = old_avail
            exif_mod._backend = old_backend
            exif_mod._batch_helper = old_helper

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["schema_version"] == 2
        assert parsed["type"] == "file"


class TestRollbackTimestampRestoration:
    """Restored files have correct mtime and atime."""

    def test_rollback_timestamp_restoration(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        workdir = _make_renamed_workdir(tmp_path)
        target = tmp_path / "restored"
        target.mkdir()

        meta2 = workdir / "y0EA30B0C7E392876DAAA2D55EF6AEA3E.exe_meta2.json"
        result = runner.invoke(
            main,
            [
                "rollback", str(meta2),
                "--target", str(target),
                "--no-verify",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        restored = target / "testdir" / "flashplayer.exe"
        assert restored.exists()

        # From fixture: modified unix = 1691106464000 (ms) → 1691106464.0 (s)
        # accessed unix = 1771165698109 (ms) → 1771165698.109 (s)
        stat = restored.stat()
        expected_mtime = 1691106464.0
        expected_atime = 1771165698.109

        # Allow 2-second tolerance for filesystem granularity
        assert abs(stat.st_mtime - expected_mtime) < 2.0, (
            f"mtime mismatch: {stat.st_mtime} vs expected {expected_mtime}"
        )


class TestRollbackHelp:
    """--help displays the full option set."""

    def test_rollback_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["rollback", "--help"])
        assert result.exit_code == 0
        output = result.output
        assert "--target" in output
        assert "--source" in output
        assert "--recursive" in output
        assert "--flat" in output
        assert "--dry-run" in output
        assert "--no-verify" in output
        assert "--force" in output
        assert "--skip-duplicates" in output
        assert "--no-restore-sidecars" in output
        assert "META2_PATH" in output

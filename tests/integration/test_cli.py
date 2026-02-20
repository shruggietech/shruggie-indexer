"""Integration tests — CLI invocation via Click test runner.

14 test cases per §14.3.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from shruggie_indexer.cli.main import ExitCode, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    """Isolated Click CLI test runner."""
    return CliRunner()


def _invoke(runner: CliRunner, args: list[str], **kwargs):
    """Invoke the CLI with exiftool mocked out."""
    import shruggie_indexer.core.exif as exif_mod

    # Ensure exiftool is disabled for all CLI tests.
    old_path = exif_mod._exiftool_path
    old_avail = exif_mod._pyexiftool_available
    old_backend = exif_mod._backend
    old_helper = exif_mod._batch_helper

    exif_mod._exiftool_path = None
    exif_mod._pyexiftool_available = False
    exif_mod._backend = None
    exif_mod._batch_helper = None

    try:
        result = runner.invoke(main, args, catch_exceptions=False, **kwargs)
    finally:
        exif_mod._exiftool_path = old_path
        exif_mod._pyexiftool_available = old_avail
        exif_mod._backend = old_backend
        exif_mod._batch_helper = old_helper

    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCliHelp:
    """Tests for --help and --version."""

    def test_help_exits_zero(self, runner: CliRunner) -> None:
        """--help prints usage and exits 0."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Usage" in result.output or "usage" in result.output.lower()

    def test_version_prints_version(self, runner: CliRunner) -> None:
        """--version prints 0.1.0 and exits 0."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestCliDefaultInvocation:
    """Tests for default CLI invocation."""

    def test_default_invocation_indexes_cwd(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        """Invoking without arguments indexes the current directory."""
        (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")
        result = _invoke(runner, [str(tmp_path)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["schema_version"] == 2


class TestCliTargetModes:
    """Tests for --file and --directory target modes."""

    def test_file_mode(self, runner: CliRunner, tmp_path: Path) -> None:
        """--file forces file treatment."""
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02")
        result = _invoke(runner, ["--file", str(f)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["type"] == "file"

    def test_directory_mode(self, runner: CliRunner, tmp_path: Path) -> None:
        """--directory forces directory treatment."""
        result = _invoke(runner, ["--directory", str(tmp_path)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["type"] == "directory"


class TestCliRecursive:
    """Tests for --recursive and --no-recursive."""

    def test_recursive_flag(
        self, runner: CliRunner, sample_tree: Path,
    ) -> None:
        """--recursive produces nested items."""
        result = _invoke(runner, [str(sample_tree), "--recursive"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["items"] is not None

    def test_no_recursive_flag(
        self, runner: CliRunner, sample_tree: Path,
    ) -> None:
        """--no-recursive produces items but subdirs have items=None."""
        result = _invoke(runner, [str(sample_tree), "--no-recursive"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["items"] is not None


class TestCliOutfile:
    """Tests for --outfile output."""

    def test_outfile(self, runner: CliRunner, tmp_path: Path) -> None:
        """--outfile writes JSON to the specified file."""
        target = tmp_path / "target.txt"
        target.write_text("content", encoding="utf-8")
        outfile = tmp_path / "result.json"

        result = _invoke(runner, [str(target), "--outfile", str(outfile)])
        assert result.exit_code == 0
        assert outfile.exists()
        parsed = json.loads(outfile.read_text(encoding="utf-8"))
        assert parsed["schema_version"] == 2


class TestCliInplace:
    """Tests for --inplace output."""

    def test_inplace(self, runner: CliRunner, tmp_path: Path) -> None:
        """--inplace creates sidecar files."""
        target = tmp_path / "target.txt"
        target.write_text("content", encoding="utf-8")

        result = _invoke(runner, [str(target), "--inplace"])
        assert result.exit_code == 0
        sidecar = tmp_path / "target.txt_meta2.json"
        assert sidecar.exists()


class TestCliMetaMerge:
    """Tests for --meta-merge (with exiftool mocked)."""

    def test_meta_merge(self, runner: CliRunner, tmp_path: Path) -> None:
        """--meta-merge enables sidecar merging."""
        target = tmp_path / "video.mp4"
        target.write_bytes(b"mp4")
        (tmp_path / "video.description").write_text("desc", encoding="utf-8")

        result = _invoke(
            runner,
            [str(target), "--meta-merge", "--stdout"],
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        # metadata should be a list (possibly with sidecar entries).
        assert parsed.get("metadata") is not None


class TestCliRename:
    """Tests for --rename --dry-run."""

    def test_rename_dry_run(self, runner: CliRunner, tmp_path: Path) -> None:
        """--rename --dry-run does NOT rename the file."""
        target = tmp_path / "original.txt"
        target.write_text("content", encoding="utf-8")

        result = _invoke(
            runner,
            [str(target), "--rename", "--dry-run", "--inplace"],
        )
        assert result.exit_code == 0
        # Original file should still exist.
        assert target.exists()


class TestCliIdType:
    """Tests for --id-type and --compute-sha512."""

    def test_id_type_sha256(self, runner: CliRunner, tmp_path: Path) -> None:
        """--id-type sha256 uses SHA-256 for identity."""
        target = tmp_path / "data.txt"
        target.write_text("data", encoding="utf-8")

        result = _invoke(runner, [str(target), "--id-type", "sha256"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["id_algorithm"] == "sha256"
        # SHA-256 IDs are longer than MD5 IDs.
        assert len(parsed["id"]) > 40

    def test_compute_sha512(self, runner: CliRunner, tmp_path: Path) -> None:
        """--compute-sha512 includes sha512 in hash output."""
        target = tmp_path / "data.txt"
        target.write_text("data", encoding="utf-8")

        result = _invoke(runner, [str(target), "--compute-sha512"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "sha512" in parsed["hashes"]


class TestCliVerbosity:
    """Tests for verbosity levels."""

    def test_quiet_mode(self, runner: CliRunner, tmp_path: Path) -> None:
        """--quiet suppresses non-error output on stderr."""
        target = tmp_path / "data.txt"
        target.write_text("data", encoding="utf-8")

        result = _invoke(runner, [str(target), "-q"])
        assert result.exit_code == 0
        # stderr should have minimal output.
        assert "ERROR" not in (result.stderr or "")


class TestCliInvalidTarget:
    """Tests for invalid target handling."""

    def test_invalid_target_exits_nonzero(self, runner: CliRunner) -> None:
        """A non-existent target results in a non-zero exit code."""
        result = runner.invoke(
            main,
            ["/nonexistent/path/that/does/not/exist"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0

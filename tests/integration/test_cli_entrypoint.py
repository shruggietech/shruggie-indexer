"""Smoke tests — CLI entry-point wiring.

Validates that every supported invocation path (pip console_script,
``python -m shruggie_indexer``, and PyInstaller ``__main__.py``) correctly
reaches the Click command group and produces output.  These tests exist to
prevent a regression of the silent-exit bug where the CLI binary defined
commands but never invoked them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from shruggie_indexer._version import __version__
from shruggie_indexer.cli.main import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    """Isolated Click CLI test runner."""
    return CliRunner()


# ---------------------------------------------------------------------------
# Click entry-point tests (in-process)
# ---------------------------------------------------------------------------


class TestClickEntryPoint:
    """Verify the Click group is callable and produces expected output."""

    def test_help_flag_produces_output(self, runner: CliRunner) -> None:
        """``--help`` must produce non-empty usage text."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        assert len(result.output.strip()) > 0, "Help output must not be empty"
        assert "usage" in result.output.lower()

    def test_short_help_flag(self, runner: CliRunner) -> None:
        """``-h`` must behave the same as ``--help``."""
        result = runner.invoke(main, ["-h"])
        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        assert "usage" in result.output.lower()

    def test_version_flag(self, runner: CliRunner) -> None:
        """``--version`` must print the version string."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_index_subcommand_help(self, runner: CliRunner) -> None:
        """``index --help`` must describe the index subcommand."""
        result = runner.invoke(main, ["index", "--help"])
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0

    def test_rollback_subcommand_help(self, runner: CliRunner) -> None:
        """``rollback --help`` must describe the rollback subcommand."""
        result = runner.invoke(main, ["rollback", "--help"])
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0


# ---------------------------------------------------------------------------
# ``python -m`` entry-point test (out-of-process)
# ---------------------------------------------------------------------------


class TestModuleEntryPoint:
    """Verify ``python -m shruggie_indexer`` works correctly."""

    def test_module_help(self) -> None:
        """``python -m shruggie_indexer --help`` must produce usage text."""
        result = subprocess.run(
            [sys.executable, "-m", "shruggie_indexer", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"returncode={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "usage" in result.stdout.lower()

    def test_module_version(self) -> None:
        """``python -m shruggie_indexer --version`` must print the version."""
        result = subprocess.run(
            [sys.executable, "-m", "shruggie_indexer", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert __version__ in result.stdout


# ---------------------------------------------------------------------------
# Direct script entry-point test (simulates PyInstaller path)
# ---------------------------------------------------------------------------


class TestDirectScriptEntryPoint:
    """Verify ``python cli/main.py`` runs correctly (PyInstaller path)."""

    def test_cli_main_direct_help(self) -> None:
        """Running cli/main.py directly must produce help (via __name__ guard)."""
        cli_main_path = (
            Path(__file__).resolve().parents[2] / "src" / "shruggie_indexer" / "cli" / "main.py"
        )
        if not cli_main_path.exists():
            pytest.skip(f"cli/main.py not found at {cli_main_path}")

        result = subprocess.run(
            [sys.executable, str(cli_main_path), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**__import__("os").environ, "PYTHONPATH": str(cli_main_path.parents[2])},
        )
        assert result.returncode == 0, (
            f"returncode={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        assert len(result.stdout.strip()) > 0, "Direct script invocation produced no output"

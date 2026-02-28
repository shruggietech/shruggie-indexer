"""Unit tests for app_paths.py — §3.3 Application Data Directory.

Tests the canonical path resolver that owns all application data
directory resolution for shruggie-indexer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shruggie_indexer.app_paths import get_app_data_dir, get_log_dir


# ---------------------------------------------------------------------------
# get_app_data_dir()
# ---------------------------------------------------------------------------


class TestGetAppDataDir:
    """Tests for get_app_data_dir()."""

    def test_returns_path_object(self) -> None:
        """get_app_data_dir() returns a Path instance."""
        result = get_app_data_dir()
        assert isinstance(result, Path)

    def test_ends_with_ecosystem_namespace(self) -> None:
        """Path ends with shruggie-tech/shruggie-indexer."""
        result = get_app_data_dir()
        assert result.parts[-2] == "shruggie-tech"
        assert result.parts[-1] == "shruggie-indexer"

    def test_windows_uses_localappdata(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """On Windows, resolves via LOCALAPPDATA environment variable."""
        monkeypatch.setattr("shruggie_indexer.app_paths.platform.system", lambda: "Windows")
        local_appdata = str(tmp_path / "LocalAppData")
        monkeypatch.setenv("LOCALAPPDATA", local_appdata)
        result = get_app_data_dir()
        assert result == Path(local_appdata) / "shruggie-tech" / "shruggie-indexer"

    def test_windows_fallback_without_env(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """On Windows, falls back to ~/AppData/Local when LOCALAPPDATA is unset."""
        monkeypatch.setattr("shruggie_indexer.app_paths.platform.system", lambda: "Windows")
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        result = get_app_data_dir()
        expected_base = Path.home() / "AppData" / "Local"
        assert result == expected_base / "shruggie-tech" / "shruggie-indexer"

    def test_linux_uses_xdg_config_home(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """On Linux, resolves via XDG_CONFIG_HOME."""
        monkeypatch.setattr("shruggie_indexer.app_paths.platform.system", lambda: "Linux")
        xdg_dir = str(tmp_path / "xdg-config")
        monkeypatch.setenv("XDG_CONFIG_HOME", xdg_dir)
        result = get_app_data_dir()
        assert result == Path(xdg_dir) / "shruggie-tech" / "shruggie-indexer"

    def test_linux_fallback_without_env(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """On Linux, falls back to ~/.config when XDG_CONFIG_HOME is unset."""
        monkeypatch.setattr("shruggie_indexer.app_paths.platform.system", lambda: "Linux")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = get_app_data_dir()
        expected_base = Path.home() / ".config"
        assert result == expected_base / "shruggie-tech" / "shruggie-indexer"

    def test_macos_uses_library_application_support(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """On macOS, uses ~/Library/Application Support."""
        monkeypatch.setattr("shruggie_indexer.app_paths.platform.system", lambda: "Darwin")
        result = get_app_data_dir()
        expected = (
            Path.home() / "Library" / "Application Support"
            / "shruggie-tech" / "shruggie-indexer"
        )
        assert result == expected


# ---------------------------------------------------------------------------
# get_log_dir()
# ---------------------------------------------------------------------------


class TestGetLogDir:
    """Tests for get_log_dir()."""

    def test_returns_path_object(self) -> None:
        """get_log_dir() returns a Path instance."""
        result = get_log_dir()
        assert isinstance(result, Path)

    def test_is_subdirectory_of_app_data_dir(self) -> None:
        """Log directory is <app_data_dir>/logs/."""
        app_dir = get_app_data_dir()
        log_dir = get_log_dir()
        assert log_dir == app_dir / "logs"
        assert log_dir.name == "logs"

    def test_windows_log_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """On Windows, log dir is under LOCALAPPDATA."""
        monkeypatch.setattr("shruggie_indexer.app_paths.platform.system", lambda: "Windows")
        local_appdata = str(tmp_path / "LocalAppData")
        monkeypatch.setenv("LOCALAPPDATA", local_appdata)
        result = get_log_dir()
        assert result == (
            Path(local_appdata) / "shruggie-tech" / "shruggie-indexer" / "logs"
        )

    def test_no_shruggie_tech_pascal_case(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """The path must never contain 'ShruggieTech' (PascalCase)."""
        for system in ("Windows", "Linux", "Darwin"):
            monkeypatch.setattr(
                "shruggie_indexer.app_paths.platform.system", lambda s=system: s,
            )
            if system == "Windows":
                monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
            result = get_log_dir()
            assert "ShruggieTech" not in str(result), (
                f"PascalCase 'ShruggieTech' found in path for {system}: {result}"
            )


# ---------------------------------------------------------------------------
# log_file.get_default_log_dir() delegation
# ---------------------------------------------------------------------------


class TestLogFileGetDefaultLogDir:
    """Verify log_file.get_default_log_dir() delegates to app_paths."""

    def test_delegates_to_app_paths(self) -> None:
        """get_default_log_dir() returns the same value as get_log_dir()."""
        from shruggie_indexer.log_file import get_default_log_dir

        assert get_default_log_dir() == get_log_dir()

"""Unit tests for core/paths.py — §6.2 Path Resolution and Manipulation.

11 test cases per §14.2.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.paths import (
    PathComponents,
    build_sidecar_path,
    build_storage_path,
    extract_components,
    resolve_path,
    validate_extension,
)


@pytest.fixture()
def config():
    """Default config for extension validation tests."""
    return load_config()


# ---------------------------------------------------------------------------
# resolve_path()
# ---------------------------------------------------------------------------


class TestResolvePath:
    """Tests for resolve_path()."""

    def test_resolve_absolute_path(self, tmp_path: Path) -> None:
        """An absolute, existing path is returned resolved."""
        f = tmp_path / "test.txt"
        f.write_text("x", encoding="utf-8")
        result = resolve_path(f)
        assert result.is_absolute()
        assert result.exists()

    def test_resolve_relative_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A relative path is resolved to an absolute form relative to cwd."""
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "rel.txt"
        f.write_text("x", encoding="utf-8")
        result = resolve_path(Path("rel.txt"))
        assert result.is_absolute()
        assert result == f.resolve()


# ---------------------------------------------------------------------------
# extract_components()
# ---------------------------------------------------------------------------


class TestExtractComponents:
    """Tests for extract_components()."""

    def test_extract_components(self, tmp_path: Path) -> None:
        """Full component extraction from a typical path."""
        p = tmp_path / "photos" / "sunset.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("img", encoding="utf-8")
        resolved = resolve_path(p)
        result = extract_components(resolved)
        assert result.name == "sunset.jpg"
        assert result.stem == "sunset"
        assert result.suffix == "jpg"
        assert result.parent_name == "photos"
        assert result.parent_path == resolved.parent

    def test_extension_lowercasing(self, tmp_path: Path) -> None:
        """FILE.JPG -> suffix 'jpg'."""
        p = tmp_path / "FILE.JPG"
        p.write_text("img", encoding="utf-8")
        result = extract_components(resolve_path(p))
        assert result.suffix == "jpg"

    def test_no_extension(self, tmp_path: Path) -> None:
        """A file named 'Makefile' -> suffix None."""
        p = tmp_path / "Makefile"
        p.write_text("all:", encoding="utf-8")
        result = extract_components(resolve_path(p))
        assert result.suffix is None

    def test_multi_dot_extension(self, tmp_path: Path) -> None:
        """'archive.tar.gz' -> suffix 'gz' (only the final extension)."""
        p = tmp_path / "archive.tar.gz"
        p.write_bytes(b"\x00")
        result = extract_components(resolve_path(p))
        assert result.suffix == "gz"

    def test_root_level_parent(self) -> None:
        """Root-level file has empty parent_name string."""
        if sys.platform == "win32":
            p = Path("C:/file.txt")
        else:
            p = Path("/file.txt")
        result = extract_components(p)
        assert result.parent_name == ""


# ---------------------------------------------------------------------------
# validate_extension()
# ---------------------------------------------------------------------------


class TestValidateExtension:
    """Tests for validate_extension()."""

    def test_extension_validation_pass(self, config) -> None:
        """'jpg' passes the default validation regex."""
        assert validate_extension("jpg", config) == "jpg"

    def test_extension_validation_fail(self, config) -> None:
        """'thisextensionistoolong' fails validation -> None."""
        assert validate_extension("thisextensionistoolong", config) is None

    def test_none_extension(self, config) -> None:
        """None input returns None."""
        assert validate_extension(None, config) is None


# ---------------------------------------------------------------------------
# build_sidecar_path()
# ---------------------------------------------------------------------------


class TestBuildSidecarPath:
    """Tests for build_sidecar_path()."""

    def test_sidecar_path_file(self) -> None:
        """File sidecar: sunset.jpg -> sunset.jpg_meta2.json."""
        p = Path("/photos/sunset.jpg")
        result = build_sidecar_path(p, "file")
        assert result == Path("/photos/sunset.jpg_meta2.json")

    def test_sidecar_path_directory(self) -> None:
        """Directory sidecar: vacation/ -> vacation/_directorymeta2.json."""
        p = Path("/photos/vacation")
        result = build_sidecar_path(p, "directory")
        assert result == Path("/photos/vacation/_directorymeta2.json")


# ---------------------------------------------------------------------------
# build_storage_path()
# ---------------------------------------------------------------------------


class TestBuildStoragePath:
    """Tests for build_storage_path()."""

    def test_build_storage_path(self) -> None:
        """storage_name is joined to parent directory."""
        p = Path("/photos/sunset.jpg")
        result = build_storage_path(p, "yABCD1234.jpg")
        assert result == Path("/photos/yABCD1234.jpg")

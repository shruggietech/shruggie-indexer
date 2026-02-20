"""Shared test fixtures for shruggie-indexer.

Provides common fixtures used across all test modules.  See §14.2 for the
full test specification.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import IndexerConfig

# Path to the fixtures directory (resolved relative to this file).
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    """Create a temporary file with known content for hashing tests.

    Content: ``b"hello world"`` (11 bytes).
    """
    p = tmp_path / "sample.txt"
    p.write_bytes(b"hello world")
    return p


@pytest.fixture()
def empty_file(tmp_path: Path) -> Path:
    """Create a zero-byte temporary file."""
    p = tmp_path / "empty.bin"
    p.write_bytes(b"")
    return p


@pytest.fixture()
def large_file(tmp_path: Path) -> Path:
    """Create a file larger than the 64 KB chunk size.

    Content: 128 KB of repeating ``b"A"`` bytes.
    """
    p = tmp_path / "large.bin"
    p.write_bytes(b"A" * (128 * 1024))
    return p


@pytest.fixture()
def sample_tree(tmp_path: Path) -> Path:
    """Create a small directory tree for traversal and path tests.

    Structure::

        sample_tree/
            file_a.txt      (content: "aaa")
            file_b.jpg      (content: "bbb")
            subdir/
                nested.txt   (content: "nested")
    """
    root = tmp_path / "sample_tree"
    root.mkdir()
    (root / "file_a.txt").write_text("aaa", encoding="utf-8")
    (root / "file_b.jpg").write_text("bbb", encoding="utf-8")
    sub = root / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested", encoding="utf-8")
    return root


@pytest.fixture()
def default_config() -> IndexerConfig:
    """Return the compiled-default configuration (no config files)."""
    return load_config()


@pytest.fixture()
def mock_exiftool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable exiftool by patching the module-level probe state.

    Sets the ``exif`` module to report no exiftool backend so that tests
    run without requiring ``exiftool`` on PATH.
    """
    import shruggie_indexer.core.exif as _exif_mod

    monkeypatch.setattr(_exif_mod, "_exiftool_path", None)
    monkeypatch.setattr(_exif_mod, "_pyexiftool_available", False)
    monkeypatch.setattr(_exif_mod, "_backend", None)
    monkeypatch.setattr(_exif_mod, "_batch_helper", None)


@pytest.fixture()
def exiftool_response() -> dict[str, Any]:
    """Load the exe exiftool response fixture as a parsed dict."""
    fixture = FIXTURES_DIR / "exiftool_responses" / "exe_response.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))
    return data[0]


@pytest.fixture()
def sidecar_tree(tmp_path: Path) -> Path:
    """Create a directory with a primary file and sidecar siblings.

    Structure::

        sidecar_tree/
            sample_video.mp4         (content: b"mp4data")
            sample_video.description (text description)
            sample_video.info.json   (JSON metadata)
            sample_video.md5         (hash file)
            sample_video.srt         (subtitles)
            sample_video.url         (link)
            sample_video.cfg         (generic metadata)
            sample_video.thumb.jpg   (thumbnail — binary stub)
            desktop.ini              (desktop_ini)
    """
    root = tmp_path / "sidecar_tree"
    root.mkdir()

    # Primary file.
    (root / "sample_video.mp4").write_bytes(b"mp4data")

    # Sidecars — copy from fixtures where possible, or inline.
    fixtures_dir = FIXTURES_DIR / "sidecar_samples"
    for name in (
        "sample_video.description",
        "sample_video.info.json",
        "sample_video.md5",
        "sample_video.srt",
        "sample_video.url",
        "sample_video.cfg",
        "desktop.ini",
    ):
        src = fixtures_dir / name
        if src.exists():
            (root / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            (root / name).write_text(f"placeholder: {name}", encoding="utf-8")

    # Binary sidecar (thumbnail).
    (root / "sample_video.thumb.jpg").write_bytes(b"\xff\xd8\xff\xe0thumb")

    return root

"""Shared test fixtures for shruggie-indexer.

Provides common fixtures used across all test modules.  See §14.2 for the
full test specification.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import IndexerConfig


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
    """Stub placeholder for exiftool mocking (Sprint 2.1).

    Currently a no-op.  When ``core/exif.py`` is implemented, this fixture
    will patch ``shutil.which("exiftool")`` and provide canned JSON output.
    """

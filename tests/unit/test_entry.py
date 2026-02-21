"""Unit tests for core/entry.py — §6.8 Index Entry Construction.

8 test cases per §14.2.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import IndexerConfig
from shruggie_indexer.core.entry import (
    build_directory_entry,
    build_file_entry,
)
from shruggie_indexer.exceptions import IndexerCancellationError
from shruggie_indexer.models.schema import IndexEntry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(**overrides: object) -> IndexerConfig:
    return load_config(overrides=overrides)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildFileEntry:
    """Tests for build_file_entry() — the 12-step orchestration."""

    def test_file_entry_construction(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """Full file entry is constructed with all required fields."""
        config = _cfg()
        entry = build_file_entry(sample_file, config)

        assert isinstance(entry, IndexEntry)
        assert entry.schema_version == 2
        assert entry.type == "file"
        assert entry.id.startswith("y")
        assert entry.name.text == "sample.txt"
        assert entry.extension == "txt"
        assert entry.size.bytes == 11
        assert entry.hashes is not None
        assert entry.hashes.md5 is not None
        assert entry.file_system is not None
        assert entry.timestamps is not None
        assert entry.attributes.is_link is False
        assert entry.items is None

    def test_file_entry_metadata_none_when_disabled(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """Metadata is None when extract_exif and meta_merge are both off."""
        config = _cfg(extract_exif=False, meta_merge=False)
        entry = build_file_entry(sample_file, config)
        assert entry.metadata is None


class TestBuildDirectoryEntry:
    """Tests for build_directory_entry()."""

    def test_directory_entry_construction(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """Directory entry has correct type and contains child items."""
        config = _cfg()
        entry = build_directory_entry(sample_tree, config, recursive=False)

        assert entry.type == "directory"
        assert entry.id.startswith("x")
        assert entry.extension is None
        assert entry.hashes is None
        assert entry.items is not None
        assert len(entry.items) > 0

    def test_recursive_directory_has_nested_items(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """Recursive mode populates nested directory items trees."""
        config = _cfg()
        entry = build_directory_entry(sample_tree, config, recursive=True)

        assert entry.items is not None
        # The sample tree has: file_a.txt, file_b.jpg, subdir/
        # Recursive makes subdir have its own items.
        subdirs = [i for i in entry.items if i.type == "directory"]
        assert len(subdirs) >= 1
        subdir = subdirs[0]
        assert subdir.items is not None
        nested_files = [i for i in subdir.items if i.type == "file"]
        assert len(nested_files) >= 1


class TestSymlinkEntry:
    """Tests for symlink file entries."""

    @pytest.mark.skipif(
        sys.platform == "win32" and not os.environ.get("CI"),
        reason="Symlink creation may require elevated privileges on Windows",
    )
    def test_symlink_entry_is_link_true(
        self, tmp_path: Path, mock_exiftool: None,
    ) -> None:
        """Symlink files have is_link=True and name-based hashes."""
        target = tmp_path / "real.txt"
        target.write_text("real content", encoding="utf-8")
        link = tmp_path / "link.txt"
        link.symlink_to(target)

        config = _cfg()
        entry = build_file_entry(link, config)

        assert entry.attributes.is_link is True
        assert entry.hashes is not None


class TestCancellation:
    """Tests for cooperative cancellation."""

    def test_cancellation_raises(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """Setting cancel_event raises IndexerCancellationError."""
        config = _cfg()
        cancel = threading.Event()
        cancel.set()  # Pre-set to trigger immediately.

        with pytest.raises(IndexerCancellationError):
            build_directory_entry(
                sample_tree, config,
                recursive=False,
                cancel_event=cancel,
            )


class TestProgressCallback:
    """Tests for progress callback invocation."""

    def test_progress_callback_called(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """Progress callback is invoked at least once during directory indexing."""
        config = _cfg()
        events: list[Any] = []

        def on_progress(event: Any) -> None:
            events.append(event)

        build_directory_entry(
            sample_tree, config,
            recursive=False,
            progress_callback=on_progress,
        )

        assert len(events) > 0
        # First event should be discovery phase.
        assert events[0].phase == "discovery"
        # Subsequent events should be processing.
        processing = [e for e in events if e.phase == "processing"]
        assert len(processing) > 0


class TestMissingExiftoolDegradation:
    """Tests for graceful degradation when exiftool is absent."""

    def test_metadata_still_works_without_exiftool(
        self, tmp_path: Path, mock_exiftool: None,
    ) -> None:
        """With extract_exif=True but no exiftool, metadata is empty list."""
        f = tmp_path / "test.txt"
        f.write_text("content", encoding="utf-8")

        config = _cfg(extract_exif=True)
        entry = build_file_entry(f, config)

        # Metadata should be an empty list (not None) since extract_exif is True.
        assert entry.metadata is not None
        assert isinstance(entry.metadata, list)


class TestSidecarFolding:
    """Tests for sidecar metadata being merged into the entry."""

    def test_sidecar_folded_into_metadata(
        self, tmp_path: Path, mock_exiftool: None,
    ) -> None:
        """With meta_merge=True, sidecar entries are folded into metadata."""
        root = tmp_path / "fold"
        root.mkdir()
        primary = root / "video.mp4"
        primary.write_bytes(b"mp4data")
        (root / "video.description").write_text("A video", encoding="utf-8")

        config = _cfg(meta_merge=True, extract_exif=False)
        siblings = sorted(
            [p for p in root.iterdir() if p.is_file()],
            key=lambda p: p.name.lower(),
        )
        entry = build_file_entry(primary, config, siblings=siblings)

        assert entry.metadata is not None
        assert len(entry.metadata) >= 1
        sidecar_entries = [
            m for m in entry.metadata if m.origin == "sidecar"
        ]
        assert len(sidecar_entries) >= 1

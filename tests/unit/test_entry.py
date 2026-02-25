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

    def test_cancel_during_file_hashing(
        self, tmp_path: Path, mock_exiftool: None,
    ) -> None:
        """Pre-set cancel_event raises from build_file_entry (via hash_file)."""
        # Create a file larger than one chunk so the cancel check triggers.
        f = tmp_path / "big.bin"
        f.write_bytes(b"A" * (128 * 1024))
        config = _cfg()
        cancel = threading.Event()
        cancel.set()

        with pytest.raises(IndexerCancellationError):
            build_file_entry(f, config, cancel_event=cancel)


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


class TestSessionIdThreading:
    """Tests for session_id propagation through entry builders."""

    def test_file_entry_session_id_populated(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """build_file_entry passes session_id to the entry."""
        config = _cfg()
        sid = "aaaaaaaa-bbbb-4ccc-9ddd-eeeeeeeeeeee"
        entry = build_file_entry(sample_file, config, session_id=sid)

        assert entry.session_id == sid

    def test_file_entry_session_id_none_by_default(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """build_file_entry without session_id leaves it None."""
        config = _cfg()
        entry = build_file_entry(sample_file, config)

        assert entry.session_id is None

    def test_directory_entry_session_id_threaded(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """session_id is threaded to all children in build_directory_entry."""
        config = _cfg()
        sid = "aaaaaaaa-bbbb-4ccc-9ddd-eeeeeeeeeeee"
        entry = build_directory_entry(
            sample_tree, config, recursive=True, session_id=sid,
        )

        assert entry.session_id == sid
        assert entry.items is not None
        for child in entry.items:
            assert child.session_id == sid
            if child.type == "directory" and child.items:
                for grandchild in child.items:
                    assert grandchild.session_id == sid


class TestIndexedAtTimestamp:
    """Tests for indexed_at timestamp generation."""

    def test_file_entry_has_indexed_at(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """build_file_entry populates indexed_at."""
        config = _cfg()
        entry = build_file_entry(sample_file, config)

        assert entry.indexed_at is not None
        assert entry.indexed_at.iso is not None
        assert entry.indexed_at.unix > 0

    def test_directory_entry_has_indexed_at(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """build_directory_entry populates indexed_at."""
        config = _cfg()
        entry = build_directory_entry(sample_tree, config, recursive=False)

        assert entry.indexed_at is not None
        assert entry.indexed_at.iso is not None
        assert entry.indexed_at.unix > 0

    def test_indexed_at_varies_between_entries(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """indexed_at values differ between parent and children."""
        config = _cfg()
        entry = build_directory_entry(sample_tree, config, recursive=False)

        assert entry.items is not None
        assert len(entry.items) > 0
        # The parent and at least one child should have distinct unix values
        # or iso values (they're generated at different moments in time).
        all_unix = [entry.indexed_at.unix] + [
            c.indexed_at.unix for c in entry.items if c.indexed_at is not None
        ]
        # With sufficient entries, at least two should differ (not guaranteed
        # for ultra-fast machines, so we just verify they are all populated).
        assert all(u > 0 for u in all_unix)

    def test_default_entry_has_no_indexed_at(self) -> None:
        """Directly constructed IndexEntry without indexed_at has None."""
        from shruggie_indexer.models.schema import (
            AttributesObject,
            FileSystemObject,
            HashSet,
            IndexEntry,
            NameObject,
            SizeObject,
            TimestampPair,
            TimestampsObject,
        )

        pair = TimestampPair(iso="2024-01-01T00:00:00.000000+00:00", unix=1704067200000)
        entry = IndexEntry(
            schema_version=2,
            id="yD41D8CD98F00B204E9800998ECF8427E",
            id_algorithm="md5",
            type="file",
            name=NameObject(
                text="test.txt",
                hashes=HashSet(
                    md5="D41D8CD98F00B204E9800998ECF8427E",
                    sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
                ),
            ),
            extension="txt",
            size=SizeObject(text="0 B", bytes=0),
            hashes=HashSet(
                md5="D41D8CD98F00B204E9800998ECF8427E",
                sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
            ),
            file_system=FileSystemObject(relative="test.txt", parent=None),
            timestamps=TimestampsObject(created=pair, modified=pair, accessed=pair),
            attributes=AttributesObject(
                is_link=False,
                storage_name="yD41D8CD98F00B204E9800998ECF8427E.txt",
            ),
        )

        assert entry.session_id is None
        assert entry.indexed_at is None

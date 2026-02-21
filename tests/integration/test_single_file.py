"""Integration tests — single file end-to-end indexing.

6 test cases per §14.3.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.entry import index_path
from shruggie_indexer.models.schema import IndexEntry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(**overrides: object):
    return load_config(overrides=overrides)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSingleFileEndToEnd:
    """End-to-end tests for indexing a single file."""

    def test_index_real_file(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """Indexing a real temp file produces a valid IndexEntry."""
        config = _cfg()
        entry = index_path(sample_file, config)

        assert isinstance(entry, IndexEntry)
        assert entry.schema_version == 2
        assert entry.type == "file"

    def test_v2_structure_has_all_required_keys(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """The entry's to_dict() has all 11 required top-level keys."""
        config = _cfg()
        entry = index_path(sample_file, config)
        d = entry.to_dict()

        required_keys = {
            "schema_version", "id", "id_algorithm", "type", "name",
            "extension", "size", "hashes", "file_system", "timestamps",
            "attributes",
        }
        assert required_keys.issubset(d.keys())

    def test_hash_correctness(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """Hashes match hashlib-computed values for the same content."""
        config = _cfg()
        entry = index_path(sample_file, config)

        content = sample_file.read_bytes()
        expected_md5 = hashlib.md5(content).hexdigest().upper()
        expected_sha256 = hashlib.sha256(content).hexdigest().upper()

        assert entry.hashes is not None
        assert entry.hashes.md5 == expected_md5
        assert entry.hashes.sha256 == expected_sha256

    def test_timestamp_plausibility(
        self, tmp_path: Path, mock_exiftool: None,
    ) -> None:
        """Timestamps are plausible (within a reasonable window of 'now')."""
        f = tmp_path / "fresh.txt"
        f.write_text("fresh", encoding="utf-8")

        config = _cfg()
        entry = index_path(f, config)

        # Modified timestamp should be very recent (within 60 seconds).
        now_ms = int(time.time() * 1000)
        assert abs(now_ms - entry.timestamps.modified.unix) < 60_000

    def test_extension_extraction(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """Extension is correctly extracted from the filename."""
        config = _cfg()
        entry = index_path(sample_file, config)
        assert entry.extension == "txt"

    def test_schema_version_value(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """schema_version is always 2."""
        config = _cfg()
        entry = index_path(sample_file, config)
        assert entry.schema_version == 2

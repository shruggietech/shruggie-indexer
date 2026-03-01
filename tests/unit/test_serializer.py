"""Unit tests for core/serializer.py — §6.9 JSON Serialization and Output Routing.

7 test cases per §14.2.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import IndexerConfig
from shruggie_indexer.core.serializer import (
    serialize_entry,
    write_inplace,
    write_output,
)
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hashset(*, sha512: str | None = None) -> HashSet:
    return HashSet(
        md5="D41D8CD98F00B204E9800998ECF8427E",
        sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
        sha512=sha512,
    )


def _make_entry(**overrides: Any) -> IndexEntry:
    pair = TimestampPair(iso="2024-01-01T00:00:00.000000+00:00", unix=1704067200000)
    defaults: dict[str, Any] = {
        "schema_version": 2,
        "id": "yD41D8CD98F00B204E9800998ECF8427E",
        "id_algorithm": "md5",
        "type": "file",
        "name": NameObject(text="test.txt", hashes=_make_hashset()),
        "extension": "txt",
        "size": SizeObject(text="0 B", bytes=0),
        "hashes": _make_hashset(),
        "file_system": FileSystemObject(relative="test.txt", parent=None),
        "timestamps": TimestampsObject(created=pair, modified=pair, accessed=pair),
        "attributes": AttributesObject(
            is_link=False,
            storage_name="yD41D8CD98F00B204E9800998ECF8427E.txt",
        ),
    }
    defaults.update(overrides)
    return IndexEntry(**defaults)


def _cfg(**overrides: object) -> IndexerConfig:
    return load_config(overrides=overrides)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestJsonRoundTrip:
    """Tests for JSON serialization round-trip fidelity."""

    def test_round_trip(self) -> None:
        """serialize_entry → json.loads matches entry.to_dict() semantics."""
        entry = _make_entry()
        json_str = serialize_entry(entry)
        parsed = json.loads(json_str)

        assert parsed["schema_version"] == 2
        assert parsed["id"] == entry.id
        assert parsed["name"]["text"] == "test.txt"
        assert isinstance(parsed["hashes"], dict)
        assert "md5" in parsed["hashes"]


class TestSchemaVersionFirstKey:
    """Tests for schema_version key ordering."""

    def test_schema_version_is_first_key(self) -> None:
        """The first key in the serialized JSON is 'schema_version'."""
        entry = _make_entry()
        json_str = serialize_entry(entry)
        # Parse ordered (json preserves insertion order in CPython 3.7+).
        parsed = json.loads(json_str)
        first_key = next(iter(parsed))
        assert first_key == "schema_version"


class TestSha512Omission:
    """Tests for sha512 omission when not computed."""

    def test_sha512_omitted_when_none(self) -> None:
        """When sha512 is None, it does not appear in output."""
        entry = _make_entry(hashes=_make_hashset(sha512=None))
        json_str = serialize_entry(entry)
        parsed = json.loads(json_str)
        assert "sha512" not in parsed["hashes"]

    def test_sha512_present_when_computed(self) -> None:
        """When sha512 is provided, it appears in output."""
        sha512_val = "A" * 128
        entry = _make_entry(hashes=_make_hashset(sha512=sha512_val))
        json_str = serialize_entry(entry)
        parsed = json.loads(json_str)
        assert parsed["hashes"]["sha512"] == sha512_val


class TestPrettyVsCompact:
    """Tests for pretty-print vs compact output modes."""

    def test_pretty_contains_newlines(self) -> None:
        """Default (pretty) output contains newlines and indentation."""
        entry = _make_entry()
        json_str = serialize_entry(entry, compact=False)
        assert "\n" in json_str
        assert "  " in json_str  # 2-space indent

    def test_compact_single_line(self) -> None:
        """Compact output is a single line with no extra whitespace."""
        entry = _make_entry()
        json_str = serialize_entry(entry, compact=True)
        # Compact should not have newlines within the JSON.
        lines = json_str.strip().split("\n")
        assert len(lines) == 1


class TestEnsureAscii:
    """Tests for ensure_ascii=False (Unicode preservation)."""

    def test_unicode_preserved(self) -> None:
        """Non-ASCII characters are preserved in output, not escaped."""
        entry = _make_entry(
            name=NameObject(text="café.txt", hashes=_make_hashset()),
            extension="txt",
        )
        json_str = serialize_entry(entry)
        assert "café" in json_str
        # Ensure it wasn't escaped.
        assert "\\u00e9" not in json_str


class TestWriteOutput:
    """Tests for write_output() stdout routing."""

    def test_stdout_output(self) -> None:
        """write_output with output_stdout=True writes to stdout."""
        entry = _make_entry()
        config = _cfg(output_stdout=True)

        captured = StringIO()
        with patch("sys.stdout", captured):
            write_output(entry, config)

        output = captured.getvalue()
        assert "schema_version" in output
        parsed = json.loads(output.strip())
        assert parsed["schema_version"] == 2


class TestWriteInplace:
    """Tests for write_inplace() sidecar file naming."""

    def test_inplace_file_naming(self, tmp_path: Path) -> None:
        """File sidecar is named _meta2.json."""
        entry = _make_entry()
        item_path = tmp_path / "test.txt"
        item_path.write_text("content", encoding="utf-8")

        write_inplace(entry, item_path, "file")

        sidecar = tmp_path / "test.txt_meta2.json"
        assert sidecar.exists()
        parsed = json.loads(sidecar.read_text(encoding="utf-8"))
        assert parsed["schema_version"] == 2

    def test_inplace_directory_naming(self, tmp_path: Path) -> None:
        """Directory sidecar is written inside the directory as {dirname}_directorymeta2.json."""
        entry = _make_entry(type="directory", hashes=None, extension=None)
        dir_path = tmp_path / "mydir"
        dir_path.mkdir()

        write_inplace(entry, dir_path, "directory")

        sidecar = dir_path / "mydir_directorymeta2.json"
        assert sidecar.exists()


class TestWriteDirectoryMetaSuppression:
    """Tests for write_directory_meta=False suppression of dir sidecars.

    Verifies that the _write_inplace_tree helper skips directory-level
    _directorymeta2.json files when write_directory_meta is False,
    while per-file sidecars remain unaffected.
    """

    @staticmethod
    def _make_dir_entry(**overrides: Any) -> IndexEntry:
        pair = TimestampPair(
            iso="2024-01-01T00:00:00.000000+00:00", unix=1704067200000,
        )
        defaults: dict[str, Any] = {
            "schema_version": 2,
            "id": "yD41D8CD98F00B204E9800998ECF8427E",
            "id_algorithm": "md5",
            "type": "directory",
            "name": NameObject(
                text="mydir",
                hashes=HashSet(
                    md5="D41D8CD98F00B204E9800998ECF8427E",
                    sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
                    sha512=None,
                ),
            ),
            "extension": None,
            "size": SizeObject(text="0 B", bytes=0),
            "hashes": None,
            "file_system": FileSystemObject(relative="mydir", parent=None),
            "timestamps": TimestampsObject(
                created=pair, modified=pair, accessed=pair,
            ),
            "attributes": AttributesObject(is_link=False, storage_name=None),
        }
        defaults.update(overrides)
        return IndexEntry(**defaults)

    def test_dir_sidecar_written_when_enabled(self, tmp_path: Path) -> None:
        """Directory sidecar is written when write_directory_meta=True."""
        from shruggie_indexer.cli.main import _write_inplace_tree

        root = tmp_path / "root"
        root.mkdir()
        subdir = root / "sub"
        subdir.mkdir()
        (subdir / "file.txt").write_bytes(b"data")

        file_entry = _make_entry(
            file_system=FileSystemObject(
                relative="root/sub/file.txt", parent=None,
            ),
        )
        sub_entry = self._make_dir_entry(
            name=NameObject(
                text="sub",
                hashes=HashSet(
                    md5="D41D8CD98F00B204E9800998ECF8427E",
                    sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
                    sha512=None,
                ),
            ),
            file_system=FileSystemObject(relative="root/sub", parent=None),
            items=[file_entry],
        )
        root_entry = self._make_dir_entry(
            name=NameObject(
                text="root",
                hashes=HashSet(
                    md5="D41D8CD98F00B204E9800998ECF8427E",
                    sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
                    sha512=None,
                ),
            ),
            file_system=FileSystemObject(relative="root", parent=None),
            items=[sub_entry],
        )

        _write_inplace_tree(
            root_entry, root, write_inplace,
            write_directory_meta=True,
        )

        # Sub-directory sidecar should exist
        sub_sidecar = subdir / "sub_directorymeta2.json"
        assert sub_sidecar.exists()
        # File sidecar should exist
        file_sidecar = subdir / "file.txt_meta2.json"
        assert file_sidecar.exists()

    def test_dir_sidecar_suppressed_when_disabled(self, tmp_path: Path) -> None:
        """Directory sidecar is NOT written when write_directory_meta=False."""
        from shruggie_indexer.cli.main import _write_inplace_tree

        root = tmp_path / "root"
        root.mkdir()
        subdir = root / "sub"
        subdir.mkdir()
        (subdir / "file.txt").write_bytes(b"data")

        file_entry = _make_entry(
            file_system=FileSystemObject(
                relative="root/sub/file.txt", parent=None,
            ),
        )
        sub_entry = self._make_dir_entry(
            name=NameObject(
                text="sub",
                hashes=HashSet(
                    md5="D41D8CD98F00B204E9800998ECF8427E",
                    sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
                    sha512=None,
                ),
            ),
            file_system=FileSystemObject(relative="root/sub", parent=None),
            items=[file_entry],
        )
        root_entry = self._make_dir_entry(
            name=NameObject(
                text="root",
                hashes=HashSet(
                    md5="D41D8CD98F00B204E9800998ECF8427E",
                    sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
                    sha512=None,
                ),
            ),
            file_system=FileSystemObject(relative="root", parent=None),
            items=[sub_entry],
        )

        _write_inplace_tree(
            root_entry, root, write_inplace,
            write_directory_meta=False,
        )

        # Sub-directory sidecar should NOT exist
        sub_sidecar = subdir / "sub_directorymeta2.json"
        assert not sub_sidecar.exists()
        # File sidecar should still exist
        file_sidecar = subdir / "file.txt_meta2.json"
        assert file_sidecar.exists()

    def test_file_sidecars_unaffected(self, tmp_path: Path) -> None:
        """Per-file sidecars are always written regardless of write_directory_meta."""
        from shruggie_indexer.cli.main import _write_inplace_tree

        root = tmp_path / "root"
        root.mkdir()
        (root / "a.txt").write_bytes(b"aaa")
        (root / "b.txt").write_bytes(b"bbb")

        entries = []
        for name in ("a.txt", "b.txt"):
            entries.append(
                _make_entry(
                    name=NameObject(
                        text=name,
                        hashes=HashSet(
                            md5="D41D8CD98F00B204E9800998ECF8427E",
                            sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
                            sha512=None,
                        ),
                    ),
                    extension=name.rsplit(".", 1)[-1],
                    file_system=FileSystemObject(
                        relative=f"root/{name}", parent=None,
                    ),
                ),
            )

        root_entry = self._make_dir_entry(
            file_system=FileSystemObject(relative="root", parent=None),
            items=entries,
        )

        _write_inplace_tree(
            root_entry, root, write_inplace,
            write_directory_meta=False,
        )

        assert (root / "a.txt_meta2.json").exists()
        assert (root / "b.txt_meta2.json").exists()

"""Output schema conformance tests — §14.4.

13 validation cases + 4 serialization invariants.

Validates that generated ``IndexEntry`` objects (serialized to JSON) conform
to ``docs/schema/shruggie-indexer-v2.schema.json``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.entry import (
    build_directory_entry,
    build_file_entry,
    index_path,
)
from shruggie_indexer.core.serializer import serialize_entry
from shruggie_indexer.models.schema import (
    AttributesObject,
    FileSystemObject,
    HashSet,
    IndexEntry,
    MetadataAttributes,
    MetadataEntry,
    NameObject,
    ParentObject,
    SizeObject,
    TimestampPair,
    TimestampsObject,
)

# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "schema"
    / "shruggie-indexer-v2.schema.json"
)


@pytest.fixture(scope="module")
def v2_schema() -> dict[str, Any]:
    """Load the v2 JSON Schema once per module."""
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(**overrides: object):
    return load_config(overrides=overrides)


def _make_hashset(*, sha512: str | None = None) -> HashSet:
    return HashSet(
        md5="D41D8CD98F00B204E9800998ECF8427E",
        sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
        sha512=sha512,
    )


def _make_timestamps() -> TimestampsObject:
    pair = TimestampPair(iso="2024-01-01T00:00:00.000000+00:00", unix=1704067200000)
    return TimestampsObject(created=pair, modified=pair, accessed=pair)


def _make_file_entry(**overrides: Any) -> IndexEntry:
    defaults: dict[str, Any] = {
        "schema_version": 2,
        "id": "yD41D8CD98F00B204E9800998ECF8427E",
        "id_algorithm": "md5",
        "type": "file",
        "name": NameObject(text="test.txt", hashes=_make_hashset()),
        "extension": "txt",
        "size": SizeObject(text="0 B", bytes=0),
        "hashes": _make_hashset(),
        "file_system": FileSystemObject(
            relative="test.txt",
            parent=ParentObject(
                id="xABCDEF0123456789ABCDEF0123456789",
                name=NameObject(text="parent", hashes=_make_hashset()),
            ),
        ),
        "timestamps": _make_timestamps(),
        "attributes": AttributesObject(
            is_link=False,
            storage_name="yD41D8CD98F00B204E9800998ECF8427E.txt",
        ),
    }
    defaults.update(overrides)
    return IndexEntry(**defaults)


def _make_dir_entry(**overrides: Any) -> IndexEntry:
    defaults: dict[str, Any] = {
        "schema_version": 2,
        "id": "xABCDEF0123456789ABCDEF0123456789",
        "id_algorithm": "md5",
        "type": "directory",
        "name": NameObject(text="mydir", hashes=_make_hashset()),
        "extension": None,
        "size": SizeObject(text="0 B", bytes=0),
        "hashes": None,
        "file_system": FileSystemObject(relative="mydir", parent=None),
        "timestamps": _make_timestamps(),
        "attributes": AttributesObject(
            is_link=False,
            storage_name="xABCDEF0123456789ABCDEF0123456789",
        ),
        "items": [],
    }
    defaults.update(overrides)
    return IndexEntry(**defaults)


def _validate(entry: IndexEntry, schema: dict[str, Any]) -> None:
    """Serialize an entry and validate against the v2 schema."""
    json_str = serialize_entry(entry)
    data = json.loads(json_str)
    jsonschema.validate(instance=data, schema=schema)


def _make_metadata_entry_sidecar() -> MetadataEntry:
    return MetadataEntry(
        id="yABCDEF0123456789ABCDEF0123456789",
        origin="sidecar",
        name=NameObject(text="video.description", hashes=_make_hashset()),
        hashes=_make_hashset(),
        attributes=MetadataAttributes(
            type="description",
            format="text",
            transforms=[],
        ),
        data="A description of the video.",
        file_system=FileSystemObject(relative="video.description", parent=None),
        size=SizeObject(text="27 B", bytes=27),
        timestamps=_make_timestamps(),
    )


def _make_metadata_entry_generated() -> MetadataEntry:
    return MetadataEntry(
        id="zABCDEF0123456789ABCDEF0123456789",
        origin="generated",
        name=NameObject(text=None, hashes=None),
        hashes=_make_hashset(),
        attributes=MetadataAttributes(
            type="exiftool.json_metadata",
            format="json",
            transforms=["key_filter"],
        ),
        data={"File:MIMEType": "video/mp4", "File:FileSize": 1024},
    )


# ---------------------------------------------------------------------------
# Validation Tests (13 cases)
# ---------------------------------------------------------------------------


class TestFileEntryValidation:
    """Tests for file entry schema validation."""

    def test_file_entry_validates(self, v2_schema: dict[str, Any]) -> None:
        """A fully constructed file entry validates against the schema."""
        entry = _make_file_entry()
        _validate(entry, v2_schema)

    def test_file_entry_from_real_file(
        self,
        sample_file: Path,
        mock_exiftool: None,
        v2_schema: dict[str, Any],
    ) -> None:
        """IndexEntry from a real file validates against the schema."""
        config = _cfg()
        entry = index_path(sample_file, config)
        _validate(entry, v2_schema)


class TestDirectoryEntryValidation:
    """Tests for directory entry schema validation."""

    def test_directory_entry_validates(self, v2_schema: dict[str, Any]) -> None:
        """A directory entry with empty items validates."""
        entry = _make_dir_entry(items=[])
        _validate(entry, v2_schema)


class TestRecursiveEntryValidation:
    """Tests for recursive (nested) entry validation."""

    def test_recursive_entry_validates(
        self,
        sample_tree: Path,
        mock_exiftool: None,
        v2_schema: dict[str, Any],
    ) -> None:
        """A recursively indexed directory validates against the schema."""
        config = _cfg()
        entry = build_directory_entry(sample_tree, config, recursive=True)
        _validate(entry, v2_schema)


class TestSymlinkEntryValidation:
    """Tests for symlink entry validation."""

    @pytest.mark.skipif(
        sys.platform == "win32" and not os.environ.get("CI"),
        reason="Symlink creation may require elevated privileges on Windows",
    )
    def test_symlink_entry_validates(
        self,
        tmp_path: Path,
        mock_exiftool: None,
        v2_schema: dict[str, Any],
    ) -> None:
        """A symlink file entry validates against the schema."""
        target = tmp_path / "real.txt"
        target.write_text("content", encoding="utf-8")
        link = tmp_path / "link.txt"
        link.symlink_to(target)

        config = _cfg()
        entry = build_file_entry(link, config)
        _validate(entry, v2_schema)


class TestOptionalFieldsValidation:
    """Tests for null/absent optional fields."""

    def test_all_null_optional_fields_validate(
        self, v2_schema: dict[str, Any],
    ) -> None:
        """Entry with all optional fields set to None validates."""
        entry = _make_file_entry(
            items=None, metadata=None, mime_type=None,
        )
        _validate(entry, v2_schema)


class TestMetadataEntryValidation:
    """Tests for MetadataEntry validation."""

    def test_sidecar_metadata_entry_validates(
        self, v2_schema: dict[str, Any],
    ) -> None:
        """A sidecar MetadataEntry validates within a file entry."""
        meta = _make_metadata_entry_sidecar()
        entry = _make_file_entry(metadata=[meta])
        _validate(entry, v2_schema)

    def test_generated_metadata_entry_validates(
        self, v2_schema: dict[str, Any],
    ) -> None:
        """A generated MetadataEntry validates within a file entry."""
        meta = _make_metadata_entry_generated()
        entry = _make_file_entry(metadata=[meta])
        _validate(entry, v2_schema)


class TestMinimalEntry:
    """Tests for minimal entries."""

    def test_minimal_file_entry_validates(
        self, v2_schema: dict[str, Any],
    ) -> None:
        """A file entry with only required fields validates."""
        entry = _make_file_entry()
        _validate(entry, v2_schema)


class TestSchemaRejections:
    """Tests for schema rejection of invalid entries."""

    def test_extra_fields_rejected(self, v2_schema: dict[str, Any]) -> None:
        """additionalProperties: false rejects unexpected fields."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        data["unexpected_field"] = "should fail"

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v2_schema)

    def test_wrong_schema_version_rejected(
        self, v2_schema: dict[str, Any],
    ) -> None:
        """schema_version != 2 is rejected by the const constraint."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        data["schema_version"] = 1

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v2_schema)

    def test_required_field_missing_rejected(
        self, v2_schema: dict[str, Any],
    ) -> None:
        """Removing a required field causes validation failure."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        del data["id"]

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v2_schema)


class TestHashSetPatterns:
    """Tests for hash pattern enforcement."""

    def test_invalid_md5_pattern_rejected(
        self, v2_schema: dict[str, Any],
    ) -> None:
        """MD5 with wrong length/chars is rejected by the schema pattern."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        data["hashes"]["md5"] = "invalid"

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v2_schema)


# ---------------------------------------------------------------------------
# Serialization Invariants (4 cases)
# ---------------------------------------------------------------------------


class TestSerializationInvariants:
    """Tests for the 4 serialization invariants from §5.12."""

    def test_key_ordering_schema_version_first(self) -> None:
        """schema_version is always the first key in serialized output."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        parsed = json.loads(json_str)
        first_key = next(iter(parsed))
        assert first_key == "schema_version"

    def test_sha512_omitted_when_not_computed(self) -> None:
        """sha512 key is absent (not null) when not computed."""
        entry = _make_file_entry(hashes=_make_hashset(sha512=None))
        json_str = serialize_entry(entry)
        parsed = json.loads(json_str)
        assert "sha512" not in parsed["hashes"]

    def test_unicode_preservation(self) -> None:
        """Non-ASCII characters are preserved verbatim, not escaped."""
        entry = _make_file_entry(
            name=NameObject(text="文件.txt", hashes=_make_hashset()),
        )
        json_str = serialize_entry(entry)
        assert "文件" in json_str
        assert "\\u" not in json_str.split('"文件')[0][-5:]  # No unicode escapes nearby

    def test_null_items_vs_absent(self) -> None:
        """File entries have items=null in output (present as null, not absent)."""
        entry = _make_file_entry(items=None, metadata=None)
        json_str = serialize_entry(entry)
        parsed = json.loads(json_str)
        # items and metadata should be present as null for file entries.
        assert "items" in parsed
        assert parsed["items"] is None
        assert "metadata" in parsed
        assert parsed["metadata"] is None

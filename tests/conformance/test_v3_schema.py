"""Output schema conformance tests for v3 — §14.4.

Validates that generated ``IndexEntry`` objects (serialized to JSON) conform
to ``docs/schema/shruggie-indexer-v3.schema.json``.

Covers:
- File and directory entries with v3 fields (encoding, created_source)
- Metadata entries with encoding and json_indent
- Backward incompatibility: v2 entries rejected by v3 schema (schema_version const)
- Schema rejection of invalid v3-specific field values
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.entry import index_path
from shruggie_indexer.core.serializer import serialize_entry
from shruggie_indexer.models.schema import (
    AttributesObject,
    EncodingObject,
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

_V3_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "schema"
    / "shruggie-indexer-v3.schema.json"
)

_V2_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "schema"
    / "shruggie-indexer-v2.schema.json"
)


@pytest.fixture(scope="module")
def v3_schema() -> dict[str, Any]:
    """Load the v3 JSON Schema once per module."""
    return json.loads(_V3_SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def v2_schema() -> dict[str, Any]:
    """Load the v2 JSON Schema once per module."""
    return json.loads(_V2_SCHEMA_PATH.read_text(encoding="utf-8"))


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


def _make_timestamps(
    created_source: str | None = "birthtime",
) -> TimestampsObject:
    pair = TimestampPair(iso="2024-01-01T00:00:00.000000+00:00", unix=1704067200000)
    return TimestampsObject(
        created=pair, modified=pair, accessed=pair,
        created_source=created_source,
    )


def _make_file_entry(**overrides: Any) -> IndexEntry:
    defaults: dict[str, Any] = {
        "schema_version": 3,
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
        "schema_version": 3,
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
    """Serialize an entry and validate against the given schema."""
    json_str = serialize_entry(entry)
    data = json.loads(json_str)
    jsonschema.validate(instance=data, schema=schema)


def _make_metadata_entry_sidecar(
    *,
    encoding: EncodingObject | None = None,
    json_style: str | None = None,
    json_indent: str | None = None,
) -> MetadataEntry:
    return MetadataEntry(
        id="yABCDEF0123456789ABCDEF0123456789",
        origin="sidecar",
        name=NameObject(text="video.description", hashes=_make_hashset()),
        hashes=_make_hashset(),
        attributes=MetadataAttributes(
            type="description",
            format="text",
            transforms=[],
            json_style=json_style,
            json_indent=json_indent,
        ),
        data="A description of the video.",
        file_system=FileSystemObject(relative="video.description", parent=None),
        size=SizeObject(text="27 B", bytes=27),
        timestamps=_make_timestamps(),
        encoding=encoding,
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
# v3 Validation Tests
# ---------------------------------------------------------------------------


class TestV3FileEntryValidation:
    """Tests for v3 file entry schema validation."""

    def test_file_entry_validates(self, v3_schema: dict[str, Any]) -> None:
        """A fully constructed v3 file entry validates against the schema."""
        entry = _make_file_entry()
        _validate(entry, v3_schema)

    def test_file_entry_with_encoding_validates(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """A v3 file entry with encoding (BOM + line endings) validates."""
        enc = EncodingObject(bom="utf-8", line_endings="crlf")
        entry = _make_file_entry(encoding=enc)
        _validate(entry, v3_schema)

    def test_file_entry_with_full_encoding_validates(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """A v3 file entry with all encoding fields validates."""
        enc = EncodingObject(
            bom="utf-8",
            line_endings="crlf",
            detected_encoding="utf-8",
            confidence=0.99,
        )
        entry = _make_file_entry(encoding=enc)
        _validate(entry, v3_schema)

    def test_file_entry_without_encoding_validates(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """A v3 file entry without encoding (binary file) validates."""
        entry = _make_file_entry(encoding=None)
        _validate(entry, v3_schema)

    def test_file_entry_from_real_file(
        self,
        sample_file: Path,
        mock_exiftool: None,
        v3_schema: dict[str, Any],
    ) -> None:
        """IndexEntry from a real file validates against the v3 schema."""
        config = _cfg()
        entry = index_path(sample_file, config)
        _validate(entry, v3_schema)


class TestV3DirectoryEntryValidation:
    """Tests for v3 directory entry schema validation."""

    def test_directory_entry_validates(self, v3_schema: dict[str, Any]) -> None:
        """A v3 directory entry with empty items validates."""
        entry = _make_dir_entry(items=[])
        _validate(entry, v3_schema)


class TestV3CreatedSourceValidation:
    """Tests for created_source field in TimestampsObject."""

    def test_entry_with_birthtime_validates(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """An entry with created_source='birthtime' validates."""
        entry = _make_file_entry(
            timestamps=_make_timestamps(created_source="birthtime"),
        )
        _validate(entry, v3_schema)

    def test_entry_with_ctime_fallback_validates(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """An entry with created_source='ctime_fallback' validates."""
        entry = _make_file_entry(
            timestamps=_make_timestamps(created_source="ctime_fallback"),
        )
        _validate(entry, v3_schema)

    def test_entry_without_created_source_validates(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """An entry without created_source still validates (optional)."""
        entry = _make_file_entry(
            timestamps=_make_timestamps(created_source=None),
        )
        _validate(entry, v3_schema)

    def test_real_file_entry_has_created_source(
        self,
        sample_file: Path,
        mock_exiftool: None,
        v3_schema: dict[str, Any],
    ) -> None:
        """IndexEntry from index_path() has timestamps.created_source."""
        config = _cfg()
        entry = index_path(sample_file, config)

        assert entry.timestamps.created_source is not None
        assert entry.timestamps.created_source in ("birthtime", "ctime_fallback")
        _validate(entry, v3_schema)


class TestV3MetadataEntryValidation:
    """Tests for MetadataEntry with v3 fields."""

    def test_sidecar_with_encoding_validates(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """A sidecar MetadataEntry with encoding validates."""
        enc = EncodingObject(bom="utf-8", line_endings="lf")
        meta = _make_metadata_entry_sidecar(encoding=enc)
        entry = _make_file_entry(metadata=[meta])
        _validate(entry, v3_schema)

    def test_sidecar_with_json_indent_validates(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """A sidecar MetadataEntry with json_indent validates."""
        meta = MetadataEntry(
            id="yABCDEF0123456789ABCDEF0123456789",
            origin="sidecar",
            name=NameObject(text="video.info.json", hashes=_make_hashset()),
            hashes=_make_hashset(),
            attributes=MetadataAttributes(
                type="json_metadata",
                format="json",
                transforms=[],
                json_style="pretty",
                json_indent="    ",
            ),
            data={"title": "Test Video"},
            file_system=FileSystemObject(relative="video.info.json", parent=None),
            size=SizeObject(text="42 B", bytes=42),
            timestamps=_make_timestamps(),
        )
        entry = _make_file_entry(metadata=[meta])
        _validate(entry, v3_schema)

    def test_sidecar_without_encoding_validates(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """A sidecar MetadataEntry without encoding validates."""
        meta = _make_metadata_entry_sidecar(encoding=None)
        entry = _make_file_entry(metadata=[meta])
        _validate(entry, v3_schema)

    def test_generated_metadata_validates(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """A generated MetadataEntry validates within a v3 file entry."""
        meta = _make_metadata_entry_generated()
        entry = _make_file_entry(metadata=[meta])
        _validate(entry, v3_schema)


# ---------------------------------------------------------------------------
# Backward Compatibility Tests
# ---------------------------------------------------------------------------


class TestV2IncompatibleWithV3:
    """Confirm that v2 entries fail validation against the v3 schema."""

    def test_v2_schema_version_rejected_by_v3(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """schema_version: 2 fails the v3 schema const: 3 constraint."""
        entry = _make_file_entry(schema_version=2)
        json_str = serialize_entry(entry)
        data = json.loads(json_str)

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v3_schema)


class TestV3IncompatibleWithV2:
    """Confirm that v3 entries fail validation against the v2 schema."""

    def test_v3_schema_version_rejected_by_v2(
        self, v2_schema: dict[str, Any],
    ) -> None:
        """schema_version: 3 fails the v2 schema const: 2 constraint."""
        entry = _make_file_entry(schema_version=3)
        json_str = serialize_entry(entry)
        data = json.loads(json_str)

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v2_schema)

    def test_v3_entry_with_encoding_rejected_by_v2(
        self, v2_schema: dict[str, Any],
    ) -> None:
        """A v3 entry with encoding is rejected by v2 (additionalProperties)."""
        enc = EncodingObject(bom="utf-8", line_endings="crlf")
        entry = _make_file_entry(encoding=enc)
        json_str = serialize_entry(entry)
        data = json.loads(json_str)

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v2_schema)


# ---------------------------------------------------------------------------
# Schema Rejection Tests
# ---------------------------------------------------------------------------


class TestV3SchemaRejections:
    """Tests for v3 schema rejection of invalid fields."""

    def test_extra_fields_rejected(self, v3_schema: dict[str, Any]) -> None:
        """additionalProperties: false rejects unexpected fields."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        data["unexpected_field"] = "should fail"

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v3_schema)

    def test_invalid_bom_enum_rejected(self, v3_schema: dict[str, Any]) -> None:
        """An invalid bom enum value is rejected."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        data["encoding"] = {"bom": "invalid-bom"}

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v3_schema)

    def test_invalid_line_endings_enum_rejected(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """An invalid line_endings enum value is rejected."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        data["encoding"] = {"line_endings": "windows"}

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v3_schema)

    def test_invalid_created_source_enum_rejected(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """An invalid created_source enum value is rejected."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        data["timestamps"]["created_source"] = "invalid"

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v3_schema)

    def test_encoding_additional_properties_rejected(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """Extra properties in EncodingObject are rejected."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        data["encoding"] = {"bom": "utf-8", "extra_field": "bad"}

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v3_schema)

    def test_confidence_out_of_range_rejected(
        self, v3_schema: dict[str, Any],
    ) -> None:
        """Confidence > 1.0 is rejected."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        data["encoding"] = {"confidence": 1.5}

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=v3_schema)


# ---------------------------------------------------------------------------
# Serialization Invariant Tests
# ---------------------------------------------------------------------------


class TestV3SerializationInvariants:
    """Verify serialization invariants hold for v3 output."""

    def test_schema_version_is_first_key(self, v3_schema: dict[str, Any]) -> None:
        """schema_version is the first key in serialized output."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        assert list(data.keys())[0] == "schema_version"

    def test_encoding_key_position(self, v3_schema: dict[str, Any]) -> None:
        """encoding appears after attributes in serialized output."""
        enc = EncodingObject(bom="utf-8", line_endings="lf")
        entry = _make_file_entry(encoding=enc)
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        keys = list(data.keys())
        assert "encoding" in keys
        attrs_idx = keys.index("attributes")
        enc_idx = keys.index("encoding")
        assert enc_idx > attrs_idx

    def test_sha512_omitted_not_null(self, v3_schema: dict[str, Any]) -> None:
        """sha512 absent (not null) when not computed."""
        entry = _make_file_entry()
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        assert "sha512" not in data["hashes"]

    def test_encoding_absent_when_none(self, v3_schema: dict[str, Any]) -> None:
        """encoding key is absent (not null) when no encoding detected."""
        entry = _make_file_entry(encoding=None)
        json_str = serialize_entry(entry)
        data = json.loads(json_str)
        assert "encoding" not in data

    def test_unicode_preservation(self, v3_schema: dict[str, Any]) -> None:
        """Non-ASCII characters are preserved (ensure_ascii=False)."""
        entry = _make_file_entry(
            name=NameObject(text="日本語.txt", hashes=_make_hashset()),
        )
        json_str = serialize_entry(entry)
        assert "日本語" in json_str

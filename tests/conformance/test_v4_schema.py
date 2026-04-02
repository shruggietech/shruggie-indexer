"""Output schema conformance tests for v4."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

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
    PredicateResult,
    RelationshipAnnotation,
    SizeObject,
    TimestampPair,
    TimestampsObject,
)

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "schema"
    / "shruggie-indexer-v4.schema.json"
)


@pytest.fixture(scope="module")
def v4_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _make_hashset() -> HashSet:
    return HashSet(
        md5="D41D8CD98F00B204E9800998ECF8427E",
        sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
    )


def _make_timestamps() -> TimestampsObject:
    pair = TimestampPair(iso="2024-01-01T00:00:00.000000+00:00", unix=1704067200000)
    return TimestampsObject(created=pair, modified=pair, accessed=pair)


def _make_entry(**overrides: Any) -> IndexEntry:
    defaults: dict[str, Any] = {
        "id": "yD41D8CD98F00B204E9800998ECF8427E",
        "id_algorithm": "md5",
        "type": "file",
        "name": NameObject(text="video.info.json", hashes=_make_hashset()),
        "extension": "json",
        "size": SizeObject(text="0 B", bytes=0),
        "hashes": _make_hashset(),
        "file_system": FileSystemObject(
            relative="video.info.json",
            parent=ParentObject(
                id="xABCDEF0123456789ABCDEF0123456789",
                name=NameObject(text="root", hashes=_make_hashset()),
            ),
        ),
        "timestamps": _make_timestamps(),
        "attributes": AttributesObject(is_link=False, storage_name="yD41D8C.json"),
    }
    defaults.update(overrides)
    return IndexEntry(**defaults)


def _validate(entry: IndexEntry, schema: dict[str, Any]) -> None:
    payload = json.loads(serialize_entry(entry))
    jsonschema.validate(instance=payload, schema=schema)


def test_file_entry_validates_v4(v4_schema: dict[str, Any]) -> None:
    _validate(_make_entry(), v4_schema)


def test_relationships_validate_v4(v4_schema: dict[str, Any]) -> None:
    rel = RelationshipAnnotation(
        target_id="yTARGET123",
        type="json_metadata",
        rule="yt-dlp-info",
        rule_source="builtin",
        confidence=3,
        predicates=[PredicateResult(name="match", satisfied=True)],
    )
    _validate(_make_entry(relationships=[rel]), v4_schema)


def test_metadata_entry_simplified_fields_validate(v4_schema: dict[str, Any]) -> None:
    meta = MetadataEntry(
        id="zABCDEF0123456789ABCDEF0123456789",
        origin="generated",
        name=NameObject(text=None, hashes=None),
        hashes=_make_hashset(),
        attributes=MetadataAttributes(
            type="exiftool.json_metadata",
            format="json",
            transforms=["key_filter"],
        ),
        data={"File:MIMEType": "application/json"},
    )
    _validate(_make_entry(metadata=[meta]), v4_schema)

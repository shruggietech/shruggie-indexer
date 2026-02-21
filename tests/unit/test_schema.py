"""Unit tests for models/schema.py — §5 Output Schema dataclasses.

5 test cases per §14.2.
"""

from __future__ import annotations

from typing import Any

import pytest

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


def _make_hashset() -> HashSet:
    return HashSet(
        md5="D41D8CD98F00B204E9800998ECF8427E",
        sha256="E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
    )


def _make_name_object() -> NameObject:
    return NameObject(text="sunset.jpg", hashes=_make_hashset())


def _make_timestamps() -> TimestampsObject:
    pair = TimestampPair(iso="2024-01-01T00:00:00.000000+00:00", unix=1704067200000)
    return TimestampsObject(created=pair, modified=pair, accessed=pair)


def _make_index_entry(**overrides: Any) -> IndexEntry:
    defaults: dict[str, Any] = {
        "schema_version": 2,
        "id": "yD41D8CD98F00B204E9800998ECF8427E",
        "id_algorithm": "md5",
        "type": "file",
        "name": _make_name_object(),
        "extension": "jpg",
        "size": SizeObject(text="0 B", bytes=0),
        "hashes": _make_hashset(),
        "file_system": FileSystemObject(relative="photos/sunset.jpg", parent=None),
        "timestamps": _make_timestamps(),
        "attributes": AttributesObject(is_link=False, storage_name="yD41D.jpg"),
    }
    defaults.update(overrides)
    return IndexEntry(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIndexEntryConstruction:
    """Tests for IndexEntry dataclass construction."""

    def test_index_entry_construction(self) -> None:
        """All required fields provided -> object created, fields accessible."""
        entry = _make_index_entry()
        assert entry.schema_version == 2
        assert entry.id.startswith("y")
        assert entry.type == "file"
        assert entry.name.text == "sunset.jpg"
        assert entry.extension == "jpg"
        assert entry.items is None
        assert entry.metadata is None

    def test_index_entry_missing_required_field(self) -> None:
        """Omitting a required field raises TypeError."""
        with pytest.raises(TypeError):
            IndexEntry(  # type: ignore[call-arg]
                schema_version=2,
                id="y123",
                # id_algorithm missing
                type="file",
                name=_make_name_object(),
                extension="jpg",
                size=SizeObject(text="0 B", bytes=0),
                hashes=_make_hashset(),
                file_system=FileSystemObject(relative="a.txt", parent=None),
                timestamps=_make_timestamps(),
                attributes=AttributesObject(is_link=False, storage_name="y123.jpg"),
            )


class TestHashSetUppercase:
    """Tests for the uppercase hex invariant."""

    def test_hashset_uppercase_invariant(self) -> None:
        """HashSet stores values as-is; callers must supply uppercase.

        This test documents the contract: the hashing module is responsible
        for producing uppercase hex, and the dataclass stores what it receives.
        """
        hs = HashSet(md5="ABCDEF0123456789" * 2, sha256="ABCDEF0123456789" * 4)
        assert all(c in "0123456789ABCDEF" for c in hs.md5)
        assert all(c in "0123456789ABCDEF" for c in hs.sha256)


class TestToDict:
    """Tests for to_dict() serialization."""

    def test_to_dict_round_trip(self) -> None:
        """to_dict() produces a valid dict with nested objects serialized."""
        entry = _make_index_entry()
        d = entry.to_dict()
        assert isinstance(d, dict)
        assert d["schema_version"] == 2
        assert isinstance(d["name"], dict)
        assert d["name"]["text"] == "sunset.jpg"
        assert isinstance(d["hashes"], dict)
        assert "md5" in d["hashes"]
        assert isinstance(d["timestamps"]["created"], dict)

    def test_schema_version_first_key(self) -> None:
        """schema_version is the first key in the to_dict() output."""
        entry = _make_index_entry()
        d = entry.to_dict()
        keys = list(d.keys())
        assert keys[0] == "schema_version"
        assert d["schema_version"] == 2


class TestNameObjectCoNull:
    """Tests for the NameObject co-nullability invariant."""

    def test_name_object_co_null_valid(self) -> None:
        """Both None or both populated is valid."""
        assert NameObject(text=None, hashes=None).text is None
        assert NameObject(text="a", hashes=_make_hashset()).text == "a"

    def test_name_object_co_null_invalid(self) -> None:
        """One None and one non-None raises ValueError."""
        with pytest.raises(ValueError, match="co-null"):
            NameObject(text="a", hashes=None)
        with pytest.raises(ValueError, match="co-null"):
            NameObject(text=None, hashes=_make_hashset())

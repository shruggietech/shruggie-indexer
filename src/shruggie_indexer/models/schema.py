"""Data models for shruggie-indexer v2/v3 schema output.

These dataclasses are the Python representation of the types defined in the
JSON Schema (docs/schema/). Each class maps directly to a schema ``$ref``
definition or to the root ``IndexEntry`` type.

See spec sections 5.2-5.10 and 9.4 for full behavioral guidance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "AttributesObject",
    "EncodingObject",
    "FileSystemObject",
    "HashSet",
    "IndexEntry",
    "MetadataAttributes",
    "MetadataEntry",
    "NameObject",
    "ParentObject",
    "SizeObject",
    "TimestampPair",
    "TimestampsObject",
]


# ---------------------------------------------------------------------------
# Reusable type definitions (§5.2)
# ---------------------------------------------------------------------------


@dataclass
class HashSet:
    """Cryptographic hash digests (§5.2.1).

    All hash values are uppercase hexadecimal strings.  ``sha512`` is optional
    and included only when the indexer is configured to compute it.
    """

    md5: str
    """MD5 digest — 32 uppercase hex characters."""

    sha256: str
    """SHA-256 digest — 64 uppercase hex characters."""

    sha512: str | None = None
    """SHA-512 digest — 128 uppercase hex characters. Optional."""

    def to_dict(self) -> dict[str, str]:
        """Serialize to a JSON-ready dict, omitting *sha512* when ``None``."""
        d: dict[str, str] = {"md5": self.md5, "sha256": self.sha256}
        if self.sha512 is not None:
            d["sha512"] = self.sha512
        return d


@dataclass
class NameObject:
    """Name with associated hash digests (§5.2.2).

    ``text`` and ``hashes`` are co-null: both must be ``None`` or both must be
    populated.
    """

    text: str | None
    """The text value of the name, or ``None``."""

    hashes: HashSet | None
    """Hash digests of the UTF-8 bytes of *text*, or ``None``."""

    def __post_init__(self) -> None:
        """Enforce co-nullability invariant."""
        if (self.text is None) != (self.hashes is None):
            raise ValueError("NameObject.text and .hashes must be co-null")

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "hashes": self.hashes.to_dict() if self.hashes is not None else None,
        }


@dataclass
class SizeObject:
    """File size in human-readable and machine-readable forms (§5.2.3).

    Uses decimal SI units: B, KB, MB, GB, TB.
    """

    text: str
    """Human-readable size string (e.g. ``'15.28 MB'``)."""

    bytes: int
    """Exact size in bytes."""

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "bytes": self.bytes}


@dataclass
class TimestampPair:
    """Single timestamp in ISO 8601 and Unix millisecond forms (§5.2.4)."""

    iso: str
    """ISO 8601 timestamp with fractional seconds and timezone offset."""

    unix: int
    """Milliseconds since epoch (1970-01-01T00:00:00Z)."""

    def to_dict(self) -> dict[str, Any]:
        return {"iso": self.iso, "unix": self.unix}


@dataclass
class TimestampsObject:
    """Three standard filesystem timestamps (§5.2.5)."""

    created: TimestampPair
    modified: TimestampPair
    accessed: TimestampPair

    created_source: str | None = None
    """Provenance of the created timestamp (§15.5).

    Values: "birthtime" (true creation time from st_birthtime),
            "ctime_fallback" (inode change time from st_ctime).
    None for v2-compatibility or when source is unknown.
    """

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "created": self.created.to_dict(),
            "modified": self.modified.to_dict(),
            "accessed": self.accessed.to_dict(),
        }
        if self.created_source is not None:
            d["created_source"] = self.created_source
        return d


@dataclass
class EncodingObject:
    """File encoding metadata for hash-perfect reversal (§5.2.8).

    Captures the byte-level encoding characteristics that are lost when
    raw file bytes are decoded into Python text strings. All fields are
    optional; the object is omitted entirely when no encoding detection
    was performed.
    """

    bom: str | None = None
    """Detected BOM type identifier, or None if no BOM was present.

    Values: "utf-8", "utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be".
    The identifier maps deterministically to the original BOM byte sequence:
      utf-8     \u2192 EF BB BF
      utf-16-le \u2192 FF FE
      utf-16-be \u2192 FE FF
      utf-32-le \u2192 FF FE 00 00
      utf-32-be \u2192 00 00 FE FF
    """

    line_endings: str | None = None
    """Detected line-ending style, or None for binary/unknown files.

    Values: "lf", "crlf", "mixed".
    "mixed" indicates the file contains both bare LF and CRLF sequences.
    """

    detected_encoding: str | None = None
    """Best-guess encoding name from chardet.

    Python codec name (e.g., "utf-8", "ascii", "windows-1252", "shift_jis").
    None when encoding detection was not performed or inconclusive.
    """

    confidence: float | None = None
    """Detection confidence score (0.0 to 1.0).

    Accompanies detected_encoding. None when detected_encoding is None.
    """

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.bom is not None:
            d["bom"] = self.bom
        if self.line_endings is not None:
            d["line_endings"] = self.line_endings
        if self.detected_encoding is not None:
            d["detected_encoding"] = self.detected_encoding
        if self.confidence is not None:
            d["confidence"] = self.confidence
        return d


@dataclass
class ParentObject:
    """Parent directory identity and name (§5.2.6)."""

    id: str
    """``x``-prefixed directory ID."""

    name: NameObject

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name.to_dict()}


# ---------------------------------------------------------------------------
# Composite field objects
# ---------------------------------------------------------------------------


@dataclass
class FileSystemObject:
    """Filesystem location and hierarchy (§5.6)."""

    relative: str
    """Forward-slash-separated relative path from the index root."""

    parent: ParentObject | None
    """Parent directory info, or ``None`` for root of single-file index."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative": self.relative,
            "parent": self.parent.to_dict() if self.parent is not None else None,
        }


@dataclass
class AttributesObject:
    """Item attributes (§5.8)."""

    is_link: bool
    """Whether the item is a symbolic link."""

    storage_name: str
    """Deterministic name for renamed/storage mode."""

    def to_dict(self) -> dict[str, Any]:
        return {"is_link": self.is_link, "storage_name": self.storage_name}


# ---------------------------------------------------------------------------
# Metadata structures (§5.10)
# ---------------------------------------------------------------------------


@dataclass
class MetadataAttributes:
    """Classification and format info for a MetadataEntry (§5.10)."""

    type: str
    """Semantic classification (e.g. ``'exiftool.json_metadata'``, ``'description'``)."""

    format: str
    """Serialization format of the ``data`` field.

    One of ``'json'``, ``'text'``, ``'base64'``, or ``'lines'``.
    """

    transforms: list[str]
    """Ordered list of transformations applied to source data."""

    source_media_type: str | None = None
    """MIME type of original source data before transforms."""

    json_style: str | None = None
    """Original JSON formatting style: ``'compact'`` or ``'pretty'``.

    Recorded at ingest for sidecar-origin JSON entries so that rollback
    can restore the file with matching formatting intent.  ``None`` for
    non-JSON formats or legacy entries (treated as ``'compact'``).
    """

    json_indent: str | None = None
    """Original JSON indentation string.

    The literal whitespace string used for one level of indentation in the
    original file. Common values: "  " (2 spaces), "    " (4 spaces),
    "\\t" (tab). None for compact JSON, non-JSON formats, or when the
    indent could not be determined. Used by the rollback engine to
    reproduce the original indentation.

    When json_style is "compact", this field MUST be None.
    When json_style is "pretty" and this field is None, the rollback
    engine defaults to 2-space indent for backward compatibility.
    """

    link_metadata: dict[str, str] | None = None
    """Structured metadata extracted from ``.lnk`` binary shortcut files.

    Contains fields such as ``target_path``, ``working_directory``,
    ``arguments``, ``icon_location``, ``description``, and ``hotkey``.
    Only populated for sidecar type ``'shortcut'``.
    """

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "format": self.format,
            "transforms": list(self.transforms),
        }
        if self.source_media_type is not None:
            d["source_media_type"] = self.source_media_type
        if self.json_style is not None:
            d["json_style"] = self.json_style
        if self.json_indent is not None:
            d["json_indent"] = self.json_indent
        if self.link_metadata is not None:
            d["link_metadata"] = dict(self.link_metadata)
        return d


@dataclass
class MetadataEntry:
    """A single metadata record associated with an IndexEntry (§5.10)."""

    id: str
    """``z``-prefixed (generated) or ``y``-prefixed (sidecar)."""

    origin: str
    """``'generated'`` or ``'sidecar'``."""

    name: NameObject
    hashes: HashSet
    attributes: MetadataAttributes
    data: Any
    """Metadata content — JSON object, string, array, or ``None``."""

    # Sidecar-only fields (absent for generated entries)
    file_system: FileSystemObject | None = None
    size: SizeObject | None = None
    timestamps: TimestampsObject | None = None

    encoding: EncodingObject | None = None
    """Encoding metadata for sidecar files (sidecar-only).

    Present for sidecar entries with text-format data. Absent for generated
    entries and binary-format sidecars. Enables hash-perfect reversal of
    the sidecar's text content back to original bytes.
    """

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "origin": self.origin,
            "name": self.name.to_dict(),
            "hashes": self.hashes.to_dict(),
            "attributes": self.attributes.to_dict(),
            "data": self.data,
        }
        if self.file_system is not None:
            # MetadataEntry file_system only includes "relative" per the v2
            # schema (no "parent" — the parent is always the owning item's
            # parent and would be redundant).
            d["file_system"] = {"relative": self.file_system.relative}
        if self.size is not None:
            d["size"] = self.size.to_dict()
        if self.timestamps is not None:
            d["timestamps"] = self.timestamps.to_dict()
        if self.encoding is not None:
            enc_dict = self.encoding.to_dict()
            if enc_dict:
                d["encoding"] = enc_dict
        return d


# ---------------------------------------------------------------------------
# Root entry (§5.3)
# ---------------------------------------------------------------------------


@dataclass
class IndexEntry:
    """A single indexed file or directory (v2 schema).

    All fields listed in §5.3 are present.  Required schema fields have no
    default value; optional fields (``items``, ``metadata``, ``mime_type``)
    default to ``None``.
    """

    schema_version: int
    """Schema version: ``3`` for v3, ``2`` for legacy."""

    id: str
    """Prefixed hash: ``y…`` (file), ``x…`` (directory)."""

    id_algorithm: str
    """``'md5'`` or ``'sha256'``."""

    type: str
    """``'file'`` or ``'directory'``."""

    name: NameObject
    extension: str | None
    size: SizeObject
    hashes: HashSet | None
    """Content hashes (file) or ``None`` (directory)."""

    file_system: FileSystemObject
    timestamps: TimestampsObject
    attributes: AttributesObject

    items: list[IndexEntry] | None = None
    """Children (directory) or ``None`` (file)."""

    metadata: list[MetadataEntry] | None = None
    """Metadata entries or ``None``."""

    duplicates: list[IndexEntry] | None = None
    """Complete IndexEntry objects for files de-duplicated against this entry."""

    mime_type: str | None = None

    encoding: EncodingObject | None = None
    """File encoding metadata for hash-perfect reversal.

    Present for files where encoding detection was performed.
    None for directories, binary files, or when detection is disabled.
    """

    session_id: str | None = None
    """UUID4 identifying the indexing session that produced this entry."""

    indexed_at: TimestampPair | None = None
    """Timestamp when this entry was constructed by the indexer."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-ready dict.

        Field ordering follows the canonical schema: ``schema_version`` is
        placed first for readability.
        """
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "id": self.id,
            "id_algorithm": self.id_algorithm,
            "type": self.type,
            "name": self.name.to_dict(),
            "extension": self.extension,
            "mime_type": self.mime_type,
            "size": self.size.to_dict(),
            "hashes": self.hashes.to_dict() if self.hashes is not None else None,
            "file_system": self.file_system.to_dict(),
            "timestamps": self.timestamps.to_dict(),
            "attributes": self.attributes.to_dict(),
            "items": (
                [item.to_dict() for item in self.items] if self.items is not None else None
            ),
            "metadata": (
                [m.to_dict() for m in self.metadata] if self.metadata is not None else None
            ),
        }
        if self.duplicates:
            d["duplicates"] = [dup.to_dict() for dup in self.duplicates]
        if self.schema_version >= 3 and self.encoding is not None:
            enc_dict = self.encoding.to_dict()
            if enc_dict:  # Only include if at least one field is populated
                d["encoding"] = enc_dict
        if self.session_id is not None:
            d["session_id"] = self.session_id
        if self.indexed_at is not None:
            d["indexed_at"] = self.indexed_at.to_dict()
        return d

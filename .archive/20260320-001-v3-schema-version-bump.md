# Sprint: v3 Schema Version Bump

| Field            | Value                                                        |
|------------------|--------------------------------------------------------------|
| **Project**      | shruggie-indexer                                             |
| **Repository**   | `github.com/shruggietech/shruggie-indexer`                   |
| **Author**       | William (ShruggieTech)                                       |
| **Date**         | 2026-03-20                                                   |
| **Target**       | v0.2.0                                                       |
| **Audience**     | AI coding agents (self-contained context for isolated window) |
| **Predecessor**  | Sprint 3.3 (final v0.1.x sprint)                            |

---

## Purpose and Ecosystem Context

The Metadexer catalog module stores ingested file content as semantically searchable text strings in PostgreSQL. During downstream development, a critical gap was identified: when text-format file content is decoded from raw bytes into Python strings (via `path.read_text(encoding="utf-8")` or equivalent), three categories of byte-level information are silently discarded:

1. **Byte Order Mark (BOM):** Python's UTF-8 codec strips a leading `\xef\xbb\xbf` BOM during decode. The original bytes cannot be reconstructed without knowing whether the BOM was present.
2. **Line endings:** Python normalizes `\r\n` to `\n` in text mode. On Windows-originated files, the original CRLF sequences are lost.
3. **Source encoding:** If a file uses a non-UTF-8 encoding (e.g., Windows-1252, Shift_JIS), the mapping from decoded text back to original bytes requires knowing what encoding produced the text.

Without this metadata, hash-perfect reversal (reconstructing the original file bytes from the stored text representation) is impossible for any file that had a BOM, used CRLF line endings, or was encoded in something other than bare UTF-8. This affects both the main indexed files (whose content the catalog stores for search) and ingested sidecar metadata files (whose text content is already stored in the `MetadataEntry.data` field).

This gap cannot be closed by an additive v2 field. The `encoding` field introduces a new top-level object on `IndexEntry` and a new field on `MetadataEntry`, which together constitute a structural addition significant enough to warrant a version bump. The v3 schema also provides an opportunity to promote two additional candidates from §18.2.2 that have matured since the v2 release:

- **`timestamps.created_source`** — Resolves the documented ambiguity (§15.5) about whether `timestamps.created` represents a true creation time or a ctime fallback. This is a new optional field on `TimestampsObject`.
- **`encoding`** — The primary driver for this sprint. A new top-level optional field on `IndexEntry` and a new sidecar-only optional field on `MetadataEntry`, both using the same `EncodingObject` type.

Additionally, the existing `json_style` attribute on `MetadataAttributes` is extended with a companion `json_indent` field to capture the precise indentation string used in the original JSON file. This closes the last significant gap in JSON sidecar reversal fidelity.

The **`type` enum extension** candidate (adding `"symlink"` as a third value) is explicitly deferred. While the v3 bump would be the natural time for this change, it alters the semantic meaning of an existing field and would require reworking symlink handling throughout the traversal, entry construction, and serialization pipelines. The risk and scope are disproportionate to the encoding-focused objective of this sprint. It remains a candidate for a future v4.

---

## Implementation Ordering

The sprint is organized into eight sections with strict dependency ordering. Each section is a self-contained unit of work suitable for a single AI coding agent session.

| Order | Section | Depends on | Rationale |
|-------|---------|------------|-----------|
| 1 | Schema model changes | None | Defines `EncodingObject`, updates `TimestampsObject`, `IndexEntry`, `MetadataEntry`, and `MetadataAttributes`. All subsequent sections depend on these types. |
| 2 | Encoding detection module | §1 | New `core/encoding.py` module implementing BOM detection, line-ending detection, and chardet integration. Consumes `EncodingObject` from §1. |
| 3 | Hashing pipeline integration | §1, §2 | Extends `build_file_entry()` to invoke encoding detection and populate `IndexEntry.encoding`. |
| 4 | Sidecar pipeline integration | §1, §2 | Extends sidecar readers to capture encoding metadata and JSON indent style for text-format sidecars. Populates `MetadataEntry.encoding`. |
| 5 | Rollback engine: encoding-aware restoration | §1 | Updates `_decode_sidecar_data()` and the main file restoration path to consume `encoding` metadata, restoring BOM, line endings, and source encoding during reversal. |
| 6 | Serializer and naming convention | §1 | Updates the serializer to emit `schema_version: 3`, the sidecar filename convention to `_meta3.json`/`_directorymeta3.json`, and the exclusion patterns to match v3 filenames. |
| 7 | v3 JSON Schema and tests | §1–§6 | Creates the canonical v3 JSON Schema file, updates schema conformance tests, and adds encoding detection and rollback unit tests. |
| 8 | Specification, documentation, and changelog | §1–§7 | Reflects all changes into the technical specification, documentation site, and changelog. Always executed last. |

---

## 1. Schema Model Changes

### 1.1. Problem Statement

The v2 schema dataclasses in `models/schema.py` have no representation for file encoding metadata. The `TimestampsObject` has no field indicating the provenance of the creation timestamp. The `MetadataAttributes` type captures `json_style` as a binary compact/pretty distinction but not the specific indentation string needed for hash-perfect JSON reversal. The `schema_version` is hardcoded to `2` throughout the codebase.

### 1.2. Required Changes

**A. New `EncodingObject` dataclass.**

Add a new reusable type definition to `models/schema.py`:

```python
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
      utf-8     → EF BB BF
      utf-16-le → FF FE
      utf-16-be → FE FF
      utf-32-le → FF FE 00 00
      utf-32-be → 00 00 FE FF
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
```

The `to_dict()` method omits all `None` fields. When all four fields are `None`, the result is an empty dict `{}`. The parent serializer (on `IndexEntry` or `MetadataEntry`) MUST omit the `encoding` key entirely when the `EncodingObject` is `None` or when `to_dict()` returns an empty dict.

**B. Update `TimestampsObject` with `created_source`.**

Add an optional field to the existing `TimestampsObject` dataclass:

```python
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
```

Update `TimestampsObject.to_dict()` to conditionally include `created_source`:

```python
def to_dict(self) -> dict[str, Any]:
    d: dict[str, Any] = {
        "created": self.created.to_dict(),
        "modified": self.modified.to_dict(),
        "accessed": self.accessed.to_dict(),
    }
    if self.created_source is not None:
        d["created_source"] = self.created_source
    return d
```

**C. Update `IndexEntry` with `encoding` field and v3 schema version.**

Add an optional `encoding` field to `IndexEntry`:

```python
encoding: EncodingObject | None = None
"""File encoding metadata for hash-perfect reversal.

Present for files where encoding detection was performed.
None for directories, binary files, or when detection is disabled.
"""
```

Update `IndexEntry.to_dict()` to include the encoding field (conditional, like `session_id`):

```python
if self.encoding is not None:
    enc_dict = self.encoding.to_dict()
    if enc_dict:  # Only include if at least one field is populated
        d["encoding"] = enc_dict
```

Update the docstring on `schema_version` from `"""Always ``2``."""` to `"""Schema version: ``3`` for v3, ``2`` for legacy."""`.

Do NOT hardcode the value `3` at the model level. The `schema_version` value is set by the entry construction functions, not by the dataclass default.

**D. Update `MetadataEntry` with `encoding` field.**

Add an optional `encoding` field to `MetadataEntry`, following the same pattern as the existing sidecar-only fields (`file_system`, `size`, `timestamps`):

```python
encoding: EncodingObject | None = None
"""Encoding metadata for sidecar files (sidecar-only).

Present for sidecar entries with text-format data. Absent for generated
entries and binary-format sidecars. Enables hash-perfect reversal of
the sidecar's text content back to original bytes.
"""
```

Update `MetadataEntry.to_dict()` to include encoding (conditional, sidecar-only pattern):

```python
if self.encoding is not None:
    enc_dict = self.encoding.to_dict()
    if enc_dict:
        d["encoding"] = enc_dict
```

**E. Add `json_indent` field to `MetadataAttributes`.**

The existing `json_style` field distinguishes `"pretty"` vs `"compact"` but does not capture the specific indent string. For hash-perfect reversal, the rollback engine needs to know whether the original file used 2-space, 4-space, tab, or another indent convention. Add a companion field:

```python
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
```

Update `MetadataAttributes.to_dict()`:

```python
if self.json_indent is not None:
    d["json_indent"] = self.json_indent
```

**F. Update `__all__` export list.**

Add `"EncodingObject"` to the `__all__` list in `models/schema.py`.

### 1.3. Affected Files

| File | Nature of change |
|------|------------------|
| `src/shruggie_indexer/models/schema.py` | New `EncodingObject` dataclass. Updated `TimestampsObject`, `IndexEntry`, `MetadataEntry`, `MetadataAttributes`. Updated `__all__`. |

### 1.4. Spec References

| Reference | Section |
|-----------|---------|
| Reusable type definitions | §5.2 |
| Top-level IndexEntry fields | §5.3 |
| Timestamp fields | §5.7 |
| MetadataEntry fields | §5.10 |
| MetadataEntry.attributes | §5.10 |
| Candidate v3 additions | §18.2.2 |

### 1.5. Acceptance Criteria

- `EncodingObject` dataclass exists with four optional fields: `bom`, `line_endings`, `detected_encoding`, `confidence`.
- `EncodingObject.to_dict()` omits `None` fields and returns empty dict when all fields are `None`.
- `TimestampsObject` has `created_source` optional field; `to_dict()` conditionally includes it.
- `IndexEntry` has `encoding` optional field; `to_dict()` conditionally includes it when non-null and non-empty.
- `MetadataEntry` has `encoding` optional field; `to_dict()` conditionally includes it when non-null and non-empty.
- `MetadataAttributes` has `json_indent` optional field; `to_dict()` conditionally includes it when non-null.
- All existing unit tests continue to pass (new fields default to `None`, so existing construction is unaffected).

---

## 2. Encoding Detection Module

### 2.1. Chardet Overview

The encoding detection module combines two complementary detection strategies: deterministic byte-pattern matching (manual) and statistical character encoding inference (chardet).

**Manual detection** handles the deterministic, byte-exact signals: BOM presence (a fixed byte-prefix match with zero ambiguity) and line-ending style (literal `\r\n` vs `\n` byte scanning). These are the signals that matter most for hash-perfect reversal, because they represent the specific bytes that Python silently strips or normalizes during text decode. Manual detection of these is trivial and infallible.

**Chardet** handles the statistical, heuristic signal: given a blob of bytes, what character encoding most likely produced them? Chardet is a universal character encoding detector for Python, originally ported from Mozilla Firefox's auto-detection library. The current version (7.x) is a ground-up MIT-licensed rewrite with a 12-stage detection pipeline using BOM detection, structural probing, byte validity filtering, and bigram statistical models. It achieves 98.2% accuracy on 2,510 test files across 99 encodings, and returns a confidence score and detected language with every result. It has zero runtime dependencies and is thread-safe.

Chardet's detection is inherently probabilistic. A Windows-1252 file and an ISO-8859-1 file might contain identical byte sequences for most Western European text. Chardet resolves these ambiguities using language-model statistics, but it still returns a confidence score because the answer is not always certain. For reversal purposes, the chardet result tells a downstream consumer "this file was probably Shift_JIS, not UTF-8" so that the correct codec can be used to re-encode decoded text back to original bytes.

The two strategies are complementary and non-overlapping: manual detection finds BOM and line endings (which chardet does not report as structured fields), while chardet identifies the character encoding (which manual byte inspection cannot do for the general case). Both run against the same raw byte sample.

### 2.2. Problem Statement

No module exists to detect BOM, line endings, or character encoding from raw file bytes.

### 2.3. Required Changes

**A. Create `src/shruggie_indexer/core/encoding.py`.**

This module provides detection functions that operate on raw bytes:

```python
"""File encoding detection for shruggie-indexer.

Detects byte-order marks (BOM), line-ending conventions, and character
encoding of file content. These signals enable downstream consumers to
perform hash-perfect reversal from decoded text back to original file bytes.

Detection has two layers:
- Manual detection: BOM prefix matching and line-ending scanning.
  Deterministic and infallible for the signals it covers.
- Chardet detection: Statistical character encoding inference via the
  chardet library. Probabilistic, with confidence scores.

See spec §6.12 for full behavioral guidance.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from shruggie_indexer.models.schema import EncodingObject

logger = logging.getLogger(__name__)

# BOM byte sequences, ordered longest-first to avoid prefix ambiguity.
# UTF-32 LE starts with FF FE 00 00, which has the same first two bytes
# as UTF-16 LE (FF FE). Checking the longer sequence first prevents
# misidentification.
_BOM_TABLE: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xef\xbb\xbf", "utf-8"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)

# Reverse lookup: BOM identifier → byte sequence. Used by the rollback
# engine to prepend the correct BOM during file restoration.
BOM_BYTES: dict[str, bytes] = {name: bom for bom, name in _BOM_TABLE}
```

**B. BOM detection function.**

```python
def detect_bom(data: bytes) -> str | None:
    """Detect a byte-order mark in the leading bytes of file content.

    Args:
        data: The first 4+ bytes of the file content.

    Returns:
        A BOM identifier string ("utf-8", "utf-16-le", etc.) or None.
    """
    for bom_bytes, bom_name in _BOM_TABLE:
        if data.startswith(bom_bytes):
            return bom_name
    return None
```

**C. Line-ending detection function.**

```python
def detect_line_endings(data: bytes) -> str | None:
    """Detect the line-ending convention used in file content.

    Scans the provided bytes for CR+LF (\\r\\n) and bare LF (\\n)
    sequences. Returns "crlf", "lf", "mixed", or None.

    The scan strips any detected BOM prefix before analysis to avoid
    false positives from BOM bytes that happen to contain 0x0A or 0x0D.

    Args:
        data: Raw file content bytes (or a representative prefix).

    Returns:
        "lf" if only bare LF found, "crlf" if only CR+LF found,
        "mixed" if both styles present, or None if no line endings
        detected (single-line file or binary).
    """
    # Strip BOM prefix if present.
    for bom_bytes, _ in _BOM_TABLE:
        if data.startswith(bom_bytes):
            data = data[len(bom_bytes):]
            break

    has_crlf = b"\r\n" in data
    # Count bare LF: occurrences of \n that are NOT preceded by \r.
    # Replace all \r\n first, then check for remaining \n.
    bare_lf_data = data.replace(b"\r\n", b"")
    has_bare_lf = b"\n" in bare_lf_data

    if has_crlf and has_bare_lf:
        return "mixed"
    if has_crlf:
        return "crlf"
    if has_bare_lf:
        return "lf"
    return None
```

**D. Chardet integration.**

Chardet is a standard runtime dependency (not optional). The import guard is retained as a defensive safety net for edge-case environments where chardet might be missing, but normal operation assumes chardet is installed.

```python
def detect_charset(data: bytes) -> tuple[str | None, float | None]:
    """Detect character encoding using chardet.

    Returns (encoding_name, confidence) or (None, None) if chardet
    is not installed or detection is inconclusive.

    The chardet library uses a 12-stage detection pipeline (BOM
    detection, structural probing, byte validity filtering, bigram
    statistical models) to identify the character encoding of
    arbitrary byte sequences. It covers 99 encodings and achieves
    98.2% accuracy on standard test corpora.

    Args:
        data: Raw file content bytes (or a representative prefix;
              chardet works well with 10 KB+ of data).

    Returns:
        Tuple of (encoding_name, confidence) where encoding_name is
        a Python codec name and confidence is 0.0-1.0, or (None, None).
    """
    try:
        import chardet
    except ImportError:
        logger.warning(
            "chardet is not installed; character encoding detection "
            "is unavailable. Install chardet to enable this feature."
        )
        return None, None

    try:
        result = chardet.detect(data)
    except Exception:  # noqa: BLE001
        logger.debug("chardet detection failed", exc_info=True)
        return None, None

    encoding = result.get("encoding")
    confidence = result.get("confidence")

    if encoding is None:
        return None, None

    # Normalize encoding name to Python codec name (lowercase).
    return encoding.lower(), confidence
```

**E. File-level convenience function.**

```python
def detect_file_encoding(
    path: Path,
    *,
    detect_charset_enabled: bool = True,
    charset_sample_size: int = 65_536,
) -> EncodingObject | None:
    """Detect encoding metadata for a file.

    Reads the file in binary mode. Performs BOM detection and
    line-ending detection unconditionally. Performs charset detection
    via chardet unless disabled.

    Args:
        path: Path to the file.
        detect_charset_enabled: Whether to run chardet detection.
            Default: True.
        charset_sample_size: Maximum bytes to read for detection
            (default: 64 KB). BOM and line-ending detection use
            the same read buffer.

    Returns:
        An EncodingObject with populated fields, or None on read failure
        or when no signals are detected.
    """
    try:
        with open(path, "rb") as f:
            sample = f.read(charset_sample_size)
    except OSError as exc:
        logger.debug("Cannot read file for encoding detection: %s: %s", path, exc)
        return None

    if not sample:
        return None

    return _detect_from_bytes(sample, detect_charset_enabled=detect_charset_enabled)
```

**F. Bytes-level convenience function (for sidecar pipeline).**

```python
def detect_bytes_encoding(
    data: bytes,
    *,
    detect_charset_enabled: bool = True,
) -> EncodingObject | None:
    """Detect encoding metadata from an in-memory byte buffer.

    Same logic as detect_file_encoding but operates on bytes already
    in memory (avoids redundant file reads for sidecars whose content
    has already been read).

    Args:
        data: Raw file content bytes.
        detect_charset_enabled: Whether to run chardet detection.
            Default: True.

    Returns:
        An EncodingObject with populated fields, or None if nothing detected.
    """
    if not data:
        return None

    return _detect_from_bytes(data, detect_charset_enabled=detect_charset_enabled)
```

**G. Shared internal implementation.**

```python
def _detect_from_bytes(
    data: bytes,
    *,
    detect_charset_enabled: bool = True,
) -> EncodingObject | None:
    """Core detection logic shared by file and bytes entry points."""
    bom = detect_bom(data)
    line_endings = detect_line_endings(data)

    detected_encoding: str | None = None
    confidence: float | None = None
    if detect_charset_enabled:
        detected_encoding, confidence = detect_charset(data)

    # Return None if nothing was detected (binary file, no BOM,
    # no line endings, chardet returned nothing).
    if bom is None and line_endings is None and detected_encoding is None:
        return None

    return EncodingObject(
        bom=bom,
        line_endings=line_endings,
        detected_encoding=detected_encoding,
        confidence=confidence,
    )
```

### 2.4. Design Decisions

**BOM detection before line-ending detection.** The `_BOM_TABLE` is ordered longest-first to prevent the UTF-32 LE prefix (`FF FE 00 00`) from being misidentified as UTF-16 LE (`FF FE`). The line-ending detector strips any detected BOM before scanning, preventing false matches from BOM bytes.

**Line-ending detection operates on the full sample buffer.** A 64 KB sample is sufficient to detect line-ending style in all but pathological cases. Files that switch line-ending styles mid-stream will report `"mixed"`.

**Chardet is a standard runtime dependency.** Because encoding detection is enabled by default and omitting encoding metadata is implicitly destructive (silently discarding reversal-critical information), chardet MUST be available at runtime. It is listed as a required dependency in `pyproject.toml`, not under an optional extras group. The import guard is retained only as a defensive safety net. See §2.5 for packaging notes.

**`BOM_BYTES` reverse lookup.** Exported as a module-level dict so that the rollback engine (§5) can convert a BOM identifier string back to the original byte sequence without reimplementing the mapping.

**Returning `None` vs empty `EncodingObject`.** When no encoding signals are detected (binary file, no BOM, no line endings, chardet returned nothing), the function returns `None` rather than an empty `EncodingObject`. This keeps the serialized output clean: files with no encoding metadata simply omit the `encoding` key.

### 2.5. Packaging and Binary Builds

**`pyproject.toml`:** Add `chardet >= 7.0` to the `dependencies` list (required, not optional).

**Standalone executables (§13.4):** The project convention for PyInstaller release builds is that **all optional dependencies are treated as non-optional**: they are bundled into the executable and available at runtime regardless of how they were classified in `pyproject.toml`. This applies to `pyexiftool`, `LnkParse3`, and now `chardet`. Chardet, being a standard (not optional) dependency, is bundled automatically. However, the PyInstaller spec and hidden-imports configuration in `.github/workflows/` may need updating if chardet's mypyc-compiled wheels (chardet 7.x ships `.so`/`.pyd` extensions) require explicit `--collect-all chardet` or `--hidden-import` directives. Verify during build testing.

### 2.6. Affected Files

| File | Nature of change |
|------|------------------|
| `src/shruggie_indexer/core/encoding.py` | **New file.** BOM detection, line-ending detection, chardet integration, `BOM_BYTES` export. |
| `pyproject.toml` | Add `chardet >= 7.0` to `dependencies`. |

### 2.7. Spec References

| Reference | Section |
|-----------|---------|
| Encoding field (dropped in v2, candidate for v3) | §5.11, §18.2.2 |
| Sidecar text reading | §6.7 |
| Standalone executable builds | §13.4 |
| Third-party Python packages | §12.3 |

### 2.8. Acceptance Criteria

- `detect_bom()` correctly identifies all five BOM types and returns `None` for no-BOM content.
- `detect_bom()` does not misidentify UTF-32 LE as UTF-16 LE (prefix ambiguity handled).
- `detect_line_endings()` returns `"lf"`, `"crlf"`, `"mixed"`, or `None` correctly.
- `detect_line_endings()` strips BOM before scanning.
- `detect_charset()` returns `(None, None)` gracefully with a `WARNING` log when chardet is not installed.
- `detect_charset()` returns a Python codec name and confidence score for known encodings.
- `detect_file_encoding()` returns `None` for empty files and binary files with no line endings.
- `detect_bytes_encoding()` produces identical results to `detect_file_encoding()` for the same content.
- `BOM_BYTES` dict maps all five identifiers to their correct byte sequences.
- `chardet >= 7.0` is listed in `pyproject.toml` under `dependencies`.

---

## 3. Hashing Pipeline Integration

### 3.1. Problem Statement

The `IndexEntry.encoding` field must be populated during the entry construction pipeline. Encoding detection (BOM, line endings, and charset) is enabled by default because omitting this metadata is implicitly destructive: it silently discards information required for hash-perfect reversal.

### 3.2. Required Changes

**A. Add encoding detection to `build_file_entry()` in `core/entry.py`.**

After the file hashing step and before `IndexEntry` construction, invoke `detect_file_encoding()`:

```python
from shruggie_indexer.core.encoding import detect_file_encoding

# Inside build_file_entry(), after hashing:
encoding_obj = None
if config.detect_encoding and not is_symlink:
    encoding_obj = detect_file_encoding(
        item_path,
        detect_charset_enabled=config.detect_charset,
    )
```

Pass `encoding_obj` to the `IndexEntry` constructor.

**B. Add configuration flags.**

Add two new fields to `IndexerConfig` in `config/types.py`:

```python
detect_encoding: bool = True
"""Enable BOM, line-ending, and character encoding detection.

When True, the indexer reads the first 64 KB of each file in binary
mode to detect encoding metadata. Default: True. Disabling this
omits the encoding field from output, which prevents hash-perfect
reversal by downstream consumers.
"""

detect_charset: bool = True
"""Enable chardet-based character encoding detection.

When True, the encoding detection module passes the file sample to
chardet for encoding identification. When False, only BOM and
line-ending detection are performed (chardet is skipped). Requires
the chardet dependency (standard, not optional). Default: True.
"""
```

**C. Add CLI flags.**

Add two disabling flags to the CLI (Click options):

- `--no-detect-encoding` — Sets `config.detect_encoding = False`. Disables all encoding detection (BOM, line endings, and chardet). No `encoding` field appears in any output entry.
- `--no-detect-charset` — Sets `config.detect_charset = False`. Disables only chardet-based detection; BOM and line-ending detection remain active. The `encoding` field may still appear but will lack `detected_encoding` and `confidence`.

**D. Symlink exclusion.**

Encoding detection MUST be skipped for symlinks. Symlinks do not have meaningful file content (the indexer hashes the name string, not the target content). The entry builder already has an `is_symlink` branch; encoding detection is gated behind `not is_symlink`.

**E. Directory exclusion.**

`build_directory_entry()` does not invoke encoding detection. Directories have no file content. `encoding` remains `None` for all directory entries.

### 3.3. Performance Considerations

Encoding detection requires reading the first 64 KB of each file in binary mode. For files whose content was already fully read during hashing (any file smaller than 64 KB), the OS file cache will serve the read from memory with negligible cost. For larger files, this is one additional 64 KB read per file, which is insignificant relative to the full content read during hashing. The overhead is bounded at approximately 1 ms per file on SSD storage. Chardet's processing time is sub-millisecond for a 64 KB sample on modern hardware (chardet 7.x is 44x faster than 6.x).

If profiling reveals that the separate read is unacceptable for very large directory trees, a future optimization could capture the first chunk during the hashing pass and pass it to the encoding detector. This optimization is explicitly deferred from this sprint to keep the hashing module's responsibility boundary clean.

### 3.4. Affected Files

| File | Nature of change |
|------|------------------|
| `src/shruggie_indexer/core/entry.py` | Add encoding detection call in `build_file_entry()`. Pass `encoding` to `IndexEntry` constructor. |
| `src/shruggie_indexer/config/types.py` | Add `detect_encoding` and `detect_charset` config fields. |
| `src/shruggie_indexer/cli/main.py` | Add `--no-detect-encoding` and `--no-detect-charset` CLI flags. |
| `src/shruggie_indexer/gui/app.py` | Thread encoding config through GUI operation execution. |

### 3.5. Spec References

| Reference | Section |
|-----------|---------|
| Entry construction | §6.8 |
| Configuration system | §7 |
| CLI interface | §8.1 |
| Performance considerations | §17 |

### 3.6. Acceptance Criteria

- Running `shruggie-indexer index <path>` on a directory containing files with UTF-8 BOM produces entries with `encoding.bom: "utf-8"`.
- Running on files with CRLF line endings produces `encoding.line_endings: "crlf"`.
- Running on pure binary files (e.g., `.exe`, `.jpg`) produces no `encoding` key in the output.
- Symlink entries have no `encoding` key.
- Directory entries have no `encoding` key.
- `--no-detect-encoding` suppresses all encoding detection; no `encoding` key appears in any entry.
- `--no-detect-charset` suppresses only chardet; BOM and line endings are still detected.
- Default operation (no flags) populates `detected_encoding` and `confidence` via chardet.
- All existing tests continue to pass.

---

## 4. Sidecar Pipeline Integration

### 4.1. Problem Statement

Sidecar files whose content is stored as text in the `MetadataEntry.data` field undergo the same lossy text decode (BOM stripping, line-ending normalization) as any other text file. For hash-perfect sidecar reversal, the `MetadataEntry` must carry encoding metadata alongside the text data. Additionally, the existing `json_style` detection does not capture the specific indentation string, preventing hash-perfect restoration of JSON sidecars that use non-standard indent widths.

### 4.2. ExifTool Encoding-Related Fields

ExifTool's JSON output can contain several encoding-adjacent tags depending on the file type being inspected: `ExifByteOrder` (EXIF segment byte ordering), `CodedCharacterSet` (IPTC internal encoding), `CurrentIPTCDigest`, and occasionally encoding-related fields for specific metadata standards. These fields describe internal metadata encoding characteristics of the media file itself (e.g., "the IPTC block inside this JPEG is stored as Latin-1"), not the encoding of the file as a whole on disk.

These fields MUST NOT be stripped from the ExifTool output. They carry legitimate metadata about the internal structure of the media file that downstream consumers (archivists, metadata editors) may need. There is no naming collision risk: ExifTool tags live inside `MetadataEntry.data` (under `origin: "generated"`), while the new `EncodingObject` lives at the `MetadataEntry.encoding` field level. They occupy structurally distinct positions in the schema.

ExifTool-generated metadata entries (`origin: "generated"`) do not have original file bytes to detect encoding from. Their `encoding` field MUST always be `None`.

### 4.3. Required Changes

**A. Capture raw bytes before text decode in sidecar readers.**

The sidecar readers (`_read_text()`, `_read_json()`, `_read_lines()`, `_read_url_as_text()`) currently read files via `path.read_text(encoding="utf-8")`, which performs BOM stripping and line-ending normalization. To capture encoding metadata, the readers for text-format sidecars must read raw bytes first, perform encoding detection, then decode:

```python
def _read_text_with_encoding(
    path: Path,
    *,
    detect_charset_enabled: bool = True,
) -> tuple[str, EncodingObject | None]:
    """Read a file as UTF-8 text, capturing encoding metadata.

    Reads raw bytes, performs encoding detection, then decodes.
    Returns (decoded_text, encoding_object).
    """
    try:
        raw = path.read_bytes()
    except OSError:
        raise

    from shruggie_indexer.core.encoding import detect_bytes_encoding
    enc = detect_bytes_encoding(raw, detect_charset_enabled=detect_charset_enabled)

    # Decode with BOM handling (utf-8-sig strips BOM automatically).
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")

    return text, enc
```

The existing reader functions (`_read_text`, `_read_json`, etc.) are NOT replaced wholesale. Instead, add `_with_encoding` variants that return the encoding alongside the data. The `_build_metadata_entry()` function threads the encoding object through to the `MetadataEntry` constructor.

**B. JSON indent detection.**

Extend the existing `_detect_json_style()` function to also capture the specific indentation string:

```python
def _detect_json_indent(path: Path) -> tuple[str, str | None]:
    """Detect JSON formatting style and indent string.

    Returns (json_style, json_indent) where:
    - json_style is "compact" or "pretty"
    - json_indent is the literal indent string (e.g., "  ", "    ",
      "\\t") for pretty JSON, or None for compact JSON.

    Detection heuristic: find the first line that starts with whitespace
    after a newline. The leading whitespace of that line (up to the first
    non-whitespace character) is the indent string. If the file contains
    no indented lines, it is compact.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "compact", None

    # Find first indented line.
    for line in raw.split("\n")[1:]:  # Skip first line (opening brace).
        if line and line[0] in (" ", "\t"):
            # Extract the indent: all leading whitespace.
            indent = ""
            for ch in line:
                if ch in (" ", "\t"):
                    indent += ch
                else:
                    break
            if indent:
                return "pretty", indent
    return "compact", None
```

Update the existing `_detect_json_style_extra()` to include `json_indent`:

```python
def _detect_json_style_extra(
    path: Path,
    fmt: str,
) -> dict[str, Any] | None:
    """Return extra attributes dict with json_style and json_indent."""
    if fmt != "json":
        return None
    style, indent = _detect_json_indent(path)
    result: dict[str, Any] = {"json_style": style}
    if indent is not None:
        result["json_indent"] = indent
    return result
```

**C. Update `_build_metadata_entry()` to accept and store encoding.**

Add an `encoding` parameter to `_build_metadata_entry()`:

```python
def _build_metadata_entry(
    sidecar_path: Path,
    sidecar_type: str,
    data: Any,
    fmt: str,
    transforms: list[str],
    index_root: Path,
    config: IndexerConfig,
    *,
    extra_attrs: dict[str, Any] | None = None,
    encoding: EncodingObject | None = None,  # NEW
) -> MetadataEntry:
```

Pass `encoding` to the `MetadataEntry` constructor.

Update `extra_attrs` handling to thread `json_indent` through to `MetadataAttributes`:

```python
json_indent: str | None = None
if extra_attrs:
    # ... existing json_style, link_metadata handling ...
    json_indent = extra_attrs.get("json_indent")

attributes = MetadataAttributes(
    # ... existing fields ...
    json_indent=json_indent,
)
```

**D. Encoding detection scope for sidecars.**

Encoding detection applies only to sidecar entries with text-based formats:

| Format | Encoding detection | JSON indent detection |
|--------|-------------------|---------------------|
| `"json"` | Yes | Yes |
| `"text"` | Yes | No |
| `"lines"` | Yes | No |
| `"base64"` | No | No |
| `"error"` | No | No |

For binary-format sidecars (screenshots, thumbnails, `.lnk` files), encoding remains `None`.

### 4.4. Affected Files

| File | Nature of change |
|------|------------------|
| `src/shruggie_indexer/core/sidecar.py` | Add `_read_text_with_encoding()` variant. Update `_detect_json_style()` to `_detect_json_indent()`. Update text-format reader paths to capture encoding. Update `_build_metadata_entry()` signature and pass-through. Thread `json_indent` through `extra_attrs` to `MetadataAttributes`. |

### 4.5. Spec References

| Reference | Section |
|-----------|---------|
| Sidecar metadata file handling | §6.7 |
| MetadataEntry fields | §5.10 |
| MetadataEntry.attributes | §5.10 |
| Format-specific readers | §6.7 (fallback chain) |
| MetaMergeDelete reversal | §6.10, §6.11 |

### 4.6. Acceptance Criteria

- A `.description` sidecar with UTF-8 BOM and CRLF line endings produces a `MetadataEntry` with `encoding.bom: "utf-8"` and `encoding.line_endings: "crlf"`.
- A `.info.json` sidecar with LF line endings produces `encoding.line_endings: "lf"`.
- A `.info.json` sidecar indented with 4-space indent produces `json_style: "pretty"` and `json_indent: "    "`.
- A `.info.json` sidecar indented with tabs produces `json_style: "pretty"` and `json_indent: "\t"`.
- A compact `.info.json` sidecar produces `json_style: "compact"` and `json_indent: null` (absent from output).
- Binary sidecars (thumbnails, screenshots, `.lnk`) have no `encoding` field.
- Generated entries (ExifTool) have no `encoding` field.
- ExifTool encoding-related tags (`ExifByteOrder`, `CodedCharacterSet`, etc.) remain in the `data` blob, not stripped.
- Existing sidecar round-trip tests continue to pass.

---

## 5. Rollback Engine: Encoding-Aware Restoration

### 5.1. Problem Statement

The current rollback engine (`core/rollback.py`, `_decode_sidecar_data()`) writes text-format data as bare UTF-8 with no BOM and `\n` line endings, regardless of the original file's encoding characteristics. The `"lines"` format joins with `"\n"`. JSON restoration uses `json.dumps(indent=2)` for pretty or `separators=(",",":")` for compact, but does not respect the original indent string. These behaviors mean that even though we now capture encoding metadata at ingest, the reversal path does not consume it. Encoding metadata without corresponding reversal logic provides no practical benefit.

### 5.2. Required Changes

**A. Update `_decode_sidecar_data()` to consume encoding metadata.**

The function currently returns `(data, is_binary)`. The encoding-aware version must accept the `MetadataEntry` (which it already does) and use its `encoding` and `attributes.json_indent` fields:

```python
def _decode_sidecar_data(meta: MetadataEntry) -> tuple[bytes | str, bool]:
    """Decode sidecar data based on format, respecting encoding metadata.

    For JSON-format sidecars, respects json_style and json_indent to
    reproduce the original formatting. For text-format sidecars, respects
    encoding metadata to restore BOM, line endings, and source encoding.

    Returns (data, is_binary).
    """
    fmt = meta.attributes.format
    data = meta.data
    enc = meta.encoding  # May be None for legacy entries.

    if fmt == "json":
        text = _restore_json(data, meta.attributes)
        return _apply_text_encoding(text, enc), True  # Always bytes.
    if fmt == "text":
        text = str(data)
        return _apply_text_encoding(text, enc), True
    if fmt == "base64":
        return base64.b64decode(data), True
    if fmt == "lines":
        if isinstance(data, list):
            text = "\n".join(str(line) for line in data)
        else:
            text = str(data)
        return _apply_text_encoding(text, enc), True

    # Unknown format — treat as text.
    return _apply_text_encoding(str(data), enc), True
```

**B. JSON restoration with indent fidelity.**

```python
def _restore_json(data: Any, attrs: MetadataAttributes) -> str:
    """Serialize JSON data respecting the original formatting style.

    Uses json_indent when available for precise indent reproduction.
    Falls back to json_style for backward compatibility with entries
    that lack json_indent.
    """
    json_style = getattr(attrs, "json_style", None)
    json_indent = getattr(attrs, "json_indent", None)

    if json_style == "pretty":
        if json_indent is not None:
            if "\t" in json_indent:
                # json.dumps does not natively support tab indentation.
                # Serialize with a placeholder indent, then replace.
                compact = json.dumps(data, indent=2, ensure_ascii=False)
                lines = compact.split("\n")
                result_lines = []
                for line in lines:
                    stripped = line.lstrip(" ")
                    n_spaces = len(line) - len(stripped)
                    n_levels = n_spaces // 2
                    result_lines.append(json_indent * n_levels + stripped)
                return "\n".join(result_lines)
            else:
                # Space-based indent: pass the indent width directly.
                return json.dumps(
                    data,
                    indent=len(json_indent),
                    ensure_ascii=False,
                )
        # Legacy entry without json_indent: default to 2-space.
        return json.dumps(data, indent=2, ensure_ascii=False)

    # Compact (default, backward-compatible).
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
```

**C. Text encoding restoration.**

```python
def _apply_text_encoding(
    text: str,
    enc: EncodingObject | None,
) -> bytes:
    """Convert a text string back to bytes, restoring encoding metadata.

    Applies (in order):
    1. Line-ending restoration (LF → CRLF if original was CRLF).
    2. Encoding to bytes using the detected source encoding
       (or UTF-8 if not detected).
    3. BOM prepending (if original had a BOM).

    Args:
        text: The decoded text string.
        enc: The encoding metadata from ingest, or None.

    Returns:
        The restored byte sequence.
    """
    from shruggie_indexer.core.encoding import BOM_BYTES

    # 1. Restore line endings.
    if enc is not None and enc.line_endings == "crlf":
        # Normalize to LF first (in case of mixed), then convert to CRLF.
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")

    # 2. Encode to bytes.
    target_encoding = "utf-8"
    if enc is not None and enc.detected_encoding is not None:
        target_encoding = enc.detected_encoding
    try:
        data = text.encode(target_encoding)
    except (UnicodeEncodeError, LookupError):
        # Fallback to UTF-8 if the detected encoding cannot represent
        # the text or is unrecognized.
        data = text.encode("utf-8")

    # 3. Prepend BOM.
    if enc is not None and enc.bom is not None:
        bom_bytes = BOM_BYTES.get(enc.bom, b"")
        if bom_bytes:
            data = bom_bytes + data

    return data
```

**D. Update the sidecar write path.**

The `_decode_sidecar_data()` return type changes: for text-format sidecars the function now always returns `bytes` (not `str`), with `is_binary=True`. The caller in `execute_rollback()` must handle this: when `sidecar_binary` is True, write with `path.write_bytes(data)`. This is already the behavior for base64 format; the change extends it to text/json/lines formats so that encoding restoration is preserved end-to-end.

Verify that the sidecar write path in `execute_rollback()` uses `write_bytes()` when `sidecar_binary` is True. If it currently uses `write_text()` for text formats (splitting on the `is_binary` flag), the condition must be updated to always use `write_bytes()` now that `_apply_text_encoding()` returns bytes for all text formats.

**E. Backward compatibility with v2 entries.**

When `encoding` is `None` (entries from v2-era sidecars or entries indexed with `--no-detect-encoding`), the restoration falls through to the existing behavior: UTF-8 encoding, no BOM, LF line endings. This is identical to the current rollback behavior, so existing round-trip tests continue to pass.

### 5.3. Affected Files

| File | Nature of change |
|------|------------------|
| `src/shruggie_indexer/core/rollback.py` | Update `_decode_sidecar_data()` to consume `encoding` and `json_indent`. Add `_restore_json()` and `_apply_text_encoding()` helpers. Update sidecar write path to use `write_bytes()` for all formats. |

### 5.4. Spec References

| Reference | Section |
|-----------|---------|
| Rollback operations | §6.11 |
| Sidecar reconstruction | §6.11 (rollback sidecar reconstruction) |
| MetadataEntry.attributes | §5.10 |
| Sidecar restoration fidelity | rollback.md |

### 5.5. Acceptance Criteria

- Rollback of a sidecar with `encoding.bom: "utf-8"` produces a file starting with `EF BB BF`.
- Rollback of a sidecar with `encoding.line_endings: "crlf"` produces a file with `\r\n` line endings.
- Rollback of a sidecar with `encoding.detected_encoding: "windows-1252"` encodes the output using Windows-1252, not UTF-8.
- Rollback of a JSON sidecar with `json_indent: "    "` (4 spaces) produces 4-space indentation.
- Rollback of a JSON sidecar with `json_indent: "\t"` produces tab indentation.
- Rollback of a v2-era sidecar (no `encoding` field, no `json_indent` field) produces identical output to the pre-change rollback behavior.
- The sidecar write path uses `write_bytes()` for all restored sidecar formats.
- All existing rollback tests continue to pass.
- New round-trip test: ingest a sidecar with BOM + CRLF + known encoding, rollback, compare bytes to original. The restored file SHOULD be byte-identical to the original for text-format sidecars where all encoding metadata was captured.

---

## 6. Serializer and Naming Convention Updates

### 6.1. Problem Statement

The serializer hardcodes `schema_version: 2`. Sidecar filenames use the `_meta2.json` / `_directorymeta2.json` convention. Exclusion patterns match `_meta2?\.json` to cover both v1 and v2. All three must be updated for v3.

### 6.2. Required Changes

**A. Update entry construction to emit `schema_version: 3`.**

In `core/entry.py`, update `build_file_entry()` and `build_directory_entry()` to pass `schema_version=3` to the `IndexEntry` constructor.

**B. Update `created_source` population in the timestamps module.**

In `core/timestamps.py`, update `extract_timestamps()` to populate `created_source`:

```python
def extract_timestamps(
    stat_result: os.stat_result,
    *,
    is_symlink: bool = False,
) -> TimestampsObject:
    # ... existing logic ...

    # Determine creation time provenance.
    created_source: str | None = None
    try:
        _ = stat_result.st_birthtime
        created_source = "birthtime"
    except AttributeError:
        created_source = "ctime_fallback"

    return TimestampsObject(
        created=...,
        modified=...,
        accessed=...,
        created_source=created_source,
    )
```

**C. Update sidecar filename convention.**

In `core/serializer.py` (or wherever `build_sidecar_path()` is defined), update the sidecar suffix from `_meta2.json` to `_meta3.json` and from `_directorymeta2.json` to `_directorymeta3.json`.

**D. Update exclusion patterns.**

In `config/defaults.py` (or wherever `METADATA_EXCLUDE_PATTERNS` is defined), update the sidecar exclusion regex to match v1, v2, and v3 filenames:

```python
re.compile(r'_(meta[23]?|directorymeta[23]?)\.json$', re.IGNORECASE),
```

The `[23]?` quantifier matches `_meta.json` (v1), `_meta2.json` (v2), and `_meta3.json` (v3).

**E. Update the serializer key ordering.**

In `core/serializer.py`, update `_TOP_LEVEL_KEY_ORDER` to include `encoding` in the appropriate position (after `attributes`, before `items`).

### 6.3. Affected Files

| File | Nature of change |
|------|------------------|
| `src/shruggie_indexer/core/entry.py` | `schema_version=3` in constructors. |
| `src/shruggie_indexer/core/timestamps.py` | Populate `created_source` field. |
| `src/shruggie_indexer/core/serializer.py` | Update key ordering to include `encoding`. |
| `src/shruggie_indexer/core/paths.py` | Update sidecar suffix constants (if defined here). |
| `src/shruggie_indexer/config/defaults.py` | Update exclusion regex for v3 filenames. |

### 6.4. Spec References

| Reference | Section |
|-----------|---------|
| Schema version field | §5.4 |
| JSON serialization and output routing | §6.9 |
| Sidecar naming convention | §5.13 |
| Exclusion patterns | §7.3 |
| Creation time portability | §15.5 |
| Timestamp extraction | §6.5 |

### 6.5. Acceptance Criteria

- Output JSON contains `"schema_version": 3`.
- In-place sidecar files are written with `_meta3.json` and `_directorymeta3.json` suffixes.
- Existing v1 (`_meta.json`) and v2 (`_meta2.json`) sidecar files are excluded from traversal by the updated exclusion patterns.
- `timestamps.created_source` is populated as `"birthtime"` or `"ctime_fallback"` on every entry.
- The `encoding` key appears in the serialized JSON in the correct position (after `attributes`, before `items`).

---

## 7. v3 JSON Schema, Tests, and Backward Compatibility

### 7.1. Problem Statement

The canonical v2 JSON Schema must be forked into a v3 schema. Schema conformance tests must validate against v3. Encoding detection and rollback restoration logic need unit tests. The v2-to-v3 migration path must be documented.

### 7.2. Required Changes

**A. Create v3 JSON Schema file.**

Create `docs/schema/shruggie-indexer-v3.schema.json` based on the v2 schema with the following changes:

1. Update `$id` to `https://schemas.shruggie.tech/data/shruggie-indexer-v3.schema.json`.
2. Update `schema_version` constraint from `"const": 2` to `"const": 3`.
3. Add `EncodingObject` to the `definitions` block:

```json
"EncodingObject": {
  "type": "object",
  "properties": {
    "bom": {
      "type": "string",
      "enum": ["utf-8", "utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"],
      "description": "Detected byte-order mark type."
    },
    "line_endings": {
      "type": "string",
      "enum": ["lf", "crlf", "mixed"],
      "description": "Detected line-ending convention."
    },
    "detected_encoding": {
      "type": "string",
      "description": "Best-guess character encoding name."
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Encoding detection confidence score."
    }
  },
  "additionalProperties": false
}
```

Note: All properties in `EncodingObject` are optional (none are in a `required` array). The object itself uses `additionalProperties: false`.

4. Add `encoding` as an optional property on the root `IndexEntry`:

```json
"encoding": {
  "$ref": "#/definitions/EncodingObject"
}
```

Do NOT add `encoding` to the `required` array.

5. Add `created_source` to `TimestampsObject`:

```json
"created_source": {
  "type": "string",
  "enum": ["birthtime", "ctime_fallback"],
  "description": "Provenance of the created timestamp."
}
```

6. Add `encoding` as an optional property on `MetadataEntry` (same `$ref`).

7. Add `json_indent` to `MetadataAttributes`:

```json
"json_indent": {
  "type": "string",
  "description": "Original JSON indentation string for hash-perfect restoration."
}
```

8. Update the `_meta2.json` references in descriptions to `_meta3.json`.

**B. Update the local schema copy.**

Copy the v3 schema to `docs/schema/shruggie-indexer-v3.schema.json`. Retain the v2 schema file for reference. Update `mkdocs.yml` if needed to serve the v3 schema.

**C. Publish v3 schema to schemas.shruggie.tech.**

Update the hosted schema at `schemas.shruggie.tech/data/shruggie-indexer-v3.schema.json`. Retain the v2 schema at its existing URL (do not redirect or remove).

**D. Update schema conformance tests.**

In `tests/unit/test_serializer.py` (or the dedicated schema conformance test file), update the validation target to the v3 schema. Add test cases:

| Test case | Input | Expected |
|-----------|-------|----------|
| Entry with encoding (BOM + line endings) | File with UTF-8 BOM and CRLF | `encoding.bom: "utf-8"`, `encoding.line_endings: "crlf"` present in output; validates against v3 schema. |
| Entry without encoding | Binary file | No `encoding` key in output; validates against v3 schema. |
| Entry with `created_source` | Any file | `timestamps.created_source` present with valid value; validates against v3 schema. |
| Sidecar entry with encoding | Text sidecar with BOM | `MetadataEntry.encoding` present; validates against v3 schema. |
| Sidecar with `json_indent` | JSON sidecar with 4-space indent | `attributes.json_indent: "    "` present; validates against v3 schema. |
| Backward: v2 entries lack v3 fields | Legacy v2 output | Does NOT validate against v3 schema (expected; `schema_version: 2` fails `const: 3`). |

**E. Encoding detection unit tests.**

Create `tests/unit/test_encoding.py`:

| Test case | Input | Expected |
|-----------|-------|----------|
| UTF-8 BOM detection | `b"\xef\xbb\xbf" + b"hello"` | `bom = "utf-8"` |
| UTF-16 LE BOM detection | `b"\xff\xfe" + b"h\x00"` | `bom = "utf-16-le"` |
| UTF-32 LE BOM detection | `b"\xff\xfe\x00\x00" + b"h\x00\x00\x00"` | `bom = "utf-32-le"` (not UTF-16 LE) |
| No BOM | `b"hello world"` | `bom = None` |
| LF line endings | `b"line1\nline2\n"` | `line_endings = "lf"` |
| CRLF line endings | `b"line1\r\nline2\r\n"` | `line_endings = "crlf"` |
| Mixed line endings | `b"line1\r\nline2\nline3\r\n"` | `line_endings = "mixed"` |
| No line endings | `b"single line"` | `line_endings = None` |
| Binary file (no signals) | Random binary bytes with no line endings | Returns `None` |
| Chardet UTF-8 detection | UTF-8 encoded text | `detected_encoding = "utf-8"`, confidence > 0.9 |
| Chardet Windows-1252 | Windows-1252 encoded text | `detected_encoding = "windows-1252"` |
| Empty file | `b""` | Returns `None` |
| BOM_BYTES reverse lookup | All five identifiers | Correct byte sequences returned |

**F. Rollback encoding restoration tests.**

Add to `tests/unit/test_rollback.py`:

| Test case | Input | Expected |
|-----------|-------|----------|
| BOM restoration | Text sidecar with `encoding.bom: "utf-8"` | Restored file starts with `EF BB BF` |
| CRLF restoration | Text sidecar with `encoding.line_endings: "crlf"` | Restored file has `\r\n` line endings |
| Encoding restoration | Text sidecar with `encoding.detected_encoding: "windows-1252"` | Restored file is Windows-1252 encoded |
| JSON 4-space indent | JSON sidecar with `json_indent: "    "` | Restored JSON uses 4-space indent |
| JSON tab indent | JSON sidecar with `json_indent: "\t"` | Restored JSON uses tab indent |
| Legacy v2 text sidecar | No `encoding` field | Restored as UTF-8 with LF (unchanged behavior) |
| Legacy v2 JSON sidecar | No `json_indent` field, `json_style: "pretty"` | Restored with 2-space indent (backward compat) |
| Full round-trip | Create temp file with BOM+CRLF, ingest, rollback | Byte-identical output |

### 7.3. Backward Compatibility Notes

**v2-to-v3 migration path.** v3 is a superset of v2. All v2 required fields remain required in v3. The new fields (`encoding`, `timestamps.created_source`, `json_indent`) are optional. A v2 entry can be upgraded to v3 by:

1. Changing `schema_version` from `2` to `3`.
2. Optionally populating the new fields (or leaving them absent).

This is a lossless upgrade. No v2 data is discarded.

**v3-to-v2 downgrade.** Stripping the new optional fields and changing `schema_version` from `3` to `2` produces a valid v2 entry. This is also lossless in the v2 direction (the encoding, created_source, and json_indent information is lost, but no v2 field is affected).

**Sidecar coexistence.** v1 (`_meta.json`), v2 (`_meta2.json`), and v3 (`_meta3.json`) sidecar files can coexist on disk. The exclusion pattern update in §6 ensures all three generations are excluded from traversal.

**Consumer guidance.** Consumers dispatching on `schema_version` should add a `case 3:` branch. The v3 field set is a strict superset of v2; consumers that parse v3 entries can reuse their v2 parsing logic and optionally inspect the new fields.

### 7.4. Affected Files

| File | Nature of change |
|------|------------------|
| `docs/schema/shruggie-indexer-v3.schema.json` | **New file.** Canonical v3 JSON Schema. |
| `docs/schema/index.md` | Updated documentation for v3 schema, new fields, migration guidance. |
| `tests/unit/test_serializer.py` | Updated schema conformance tests targeting v3. |
| `tests/unit/test_encoding.py` | **New file.** Encoding detection unit tests. |
| `tests/unit/test_rollback.py` | New encoding-aware restoration tests. |

### 7.5. Spec References

| Reference | Section |
|-----------|---------|
| Schema validation and enforcement | §5.12 |
| Output schema conformance tests | §14.4 |
| Backward compatibility considerations | §5.13 |
| Compatibility strategy | §18.2.3 |

### 7.6. Acceptance Criteria

- `docs/schema/shruggie-indexer-v3.schema.json` exists and is valid JSON Schema Draft-07.
- All output from the indexer validates against the v3 schema.
- All encoding detection unit tests pass.
- All rollback encoding restoration tests pass.
- The v2 schema file is retained (not deleted or modified).
- `mkdocs build --strict` passes.

---

## 8. Specification, Documentation, and Changelog Updates (Execute Last)

### 8.1. Purpose

After all code changes in Sections 1-7 are implemented and verified, the technical specification, documentation site, and changelog must be updated to reflect the new behavior.

### 8.2. Required Spec Updates

| Section | Update |
|---------|--------|
| §1.1 (header) | Update **Date** and bump **Status** to `AMENDED`. |
| §5.2 (Reusable Type Definitions) | Add §5.2.8 `EncodingObject` definition with field descriptions, enum values, and nullability semantics. |
| §5.2.5 (TimestampsObject) | Add `created_source` field description. |
| §5.3 (Top-Level IndexEntry Fields) | Add `encoding` to the field table. Update `schema_version` from `const: 2` to `const: 3`. Update `required` array documentation. Update `additionalProperties` documentation to list `encoding` as a declared-but-not-required property. |
| §5.4 (Identity Fields) | Update `schema_version` subsection: change "Always the integer `2`" to "Always the integer `3` for v3 output. v2 output used `2`." |
| §5.7 (Timestamp Fields) | Add documentation for `created_source` field on `TimestampsObject`. Cross-reference §15.5. |
| §5.10 (MetadataEntry Fields) | Add `encoding` to the MetadataEntry field table. Document that it is sidecar-only (like `file_system`, `size`, `timestamps`). Update the origin behavior table to show `encoding` as "Present" for sidecar and "Absent" for generated. Add `json_indent` to the MetadataEntry.attributes table. |
| §5.11 (Dropped and Restructured Fields) | Update the `Encoding` entry to note that v3 reintroduces encoding metadata in a Python-native form (`EncodingObject`), distinct from the dropped v1 .NET `Encoding` object. |
| §5.12 (Schema Validation and Enforcement) | Reference the v3 schema as the validation target. Update serialization invariants to cover `encoding` conditional inclusion. |
| §5.13 (Backward Compatibility) | Add v2-to-v3 migration guidance. Document the `_meta3.json`/`_directorymeta3.json` sidecar naming convention. Update consumer guidance for v3 dispatch. |
| §6.5 (Filesystem Timestamps) | Document `created_source` population logic in `extract_timestamps()`. |
| §6.7 (Sidecar Metadata File Handling) | Document encoding detection during sidecar reading. Add `json_indent` detection to the JSON style detection subsection. Add to the MetadataEntry construction table. |
| §6.8 (Index Entry Construction) | Document encoding detection call in `build_file_entry()`. |
| §6.9 (JSON Serialization and Output Routing) | Update key ordering to include `encoding`. Document v3 sidecar suffix. |
| §6.11 (Rollback Operations) | Document encoding-aware restoration in `_decode_sidecar_data()`. Document `_apply_text_encoding()` logic (BOM prepend, line-ending restoration, source encoding). Document `json_indent`-aware JSON restoration. Update the sidecar restoration fidelity table to reflect improved fidelity for text formats. |
| NEW §6.12 (Encoding Detection) | New section documenting the encoding detection module: BOM detection, line-ending detection, chardet integration, detection scope (files vs directories vs symlinks), and the `EncodingObject` population logic. |
| §7 (Configuration) | Document `detect_encoding` and `detect_charset` configuration fields and their CLI flag equivalents. |
| §8.1 (CLI Interface) | Add `--no-detect-encoding` and `--no-detect-charset` to the flag table. |
| §9.4 (Data Models) | Add `EncodingObject` to the dataclass documentation. Update `IndexEntry`, `MetadataEntry`, `MetadataAttributes`, and `TimestampsObject` field lists. |
| §12.3 (Third-Party Python Packages) | Add `chardet >= 7.0` to the dependency table. Document its purpose (character encoding detection for hash-perfect reversal). |
| §13.4 (Standalone Executable Builds) | Note that chardet's mypyc-compiled extensions require PyInstaller hidden-imports if applicable. Reiterate the convention: all optional dependencies are bundled in release builds. |
| §14.4 (Output Schema Conformance Tests) | Reference v3 schema. |
| §15.5 (Creation Time Portability) | Add note that `created_source` is now populated in v3, resolving the ambiguity documented in this section. |
| §18.2.1 (Evolution Principles) | No changes needed; the v3 bump follows the documented principles. |
| §18.2.2 (Candidate v3 Additions) | Strike through `encoding` and `timestamps.created_source` entries (mark as implemented in v3, following the `session_id` precedent). Add a note to the `type` enum extension entry that it was evaluated for v3 but deferred due to scope. |
| §18.2.3 (Compatibility Strategy) | Update to reflect v3 coexistence with v1 and v2. Document `_meta3.json` naming. |

### 8.3. Required Documentation Updates

| File | Update |
|------|--------|
| `docs/schema/index.md` | Add v3 schema documentation: new `EncodingObject` type, new `created_source` field, `json_indent` attribute, `encoding` on IndexEntry and MetadataEntry. Add annotated example showing a v3 entry with encoding metadata. Update migration notes. |
| `docs/user-guide/python-api.md` | Update `IndexEntry`, `MetadataEntry`, `MetadataAttributes`, and reusable types tables to include new fields. |
| `docs/user-guide/platform-notes.md` | Add note about `created_source` resolving the ctime ambiguity. |
| `docs/user-guide/rollback.md` | Update the sidecar restoration fidelity table: text formats now achieve byte-identical restoration when encoding metadata is present. Document `json_indent`-aware JSON restoration. Add encoding restoration section. |
| `docs/user-guide/cli-reference.md` | Add `--no-detect-encoding` and `--no-detect-charset` flag documentation (if this file exists). |
| `CHANGELOG.md` | Add v0.2.0 section with entries for all changes. |
| `docs/changelog.md` | Sync from `CHANGELOG.md` (auto-copy header preserved). |

### 8.4. Changelog Entry (Draft)

```markdown
## [0.2.0] - 2026-XX-XX

### Added
- **v3 output schema.** `schema_version` is now `3`. In-place sidecars use
  `_meta3.json` and `_directorymeta3.json` suffixes. v2 and v1 sidecar files
  are still recognized and excluded during traversal.
- **`encoding` field on `IndexEntry`.** Optional top-level field capturing
  BOM type, line-ending convention, detected character encoding, and detection
  confidence. Enables hash-perfect reversal when file content is stored as
  decoded text by downstream consumers. Populated for files by default;
  absent for directories, symlinks, and when `--no-detect-encoding` is
  specified.
- **`encoding` field on `MetadataEntry`.** Sidecar-only field capturing the
  same encoding metadata for ingested sidecar files. Enables hash-perfect
  reversal of sidecar text content.
- **`timestamps.created_source` field.** New optional field on
  `TimestampsObject` indicating whether the creation timestamp was derived
  from `st_birthtime` (true creation time) or `st_ctime` (inode change
  time fallback). Resolves the cross-platform ambiguity documented in §15.5.
- **`attributes.json_indent` field.** New optional field on
  `MetadataAttributes` capturing the precise indentation string used in the
  original JSON sidecar file (e.g., 2-space, 4-space, tab). Enables
  hash-perfect JSON restoration during rollback.
- **`core/encoding.py` module.** BOM detection, line-ending detection, and
  chardet integration for character encoding identification.
- **Encoding-aware rollback restoration.** The rollback engine now consumes
  `encoding` metadata to restore BOM, line endings, and source encoding
  during sidecar restoration. JSON sidecars are restored with the original
  indent string when `json_indent` is available. Text-format sidecar
  restoration is now byte-identical when full encoding metadata is present.
- **`--no-detect-encoding` CLI flag.** Disables all encoding detection (BOM,
  line endings, and chardet), omitting the `encoding` field from output.
- **`--no-detect-charset` CLI flag.** Disables only chardet-based detection;
  BOM and line-ending detection remain active.
- **v3 JSON Schema.** Canonical schema at
  `schemas.shruggie.tech/data/shruggie-indexer-v3.schema.json`.
- **`chardet` dependency.** Added as a standard runtime dependency for
  character encoding detection.

### Changed
- Sidecar exclusion patterns updated to match v1, v2, and v3 sidecar
  filenames.
- Serializer key ordering updated to include `encoding` field.
- JSON style detection extended to capture indent string alongside
  compact/pretty classification.
```

### 8.5. Acceptance Criteria

- All spec sections listed in §8.2 have been updated with `> **Updated 2026-03-XX:**` callouts where appropriate.
- No cross-references (`§X.Y`) are broken.
- `CHANGELOG.md` includes entries for all v0.2.0 changes.
- `docs/changelog.md` is synced from `CHANGELOG.md`.
- `mkdocs build --strict` passes with zero warnings.
- The v3 JSON Schema is committed to `docs/schema/`.

---

## Appendix A: Deferred Items

The following items were evaluated for inclusion in this sprint and explicitly deferred.

**`type` enum extension (`"symlink"` value).** Adding `"symlink"` as a third value for the `type` field would change the semantic meaning of an existing field. Consumers that dispatch on `type` with a two-value assumption (`"file"` / `"directory"`) would break. While the v3 bump is the natural window for this change, the implementation scope is large: the traversal logic, entry builder, serializer, rollback engine, and all tests that assert on `type` values would need updating. The encoding-focused objective of this sprint does not justify the risk. Remains a candidate for v4.

**Encoding detection during the hashing pass.** Capturing the first chunk of file content during `hash_file()` and passing it to the encoding detector would eliminate the separate 64 KB read. This optimization is architecturally clean but crosses the module boundary between `core/hashing.py` (which should only produce `HashSet`) and `core/encoding.py`. Deferred unless profiling reveals the extra read is a bottleneck.

**v2-to-v3 migration utility.** The v1-to-v2 migration utility (§18.1.1) is already deferred. A v2-to-v3 migration utility would be simpler (v3 is a strict superset of v2; migration is `schema_version = 3` plus optional field population). This is low priority because v2 consumers can ignore unknown v3 fields, and the coexistence of v2 and v3 sidecars on disk is handled by the exclusion pattern update.

**ExifTool encoding tag stripping.** ExifTool outputs encoding-related tags (`ExifByteOrder`, `CodedCharacterSet`, etc.) that describe the internal metadata encoding of the media file. These were evaluated for stripping from the generated metadata output. Decision: retain them. They describe the media file's internal structure (not the file-on-disk encoding), they occupy a structurally distinct position (`MetadataEntry.data` vs `MetadataEntry.encoding`), and downstream consumers may need them for archival or metadata editing purposes.

---

## Appendix B: Chardet Reference

**Library:** chardet (PyPI: `chardet`)
**Version requirement:** >= 7.0
**License:** MIT
**Runtime dependencies:** None (zero-dependency library)
**Python:** 3.10+
**Thread safety:** `detect()` and `detect_all()` are safe to call concurrently.

**What it does:** Analyzes a byte string and returns the most likely character encoding, a confidence score (0.0-1.0), and the detected language. Uses a 12-stage detection pipeline: BOM detection, structural probing, byte validity filtering, and bigram statistical models. Covers 99 encodings across six "encoding eras" (modern web, legacy ISO, Mac, DOS, regional, mainframe).

**What it does not do:** Chardet does not detect BOM type as a structured field (it uses BOM internally as one stage of its pipeline but does not surface it separately). It does not detect line-ending conventions. These are handled by the manual detection layer in `core/encoding.py`.

**API usage in this project:**

```python
import chardet
result = chardet.detect(raw_bytes)
# result = {"encoding": "utf-8", "confidence": 0.99, "language": "en"}
```

The `compat_names=False` option may be used to get raw Python codec names (e.g., `"shift_jis_2004"` instead of `"SHIFT_JIS"`). The project normalizes encoding names to lowercase regardless.

**Performance:** chardet 7.x is 44x faster than 6.x (with mypyc compilation) and 4.1x faster than charset-normalizer. Sub-millisecond for typical 64 KB samples.

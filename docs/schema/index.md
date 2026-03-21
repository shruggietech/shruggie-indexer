# Schema Reference

The v3 output schema defines the structure of every index entry produced by shruggie-indexer. It extends the v2 schema with encoding metadata, timestamp provenance, and indent-aware restoration while retaining full backward compatibility.

## Canonical Schema

The authoritative machine-readable schemas are hosted at:

- **v3 (current):** [schemas.shruggie.tech/data/shruggie-indexer-v3.schema.json](https://schemas.shruggie.tech/data/shruggie-indexer-v3.schema.json) — [local copy](shruggie-indexer-v3.schema.json)
- **v2 (legacy):** [schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json](https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json) — [local copy](shruggie-indexer-v2.schema.json)

## Design Principles

| Principle | Summary |
|-----------|---------|
| **P1 — Logical grouping** | Related fields are consolidated into typed sub-objects (`NameObject`, `SizeObject`, `TimestampPair`, `ParentObject`) instead of scattered across the top level. |
| **P2 — Single type discriminator** | A `type` enum (`"file"` or `"directory"`) replaces the legacy dual-boolean pattern. Combined with `schema_version`, consumers can route parsing unambiguously. |
| **P3 — Metadata provenance** | `MetadataEntry` includes `origin`, `file_system`, `size`, `timestamps`, and `attributes` — enough to reconstruct the original sidecar file for MetaMergeDelete reversal. |
| **P4 — No redundancy** | Dropped `BaseName` (derivable), `SHA1` (no unique purpose), and `Encoding` (.NET-specific). |
| **P5 — Explicit algorithm** | `id_algorithm` records which hash algorithm produced the `id`, eliminating reverse-matching. |
| **P6 — Encoding fidelity** | v3 captures BOM, line endings, and character encoding so the rollback engine can restore sidecar files byte-identically. |

## Top-Level IndexEntry Fields

An `IndexEntry` is the root JSON object describing a single indexed file or directory.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `schema_version` | `integer` (const `3`) | Yes | Always `3`. Placed first in serialized output. |
| `id` | `string` | Yes | Primary identifier. Prefix `y` = file, `x` = directory. Pattern: `^[xy][0-9A-F]+$`. |
| `id_algorithm` | `string` (enum) | Yes | `"md5"` or `"sha256"`. The algorithm used to derive `id`. |
| `type` | `string` (enum) | Yes | `"file"` or `"directory"`. |
| `name` | `NameObject` | Yes | Item name with associated hash digests. |
| `extension` | `string` or `null` | Yes | File extension without leading dot, lowercase. `null` for directories or extensionless files. |
| `mime_type` | `string` or `null` | No | MIME type via `mimetypes.guess_type()`, overridden by ExifTool when available. |
| `size` | `SizeObject` | Yes | Human-readable and byte-count size. |
| `hashes` | `HashSet` or `null` | Yes | Content hashes (file) or `null` (directory). Symlinks hash the name string instead. |
| `file_system` | `object` | Yes | Relative path and parent directory identity. |
| `timestamps` | `TimestampsObject` | Yes | Created, modified, and accessed timestamps. |
| `attributes` | `object` | Yes | Symlink status and deterministic storage name. |
| `items` | `array[IndexEntry]` or `null` | No | Child entries (directory) or `null` (file). |
| `metadata` | `array[MetadataEntry]` or `null` | No | Metadata records (file) or `null` (directory). |
| `encoding` | `EncodingObject` | No | Source file encoding metadata (BOM, line endings, charset). Absent for binary files. |
| `duplicates` | `array[IndexEntry]` | No | Complete `IndexEntry` objects for files de-duplicated against this entry during rename. Absent when no duplicates exist. |
| `session_id` | `string` (UUID4) | No | Identifies the indexing invocation that produced this entry. All entries within a single CLI/GUI/API invocation share the same value. |
| `indexed_at` | `TimestampPair` | No | The moment this IndexEntry was constructed. Distinct from file timestamps — records the indexer's observation time. |

`additionalProperties` is `false`. The `required` set:

```json
["schema_version", "id", "id_algorithm", "type", "name",
 "extension", "size", "hashes", "file_system", "timestamps", "attributes"]
```

`session_id`, `indexed_at`, `encoding`, and `duplicates` are declared properties but are **not** in the `required` array. `session_id` and `indexed_at` are present when the indexer is invoked through the standard CLI, GUI, or API entry points. `encoding` is present when the source file has detectable text encoding signals; absent for binary files. `duplicates` is present only on canonical entries that absorbed one or more byte-identical files during a rename operation. Entries constructed directly (e.g., in tests) may omit all three optional fields.

### Field behavior by type

| `type` value | `hashes` | `extension` | `items` | `metadata` |
|---|---|---|---|---|
| `"file"` | Content `HashSet` (or name hash if symlink) | Extension string | `null` | `MetadataEntry[]` or `null` |
| `"directory"` | `null` | `null` | `IndexEntry[]` or `null` | `null` |

## Reusable Type Definitions

### HashSet

Cryptographic hash digests. All values are uppercase hexadecimal strings (`0-9`, `A-F`).

| Property | Type | Required | Pattern | Description |
|----------|------|----------|---------|-------------|
| `md5` | `string` | Yes | `^[0-9A-F]{32}$` | MD5 digest (32 chars). |
| `sha256` | `string` | Yes | `^[0-9A-F]{64}$` | SHA-256 digest (64 chars). |
| `sha512` | `string` | No | `^[0-9A-F]{128}$` | SHA-512 digest (128 chars). Omitted from output when not computed. |

!!! info "SHA-1 Removal"
    SHA-1 is dropped from v2 entirely. It was not used for identity derivation, adds computational overhead, and has demonstrated collision attacks since 2017.

### NameObject

Pairs a text string with its associated hash digests.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `text` | `string` or `null` | Yes | The name value including extension for files. `null` for generated metadata entries. |
| `hashes` | `HashSet` or `null` | Yes | Hashes of the UTF-8 byte representation of `text`. `null` when `text` is `null`. |

`text` and `hashes` are **co-nullable**: both `null` or both populated. The implementation enforces this at construction time.

### SizeObject

File size in human-readable and machine-readable forms.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `text` | `string` | Yes | Formatted string with unit (e.g., `"15.28 MB"`, `"135 B"`). Uses decimal SI: B, KB, MB, GB, TB. |
| `bytes` | `integer` | Yes | Exact byte count (≥ 0). |

Formatting thresholds use powers of 1,000 (decimal SI), not 1,024 (binary). Two decimal places for values ≥ 1 KB.

### TimestampPair

A single timestamp in dual format.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `iso` | `string` | Yes | ISO 8601 with fractional seconds and timezone offset. |
| `unix` | `integer` | Yes | Milliseconds since epoch (1970-01-01T00:00:00Z). |

### TimestampsObject

Three standard filesystem timestamps.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `created` | `TimestampPair` | Yes | Filesystem creation time. See [platform notes](../user-guide/platform-notes.md#creation-time-portability) for cross-platform behavior. |
| `modified` | `TimestampPair` | Yes | Last content modification time. |
| `accessed` | `TimestampPair` | Yes | Last access time. May be approximate on Linux with `relatime`. |
| `created_source` | `string` (enum) | No | Provenance of the `created` timestamp: `"birthtime"` (true creation time) or `"ctime_fallback"` (inode change time used as fallback on platforms without birth time). |

### ParentObject

Parent directory identity and name.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | `string` | Yes | Parent directory identifier. `x`-prefixed. Pattern: `^x[0-9A-F]+$`. |
| `name` | `NameObject` | Yes | Parent directory name with hashes. |

### EncodingObject

Source file encoding metadata captured during ingestion. All properties are optional — the object may contain any combination of fields. Uses `additionalProperties: false`.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `bom` | `string` (enum) | No | Detected byte-order mark type: `"utf-8"`, `"utf-16-le"`, `"utf-16-be"`, `"utf-32-le"`, or `"utf-32-be"`. Absent when no BOM is present. |
| `line_endings` | `string` (enum) | No | Detected line-ending convention: `"lf"`, `"crlf"`, or `"mixed"`. Absent for binary files or files with no line endings. |
| `detected_encoding` | `string` | No | Best-guess character encoding name from `chardet` (e.g., `"utf-8"`, `"windows-1252"`, `"ascii"`). |
| `confidence` | `number` (0.0–1.0) | No | `chardet` detection confidence score. Present only when `detected_encoding` is present. |

The rollback engine uses `EncodingObject` fields to restore BOM bytes, line endings, and character encoding when rebuilding sidecar files.

## Filesystem Location Fields

The `file_system` object provides path and hierarchy information.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `relative` | `string` | Yes | Forward-slash path from index root to this item. `"."` for the root item. |
| `parent` | `ParentObject` or `null` | Yes | Parent directory identity. `null` for root of a single-file index. |

`file_system.relative` always uses `/` separators regardless of platform. `file_system.absolute` (if present) uses the platform-native separator.

## Attribute Fields

The `attributes` object carries item-level flags and computed values.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `is_link` | `boolean` | Yes | `true` when the item is a symbolic link. |
| `storage_name` | `string` | Yes | Deterministic rename target: `id` + `.` + extension for files with extensions; `id` alone for directories or extensionless files. |

## Items Field

| Scenario | `items` value |
|----------|--------------|
| File | `null` |
| Directory (flat mode) | Array of immediate child `IndexEntry` objects |
| Directory (recursive mode) | Nested array of `IndexEntry` objects |

Children are ordered files-first, then directories, each group sorted by name (case-insensitive lexicographic). No `null` entries are permitted within the array.

## MetadataEntry

A single metadata record associated with an `IndexEntry`.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | `string` | Yes | `z`-prefixed (generated) or `y`-prefixed (sidecar). |
| `origin` | `string` (enum) | Yes | `"generated"` or `"sidecar"`. |
| `name` | `NameObject` | Yes | Source name. Both fields `null` for generated entries. |
| `hashes` | `HashSet` | Yes | Content hashes of the metadata payload. |
| `attributes` | `object` | Yes | Type classification, format, and transforms. |
| `data` | varies | Yes | The metadata content (type depends on `attributes.format`). |
| `encoding` | `EncodingObject` | Sidecar only | Source encoding metadata for text sidecars. Absent for binary sidecars or when encoding detection is disabled. |
| `file_system` | `object` | Sidecar only | Relative path to the original sidecar file. |
| `size` | `SizeObject` | Sidecar only | Size of the original sidecar file. |
| `timestamps` | `TimestampsObject` | Sidecar only | Timestamps of the original sidecar file. |

### Origin behavior

| `origin` | ID prefix | `file_system` | `size` | `timestamps` | Description |
|----------|-----------|---------------|--------|-------------|-------------|
| `"generated"` | `z` | Absent | Absent | Absent | Created by a tool during indexing (e.g., ExifTool). |
| `"sidecar"` | `y` | Present | Present | Present | Absorbed from an external metadata file. |

### MetadataEntry.attributes

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `type` | `string` | Yes | Semantic classification (see table below). |
| `format` | `string` (enum) | Yes | `"json"`, `"text"`, `"base64"`, or `"lines"`. |
| `transforms` | `array[string]` | Yes | Ordered transformation identifiers. Empty = stored as-is. |
| `source_media_type` | `string` | No | MIME type of original source when format differs. |
| `json_style` | `string` (enum) | No | Detected JSON formatting style of the original sidecar file: `"pretty"` (indented) or `"compact"` (minified). Present only when `format` is `"json"`. Used by the rollback engine to restore the original whitespace convention. |
| `json_indent` | `string` | No | Original JSON indentation string for hash-perfect restoration. Captures the exact whitespace used (e.g., `"  "` for 2 spaces, `"    "` for 4 spaces, `"\t"` for tabs). Present only when `format` is `"json"` and `json_style` is `"pretty"`. |
| `link_metadata` | `object` | No | Structured metadata extracted from a Windows `.lnk` shortcut file. Contains string-valued fields such as `target_path`, `working_directory`, `arguments`, `icon_location`, `description`, and `hotkey`. Present only when `type` is `"shortcut"` and the `LnkParse3` library is available. |

### Metadata type values

**Generated** (tool-prefixed):

| Type | Description |
|------|-------------|
| `exiftool.json_metadata` | EXIF/XMP/IPTC metadata from ExifTool. |

**Sidecar** (unprefixed):

| Type | Description |
|------|-------------|
| `description` | Text description files (e.g., youtube-dl `.description`). |
| `desktop_ini` | Windows `desktop.ini` files. |
| `generic_metadata` | Config/metadata files (`.cfg`, `.conf`, `.yaml`, `.meta`). |
| `hash` | Hash/checksum files (`.md5`, `.sha256`, `.crc32`). |
| `json_metadata` | JSON metadata (`.info.json`, `.meta.json`). |
| `link` | URL shortcuts (`.url`) and pointer files. Stored as full text content. |
| `shortcut` | Windows filesystem shortcuts (`.lnk`). Stored as Base64-encoded binary with optional structured `link_metadata`. |
| `screenshot` | Screen capture images. |
| `subtitles` | Subtitle tracks (`.srt`, `.sub`, `.vtt`, `.lrc`). |
| `thumbnail` | Thumbnail/cover images (`.cover`, `.thumb`). |
| `torrent` | Torrent/magnet link files. |
| `error` | Entry could not be read or classified. |

### Format values

| Format | `data` type | Description |
|--------|-------------|-------------|
| `"json"` | `object` or `array` | Parsed JSON structure. |
| `"text"` | `string` | UTF-8 text. |
| `"base64"` | `string` | Base64-encoded binary. |
| `"lines"` | `array[string]` | Line-oriented content. |

### Transform identifiers

| Transform | Description |
|-----------|-------------|
| `base64_encode` | Binary source was Base64-encoded. |
| `json_compact` | Source JSON was compacted. |
| `line_split` | Text split into line array. |
| `key_filter` | Keys removed from JSON object (not reversible). |

## Annotated Example

The following is a v3-compliant output entry for a text file with encoding metadata:

```json
{
  "schema_version": 3,
  "id": "yA8A8C089A6A8583B24C85F5A4A41F5AC",
  "id_algorithm": "md5",
  "type": "file",
  "name": {
    "text": "readme.txt",
    "hashes": {
      "md5": "3470F718BA9457335A59CE06239A9250",
      "sha256": "4DC834B31A1A5967F7A97AAD3D62EE91CCCC99B2034748135AFC193889B9A0EB"
    }
  },
  "extension": "txt",
  "mime_type": "text/plain",
  "size": {
    "text": "1.25 KB",
    "bytes": 1250
  },
  "hashes": {
    "md5": "A8A8C089A6A8583B24C85F5A4A41F5AC",
    "sha256": "B6BA115C2B43D87AADDF0060C44726E7AF1A12C9501FC63DE652A9517D7367DB"
  },
  "file_system": {
    "relative": ".test/readme.txt",
    "parent": {
      "id": "x3B4F479E9F880E438882FC34B67D352C",
      "name": {
        "text": ".test",
        "hashes": {
          "md5": "5E7576E3CD79114D46850714E998A3B0",
          "sha256": "5559EC61AE317CDF207A17666B01777B00DDF4AB1044BE5CC213DD3618E5F98C"
        }
      }
    }
  },
  "timestamps": {
    "created": { "iso": "2026-02-15T09:28:17.4084620-05:00", "unix": 1771165697408 },
    "modified": { "iso": "2023-08-03T19:47:44.0000000-04:00", "unix": 1691106464000 },
    "accessed": { "iso": "2026-02-15T09:28:18.1093900-05:00", "unix": 1771165698109 },
    "created_source": "birthtime"
  },
  "attributes": {
    "is_link": false,
    "storage_name": "yA8A8C089A6A8583B24C85F5A4A41F5AC.txt"
  },
  "items": null,
  "metadata": null,
  "encoding": {
    "bom": "utf-8",
    "line_endings": "crlf",
    "detected_encoding": "utf-8",
    "confidence": 0.99
  }
}
```

Key observations:

- `schema_version` is `3` — identifies this as a v3 entry
- `id` is `"y"` + the MD5 content hash (matching `id_algorithm: "md5"`)
- `storage_name` is `id` + `"."` + `extension`
- `name.hashes` are hashes of the UTF-8 bytes of `"readme.txt"` (different from content `hashes`)
- `file_system.relative` uses forward slashes regardless of platform
- `hashes.sha512` is absent (not `null`) because SHA-512 was not computed
- `timestamps.created_source` records that the creation time came from the filesystem's birth time
- `encoding` captures the BOM type, line-ending convention, character encoding, and detection confidence
- `items` and `metadata` are explicitly `null` (file with no metadata extraction requested)
- For binary files, `encoding` would be absent entirely

## v2 to v3 Migration

v3 is a strict superset of v2. All v2 required fields remain required in v3. The new fields are optional:

| New field | Location | Description |
|-----------|----------|-------------|
| `encoding` | `IndexEntry`, `MetadataEntry` | Source encoding metadata (BOM, line endings, charset). |
| `created_source` | `TimestampsObject` | Provenance of the `created` timestamp. |
| `json_indent` | `MetadataAttributes` | Original JSON indentation string for exact restoration. |

**Upgrading v2 → v3:** Change `schema_version` from `2` to `3`. Optionally populate the new fields. This is a lossless upgrade — no v2 data is discarded.

**Downgrading v3 → v2:** Strip `encoding`, `created_source`, and `json_indent`. Change `schema_version` from `3` to `2`. The encoding and provenance information is lost, but no v2 field is affected.

**Sidecar coexistence:** v1 (`_meta.json`), v2 (`_meta2.json`), and v3 (`_meta3.json`) sidecar files can coexist on disk. The exclusion logic ensures all three generations are excluded from directory traversal.

**Consumer guidance:** Consumers dispatching on `schema_version` should add a `case 3:` branch. The v3 field set is a strict superset of v2; consumers that parse v3 entries can reuse their v2 parsing logic and optionally inspect the new fields.

## Validation Examples

The [examples/](examples/) directory contains real-world output files:

- [flashplayer.exe_meta2.json](examples/flashplayer.exe_meta2.json)
- [deduplicated_meta2.json](examples/deduplicated_meta2.json) — demonstrates the `duplicates` field for provenance-preserving de-duplication

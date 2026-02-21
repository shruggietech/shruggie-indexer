# Schema Reference

The v2 output schema defines the structure of every index entry produced by shruggie-indexer. It consolidates related fields into logical sub-objects, eliminates redundancies from the legacy format, and includes a `schema_version` discriminator for forward compatibility.

## Canonical Schema

The authoritative machine-readable schema is hosted at:

- **Canonical URL:** [schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json](https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json)
- **Local copy:** [shruggie-indexer-v2.schema.json](shruggie-indexer-v2.schema.json)

## Design Principles

| Principle | Summary |
|-----------|---------|
| **P1 — Logical grouping** | Related fields are consolidated into typed sub-objects (`NameObject`, `SizeObject`, `TimestampPair`, `ParentObject`) instead of scattered across the top level. |
| **P2 — Single type discriminator** | A `type` enum (`"file"` or `"directory"`) replaces the legacy dual-boolean pattern. Combined with `schema_version`, consumers can route parsing unambiguously. |
| **P3 — Metadata provenance** | `MetadataEntry` includes `origin`, `file_system`, `size`, `timestamps`, and `attributes` — enough to reconstruct the original sidecar file for MetaMergeDelete reversal. |
| **P4 — No redundancy** | Dropped `BaseName` (derivable), `SHA1` (no unique purpose), and `Encoding` (.NET-specific). |
| **P5 — Explicit algorithm** | `id_algorithm` records which hash algorithm produced the `id`, eliminating reverse-matching. |

## Top-Level IndexEntry Fields

An `IndexEntry` is the root JSON object describing a single indexed file or directory.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `schema_version` | `integer` (const `2`) | Yes | Always `2`. Placed first in serialized output. |
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

`additionalProperties` is `false`. The `required` set:

```json
["schema_version", "id", "id_algorithm", "type", "name",
 "extension", "size", "hashes", "file_system", "timestamps", "attributes"]
```

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

### ParentObject

Parent directory identity and name.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | `string` | Yes | Parent directory identifier. `x`-prefixed. Pattern: `^x[0-9A-F]+$`. |
| `name` | `NameObject` | Yes | Parent directory name with hashes. |

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
| `link` | URL shortcuts (`.url`), filesystem shortcuts (`.lnk`). |
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

The following is a real v2-compliant output entry for an executable file:

```json
{
  "schema_version": 2,
  "id": "yA8A8C089A6A8583B24C85F5A4A41F5AC",
  "id_algorithm": "md5",
  "type": "file",
  "name": {
    "text": "flashplayer.exe",
    "hashes": {
      "md5": "3470F718BA9457335A59CE06239A9250",
      "sha256": "4DC834B31A1A5967F7A97AAD3D62EE91CCCC99B2034748135AFC193889B9A0EB"
    }
  },
  "extension": "exe",
  "mime_type": "application/octet-stream",
  "size": {
    "text": "15.28 MB",
    "bytes": 16027648
  },
  "hashes": {
    "md5": "A8A8C089A6A8583B24C85F5A4A41F5AC",
    "sha256": "B6BA115C2B43D87AADDF0060C44726E7AF1A12C9501FC63DE652A9517D7367DB"
  },
  "file_system": {
    "relative": ".test/flashplayer.exe",
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
    "accessed": { "iso": "2026-02-15T09:28:18.1093900-05:00", "unix": 1771165698109 }
  },
  "attributes": {
    "is_link": false,
    "storage_name": "yA8A8C089A6A8583B24C85F5A4A41F5AC.exe"
  },
  "items": null,
  "metadata": null
}
```

Key observations:

- `id` is `"y"` + the MD5 content hash (matching `id_algorithm: "md5"`)
- `storage_name` is `id` + `"."` + `extension`
- `name.hashes` are hashes of the UTF-8 bytes of `"flashplayer.exe"` (different from content `hashes`)
- `file_system.relative` uses forward slashes regardless of platform
- `hashes.sha512` is absent (not `null`) because SHA-512 was not computed
- `items` and `metadata` are explicitly `null` (file with no metadata extraction requested)

## Validation Examples

The [examples/](examples/) directory contains real-world v2-compliant output files:

- [flashplayer.exe_meta2.json](examples/flashplayer.exe_meta2.json)

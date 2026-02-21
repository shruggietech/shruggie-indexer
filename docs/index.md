# shruggie-indexer

**shruggie-indexer** produces structured JSON index entries for files and directories, capturing hash-based identities, filesystem timestamps, EXIF metadata, sidecar metadata, and storage attributes. Every entry conforms to the [v2 JSON Schema](schema/shruggie-indexer-v2.schema.json) and includes deterministic, content-derived identifiers that are stable across runs and platforms. The tool ships as a CLI utility, a Python library, and a standalone GUI application — all powered by the same core indexing engine.

## Key Features

**Deterministic hash-based identity** — Each file receives a unique identifier derived from its content hashes (MD5 or SHA-256), prefixed by type (`y` for files, `x` for directories). The same file always produces the same ID.

**Multi-algorithm hashing** — MD5 and SHA-256 are computed in a single streaming pass over each file. Optional SHA-512 is available for high-strength verification workflows.

**EXIF metadata extraction** — Embedded EXIF, XMP, and IPTC metadata is extracted via [ExifTool](https://exiftool.org/) using a persistent batch process for high throughput. When ExifTool is not installed, all other features continue to work normally.

**Sidecar metadata discovery and merging** — Automatically discovers sidecar files (`.info.json`, `.description`, thumbnails, subtitles, hash files, and more) alongside indexed items. Sidecar content can be merged into parent entries or merged-and-deleted with full provenance tracking for reversal.

**Configurable TOML-based settings** — All behavior is configurable through a layered system: built-in defaults, user config files, project-local config files, and CLI flags. Sidecar patterns, exclusion lists, and extension validation are all user-modifiable without editing source code.

**Cross-platform** — Windows, Linux, and macOS are fully supported with platform-aware handling of timestamps, symlinks, and filesystem attributes.

**Structured v2 JSON output** — Output follows a well-defined schema with typed sub-objects (`HashSet`, `NameObject`, `SizeObject`, `TimestampPair`, `TimestampsObject`, `ParentObject`) and a `schema_version` discriminator for forward compatibility.

## Quick Example

Index a file and print the result to stdout:

```bash
shruggie-indexer path/to/file.exe
```

Output (abbreviated):

```json
{
  "schema_version": 2,
  "id": "yA8A8C089A6A8583B24C85F5A4A41F5AC",
  "id_algorithm": "md5",
  "type": "file",
  "name": {
    "text": "file.exe",
    "hashes": { "md5": "...", "sha256": "..." }
  },
  "extension": "exe",
  "size": { "text": "15.28 MB", "bytes": 16027648 },
  "hashes": { "md5": "A8A8C089...", "sha256": "B6BA115C..." },
  "file_system": {
    "relative": "file.exe",
    "parent": { "id": "x3B4F479E...", "name": { "text": "my-dir", "hashes": { "...": "..." } } }
  },
  "timestamps": {
    "created":  { "iso": "2026-02-15T09:28:17.408462-05:00", "unix": 1771165697408 },
    "modified": { "iso": "2023-08-03T19:47:44.000000-04:00", "unix": 1691106464000 },
    "accessed": { "iso": "2026-02-15T09:28:18.109390-05:00", "unix": 1771165698109 }
  },
  "attributes": { "is_link": false, "storage_name": "yA8A8C089A6A8583B24C85F5A4A41F5AC.exe" },
  "items": null,
  "metadata": null,
  "mime_type": "application/octet-stream"
}
```

## Documentation Sections

- **[Getting Started](getting-started/installation.md)** — Install shruggie-indexer, set up ExifTool, and index your first file in minutes.
- **[User Guide](user-guide/index.md)** — Complete CLI reference, configuration guide, Python API documentation, and platform-specific notes.
- **[Schema Reference](schema/index.md)** — Full v2 JSON Schema documentation with type definitions, field tables, and annotated examples.
- **[Porting Reference](porting-reference/index.md)** — Historical reference materials from the original PowerShell implementation.
- **[Changelog](changelog.md)** — Version history and release notes.

## Quick Links

- [GitHub Repository](https://github.com/shruggietech/shruggie-indexer)
- [V2 JSON Schema (canonical)](https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json)
- [Technical Specification](https://github.com/shruggietech/shruggie-indexer/blob/main/shruggie-indexer-spec.md)

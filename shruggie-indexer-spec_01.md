# Shruggie-Indexer — Technical Specification

**Project:** `shruggie-indexer`
**Repository:** [shruggietech/shruggie-indexer](https://github.com/shruggietech/shruggie-indexer)
**License:** Apache 2.0 ([full text](https://www.apache.org/licenses/LICENSE-2.0))
**Version:** 0.1.0 (MVP)
**Author:** William Thompson / ShruggieTech LLC
**Date:** 2026-02-15
**Status:** DRAFT
**Audience:** AI-first, Human-second

---

## 1. Document Information

### 1.1. Purpose and Audience

This document is the authoritative technical specification for `shruggie-indexer`, a Python reimplementation of the `MakeIndex` function and its full dependency tree from the original PowerShell-based pslib library. It serves as the single source of truth for building the tool from an empty repository to a release-ready codebase, validating its output against the behavior of the original implementation, and maintaining it as the project evolves.

The specification is written for an **AI-first, Human-second** audience. Its primary consumers are AI implementation agents operating within isolated context windows during sprint-based development. Every section is designed to provide sufficient detail for an AI agent to produce correct, complete code without requiring access to the original PowerShell source or interactive clarification. Human developers and maintainers are the secondary audience — the document is equally valid as a traditional engineering reference, but its level of explicitness and redundancy reflects the needs of stateless AI execution contexts.

This specification describes:

- The complete behavioral contract of the tool, including all input modes, output schemas, configuration surfaces, and edge cases.
- The architectural decisions that govern the Python port, including where and why it deviates from the original implementation.
- The repository structure, packaging, testing strategy, and platform portability requirements necessary to ship the tool as a cross-platform CLI utility, Python library, and standalone GUI application.

This specification does NOT serve as a tutorial, user guide, or API reference. Those artifacts are derived from this document but are separate deliverables.

### 1.2. Scope

#### In Scope

This specification covers the following:

- **Core indexing engine.** The complete Python reimplementation of the `MakeIndex` function — filesystem traversal, file and directory identity generation (hashing), symlink detection, timestamp extraction and conversion, EXIF/embedded metadata extraction via `exiftool`, sidecar metadata file discovery and parsing, index entry construction, and JSON output serialization.

- **All original dependencies.** The eight external pslib functions consumed by `MakeIndex` (`Base64DecodeString`, `Date2UnixTime`, `DirectoryId`, `FileId`, `MetaFileRead`, `TempOpen`, `TempClose`, `Vbs`) and the two external binaries (`exiftool`, `jq`). Where original dependencies are eliminated by Python's standard library or architectural improvements, the specification documents the elimination rationale and replacement strategy.

- **Output schema (v2).** The complete JSON output schema for index entries as defined by the [shruggie-indexer v2 schema](https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json). The v2 schema is a ground-up restructuring of the original MakeIndex v1 output format — it consolidates related fields into logical sub-objects (e.g., `TimestampPair`, `NameObject`, `HashSet`, `SizeObject`), eliminates redundant fields, adds explicit provenance tracking for metadata entries, adds a `schema_version` discriminator, and provides the structural foundation for MetaMergeDelete reversal operations. The v1 schema (`MakeIndex_OutputSchema.json`) remains available as a porting reference for understanding the original implementation's output, but the v2 schema is the target for all new implementation work. A v1-to-v2 migration utility for converting existing v1 index assets to the v2 format is planned but deferred to post-MVP.

- **MetadataFileParser configuration.** The `$global:MetadataFileParser` object from the original pslib library is the source of truth for sidecar metadata file discovery and classification. It defines the regex patterns used to identify sidecar file types (Description, DesktopIni, GenericMetadata, Hash, JsonMetadata, Link, Screenshot, Subtitles, Thumbnail, Torrent), the per-type behavioral attributes (expected data formats, valid parent relationships), the exiftool file-type exclusion list, the extension group classifications (Archive, Audio, Font, Image, Link, Subtitles, Video), and the indexer include/exclude patterns. The original regex patterns in this object have been carefully crafted — including an extensive BCP 47 language code alternation for subtitle detection — and MUST be ported to Python with deliberate care to preserve their exact matching behavior. The isolated reference script `MakeIndex_MetadataFileParser_.ps1` (see §1.5) provides the complete object definition for porting reference.

- **CLI interface.** The command-line interface exposing all indexing operations — target selection, output mode control, metadata processing options, rename operations, ID type selection, and verbosity/logging configuration.

- **Python API.** The public programmatic interface for consumers who import `shruggie_indexer` as a library rather than invoking it from the command line.

- **Graphical user interface.** A standalone desktop GUI application built with CustomTkinter, modeled after the `shruggie-feedtools` GUI (see §1.5, External References). The GUI serves as a visual frontend to the same library code used by the CLI. It is shipped as a separate release artifact alongside the CLI executable. The full GUI specification is defined in a later section of this document.

- **Configuration system.** The externalized configuration architecture that replaces the original's hardcoded `$global:MetadataFileParser` object, including default values, file format, and override/merge behavior.

- **Logging and diagnostics.** The structured logging system that replaces the original's `Vbs` function, including logger hierarchy, log levels, session identifiers, and output destinations.

- **Packaging and distribution.** `pyproject.toml` configuration, entry points, standalone executable builds via PyInstaller, and release artifact definitions.

- **Testing strategy.** Unit tests, integration tests, output schema conformance tests, cross-platform test matrix, backward compatibility validation, and performance benchmarks.

- **Platform portability.** Cross-platform design principles and platform-specific considerations for Windows, Linux, and macOS — including filesystem behavior differences, creation time portability, and symlink/reparse point handling.

- **Security and safety.** Symlink traversal safety, path validation, temporary file handling, metadata merge-delete safeguards, and large file/deep recursion handling.

- **Performance considerations.** Multi-algorithm hashing in a single pass, chunked file reading, large directory tree handling, JSON serialization performance, and exiftool invocation strategy.

#### Out of Scope

This specification explicitly does NOT cover:

- **The broader pslib library.** Only the `MakeIndex` function and its dependency tree are ported. The hundreds of other functions in `main.ps1` (e.g., `Add`, `ApkDexDump`, `ChromeBookmark`, etc.) are unrelated to this project.

- **The `Encoding` output field.** The original v1 output schema includes an `Encoding` key containing detailed file encoding properties derived from BOM byte inspection. This field is intentionally dropped from the port and does not appear in the v2 schema. The `GetFileEncoding` sub-function and all related logic are not carried forward. See §5.9 for the full rationale.

- **The v1-to-v2 migration utility.** A migration script for converting existing v1 index assets to the v2 schema format is a planned deliverable but is deferred to post-MVP. It is not part of the v0.1.0 release.

- **The original PowerShell source code.** The original `main.ps1` is closed-source and is not included in the `shruggie-indexer` repository. The original source code for the `MakeIndex` function — including its complete function body, parameter block, and all nested sub-functions — SHALL NOT be included in the repository in any form (neither as a reference file, nor embedded in documentation, nor as inline code comments). All behavioral knowledge required to implement the port is captured in this specification and the reference documents listed in §1.5. An implementer MUST NOT require access to `main.ps1` or to the `MakeIndex` function source.

### 1.3. Document Maintenance

This specification is maintained as a living document alongside the codebase. It is the authoritative reference for the project's intended behavior and architecture. When the specification and the implementation disagree, the specification is presumed correct unless a deliberate amendment has been made.

Updates to this document SHOULD be committed alongside the code changes they describe. Significant architectural changes — such as adding a new output field, changing the CLI interface, or altering the configuration format — MUST be reflected in this specification before or concurrent with the implementation.

The document header's **Date** field reflects the date of the most recent substantive revision. The **Status** field uses one of the following values:

| Status | Meaning |
|--------|---------|
| `DRAFT` | The specification is under active development. Sections may be incomplete or subject to change. |
| `REVIEW` | The specification is believed complete and is undergoing review for correctness and consistency. |
| `APPROVED` | The specification has been reviewed and accepted as the implementation target. |
| `AMENDED` | The specification has been modified after initial approval to reflect post-release changes. |

### 1.4. Conventions Used in This Document

#### Requirement Level Keywords

This specification uses the keywords defined in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) to indicate requirement levels:

| Keyword | Meaning |
|---------|---------|
| **MUST** / **MUST NOT** | An absolute requirement or prohibition. Implementations that violate a MUST or MUST NOT are non-conformant. |
| **SHALL** / **SHALL NOT** | Synonymous with MUST / MUST NOT. |
| **SHOULD** / **SHOULD NOT** | A strong recommendation. There may be valid reasons to deviate, but the implications must be understood and the deviation must be deliberate. |
| **MAY** | An item is truly optional. An implementation may include or omit the feature without affecting conformance. |

These keywords are capitalized when used in their RFC 2119 sense. Lowercase usage of these words carries their ordinary English meaning.

#### Typographic Conventions

- `Monospace text` denotes code identifiers, file paths, CLI flags, configuration keys, and literal values.
- **Bold text** denotes emphasis or key terms being defined.
- *Italic text* denotes document titles, variable placeholders, or first use of a defined term.
- `§N.N` denotes a cross-reference to another section of this specification (e.g., §5.2 refers to section 5.2, "Top-Level IndexEntry Fields").

#### Terminology

| Term | Definition |
|------|------------|
| **Original** | The PowerShell implementation of `MakeIndex` and its dependency tree within the pslib library (`main.ps1`). Used when describing behavior being ported or intentionally changed. |
| **Port** | The Python reimplementation described by this specification. Synonymous with `shruggie-indexer`. |
| **v1 schema** | The original MakeIndex output format as defined by `MakeIndex_OutputSchema.json`. Used as a porting reference only. The port does not target v1 output. |
| **v2 schema** | The restructured output format defined by `shruggie-indexer-v2.schema.json`. This is the target schema for all implementation work in the port. |
| **Index entry** | A single structured data object representing a file or directory in the v2 output schema. Defined in §5. |
| **Sidecar file** | An external metadata file that lives alongside the file it describes, identified by filename pattern matching (e.g., `photo.jpg` may have a sidecar `photo_meta2.json`). |
| **Content hash** | A cryptographic hash computed from the byte content of a file. Used for file identity. Directories do not have content hashes. |
| **Name hash** | A cryptographic hash computed from the UTF-8 encoded bytes of a file or directory name string. Used for directory identity and as a secondary identifier for files. |
| **HashSet** | A v2 schema object containing hash digests for a given input. Always includes `md5` and `sha256`; optionally includes `sha512`. Replaces the v1 schema's separate `Ids`, `NameHashes`, `ContentHashes`, `ParentIds`, and `ParentNameHashes` fields. |
| **NameObject** | A v2 schema object pairing a `text` string with its `hashes` (a HashSet). Replaces the v1 pattern of separate `Name`/`NameHashes` and `ParentName`/`ParentNameHashes` field pairs. |
| **TimestampPair** | A v2 schema object containing both an `iso` (ISO 8601 string) and `unix` (milliseconds since epoch) representation of a single timestamp. Replaces the v1 pattern of separate `TimeAccessed`/`UnixTimeAccessed` field pairs. |
| **Identity (`id`)** | The primary unique identifier assigned to an index entry, selected from one of the computed hash algorithms (MD5 or SHA256) based on the `id_algorithm` field. Prefixed with `y` for files, `x` for directories, `z` for generated metadata entries. |
| **StorageName (`storage_name`)** | The deterministic filename derived from an item's `id` and extension (e.g., `yA8A8C089A6A8583B24C85F5A4A41F5AC.exe` for a file, `x3B4F479E9F880E438882FC34B67D352C` for a directory). Used when the rename operation is active. |
| **MetaMerge** | The operation of folding sidecar metadata into the parent item's `metadata` array during indexing. |
| **MetaMergeDelete** | An extension of MetaMerge that queues the original sidecar files for deletion after their content has been merged into the parent item's metadata. The v2 schema's sidecar metadata entries carry sufficient filesystem provenance (path, size, timestamps) to support reversal of this operation. |
| **In-place write** | Writing individual `_meta2.json` or `_directorymeta2.json` sidecar files alongside each processed item, as opposed to writing a single aggregate output file. |
| **MetadataFileParser** | The configuration object governing sidecar metadata file discovery and classification. In the original, this is the `$global:MetadataFileParser` PowerShell ordered hashtable. In the port, it is externalized into a typed configuration structure. See §7. |

#### Code Examples

Code examples in this specification use Python syntax unless otherwise noted. Examples marked with `# Original (PowerShell)` show the original implementation's approach for comparison purposes. Code examples are illustrative — they demonstrate intent and structure but are not necessarily the exact implementation. The implementation SHOULD follow the examples' intent while MAY differing in specific variable names, error handling details, or stylistic choices.

### 1.5. Reference Documents

The following documents inform this specification. All repository paths are relative to the repository root and resolve within the live repository.

#### Planning

| Document | Path | Description |
|----------|------|-------------|
| Implementation Plan | [`./shruggie-indexer-plan.md`](./shruggie-indexer-plan.md) | Sprint-based implementation plan for building the tool from an empty repository to a release-ready codebase. |

#### Output Schema

| Document | Location | Description |
|----------|----------|-------------|
| v2 Schema (canonical) | [schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json](https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json) | The canonical JSON Schema definition for the v2 index entry output format. This is the target schema for all implementation work. Defines all fields, types, nullability, required properties, definitions (`NameObject`, `HashSet`, `SizeObject`, `TimestampPair`, `TimestampsObject`, `ParentObject`, `MetadataEntry`), and structural constraints. §5 of this specification interprets and extends the schema with behavioral guidance but does not supersede it for field-level definitions. |
| v1 Schema (porting reference) | [`./docs/porting-reference/MakeIndex_OutputSchema.json`](./docs/porting-reference/MakeIndex_OutputSchema.json) | The JSON Schema definition for the original MakeIndex v1 output format. Retained as a porting reference for understanding the original implementation's output structure and for informing the eventual v1-to-v2 migration utility. The port does NOT target this schema. |

#### Operations Reference

| Document | Path | Description |
|----------|------|-------------|
| Operations Catalog | [`./docs/porting-reference/MakeIndex_OperationsCatalog.md`](./docs/porting-reference/MakeIndex_OperationsCatalog.md) | Categorized inventory of all logical operations in the original `MakeIndex` and its dependency tree, mapped to recommended Python modules with improvement notes. The primary architectural reference for the port. |

#### Configuration Reference

| Document | Path | Description |
|----------|------|-------------|
| MetadataFileParser Object | [`./docs/porting-reference/MakeIndex(MetadataFileParser).ps1`](./docs/porting-reference/MakeIndex%28MetadataFileParser%29.ps1) | Isolated PowerShell script containing the complete `$global:MetadataFileParser` object definition. This is the source of truth for sidecar metadata file discovery and classification — including all regex identification patterns, per-type behavioral attributes, exiftool exclusion lists, extension group classifications, and indexer include/exclude patterns. The regex patterns in this object (particularly the BCP 47 language code alternation for subtitle detection) have been carefully crafted and MUST be ported to Python with deliberate attention to preserving their exact matching semantics. See §7.3 for the full porting guidance. |

#### Dependency Catalogs

Each dependency catalog documents a single function from the original pslib library that `MakeIndex` depends on — its parameters, internal sub-functions, external calls, and behavioral contract.

| Document | Path | Original Function |
|----------|------|-------------------|
| Base64DecodeString | [`./docs/porting-reference/Base64DecodeString_DependencyCatalog.md`](./docs/porting-reference/Base64DecodeString_DependencyCatalog.md) | Decodes Base64-encoded and URL-encoded strings. Eliminated in the port — exiftool arguments are passed directly. |
| Date2UnixTime | [`./docs/porting-reference/Date2UnixTime_DependencyCatalog.md`](./docs/porting-reference/Date2UnixTime_DependencyCatalog.md) | Converts formatted date strings to Unix timestamps in milliseconds. Eliminated in the port — timestamps are derived directly from stat results. |
| DirectoryId | [`./docs/porting-reference/DirectoryId_DependencyCatalog.md`](./docs/porting-reference/DirectoryId_DependencyCatalog.md) | Computes hash-based identity for directories using the two-layer `hash(hash(name) + hash(parentName))` scheme. |
| FileId | [`./docs/porting-reference/FileId_DependencyCatalog.md`](./docs/porting-reference/FileId_DependencyCatalog.md) | Computes hash-based identity for files from content hashes (or name hashes for symlinks). |
| MakeIndex | [`./docs/porting-reference/MakeIndex_DependencyCatalog.md`](./docs/porting-reference/MakeIndex_DependencyCatalog.md) | The top-level function being ported. Orchestrates traversal, identity generation, metadata extraction, and output routing. |
| MetaFileRead | [`./docs/porting-reference/MetaFileRead_DependencyCatalog.md`](./docs/porting-reference/MetaFileRead_DependencyCatalog.md) | Reads and parses sidecar metadata files with format-specific handling (JSON, text, binary, subtitles, hash files, URL/LNK shortcuts). |
| TempOpen | [`./docs/porting-reference/TempOpen_DependencyCatalog.md`](./docs/porting-reference/TempOpen_DependencyCatalog.md) | Creates temporary files with UUID-based naming. Eliminated in the port — replaced by `tempfile` if needed at all. |
| TempClose | [`./docs/porting-reference/TempClose_DependencyCatalog.md`](./docs/porting-reference/TempClose_DependencyCatalog.md) | Deletes temporary files by path. Eliminated in the port — replaced by context manager cleanup. |
| Vbs | [`./docs/porting-reference/Vbs_DependencyCatalog.md`](./docs/porting-reference/Vbs_DependencyCatalog.md) | Structured logging with severity levels, caller identification, session IDs, and colorized console output. Replaced by Python's `logging` framework. |

#### External References

| Document | URL | Description |
|----------|-----|-------------|
| RFC 2119 | [https://www.rfc-editor.org/rfc/rfc2119](https://www.rfc-editor.org/rfc/rfc2119) | Defines the requirement level keywords (MUST, SHOULD, MAY, etc.) used throughout this specification. |
| JSON Schema Draft-07 | [https://json-schema.org/draft-07/schema#](https://json-schema.org/draft-07/schema#) | The JSON Schema dialect used by both the v1 and v2 output schemas. |
| ExifTool | [https://exiftool.org/](https://exiftool.org/) | The external binary dependency for embedded metadata extraction. |
| shruggie-feedtools | [https://github.com/shruggietech/shruggie-feedtools](https://github.com/shruggietech/shruggie-feedtools) | A sibling ShruggieTech project whose specification, repository layout, and GUI design serve as the primary architectural and visual reference for `shruggie-indexer`. The `shruggie-indexer` GUI is modeled directly after the `shruggie-feedtools` GUI (CustomTkinter, two-panel layout, dark theme, shared font stack and appearance conventions). |

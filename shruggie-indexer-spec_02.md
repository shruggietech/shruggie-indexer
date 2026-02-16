## 2. Project Overview

### 2.1. Project Identity

| Field | Value |
|-------|-------|
| Project name | `shruggie-indexer` |
| Package name (PyPI) | `shruggie-indexer` |
| Import name (Python) | `shruggie_indexer` |
| Repository | [shruggietech/shruggie-indexer](https://github.com/shruggietech/shruggie-indexer) |
| Organization | ShruggieTech LLC |
| License | Apache 2.0 ([full text](https://www.apache.org/licenses/LICENSE-2.0)) |
| License file | `LICENSE` (full Apache 2.0 text, obtained from [https://www.apache.org/licenses/LICENSE-2.0.txt](https://www.apache.org/licenses/LICENSE-2.0.txt)) |
| Build system | `hatchling` |
| Current version | 0.1.0 (MVP) |
| CLI entry point | `shruggie-indexer = "shruggie_indexer.cli.main:main"` |
| Module entry point | `python -m shruggie_indexer` (via `__main__.py`) |

`shruggie-indexer` is a standalone project within the ShruggieTech tool family. It shares no code with `shruggie-feedtools` or any other ShruggieTech project at runtime, but it follows the same repository conventions, packaging patterns, build tooling, and GUI design language established by `shruggie-feedtools` (see §1.5, External References). Where this specification does not explicitly define a convention — such as `pyproject.toml` field ordering, ruff configuration, or venv setup scripting — the `shruggie-feedtools` repository serves as the normative reference for project scaffolding.

This project is not published to PyPI. End users download pre-built executables from [GitHub Releases](https://github.com/shruggietech/shruggie-indexer/releases). The `pip install -e` workflow is for contributors setting up a local development environment only.

### 2.2. Relationship to the Original Implementation

`shruggie-indexer` is a ground-up Python reimplementation of the `MakeIndex` function from the PowerShell-based pslib library (`main.ps1`). The relationship is behavioral, not structural — the port targets the same logical outcomes (filesystem indexing with hash-based identity, metadata extraction, and structured JSON output) but makes no attempt to mirror the original's code organization, naming patterns, or internal architecture.

The original `MakeIndex` is one function among hundreds in `main.ps1`, a monolithic 17,000+ line PowerShell script that serves as a general-purpose utility library. `MakeIndex` itself spans approximately 1,500 lines and defines 20+ nested sub-functions inline. It depends on eight additional top-level pslib functions (`Base64DecodeString`, `Date2UnixTime`, `DirectoryId`, `FileId`, `MetaFileRead`, `TempOpen`, `TempClose`, `Vbs`) and two external binaries (`exiftool`, `jq`). The combined dependency tree — including all sub-functions defined within those eight dependencies — encompasses roughly 60 discrete code units.

The port carries forward the original's core behavioral contract: given a target path (file or directory), produce a JSON index entry containing hash-based identities, filesystem metadata, timestamps, embedded EXIF data, and sidecar metadata — all structured according to a defined output schema. Everything else — the language, the architecture, the output schema version, the dependency set, the configuration model, and the platform scope — is reengineered for the Python ecosystem and cross-platform execution.

The original PowerShell source code is closed-source and is not included in the `shruggie-indexer` repository. All behavioral knowledge required to implement the port is captured in this specification and the reference documents listed in §1.5. An implementer MUST NOT require access to `main.ps1` or to the `MakeIndex` function source. See §1.2 (Out of Scope) for the full policy on original source handling.

### 2.3. Design Goals and Non-Goals

#### Design Goals

**G1 — Behavioral fidelity.** For any input path that the original `MakeIndex` can process, the port MUST produce a v2 index entry whose semantic content is equivalent to the original's v1 output — after accounting for the documented schema restructuring (§5) and the intentional deviations listed in §2.6. "Semantic equivalence" means that the same file produces the same hash-based identity, the same timestamp values (within platform precision limits), the same embedded metadata extraction results, and the same sidecar metadata discovery and parsing outcomes. It does NOT mean byte-identical JSON output; the v2 schema reorganizes fields into sub-objects and adds fields that did not exist in v1.

**G2 — Cross-platform portability.** The original runs only on Windows due to its reliance on PowerShell, .NET Framework types, `certutil`, Windows-specific path handling, and hardcoded Windows filesystem assumptions. The port MUST run on Windows, Linux, and macOS without platform-specific code branches in the core indexing engine. Platform-specific behavior (such as creation time availability or symlink semantics) is handled through documented abstractions with explicit fallback strategies, not through conditional imports or OS-detection switches in the hot path. The only external binary dependency — `exiftool` — is itself cross-platform.

**G3 — Three delivery surfaces from a single codebase.** The tool ships as a CLI utility, a Python library, and a standalone GUI application. All three surfaces consume the same core indexing engine. The CLI and GUI are thin presentation layers over the library API. No indexing logic lives in the CLI argument parser or the GUI event handlers. This is the same architecture used by `shruggie-feedtools`.

**G4 — Externalized, user-modifiable configuration.** The original hardcodes all configuration in the `$global:MetadataFileParser` PowerShell object and in various literal values scattered across the function body (exclusion lists, extension validation regex, exiftool argument strings, system directory filters). The port externalizes all such values into a typed configuration system with sensible defaults, a documented configuration file format, and a merge/override mechanism for user customization. A user SHOULD be able to add a new sidecar metadata pattern, extend the exiftool exclusion list, or modify the filesystem exclusion filters without editing source code.

**G5 — Dependency minimization.** The port's core indexing engine MUST run using only the Python standard library plus `exiftool` as an external binary. No third-party Python packages are required for the core pipeline. Third-party packages (such as `click` for CLI, `orjson` for fast serialization, `PyExifTool` for batch performance, `tqdm` or `rich` for progress reporting, and `customtkinter` for the GUI) are used as optional enhancements and are isolated behind import guards or declared as extras in `pyproject.toml`.

**G6 — AI-agent implementability.** Every section of this specification provides sufficient detail for an AI implementation agent to produce correct, complete code for the described component within a single context window, without interactive clarification or access to the original source. Cross-references between sections are explicit. Ambiguous behavioral questions are resolved in the specification text rather than left to implementer judgment. This is the document's primary design constraint and the reason for its level of explicitness.

**G7 — Structured, v2-native output.** The port targets the v2 output schema exclusively. The v2 schema consolidates the v1 schema's flat field layout into logical sub-objects (`NameObject`, `HashSet`, `SizeObject`, `TimestampPair`, `TimestampsObject`, `ParentObject`, `MetadataEntry`), eliminates redundant fields, adds a `schema_version` discriminator, and provides the structural foundation for MetaMergeDelete reversal. The port does not produce v1 output. A v1-to-v2 migration utility is a planned post-MVP deliverable (see §1.2, Out of Scope).

#### Non-Goals

**NG1 — Full pslib port.** Only the `MakeIndex` function and its dependency tree are ported. The hundreds of other functions in `main.ps1` (`Add`, `ApkDexDump`, `ChromeBookmark`, etc.) are unrelated to this project.

**NG2 — Backward-compatible v1 JSON output.** The port does not produce output conforming to the v1 schema (`MakeIndex_OutputSchema.json`). Consumers of existing v1 index assets will need the planned v1-to-v2 migration utility (post-MVP) or must adapt their parsers to the v2 schema.

**NG3 — Drop-in PowerShell replacement.** The port does not replicate the original's PowerShell parameter interface, its `-OutputObject` / `-OutputJson` switch pattern, or its integration with the pslib global state (`$global:MetadataFileParser`, `$global:DeleteQueue`, `$LibSessionID`). The Python tool has its own CLI, API, and configuration system designed for the Python ecosystem.

**NG4 — Real-time or watch-mode indexing.** The tool processes a target path and produces output. It does not monitor the filesystem for changes or re-index automatically. File-watching functionality is a potential future enhancement (see §17) but is not part of the MVP.

**NG5 — Database or server backend.** Index output is written to JSON files or stdout. The tool does not write to databases, expose an HTTP API, or provide query functionality over indexed data. Downstream consumers ingest the JSON output using their own storage and query infrastructure.

**NG6 — Metadata editing or file transformation.** The tool reads and indexes filesystem content. It does not modify file contents, edit EXIF tags, transcode media, or perform any write operation on the indexed files themselves. The rename operation (§6.10) renames files to their `storage_name` but does not alter their content. The MetaMergeDelete operation deletes sidecar files after merging but does not modify the parent file.

### 2.4. Platform and Runtime Requirements

#### Target Platforms

| Platform | Status | Notes |
|----------|--------|-------|
| Windows 10/11 x64 | Primary | The original's sole platform. Primary target for standalone `.exe` builds via PyInstaller. |
| Linux x64 (Ubuntu 22.04+, Fedora 38+) | Supported | Full feature parity. CI test matrix includes Ubuntu. |
| macOS x64 / ARM64 (13 Ventura+) | Supported | Full feature parity. `st_birthtime` available for true creation time. CI test matrix includes macOS. |

"Primary" means this platform receives standalone executable artifacts in every release and is the first target for manual testing and user-facing documentation. "Supported" means full feature parity, inclusion in the CI test matrix, and bug fixes for platform-specific issues, but standalone executables MAY lag behind the primary platform in release cadence.

#### Required External Binary

| Binary | Version | Purpose | Installation |
|--------|---------|---------|-------------|
| `exiftool` | ≥ 12.0 | Embedded EXIF/XMP/IPTC metadata extraction | Must be installed separately and available on the system `PATH`. See [https://exiftool.org/](https://exiftool.org/) for platform-specific installation instructions. |

`exiftool` is the only external binary dependency. The original also required `jq` for JSON processing and `certutil` for Base64 encoding; both are eliminated in the port (see §2.6). The tool MUST verify `exiftool` availability at startup and produce a clear, actionable error message if it is not found. If `exiftool` is missing, operations that require it (embedded metadata extraction) MUST fail gracefully with a warning, while operations that do not require it (hashing, timestamp extraction, sidecar metadata reading) MUST continue to function normally.

#### Runtime Environment

The tool does not require administrator/root privileges for any operation. It operates entirely within the permissions of the invoking user. Filesystem paths that the user cannot read produce per-item warnings and are skipped rather than causing the entire indexing operation to fail.

### 2.5. Python Version Requirements

| Requirement | Value | Rationale |
|-------------|-------|-----------|
| Minimum Python version | `>=3.12` | Matches the `shruggie-feedtools` baseline. Provides `tomllib` in the standard library (3.11+), improved `pathlib` semantics, enhanced `dataclasses` features, and current `typing` module capabilities. |
| Target Python version for development | 3.12 | The `ruff` target version, CI primary version, and PyInstaller build version. |
| Maximum Python version | No upper bound | The tool SHOULD work on 3.13+ without modification. The `pyproject.toml` specifies `requires-python = ">=3.12"` with no upper constraint. |

The `>=3.12` floor is a deliberate alignment with the ShruggieTech project family. Key standard library features that justify this floor include `tomllib` for TOML configuration parsing without a third-party dependency, `pathlib.Path.walk()` (3.12+) as a modern alternative to `os.walk()`, improved error messages in `argparse` and `dataclasses`, and PEP 695 type parameter syntax support.

The implementation MUST NOT use features introduced after Python 3.12 without a documented compatibility fallback, to ensure the tool works on the minimum supported version.

### 2.6. Intentional Deviations from the Original

This section catalogs the architectural and behavioral decisions where the port deliberately diverges from the original implementation. Each deviation is identified by a short code (e.g., `DEV-01`) for cross-referencing from other sections of this specification. The full technical details of each deviation are developed in the referenced sections; this subsection provides the summary rationale and serves as a navigational index.

#### DEV-01 — Unified hashing module

**Original:** Hashing logic is independently reimplemented in four separate locations — `FileId` (8 sub-functions), `DirectoryId` (5 sub-functions), `ReadMetaFile` (2 sub-functions), and `MetaFileRead` (2+ sub-functions) — each repeating the same `Create() → ComputeHash() → ToString() → replace('-','')` pattern with no shared code.

**Port:** A single hashing utility module provides `hash_file()` and `hash_string()` functions consumed by all callers. This eliminates approximately 17 redundant sub-functions. See §6.3.

#### DEV-02 — All four hash algorithms computed by default

**Original:** Only MD5 and SHA256 are computed at runtime, despite the output schema defining fields for SHA1 and SHA512. The additional algorithm fields are left `$null` in practice.

**Port:** All four algorithms (MD5, SHA1, SHA256, SHA512) are computed in every indexing pass. Because `hashlib` can feed the same byte chunks to multiple hash objects in a single file read, the marginal cost of additional algorithms is near-zero. This fills previously-empty schema fields and enables downstream consumers to select their preferred algorithm without re-indexing. See §6.3.

#### DEV-03 — Unified filesystem traversal

**Original:** Recursive and non-recursive directory traversal are implemented as two entirely separate code paths (`MakeDirectoryIndexRecursiveLogic` and `MakeDirectoryIndexLogic`) with near-complete code duplication. Both paths manually assemble an `ArrayList` from separate `Get-ChildItem` calls for files and directories.

**Port:** A single traversal function parameterized by a `recursive: bool` flag. `Path.rglob('*')` or `os.walk()` handles the recursive case; `Path.iterdir()` handles the non-recursive case. Both paths feed into the same object-construction pipeline. See §6.1.

#### DEV-04 — Unified path resolution

**Original:** The "resolve path" operation is independently implemented in three locations: `ResolvePath` in `MakeIndex`, `FileId-ResolvePath` in `FileId`, and `DirectoryId-ResolvePath` in `DirectoryId`. All three perform the same `Resolve-Path` → `GetFullPath()` fallback logic.

**Port:** A single `resolve_path()` utility function replaces all three. See §6.2.

#### DEV-05 — Elimination of the Base64 argument encoding pipeline

**Original:** Exiftool arguments are stored as Base64-encoded strings in the source code, decoded at runtime by `Base64DecodeString` (which itself calls `certutil` on Windows and handles URL-encoding as a separate opcode), written to a temporary file via `TempOpen`, passed to exiftool via its `-@` argfile switch, and cleaned up via `TempClose`.

**Port:** Exiftool arguments are defined as plain Python string lists and passed directly to `subprocess.run()`. This eliminates four dependencies in one stroke: `Base64DecodeString`, `certutil`, `TempOpen`, and `TempClose`. See §6.6.

#### DEV-06 — Elimination of jq

**Original:** Exiftool's JSON output is piped through `jq` for two purposes: compacting the JSON and deleting unwanted keys (ExifToolVersion, FileName, Directory, FilePermissions, etc.).

**Port:** `json.loads()` handles parsing natively. Unwanted keys are removed with a dict comprehension. The `jq` binary dependency is eliminated entirely. See §6.6.

#### DEV-07 — Direct timestamp derivation (Date2UnixTime elimination)

**Original:** Timestamps are read from `Get-Item` as .NET `DateTime` objects, formatted to strings via `.ToString($DateFormat)`, then passed to the external `Date2UnixTime` function which parses those strings back into `DateTimeOffset` objects to call `.ToUnixTimeMilliseconds()` — a needless format-parse-format round-trip.

**Port:** Unix timestamps are derived directly from `os.stat()` float values: `int(stat_result.st_mtime * 1000)`. ISO 8601 strings are produced separately from the same `datetime` object. No round-trip parsing. `Date2UnixTime` and its own internal dependency chain (`Date2FormatCode`, `Date2UnixTimeSquash`, `Date2UnixTimeCountDigits`, `Date2UnixTimeFormatCode`) are eliminated entirely. See §6.5.

#### DEV-08 — Python logging replaces Vbs

**Original:** `Vbs` is a custom structured logging function that is the most widely-called function in the pslib library. It implements its own severity normalization, colorized console output via `Write-Host`, call-stack compression (`A:A:A` → `A(3)`), session ID embedding, monthly log file rotation, and log directory bootstrapping — all manually.

**Port:** Python's `logging` standard library module provides all of these capabilities natively or through standard handlers: severity levels, formatters for console and file output, `RotatingFileHandler` or `TimedRotatingFileHandler` for log rotation, and built-in caller information. The port uses a logger hierarchy rooted at `shruggie_indexer` with per-module child loggers. See §10.

#### DEV-09 — Computed null-hash constants

**Original:** Null-hash constants (the hash of an empty string) are hardcoded as literal hex strings in multiple locations across `DirectoryId` and `FileId` sub-functions (e.g., `D41D8CD98F00B204E9800998ECF8427E` for MD5).

**Port:** Null-hash constants are computed once at module load time: `hashlib.md5(b'').hexdigest().upper()`, etc. This is self-documenting, eliminates the risk of copy-paste errors in long hex strings, and automatically produces correct values if additional algorithms are added in the future. See §6.3.

#### DEV-10 — Externalized filesystem exclusion filters

**Original:** The exclusion of `$RECYCLE.BIN` and `System Volume Information` is hardcoded as inline `Where-Object` filters in the traversal logic. These are Windows-specific system directories.

**Port:** The exclusion list is externalized into the configuration system with a cross-platform default set that covers `$RECYCLE.BIN`, `System Volume Information`, `.DS_Store`, `.Spotlight-V100`, `.Trashes`, `.fseventsd`, and similar platform artifacts. Users can extend or override the list via configuration. See §6.1 and §7.

#### DEV-11 — v2 output schema

**Original:** Output conforms to the v1 schema (`MakeIndex_OutputSchema.json`), which uses a flat field layout with separate top-level keys for each hash variant, timestamp format, and parent attribute — resulting in significant structural redundancy.

**Port:** Output conforms to the v2 schema, which consolidates related fields into typed sub-objects (`NameObject`, `HashSet`, `SizeObject`, `TimestampPair`, `TimestampsObject`, `ParentObject`), adds a `schema_version` discriminator, adds filesystem provenance fields to `MetadataEntry` for MetaMergeDelete reversal, and eliminates the `Encoding` field (see DEV-12). The v2 schema is defined at [schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json](https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json). See §5.

#### DEV-12 — Encoding field dropped

**Original:** The v1 output includes an `Encoding` key containing detailed file encoding properties (BOM detection, code page, encoder/decoder fallback objects) derived from the `GetFileEncoding` sub-function, which invokes a custom C# class (`EncodingDetector.cs`) loaded at pslib initialization.

**Port:** The `Encoding` field is intentionally dropped from the v2 schema. The field's value is derived from a .NET-specific BOM inspection mechanism that has no direct Python equivalent producing the same output structure. The encoding information it provides (code page identifiers, `IsBrowserDisplay`, `IsMailNewsSave`, etc.) is deeply coupled to the .NET `System.Text.Encoding` type hierarchy and has limited utility outside of .NET consumers. The `GetFileEncoding` sub-function and all related logic (`EncodingDetector.cs`, `GetFileEncoding-Squash`) are not carried forward. See §5.9.

#### DEV-13 — Dead code removal

**Original:** `ValidateIsLink` is listed as a dependency in the `MakeIndex` docstring but is never actually called — `FileId` and `DirectoryId` perform symlink detection inline. `UpdateFunctionStack` and `VariableStringify` are internal utility functions whose purposes are absorbed by Python built-ins.

**Port:** These functions are not carried forward. See §11.4.

#### DEV-14 — Configurable extension validation

**Original:** The extension validation regex `^(([a-z0-9]){1,2}|([a-z0-9]){1}([a-z0-9\-]){1,12}([a-z0-9]){1})$` is hardcoded in `MakeObject`. It rejects extensions longer than 14 characters or those containing non-alphanumeric characters (beyond hyphens).

**Port:** The extension validation pattern is externalized into the configuration system so users can adjust it for edge cases (e.g., `.numbers`, `.download`, or other legitimate long extensions) without editing source code. The default pattern preserves the original's intent. See §7.

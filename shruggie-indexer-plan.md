<a id="shruggie-indexer-plan-of-action"></a>
# shruggie-indexer — Plan of Action

- **Project:** `shruggie-indexer`
- **Version Target:** 0.1.0 (MVP)
- **Date:** 2026-02-19
- **Status:** DRAFT — Iteration 2

---

## Overview

This plan defines a dependency-ordered build sequence for the `shruggie-indexer` v0.1.0 MVP. The entire MVP is structured into **three milestones**, each containing **three sprints** (nine sprints total). Each sprint is sized to fit comfortably within the standard context window of Claude Opus 4.6 (~200K tokens) while maximizing the amount of work accomplished per sprint.

### Guiding Constraints

| Constraint | Strategy |
|------------|----------|
| **Context window fit** | Each sprint references only the spec sections and reference docs it needs. No sprint requires the full 9,180-line spec in context. File manifests and spec section references replace inline behavioral restatements — the implementing agent reads the cited sections directly. |
| **Minimal milestone count** | Three milestones. Work is consolidated aggressively — the only reason to split work across milestones is a hard dependency (Milestone 2 builds on Milestone 1 outputs, Milestone 3 builds on Milestone 2 outputs). |
| **Dependency ordering** | Milestone 1 produces every module that later milestones import. Milestone 2 consumes Milestone 1 artifacts to build the engine and its primary interface. Milestone 3 adds the secondary interface and release infrastructure on top of the complete engine. |
| **Sprint sequencing** | Within each milestone, sprints are chronologically ordered. Each sprint's deliverables are consumed by subsequent sprints within the same milestone. |

### Milestone Dependency Chain

```
Milestone 1: Scaffold + Data Layer + Core Utilities
    │  Sprint 1.1 → Sprint 1.2 → Sprint 1.3
    │
    │  provides: models/, config/, core/paths.py, core/hashing.py,
    │            core/timestamps.py, pyproject.toml, package skeleton
    ▼
Milestone 2: Processing Engine + CLI
    │  Sprint 2.1 → Sprint 2.2 → Sprint 2.3
    │
    │  provides: core/traversal.py, core/exif.py, core/sidecar.py,
    │            core/entry.py, core/serializer.py, core/rename.py,
    │            cli/main.py, unit + integration + conformance tests
    ▼
Milestone 3: GUI + Packaging + Release Infrastructure
    │  Sprint 3.1 → Sprint 3.2 → Sprint 3.3
    │
    │  provides: gui/app.py, scripts/build.*, .spec files, CI workflows,
    │            mkdocs.yml, platform tests, README.md
    ▼
   MVP Complete (v0.1.0)
```

---

## Milestone 1 — Scaffold, Data Layer, and Core Utilities

**Goal:** Establish the repository skeleton, define all data structures and configuration types, and implement the stateless utility modules that every subsequent module depends on. At the end of this milestone, the project is installable (`pip install -e .`), all model classes are importable, configuration loads from defaults, and the three foundational core modules (paths, hashing, timestamps) are functional and unit-tested.

---

### Sprint 1.1 — Repository Scaffolding and Package Skeleton

**Goal:** Create the repository root files, establish the full `src/` layout with all `__init__.py` files, define the exception hierarchy, and ensure the package is installable in editable mode.

#### Spec References

The implementing agent for Sprint 1.1 MUST have the following in its context window:

| Source | Sections / Files |
|--------|-----------------|
| [§2.1 — Project Identity](shruggie-indexer-spec.md#21-project-identity) | Package naming, description, license, author metadata |
| [§2.5 — Python Version Requirements](shruggie-indexer-spec.md#25-python-version-requirements) | Minimum Python version, version pinning strategy |
| [§3.1 — Top-Level Layout](shruggie-indexer-spec.md#31-top-level-layout) | Root-level file inventory and descriptions |
| [§3.2 — Source Package Layout](shruggie-indexer-spec.md#32-source-package-layout) | Full `src/shruggie_indexer/` directory tree, sub-package descriptions |
| [§4.5 — Error Handling Strategy](shruggie-indexer-spec.md#45-error-handling-strategy) | Exception class hierarchy, severity tiers |
| [§9.1 — Public API Surface](shruggie-indexer-spec.md#91-public-api-surface) | `__init__.py` re-exports, `__all__` contents |
| [§9.4 — Data Classes and Type Definitions](shruggie-indexer-spec.md#94-data-classes-and-type-definitions) | Exception classes: `IndexerError`, `IndexerConfigError`, `IndexerTargetError`, `IndexerRuntimeError`, `RenameError`, `IndexerCancellationError` |
| [§12.3 — Third-Party Python Packages](shruggie-indexer-spec.md#123-third-party-python-packages) | All dependency specifications for `pyproject.toml` |
| [§13.1 — Package Metadata](shruggie-indexer-spec.md#131-package-metadata) | PyPI classifiers, URLs, description |
| [§13.2 — pyproject.toml Configuration](shruggie-indexer-spec.md#132-pyprojecttoml-configuration) | Full canonical `pyproject.toml` content |
| [§13.3 — Entry Points and Console Scripts](shruggie-indexer-spec.md#133-entry-points-and-console-scripts) | CLI and GUI entry point definitions |
| [§13.6 — Version Management](shruggie-indexer-spec.md#136-version-management) | Single-source version strategy, `_version.py` |

#### Deliverables

| File | Description |
|------|-------------|
| `pyproject.toml` | Full canonical content per §13.2. Build system, metadata, deps, entry points, tool config. |
| `.gitignore` | Standard Python gitignore (see §3.1). |
| `.python-version` | Contains `3.12`. |
| `src/shruggie_indexer/__init__.py` | Public API re-exports + `__version__`. Stub imports for names not yet implemented (Sprint 1.2 and later). |
| `src/shruggie_indexer/__main__.py` | `python -m` entry point — import and call `cli.main.main`. |
| `src/shruggie_indexer/_version.py` | `__version__ = "0.1.0"` |
| `src/shruggie_indexer/core/__init__.py` | Re-exports for orchestration functions (stubs until Milestone 2). |
| `src/shruggie_indexer/models/__init__.py` | Re-exports from `schema.py` (stubs until Sprint 1.2). |
| `src/shruggie_indexer/config/__init__.py` | Re-exports `IndexerConfig`, `load_config()` (stubs until Sprint 1.2). |
| `src/shruggie_indexer/cli/__init__.py` | Empty. |
| `src/shruggie_indexer/gui/__init__.py` | Empty. |
| `src/shruggie_indexer/exceptions.py` | `IndexerError` (base), `IndexerConfigError`, `IndexerTargetError`, `IndexerRuntimeError`, `RenameError`, `IndexerCancellationError`. |

#### Steps

1. Create the repository root files: `pyproject.toml`, `.gitignore`, `.python-version`.
2. Create the `src/shruggie_indexer/` directory tree with all `__init__.py` files for sub-packages: `core/`, `models/`, `config/`, `cli/`, `gui/`.
3. Create `_version.py` with the version string `"0.1.0"`.
4. Create `__main__.py` with the `python -m shruggie_indexer` entry point.
5. Create `exceptions.py` with the full exception hierarchy per §4.5 and §9.4.
6. Populate `__init__.py` in each sub-package with appropriate stub imports and re-exports per §9.1.
7. Verify installability: `pip install -e ".[dev]"` must succeed.
8. Verify import: `python -c "from shruggie_indexer._version import __version__; print(__version__)"` must print `0.1.0`.

#### Exit Criteria

- [ ] `pip install -e ".[dev]"` succeeds from the repository root.
- [ ] `python -c "from shruggie_indexer._version import __version__"` succeeds.
- [ ] All sub-package `__init__.py` files are importable without error.
- [ ] `ruff check src/` — zero errors.

---

### Sprint 1.2 — Data Models and Configuration System

**Goal:** Implement all v2 schema dataclasses in `models/schema.py`, the full configuration type system in `config/types.py`, the compiled default values in `config/defaults.py`, and the TOML-based configuration loader in `config/loader.py`.

#### Spec References

The implementing agent for Sprint 1.2 MUST have the following in its context window:

| Source | Sections / Files |
|--------|-----------------|
| [§2.6 — Intentional Deviations from the Original](shruggie-indexer-spec.md#26-intentional-deviations-from-the-original) | All 16 DEV items — especially DEV-10 (externalized exclusions), DEV-11 (v2 schema), DEV-12 (encoding dropped), DEV-14 (configurable extension validation) |
| [§5.1 — Schema Overview](shruggie-indexer-spec.md#51-schema-overview) | Schema design principles, schema version |
| [§5.2 — Reusable Type Definitions](shruggie-indexer-spec.md#52-reusable-type-definitions) | `HashSet`, `NameObject`, `SizeObject`, `TimestampPair`, `TimestampsObject`, `ParentObject` |
| [§5.3 — Top-Level IndexEntry Fields](shruggie-indexer-spec.md#53-top-level-indexentry-fields) | Full field inventory |
| [§5.4 — Identity Fields](shruggie-indexer-spec.md#54-identity-fields) | `schema_version`, `id`, `id_algorithm`, `type` |
| [§5.5 — Naming and Content Fields](shruggie-indexer-spec.md#55-naming-and-content-fields) | `name`, `extension`, `mime_type`, `size`, `hashes` |
| [§5.6 — Filesystem Location and Hierarchy Fields](shruggie-indexer-spec.md#56-filesystem-location-and-hierarchy-fields) | `file_system` object |
| [§5.7 — Timestamp Fields](shruggie-indexer-spec.md#57-timestamp-fields) | `timestamps` object |
| [§5.8 — Attribute Fields](shruggie-indexer-spec.md#58-attribute-fields) | `attributes` object |
| [§5.9 — Recursive Items Field](shruggie-indexer-spec.md#59-recursive-items-field) | `items` array |
| [§5.10 — Metadata Array and MetadataEntry Fields](shruggie-indexer-spec.md#510-metadata-array-and-metadataentry-fields) | `metadata` array, `MetadataEntry` structure |
| [§5.11 — Dropped and Restructured Fields](shruggie-indexer-spec.md#511-dropped-and-restructured-fields) | v1→v2 field mapping |
| [§5.12 — Schema Validation and Enforcement](shruggie-indexer-spec.md#512-schema-validation-and-enforcement) | Serialization invariants |
| [§7.1 — Configuration Architecture](shruggie-indexer-spec.md#71-configuration-architecture) | 4-layer merge, frozen dataclass, config discovery |
| [§7.2 — Default Configuration](shruggie-indexer-spec.md#72-default-configuration) | All compiled default values |
| [§7.3 — Metadata File Parser Configuration](shruggie-indexer-spec.md#73-metadata-file-parser-configuration) | Sidecar type definitions, regex patterns, extension groups |
| [§7.4 — Exiftool Exclusion Lists](shruggie-indexer-spec.md#74-exiftool-exclusion-lists) | Exiftool exclusion extensions |
| [§7.5 — Sidecar Suffix Patterns and Type Identification](shruggie-indexer-spec.md#75-sidecar-suffix-patterns-and-type-identification) | 10 sidecar regex patterns including BCP 47 subtitle alternation |
| [§7.6 — Configuration File Format](shruggie-indexer-spec.md#76-configuration-file-format) | TOML structure and examples |
| [§7.7 — Configuration Override and Merging Behavior](shruggie-indexer-spec.md#77-configuration-override-and-merging-behavior) | Merge semantics: scalar override, collection replace, `_append` merge |
| [§9.3 — Configuration API](shruggie-indexer-spec.md#93-configuration-api) | `load_config()` signature and behavior |
| [§9.4 — Data Classes and Type Definitions](shruggie-indexer-spec.md#94-data-classes-and-type-definitions) | Full dataclass signatures for all schema and config types |
| [§3.3 — Configuration File Locations](shruggie-indexer-spec.md#33-configuration-file-locations) | Platform-aware config file paths |
| `docs/schema/shruggie-indexer-v2.schema.json` | Full file (canonical v2 schema definition) |
| `docs/porting-reference/MakeIndex(MetadataFileParser).ps1` | Full file (regex patterns, extension groups, exclusion lists for `config/defaults.py`) |

#### Deliverables

| File | Description |
|------|-------------|
| `src/shruggie_indexer/models/schema.py` | All v2 schema dataclasses: `IndexEntry`, `HashSet`, `NameObject`, `SizeObject`, `TimestampPair`, `TimestampsObject`, `ParentObject`, `FileSystemObject`, `AttributesObject`, `MetadataEntry`, `MetadataAttributes`. Serialization helpers (`to_dict()`). |
| `src/shruggie_indexer/config/types.py` | `IndexerConfig` frozen dataclass + all nested config types (`MetadataTypeConfig`, `ExiftoolConfig`, `SidecarConfig`, etc.). |
| `src/shruggie_indexer/config/defaults.py` | All compiled default values: 10 sidecar regex patterns (including the BCP 47 subtitle alternation), 7 extension group classifications, filesystem exclusion lists, exiftool exclusion list, include/exclude patterns. Ported from `MakeIndex(MetadataFileParser).ps1`. |
| `src/shruggie_indexer/config/loader.py` | `load_config()`: TOML file discovery (platform-aware paths), parsing via `tomllib`, 4-layer merge (defaults → user → project → overrides), validation. |

#### Steps

1. Read `docs/schema/shruggie-indexer-v2.schema.json` as the canonical type reference.
2. Implement `models/schema.py` with all dataclasses matching §5.2–5.10. Include `to_dict()` serialization helpers on each dataclass. Ensure all required vs. optional fields align with the JSON schema.
3. Implement `config/types.py` with the `IndexerConfig` frozen dataclass and all nested configuration types per §7.1 and §9.3.
4. Read `docs/porting-reference/MakeIndex(MetadataFileParser).ps1` for all regex patterns and default values.
5. Implement `config/defaults.py` with all compiled defaults per §7.2–7.5. Port every regex pattern, extension group, and exclusion list with exact matching behavior preserved.
6. Implement `config/loader.py` with `load_config()`: TOML file discovery per §3.3, parsing via `tomllib`, 4-layer merge per §7.7, validation.
7. Update `models/__init__.py` to re-export all schema classes.
8. Update `config/__init__.py` to re-export `IndexerConfig` and `load_config()`.
9. Verify: `python -c "from shruggie_indexer.models.schema import IndexEntry, HashSet, NameObject"` succeeds.
10. Verify: `python -c "from shruggie_indexer.config import load_config; c = load_config(); print(c)"` succeeds and prints a populated `IndexerConfig`.

#### Exit Criteria

- [ ] `python -c "from shruggie_indexer.models.schema import IndexEntry, HashSet, NameObject"` succeeds.
- [ ] `python -c "from shruggie_indexer.config import load_config; c = load_config(); print(c)"` succeeds and prints a populated `IndexerConfig`.
- [ ] All 10 sidecar regex patterns compile without error.
- [ ] `ruff check src/` — zero errors.

---

### Sprint 1.3 — Core Utilities and Milestone 1 Tests

**Goal:** Implement the three foundational core modules (`paths.py`, `hashing.py`, `timestamps.py`) and write all unit tests for Milestone 1 deliverables (schema, config, paths, hashing, timestamps).

#### Spec References

The implementing agent for Sprint 1.3 MUST have the following in its context window:

| Source | Sections / Files |
|--------|-----------------|
| [§6.2 — Path Resolution and Manipulation](shruggie-indexer-spec.md#62-path-resolution-and-manipulation) | `resolve_path()`, `extract_components()`, `validate_extension()`, `build_sidecar_path()`, forward-slash normalization |
| [§6.3 — Hashing and Identity Generation](shruggie-indexer-spec.md#63-hashing-and-identity-generation) | `hash_file()`, `hash_string()`, `hash_directory_id()`, `select_id()`, `NULL_HASHES`, single-pass multi-algorithm, 64KB chunks, NFC normalization, uppercase hex, `x`/`y`/`z` prefix logic |
| [§6.5 — Filesystem Timestamps and Date Conversion](shruggie-indexer-spec.md#65-filesystem-timestamps-and-date-conversion) | `extract_timestamps()`, `os.stat()`/`os.lstat()`, `st_birthtime` → `st_ctime` fallback, millisecond Unix + microsecond ISO 8601 |
| [§2.6 — Intentional Deviations from the Original](shruggie-indexer-spec.md#26-intentional-deviations-from-the-original) | DEV-01 (unified hashing), DEV-02 (single-pass), DEV-04 (unified paths), DEV-07 (direct timestamps), DEV-09 (computed null-hash), DEV-15 (NFC normalization) |
| [§14.2 — Unit Test Coverage](shruggie-indexer-spec.md#142-unit-test-coverage) | Test specifications for: `test_hashing`, `test_paths`, `test_timestamps`, `test_schema`, `test_config` |
| [§15.5 — Creation Time Portability](shruggie-indexer-spec.md#155-creation-time-portability) | `st_birthtime` availability per platform |
| `docs/porting-reference/DirectoryId_DependencyCatalog.md` | Full file (two-layer hashing scheme) |
| `docs/porting-reference/FileId_DependencyCatalog.md` | Full file (content hashing, null-hash, prefix logic) |
| `docs/porting-reference/Date2UnixTime_DependencyCatalog.md` | Full file (timestamp conversion — for understanding what DEV-07 eliminates) |
| Sprint 1.1 + 1.2 source files | All `.py` files created in Sprints 1.1 and 1.2 (exceptions, models, config) — the implementing agent must see the actual interfaces it is building on |

#### Deliverables

**Core Utility Modules:**

| File | Description |
|------|-------------|
| `src/shruggie_indexer/core/paths.py` | `resolve_path()`, `extract_components()`, `validate_extension()`, `build_sidecar_path()`. Forward-slash normalization for relative paths. |
| `src/shruggie_indexer/core/hashing.py` | `hash_file()`, `hash_string()`, `hash_directory_id()`, `select_id()`, `NULL_HASHES`. Single-pass multi-algorithm (MD5+SHA256, opt-in SHA512). 64KB chunks. NFC normalization. Uppercase hex. Null-hash = `hash(b"0")` computed at load time. `x`/`y`/`z` prefix logic. |
| `src/shruggie_indexer/core/timestamps.py` | `extract_timestamps()`. `os.stat()`/`os.lstat()` → `TimestampPair` + `TimestampsObject`. `st_birthtime` → `st_ctime` fallback. Millisecond Unix + microsecond ISO 8601. |

**Test Files:**

| File | Description |
|------|-------------|
| `tests/conftest.py` | Shared fixtures: `sample_file`, `sample_tree`, `default_config`, `mock_exiftool`. |
| `tests/unit/__init__.py` | Empty. |
| `tests/unit/test_hashing.py` | 12 cases per §14.2: MD5+SHA256 correctness, SHA512 opt-in, single-pass equivalence, empty file, large file (>64KB), NFC normalization, null-hash constants, `hash_directory_id` two-layer scheme, `select_id` prefix logic, `HashSet` construction. |
| `tests/unit/test_paths.py` | 11 cases per §14.2: absolute/relative resolution, component extraction, extension validation, forward-slash normalization, UNC paths (Windows), long paths, Unicode filenames, sidecar path construction. |
| `tests/unit/test_timestamps.py` | 6 cases per §14.2: mtime/atime/ctime extraction, ISO 8601 format validation, millisecond Unix conversion, symlink `lstat()` timestamps, missing `st_birthtime` fallback. |
| `tests/unit/test_schema.py` | 5 cases per §14.2: dataclass construction, `to_dict()` round-trip, required vs. optional fields, `schema_version` presence, nested object construction. |
| `tests/unit/test_config.py` | 8 cases per §14.2: default config construction, TOML parsing, layer merging, scalar override, collection replace, `_append` merge, validation rejection, missing file tolerance. |

#### Steps

1. Read `docs/porting-reference/DirectoryId_DependencyCatalog.md` and `docs/porting-reference/FileId_DependencyCatalog.md` for the hashing scheme reference.
2. Implement `core/hashing.py` with all public functions per §6.3. Ensure single-pass multi-algorithm hashing with 64KB chunks. Compute `NULL_HASHES` at module load time as `hash(b"0")` for each algorithm. Implement the `x`/`y`/`z` identity prefix logic per §6.3.
3. Read `docs/porting-reference/Date2UnixTime_DependencyCatalog.md` to understand the timestamp conversion approach being replaced.
4. Implement `core/timestamps.py` with `extract_timestamps()` per §6.5. Handle `st_birthtime` → `st_ctime` fallback. Output both millisecond Unix timestamps and microsecond ISO 8601 strings.
5. Implement `core/paths.py` with all public functions per §6.2. Forward-slash normalization for relative paths in output. Platform-aware path resolution.
6. Create `tests/conftest.py` with shared fixtures.
7. Write `tests/unit/test_hashing.py` — 12 test cases per §14.2.
8. Write `tests/unit/test_paths.py` — 11 test cases per §14.2.
9. Write `tests/unit/test_timestamps.py` — 6 test cases per §14.2.
10. Write `tests/unit/test_schema.py` — 5 test cases per §14.2.
11. Write `tests/unit/test_config.py` — 8 test cases per §14.2.
12. Run the full unit test suite and fix any failures.

#### Exit Criteria

- [ ] `python -c "from shruggie_indexer.core.hashing import hash_file, hash_string, NULL_HASHES"` succeeds.
- [ ] `python -c "from shruggie_indexer.core.paths import resolve_path, extract_components"` succeeds.
- [ ] `python -c "from shruggie_indexer.core.timestamps import extract_timestamps"` succeeds.
- [ ] `pytest tests/unit/test_hashing.py tests/unit/test_paths.py tests/unit/test_timestamps.py tests/unit/test_schema.py tests/unit/test_config.py` — all pass.
- [ ] `ruff check src/` — zero errors.

---

## Milestone 2 — Processing Engine and CLI

**Goal:** Implement the complete indexing pipeline (traversal, EXIF extraction, sidecar metadata discovery/parsing, entry orchestration, JSON serialization, rename operations), wire it up through the CLI, and validate with unit tests, integration tests, and schema conformance tests. At the end of this milestone, `shruggie-indexer <target>` produces valid v2 JSON output for any input path.

**Depends on:** Milestone 1 (models, config, paths, hashing, timestamps all must exist).

---

### Sprint 2.1 — Traversal, EXIF Extraction, and Sidecar Parsing

**Goal:** Implement the three core engine modules that discover and extract data from the filesystem: `traversal.py` (directory enumeration), `exif.py` (embedded metadata via exiftool), and `sidecar.py` (sidecar metadata file discovery and parsing with all 10 type detectors).

#### Spec References

The implementing agent for Sprint 2.1 MUST have the following in its context window:

| Source | Sections / Files |
|--------|-----------------|
| [§6.1 — Filesystem Traversal and Discovery](shruggie-indexer-spec.md#61-filesystem-traversal-and-discovery) | `list_children()`, `os.scandir()`, exclusion filters, recursive/non-recursive, symlink-aware classification |
| [§6.4 — Symlink Detection](shruggie-indexer-spec.md#64-symlink-detection) | Detection mechanism, behavioral effects, dangling symlinks |
| [§6.6 — EXIF and Embedded Metadata Extraction](shruggie-indexer-spec.md#66-exif-and-embedded-metadata-extraction) | `extract_exif()`, `_exiftool_available()`, `pyexiftool` batch mode, subprocess fallback, JSON parsing, key filtering, extension-gate, 30s timeout, graceful degradation |
| [§6.7 — Sidecar Metadata File Handling](shruggie-indexer-spec.md#67-sidecar-metadata-file-handling) | `discover_and_parse()`, sibling pre-enumeration, 10 type detectors, format-specific readers, fallback chain, Base64 encoding, `MetadataEntry` construction, MetaMergeDelete queue |
| [§2.6 — Intentional Deviations from the Original](shruggie-indexer-spec.md#26-intentional-deviations-from-the-original) | DEV-03 (unified traversal), DEV-06 (jq elimination), DEV-10 (externalized exclusions), DEV-16 (pyexiftool batch mode) |
| [§4.1 — High-Level Processing Pipeline](shruggie-indexer-spec.md#41-high-level-processing-pipeline) | Pipeline stage ordering context |
| [§4.2 — Module Decomposition](shruggie-indexer-spec.md#42-module-decomposition) | Module dependency graph |
| [§7.3 — Metadata File Parser Configuration](shruggie-indexer-spec.md#73-metadata-file-parser-configuration) | Sidecar type definitions, per-type behavioral attributes |
| [§7.4 — Exiftool Exclusion Lists](shruggie-indexer-spec.md#74-exiftool-exclusion-lists) | Extension exclusion list for exiftool |
| [§7.5 — Sidecar Suffix Patterns and Type Identification](shruggie-indexer-spec.md#75-sidecar-suffix-patterns-and-type-identification) | Regex patterns for the 10 sidecar types |
| [§16.1 — Symlink Traversal Safety](shruggie-indexer-spec.md#161-symlink-traversal-safety) | Symlink loop prevention |
| `docs/porting-reference/MakeIndex_OperationsCatalog.md` | Full file (operation-to-module mapping) |
| `docs/porting-reference/MetaFileRead_DependencyCatalog.md` | Full file (sidecar parsing logic, format-specific handlers, fallback chain) |
| `docs/porting-reference/MakeIndex(MetadataFileParser).ps1` | Full file (sidecar regex patterns — needed during `sidecar.py` implementation) |
| Milestone 1 source files | All `.py` files created in Milestone 1 (models, config, paths, hashing, timestamps) — the implementing agent must see the actual interfaces it is calling into |

#### Deliverables

| File | Description |
|------|-------------|
| `src/shruggie_indexer/core/traversal.py` | `list_children()`. Single-pass `os.scandir()`, configurable filesystem exclusions, recursive/non-recursive modes, sorted output, symlink-aware classification. |
| `src/shruggie_indexer/core/exif.py` | `extract_exif()`, `_exiftool_available()`. `pyexiftool` batch mode primary backend (DEV-16), `subprocess.run()` + argfile fallback. JSON parsing (DEV-06). Key filtering via dict comprehension. Extension-gate from config. 30s timeout. Graceful degradation when `exiftool` absent. |
| `src/shruggie_indexer/core/sidecar.py` | `discover_and_parse()`. Pre-enumerate siblings via `os.scandir()`. 10 type detectors (Description, DesktopIni, GenericMetadata, Hash, JsonMetadata, Link, Screenshot, Subtitles, Thumbnail, Torrent) matched against configurable regex patterns. Format-specific readers: JSON → plain text → binary fallback chain. Base64 encoding for binary content. `MetadataEntry` construction with full provenance (filesystem, size, timestamps). MetaMerge queue building. MetaMergeDelete safety gates. |

#### Steps

1. Implement `core/traversal.py` with `list_children()` per §6.1. Use `os.scandir()` for single-pass enumeration. Apply configurable filesystem exclusion filters from the config. Sort output. Classify entries as file/directory/symlink. Support recursive and non-recursive modes. Implement symlink loop prevention per §16.1.
2. Implement `core/exif.py` with `extract_exif()` and `_exiftool_available()` per §6.6. Implement the dual backend strategy: `pyexiftool` batch mode as primary, `subprocess.run()` + argfile as fallback. Parse JSON output directly (no `jq` needed per DEV-06). Filter keys via dict comprehension. Gate extraction by file extension per config. Set 30s timeout. Return empty dict when `exiftool` is absent (graceful degradation).
3. Read `docs/porting-reference/MetaFileRead_DependencyCatalog.md` for the complete sidecar parsing reference.
4. Implement `core/sidecar.py` with `discover_and_parse()` per §6.7. Pre-enumerate siblings using `os.scandir()`. Match filenames against the 10 type detector regex patterns from config. Implement format-specific readers: JSON parser, plain text reader, binary-to-Base64 fallback. Construct `MetadataEntry` objects with full provenance (filesystem object, size, timestamps). Build the MetaMerge queue. Implement MetaMergeDelete safety gates per §16.4.
5. Verify all three modules import correctly and their public functions have correct signatures.

#### Exit Criteria

- [ ] `python -c "from shruggie_indexer.core.traversal import list_children"` succeeds.
- [ ] `python -c "from shruggie_indexer.core.exif import extract_exif"` succeeds.
- [ ] `python -c "from shruggie_indexer.core.sidecar import discover_and_parse"` succeeds.
- [ ] `ruff check src/` — zero errors.

---

### Sprint 2.2 — Entry Orchestration, Serializer, Rename, and CLI

**Goal:** Implement the hub-and-spoke entry orchestration module (`entry.py`), JSON serialization with output routing (`serializer.py`), file rename operations (`rename.py`), and the complete `click`-based CLI (`cli/main.py`). Update all stubs from Milestone 1.

#### Spec References

The implementing agent for Sprint 2.2 MUST have the following in its context window:

| Source | Sections / Files |
|--------|-----------------|
| [§6.8 — Index Entry Construction](shruggie-indexer-spec.md#68-index-entry-construction) | `build_file_entry()` 12-step orchestration, `build_directory_entry()`, `index_path()`, progress callback, cooperative cancellation |
| [§6.9 — JSON Serialization and Output Routing](shruggie-indexer-spec.md#69-json-serialization-and-output-routing) | `serialize_entry()`, `write_output()`, `write_inplace()`, `orjson` primary / `json.dumps()` fallback, three output modes, atomic writes, `schema_version` first key, pretty vs. compact, `ensure_ascii=False` |
| [§6.10 — File Rename and In-Place Write Operations](shruggie-indexer-spec.md#610-file-rename-and-in-place-write-operations) | `rename_item()`, `build_storage_path()`, collision detection, dry-run mode, `shutil.move()` fallback |
| [§4.3 — Data Flow](shruggie-indexer-spec.md#43-data-flow) | Module boundary data types, recursive directory data flow |
| [§4.4 — State Management](shruggie-indexer-spec.md#44-state-management) | No mutable global state, delete queue lifecycle |
| [§4.6 — Entry Point Routing](shruggie-indexer-spec.md#46-entry-point-routing) | Input classification, routing decision tree, symlink edge case |
| [§8.1 — Command Structure](shruggie-indexer-spec.md#81-command-structure) | CLI invocation patterns |
| [§8.2 — Target Input Options](shruggie-indexer-spec.md#82-target-input-options) | `TARGET`, `--file`, `--directory` |
| [§8.3 — Output Mode Options](shruggie-indexer-spec.md#83-output-mode-options) | `--stdout`, `--outfile`, `--inplace` |
| [§8.4 — Metadata Processing Options](shruggie-indexer-spec.md#84-metadata-processing-options) | `--meta`, `--meta-merge`, `--meta-merge-delete` |
| [§8.5 — Rename Option](shruggie-indexer-spec.md#85-rename-option) | `--rename`, `--dry-run` |
| [§8.6 — ID Type Selection](shruggie-indexer-spec.md#86-id-type-selection) | `--id-type`, `--compute-sha512` |
| [§8.7 — Verbosity and Logging Options](shruggie-indexer-spec.md#87-verbosity-and-logging-options) | `-v`/`-vv`/`-vvv`, `-q` |
| [§8.8 — Mutual Exclusion Rules and Validation](shruggie-indexer-spec.md#88-mutual-exclusion-rules-and-validation) | Option conflict rules, implication chains |
| [§8.9 — Output Scenarios](shruggie-indexer-spec.md#89-output-scenarios) | Complete behavior matrix for combined options |
| [§8.10 — Exit Codes](shruggie-indexer-spec.md#810-exit-codes) | Exit code enumeration (0–5) |
| [§8.11 — Signal Handling and Graceful Interruption](shruggie-indexer-spec.md#811-signal-handling-and-graceful-interruption) | Two-phase SIGINT handling |
| [§9.1 — Public API Surface](shruggie-indexer-spec.md#91-public-api-surface) | `__all__` with 21 public names |
| [§9.2 — Core Functions](shruggie-indexer-spec.md#92-core-functions) | `index_path()`, `build_file_entry()`, `build_directory_entry()` signatures |
| [§11.1 — Logging Architecture](shruggie-indexer-spec.md#111-logging-architecture) | `configure_logging()`, `SessionFilter` |
| [§11.2 — Logger Naming Hierarchy](shruggie-indexer-spec.md#112-logger-naming-hierarchy) | Logger names per module |
| [§11.3 — Log Levels and CLI Flag Mapping](shruggie-indexer-spec.md#113-log-levels-and-cli-flag-mapping) | Verbosity → log level mapping |
| [§11.4 — Session Identifiers](shruggie-indexer-spec.md#114-session-identifiers) | Session ID generation |
| [§11.5 — Log Output Destinations](shruggie-indexer-spec.md#115-log-output-destinations) | stderr, file handler |
| [§11.6 — Progress Reporting](shruggie-indexer-spec.md#116-progress-reporting) | `tqdm` for TTY, log-line milestones for non-TTY |
| [§16.4 — Metadata Merge-Delete Safeguards](shruggie-indexer-spec.md#164-metadata-merge-delete-safeguards) | Safety checks for destructive operations |
| Sprint 2.1 source files | `traversal.py`, `exif.py`, `sidecar.py` — the modules this sprint's code calls |
| Milestone 1 source files | All `.py` files from Milestone 1 |

#### Deliverables

| File | Description |
|------|-------------|
| `src/shruggie_indexer/core/entry.py` | `build_file_entry()` (12-step orchestration), `build_directory_entry()`, `index_path()`. Hub-and-spoke calls to hashing, timestamps, exif, sidecar, paths. Progress callback support. Cooperative cancellation via `threading.Event`. |
| `src/shruggie_indexer/core/serializer.py` | `serialize_entry()`, `write_output()`, `write_inplace()`. `orjson` primary serializer with `json.dumps()` fallback. Three independent output modes: stdout, outfile (aggregate), inplace (per-item sidecar `_meta2.json` / `_directorymeta2.json`). Atomic file writes. `schema_version` always first key. Pretty-print vs. compact. `ensure_ascii=False`. |
| `src/shruggie_indexer/core/rename.py` | `rename_item()`, `build_storage_path()`. Hash-based `storage_name` derivation. Collision detection (inode comparison). Dry-run mode. MetaMergeDelete-safe guard. `shutil.move()` fallback. |
| `src/shruggie_indexer/cli/main.py` | `click`-based CLI. All options per §8: `TARGET`, `--file`/`--directory`, `--recursive`/`--no-recursive`, `--stdout`/`--no-stdout`, `--outfile`, `--inplace`, `--meta`/`--meta-merge`/`--meta-merge-delete`, `--rename`, `--dry-run`, `--id-type`, `--compute-sha512`, `-v`/`-vv`/`-vvv`, `-q`, `--version`. Exit codes as `IntEnum` (0–5). Implication chains. `configure_logging()` with `SessionFilter`. `tqdm` progress for TTY, log-line milestones for non-TTY. Optional `rich` colorization. Two-phase SIGINT handling. |
| `src/shruggie_indexer/__init__.py` | **Updated:** Replace stub imports with real imports from `core/entry.py`. Wire up full `__all__` with 21 public names. |
| `src/shruggie_indexer/core/__init__.py` | **Updated:** Replace stubs with real re-exports of `index_path`, `build_file_entry`, `build_directory_entry`. |

#### Steps

1. Implement `core/entry.py` with `build_file_entry()`, `build_directory_entry()`, and `index_path()` per §6.8. The `build_file_entry()` function follows the 12-step orchestration sequence documented in the spec. Wire hub-and-spoke calls to all core modules (hashing, timestamps, exif, sidecar, paths). Implement progress callback support and cooperative cancellation via `threading.Event`.
2. Implement `core/serializer.py` with `serialize_entry()`, `write_output()`, and `write_inplace()` per §6.9. Use `orjson` as primary serializer with `json.dumps()` fallback. Implement three independent output modes: stdout, outfile (aggregate JSON), inplace (per-item sidecar `_meta2.json`/`_directorymeta2.json`). Use atomic file writes. Ensure `schema_version` is always the first key. Support pretty-print and compact modes. Set `ensure_ascii=False`.
3. Implement `core/rename.py` with `rename_item()` and `build_storage_path()` per §6.10. Derive `storage_name` from hashes. Detect collisions via inode comparison. Support dry-run mode. Guard against unsafe MetaMergeDelete operations.
4. Implement `cli/main.py` with the full `click`-based CLI per §8.1–8.11. Define all options, implement mutual exclusion validation per §8.8, wire implication chains, configure logging per §11.1–11.6, implement progress reporting, implement two-phase SIGINT handling per §8.11, and define exit codes as `IntEnum`.
5. Update `src/shruggie_indexer/__init__.py` — replace stub imports with real imports. Wire up the full `__all__` with 21 public names per §9.1.
6. Update `src/shruggie_indexer/core/__init__.py` — replace stubs with real re-exports.
7. Verify: `shruggie-indexer --help` prints usage and exits 0.
8. Verify: `shruggie-indexer --version` prints `0.1.0` and exits 0.

#### Exit Criteria

- [ ] `shruggie-indexer --help` prints usage and exits 0.
- [ ] `shruggie-indexer --version` prints `0.1.0` and exits 0.
- [ ] `shruggie-indexer <path-to-a-real-file>` produces v2 JSON on stdout.
- [ ] `ruff check src/` — zero errors.

---

### Sprint 2.3 — Milestone 2 Tests and Validation

**Goal:** Write all unit tests (traversal, exif, sidecar, entry, serializer, rename), all integration tests (single file, directory, output modes, CLI), all schema conformance tests, and create the required test fixtures. Validate the complete pipeline end-to-end.

#### Spec References

The implementing agent for Sprint 2.3 MUST have the following in its context window:

| Source | Sections / Files |
|--------|-----------------|
| [§14.1 — Testing Strategy](shruggie-indexer-spec.md#141-testing-strategy) | Test organization, naming conventions, marker usage |
| [§14.2 — Unit Test Coverage](shruggie-indexer-spec.md#142-unit-test-coverage) | Required test cases for: `test_traversal`, `test_exif`, `test_sidecar`, `test_entry`, `test_serializer`, `test_rename` |
| [§14.3 — Integration Tests](shruggie-indexer-spec.md#143-integration-tests) | Required test cases for: `test_single_file`, `test_directory_flat`, `test_directory_recursive`, `test_output_modes`, `test_cli` |
| [§14.4 — Output Schema Conformance Tests](shruggie-indexer-spec.md#144-output-schema-conformance-tests) | 13 validation cases + 4 serialization invariants |
| [§3.4 — Test Directory Layout](shruggie-indexer-spec.md#34-test-directory-layout) | Test file organization, fixture directory structure |
| [§5.12 — Schema Validation and Enforcement](shruggie-indexer-spec.md#512-schema-validation-and-enforcement) | Serialization invariants: key ordering, `sha512` omission, Unicode preservation, `null` vs. absent |
| `docs/schema/shruggie-indexer-v2.schema.json` | Full file (for conformance test validation) |
| All Sprint 2.1 and 2.2 source files | The modules being tested |

#### Deliverables

**Unit Test Files:**

| File | Description |
|------|-------------|
| `tests/unit/test_traversal.py` | 9 cases: flat listing, recursive listing, exclusion filtering, symlink handling, empty directory, deeply nested, hidden files, sort order, mixed file/dir classification. |
| `tests/unit/test_exif.py` | 7 cases: successful extraction, exiftool absent (graceful skip), extension-gated skip, key filtering, timeout handling, malformed JSON response, batch vs. fallback parity. |
| `tests/unit/test_sidecar.py` | 9 cases: each of the 10 sidecar types (combined where trivial), no-match (no sidecars found), JSON parse, text parse, binary-to-Base64, MetadataEntry provenance fields, MetaMergeDelete queue population. |
| `tests/unit/test_entry.py` | 8 cases: file entry construction, directory entry construction, symlink entry, recursive directory, cancellation mid-traversal, progress callback invocation, missing exiftool degradation, sidecar folding. |
| `tests/unit/test_serializer.py` | 7 cases: JSON round-trip, `schema_version` first key, `sha512` omission when not computed, pretty vs. compact, `ensure_ascii=False`, stdout output, inplace file naming. |
| `tests/unit/test_rename.py` | 4 cases: successful rename, dry-run (no filesystem change), collision detection, storage_name derivation. |

**Integration Test Files:**

| File | Description |
|------|-------------|
| `tests/integration/__init__.py` | Empty. |
| `tests/integration/test_single_file.py` | 6 cases: index a real file end-to-end, validate v2 output structure, hash correctness against known digest, timestamp plausibility, extension extraction, MIME type. |
| `tests/integration/test_directory_flat.py` | 3 cases: flat directory indexing, item count matches, child entries are files. |
| `tests/integration/test_directory_recursive.py` | 4 cases: recursive traversal depth, nested directory identity, parent references, item ordering. |
| `tests/integration/test_output_modes.py` | 5 cases: stdout capture, outfile write, inplace sidecar write, combined modes, empty directory output. |
| `tests/integration/test_cli.py` | 14 cases: `--help`, `--version`, default invocation, `--file` mode, `--directory` mode, `--recursive`/`--no-recursive`, `--outfile`, `--inplace`, `--meta-merge`, `--rename --dry-run`, `--id-type sha256`, `--compute-sha512`, verbosity levels, invalid target (exit code 3). |

**Conformance Test Files:**

| File | Description |
|------|-------------|
| `tests/conformance/__init__.py` | Empty. |
| `tests/conformance/test_v2_schema.py` | 13 cases per §14.4: file entry validates, directory entry validates, recursive entry validates, symlink entry validates, all-null optional fields validate, MetadataEntry validates, minimal entry validates, extra fields rejected (additionalProperties), `schema_version` wrong value rejected, required field missing rejected. Plus 4 serialization invariants: key ordering, `sha512` omission, Unicode preservation, `null` vs. absent. |

**Test Fixtures:**

| Path | Description |
|------|-------------|
| `tests/fixtures/exiftool_responses/` | At least 2 captured JSON responses for mocking. |
| `tests/fixtures/sidecar_samples/` | One sample file per sidecar type (10 files). |
| `tests/fixtures/config_files/` | Valid TOML, partial TOML, invalid TOML. |

#### Steps

1. Create the `tests/fixtures/` directory tree with all required sub-directories.
2. Create test fixture files: exiftool mock responses (at least 2 JSON files), sidecar samples (one per type, 10 files), config test files (valid, partial, invalid TOML).
3. Write `tests/unit/test_traversal.py` — 9 test cases.
4. Write `tests/unit/test_exif.py` — 7 test cases (mock exiftool by default).
5. Write `tests/unit/test_sidecar.py` — 9 test cases using the sidecar fixture files.
6. Write `tests/unit/test_entry.py` — 8 test cases with mocked dependencies.
7. Write `tests/unit/test_serializer.py` — 7 test cases.
8. Write `tests/unit/test_rename.py` — 4 test cases.
9. Write `tests/integration/test_single_file.py` — 6 end-to-end cases.
10. Write `tests/integration/test_directory_flat.py` — 3 cases.
11. Write `tests/integration/test_directory_recursive.py` — 4 cases.
12. Write `tests/integration/test_output_modes.py` — 5 cases.
13. Write `tests/integration/test_cli.py` — 14 cases.
14. Write `tests/conformance/test_v2_schema.py` — 13 validation cases + 4 serialization invariants.
15. Run `pytest tests/unit/` — all must pass.
16. Run `pytest tests/integration/` — all must pass (with `exiftool` mocked if not installed).
17. Run `pytest tests/conformance/` — all must pass.
18. Run `ruff check src/` — zero errors.

#### Exit Criteria

- [ ] `shruggie-indexer <path-to-a-real-file>` produces valid v2 JSON on stdout.
- [ ] `shruggie-indexer <path-to-a-directory> --recursive` produces valid v2 JSON with nested `items`.
- [ ] `shruggie-indexer <path> --outfile out.json` writes to `out.json`.
- [ ] `shruggie-indexer <path> --inplace` writes a `_meta2.json` sidecar.
- [ ] `shruggie-indexer <path> --meta` includes sidecar metadata in output (when sidecars exist).
- [ ] `shruggie-indexer <path> --rename --dry-run` reports proposed renames without modifying files.
- [ ] `pytest tests/unit/` — all pass.
- [ ] `pytest tests/integration/` — all pass (with `exiftool` mocked if not installed).
- [ ] `pytest tests/conformance/` — all pass (v2 schema validation).
- [ ] `ruff check src/` — zero errors.

---

## Milestone 3 — GUI, Packaging, and Release Infrastructure

**Goal:** Build the desktop GUI application, create all build/packaging scripts, configure CI/CD pipelines, scaffold the documentation site, and add platform-specific tests. At the end of this milestone, the repository is release-ready: both CLI and GUI executables can be built, CI runs the full test suite on all target platforms, and the documentation site is deployable.

**Depends on:** Milestone 2 (the complete core engine and CLI must be functional).

---

### Sprint 3.1 — GUI Application

**Goal:** Implement the full desktop GUI application in a single `app.py` module using CustomTkinter. The GUI provides a visual frontend to the same library code used by the CLI.

#### Spec References

The implementing agent for Sprint 3.1 MUST have the following in its context window:

| Source | Sections / Files |
|--------|-----------------|
| [§10.1 — GUI Framework and Architecture](shruggie-indexer-spec.md#101-gui-framework-and-architecture) | CustomTkinter, dark theme, threading model, queue-based communication, `after()` polling |
| [§10.2 — Window Layout](shruggie-indexer-spec.md#102-window-layout) | 1100×750 default, 140px sidebar, 4 operation tabs, Settings tab |
| [§10.3 — Target Selection and Input](shruggie-indexer-spec.md#103-target-selection-and-input) | Path entry, Browse button, type radios, recursive checkbox, per-tab input forms |
| [§10.4 — Configuration Panel](shruggie-indexer-spec.md#104-configuration-panel) | Settings tab controls |
| [§10.5 — Indexing Execution and Progress](shruggie-indexer-spec.md#105-indexing-execution-and-progress) | Threaded background execution, indeterminate/determinate progress, cooperative cancellation |
| [§10.6 — Output Display and Export](shruggie-indexer-spec.md#106-output-display-and-export) | Dual-view output (JSON/Log), syntax highlighting, Copy/Save buttons, large output handling |
| [§10.7 — Keyboard Shortcuts and Accessibility](shruggie-indexer-spec.md#107-keyboard-shortcuts-and-accessibility) | Ctrl+R run, Ctrl+C copy, Ctrl+S save, Ctrl+. cancel, Ctrl+1–4 tabs, Ctrl+Q quit |
| [§11.1 — Logging Architecture](shruggie-indexer-spec.md#111-logging-architecture) | Logging format for GUI log panel |
| [§11.6 — Progress Reporting](shruggie-indexer-spec.md#116-progress-reporting) | Progress callback interface |
| [§13.3 — Entry Points and Console Scripts](shruggie-indexer-spec.md#133-entry-points-and-console-scripts) | `[project.gui-scripts]` entry point |
| Milestone 1 + 2 source files | Specifically: `models/schema.py` (GUI displays these), `config/types.py` + `config/loader.py` (GUI constructs config), `core/entry.py` (GUI calls `index_path()`), `core/serializer.py` (GUI calls `serialize_entry()`) |

#### Deliverables

| File | Description |
|------|-------------|
| `src/shruggie_indexer/gui/app.py` | `ShruggiIndexerApp` — CustomTkinter dark-theme desktop app. 1100×750 default. 140px sidebar with 4 operation tabs (Index, Meta Merge, Meta Merge Delete, Rename) + separator + Settings. Per-tab input forms with target selection (path entry + Browse + type radios + recursive checkbox) and tab-specific options. Threaded background execution (`threading.Thread` + `queue.Queue` + 50ms `after()` polling). Cooperative cancellation via `threading.Event`. Progress display (indeterminate during discovery, determinate during processing). Dual-view output panel (JSON / Log). JSON viewer with optional syntax highlighting. Copy + Save buttons. Keyboard shortcuts (Ctrl+R run, Ctrl+C copy, Ctrl+S save, Ctrl+. cancel, Ctrl+1–4 tabs, Ctrl+Q quit). Session persistence. Large output handling (>1MB no highlighting, >10MB summary only). `main()` entry point for `[project.gui-scripts]`. |

#### Steps

1. Create the `ShruggiIndexerApp` class inheriting from `customtkinter.CTk`. Set default geometry to 1100×750. Apply dark theme.
2. Build the 140px sidebar with 4 operation tab buttons (Index, Meta Merge, Meta Merge Delete, Rename) and a separator followed by a Settings button.
3. Implement the per-tab content frames with target selection controls: path entry field, Browse button for file/folder dialog, file/directory type radio buttons, recursive checkbox, and tab-specific option controls.
4. Implement the Settings tab per §10.4 with configuration controls that map to `IndexerConfig` fields.
5. Implement threaded background execution: `threading.Thread` for the indexing operation, `queue.Queue` for result communication, 50ms `after()` polling loop for UI updates.
6. Implement cooperative cancellation via `threading.Event` — a Cancel button sets the event, which is checked by the core engine at probe points.
7. Implement progress display: indeterminate progress bar during discovery phase, determinate progress bar during processing phase.
8. Implement the dual-view output panel with JSON and Log tabs. JSON view with optional syntax highlighting. Large output handling: disable highlighting >1MB, show summary only >10MB.
9. Implement Copy and Save buttons for the output panel.
10. Bind all keyboard shortcuts per §10.7: Ctrl+R (run), Ctrl+C (copy), Ctrl+S (save), Ctrl+. (cancel), Ctrl+1–4 (tab switching), Ctrl+Q (quit).
11. Implement session persistence for the last-used settings.
12. Create the `main()` entry point function for `[project.gui-scripts]`.
13. Update `src/shruggie_indexer/gui/__init__.py` with appropriate exports.

#### Exit Criteria

- [ ] `pip install -e ".[gui]"` succeeds.
- [ ] `shruggie-indexer-gui` launches the GUI window without errors.
- [ ] GUI can index a single file and display v2 JSON output.
- [ ] GUI cancel button stops a running operation.
- [ ] All keyboard shortcuts function correctly.

---

### Sprint 3.2 — Build Scripts, Packaging, and CI/CD

**Goal:** Create the PyInstaller build scripts (PowerShell + Bash), PyInstaller spec files for CLI and GUI executables, and GitHub Actions CI/CD workflows for automated releases and documentation deployment. The `venv-setup` and `test` script pairs were created during pre-sprint scaffolding and already exist in `scripts/`.

#### Spec References

The implementing agent for Sprint 3.2 MUST have the following in its context window:

| Source | Sections / Files |
|--------|-----------------|
| [§3.5 — Scripts and Build Tooling](shruggie-indexer-spec.md#35-scripts-and-build-tooling) | Script inventory, naming conventions, purposes |
| [§13.2 — pyproject.toml Configuration](shruggie-indexer-spec.md#132-pyprojecttoml-configuration) | Dependency groups for `[dev]` and `[gui]` extras |
| [§13.4 — Standalone Executable Builds](shruggie-indexer-spec.md#134-standalone-executable-builds) | PyInstaller configuration: `--onefile`, `--console`/`--windowed`, exclusions, UPX, asset bundling |
| [§13.5 — Release Artifact Inventory](shruggie-indexer-spec.md#135-release-artifact-inventory) | 8 artifacts per release, naming scheme |
| [§13.5.1 — GitHub Actions Release Pipeline](shruggie-indexer-spec.md#1351-github-actions-release-pipeline) | Release workflow: trigger, matrix, stages, artifact upload |
| [§14.5 — Cross-Platform Test Matrix](shruggie-indexer-spec.md#145-cross-platform-test-matrix) | CI matrix: windows-latest, ubuntu-latest, macos-13, macos-latest |
| [§3.7 — Documentation Site](shruggie-indexer-spec.md#37-documentation-site) | MkDocs configuration for docs deployment workflow |
| [§3.7.4 — Deployment](shruggie-indexer-spec.md#374-deployment) | `mkdocs gh-deploy --force` |

#### Deliverables

**Build Scripts:**

| File | Description |
|------|-------------|
| `scripts/build.ps1` | PowerShell: PyInstaller build for CLI + GUI executables. |
| `scripts/build.sh` | Bash equivalent. |

> **Note:** `scripts/venv-setup.ps1`, `scripts/venv-setup.sh`, `scripts/test.ps1`, and `scripts/test.sh` already exist (created during pre-sprint scaffolding). They are not deliverables of this sprint.

**PyInstaller Spec Files:**

| File | Description |
|------|-------------|
| `shruggie-indexer-cli.spec` | `--onefile --console`. Excludes tkinter/customtkinter. UPX compression. |
| `shruggie-indexer-gui.spec` | `--onefile --windowed`. Excludes click. UPX compression. Bundles CustomTkinter assets. |

**CI/CD Workflows:**

| File | Description |
|------|-------------|
| `.github/workflows/release.yml` | Triggers on `v*` tag push. Matrix: windows-latest, ubuntu-latest, macos-13 (x64), macos-latest (arm64). Stages: checkout → test → build CLI + GUI → rename artifacts → upload → create release. 8 artifacts per release. |
| `.github/workflows/docs.yml` | Triggers on push to `main` when `docs/` or `mkdocs.yml` change. `mkdocs build --strict` → `mkdocs gh-deploy --force`. |

#### Steps

1. Create `scripts/build.ps1`: activate venv, run PyInstaller with both spec files, verify output executables in `dist/`.
2. Create `scripts/build.sh`: equivalent Bash script.
3. Create `shruggie-indexer-cli.spec`: PyInstaller spec for `--onefile --console`, exclude tkinter/customtkinter, enable UPX compression.
4. Create `shruggie-indexer-gui.spec`: PyInstaller spec for `--onefile --windowed`, exclude click, enable UPX compression, bundle CustomTkinter assets.
5. Create `.github/workflows/release.yml`: trigger on `v*` tag push, 4-platform matrix (windows-latest, ubuntu-latest, macos-13, macos-latest), stages for checkout → test → build → rename → upload → release. Produce 8 artifacts per release (CLI + GUI × 4 platforms).
6. Create `.github/workflows/docs.yml`: trigger on docs changes, run `mkdocs build --strict`, deploy with `mkdocs gh-deploy --force`.
7. Validate all scripts are syntactically correct and the YAML workflows pass `yamllint` or equivalent.

#### Exit Criteria

- [ ] `scripts/build.ps1` produces `dist/shruggie-indexer-cli.exe` and `dist/shruggie-indexer-gui.exe`.
- [ ] `shruggie-indexer-cli.spec` and `shruggie-indexer-gui.spec` are valid PyInstaller spec files.
- [ ] `.github/workflows/release.yml` is valid YAML with correct matrix and stage definitions.
- [ ] `.github/workflows/docs.yml` is valid YAML with correct trigger and deploy commands.

---

### Sprint 3.3 — Documentation, Platform Tests, and Final Validation

**Goal:** Create the MkDocs site configuration, populate the README, write platform-specific tests, and perform a full end-to-end validation of the entire repository to confirm release readiness.

#### Spec References

The implementing agent for Sprint 3.3 MUST have the following in its context window:

| Source | Sections / Files |
|--------|-----------------|
| [§3.6 — Documentation Artifacts](shruggie-indexer-spec.md#36-documentation-artifacts) | Documentation file inventory and descriptions |
| [§3.7 — Documentation Site](shruggie-indexer-spec.md#37-documentation-site) | MkDocs configuration overview |
| [§3.7.1 — Site Configuration](shruggie-indexer-spec.md#371-site-configuration) | Full `mkdocs.yml` content: Material theme, navigation structure, strict mode |
| [§3.7.2 — Non-Markdown Asset Handling](shruggie-indexer-spec.md#372-non-markdown-asset-handling) | JSON schema and script file handling in docs |
| [§3.7.3 — Build and Preview](shruggie-indexer-spec.md#373-build-and-preview) | `mkdocs build --strict`, `mkdocs serve` |
| [§3.7.5 — Dependencies](shruggie-indexer-spec.md#375-dependencies) | MkDocs-related Python packages |
| [§14.5 — Cross-Platform Test Matrix](shruggie-indexer-spec.md#145-cross-platform-test-matrix) | Platform-specific test requirements |
| [§14.6 — Backward Compatibility Validation](shruggie-indexer-spec.md#146-backward-compatibility-validation) | v1→v2 compatibility test concepts |
| [§14.7 — Performance Benchmarks](shruggie-indexer-spec.md#147-performance-benchmarks) | Benchmark test structure |
| [§15.1 — Cross-Platform Design Principles](shruggie-indexer-spec.md#151-cross-platform-design-principles) | Platform abstraction strategy |
| [§15.2 — Windows-Specific Considerations](shruggie-indexer-spec.md#152-windows-specific-considerations) | Junction detection, long paths, UNC paths |
| [§15.3 — Linux and macOS Considerations](shruggie-indexer-spec.md#153-linux-and-macos-considerations) | Permission handling, case sensitivity |
| [§15.4 — Filesystem Behavior Differences](shruggie-indexer-spec.md#154-filesystem-behavior-differences) | Cross-platform filesystem behavior matrix |
| [§15.5 — Creation Time Portability](shruggie-indexer-spec.md#155-creation-time-portability) | `st_birthtime` availability per platform |
| [§15.6 — Symlink and Reparse Point Handling](shruggie-indexer-spec.md#156-symlink-and-reparse-point-handling) | Platform-specific symlink behavior |
| [§2.1 — Project Identity](shruggie-indexer-spec.md#21-project-identity) | Project description and metadata for README |

#### Deliverables

**Documentation:**

| File | Description |
|------|-------------|
| `mkdocs.yml` | Full MkDocs configuration per §3.7.1: Material theme, navigation structure, strict mode. |
| `docs/schema/index.md` | Schema reference landing page (stub content for MVP). |
| `README.md` | Project overview, installation, quick-start, CLI usage summary, links to docs. |

**Platform Tests:**

| File | Description |
|------|-------------|
| `tests/platform/__init__.py` | Empty. |
| `tests/platform/test_timestamps_platform.py` | 4 cases: `st_birthtime` availability (macOS/Windows), `st_ctime` fallback (Linux), creation time accuracy, timezone handling. |
| `tests/platform/test_symlinks_platform.py` | 5 cases: symlink detection, dangling symlink handling, directory symlink, junction detection (Windows), symlink name-hash fallback. |

#### Steps

1. Create `mkdocs.yml` with the full Material theme configuration per §3.7.1. Define the complete navigation structure referencing all existing docs. Enable strict mode.
2. Update `docs/schema/index.md` with a stub schema reference landing page.
3. Write `README.md` with: project overview and description, badges (license, version, CI status), installation instructions (pip, standalone executables), quick-start CLI examples, Python API usage snippet, link to full documentation site, link to the technical specification.
4. Create `tests/platform/__init__.py`.
5. Write `tests/platform/test_timestamps_platform.py` — 4 platform-conditional test cases: `st_birthtime` availability test (macOS/Windows only), `st_ctime` fallback test (Linux only), creation time accuracy validation, timezone handling verification. Use `pytest.mark.skipif` for platform-gating.
6. Write `tests/platform/test_symlinks_platform.py` — 5 platform-conditional test cases: symlink detection, dangling symlink handling, directory symlink traversal, junction detection (Windows only), symlink name-hash fallback.
7. Run `mkdocs build --strict` — must succeed without warnings.
8. Run `pytest tests/platform/` — must pass on the current platform (skipping non-applicable tests).
9. Run the full test suite: `pytest tests/` — all tests across all directories must pass.
10. Run `ruff check src/` — zero errors.
11. Verify the complete file manifest against the list below.

#### Exit Criteria

- [ ] `mkdocs build --strict` — succeeds without warnings.
- [ ] `pytest tests/platform/` — passes on the current platform (skips non-applicable tests).
- [ ] `pytest tests/` — full suite passes.
- [ ] `ruff check src/` — zero errors.
- [ ] `README.md` contains installation instructions, quick-start, and links to docs.

---

## Complete File Manifest

All files created or modified across all three milestones, in dependency order.

### Milestone 1 — 22 files (3 sprints)

**Sprint 1.1 — 12 files:**
```
pyproject.toml
.gitignore
.python-version
src/shruggie_indexer/__init__.py
src/shruggie_indexer/__main__.py
src/shruggie_indexer/_version.py
src/shruggie_indexer/exceptions.py
src/shruggie_indexer/core/__init__.py
src/shruggie_indexer/models/__init__.py
src/shruggie_indexer/config/__init__.py
src/shruggie_indexer/cli/__init__.py
src/shruggie_indexer/gui/__init__.py
```

**Sprint 1.2 — 4 files:**
```
src/shruggie_indexer/models/schema.py
src/shruggie_indexer/config/types.py
src/shruggie_indexer/config/defaults.py
src/shruggie_indexer/config/loader.py
```

**Sprint 1.3 — 8 files:**
```
src/shruggie_indexer/core/paths.py
src/shruggie_indexer/core/hashing.py
src/shruggie_indexer/core/timestamps.py
tests/conftest.py
tests/unit/__init__.py
tests/unit/test_hashing.py
tests/unit/test_paths.py
tests/unit/test_timestamps.py
tests/unit/test_schema.py
tests/unit/test_config.py
```

### Milestone 2 — 25 files (3 sprints)

**Sprint 2.1 — 3 files:**
```
src/shruggie_indexer/core/traversal.py
src/shruggie_indexer/core/exif.py
src/shruggie_indexer/core/sidecar.py
```

**Sprint 2.2 — 6 files (4 new + 2 updated):**
```
src/shruggie_indexer/core/entry.py
src/shruggie_indexer/core/serializer.py
src/shruggie_indexer/core/rename.py
src/shruggie_indexer/cli/main.py
src/shruggie_indexer/__init__.py              (updated)
src/shruggie_indexer/core/__init__.py          (updated)
```

**Sprint 2.3 — 16 files:**
```
tests/unit/test_traversal.py
tests/unit/test_exif.py
tests/unit/test_sidecar.py
tests/unit/test_entry.py
tests/unit/test_serializer.py
tests/unit/test_rename.py
tests/integration/__init__.py
tests/integration/test_single_file.py
tests/integration/test_directory_flat.py
tests/integration/test_directory_recursive.py
tests/integration/test_output_modes.py
tests/integration/test_cli.py
tests/conformance/__init__.py
tests/conformance/test_v2_schema.py
tests/fixtures/                                (directory + sample files)
```

### Milestone 3 — 16 files (3 sprints)

**Sprint 3.1 — 1 file:**
```
src/shruggie_indexer/gui/app.py
```

**Sprint 3.2 — 10 files:**
```
scripts/venv-setup.ps1
scripts/venv-setup.sh
scripts/build.ps1
scripts/build.sh
scripts/test.ps1
scripts/test.sh
shruggie-indexer-cli.spec
shruggie-indexer-gui.spec
.github/workflows/release.yml
.github/workflows/docs.yml
```

**Sprint 3.3 — 5 files:**
```
mkdocs.yml
docs/schema/index.md
README.md                                      (content populated)
tests/platform/__init__.py
tests/platform/test_timestamps_platform.py
tests/platform/test_symlinks_platform.py
```

**Total: ~63 files** across 3 milestones / 9 sprints.

---

## Risk Notes

| Risk | Mitigation |
|------|------------|
| `config/defaults.py` is the single most complex file (massive regex patterns, BCP 47 alternation). | Port directly from `MakeIndex(MetadataFileParser).ps1` with the file in context. Validate each regex against the original's test expectations. |
| `core/sidecar.py` has 10 type detectors with format-specific parsing logic. | The `MetaFileRead_DependencyCatalog.md` documents every code path. Keep it in context during Sprint 2.1. |
| GUI is a large single-file module for MVP. | The spec explicitly permits a single `app.py` for MVP with an option to decompose later. Follow the `shruggie-feedtools` GUI as the visual reference. |
| PyInstaller builds are platform-sensitive. | Build scripts are paired (`.ps1`/`.sh`). CI matrix covers all 4 target platform variants. |
| `pyexiftool` batch mode may behave differently across platforms. | Dual backend (batch + subprocess fallback) provides resilience. Tests mock exiftool by default; `@pytest.mark.requires_exiftool` gates real-binary tests. |

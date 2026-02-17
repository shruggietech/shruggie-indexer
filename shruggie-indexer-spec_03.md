## 3. Repository Structure

This section defines the complete file and directory layout of the `shruggie-indexer` repository. The structure follows the conventions established by `shruggie-feedtools` (see §1.5, External References) — specifically the `src`-layout packaging pattern, the `scripts/` directory for platform-paired build and setup scripts, and the separation of porting-reference documentation from project documentation. Where this section does not explicitly define a convention, the `shruggie-feedtools` repository is the normative reference.

All paths in this section are relative to the repository root unless otherwise noted.

### 3.1. Top-Level Layout

```
shruggie-indexer/
├── .github/
│   └── workflows/
│       └── release.yml
├── docs/
│   ├── porting-reference/
│   └── user/
├── scripts/
├── src/
│   └── shruggie_indexer/
├── tests/
├── .gitignore
├── .python-version
├── LICENSE
├── README.md
├── pyproject.toml
├── shruggie-indexer-plan.md
└── shruggie-indexer-spec.md
```

| Path | Type | Description |
|------|------|-------------|
| `.github/workflows/` | Directory | GitHub Actions CI/CD pipeline definitions. Contains at minimum `release.yml` for the release build pipeline (see §13). |
| `docs/` | Directory | All project documentation beyond the top-level planning and specification files. Subdivided into `porting-reference/` (original implementation reference materials) and `user/` (end-user documentation). See §3.6. |
| `scripts/` | Directory | Platform-paired shell scripts for development environment setup, build automation, and test execution. See §3.5. |
| `src/shruggie_indexer/` | Directory | The Python source package. All importable code lives here. See §3.2. |
| `tests/` | Directory | All test code. Mirrors the source package structure. See §3.4. |
| `.gitignore` | File | Standard Python `.gitignore` covering `__pycache__/`, `*.pyc`, `.venv/`, `dist/`, `build/`, `*.egg-info/`, IDE/editor files, OS artifacts, and PyInstaller working directories. |
| `.python-version` | File | Contains the string `3.12` (no minor patch). Used by `pyenv` and similar version managers to auto-select the correct interpreter. |
| `LICENSE` | File | Full Apache 2.0 license text, obtained from [https://www.apache.org/licenses/LICENSE-2.0.txt](https://www.apache.org/licenses/LICENSE-2.0.txt). |
| `README.md` | File | Project overview, installation instructions, quick-start usage examples, and links to full documentation. |
| `pyproject.toml` | File | Centralized project metadata, build system configuration, dependency declarations, entry points, and tool settings (`ruff`, `pytest`, `pyinstaller`). See §13.2. |
| `shruggie-indexer-plan.md` | File | Sprint-based implementation plan. Lives at the repository root for top-level visibility, consistent with `shruggie-feedtools`. |
| `shruggie-indexer-spec.md` | File | This technical specification (or a consolidated single-file version of it). Lives at the repository root for top-level visibility. |

The `src`-layout (source code under `src/shruggie_indexer/` rather than a bare `shruggie_indexer/` at the root) is a deliberate choice inherited from `shruggie-feedtools`. It prevents accidental imports of the development source tree during testing — `import shruggie_indexer` in tests always resolves to the installed package, not the working directory. This is the layout recommended by the Python Packaging Authority and enforced by `hatchling` by default.

### 3.2. Source Package Layout

```
src/shruggie_indexer/
├── __init__.py
├── __main__.py
├── _version.py
├── core/
│   ├── __init__.py
│   ├── traversal.py
│   ├── paths.py
│   ├── hashing.py
│   ├── timestamps.py
│   ├── exif.py
│   ├── sidecar.py
│   ├── entry.py
│   ├── serializer.py
│   └── rename.py
├── models/
│   ├── __init__.py
│   └── schema.py
├── config/
│   ├── __init__.py
│   ├── types.py
│   ├── defaults.py
│   └── loader.py
├── cli/
│   ├── __init__.py
│   └── main.py
└── gui/
    ├── __init__.py
    └── app.py
```

#### Top-Level Package Files

| File | Purpose |
|------|---------|
| `__init__.py` | Public API surface. Exports the primary programmatic entry points (e.g., `index_path()`, `index_file()`, `index_directory()`) and the configuration constructor. Consumers who `import shruggie_indexer` interact through this module. See §9.1. |
| `__main__.py` | Enables `python -m shruggie_indexer` invocation. Contains only an import and call to `cli.main.main()`. No logic beyond the entry-point dispatch. |
| `_version.py` | Single source of truth for the package version string: `__version__ = "0.1.0"`. Read by `pyproject.toml` (via `hatchling`'s version plugin), by `__init__.py` for the public `__version__` attribute, and by the CLI `--version` flag. This is the same version management pattern used by `shruggie-feedtools`. |

#### `core/` — Indexing Engine

The `core/` subpackage contains all indexing logic. Every module in `core/` corresponds to one or more operation categories from the Operations Catalog (§1.5). The CLI and GUI are thin presentation layers that call into `core/` — no indexing logic lives outside this subpackage.

| Module | Operations Catalog Categories | Responsibility |
|--------|-------------------------------|----------------|
| `traversal.py` | Cat 1 (Filesystem Traversal & Discovery) | Enumerates files and directories within a target path. Supports recursive and non-recursive modes via a single parameterized function (DEV-03). Applies configurable filesystem exclusion filters. Classifies items as files or directories. Yields items to the entry-construction pipeline. |
| `paths.py` | Cat 2 (Path Resolution & Manipulation) | The single `resolve_path()` utility (DEV-04) plus path component extraction (parent, name, stem, suffix) and extension validation against the configurable regex pattern (DEV-14). All callers — traversal, hashing, entry construction — use this one module for path operations. |
| `hashing.py` | Cat 3 (Hashing & Identity Generation) | Provides `hash_file()` (content hashing) and `hash_string()` (name hashing) functions that compute all four algorithms (MD5, SHA1, SHA256, SHA512) in a single pass (DEV-01, DEV-02). Computes null-hash constants at module load time (DEV-09). Constructs `HashSet` objects. Implements the directory two-layer identity scheme (`hash(hash(name) + hash(parentName))`). Prefixes identities with `y` (file), `x` (directory), or `z` (generated metadata). |
| `timestamps.py` | Cat 5 (Filesystem Timestamps & Date Conversion) | Derives Unix timestamps (milliseconds) and ISO 8601 strings directly from `os.stat()` results (DEV-07). Handles creation-time portability: `st_birthtime` on macOS, `st_ctime` on Windows, documented fallback on Linux. Constructs `TimestampPair` and `TimestampsObject` model instances. |
| `exif.py` | Cat 6 (EXIF / Embedded Metadata Extraction) | Invokes `exiftool` as a subprocess with arguments passed as plain Python lists (DEV-05). Parses JSON output directly with `json.loads()` (DEV-06). Filters unwanted keys via dict comprehension. Respects the configurable exiftool file-type exclusion list. Handles `exiftool` absence gracefully (warning, not fatal). |
| `sidecar.py` | Cat 7 (Sidecar Metadata File Handling) | Discovers sidecar metadata files by matching filenames against the configurable regex identification patterns from `MetadataFileParser`. Classifies sidecars by type (Description, JsonMetadata, Hash, Link, Subtitles, Thumbnail, etc.). Reads and parses sidecar content with format-specific handlers (JSON, plain text, hash files, URL/LNK shortcuts). Constructs `MetadataEntry` model instances. This is the Python equivalent of the original `MetaFileRead` function. |
| `entry.py` | Cat 8 (Output Object Construction & Schema) | Orchestrates the construction of a single `IndexEntry` from a filesystem path. Calls into `paths`, `hashing`, `timestamps`, `exif`, and `sidecar` to gather all components, then assembles the final v2 schema object. This is the Python equivalent of the original `MakeObject` / `MakeFileIndex` / `MakeDirectoryIndex` family of functions. |
| `serializer.py` | Cat 9 (JSON Serialization & Output Routing) | Converts `IndexEntry` model instances to JSON. Routes output to stdout, a single aggregate file, or per-item in-place sidecar files (`_meta2.json` / `_directorymeta2.json`), depending on the active output mode. Handles pretty-printing vs. compact output. Optionally uses `orjson` for performance when available. |
| `rename.py` | Cat 10 (File Rename & In-Place Write) | Implements the `StorageName` rename operation: renames files and directories from their original names to their hash-based `storage_name` values. Handles collision detection, dry-run mode, and rollback on partial failure. |

The `core/__init__.py` file SHOULD re-export the primary orchestration functions (e.g., `index_path`, `index_file`, `index_directory`) so that internal callers can write `from shruggie_indexer.core import index_path` without reaching into individual modules. The individual modules remain importable for callers who need fine-grained access (e.g., `from shruggie_indexer.core.hashing import hash_file`).

#### `models/` — Data Structures

| Module | Responsibility |
|--------|----------------|
| `schema.py` | Defines the v2 output schema as Python data structures — `IndexEntry`, `NameObject`, `HashSet`, `SizeObject`, `TimestampPair`, `TimestampsObject`, `ParentObject`, `MetadataEntry`, and any supporting types. Implemented as `dataclasses` for the stdlib-only core (see G5 in §2.3), with optional Pydantic models behind an import guard for consumers who want runtime schema validation. Includes serialization helpers (`to_dict()`, `to_json()`) that produce schema-compliant output. |

**Rationale for `models/` as a separate subpackage:** In `shruggie-feedtools`, the Pydantic schema models live inside `core/schema.py`. That works for feedtools because its model layer is relatively flat (one `FeedOutput` model with nested item objects). The indexer's model layer is more complex — the v2 schema defines seven distinct sub-object types, the `IndexEntry` itself is recursive (the `items` field contains child `IndexEntry` objects), and the configuration system introduces a parallel set of typed structures (see `config/types.py` below). Separating `models/` from `core/` avoids circular import risks between the configuration types that `core/` modules consume and the schema types that `core/` modules produce. It also provides a clean import path for external consumers who need the types without pulling in the engine: `from shruggie_indexer.models import IndexEntry`.

> **Deviation note:** This is a structural departure from the `shruggie-feedtools` convention of keeping schema models inside `core/`. The departure is justified by the added complexity of the indexer's type hierarchy and the circular-import risk it introduces. If during implementation the `models/` subpackage proves to contain only `schema.py` with no future growth path, collapsing it back into `core/schema.py` is an acceptable simplification — but the separation SHOULD be the starting point.

#### `config/` — Configuration System

| Module | Responsibility |
|--------|----------------|
| `types.py` | Defines the typed configuration dataclasses: the top-level `IndexerConfig` and any nested structures for metadata file parser settings, exiftool exclusion lists, filesystem exclusion filters, extension validation patterns, and sidecar suffix patterns. These are the Python equivalent of the original `$global:MetadataFileParser` ordered hashtable, restructured into a typed hierarchy. See §7.1. |
| `defaults.py` | Contains the hardcoded default values for every configuration field. This is the baseline configuration that applies when no user configuration file is present. The defaults reproduce the behavioral intent of the original's hardcoded values (regex patterns, exclusion lists, extension groups) while extending them for cross-platform coverage (DEV-10). See §7.2. |
| `loader.py` | Reads TOML configuration files via `tomllib` (stdlib, Python 3.11+), validates their structure against the `types.py` dataclasses, and merges user-provided values over the defaults. Implements the override/merge strategy defined in §7.7. Provides the `load_config()` function consumed by the CLI, GUI, and public API. |

The `config/__init__.py` file SHOULD export `IndexerConfig`, `load_config()`, and `get_default_config()` as the public configuration API.

#### `cli/` — Command-Line Interface

| Module | Responsibility |
|--------|----------------|
| `main.py` | Defines the CLI entry point using `click` (preferred) or `argparse` (stdlib fallback). Parses command-line arguments, constructs an `IndexerConfig`, calls into `core/` to perform the requested operation, and routes output via `serializer`. Contains no indexing logic — it is a pure presentation layer. Registered as the `shruggie-indexer` console script entry point in `pyproject.toml`. See §8. |

The `cli/` subpackage is intentionally minimal for the MVP. If the CLI grows to support subcommands in future versions, additional modules (e.g., `cli/commands/`) can be added without restructuring.

#### `gui/` — Graphical User Interface

| Module | Responsibility |
|--------|----------------|
| `app.py` | The standalone desktop GUI application built with CustomTkinter. Modeled after the `shruggie-feedtools` GUI: two-panel layout, dark theme, shared font stack and appearance conventions. Provides a visual frontend to the same `core/` library code used by the CLI. Shipped as a separate PyInstaller-built executable artifact. See the GUI specification section of this document. |

The `gui/` subpackage is isolated from the rest of the package — it imports from `core/`, `models/`, and `config/`, but nothing outside `gui/` imports from it. The `customtkinter` dependency is declared as an optional extra (`pip install shruggie-indexer[gui]`) and is only imported inside `gui/`. This ensures that the CLI and library surfaces function without any GUI dependencies installed.

If the GUI grows in complexity (custom widgets, asset files, multiple views), additional modules and an `assets/` subdirectory can be added under `gui/` without restructuring.

### 3.3. Configuration File Locations

The indexer's configuration system uses a layered resolution strategy. The following locations are checked in order, with later sources overriding earlier ones:

| Priority | Location | Description |
|----------|----------|-------------|
| 1 (lowest) | Compiled defaults | The values in `config/defaults.py`. Always present. |
| 2 | User config directory | `~/.config/shruggie-indexer/config.toml` on Linux/macOS, `%APPDATA%\shruggie-indexer\config.toml` on Windows. Per-user persistent configuration. |
| 3 | Project/working directory | `./shruggie-indexer.toml` in the current working directory. Per-project overrides. |
| 4 (highest) | CLI flags | Command-line arguments override all file-based configuration. |

The user config directory path is resolved using Python's `platformdirs` conventions (or a manual equivalent using `os.environ` lookups for `XDG_CONFIG_HOME` / `APPDATA`). The implementation MUST NOT hardcode platform-specific paths — the resolution logic must work correctly on all three target platforms.

Configuration files are TOML format, parsed by `tomllib` (stdlib). See §7.6 for the file format specification and §7.7 for the merge/override behavior.

No configuration file is required. The tool MUST operate correctly using only compiled defaults. If no configuration files are found at any of the checked locations, the tool proceeds silently with default configuration — it does NOT produce a warning or error about missing configuration files.

### 3.4. Test Directory Layout

```
tests/
├── conftest.py
├── fixtures/
│   ├── sample_files/
│   ├── sample_trees/
│   ├── sidecar_samples/
│   ├── exiftool_responses/
│   └── config_files/
├── unit/
│   ├── __init__.py
│   ├── test_traversal.py
│   ├── test_paths.py
│   ├── test_hashing.py
│   ├── test_timestamps.py
│   ├── test_exif.py
│   ├── test_sidecar.py
│   ├── test_entry.py
│   ├── test_serializer.py
│   ├── test_rename.py
│   ├── test_schema.py
│   └── test_config.py
├── integration/
│   ├── __init__.py
│   ├── test_single_file.py
│   ├── test_directory_flat.py
│   ├── test_directory_recursive.py
│   ├── test_output_modes.py
│   └── test_cli.py
├── conformance/
│   ├── __init__.py
│   └── test_v2_schema.py
└── platform/
    ├── __init__.py
    ├── test_timestamps_platform.py
    └── test_symlinks_platform.py
```

| Directory | Purpose |
|-----------|---------|
| `conftest.py` | Shared pytest fixtures, temporary directory setup, `exiftool` mock/skip markers, and common test utilities. |
| `fixtures/` | Static test data files consumed by tests. `sample_files/` contains individual files of various types for single-file indexing tests. `sample_trees/` contains pre-built directory hierarchies for traversal and recursive indexing tests. `sidecar_samples/` contains sidecar metadata files of each supported type. `exiftool_responses/` contains captured JSON outputs for mocking exiftool in unit tests. `config_files/` contains valid, invalid, and partial TOML configuration files for config-loading tests. |
| `unit/` | Unit tests. Each `test_*.py` file corresponds to the `core/`, `models/`, or `config/` module it exercises. Tests in this directory mock external dependencies (exiftool, filesystem) and validate individual function behavior in isolation. |
| `integration/` | Integration tests. Exercise the full indexing pipeline end-to-end — from a real filesystem path to a validated JSON output — without mocking the core engine. `exiftool` may still be mocked or skipped (via pytest markers) in CI environments where it is not installed. |
| `conformance/` | Schema conformance tests. Validate that the JSON output produced by the tool conforms to the v2 JSON Schema definition. These tests load the canonical v2 schema from its published URL (or a local copy) and run `jsonschema` validation against actual indexer output. |
| `platform/` | Platform-specific tests. Exercise behaviors that vary by operating system — creation-time availability, symlink semantics, case-sensitivity, path-length limits. These tests use pytest markers to conditionally skip on platforms where the tested behavior is not applicable. |

The test directory does NOT mirror the `src/shruggie_indexer/` package hierarchy directory-for-directory. Instead, test files are grouped by test type (unit, integration, conformance, platform) with a flat file layout within each group. This is a deliberate choice: the test type grouping is more useful for CI matrix configuration (run unit tests everywhere, run platform tests conditionally) than a structural mirror would be.

Test files MUST be runnable with a bare `pytest` invocation from the repository root. The `pyproject.toml` `[tool.pytest.ini_options]` section configures `testpaths = ["tests"]` and registers custom markers for platform-conditional and exiftool-dependent tests.

### 3.5. Scripts and Build Tooling

```
scripts/
├── venv-setup.ps1
├── venv-setup.sh
├── build.ps1
├── build.sh
├── test.ps1
└── test.sh
```

Scripts are provided in platform-paired sets: `.ps1` (PowerShell, for Windows) and `.sh` (Bash, for Linux/macOS). This is the same convention used by `shruggie-feedtools`.

| Script Pair | Purpose |
|-------------|---------|
| `venv-setup.ps1` / `venv-setup.sh` | Creates a Python virtual environment (`.venv/`), activates it, installs the package in editable mode (`pip install -e ".[dev,gui]"`), and verifies that the `shruggie-indexer` console script is available. Checks for the correct Python version before proceeding. Idempotent — safe to re-run. |
| `build.ps1` / `build.sh` | Runs the PyInstaller build to produce standalone executables. Builds both the CLI executable and the GUI executable as separate artifacts. Outputs to `dist/`. See §13.4. |
| `test.ps1` / `test.sh` | Runs the full test suite via `pytest`. Accepts optional arguments to control scope (e.g., `./test.sh unit` to run only unit tests). Sets up any required environment variables and ensures the virtual environment is active. |

Scripts MUST be executable without arguments for the default behavior. Optional arguments (e.g., test scope, build target) are documented in a comment block at the top of each script.

All scripts assume they are invoked from the repository root. They MUST NOT `cd` into subdirectories as part of their operation — all paths within the scripts are relative to the repository root.

### 3.6. Documentation Artifacts

```
docs/
├── porting-reference/
│   ├── MakeIndex_DependencyCatalog.md
│   ├── Base64DecodeString_DependencyCatalog.md
│   ├── Date2UnixTime_DependencyCatalog.md
│   ├── DirectoryId_DependencyCatalog.md
│   ├── FileId_DependencyCatalog.md
│   ├── MetaFileRead_DependencyCatalog.md
│   ├── TempOpen_DependencyCatalog.md
│   ├── TempClose_DependencyCatalog.md
│   ├── Vbs_DependencyCatalog.md
│   ├── MakeIndex_OperationsCatalog.md
│   ├── MakeIndex_OutputSchema.json
│   └── MakeIndex(MetadataFileParser).ps1
└── user/
    └── (end-user documentation, post-MVP)
```

| Directory | Purpose |
|-----------|---------|
| `porting-reference/` | Reference materials derived from the original PowerShell implementation. These documents inform the port but are not part of the runtime codebase. They include dependency catalogs for each of the eight ported pslib functions, the operations catalog mapping original logic to Python modules, the v1 output schema (for porting reference only — the port does not target v1), and the isolated `MetadataFileParser` object definition. These files are committed to the repository for traceability and to support AI implementation agents who may need to consult them during sprint execution. They are read-only reference artifacts — they are never modified after initial commit unless an error in the original documentation is discovered. |
| `user/` | End-user documentation: installation guide, usage examples, configuration reference, and changelog. This directory is a post-MVP deliverable. For the v0.1.0 release, user-facing documentation is limited to the `README.md` at the repository root. |

**Important constraint (reiterated from §1.2):** The original PowerShell source code for the `MakeIndex` function — including its complete function body, parameter block, and all nested sub-functions — SHALL NOT be included in the repository in any form. The `MakeIndex(MetadataFileParser).ps1` file in `porting-reference/` is permitted because it contains only the configuration data object, not the function's implementation logic. The dependency catalogs and operations catalog describe behavior in prose, not source code. No file in `porting-reference/` contains executable `MakeIndex` source.

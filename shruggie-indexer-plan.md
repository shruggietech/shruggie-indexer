<a id="shruggie-indexer-plan-of-action"></a>
# shruggie-indexer — Plan of Action

- **Project:** `shruggie-indexer`
- **Version Target:** 0.1.0 (MVP)
- **Date:** 2026-02-19
- **Status:** DRAFT — Iteration 1

---

## Overview

This plan defines a condensed, dependency-ordered build sequence for the `shruggie-indexer` v0.1.0 MVP. The entire MVP is structured into **three build phases** designed to be completable within a single full workday. Each phase is sized to fit comfortably within the standard context window of Claude Opus 4.6 (~200K tokens) while maximizing the amount of work accomplished per phase.

### Guiding Constraints

| Constraint | Strategy |
|------------|----------|
| **Context window fit** | Each phase references only the spec sections and reference docs it needs. No phase requires the full 9,180-line spec in context. File manifests and spec section references replace inline behavioral restatements — the implementing agent reads the cited sections directly. |
| **Minimal phase count** | Three phases. Work is consolidated aggressively — the only reason to split work across phases is a hard dependency (Phase 2 builds on Phase 1 outputs, Phase 3 builds on Phase 2 outputs). |
| **Dependency ordering** | Phase 1 produces every module that later phases import. Phase 2 consumes Phase 1 artifacts to build the engine and its primary interface. Phase 3 adds the secondary interface and release infrastructure on top of the complete engine. |
| **Single workday** | Estimated 8–10 hours total. Phase 1 ≈ 2.5h, Phase 2 ≈ 4h, Phase 3 ≈ 3h. Estimates assume AI-assisted implementation with the spec as the source of truth. |

### Phase Dependency Chain

```
Phase 1: Scaffold + Data Layer + Core Utilities
    │
    │  provides: models/, config/, core/paths.py, core/hashing.py,
    │            core/timestamps.py, pyproject.toml, package skeleton
    ▼
Phase 2: Processing Engine + CLI
    │
    │  provides: core/traversal.py, core/exif.py, core/sidecar.py,
    │            core/entry.py, core/serializer.py, core/rename.py,
    │            cli/main.py, unit + integration + conformance tests
    ▼
Phase 3: GUI + Packaging + Release Infrastructure
    │
    │  provides: gui/app.py, scripts/, .spec files, CI workflows,
    │            mkdocs.yml, platform tests, README.md
    ▼
   MVP Complete (v0.1.0)
```

---

## Phase 1 — Scaffold, Data Layer, and Core Utilities

**Goal:** Establish the repository skeleton, define all data structures and configuration types, and implement the stateless utility modules that every subsequent module depends on. At the end of this phase, the project is installable (`pip install -e .`), all model classes are importable, configuration loads from defaults, and the three foundational core modules (paths, hashing, timestamps) are functional and unit-tested.

**Estimated duration:** 2.5 hours

### 1.1. Deliverables

#### Repository Scaffolding

| File | Description |
|------|-------------|
| `pyproject.toml` | Full canonical content per §13.2. Build system, metadata, deps, entry points, tool config. |
| `.gitignore` | Standard Python gitignore (see §3.1). |
| `.python-version` | Contains `3.12`. |
| `src/shruggie_indexer/__init__.py` | Public API re-exports + `__version__`. Stub imports for names not yet implemented (Phase 2). |
| `src/shruggie_indexer/__main__.py` | `python -m` entry point — import and call `cli.main.main`. |
| `src/shruggie_indexer/_version.py` | `__version__ = "0.1.0"` |
| `src/shruggie_indexer/core/__init__.py` | Re-exports for orchestration functions (stubs until Phase 2). |
| `src/shruggie_indexer/models/__init__.py` | Re-exports from `schema.py`. |
| `src/shruggie_indexer/config/__init__.py` | Re-exports `IndexerConfig`, `load_config()`. |
| `src/shruggie_indexer/cli/__init__.py` | Empty. |
| `src/shruggie_indexer/gui/__init__.py` | Empty. |

#### Data Models (`models/`)

| File | Description |
|------|-------------|
| `src/shruggie_indexer/models/schema.py` | All v2 schema dataclasses: `IndexEntry`, `HashSet`, `NameObject`, `SizeObject`, `TimestampPair`, `TimestampsObject`, `ParentObject`, `FileSystemObject`, `AttributesObject`, `MetadataEntry`, `MetadataAttributes`. Serialization helpers (`to_dict()`). |

#### Configuration System (`config/`)

| File | Description |
|------|-------------|
| `src/shruggie_indexer/config/types.py` | `IndexerConfig` frozen dataclass + all nested config types (`MetadataTypeConfig`, `ExiftoolConfig`, `SidecarConfig`, etc.). |
| `src/shruggie_indexer/config/defaults.py` | All compiled default values: 10 sidecar regex patterns (including the BCP 47 subtitle alternation), 7 extension group classifications, filesystem exclusion lists, exiftool exclusion list, include/exclude patterns. Ported from `MakeIndex(MetadataFileParser).ps1`. |
| `src/shruggie_indexer/config/loader.py` | `load_config()`: TOML file discovery (platform-aware paths), parsing via `tomllib`, 4-layer merge (defaults → user → project → overrides), validation. |

#### Core Utilities (`core/`)

| File | Description |
|------|-------------|
| `src/shruggie_indexer/core/paths.py` | `resolve_path()`, `extract_components()`, `validate_extension()`, `build_sidecar_path()`. Forward-slash normalization for relative paths. |
| `src/shruggie_indexer/core/hashing.py` | `hash_file()`, `hash_string()`, `hash_directory_id()`, `select_id()`, `NULL_HASHES`. Single-pass multi-algorithm (MD5+SHA256, opt-in SHA512). 64KB chunks. NFC normalization. Uppercase hex. Null-hash = `hash(b"0")` computed at load time. `x`/`y`/`z` prefix logic. |
| `src/shruggie_indexer/core/timestamps.py` | `extract_timestamps()`. `os.stat()`/`os.lstat()` → `TimestampPair` + `TimestampsObject`. `st_birthtime` → `st_ctime` fallback. Millisecond Unix + microsecond ISO 8601. |

#### Exception Hierarchy

| Location | Classes |
|----------|---------|
| `src/shruggie_indexer/models/schema.py` (or a dedicated `exceptions.py`) | `IndexerError` (base), `IndexerConfigError`, `IndexerTargetError`, `IndexerRuntimeError`, `RenameError`, `IndexerCancellationError`. |

#### Phase 1 Tests

| File | Description |
|------|-------------|
| `tests/conftest.py` | Shared fixtures: `sample_file`, `sample_tree`, `default_config`, `mock_exiftool`. |
| `tests/unit/__init__.py` | Empty. |
| `tests/unit/test_hashing.py` | 12 cases per §14.2: MD5+SHA256 correctness, SHA512 opt-in, single-pass equivalence, empty file, large file (>64KB), NFC normalization, null-hash constants, `hash_directory_id` two-layer scheme, `select_id` prefix logic, `HashSet` construction. |
| `tests/unit/test_paths.py` | 11 cases per §14.2: absolute/relative resolution, component extraction, extension validation, forward-slash normalization, UNC paths (Windows), long paths, Unicode filenames, sidecar path construction. |
| `tests/unit/test_timestamps.py` | 6 cases per §14.2: mtime/atime/ctime extraction, ISO 8601 format validation, millisecond Unix conversion, symlink `lstat()` timestamps, missing `st_birthtime` fallback. |
| `tests/unit/test_schema.py` | 5 cases per §14.2: dataclass construction, `to_dict()` round-trip, required vs. optional fields, `schema_version` presence, nested object construction. |
| `tests/unit/test_config.py` | 8 cases per §14.2: default config construction, TOML parsing, layer merging, scalar override, collection replace, `_append` merge, validation rejection, missing file tolerance. |

### 1.2. Spec Sections Required in Context

The implementing agent for Phase 1 MUST have the following in its context window:

| Source | Sections / Files |
|--------|-----------------|
| `shruggie-indexer-spec.md` | §2.1 (Project Identity), §2.6 (Intentional Deviations — all 16 DEV items), §3.1–3.3 (Repository Structure, Source Package Layout, Config File Locations), §5.1–5.12 (Output Schema — all field definitions and type definitions), §7.1–7.7 (Configuration — full section), §9.1–9.4 (Public API Surface, Data Classes, Exceptions, Configuration API), §13.2 (pyproject.toml), §14.2 (Unit Test Coverage — test_hashing, test_paths, test_timestamps, test_schema, test_config) |
| `docs/schema/shruggie-indexer-v2.schema.json` | Full file (canonical v2 schema definition) |
| `docs/porting-reference/MakeIndex(MetadataFileParser).ps1` | Full file (regex patterns, extension groups, exclusion lists for `config/defaults.py`) |
| `docs/porting-reference/DirectoryId_DependencyCatalog.md` | Full file (two-layer hashing scheme) |
| `docs/porting-reference/FileId_DependencyCatalog.md` | Full file (content hashing, null-hash, prefix logic) |
| `docs/porting-reference/Date2UnixTime_DependencyCatalog.md` | Full file (timestamp conversion — for understanding what DEV-07 eliminates) |

### 1.3. Exit Criteria

- [ ] `pip install -e ".[dev]"` succeeds from the repository root.
- [ ] `python -c "from shruggie_indexer.models.schema import IndexEntry, HashSet, NameObject"` succeeds.
- [ ] `python -c "from shruggie_indexer.config import load_config; c = load_config(); print(c)"` succeeds and prints a populated `IndexerConfig`.
- [ ] `python -c "from shruggie_indexer.core.hashing import hash_file, hash_string, NULL_HASHES"` succeeds.
- [ ] `pytest tests/unit/test_hashing.py tests/unit/test_paths.py tests/unit/test_timestamps.py tests/unit/test_schema.py tests/unit/test_config.py` — all pass.
- [ ] `ruff check src/` — zero errors.

---

## Phase 2 — Processing Engine and CLI

**Goal:** Implement the complete indexing pipeline (traversal, EXIF extraction, sidecar metadata discovery/parsing, entry orchestration, JSON serialization, rename operations), wire it up through the CLI, and validate with unit tests, integration tests, and schema conformance tests. At the end of this phase, `shruggie-indexer <target>` produces valid v2 JSON output for any input path.

**Estimated duration:** 4 hours

**Depends on:** Phase 1 (models, config, paths, hashing, timestamps all must exist).

### 2.1. Deliverables

#### Core Engine Modules (`core/`)

| File | Description |
|------|-------------|
| `src/shruggie_indexer/core/traversal.py` | `list_children()`. Single-pass `os.scandir()`, configurable filesystem exclusions, recursive/non-recursive modes, sorted output, symlink-aware classification. |
| `src/shruggie_indexer/core/exif.py` | `extract_exif()`, `_exiftool_available()`. `pyexiftool` batch mode primary backend (DEV-16), `subprocess.run()` + argfile fallback. JSON parsing (DEV-06). Key filtering via dict comprehension. Extension-gate from config. 30s timeout. Graceful degradation when `exiftool` absent. |
| `src/shruggie_indexer/core/sidecar.py` | `discover_and_parse()`. Pre-enumerate siblings via `os.scandir()`. 10 type detectors (Description, DesktopIni, GenericMetadata, Hash, JsonMetadata, Link, Screenshot, Subtitles, Thumbnail, Torrent) matched against configurable regex patterns. Format-specific readers: JSON → plain text → binary fallback chain. Base64 encoding for binary content. `MetadataEntry` construction with full provenance (filesystem, size, timestamps). MetaMerge queue building. MetaMergeDelete safety gates. |
| `src/shruggie_indexer/core/entry.py` | `build_file_entry()` (12-step orchestration), `build_directory_entry()`, `index_path()`. Hub-and-spoke calls to hashing, timestamps, exif, sidecar, paths. Progress callback support. Cooperative cancellation via `threading.Event`. |
| `src/shruggie_indexer/core/serializer.py` | `serialize_entry()`, `write_output()`, `write_inplace()`. `orjson` primary serializer with `json.dumps()` fallback. Three independent output modes: stdout, outfile (aggregate), inplace (per-item sidecar `_meta2.json` / `_directorymeta2.json`). Atomic file writes. `schema_version` always first key. Pretty-print vs. compact. `ensure_ascii=False`. |
| `src/shruggie_indexer/core/rename.py` | `rename_item()`, `build_storage_path()`. Hash-based `storage_name` derivation. Collision detection (inode comparison). Dry-run mode. MetaMergeDelete-safe guard. `shutil.move()` fallback. |

#### CLI (`cli/`)

| File | Description |
|------|-------------|
| `src/shruggie_indexer/cli/main.py` | `click`-based CLI. All options per §8: `TARGET`, `--file`/`--directory`, `--recursive`/`--no-recursive`, `--stdout`/`--no-stdout`, `--outfile`, `--inplace`, `--meta`/`--meta-merge`/`--meta-merge-delete`, `--rename`, `--dry-run`, `--id-type`, `--compute-sha512`, `-v`/`-vv`/`-vvv`, `-q`, `--version`. Exit codes as `IntEnum` (0–5). Implication chains. `configure_logging()` with `SessionFilter`. `tqdm` progress for TTY, log-line milestones for non-TTY. Optional `rich` colorization. Two-phase SIGINT handling. |

#### Update Stubs from Phase 1

| File | Change |
|------|--------|
| `src/shruggie_indexer/__init__.py` | Replace stub imports with real imports from `core/entry.py`. Wire up full `__all__` with 21 public names. |
| `src/shruggie_indexer/core/__init__.py` | Replace stubs with real re-exports of `index_path`, `build_file_entry`, `build_directory_entry`. |

#### Phase 2 Tests

| File | Description |
|------|-------------|
| `tests/unit/test_traversal.py` | 9 cases: flat listing, recursive listing, exclusion filtering, symlink handling, empty directory, deeply nested, hidden files, sort order, mixed file/dir classification. |
| `tests/unit/test_exif.py` | 7 cases: successful extraction, exiftool absent (graceful skip), extension-gated skip, key filtering, timeout handling, malformed JSON response, batch vs. fallback parity. |
| `tests/unit/test_sidecar.py` | 9 cases: each of the 10 sidecar types (combined where trivial), no-match (no sidecars found), JSON parse, text parse, binary-to-Base64, MetadataEntry provenance fields, MetaMergeDelete queue population. |
| `tests/unit/test_entry.py` | 8 cases: file entry construction, directory entry construction, symlink entry, recursive directory, cancellation mid-traversal, progress callback invocation, missing exiftool degradation, sidecar folding. |
| `tests/unit/test_serializer.py` | 7 cases: JSON round-trip, `schema_version` first key, `sha512` omission when not computed, pretty vs. compact, `ensure_ascii=False`, stdout output, inplace file naming. |
| `tests/unit/test_rename.py` | 4 cases: successful rename, dry-run (no filesystem change), collision detection, storage_name derivation. |
| `tests/integration/test_single_file.py` | 6 cases: index a real file end-to-end, validate v2 output structure, hash correctness against known digest, timestamp plausibility, extension extraction, MIME type. |
| `tests/integration/test_directory_flat.py` | 3 cases: flat directory indexing, item count matches, child entries are files. |
| `tests/integration/test_directory_recursive.py` | 4 cases: recursive traversal depth, nested directory identity, parent references, item ordering. |
| `tests/integration/test_output_modes.py` | 5 cases: stdout capture, outfile write, inplace sidecar write, combined modes, empty directory output. |
| `tests/integration/test_cli.py` | 14 cases: `--help`, `--version`, default invocation, `--file` mode, `--directory` mode, `--recursive`/`--no-recursive`, `--outfile`, `--inplace`, `--meta-merge`, `--rename --dry-run`, `--id-type sha256`, `--compute-sha512`, verbosity levels, invalid target (exit code 3). |
| `tests/integration/__init__.py` | Empty. |
| `tests/conformance/__init__.py` | Empty. |
| `tests/conformance/test_v2_schema.py` | 13 cases per §14.4: file entry validates, directory entry validates, recursive entry validates, symlink entry validates, all-null optional fields validate, MetadataEntry validates, minimal entry validates, extra fields rejected (additionalProperties), `schema_version` wrong value rejected, required field missing rejected. Plus 4 serialization invariants: key ordering, `sha512` omission, Unicode preservation, `null` vs. absent. |

#### Test Fixtures

| Path | Description |
|------|-------------|
| `tests/fixtures/exiftool_responses/` | At least 2 captured JSON responses for mocking. |
| `tests/fixtures/sidecar_samples/` | One sample file per sidecar type (10 files). |
| `tests/fixtures/config_files/` | Valid TOML, partial TOML, invalid TOML. |

### 2.2. Spec Sections Required in Context

The implementing agent for Phase 2 MUST have the following in its context window:

| Source | Sections / Files |
|--------|-----------------|
| `shruggie-indexer-spec.md` | §2.6 (Intentional Deviations — for reference during implementation), §4.1–4.6 (Architecture — full section), §6.1–6.10 (Core Operations — full section), §8.1–8.11 (CLI Interface — full section), §11.1–11.6 (Logging and Diagnostics — full section), §14.2–14.4 (Unit Tests, Integration Tests, Conformance Tests) |
| `docs/porting-reference/MakeIndex_OperationsCatalog.md` | Full file (operation-to-module mapping, Python module recommendations) |
| `docs/porting-reference/MakeIndex_DependencyCatalog.md` | Full file (top-level orchestration logic, parameter handling, sub-function inventory) |
| `docs/porting-reference/MetaFileRead_DependencyCatalog.md` | Full file (sidecar parsing logic, format-specific handlers, fallback chain) |
| `docs/porting-reference/MakeIndex(MetadataFileParser).ps1` | Full file (sidecar regex patterns — needed during `sidecar.py` implementation) |
| `docs/schema/shruggie-indexer-v2.schema.json` | Full file (for serializer output validation and conformance tests) |
| Phase 1 source files | All `.py` files created in Phase 1 (models, config, paths, hashing, timestamps) — the implementing agent must see the actual interfaces it is calling into |

### 2.3. Exit Criteria

- [ ] `shruggie-indexer --help` prints usage and exits 0.
- [ ] `shruggie-indexer --version` prints `0.1.0` and exits 0.
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

## Phase 3 — GUI, Packaging, and Release Infrastructure

**Goal:** Build the desktop GUI application, create all build/packaging scripts, configure CI/CD pipelines, scaffold the documentation site, and add platform-specific tests. At the end of this phase, the repository is release-ready: both CLI and GUI executables can be built, CI runs the full test suite on all target platforms, and the documentation site is deployable.

**Estimated duration:** 3 hours

**Depends on:** Phase 2 (the complete core engine and CLI must be functional).

### 3.1. Deliverables

#### GUI Application (`gui/`)

| File | Description |
|------|-------------|
| `src/shruggie_indexer/gui/app.py` | `ShruggiIndexerApp` — CustomTkinter dark-theme desktop app. 1100×750 default. 140px sidebar with 4 operation tabs (Index, Meta Merge, Meta Merge Delete, Rename) + separator + Settings. Per-tab input forms with target selection (path entry + Browse + type radios + recursive checkbox) and tab-specific options. Threaded background execution (`threading.Thread` + `queue.Queue` + 50ms `after()` polling). Cooperative cancellation via `threading.Event`. Progress display (indeterminate during discovery, determinate during processing). Dual-view output panel (JSON / Log). JSON viewer with optional syntax highlighting. Copy + Save buttons. Keyboard shortcuts (Ctrl+R run, Ctrl+C copy, Ctrl+S save, Ctrl+. cancel, Ctrl+1–4 tabs, Ctrl+Q quit). Session persistence. Large output handling (>1MB no highlighting, >10MB summary only). `main()` entry point for `[project.gui-scripts]`. |

#### Build Scripts (`scripts/`)

| File | Description |
|------|-------------|
| `scripts/venv-setup.ps1` | PowerShell: create `.venv/`, install `pip install -e ".[dev,gui]"`, verify `shruggie-indexer` on PATH. |
| `scripts/venv-setup.sh` | Bash equivalent. |
| `scripts/build.ps1` | PowerShell: PyInstaller build for CLI + GUI executables. |
| `scripts/build.sh` | Bash equivalent. |
| `scripts/test.ps1` | PowerShell: run `pytest` with optional scope argument. |
| `scripts/test.sh` | Bash equivalent. |

#### PyInstaller Spec Files

| File | Description |
|------|-------------|
| `shruggie-indexer-cli.spec` | `--onefile --console`. Excludes tkinter/customtkinter. UPX compression. |
| `shruggie-indexer-gui.spec` | `--onefile --windowed`. Excludes click. UPX compression. Bundles CustomTkinter assets. |

#### CI/CD Workflows

| File | Description |
|------|-------------|
| `.github/workflows/release.yml` | Triggers on `v*` tag push. Matrix: windows-latest, ubuntu-latest, macos-13 (x64), macos-latest (arm64). Stages: checkout → test → build CLI + GUI → rename artifacts → upload → create release. 8 artifacts per release. |
| `.github/workflows/docs.yml` | Triggers on push to `main` when `docs/` or `mkdocs.yml` change. `mkdocs build --strict` → `mkdocs gh-deploy --force`. |

#### Documentation Site

| File | Description |
|------|-------------|
| `mkdocs.yml` | Full MkDocs configuration per §3.7: Material theme, navigation structure, strict mode. |
| `docs/schema/index.md` | Schema reference landing page (stub content for MVP). |
| `README.md` | Project overview, installation, quick-start, CLI usage summary, links to docs. |

#### Platform Tests

| File | Description |
|------|-------------|
| `tests/platform/__init__.py` | Empty. |
| `tests/platform/test_timestamps_platform.py` | 4 cases: `st_birthtime` availability (macOS/Windows), `st_ctime` fallback (Linux), creation time accuracy, timezone handling. |
| `tests/platform/test_symlinks_platform.py` | 5 cases: symlink detection, dangling symlink handling, directory symlink, junction detection (Windows), symlink name-hash fallback. |

### 3.2. Spec Sections Required in Context

The implementing agent for Phase 3 MUST have the following in its context window:

| Source | Sections / Files |
|--------|-----------------|
| `shruggie-indexer-spec.md` | §3.5 (Scripts and Build Tooling), §3.7 (Documentation Site — full subsection), §10.1–10.7 (GUI Application — full section), §11.1–11.6 (Logging — for GUI log panel format), §13.1–13.6 (Packaging and Distribution — full section), §14.5–14.7 (Platform Tests, Backward Compatibility, Performance Benchmarks), §15.1–15.6 (Platform Portability — full section) |
| Phase 1 + Phase 2 source files | Specifically: `models/schema.py` (GUI displays these), `config/types.py` + `config/loader.py` (GUI constructs config), `core/entry.py` (GUI calls `index_path()`), `core/serializer.py` (GUI calls `serialize_entry()`), `cli/main.py` (reference for logging setup pattern) |

### 3.3. Exit Criteria

- [ ] `pip install -e ".[gui]"` succeeds.
- [ ] `shruggie-indexer-gui` launches the GUI window without errors.
- [ ] GUI can index a single file and display v2 JSON output.
- [ ] GUI cancel button stops a running operation.
- [ ] `scripts/venv-setup.ps1` creates and configures a working venv on Windows.
- [ ] `scripts/build.ps1` produces `dist/shruggie-indexer-cli.exe` and `dist/shruggie-indexer-gui.exe`.
- [ ] `pytest tests/platform/` — passes on the current platform (skips non-applicable tests).
- [ ] `pytest tests/` — full suite passes.
- [ ] `ruff check src/` — zero errors.
- [ ] `mkdocs build --strict` — succeeds without warnings.
- [ ] `.github/workflows/release.yml` is valid YAML with correct matrix and stage definitions.

---

## Complete File Manifest

All files created or modified across all three phases, in dependency order.

### Phase 1 — 22 files

```
pyproject.toml
.gitignore
.python-version
src/shruggie_indexer/__init__.py
src/shruggie_indexer/__main__.py
src/shruggie_indexer/_version.py
src/shruggie_indexer/core/__init__.py
src/shruggie_indexer/models/__init__.py
src/shruggie_indexer/models/schema.py
src/shruggie_indexer/config/__init__.py
src/shruggie_indexer/config/types.py
src/shruggie_indexer/config/defaults.py
src/shruggie_indexer/config/loader.py
src/shruggie_indexer/core/paths.py
src/shruggie_indexer/core/hashing.py
src/shruggie_indexer/core/timestamps.py
src/shruggie_indexer/cli/__init__.py
src/shruggie_indexer/gui/__init__.py
tests/conftest.py
tests/unit/__init__.py
tests/unit/test_hashing.py
tests/unit/test_paths.py
tests/unit/test_timestamps.py
tests/unit/test_schema.py
tests/unit/test_config.py
```

### Phase 2 — 25 files (6 new core + 1 CLI + 2 updated + 16 test files/dirs)

```
src/shruggie_indexer/core/traversal.py
src/shruggie_indexer/core/exif.py
src/shruggie_indexer/core/sidecar.py
src/shruggie_indexer/core/entry.py
src/shruggie_indexer/core/serializer.py
src/shruggie_indexer/core/rename.py
src/shruggie_indexer/cli/main.py
src/shruggie_indexer/__init__.py              (updated)
src/shruggie_indexer/core/__init__.py          (updated)
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

### Phase 3 — 16 files

```
src/shruggie_indexer/gui/app.py
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
mkdocs.yml
docs/schema/index.md
README.md                                      (content populated)
tests/platform/__init__.py
tests/platform/test_timestamps_platform.py
tests/platform/test_symlinks_platform.py
```

**Total: ~63 files** across 3 phases.

---

## Risk Notes

| Risk | Mitigation |
|------|------------|
| `config/defaults.py` is the single most complex file (massive regex patterns, BCP 47 alternation). | Port directly from `MakeIndex(MetadataFileParser).ps1` with the file in context. Validate each regex against the original's test expectations. |
| `core/sidecar.py` has 10 type detectors with format-specific parsing logic. | The `MetaFileRead_DependencyCatalog.md` documents every code path. Keep it in context during Phase 2. |
| GUI is a large single-file module for MVP. | The spec explicitly permits a single `app.py` for MVP with an option to decompose later. Follow the `shruggie-feedtools` GUI as the visual reference. |
| PyInstaller builds are platform-sensitive. | Build scripts are paired (`.ps1`/`.sh`). CI matrix covers all 4 target platform variants. |
| `pyexiftool` batch mode may behave differently across platforms. | Dual backend (batch + subprocess fallback) provides resilience. Tests mock exiftool by default; `@pytest.mark.requires_exiftool` gates real-binary tests. |


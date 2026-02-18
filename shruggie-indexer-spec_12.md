## 12. External Dependencies

This section catalogs every dependency — binary, standard library, and third-party — that `shruggie-indexer` consumes at runtime, during testing, or during build/packaging. It defines which dependencies are required, which are optional, how optional dependencies are declared and gated, and which original dependencies are eliminated by the port. The section serves both as a dependency manifest for implementers and as the normative reference for the `[project.dependencies]` and `[project.optional-dependencies]` tables in `pyproject.toml` (§13.2).

The dependency architecture implements design goal G5 (§2.3): the core indexing engine runs using only the Python standard library plus `exiftool` as an external binary. All third-party Python packages are optional enhancements isolated behind import guards or declared as extras. A bare `pip install shruggie-indexer` installs zero third-party packages — the `[project.dependencies]` list is empty.

> **Dependency philosophy:** The original `MakeIndex` has an implicit dependency set — it calls functions, invokes binaries, and reads global variables without any declaration mechanism. An implementer must trace every code path to discover what is required. The port makes every dependency explicit: external binaries are probed at runtime (§12.5), standard library modules are imported at the top of each file, and third-party packages are declared in `pyproject.toml` with version constraints. Nothing is silently assumed to exist.

### 12.1. Required External Binaries

`exiftool` is the sole external binary dependency of the entire project. No other binary is required at runtime on any platform.

#### exiftool

| Field | Value |
|-------|-------|
| Binary name | `exiftool` |
| Minimum version | ≥ 12.0 |
| Purpose | Extraction of EXIF, XMP, IPTC, and other embedded metadata from media files |
| Required by | `core/exif.py` (§6.6) |
| Resolution | Must be present on the system `PATH`. Resolved via `shutil.which("exiftool")` at runtime (§12.5). |
| Cross-platform availability | Available on Windows, Linux, and macOS. See [https://exiftool.org/](https://exiftool.org/) for platform-specific installation. |
| Failure behavior | Graceful degradation — if `exiftool` is absent, the `metadata` array in all `IndexEntry` output omits the `exiftool.json_metadata` entry; all other indexing operations (hashing, timestamps, sidecar metadata, identity generation) continue normally (§4.5). |

The minimum version requirement of ≥ 12.0 is driven by the use of the `-api requestall=3` and `-api largefilesupport=1` arguments (§6.6), which were stabilized in exiftool 12.x. The port does not enforce version checking at runtime — an older exiftool will likely work for most files but may produce incomplete or incorrect metadata for some edge cases. Version checking is a potential post-MVP enhancement.

> **Deviation from original:** The original depends on two external binaries: `exiftool` and `jq`. The `jq` dependency is eliminated entirely (DEV-06, §2.6) — JSON parsing is handled natively by `json.loads()` and unwanted keys are removed with a dict comprehension. Additionally, `MetaFileRead` in the original depends on `certutil` (a Windows-only system utility) for Base64 encoding of binary sidecar file contents. The port replaces `certutil` with Python's `base64.b64encode()`, which is cross-platform, requires no subprocess invocation, and is part of the standard library. See §12.4 for the complete elimination catalog.

### 12.2. Python Standard Library Modules

The core indexing engine (`core/`, `config/`, `models/`) uses only standard library modules. The following table lists every stdlib module imported by the source package, organized by the component that consumes them. This is not a theoretical "might use" list — it is the definitive set of imports an implementer will write.

#### Core engine modules

| Standard library module | Consuming package module(s) | Purpose |
|-------------------------|-----------------------------|---------|
| `base64` | `core/sidecar.py` | Base64 encoding of binary sidecar file contents (screenshots, thumbnails, torrents). Replaces the original's `certutil` pipeline (DEV-05). |
| `dataclasses` | `config/types.py`, `models/schema.py` | Frozen dataclass definitions for `IndexerConfig`, `IndexEntry`, and all v2 schema sub-objects. `dataclasses.asdict()` used by the serializer (§6.9). |
| `datetime` | `core/timestamps.py` | ISO 8601 string generation from `os.stat()` float values via `datetime.fromtimestamp()` and `.isoformat()`. |
| `hashlib` | `core/hashing.py` | All hash computation — MD5, SHA1, SHA256, SHA512 for both file content and string inputs. Multi-algorithm single-pass hashing via `hashlib.new()` (§6.3). |
| `json` | `core/serializer.py`, `core/exif.py`, `core/sidecar.py` | JSON parsing of exiftool output (`json.loads()`), JSON parsing of sidecar metadata files, and JSON serialization of `IndexEntry` output (`json.dumps()`). |
| `logging` | All modules | Per-module loggers via `logging.getLogger(__name__)`. Logging configuration in CLI and GUI entry points (§11). |
| `os` | `core/traversal.py`, `core/timestamps.py`, `core/hashing.py` | `os.stat()` for timestamp extraction and file size. `os.walk()` as an alternative traversal backend. `os.fsdecode()` for filename handling. |
| `pathlib` | `core/traversal.py`, `core/paths.py`, `core/entry.py`, `core/rename.py`, `config/loader.py` | Path resolution, component extraction, directory enumeration (`Path.iterdir()`), glob matching, and path arithmetic. Central to the cross-platform path abstraction (§6.2). |
| `re` | `core/sidecar.py`, `config/defaults.py`, `config/loader.py` | Regex matching for sidecar file type detection, filesystem exclusion filters, and extension validation. Compiles the patterns from the `MetadataFileParser` configuration (§7.3). |
| `shutil` | `core/exif.py`, `core/rename.py` | `shutil.which()` for exiftool binary probing (§12.5). `shutil.move()` as a cross-filesystem rename fallback (§6.10). |
| `subprocess` | `core/exif.py` | Invocation of `exiftool` via `subprocess.run()` with argument lists (§6.6). |
| `tempfile` | (not used) | See note below. |
| `time` | `cli/main.py`, `core/entry.py` | `time.perf_counter()` for elapsed-time measurement in progress reporting and per-item trace logging (§11.6). |
| `tomllib` | `config/loader.py` | TOML configuration file parsing (§7.6). Standard library since Python 3.11; the `>=3.12` floor (§2.5) guarantees availability. |
| `typing` | All modules | Type annotations: `Optional`, `Callable`, `Sequence`, `Literal`, etc. Used for function signatures, dataclass field types, and `TYPE_CHECKING` import guards. |
| `uuid` | `cli/main.py`, `gui/app.py` | Session ID generation via `uuid.uuid4()` (§11.4). |

**Note on `tempfile`:** The original uses `TempOpen`/`TempClose` for temporary file management during exiftool argument passing. The port eliminates temporary files entirely (DEV-05, §2.6) — exiftool arguments are passed as a direct argument list to `subprocess.run()`, requiring no intermediary file. Python's `tempfile` module is not imported by any module in the source package. If a future enhancement requires temporary files (e.g., for batch exiftool mode via `-@ argfile`), `tempfile.NamedTemporaryFile` with automatic cleanup is the correct approach — not a reimplementation of the `TempOpen`/`TempClose` pattern.

#### Additional stdlib modules used by entry points and packaging

| Standard library module | Consuming module(s) | Purpose |
|-------------------------|---------------------|---------|
| `sys` | `cli/main.py`, `gui/app.py` | `sys.stdout` for JSON output, `sys.stderr` for log output, `sys.exit()` for exit code propagation. |
| `queue` | `gui/app.py` | `queue.Queue` for thread-safe communication between the indexing worker thread and the GUI main thread (§10.5). |
| `threading` | `gui/app.py` | `threading.Thread` for running the indexing operation off the main thread to keep the GUI responsive (§10.5). |
| `platform` | `core/timestamps.py` | `platform.system()` for platform-conditional creation-time extraction (`st_birthtime` on macOS, `st_ctime` on Windows, fallback on Linux) (§6.5). |
| `functools` | `core/exif.py`, `config/defaults.py` | `functools.lru_cache` for caching the exiftool availability probe result (§12.5). |
| `collections` | `core/serializer.py` | `collections.OrderedDict` for placing `schema_version` first in serialized output (§6.9). |

### 12.3. Third-Party Python Packages

All third-party packages are optional. The `[project.dependencies]` list in `pyproject.toml` is empty — a bare `pip install shruggie-indexer` installs zero third-party runtime dependencies. Third-party packages are declared as extras in `[project.optional-dependencies]` and are imported behind conditional guards that fail gracefully (with a clear error message or silent fallback) when the package is not installed.

The extras are organized by delivery surface, matching the three-surface architecture (G3, §2.3):

```toml
# pyproject.toml (illustrative excerpt — see §13.2 for the full file)

[project.optional-dependencies]
cli = ["click>=8.1"]
gui = ["customtkinter>=5.2"]
perf = ["orjson>=3.9", "pyexiftool>=0.5"]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "jsonschema>=4.17",
    "pydantic>=2.0",
    "ruff>=0.3",
    "tqdm>=4.65",
    "rich>=13.0",
]
all = ["shruggie-indexer[cli,gui,perf]"]
```

#### Per-package details

**`click`** (extra: `cli`)

| Field | Value |
|-------|-------|
| Version constraint | `>=8.1` |
| Purpose | CLI argument parsing, option groups, help text generation, mutual exclusion enforcement (§8) |
| Imported by | `cli/main.py` exclusively |
| Import guard | The `cli/main.py` module imports `click` at the top level. If `click` is not installed and the user invokes the CLI entry point, the `ImportError` is caught in `__main__.py` and produces a clear message: `"The CLI requires the 'click' package. Install it with: pip install shruggie-indexer[cli]"`. |
| Why not `argparse` | `click` provides decorator-based option declaration, automatic mutual exclusion (`@click.option(cls=MutuallyExclusiveOption)`), typed parameter conversion, and composable help text groups — all of which the CLI requires (§8). Using `argparse` would require reimplementing these capabilities manually. The `click` dependency is scoped to the `cli` extra and does not affect library consumers. |

**`customtkinter`** (extra: `gui`)

| Field | Value |
|-------|-------|
| Version constraint | `>=5.2` |
| Purpose | Desktop GUI widget toolkit (§10) |
| Imported by | `gui/app.py` exclusively |
| Import guard | Same pattern as `click`: `ImportError` caught at the GUI entry point, with a message directing the user to `pip install shruggie-indexer[gui]`. |
| Transitive dependencies | `customtkinter` depends on `darkdetect` and `packaging`. These are installed automatically as transitive dependencies and are not interacted with directly by any `shruggie-indexer` module. |

**`orjson`** (extra: `perf`)

| Field | Value |
|-------|-------|
| Version constraint | `>=3.9` |
| Purpose | High-performance JSON serialization as a drop-in replacement for `json.dumps()` in the serializer (§6.9) |
| Imported by | `core/serializer.py` |
| Import guard | `try: import orjson` / `except ImportError: orjson = None`. The serializer checks `if orjson is not None:` before each serialization call and falls back to `json.dumps()` seamlessly. No user-facing error — the fallback is silent and functionally equivalent. |
| Why optional | `orjson` is a compiled C extension. Making it required would break installation on platforms without pre-built wheels and would violate G5's "standard library only for core" principle. The performance benefit is meaningful only for very large directory trees (thousands of entries) where serialization becomes a measurable fraction of total runtime. |

**`pyexiftool`** (extra: `perf`)

| Field | Value |
|-------|-------|
| Version constraint | `>=0.5` |
| Purpose | Persistent exiftool process for batch metadata extraction, avoiding per-file subprocess spawn overhead (§6.6) |
| Imported by | `core/exif.py` |
| Import guard | `try: import exiftool` / `except ImportError: exiftool = None`. The exif module selects the invocation strategy based on availability: `pyexiftool` batch mode if installed, `subprocess.run()` per-file mode otherwise. The selection is logged at `DEBUG` level. |
| Why optional | The `subprocess.run()` invocation strategy is correct and sufficient for the MVP. `pyexiftool` is a performance optimization for large-scale indexing runs. Making it required would add a dependency that most users — indexing single files or small directories — would never benefit from. The batch mode implementation is deferred to a performance optimization pass (§6.6). |

**`tqdm`** (extra: `dev`)

| Field | Value |
|-------|-------|
| Version constraint | `>=4.65` |
| Purpose | Optional progress bar display for the CLI (§11.6) |
| Imported by | `cli/main.py` |
| Import guard | `try: import tqdm` / `except ImportError: tqdm = None`. The CLI constructs a `tqdm` progress bar if the library is available and `-v` is active; otherwise, it falls back to the log-line-based progress reporting described in §11.6. |
| Why in `dev` and not `cli` | The `tqdm` progress bar is a convenience enhancement for developers and power users running the tool interactively. The log-based milestone reporting (§11.6) is the baseline behavior and is sufficient for all use cases including piped output and CI environments. Bundling `tqdm` into the `cli` extra would add a dependency that the PyInstaller-built standalone executable would need to include, increasing bundle size for a non-essential feature. Users who want it can install it separately. |

**`rich`** (extra: `dev`)

| Field | Value |
|-------|-------|
| Version constraint | `>=13.0` |
| Purpose | Colorized log output via `rich.logging.RichHandler` as an optional enhancement to the CLI's stderr log stream (§11.1) |
| Imported by | `cli/main.py` |
| Import guard | `try: from rich.logging import RichHandler` / `except ImportError: RichHandler = None`. The CLI uses `RichHandler` as the stderr handler if available, falling back to the standard `logging.StreamHandler` otherwise. |
| Why in `dev` and not `cli` | Same rationale as `tqdm`: visual enhancement, not functional requirement. The standard `StreamHandler` with the format string defined in §11.1 produces perfectly adequate log output. `rich` adds syntax highlighting, automatic log-level coloring, and improved traceback formatting, which are valuable during development but not required for production use. |

**`jsonschema`** (extra: `dev`)

| Field | Value |
|-------|-------|
| Version constraint | `>=4.17` |
| Purpose | Draft-07 JSON Schema validation for output conformance tests (§5.12, §14.4) |
| Imported by | Test modules only (`tests/`) |
| Import guard | None — `jsonschema` is a test dependency, not a runtime dependency. It is imported unconditionally in test modules. The test suite SHOULD fail with a clear `ImportError` if `jsonschema` is not installed, directing the developer to `pip install shruggie-indexer[dev]`. |

**`pydantic`** (extra: `dev`)

| Field | Value |
|-------|-------|
| Version constraint | `>=2.0` |
| Purpose | Optional runtime type validation models for consumers who ingest index output from untrusted sources (§5.12). Also used in test modules for strict schema validation. |
| Imported by | `models/schema.py` (behind `TYPE_CHECKING` and a runtime import guard) |
| Import guard | The Pydantic models in `models/schema.py` are defined behind a conditional block: `if TYPE_CHECKING or _PYDANTIC_AVAILABLE:`. The `_PYDANTIC_AVAILABLE` flag is set via `try: import pydantic` at the top of the module. Core engine modules never import the Pydantic models — they use the stdlib `dataclass` definitions exclusively. |

**`pytest`, `pytest-cov`, `ruff`** (extra: `dev`)

These are development-only tools that are not imported by any runtime module. They are included in the `dev` extra for contributor convenience:

| Package | Version constraint | Purpose |
|---------|--------------------|---------|
| `pytest` | `>=7.0` | Test runner (§14) |
| `pytest-cov` | `>=4.0` | Coverage reporting for test runs |
| `ruff` | `>=0.3` | Linter and formatter, configured in `pyproject.toml` (§13.2) |

### 12.4. Eliminated Original Dependencies

The original `MakeIndex` and its dependency tree consume two external binaries, eight top-level pslib functions, six global variables, and approximately 60 nested sub-functions. The port eliminates the majority of these dependencies through Python's standard library, architectural consolidation, or deliberate scope reduction. This subsection provides the complete elimination manifest — every original dependency, its purpose, and what replaces it (or why it is dropped).

#### Eliminated external binaries

| Original binary | Original purpose | Replacement | Deviation |
|-----------------|-----------------|-------------|-----------|
| `jq` | JSON parsing and key filtering of exiftool output (invoked in `GetFileExifRun` and `MetaFileRead-Data-ReadJson`) | `json.loads()` for parsing; dict comprehension for key filtering. Zero-dependency, cross-platform, no subprocess overhead. | DEV-06 |
| `certutil` | Base64 encoding of binary sidecar file contents (invoked in `MetaFileRead-Data-Base64Encode`). Windows-only system utility. | `base64.b64encode()` from the standard library. Cross-platform, no subprocess overhead, no temporary file needed. | DEV-05 (part of the broader Base64 pipeline elimination) |

#### Eliminated pslib functions

| Original function | Original purpose | Replacement | Deviation |
|-------------------|-----------------|-------------|-----------|
| `Base64DecodeString` | Decodes Base64-encoded exiftool argument strings at runtime. Uses an OpsCode dispatch pattern across four encoding/URL-decode combinations. | Eliminated entirely. Exiftool arguments are defined as plain Python string lists — no encoding, no decoding, no dispatch. | DEV-05 |
| `Date2UnixTime` | Converts formatted date strings to Unix timestamps via a three-stage pipeline: format-code resolution (calling `Date2FormatCode` externally, then falling back to an internal digit-counting heuristic via `Date2UnixTimeSquash` → `Date2UnixTimeCountDigits` → `Date2UnixTimeFormatCode`), then `[DateTimeOffset]::ParseExact().ToUnixTimeMilliseconds()`. | `int(os.stat_result.st_mtime * 1000)` for Unix milliseconds. `datetime.fromtimestamp().isoformat()` for ISO 8601 strings. Both derived directly from `os.stat()` float values — no string formatting, no reparsing, no format-code guessing. | DEV-07 |
| `Date2FormatCode` | Analyzes date string structure and returns a .NET format code. Called by `Date2UnixTime` as its primary format-detection strategy. | Eliminated along with `Date2UnixTime`. The port never converts date strings — it works with numeric timestamps from the filesystem directly. | DEV-07 |
| `DirectoryId` (as a standalone function) | Generates directory identifiers by hashing directory name + parent name with four algorithms. Defines 7 internal sub-functions: `DirectoryId-GetName`, `DirectoryId-HashString`, `DirectoryId-HashString-Md5`, `-Sha1`, `-Sha256`, `-Sha512`, `DirectoryId-ParentName`, `DirectoryId-ResolvePath`. | `core/hashing.hash_string()` for all string hashing. `core/paths.extract_components()` for name/parent extraction. `core/hashing.compute_directory_id()` for the two-layer hash+concatenate+hash identity algorithm. The identity algorithm is preserved; the seven sub-functions are replaced by two shared utility functions. | DEV-01 |
| `FileId` (as a standalone function) | Generates file identifiers by hashing file content (or name for symlinks) with up to four algorithms. Defines 10 internal sub-functions: `FileId-GetName`, `FileId-HashMd5`, `-HashMd5-String`, `-HashSha1`, `-HashSha1-String`, `-HashSha256`, `-HashSha256-String`, `-HashSha512`, `-HashSha512-String`, `FileId-ResolvePath`. | `core/hashing.hash_file()` for content hashing with single-pass multi-algorithm computation. `core/hashing.hash_string()` for name hashing. `core/paths.resolve_path()` for path resolution. The ten sub-functions are replaced by two shared utility functions. | DEV-01, DEV-02 |
| `MetaFileRead` (as a standalone function) | Reads and parses sidecar metadata files. Defines 16 internal sub-functions for type detection, parent resolution, data reading (JSON, text, binary, link), and hashing. Depends on `certutil`, `jq`, `Lnk2Path`, `UrlFile2Url`, and `ValidateIsJson`. | `core/sidecar.py` reimplements the behavioral contract using stdlib: `json.loads()` replaces `jq`, `base64.b64encode()` replaces `certutil`, `hashlib` replaces the internal hash functions. `Lnk2Path` and `UrlFile2Url` are not ported — `.lnk` and `.url` are Windows-specific shortcut formats that are treated as opaque binary data in the cross-platform port (Base64-encoded when encountered as sidecar content). | DEV-05, DEV-06 |
| `TempOpen` | Creates a temporary file with a UUID-based name in a hardcoded pslib temp directory (`C:\bin\pslib\temp`). | Eliminated. The only consumer was the exiftool argument-file pipeline, which is itself eliminated (DEV-05). If temporary files are needed in the future, `tempfile.NamedTemporaryFile` is the stdlib replacement. | DEV-05 |
| `TempClose` | Deletes a temporary file created by `TempOpen`. Includes a `ForceAll` mode for batch cleanup of the pslib temp directory. | Eliminated along with `TempOpen`. Python's `tempfile` context managers handle cleanup automatically via `__exit__`. | DEV-05 |
| `Vbs` | Centralized structured logging function: severity normalization, colorized `Write-Host` output, manual call-stack compression, session ID embedding, monthly log file rotation, log directory bootstrapping. Called by every function in the dependency tree. | Python's `logging` standard library module. Named loggers, hierarchical filtering, pluggable formatters and handlers, and automatic caller identification replace 100% of the `Vbs` implementation. See §11. | DEV-08 |

#### Eliminated pslib helper functions (not called directly by MakeIndex, DEV-13)

| Original function | Original purpose | Status in port |
|-------------------|-----------------|----------------|
| `ValidateIsLink` | Listed as a dependency in the `MakeIndex` docstring but never actually invoked. `FileId` and `DirectoryId` perform symlink detection inline via `ReparsePoint` attribute check. | Not ported. Dead code in the original. Symlink detection in the port uses `Path.is_symlink()`. | 
| `ValidateIsFile` | Validates that a path references an existing file. Called by `MetaFileRead`. | Not ported as a standalone function. Replaced by `Path.is_file()` calls inline where needed. |
| `ValidateIsJson` | Validates whether a file contains valid JSON. Called by `MetaFileRead-Data`. | Not ported as a standalone function. Replaced by a try/except around `json.loads()` — the Pythonic pattern for JSON validation. |
| `Lnk2Path` | Resolves Windows `.lnk` shortcut files to their target paths. Called by `MetaFileRead-Data-ReadLink`. | Not ported. `.lnk` parsing requires either a Windows COM interface or a third-party library (`pylnk3`). In the cross-platform port, `.lnk` files encountered as sidecar content are treated as opaque binary data and Base64-encoded. A post-MVP enhancement could add `.lnk` resolution on Windows via an optional dependency. |
| `UrlFile2Url` | Extracts the URL from Windows `.url` internet shortcut files. Called by `MetaFileRead-Data-ReadLink`. | Not ported as a standalone function. `.url` files are simple INI-format text files; the URL is extracted with a regex or `configparser` inline in the sidecar reader. This is a trivial operation that does not warrant a separate function. |
| `UpdateFunctionStack` | Maintains a colon-delimited call-stack string for `Vbs` logging (e.g., `"MakeIndex:MakeObject:GetFileExif"`). Called by every internal sub-function. | Not ported. Python's `logging` framework provides automatic caller identification via `%(name)s`, `%(funcName)s`, and `%(lineno)s` format tokens. Manual call-stack bookkeeping is unnecessary. | 
| `VariableStringify` | Converts PowerShell variables to string representations, handling `$null` and empty values. Called by `MakeObject`. | Not ported. Python's `str()`, `repr()`, and the `or` pattern (`value or default`) cover all cases handled by this function. |

#### Eliminated global state

| Original global variable | Original purpose | Replacement |
|--------------------------|-----------------|-------------|
| `$global:MetadataFileParser` | Configuration object governing metadata file parsing: exiftool exclusion lists, sidecar suffix patterns, type identification regexes, extension group classifications. | `IndexerConfig` dataclass (§7.1) — loaded from compiled defaults and optional TOML configuration files, passed as an explicit parameter through the call chain. No global state. |
| `$global:ExiftoolRejectList` | Runtime copy of `$MetadataFileParser.Exiftool.Exclude`, promoted to global scope for access by deeply nested sub-functions. | `config.exiftool_exclude_extensions` field on `IndexerConfig`, threaded explicitly to `core/exif.py`. |
| `$global:MetaSuffixInclude`, `$global:MetaSuffixIncludeString` | Runtime copies of sidecar include patterns, promoted to global scope. | `config.sidecar_include_patterns` field on `IndexerConfig`, threaded explicitly to `core/sidecar.py`. |
| `$global:MetaSuffixExclude`, `$global:MetaSuffixExcludeString` | Runtime copies of sidecar exclude patterns, promoted to global scope. | `config.sidecar_exclude_patterns` field on `IndexerConfig`, threaded explicitly to `core/sidecar.py`. |
| `$global:DeleteQueue` | Accumulates sidecar file paths for batch deletion when `MetaMergeDelete` is active. Initialized as empty array, populated during traversal, drained after indexing completes. | A local `list[Path]` managed by `core/entry.py`'s orchestrator function, returned to the caller as part of the result. No global mutation. See §6.8. |
| `$Sep` | Directory separator character. Used in path construction for renamed files. | `pathlib`'s `/` operator and `os.sep`. Manual separator handling is eliminated entirely (§6.2). |
| `$D_PSLIB_TEMP` | Hardcoded temp directory path (`C:\bin\pslib\temp`). | Eliminated. No temporary files are used in the port's core pipeline (DEV-05). |
| `$D_PSLIB_LOGS` | Hardcoded log directory path (`C:\bin\pslib\logs`). | Eliminated. The port does not write log files by default (§11.1, Principle 3). |
| `$LibSessionID` | Session GUID generated at pslib script load time, embedded in every `Vbs` log entry. | `uuid.uuid4().hex[:8]` generated per invocation in the CLI/GUI entry point and injected via the `SessionFilter` (§11.4). Scoped to the invocation, not global. |

#### Summary of elimination impact

The port's dependency elimination is substantial in both breadth and depth:

| Category | Original count | Ported | Eliminated | Elimination rate |
|----------|---------------|--------|------------|-----------------|
| External binaries | 3 (`exiftool`, `jq`, `certutil`) | 1 (`exiftool`) | 2 | 67% |
| Top-level pslib functions | 8 | 0 (all absorbed into core modules) | 8 | 100% |
| Nested sub-functions across all dependencies | ~60 | 0 (replaced by ~10 shared utility functions) | ~60 | 100% |
| Global variables | 9 | 0 | 9 | 100% |

The net effect is a dependency tree that is narrower (one external binary instead of three), shallower (no nested sub-function hierarchies), explicit (all dependencies declared in `pyproject.toml` or imported at module level), and stateless (no global variable mutation).

### 12.5. Dependency Verification at Runtime

The port verifies dependency availability at runtime rather than failing silently or producing confusing errors deep in the call stack. Verification follows two patterns: proactive probing for the external binary, and import-guarded fallback for optional Python packages.

#### Exiftool binary probing

The `core/exif.py` module probes for `exiftool` availability exactly once per process lifetime using `shutil.which()`. The result is cached via `functools.lru_cache` to avoid repeated filesystem lookups:

```python
# core/exif.py (illustrative — not the exact implementation)

import shutil
import functools
import logging

logger = logging.getLogger(__name__)

@functools.lru_cache(maxsize=1)
def _exiftool_available() -> bool:
    """Check whether exiftool is on PATH. Cached for process lifetime."""
    available = shutil.which("exiftool") is not None
    if not available:
        logger.warning(
            "exiftool not found on PATH. "
            "Embedded metadata extraction will be skipped for all files. "
            "Install exiftool from https://exiftool.org/"
        )
    return available
```

The probe is invoked lazily — on the first call to the exiftool extraction function, not at module import time. This means that importing `shruggie_indexer` as a library does not trigger the probe, and consumers who never call metadata extraction never see the warning. The CLI and GUI entry points do not need to check exiftool availability explicitly — the probe fires automatically when the first eligible file is encountered during indexing.

> **Improvement over original:** The original's `GetFileExifRun` invokes `exiftool` directly for every eligible file without prior availability checking. If exiftool is missing, every invocation produces a separate error, resulting in N errors for N files — where a single diagnostic message would suffice. The port's probe-once approach emits one warning for the entire invocation and avoids spawning N doomed subprocesses.

#### Optional Python package import guards

Optional third-party packages follow the try/except import pattern. The pattern has two variants depending on the failure mode:

**Silent fallback** — for performance-tier packages (`orjson`, `pyexiftool`, `tqdm`, `rich`) where a stdlib equivalent exists:

```python
# core/serializer.py
try:
    import orjson
except ImportError:
    orjson = None  # type: ignore[assignment]

def serialize_entry(entry: IndexEntry, ...) -> str:
    if orjson is not None:
        return orjson.dumps(entry_dict, option=orjson.OPT_INDENT_2).decode()
    return json.dumps(entry_dict, indent=2, ensure_ascii=False)
```

The consumer never knows or cares which serializer was used — the output is identical (modulo insignificant whitespace differences). The selection is logged at `DEBUG` level for diagnostic purposes.

**Hard failure with guidance** — for surface-specific packages (`click`, `customtkinter`) where no fallback exists:

```python
# __main__.py
def main() -> None:
    try:
        from shruggie_indexer.cli.main import main as cli_main
    except ImportError:
        print(
            "The CLI requires the 'click' package.\n"
            "Install it with: pip install shruggie-indexer[cli]",
            file=sys.stderr,
        )
        sys.exit(1)
    cli_main()
```

The error message is specific, actionable, and includes the exact `pip install` command needed. This is a deliberate UX choice: a raw `ImportError` traceback pointing at `import click` conveys the same information but requires the user to diagnose the missing package themselves.

#### Dependency verification summary

| Dependency | Verification method | Timing | Failure mode |
|------------|-------------------|--------|-------------|
| `exiftool` | `shutil.which()`, cached | Lazy (first exif extraction call) | Warning + graceful degradation (null metadata) |
| `click` | `try: import` | CLI entry point invocation | Hard error with install instructions |
| `customtkinter` | `try: import` | GUI entry point invocation | Hard error with install instructions |
| `orjson` | `try: import` | Module load of `core/serializer.py` | Silent fallback to `json.dumps()` |
| `pyexiftool` | `try: import` | Module load of `core/exif.py` | Silent fallback to `subprocess.run()` |
| `tqdm` | `try: import` | CLI progress callback setup | Silent fallback to log-line milestones |
| `rich` | `try: import` | CLI logging configuration | Silent fallback to `logging.StreamHandler` |
| `pydantic` | `try: import` | Module load of `models/schema.py` | Pydantic models unavailable; stdlib dataclasses used |
| `jsonschema` | Direct import (test only) | Test module load | `ImportError` — developer installs `[dev]` extra |

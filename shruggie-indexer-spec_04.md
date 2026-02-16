## 4. Architecture

This section defines the high-level architecture of `shruggie-indexer` — the processing pipeline, module decomposition, data flow, state management, error handling strategy, and entry point routing. It describes the system as the port intends to build it, not as the original implemented it. Where the original's architecture informed a decision, that lineage is noted. Where the port departs from the original, the deviation is called out explicitly with a rationale.

The module-level detail here complements the source package layout in §3.2 but focuses on **behavioral relationships** between modules — who calls whom, what data crosses each boundary, and what invariants each layer is responsible for maintaining. §6 (Core Operations) provides the per-operation behavioral contracts; this section provides the structural skeleton that those operations hang on.

### 4.1. High-Level Processing Pipeline

Every invocation of `shruggie-indexer` — whether from the CLI, the GUI, or the Python API — passes through the same linear pipeline. The pipeline has six stages, executed in strict order. No stage begins until its predecessor completes for the current item, though the pipeline as a whole operates on one item at a time within a traversal loop.

**Stage 1 — Configuration Resolution.** Load compiled defaults, merge any user configuration file (§7), and apply CLI/API overrides. Produce a fully-resolved, immutable `IndexerConfig` object. This happens exactly once per invocation.

**Stage 2 — Target Resolution and Classification.** Resolve the input target path to an absolute canonical form. Classify the target as one of three types: single file, single directory (flat), or directory tree (recursive). This classification determines which traversal strategy is used in Stage 3. If the path does not exist or is not accessible, the pipeline terminates with an error at this stage.

**Stage 3 — Traversal and Discovery.** Enumerate the items to be indexed. For a single file, the "traversal" is trivial — the item set contains only the target. For a directory (flat or recursive), the traversal yields files and subdirectories according to the recursion mode, filtering out excluded paths per the configuration. The traversal produces an ordered sequence of filesystem paths to process.

**Stage 4 — Entry Construction.** For each path yielded by Stage 3, build a complete `IndexEntry` (the v2 schema object defined in §5). This is the core of the indexing engine and involves:

- Path component extraction (name, stem, suffix, parent).
- Symlink detection.
- Hash computation (content hashes for files, name hashes for directories, name hashes for both).
- Identity generation (selecting the `_id` from the chosen algorithm, applying the `y`/`x`/`z` prefix).
- Timestamp extraction (accessed, created, modified — in both Unix-millisecond and ISO 8601 forms).
- EXIF/embedded metadata extraction (via `exiftool`, if applicable and available).
- Sidecar metadata discovery, parsing, and optional merging.
- Parent identity computation.
- Assembly of the final `IndexEntry` model instance.

For directory entries in recursive mode, Stage 4 recurses into child items and attaches their completed `IndexEntry` objects to the parent's `items` field before the parent entry is considered complete.

**Stage 5 — Output Routing.** Route the completed entry (or entry tree) to one or more output destinations based on the configured output mode: stdout, a single aggregate file, and/or per-item in-place sidecar files. Serialization to JSON occurs at this stage. In-place sidecar writes happen during traversal (Stage 3–4 loop) so that partial results survive interruption; stdout and aggregate file writes happen after the full entry tree is assembled.

**Stage 6 — Post-Processing.** Execute deferred operations that must occur after all indexing is complete: MetaMergeDelete file removal (if active), global variable cleanup (a no-op in the port — see §4.4), elapsed-time logging, and final status reporting.

The stages map to original code as follows, for traceability:

| Stage | Port Module(s) | Original Function(s) |
|-------|----------------|---------------------|
| 1 — Configuration | `config/loader.py` | `$global:MetadataFileParser` initialization, `MakeIndex` param block promoting globals |
| 2 — Target Resolution | `core/paths.py`, `cli/main.py` | `ResolvePath`, `MakeIndex` input validation and `TargetTyp` assignment |
| 3 — Traversal | `core/traversal.py` | `MakeDirectoryIndexRecursiveLogic`, `MakeDirectoryIndexLogic`, `MakeFileIndex` |
| 4 — Entry Construction | `core/entry.py` (orchestrator), `core/hashing.py`, `core/timestamps.py`, `core/exif.py`, `core/sidecar.py`, `core/paths.py` | `MakeObject`, `FileId`, `DirectoryId`, `Date2UnixTime`, `GetFileExif`, `GetFileMetaSiblings`, `ReadMetaFile`, `MetaFileRead` |
| 5 — Output Routing | `core/serializer.py`, `core/rename.py` | `MakeIndex` output-scenario routing, `ConvertTo-Json`, `Set-Content`, `Move-Item` |
| 6 — Post-Processing | `core/serializer.py` (finalization), top-level orchestrator | `$global:DeleteQueue` iteration, `Remove-Variable` cleanup |

#### Deviation from original: pipeline linearity

The original interleaves traversal, entry construction, output writing, and rename operations within the bodies of `MakeDirectoryIndexLogic` and `MakeDirectoryIndexRecursiveLogic` — a single function handles discovery, construction, serialization, and file mutation in a tightly coupled loop. This made the original's output scenarios difficult to reason about and contributed to the five-branch `switch` duplication in `MakeObject`.

The port separates traversal (Stage 3) from entry construction (Stage 4) from output routing (Stage 5) at the module boundary level. Entry construction knows nothing about where its output goes. Output routing knows nothing about how entries were built. The one deliberate exception is in-place sidecar writes, which occur within the traversal loop for the practical reason described in Stage 5 above — but even there, the serializer module is called as a service rather than being inlined into the traversal logic.

### 4.2. Module Decomposition

This subsection describes the dependency relationships between modules. §3.2 defines each module's responsibility in isolation; this section defines who calls whom and why.

#### Dependency Graph

The following graph shows the runtime call relationships between the port's Python modules. Arrows point from caller to callee. Modules are grouped by subpackage.

```
cli/main.py ──────────────────────┐
gui/app.py ───────────────────────┤
__init__.py (public API) ─────────┤
                                  ▼
                          config/loader.py
                                  │
                          config/defaults.py
                          config/types.py
                                  │
                                  ▼
                          core/traversal.py ──► core/paths.py
                                  │
                                  ▼
                          core/entry.py (orchestrator)
                           │  │  │  │  │
              ┌────────────┘  │  │  │  └────────────┐
              ▼               ▼  │  ▼               ▼
        core/hashing.py  core/paths.py  core/exif.py  core/sidecar.py
              │               │  │                    │
              │               │  ▼                    │
              │               │  core/timestamps.py   │
              │               │                       │
              └───────────────┼───────────────────────┘
                              ▼
                       models/schema.py
                              ▲
                              │
                       core/serializer.py
                       core/rename.py
```

Key structural rules:

**Rule 1 — Presentation layers are thin.** `cli/main.py`, `gui/app.py`, and the public API (`__init__.py`) contain no indexing logic. They perform argument parsing or UI event handling, construct an `IndexerConfig`, call into `core/`, and format the result for their respective output medium. This is design goal G3 from §2.3.

**Rule 2 — `core/entry.py` is the sole orchestrator.** All coordination between the component modules (hashing, timestamps, exif, sidecar, paths) happens inside `entry.py`. No component module calls another component module directly — `hashing.py` does not call `paths.py`, `exif.py` does not call `hashing.py`. Each component module receives its inputs as function arguments and returns its outputs as return values. `entry.py` wires them together.

> **Deviation note and rationale:** The original's `MakeObject` function calls `FileId`, `DirectoryId`, `Date2UnixTime`, `GetFileExif`, `GetFileMetaSiblings`, and `ReadMetaFile` directly, which in turn each internally call their own copies of path resolution and hashing logic. This created a web of implicit dependencies and the code duplication cataloged in §2.6 (DEV-01 through DEV-04). The port's hub-and-spoke model through `entry.py` eliminates this duplication by making all shared operations (hashing, path resolution) explicit dependencies injected by the orchestrator rather than independently reimplemented by each component.

**Rule 3 — `models/schema.py` is a leaf dependency.** The schema model types (`IndexEntry`, `HashSet`, `TimestampPair`, etc.) are pure data structures with no business logic and no imports from `core/` or `config/`. Every `core/` module that produces or consumes schema objects imports from `models/`, but `models/` never imports from `core/`. This prevents circular imports and keeps the data model independently testable.

**Rule 4 — `config/` is consumed, not called back into.** Configuration flows one direction: from `config/loader.py` into the calling code, and then down through the `core/` module call chain as function parameters. No `core/` module reaches back into `config/loader.py` to re-read configuration at runtime. The `IndexerConfig` object is constructed once and threaded through as an argument.

**Rule 5 — `gui/` is isolated.** The `gui/` subpackage imports from `core/`, `models/`, and `config/`, but nothing outside `gui/` imports from it. The `customtkinter` dependency is only imported inside `gui/`. Removing the `gui/` subpackage entirely has zero effect on the CLI or library surfaces.

#### Module count and original-function mapping

The port's 10 `core/` modules, 1 `models/` module, and 3 `config/` modules replace approximately 60 discrete code units from the original (the `MakeIndex` function body, its 20+ inline sub-functions, the 8 external pslib dependencies, and their own internal sub-functions). The consolidation ratio is roughly 4:1, achieved primarily by eliminating the hashing duplication (DEV-01), path resolution duplication (DEV-04), and the five eliminated dependencies (DEV-05 through DEV-08, DEV-13).

### 4.3. Data Flow

This subsection traces the data that flows through the pipeline for the most common operation — indexing a directory recursively — and identifies the types that cross module boundaries.

#### Primary data types at module boundaries

| Boundary | Data Crossing | Type |
|----------|---------------|------|
| CLI/API → `config/loader` | Raw CLI arguments or API keyword arguments | `dict` / keyword args |
| `config/loader` → caller | Fully-resolved configuration | `IndexerConfig` (frozen dataclass) |
| CLI/API → `core/traversal` | Target path + config + recursion flag | `Path`, `IndexerConfig`, `bool` |
| `core/traversal` → `core/entry` | Individual filesystem path to index | `Path` (yielded one at a time) |
| `core/entry` → `core/paths` | Raw `Path` for component extraction | `Path` → `str` (name, stem, suffix, parent name) |
| `core/entry` → `core/hashing` | File path (for content hashing) or string (for name hashing) | `Path` or `str` → `HashSet` |
| `core/entry` → `core/timestamps` | `os.stat_result` | `os.stat_result` → `TimestampsObject` |
| `core/entry` → `core/exif` | File path + config (exclusion list) | `Path`, `IndexerConfig` → `dict` or `None` |
| `core/entry` → `core/sidecar` | File path + parent directory listing + config (patterns) | `Path`, `list[Path]`, `IndexerConfig` → `list[MetadataEntry]` |
| `core/entry` → caller | Completed index entry | `IndexEntry` |
| Caller → `core/serializer` | Completed entry tree + output mode config | `IndexEntry`, `IndexerConfig` → JSON `str` or file writes |
| Caller → `core/rename` | Completed entry + original path | `IndexEntry`, `Path` → renamed `Path` |

#### Recursive directory data flow (detailed)

The following walkthrough traces data through the system for a recursive directory indexing operation — the most complex scenario — in sufficient detail for an implementer to understand the wiring.

1. The caller (CLI, GUI, or API) invokes `index_path(target, config)` where `target` is a `Path` to a directory and `config` is the resolved `IndexerConfig` with `recursive=True`.

2. `index_path()` calls `core/paths.resolve_path(target)` to canonicalize the target. It then calls `target.stat()` and `target.is_dir()` to classify the target as a directory.

3. `index_path()` calls `core/entry.build_directory_entry(target, config, recursive=True)`.

4. Inside `build_directory_entry()`:

   a. Path components are extracted via `core/paths`: `target.name`, `target.parent.name`.

   b. Symlink status is checked: `target.is_symlink()`.

   c. Directory identity is computed via `core/hashing.hash_directory(name, parent_name)`, which implements the two-layer `hash(hash(name) + hash(parent_name))` scheme and returns a `HashSet`.

   d. An `_id` is selected from the `HashSet` based on `config.id_algorithm` and prefixed with `x`.

   e. Timestamps are extracted via `core/timestamps.extract_timestamps(target.stat())`, returning a `TimestampsObject`.

   f. Parent identity is computed via `core/hashing.hash_directory(parent_name, grandparent_name)`, returning a `ParentObject`.

   g. `core/traversal.list_children(target, config)` yields child paths, separated into files and subdirectories. The files-first, directories-second ordering from the original is preserved.

   h. For each child file: `core/entry.build_file_entry(child_path, config)` is called, producing a child `IndexEntry`. This call internally invokes `hashing.hash_file()` for content hashing, `exif.extract_exif()` for embedded metadata, and `sidecar.discover_and_parse()` for sidecar metadata.

   i. For each child subdirectory: `core/entry.build_directory_entry(child_path, config, recursive=True)` is called recursively, producing a child `IndexEntry` with its own `items` list.

   j. The child `IndexEntry` objects are collected into the parent's `items` list. The directory's `size` is computed as the sum of all child sizes.

   k. If in-place output mode is active, `core/serializer.write_inplace(entry, target)` writes the current entry's sidecar file before returning.

   l. The completed `IndexEntry` for the directory is returned.

5. Back in `index_path()`, the completed root `IndexEntry` (containing the full recursive tree) is passed to `core/serializer` for output routing.

6. If MetaMergeDelete is active, the accumulated delete queue (a `list[Path]` built up during sidecar discovery in step 4h) is iterated and files are removed.

#### Data flow invariant

Every `core/` module function is a **pure data transformation** with respect to the index entry being built — it receives input arguments and returns output values without modifying global state, writing to the filesystem (except `serializer` and `rename`), or communicating with other modules via side channels. The only exceptions are:

- `core/exif.py` invokes an external subprocess (`exiftool`). This is an I/O side effect but does not mutate program state.
- `core/serializer.py` writes JSON to the filesystem or stdout. This is the intended terminal side effect.
- `core/rename.py` renames files on the filesystem. This is the intended terminal side effect.
- `core/sidecar.py` reads sidecar file contents from the filesystem. This is a read-only I/O operation.

This property makes the core indexing logic straightforward to unit-test: mock the filesystem interactions (stat, read, subprocess) and every module becomes a deterministic function from inputs to outputs.

### 4.4. State Management

#### Design principle: no mutable global state

The original `MakeIndex` relies heavily on mutable global state. The `$global:MetadataFileParser` object, `$global:ExiftoolRejectList`, `$global:MetaSuffixInclude`, `$global:MetaSuffixExclude`, `$global:MetaSuffixIncludeString`, `$global:MetaSuffixExcludeString`, `$global:DeleteQueue`, and `$LibSessionID` are all script-level or explicitly `$global:`-promoted variables that are read and written by deeply nested sub-functions across the call tree. At the end of `MakeIndex`, a cleanup block calls `Remove-Variable` on each promoted global to prevent state leakage between invocations within the same PowerShell session.

The port eliminates global state entirely. All shared data flows through one of two mechanisms:

1. **Function parameters.** Configuration, file paths, and intermediate results are passed as explicit arguments down the call chain. Every function's data dependencies are visible in its signature.

2. **Return values.** Results flow upward through return values and are collected by the orchestrator (`entry.py`) or the top-level caller.

There are no module-level mutable variables, no singleton objects with hidden state, and no cleanup blocks needed at the end of an invocation. This is possible because the port's module decomposition (§4.2) eliminates the deeply-nested sub-function scoping issue that motivated the original's global promotion pattern — Python's import system and explicit parameter passing provide what PowerShell's scope hierarchy could not.

#### State objects and their lifetimes

| Object | Created | Lifetime | Mutability | Scope |
|--------|---------|----------|------------|-------|
| `IndexerConfig` | Stage 1 (configuration resolution) | Entire invocation | Immutable (frozen dataclass) | Passed as argument to every `core/` function that needs configuration |
| `IndexEntry` | Stage 4 (entry construction), one per item | Until serialized and output in Stage 5 | Built incrementally during Stage 4, immutable after construction completes | Returned by `build_file_entry()` / `build_directory_entry()`, collected by parent entries or the top-level caller |
| Delete queue | Built during Stage 4 sidecar processing | Until Stage 6 post-processing | Append-only `list[Path]` | Created by the top-level orchestrator function and passed into sidecar processing; iterated during Stage 6 |
| Session ID | Generated at startup | Entire invocation | Immutable (`str`) | Injected into the logging system via a `logging.Filter`; not passed through the indexing call chain |
| Logger instances | Created at import time (module-level) | Process lifetime | Mutable (log level can be reconfigured) | Per-module via `logging.getLogger(__name__)` |

#### The delete queue

The delete queue warrants specific attention because it is the one piece of cross-cutting mutable state that the port preserves from the original. When MetaMergeDelete is active, sidecar files that have been successfully merged into their parent entry's `metadata` array are queued for deletion. The deletion itself is deferred to Stage 6 (post-processing) rather than happening inline during traversal, for safety: if the process is interrupted mid-traversal, no sidecar files have been deleted, and the partially-written index entries still reference the original sidecar paths.

In the port, the delete queue is implemented as a plain `list[Path]` owned by the top-level orchestrator function (not a global variable). It is passed into `core/sidecar.discover_and_parse()` as a parameter, and that function appends paths to it. After the traversal loop completes and all output has been written, the orchestrator iterates the queue and calls `Path.unlink()` on each entry. Errors during deletion are logged as warnings, not raised as exceptions — a failure to delete one sidecar file does not abort the deletion of others.

> **Deviation from original:** The original's `$global:DeleteQueue` is a `$global:`-scoped `ArrayList` that `ReadMetaFile` appends to directly. The port makes the delete queue an explicit parameter rather than a global, consistent with the no-global-state principle. The behavioral contract is identical — accumulate during traversal, drain after completion — but the ownership is explicit rather than ambient.

### 4.5. Error Handling Strategy

#### Design principle: fail per-item, not per-invocation

When indexing a directory tree that may contain thousands of items, a single unreadable file, a permission error, or a corrupt metadata file MUST NOT abort the entire operation. The port's error handling follows a **per-item isolation** strategy: errors encountered while processing a single file or directory are caught, logged, and result in that item being either skipped or partially populated, while the traversal continues with the next item.

The original follows this same principle in practice — most errors within `MakeObject` are caught, logged via `Vbs`, and result in `$null` values for the affected fields. The port formalizes this into an explicit strategy.

#### Error severity tiers

| Tier | Behavior | Examples | Original Equivalent |
|------|----------|----------|-------------------|
| **Fatal** | Abort the entire invocation. Exit with a non-zero code. | Target path does not exist. Target path is not readable. Invalid configuration file syntax. | Implicit — the original does not cleanly distinguish these, but equivalent conditions cause PowerShell terminating errors. |
| **Item-level** | Log a warning. Skip the affected item entirely (exclude it from the output). Continue processing remaining items. | Permission denied reading a file. Filesystem error during `stat()`. Symlink target does not exist (and fallback hashing also fails). | Corresponds to `Vbs -Status e` messages within `MakeObject` followed by returning `$null` for the item. |
| **Field-level** | Log a warning. Populate the affected field with `null` (or its type-appropriate absence value). Include the item in the output with the affected field empty. Continue processing the current item. | `exiftool` not installed (EXIF metadata will be `null`). `exiftool` returns an error for a specific file. A sidecar metadata file exists but contains malformed JSON. Timestamp extraction fails for one timestamp type. | Corresponds to `Vbs -Status w` or `Vbs -Status e` messages within sub-functions, with the field set to `$null`. |
| **Diagnostic** | Log at debug level. No effect on output. | A file matched the exiftool exclusion list and was skipped. A directory matched the filesystem exclusion filter and was skipped. A sidecar pattern regex matched but the file had no parseable content. | Corresponds to `Vbs -Status d` or `Vbs -Status i` messages. |

#### Implementation pattern

Every `core/` module function that performs I/O or processes untrusted input (file content, exiftool output, sidecar file content) follows this pattern:

```python
# Illustrative — not the exact implementation.
def extract_exif(path: Path, config: IndexerConfig) -> dict | None:
    """Extract EXIF metadata. Returns None if extraction fails or is skipped."""
    if path.suffix.lower() in config.exiftool_exclude_extensions:
        logger.debug("Skipping exiftool for excluded extension: %s", path.suffix)
        return None
    try:
        result = subprocess.run(
            ["exiftool", "-json", "-n", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning("exiftool returned non-zero for %s: %s", path, result.stderr)
            return None
        data = json.loads(result.stdout)
        # ... filter unwanted keys ...
        return filtered_data
    except FileNotFoundError:
        logger.warning("exiftool not found on PATH; EXIF extraction disabled")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("exiftool timed out for %s", path)
        return None
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.warning("Failed to parse exiftool output for %s: %s", path, exc)
        return None
```

The orchestrator (`entry.py`) checks the return value and populates the corresponding `IndexEntry` field with `None` (which serializes to `null` in JSON) when a component returns a failure signal. The orchestrator does not catch exceptions from component modules — the components are responsible for catching their own anticipated failure modes and returning clean failure values. Unanticipated exceptions (bugs) propagate upward to the top-level caller, where a final catch-all logs the error and, depending on the invocation mode, either skips the item (directory traversal) or terminates with a non-zero exit code (single-file mode).

#### Exiftool availability

`exiftool` occupies a unique position in the error model: it is the only external binary dependency, and its absence is a **configuration-time condition**, not a per-item error. The port checks for `exiftool` availability once during Stage 1 or at the first attempted invocation, caches the result, and uses it to gate all subsequent exiftool calls. If `exiftool` is not found, a single warning is emitted (not per-file) and all EXIF metadata fields are populated with `null` for the entire invocation. This avoids the performance cost and log noise of repeatedly spawning a doomed subprocess.

> **Improvement over original:** The original invokes `exiftool` via `GetFileExifRun` for every eligible file without first checking whether the binary exists. If `exiftool` is missing, each invocation fails independently, producing a per-file error. The port's probe-once approach is both more efficient and more user-friendly.

### 4.6. Entry Point Routing

Three input scenarios determine how the pipeline executes. The classification is performed once, during Stage 2 (target resolution), and dictates the traversal strategy for Stage 3.

#### Input classification

| Scenario | Condition | Target Type Code | Pipeline Behavior |
|----------|-----------|-----------------|-------------------|
| **Single file** | Target path exists and is a file (or a symlink to a file) | `file` | No traversal. `build_file_entry()` is called once on the target. Output is a single `IndexEntry` (no `items` field). |
| **Directory (flat)** | Target path exists and is a directory; recursive mode is not requested | `directory_flat` | `list_children()` enumerates immediate children. `build_directory_entry()` constructs the parent entry with a single level of child entries in its `items` list. No descent into subdirectories. |
| **Directory (recursive)** | Target path exists and is a directory; recursive mode is requested | `directory_recursive` | `build_directory_entry()` recurses depth-first into all subdirectories. The result is a fully nested tree of `IndexEntry` objects mirroring the filesystem hierarchy. |

The original uses a numeric `$TargetTyp` variable (`0` = recursive directory, `1` = single file, `2` = flat directory) assigned during input validation, and routes to `MakeDirectoryIndexRecursive`, `MakeFileIndex`, or `MakeDirectoryIndex` respectively. Each of these three entry points calls `MakeObject` — but via separate wrapper functions with near-identical logic (the code duplication noted in DEV-03).

The port replaces this three-way dispatch with two functions that compose naturally:

- `build_file_entry(path, config) → IndexEntry` — handles a single file.
- `build_directory_entry(path, config, recursive) → IndexEntry` — handles a directory. When `recursive=True`, it calls itself for child subdirectories and calls `build_file_entry()` for child files. When `recursive=False`, it does the same for immediate children only, without descending.

Both functions delegate to the same component modules (hashing, timestamps, exif, sidecar). There is no duplicated wiring between the file path and the directory path — only the presence or absence of the `items` assembly loop.

#### Routing decision tree

The following pseudocode shows the complete routing logic performed by the top-level `index_path()` function. This is the single entry point consumed by the CLI, GUI, and public API.

```python
# Illustrative — not the exact implementation.
def index_path(target: Path, config: IndexerConfig) -> IndexEntry:
    resolved = resolve_path(target)

    if not resolved.exists():
        raise IndexerError(f"Target does not exist: {resolved}")

    if resolved.is_file() or (resolved.is_symlink() and not resolved.is_dir()):
        return build_file_entry(resolved, config)

    if resolved.is_dir():
        return build_directory_entry(resolved, config, recursive=config.recursive)

    raise IndexerError(f"Target is neither a file nor a directory: {resolved}")
```

The `config.recursive` flag is the sole control that distinguishes the flat-directory and recursive-directory scenarios. Unlike the original — where the `Recursive` switch, the `Directory` switch, and the `File` switch are three separate parameters requiring mutual-exclusion validation — the port infers the target type from the filesystem and accepts `recursive` as the only behavioral modifier. The CLI SHOULD still accept `--file` and `--directory` flags for explicit disambiguation (e.g., when indexing a symlink whose target type is ambiguous), but these flags refine the classification rather than selecting between separate code paths.

> **Deviation from original:** The original's `TargetTyp` routing selects between three essentially-independent code paths (`MakeDirectoryIndexRecursive`, `MakeFileIndex`, `MakeDirectoryIndex`), each of which is a wrapper that calls `MakeObject` differently and contains its own traversal, output-writing, and rename logic. The port's `index_path()` → `build_file_entry()` / `build_directory_entry()` routing selects between two functions that share all component modules and differ only in whether a traversal loop is present. This eliminates the structural duplication without changing the logical behavior.

#### Symlink routing edge case

When the target path is a symlink, the classification follows the symlink's target type (file or directory) for routing purposes, but the `is_link` flag on the resulting `IndexEntry` is set to `True`. Content hashing falls back to name hashing for symlinked files (because the link target may be inaccessible or on a different filesystem), and exiftool is skipped for symlinks. This matches the original's behavior — `FileId` and `DirectoryId` both check for the reparse-point attribute and switch to name-based hashing when it is present.

If the symlink target does not exist (a dangling symlink), the item is treated as an item-level error: a warning is logged, and the item is either skipped or included with degraded fields (null hashes, null timestamps), depending on what information can be recovered from `os.lstat()` (which reads the symlink itself, not its target). The original does not explicitly handle dangling symlinks — the PowerShell `Get-Item` call would fail, and the error would propagate in a platform-dependent way. The port's explicit handling is a minor robustness improvement.

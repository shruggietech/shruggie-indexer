# Python API

shruggie-indexer exposes a public Python API for consumers who `import shruggie_indexer` as a library rather than invoking it from the command line. The CLI and GUI are both consumers of this API — they add no indexing logic of their own.

## Public API Surface

All public names are exported from the top-level `shruggie_indexer` namespace. Internal modules (`core/`, `config/`, `models/`) are implementation details — import from the top-level package, not from subpackages.

```python
from shruggie_indexer import (
    # Version
    __version__,
    # Configuration
    load_config,
    IndexerConfig,
    MetadataTypeAttributes,
    # Core functions
    index_path,
    build_file_entry,
    build_directory_entry,
    serialize_entry,
    # Progress and cancellation
    ProgressEvent,
    IndexerCancellationError,
    # Data models
    IndexEntry,
    MetadataEntry,
    HashSet,
    NameObject,
    SizeObject,
    TimestampPair,
    TimestampsObject,
    ParentObject,
    # Rollback
    RollbackPlan,
    RollbackAction,
    RollbackStats,
    RollbackResult,
    SourceResolver,
    LocalSourceResolver,
    load_meta2,
    discover_meta2_files,
    plan_rollback,
    execute_rollback,
    verify_file_hash,
)
```

Names not listed in `__all__` are internal and may change without notice between versions.

!!! note "API Stability"
    For the v0.1.0 release the public API is **provisional**. Breaking changes may occur in minor version bumps (0.2.0, 0.3.0) without a deprecation cycle. Once the project reaches 1.0.0, the public API becomes subject to semantic versioning.

## Core Functions

### `index_path()`

The top-level entry point. Given a filesystem path and a configuration, produces a complete `IndexEntry`.

```python
def index_path(
    target: Path | str,
    config: IndexerConfig | None = None,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: threading.Event | None = None,
    session_id: str | None = None,
) -> IndexEntry: ...
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `Path \| str` | Path to index. Strings are converted to `Path` objects. Relative paths resolve against the current working directory. |
| `config` | `IndexerConfig \| None` | Resolved configuration. When `None`, compiled defaults are used (equivalent to `load_config()` with no arguments). |
| `progress_callback` | `Callable[[ProgressEvent], None] \| None` | Called after each item is processed during directory traversal. Must be non-blocking. Ignored for single-file targets. |
| `cancel_event` | `threading.Event \| None` | Checked between items during directory traversal. When set, raises `IndexerCancellationError`. Ignored for single-file targets. |
| `session_id` | `str \| None` | UUID4 identifying this indexing session. When `None`, a new UUID4 is auto-generated. All entries produced by a single call share the same session ID. |

**Returns:** A fully populated `IndexEntry` conforming to the v2 schema.

**Raises:**

| Exception | Condition |
|-----------|-----------|
| `IndexerTargetError` | Target path does not exist, is not accessible, or is neither a file nor a directory. |
| `IndexerConfigError` | Configuration is invalid (only when `config=None` triggers internal construction). |
| `IndexerRuntimeError` | Unrecoverable error during processing. |
| `IndexerCancellationError` | The `cancel_event` was set during processing. |

### `build_file_entry()`

Builds an `IndexEntry` for a single file. This is the lower-level function that `index_path()` dispatches to when the target is a file.

```python
def build_file_entry(
    path: Path,
    config: IndexerConfig,
    *,
    siblings: list[Path] | None = None,
    delete_queue: list[Path] | None = None,
    session_id: str | None = None,
) -> IndexEntry: ...
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `Path` | Absolute path to the file. |
| `config` | `IndexerConfig` | Resolved configuration. |
| `siblings` | `list[Path] \| None` | Pre-enumerated sibling files for sidecar discovery. When `None`, the parent directory is enumerated on demand. |
| `delete_queue` | `list[Path] \| None` | When MetaMergeDelete is active, sidecar paths are appended here for deferred deletion by the caller. |
| `session_id` | `str \| None` | UUID4 session identifier. Threaded into the constructed entry's `session_id` field. |

### `build_directory_entry()`

Builds an `IndexEntry` for a directory, optionally recursing into subdirectories.

```python
def build_directory_entry(
    path: Path,
    config: IndexerConfig,
    *,
    recursive: bool = False,
    delete_queue: list[Path] | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: threading.Event | None = None,
    session_id: str | None = None,
) -> IndexEntry: ...
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `Path` | Absolute path to the directory. |
| `config` | `IndexerConfig` | Resolved configuration. |
| `recursive` | `bool` | Descend into subdirectories when `True`. |
| `delete_queue` | `list[Path] \| None` | MetaMergeDelete accumulator. |
| `progress_callback` | `Callable \| None` | Progress callback forwarded through recursive calls. |
| `cancel_event` | `threading.Event \| None` | Cancellation event forwarded through recursive calls. |
| `session_id` | `str \| None` | UUID4 session identifier. Threaded into all child entries during recursive construction. |

### `serialize_entry()`

Converts an `IndexEntry` to a JSON string conforming to the v2 schema.

```python
def serialize_entry(
    entry: IndexEntry,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
) -> str: ...
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entry` | `IndexEntry` | — | The entry to serialize. |
| `indent` | `int \| None` | `2` | Indentation level. `None` produces compact single-line JSON. |
| `sort_keys` | `bool` | `False` | Sort keys alphabetically. Default preserves schema-defined field order. |

Serialization invariants enforced by this function:

- `schema_version` appears first in the output (when `sort_keys=False`)
- Required fields are always present
- `HashSet.sha512` is omitted when not computed (not emitted as `null`)
- All hash hex strings are uppercase

## Configuration API

### `load_config()`

The sole factory function for `IndexerConfig` objects. Implements the full four-layer resolution pipeline.

```python
def load_config(
    *,
    config_file: Path | str | None = None,
    target_directory: Path | str | None = None,
    overrides: dict[str, Any] | None = None,
) -> IndexerConfig: ...
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `config_file` | `Path \| str \| None` | Explicit TOML config file. Replaces platform-standard user config resolution. |
| `target_directory` | `Path \| str \| None` | Directory being indexed. Used to search for project-local `.shruggie-indexer.toml`. |
| `overrides` | `dict[str, Any] \| None` | Highest-priority overrides. Keys are `IndexerConfig` field names; nested settings use dotted paths (e.g., `"exiftool.exclude_extensions"`). |

After merging all layers, `load_config()` applies [parameter implications](configuration.md#parameter-implications), validates the result, compiles regex patterns, and returns an immutable `IndexerConfig`.

```python
# Example: SHA-256 with metadata extraction
config = load_config(overrides={
    "id_algorithm": "sha256",
    "extract_exif": True,
    "recursive": True,
})
```

### `IndexerConfig`

A frozen dataclass carrying all configuration for a single indexing invocation. Constructed via `load_config()` or directly for testing.

```python
@dataclass(frozen=True)
class IndexerConfig:
    """Immutable configuration for a single indexing invocation."""
```

The `frozen=True` guarantee means a single `IndexerConfig` can safely be shared across threads without synchronization. To create a modified copy:

```python
from dataclasses import replace
new_config = replace(config, id_algorithm="sha256")
```

!!! warning "Direct Construction"
    Direct `IndexerConfig()` construction bypasses parameter implications and validation. Callers who construct directly **must** ensure implications are satisfied:

    - `rename=True` → `output_inplace=True`
    - `meta_merge_delete=True` → `meta_merge=True`
    - `meta_merge=True` → `extract_exif=True`

    The `write_directory_meta` field (default `True`) controls whether `_directorymeta2.json` directory sidecar files are emitted during output. Set to `False` to suppress directory-level sidecars while retaining per-file sidecars. Corresponds to the CLI `--no-dir-meta` flag.

## Data Models

All data classes are defined in `models/schema.py` and map directly to the [v2 JSON Schema](../schema/index.md) types.

### `IndexEntry`

The root data class representing a single indexed file or directory.

```python
@dataclass
class IndexEntry:
    schema_version: int       # Always 2
    id: str                   # Prefixed hash: y... (file), x... (directory)
    id_algorithm: str         # "md5" or "sha256"
    type: str                 # "file" or "directory"
    name: NameObject
    extension: str | None
    size: SizeObject
    hashes: HashSet | None    # Content hashes (file) or null (directory/symlink)
    file_system: FileSystemObject
    timestamps: TimestampsObject
    attributes: AttributesObject
    items: list[IndexEntry] | None = None
    metadata: list[MetadataEntry] | None = None
    mime_type: str | None = None
    duplicates: list[IndexEntry] | None = None  # Absorbed dedup entries (rename only)
    session_id: str | None = None    # UUID4 identifying the indexing session
    indexed_at: TimestampPair | None = None  # When this entry was constructed
```

### Reusable types

| Class | Fields | Description |
|-------|--------|-------------|
| `HashSet` | `md5`, `sha256`, `sha512` (optional) | Cryptographic hash digests. All hex strings are uppercase. |
| `NameObject` | `text`, `hashes` | Name with associated hash digests. `text` and `hashes` are co-nullable. |
| `SizeObject` | `text`, `bytes` | Human-readable and machine-readable size. |
| `TimestampPair` | `iso`, `unix` | ISO 8601 string and Unix milliseconds. |
| `TimestampsObject` | `created`, `modified`, `accessed` | Three standard filesystem timestamps, each a `TimestampPair`. |
| `ParentObject` | `id`, `name` | Parent directory identity and name. |
| `FileSystemObject` | `relative`, `parent` | Filesystem location with forward-slash relative path. |
| `AttributesObject` | `is_link`, `storage_name` | Item attributes including symlink status and deterministic rename target. |
| `MetadataEntry` | `id`, `origin`, `name`, `hashes`, `attributes`, `data`, ... | A single metadata record (sidecar or generated). |

### `ProgressEvent`

Lightweight event object emitted during directory indexing via the `progress_callback`.

```python
@dataclass
class ProgressEvent:
    phase: str               # "discovery", "processing", "output", "cleanup"
    items_total: int | None  # None during discovery phase
    items_completed: int     # Items processed so far
    current_path: Path | None
    message: str | None
    level: str               # "info", "warning", "error", "debug"
```

| Phase | Emitted when | `items_total` | `items_completed` |
|-------|-------------|---------------|-------------------|
| `"discovery"` | After directory enumeration | `None` → count once complete | `0` |
| `"processing"` | After each child entry is built | Known count | Incrementing |
| `"output"` | During serialization/output writing | Final count | Final count |
| `"cleanup"` | During MetaMergeDelete removal | Final count | Final count |

!!! tip "Callback threading"
    The callback is invoked on the indexing thread. GUI consumers should enqueue events into a `queue.Queue` for main-thread processing. CLI consumers using `tqdm` or `rich` can update progress bars directly (both are thread-safe for single-bar updates). If the callback raises an exception, the engine logs a warning and continues.

## De-duplication API

The `core.dedup` module provides session-scoped de-duplication primitives. These are public API and designed for standalone import by downstream projects.

```python
from shruggie_indexer.core.dedup import (
    DedupRegistry,
    DedupResult,
    DedupStats,
    DedupAction,
    scan_tree,
    apply_dedup,
    cleanup_duplicate_files,
)
```

### `DedupRegistry`

Session-scoped registry that maps content hashes to lists of `IndexEntry` objects. Call `register()` to add entries; call `get_groups()` to retrieve groups with two or more members.

### `scan_tree(entry, registry=None)`

Recursively walk an `IndexEntry` tree, registering every file-type entry into the given `DedupRegistry` (or a fresh one). Returns the populated `DedupRegistry`.

```python
registry = scan_tree(root_entry)
for hash_key, entries in registry.get_groups().items():
    print(f"{hash_key}: {len(entries)} duplicates")
```

### `apply_dedup(entry, registry)`

Apply de-duplication to the entry tree using the populated registry. For each group, the first entry is the canonical copy; all subsequent entries are moved into the canonical entry's `duplicates` array and removed from the tree. Returns a `DedupResult`.

### `DedupResult`

Result object from `apply_dedup()` containing:

| Attribute | Type | Description |
|-----------|------|-------------|
| `stats` | `DedupStats` | Aggregate statistics (groups found, files absorbed, bytes saved). |
| `actions` | `list[DedupAction]` | Per-file actions taken (canonical designation or duplicate absorption). |

### `cleanup_duplicate_files(actions, *, dry_run=False)`

Delete duplicate files from disk based on the actions list from `apply_dedup()`. In dry-run mode, logs proposed deletions without removing files. Each deletion is logged at `INFO` level; failures are logged at `ERROR` level and do not abort remaining deletions.

## Rollback API

The `core.rollback` module provides the rollback engine for reversing rename and de-duplication operations. All symbols are exported from the top-level `shruggie_indexer` namespace.

```python
from shruggie_indexer import (
    # Data classes
    RollbackPlan,
    RollbackAction,
    RollbackStats,
    RollbackResult,
    # Source resolution
    SourceResolver,
    LocalSourceResolver,
    # Core functions
    load_meta2,
    discover_meta2_files,
    plan_rollback,
    execute_rollback,
    verify_file_hash,
)
```

### `load_meta2(path, *, recursive=False)`

Load and parse a `_meta2.json` file into a flat list of `IndexEntry` objects.

```python
def load_meta2(
    path: Path,
    *,
    recursive: bool = False,
) -> list[IndexEntry]: ...
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `Path` | Path to a per-file sidecar, aggregate output file, or directory of sidecars. |
| `recursive` | `bool` | When `path` is a directory and `recursive=True`, search subdirectories for sidecar files. Default: `False`. |

Handles three input shapes:

1. **Per-file sidecar** — A single `IndexEntry` object → returns `[entry]`.
2. **Aggregate output** — A directory entry with nested `items[]` → walks the tree, returns all file-type entries flattened.
3. **Directory path** — Discovers all `*_meta2.json` files (recursively if `recursive=True`), loads each, returns combined flat list.

Duplicate entries from the `duplicates` array of each canonical entry are extracted and included in the returned list with annotations distinguishing them from canonical entries.

**Raises:**

| Exception | Condition |
|-----------|-----------|
| `IndexerConfigError` | Invalid JSON or `schema_version` is not 2. |
| `IndexerTargetError` | Path does not exist. |

### `discover_meta2_files(directory, *, recursive=False)`

Find all `*_meta2.json` files in a directory.

```python
def discover_meta2_files(
    directory: Path,
    *,
    recursive: bool = False,
) -> list[Path]: ...
```

Returns a sorted list of discovered meta2 file paths. When `recursive=False` (default), only the immediate directory is searched.

### `plan_rollback()`

Compute the full rollback plan without executing it.

```python
def plan_rollback(
    entries: list[IndexEntry],
    target_dir: Path,
    *,
    source_dir: Path | None = None,
    resolver: SourceResolver | None = None,
    verify: bool = True,
    force: bool = False,
    flat: bool = False,
    skip_duplicates: bool = False,
    restore_sidecars: bool = True,
) -> RollbackPlan: ...
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entries` | `list[IndexEntry]` | — | Flat list from `load_meta2()`. |
| `target_dir` | `Path` | — | Root directory for restored files. Created if absent. |
| `source_dir` | `Path \| None` | `None` | Directory to search for content files. |
| `resolver` | `SourceResolver \| None` | `None` | Source file locator. Defaults to `LocalSourceResolver()`. |
| `verify` | `bool` | `True` | Verify content hashes before restoring. |
| `force` | `bool` | `False` | Overwrite existing files in target directory. |
| `flat` | `bool` | `False` | Restore using `name.text` only, no directory structure. |
| `skip_duplicates` | `bool` | `False` | Do not restore files from `duplicates[]` arrays. |
| `restore_sidecars` | `bool` | `True` | Restore absorbed sidecar metadata files. |

Returns a `RollbackPlan` describing all actions to be taken.

### `execute_rollback()`

Execute a previously computed rollback plan.

```python
def execute_rollback(
    plan: RollbackPlan,
    *,
    dry_run: bool = False,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> RollbackResult: ...
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `plan` | `RollbackPlan` | — | The plan from `plan_rollback()`. |
| `dry_run` | `bool` | `False` | Log actions without executing them. |
| `progress_callback` | `Callable \| None` | `None` | Optional callback for progress reporting. |
| `cancel_event` | `threading.Event \| None` | `None` | Optional event for cancellation. |

Processes actions in order: mkdir → restore → duplicate_restore → sidecar_restore. Returns a `RollbackResult` summarizing the outcome.

### `verify_file_hash(path, expected, algorithm="md5")`

Verify a file's content hash against expected values.

```python
def verify_file_hash(
    path: Path,
    expected: HashSet,
    algorithm: str = "md5",
) -> bool: ...
```

Returns `True` if the hash matches, `False` otherwise.

### Data Classes

#### `RollbackAction`

A single file restoration action within a rollback plan.

| Attribute | Type | Description |
|-----------|------|-------------|
| `source_path` | `Path \| None` | Where the content bytes currently live. `None` if unresolvable. |
| `target_path` | `Path` | Where they should be restored to. |
| `entry` | `IndexEntry` | The `IndexEntry` driving this action. |
| `action_type` | `str` | One of: `'restore'`, `'duplicate_restore'`, `'sidecar_restore'`, `'mkdir'`. |
| `skip_reason` | `str \| None` | Non-`None` if this action will be skipped. Contains the reason. |
| `verified` | `bool` | Whether the source file's hash was checked against the sidecar. |

#### `RollbackStats`

Summary statistics for a rollback plan or execution result.

| Attribute | Type | Description |
|-----------|------|-------------|
| `total_entries` | `int` | Total entries processed. |
| `files_to_restore` | `int` | Canonical files to restore. |
| `duplicates_to_restore` | `int` | Duplicate files to restore. |
| `sidecars_to_restore` | `int` | Sidecar metadata files to restore. |
| `directories_to_create` | `int` | Directories to create. |
| `skipped_unresolvable` | `int` | Entries skipped because source file not found. |
| `skipped_conflict` | `int` | Entries skipped due to target conflict. |
| `skipped_already_exists` | `int` | Entries skipped because target already exists with same content. |

#### `RollbackPlan`

Complete plan for a rollback operation, computed before execution.

| Attribute | Type | Description |
|-----------|------|-------------|
| `actions` | `list[RollbackAction]` | All actions to be taken. |
| `stats` | `RollbackStats` | Summary statistics. |
| `warnings` | `list[str]` | Advisory warnings (e.g., mixed-session detection). |

#### `RollbackResult`

Outcome of executing a rollback plan.

| Attribute | Type | Description |
|-----------|------|-------------|
| `restored` | `int` | Canonical files restored. |
| `duplicates_restored` | `int` | Duplicate files restored. |
| `sidecars_restored` | `int` | Sidecar metadata files restored. |
| `directories_created` | `int` | Directories created. |
| `skipped` | `int` | Actions skipped. |
| `failed` | `int` | Actions that failed. |
| `errors` | `list[str]` | Error messages for failed actions. |

### `SourceResolver` Protocol

The `SourceResolver` protocol enables pluggable source file resolution. The default implementation (`LocalSourceResolver`) searches the local filesystem for content files. Downstream tools can provide custom implementations for remote storage retrieval.

```python
class SourceResolver(Protocol):
    def resolve(self, entry: IndexEntry, search_dir: Path | None) -> Path | None:
        """Return the local path to the content file, or None if not found."""
        ...
```

### `LocalSourceResolver`

Default implementation that searches the local filesystem:

1. Look for `storage_name` in `search_dir` (renamed file).
2. Look for `name.text` in `search_dir`, verify hash if found (non-renamed file).
3. Return `None` if neither match succeeds.

```python
resolver = LocalSourceResolver(verify_hash=True)
path = resolver.resolve(entry, search_dir=Path("/vault"))
```

### Vault Integration Example

The `SourceResolver` protocol enables downstream tools like `shruggie-vault` to provide custom file retrieval logic for rollback operations. Here is an example of using the rollback API for single-file vault delivery with `flat=True`:

```python
from pathlib import Path
from shruggie_indexer import (
    load_meta2,
    plan_rollback,
    execute_rollback,
    LocalSourceResolver,
)

# Load a single sidecar
entries = load_meta2(Path("/vault/yABC.jpg_meta2.json"))

# Plan a flat restore (single file, no directory structure)
plan = plan_rollback(
    entries,
    target_dir=Path("/delivery/output"),
    source_dir=Path("/vault"),
    flat=True,
)

# Execute the restore
result = execute_rollback(plan)
print(f"Restored {result.restored} file(s)")
# The file at /delivery/output/original-photo.jpg now has its original
# name, and mtime/atime are set from the sidecar timestamps.
```

## Exception Hierarchy

All exceptions inherit from `IndexerError` for catch-all handling:

```python
class IndexerError(Exception):
    """Base class for all shruggie-indexer exceptions."""

class IndexerConfigError(IndexerError):
    """Configuration is invalid or cannot be loaded."""

class IndexerTargetError(IndexerError):
    """Target path is invalid, inaccessible, or unclassifiable."""

class IndexerRuntimeError(IndexerError):
    """Unrecoverable error during indexing execution."""

class RenameError(IndexerError):
    """File rename failed (collision, permission, etc.)."""

class RollbackError(IndexerRuntimeError):
    """Rollback-specific failure."""

class IndexerCancellationError(IndexerError):
    """The indexing operation was cancelled by the caller."""
```

Exception-to-exit-code mapping:

| Exception | CLI exit code |
|-----------|--------------|
| `IndexerConfigError` | 2 |
| `IndexerTargetError` | 3 |
| `IndexerRuntimeError` | 4 |
| `IndexerCancellationError` | 5 (`INTERRUPTED`) |

## Usage Examples

### Index a single file with defaults

```python
from pathlib import Path
from shruggie_indexer import index_path, serialize_entry

entry = index_path(Path("/path/to/photo.jpg"))
print(entry.id)         # "yA8A8C089A6A8583B24C85F5A4A41F5AC"
print(entry.type)       # "file"
print(entry.size.text)  # "3.45 MB"

json_str = serialize_entry(entry)
print(json_str)
```

### Custom configuration with metadata

```python
from pathlib import Path
from shruggie_indexer import index_path, load_config, serialize_entry

config = load_config(overrides={
    "id_algorithm": "sha256",
    "extract_exif": True,
    "meta_merge": True,
})

entry = index_path(Path("/path/to/media/folder"), config)
for child in entry.items or []:
    if child.metadata:
        for meta in child.metadata:
            print(f"{meta.origin}: {meta.attributes.type}")
```

### Batch indexing with shared configuration

```python
from pathlib import Path
from shruggie_indexer import index_path, load_config, serialize_entry

config = load_config(overrides={"compute_sha512": True})
targets = [Path("/data/set-a"), Path("/data/set-b"), Path("/data/set-c")]

for target in targets:
    entry = index_path(target, config)
    json_str = serialize_entry(entry, indent=None)  # compact JSON
    (target / "index.json").write_text(json_str, encoding="utf-8")
```

### Progress reporting and cancellation

```python
import threading
from pathlib import Path
from shruggie_indexer import (
    index_path, load_config, ProgressEvent, IndexerCancellationError,
)

config = load_config(overrides={"extract_exif": True})
cancel = threading.Event()

def on_progress(event: ProgressEvent) -> None:
    if event.phase == "processing" and event.items_total:
        pct = event.items_completed / event.items_total * 100
        print(f"\r{event.items_completed}/{event.items_total} ({pct:.0f}%)", end="")

try:
    entry = index_path(
        Path("/path/to/large/archive"),
        config,
        progress_callback=on_progress,
        cancel_event=cancel,
    )
    print(f"\nDone: {entry.id}")
except IndexerCancellationError:
    print("\nCancelled.")
```

### Error handling

```python
from pathlib import Path
from shruggie_indexer import index_path, load_config
from shruggie_indexer.exceptions import (
    IndexerConfigError, IndexerTargetError,
)

try:
    config = load_config(overrides={"id_algorithm": "blake2"})
except IndexerConfigError as e:
    print(f"Config error: {e}")
    # "id_algorithm must be 'md5' or 'sha256', got 'blake2'"

try:
    entry = index_path(Path("/nonexistent/path"))
except IndexerTargetError as e:
    print(f"Target error: {e}")
```

### Inspecting the entry tree

```python
from shruggie_indexer import IndexEntry, index_path

def find_large_files(entry: IndexEntry, threshold: int) -> list[IndexEntry]:
    """Walk the entry tree and find files exceeding a byte threshold."""
    results = []
    if entry.type == "file" and entry.size.bytes > threshold:
        results.append(entry)
    for child in entry.items or []:
        results.extend(find_large_files(child, threshold))
    return results

entry = index_path("/path/to/archive")
for f in find_large_files(entry, 100_000_000):  # > 100 MB
    print(f"{f.name.text}: {f.size.text}")
```

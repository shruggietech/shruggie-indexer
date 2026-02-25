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

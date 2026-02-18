## 9. Python API

This section defines the public programmatic interface for consumers who `import shruggie_indexer` as a Python library rather than invoking it from the command line or GUI. The API is the contract between the library and its consumers Ã¢â‚¬â€ it specifies which names are importable, what each function accepts and returns, what exceptions it raises, and what behavioral guarantees it provides. The CLI (Ã‚Â§8) and GUI (Ã‚Â§10) are both consumers of this API; they add no indexing logic of their own.

The API is design goal G3 in action (Ã‚Â§2.3): a single core engine exposed through three delivery surfaces. The Python API is the most direct of the three Ã¢â‚¬â€ it provides access to the core functions without the overhead of argument parsing (CLI) or event-loop management (GUI). Consumers include: automation scripts that process index output programmatically, applications that embed indexing functionality, test harnesses that need fine-grained control over individual indexing steps, and the CLI/GUI modules themselves.

**Module location:** The public API surface is defined in `__init__.py` at the top level of the `shruggie_indexer` package (Ã‚Â§3.2). Internal modules (`core/`, `config/`, `models/`) are implementation details Ã¢â‚¬â€ consumers import from the top-level namespace, not from subpackages.

> **Deviation from original:** The original `MakeIndex` is a single PowerShell function with 14 parameters that conflates configuration, execution, and output routing in one call. There is no "library API" Ã¢â‚¬â€ calling `MakeIndex` from another PowerShell script is possible but not designed for, and the function relies on global state (`$global:MetadataFileParser`, `$global:DeleteQueue`) that makes isolated invocation fragile. The port's API separates configuration construction from indexing execution from output routing, each with its own function and return type, enabling clean programmatic composition.

### 9.1. Public API Surface

The `__init__.py` module exports the following names. These constitute the complete public API Ã¢â‚¬â€ all other modules and names are internal.

```python
# src/shruggie_indexer/__init__.py

from shruggie_indexer._version import __version__
from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import IndexerConfig, MetadataTypeAttributes
from shruggie_indexer.core.entry import (
    index_path,
    build_file_entry,
    build_directory_entry,
    IndexerCancellationError,
)
from shruggie_indexer.core.progress import ProgressEvent
from shruggie_indexer.core.serializer import serialize_entry
from shruggie_indexer.models.schema import (
    IndexEntry,
    MetadataEntry,
    HashSet,
    NameObject,
    SizeObject,
    TimestampPair,
    TimestampsObject,
    ParentObject,
)

__all__ = [
    # Version
    "__version__",
    # Configuration
    "load_config",
    "IndexerConfig",
    "MetadataTypeAttributes",
    # Core functions
    "index_path",
    "build_file_entry",
    "build_directory_entry",
    "serialize_entry",
    # Progress and cancellation
    "ProgressEvent",
    "IndexerCancellationError",
    # Data models
    "IndexEntry",
    "MetadataEntry",
    "HashSet",
    "NameObject",
    "SizeObject",
    "TimestampPair",
    "TimestampsObject",
    "ParentObject",
]
```

The `__all__` list is exhaustive Ã¢â‚¬â€ it defines the complete set of names available via `from shruggie_indexer import *`. Names not in `__all__` are not part of the public API and may change without notice between versions. Consumers who import from subpackages (`from shruggie_indexer.core.hashing import hash_file`) do so at their own risk Ã¢â‚¬â€ those paths are internal and may be restructured.

#### API stability scope

For the v0.1.0 MVP release, the public API is provisional. Breaking changes may occur in minor version bumps (0.2.0, 0.3.0) without a deprecation cycle. Once the project reaches 1.0.0, the public API surface defined here becomes subject to semantic versioning: breaking changes require a major version bump. The JSON output schema (Ã‚Â§5) and the public API are the two stability boundaries that downstream consumers can depend on.

#### Dependency isolation

The public API does not require any optional dependencies. All exported names are importable with only the Python standard library installed. Optional dependencies (`click` for CLI, `customtkinter` for GUI, `orjson` for fast serialization, `pydantic` for runtime validation) are isolated behind import guards in their respective modules Ã¢â‚¬â€ they are never imported at the top-level `__init__.py` scope.

This is an explicit design constraint: a consumer who `pip install shruggie-indexer` (with no extras) can immediately `from shruggie_indexer import index_path, load_config` and use the library without encountering `ImportError`. The CLI and GUI extras add presentation layers, not core functionality.

### 9.2. Core Functions

These are the primary functions for performing indexing operations. They compose in a layered hierarchy: `index_path()` calls `build_file_entry()` or `build_directory_entry()`, which in turn call into the `core/` component modules. Consumers can invoke at any layer depending on their needs.

#### `index_path()`

The top-level entry point. Given a filesystem path and a configuration, produces a complete `IndexEntry`. This is the function the CLI and GUI call Ã¢â‚¬â€ it handles target resolution, classification, and dispatch.

```python
def index_path(
    target: Path | str,
    config: IndexerConfig | None = None,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> IndexEntry:
    """Index a file or directory and return the complete entry.

    Args:
        target: Path to the file or directory to index. Strings are
                converted to Path objects. Relative paths are resolved
                against the current working directory.
        config: Resolved configuration. When None, compiled defaults
                are used (equivalent to load_config() with no arguments).
        progress_callback: Optional callable invoked after each item
                is processed during directory traversal. Receives a
                ProgressEvent with phase, item counts, current path,
                and log-level messages. Ignored for single-file
                targets (the operation is effectively atomic).
                Callers MUST NOT perform long-running work inside the
                callback â€” it executes on the indexing thread and
                blocks further processing until it returns. GUI and
                CLI consumers should enqueue events for asynchronous
                display rather than updating UI directly.
        cancel_event: Optional threading.Event checked between items
                during directory traversal. When the event is set,
                the engine stops processing at the next item boundary
                and raises IndexerCancellationError. The partially
                built entry tree is not returned â€” cancellation is
                a clean abort, not a partial result. Ignored for
                single-file targets.

    Returns:
        A fully populated IndexEntry conforming to the v2 schema.

    Raises:
        IndexerTargetError: The target path does not exist, is not
            accessible, or is neither a file nor a directory.
        IndexerConfigError: The configuration is invalid (e.g.,
            meta_merge_delete=True with no output destination).
            Only raised when config is constructed internally
            from defaults.
        IndexerRuntimeError: An unrecoverable error occurred during
            processing (e.g., filesystem became unavailable mid-
            operation).
        IndexerCancellationError: The cancel_event was set during
            processing. No partial output is returned.
    """
```

**Behavioral contract:**

1. If `target` is a string, it is converted to a `Path` via `Path(target)`.
2. The path is resolved to an absolute canonical form via `core.paths.resolve_path()` (Ã‚Â§6.2).
3. If `config` is `None`, the function calls `load_config()` with no arguments to obtain compiled defaults. This is a convenience for simple scripting Ã¢â‚¬â€ production callers should construct and reuse a config explicitly.
4. The target is classified as file or directory per Ã‚Â§4.6 and dispatched to `build_file_entry()` or `build_directory_entry()`.
5. For directory targets, `progress_callback` and `cancel_event` are forwarded to `build_directory_entry()`, which checks the cancellation flag and invokes the callback at each item boundary during the child-processing loop. For single-file targets, neither parameter has any effect.
6. The returned `IndexEntry` is complete and ready for serialization via `serialize_entry()`, inspection via attribute access, or further programmatic processing.

**Default config convenience:** The `config=None` default is a deliberate API usability decision. The most common programmatic use case Ã¢â‚¬â€ "index this path with default settings" Ã¢â‚¬â€ should require exactly one function call, not two. The config object is still constructed properly through the full `load_config()` pipeline, including user config file resolution. Callers who need non-default settings must construct a config explicitly.

> **Deviation from original:** The original `MakeIndex` accepts a `-Directory` or `-File` parameter, one of four output mode switches, a `-Meta`/`-MetaMerge`/`-MetaMergeDelete` switch, and performs output routing internally. The port's `index_path()` does none of that Ã¢â‚¬â€ it accepts a path and a config, produces a data structure, and returns it. Output routing is the caller's responsibility. This separation is what makes the function composable: the same `IndexEntry` can be serialized to stdout, written to a file, stored in a database, or piped into another processing step, without `index_path()` knowing or caring about the destination.

#### `build_file_entry()`

Builds an `IndexEntry` for a single file. This is the lower-level function that `index_path()` dispatches to when the target is a file. Consumers who already know they are indexing a file (and want to skip the target classification step) can call this directly.

```python
def build_file_entry(
    path: Path,
    config: IndexerConfig,
    *,
    siblings: list[Path] | None = None,
    delete_queue: list[Path] | None = None,
) -> IndexEntry:
    """Build a complete IndexEntry for a single file.

    Args:
        path: Absolute path to the file. Must exist and be a file
              (or a symlink to a file).
        config: Resolved configuration.
        siblings: Pre-enumerated list of all files in the same
                  directory. Used for sidecar metadata discovery.
                  When None, the directory is enumerated on demand
                  (acceptable for single-file use, inefficient for
                  batch use within a directory traversal).
        delete_queue: When MetaMergeDelete is active, sidecar paths
                      discovered during metadata processing are
                      appended to this list for deferred deletion
                      by the caller. When None, no paths are
                      collected (MetaMergeDelete is inactive or
                      the caller manages deletion separately).

    Returns:
        A fully populated IndexEntry with type="file" and items=null.

    Raises:
        IndexerTargetError: The path does not exist or is not a file.
        OSError: Filesystem-level errors (permission denied, I/O error)
            propagate for the file itself. Component-level errors
            (exiftool failure, sidecar parse error) are handled
            internally and result in degraded fields (null values),
            not exceptions.
    """
```

**The `siblings` parameter** is an optimization for directory traversal. When `build_directory_entry()` calls `build_file_entry()` for each child file, it passes the pre-enumerated sibling list from `traversal.list_children()`. This avoids re-scanning the directory for sidecar discovery on every file (Ã‚Â§6.7). When `build_file_entry()` is called standalone (via `index_path()` for a single-file target), `siblings` is `None` and the function enumerates the parent directory once internally.

**The `delete_queue` parameter** implements the MetaMergeDelete accumulation pattern described in Ã‚Â§6.7. The function does not delete files itself Ã¢â‚¬â€ it only appends paths to the caller-provided list. Actual deletion is a post-processing step (Stage 6, Ã‚Â§4.1) handled by the top-level orchestrator. This separation ensures that file deletion never occurs mid-traversal if the operation is interrupted.

#### `build_directory_entry()`

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
) -> IndexEntry:
    """Build a complete IndexEntry for a directory.

    Args:
        path: Absolute path to the directory. Must exist and be a
              directory.
        config: Resolved configuration.
        recursive: When True, descends into subdirectories and
                   populates items with a fully nested tree. When
                   False, populates items with immediate children
                   only (flat mode).
        delete_queue: MetaMergeDelete accumulator (see
                      build_file_entry).
        progress_callback: Optional callable invoked after each
                child item is processed (file built or directory
                recursion completed) and once after child discovery.
                The callback receives a ProgressEvent whose
                items_total field is populated once discovery
                completes and whose items_completed field
                increments with each processed child. When this
                function calls itself recursively for child
                directories, it forwards the same callback so
                that progress reporting spans the entire tree.
        cancel_event: Optional threading.Event checked at the top
                of each iteration of the child-processing loop.
                When set, the function raises
                IndexerCancellationError immediately, before
                processing the next child. Items already processed
                are discarded (the partially built entry is not
                returned). When this function calls itself
                recursively, it forwards the same Event so that
                cancellation is effective at any depth.

    Returns:
        A fully populated IndexEntry with type="directory" and
        items populated with child entries.

    Raises:
        IndexerTargetError: The path does not exist or is not a
            directory.
        IndexerCancellationError: The cancel_event was set during
            the child-processing loop.
        OSError: Fatal directory-level errors (cannot enumerate
            children) propagate. Item-level errors within child
            entries are handled per the error tier model (Ã‚Â§4.5) Ã¢â‚¬â€
            the child is either skipped or included with degraded
            fields, and the parent entry is still returned.
    """
```

**Recursion control:** The `recursive` parameter directly maps to `config.recursive` when called from `index_path()`, but is a separate explicit parameter rather than being read from the config object. This is intentional Ã¢â‚¬â€ it allows `build_directory_entry()` to call itself with `recursive=True` for child directories regardless of the top-level config value, without mutating the config. The config controls whether recursion starts; the parameter controls whether it continues.

> **Architectural note:** The `recursive` parameter on `build_directory_entry()` may appear redundant with `config.recursive`, but the separation is necessary. When `index_path()` processes a recursive directory target, it calls `build_directory_entry(path, config, recursive=True)`. The directory entry builder then calls itself for child directories with `recursive=True` Ã¢â‚¬â€ the recursion depth is not a config concern, it is a call-graph concern. If a future enhancement adds depth-limited recursion (`max_depth=3`), the control mechanism is this parameter, not a config mutation.

#### `serialize_entry()`

Converts an `IndexEntry` to a JSON string. This is the serialization boundary Ã¢â‚¬â€ everything before this function operates on Python data structures; everything after operates on text.

```python
def serialize_entry(
    entry: IndexEntry,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
) -> str:
    """Serialize an IndexEntry to a JSON string.

    Args:
        entry: The IndexEntry to serialize.
        indent: JSON indentation level. 2 (default) produces
                human-readable output matching the original's
                ConvertTo-Json formatting. None produces compact
                single-line JSON.
        sort_keys: Whether to sort JSON object keys alphabetically.
                   Default False preserves the schema-defined field
                   order (schema_version first, then identity fields,
                   then content fields, etc.).

    Returns:
        A UTF-8 JSON string conforming to the v2 schema.
    """
```

**Serialization invariants** are enforced here, not by the caller (Ã‚Â§5.12):

1. `schema_version` appears first in the output (when `sort_keys=False`).
2. Required fields are always present.
3. `HashSet.sha512` is omitted (not emitted as `null`) when it was not computed.
4. Sidecar-only `MetadataEntry` fields (`file_system`, `size`, `timestamps`) are present for sidecar entries and absent for generated entries.
5. All hash hex strings are uppercase.

The function uses `json.dumps()` from the standard library by default. When `orjson` is installed, the serializer MAY use it for improved performance on large trees Ã¢â‚¬â€ this is an internal optimization that does not change the output format. The selection is transparent to the caller.

### 9.3. Configuration API

Configuration construction is separated from indexing execution. Callers build an `IndexerConfig` object first, then pass it to the core functions. This separation enables config reuse across multiple indexing operations (e.g., indexing several directories with the same settings) and makes the configuration inspectable and testable independently of the indexing engine.

#### `load_config()`

The sole factory for `IndexerConfig` objects. Implements the full four-layer resolution pipeline described in Ã‚Â§7.1.

```python
def load_config(
    *,
    config_file: Path | str | None = None,
    target_directory: Path | str | None = None,
    overrides: dict[str, Any] | None = None,
) -> IndexerConfig:
    """Construct a fully resolved, immutable IndexerConfig.

    Resolution layers (lowest to highest priority):
    1. Compiled defaults (Ã‚Â§7.2).
    2. User config file at the platform-standard location (Ã‚Â§3.3),
       unless config_file is specified.
    3. Project-local config file in target_directory or its ancestors,
       if target_directory is provided.
    4. Explicit overrides from the overrides dict.

    After merging, the function applies parameter implications
    (Ã‚Â§7.1), validates the result, compiles regex patterns, and
    returns an immutable IndexerConfig.

    Args:
        config_file: Explicit path to a TOML configuration file.
                     When provided, this replaces the user config
                     file resolution (layer 2) Ã¢â‚¬â€ the platform-
                     standard location is not searched. When None,
                     the standard resolution logic applies.
        target_directory: The directory being indexed. Used to
                         search for a project-local config file.
                         When None, no project-local config is
                         loaded.
        overrides: Dict of field-name-to-value overrides applied
                   as the highest-priority layer. Keys correspond
                   to IndexerConfig field names. Unknown keys
                   produce a warning and are ignored.

    Returns:
        A frozen IndexerConfig instance.

    Raises:
        IndexerConfigError: The config file does not exist, contains
            invalid TOML, contains values of the wrong type, or the
            resolved configuration fails validation (e.g.,
            meta_merge_delete without an output destination).
    """
```

**Override dict convention:** The `overrides` dict uses flat `IndexerConfig` field names as keys. Nested configuration (e.g., exiftool settings) uses dotted key paths: `{"exiftool.exclude_extensions": frozenset({"csv", "xml"})}`. This matches the TOML section structure and avoids requiring callers to construct nested dicts.

The CLI module constructs the `overrides` dict from parsed `click` arguments. API callers construct it directly:

```python
config = load_config(overrides={
    "id_algorithm": "sha256",
    "extract_exif": True,
    "recursive": True,
})
```

**Implications and validation** are applied identically to the CLI path Ã¢â‚¬â€ the configuration loader does not distinguish between a CLI caller and an API caller. If `overrides={"meta_merge_delete": True}` is passed without also setting an output destination, the function raises `IndexerConfigError` with the same message the CLI would produce.

#### `IndexerConfig`

The frozen dataclass that carries all configuration. Fully defined in Ã‚Â§7.1 Ã¢â‚¬â€ this section documents only the API-facing aspects.

```python
@dataclass(frozen=True)
class IndexerConfig:
    """Immutable configuration for a single indexing invocation.

    All fields have defaults Ã¢â‚¬â€ an IndexerConfig constructed with
    no arguments represents the compiled default configuration.

    This class is frozen (immutable). To create a modified copy,
    use dataclasses.replace():

        new_config = replace(config, id_algorithm="sha256")
    """
```

The `frozen=True` guarantee means callers can safely share a single `IndexerConfig` across threads or async tasks without synchronization. The `dataclasses.replace()` pattern provides the modification mechanism Ã¢â‚¬â€ rather than mutating the config, callers create a new instance with the desired field(s) changed. This is the same pattern used for immutable configuration in the broader Python ecosystem (e.g., `attrs`, Pydantic's `model_copy()`).

**Direct construction vs. `load_config()`:** Callers MAY construct `IndexerConfig` directly for testing or for scenarios where the full config resolution pipeline is unnecessary. However, direct construction bypasses parameter implications and validation. A directly-constructed config with `meta_merge_delete=True, meta_merge=False` is structurally valid (the dataclass accepts it) but behaviorally invalid (MetaMergeDelete requires MetaMerge). `load_config()` prevents this; direct construction does not. The API does not enforce implications on direct construction because it would require the dataclass `__post_init__` to have side effects, which conflicts with the frozen guarantee.

Callers who construct `IndexerConfig` directly MUST ensure that parameter implications are satisfied:

- `rename=True` Ã¢â€ â€™ `output_inplace=True`
- `meta_merge_delete=True` Ã¢â€ â€™ `meta_merge=True`
- `meta_merge=True` Ã¢â€ â€™ `extract_exif=True`

### 9.4. Data Classes and Type Definitions

All data classes used in the public API are defined in `models/schema.py` (Ã‚Â§3.2). They are the Python representation of the v2 JSON Schema types defined in Ã‚Â§5. Each class maps directly to a schema `$ref` definition or to the root `IndexEntry` type.

#### Model implementation strategy

The data classes are implemented as `@dataclass` types using the standard library. They are NOT frozen Ã¢â‚¬â€ unlike `IndexerConfig`, the entry models are constructed incrementally during the building process (Ã‚Â§6.8) and may have fields set in multiple steps. The immutability boundary is the API return: once `index_path()`, `build_file_entry()`, or `build_directory_entry()` returns an `IndexEntry`, the caller SHOULD treat it as immutable. Mutation after return is not prohibited but is unsupported and may produce inconsistent serialization output.

For consumers who want runtime type validation (e.g., when ingesting index output from untrusted sources), `models/schema.py` provides optional Pydantic models behind an import guard. The Pydantic models mirror the dataclass definitions and add `model_validate_json()` for schema-validating a JSON string. They are not used by the core engine.

```python
# Standard usage Ã¢â‚¬â€ dataclass models (no extra dependency)
from shruggie_indexer import IndexEntry

# Optional Ã¢â‚¬â€ Pydantic models for runtime validation
try:
    from shruggie_indexer.models.schema import IndexEntryModel  # Pydantic
    entry = IndexEntryModel.model_validate_json(json_string)
except ImportError:
    # Pydantic not installed; fall back to json.loads() + manual access
    import json
    entry_dict = json.loads(json_string)
```

#### `IndexEntry`

The root data class. Represents a single indexed file or directory.

```python
@dataclass
class IndexEntry:
    """A single indexed file or directory (v2 schema)."""

    schema_version: int  # Always 2
    id: str              # Prefixed hash: y... (file), x... (directory)
    id_algorithm: str    # "md5" or "sha256"
    type: str            # "file" or "directory"

    name: NameObject
    extension: str | None
    size: SizeObject
    hashes: HashSet | None  # Content hashes (file) or null (directory/symlink)

    file_system: FileSystemObject
    timestamps: TimestampsObject
    attributes: AttributesObject

    items: list[IndexEntry] | None = None    # Children (directory) or null (file)
    metadata: list[MetadataEntry] | None = None  # Metadata entries or null
    mime_type: str | None = None
```

All fields listed in Ã‚Â§5.3 are present. Required schema fields have no default value; optional schema fields (`items`, `metadata`, `mime_type`) default to `None`. The field order matches the schema-defined serialization order.

#### `HashSet`

```python
@dataclass
class HashSet:
    """Cryptographic hash digests (Ã‚Â§5.2.1)."""

    md5: str      # 32 uppercase hex characters
    sha256: str   # 64 uppercase hex characters
    sha512: str | None = None  # 128 uppercase hex characters, optional
```

#### `NameObject`

```python
@dataclass
class NameObject:
    """Name with associated hash digests (Ã‚Â§5.2.2)."""

    text: str | None       # Filename including extension, or null
    hashes: HashSet | None  # Hashes of UTF-8 bytes of text, or null

    def __post_init__(self) -> None:
        """Enforce co-nullability: text and hashes are both null or both populated."""
        if (self.text is None) != (self.hashes is None):
            raise ValueError("NameObject.text and .hashes must be co-null")
```

The `__post_init__` validation enforces the co-nullability invariant from Ã‚Â§5.2.2. This is one of the few validation checks performed at construction time Ã¢â‚¬â€ it catches a common construction error (providing a name without hashes, or vice versa) immediately rather than at serialization time.

#### `SizeObject`

```python
@dataclass
class SizeObject:
    """File size in human-readable and machine-readable forms (Ã‚Â§5.2.3)."""

    text: str   # e.g., "15.28 MB", "135 B"
    bytes: int  # Exact byte count, >= 0
```

#### `TimestampPair`

```python
@dataclass
class TimestampPair:
    """Single timestamp in ISO 8601 and Unix millisecond forms (Ã‚Â§5.2.4)."""

    iso: str   # ISO 8601 with timezone offset
    unix: int  # Milliseconds since epoch
```

#### `TimestampsObject`

```python
@dataclass
class TimestampsObject:
    """Three standard filesystem timestamps (Ã‚Â§5.2.5)."""

    created: TimestampPair
    modified: TimestampPair
    accessed: TimestampPair
```

#### `ParentObject`

```python
@dataclass
class ParentObject:
    """Parent directory identity and name (Ã‚Â§5.2.6)."""

    id: str          # x-prefixed directory ID
    name: NameObject
```

#### `FileSystemObject`

```python
@dataclass
class FileSystemObject:
    """Filesystem location fields (Ã‚Â§5.6)."""

    relative: str                 # Forward-slash-separated relative path
    parent: ParentObject | None   # Null for root of single-file index
```

#### `AttributesObject`

```python
@dataclass
class AttributesObject:
    """Item attributes (Ã‚Â§5.8)."""

    is_link: bool     # Whether the item is a symbolic link
    storage_name: str  # Deterministic name for rename operations
```

#### `MetadataEntry`

```python
@dataclass
class MetadataEntry:
    """A single metadata record associated with an IndexEntry (Ã‚Â§5.10)."""

    id: str              # z-prefixed (generated) or y-prefixed (sidecar)
    origin: str          # "generated" or "sidecar"
    name: NameObject
    hashes: HashSet
    attributes: MetadataAttributes
    data: Any            # JSON object, string, array, or null

    # Sidecar-only fields (absent for generated entries)
    file_system: FileSystemObject | None = None
    size: SizeObject | None = None
    timestamps: TimestampsObject | None = None
```

#### `MetadataAttributes`

```python
@dataclass
class MetadataAttributes:
    """Classification and format info for a MetadataEntry (Ã‚Â§5.10)."""

    type: str                        # e.g., "exiftool.json_metadata", "description"
    format: str                      # "json", "text", "base64", or "lines"
    transforms: list[str]            # Ordered transformation identifiers
    source_media_type: str | None = None  # MIME type of original source data
```

#### `ProgressEvent`

Defined in `core/progress.py`. A lightweight event object used by `build_directory_entry()` to report progress to callers via the `progress_callback` parameter. This type is part of the public API because GUI and CLI consumers construct callbacks that receive it.

```python
@dataclass
class ProgressEvent:
    """Progress report emitted during directory indexing."""

    phase: str                    # "discovery", "processing", "output", "cleanup"
    items_total: int | None       # Total items discovered; None during discovery phase
    items_completed: int          # Items processed so far (0 during discovery)
    current_path: Path | None     # Item currently being processed, or None
    message: str | None           # Optional human-readable log message
    level: str                    # Log level: "info", "warning", "error", "debug"
```

**Phase values:**

| Phase | When emitted | `items_total` | `items_completed` |
|-------|-------------|---------------|-------------------|
| `"discovery"` | After `list_children()` returns for each directory level. | `None` until the top-level directory's children are fully enumerated, then the count of all immediate children (files + subdirectories). For recursive mode, the total grows as child directories are entered. | `0` |
| `"processing"` | After each child item's entry construction completes (or is skipped due to error). | Known count from discovery. | Incrementing count. |
| `"output"` | During serialization and output writing (Stage 5). | Same as final `items_total`. | Same as final `items_completed`. |
| `"cleanup"` | During post-processing (Stage 6): MetaMergeDelete file removal, final logging. | Same. | Same. |

**Threading safety:** The callback is invoked on the indexing thread (the background thread in the GUI, the main thread in CLI/API use). The callback implementation MUST be non-blocking. GUI consumers should enqueue the event into a `queue.Queue` for main-thread processing rather than touching widgets directly. CLI consumers using `tqdm` or `rich` can update the progress bar directly since both libraries are thread-safe for single-bar updates.

**Callback errors:** If the callback raises an exception, the indexing engine logs a warning and continues processing. A broken progress callback does not abort the indexing operation.

### 9.5. Programmatic Usage Examples

These examples demonstrate the primary usage patterns for the Python API. They are illustrative Ã¢â‚¬â€ not the exact implementation Ã¢â‚¬â€ and assume the library is installed via `pip install -e ".[dev]"`.

#### Basic: index a single file with defaults

```python
from pathlib import Path
from shruggie_indexer import index_path, serialize_entry

entry = index_path(Path("/path/to/photo.jpg"))
print(entry.id)          # "yA8A8C089A6A8583B24C85F5A4A41F5AC"
print(entry.type)        # "file"
print(entry.size.text)   # "3.45 MB"
print(entry.name.text)   # "photo.jpg"

# Serialize to JSON
json_str = serialize_entry(entry)
print(json_str)
```

#### Custom configuration: SHA-256 with metadata extraction

```python
from pathlib import Path
from shruggie_indexer import index_path, load_config, serialize_entry

config = load_config(overrides={
    "id_algorithm": "sha256",
    "extract_exif": True,
    "meta_merge": True,
})

entry = index_path(Path("/path/to/media/folder"), config)

# The entry is a directory with nested children
print(entry.type)             # "directory"
print(len(entry.items))       # Number of children

# Access a child file's metadata
child = entry.items[0]
if child.metadata:
    for meta in child.metadata:
        print(f"{meta.origin}: {meta.attributes.type}")
```

#### Batch indexing: process multiple directories with shared config

```python
from pathlib import Path
from shruggie_indexer import index_path, load_config, serialize_entry

config = load_config(overrides={"compute_sha512": True})
targets = [Path("/data/set-a"), Path("/data/set-b"), Path("/data/set-c")]

for target in targets:
    entry = index_path(target, config)
    json_str = serialize_entry(entry, indent=None)  # compact JSON
    output_path = target / "index.json"
    output_path.write_text(json_str, encoding="utf-8")
```

#### Low-level: index a single file without target classification

```python
from pathlib import Path
from shruggie_indexer import build_file_entry, load_config, serialize_entry

config = load_config()
path = Path("/path/to/document.pdf").resolve()

entry = build_file_entry(path, config)
print(entry.hashes.md5)     # "A8A8C089A6A8583B24C85F5A4A41F5AC"
print(entry.hashes.sha256)  # "E3B0C44298FC1C149AFBF4C8996FB924..."
```

#### Configuration from a TOML file

```python
from pathlib import Path
from shruggie_indexer import index_path, load_config

config = load_config(config_file=Path("my-config.toml"))
entry = index_path(Path("."), config)
```

#### Inspecting and filtering the entry tree

```python
from shruggie_indexer import IndexEntry

def find_large_files(entry: IndexEntry, threshold_bytes: int) -> list[IndexEntry]:
    """Walk the entry tree and find files exceeding the size threshold."""
    results = []
    if entry.type == "file" and entry.size.bytes > threshold_bytes:
        results.append(entry)
    if entry.items:
        for child in entry.items:
            results.extend(find_large_files(child, threshold_bytes))
    return results

# Usage
entry = index_path(Path("/path/to/archive"))
large_files = find_large_files(entry, threshold_bytes=100_000_000)  # > 100 MB
for f in large_files:
    print(f"{f.name.text}: {f.size.text}")
```

#### Progress reporting and cancellation

```python
import threading
from pathlib import Path
from shruggie_indexer import index_path, load_config, ProgressEvent

config = load_config(overrides={"extract_exif": True})
cancel = threading.Event()

def on_progress(event: ProgressEvent) -> None:
    if event.phase == "processing" and event.items_total:
        pct = event.items_completed / event.items_total * 100
        print(f"\r{event.items_completed}/{event.items_total} ({pct:.0f}%)", end="")
    if event.level == "warning" and event.message:
        print(f"\n  WARN: {event.message}")

try:
    entry = index_path(
        Path("/path/to/large/archive"),
        config,
        progress_callback=on_progress,
        cancel_event=cancel,
    )
    print(f"\nDone: {entry.id}")
except IndexerCancellationError:
    print("\nCancelled by user.")
```

To cancel from another thread (e.g., a GUI button handler), call `cancel.set()`. The engine will stop at the next item boundary.

#### Error handling

```python
from pathlib import Path
from shruggie_indexer import index_path, load_config
from shruggie_indexer.core.entry import IndexerTargetError, IndexerRuntimeError
from shruggie_indexer.config.loader import IndexerConfigError

try:
    config = load_config(overrides={"id_algorithm": "blake2"})
except IndexerConfigError as e:
    print(f"Configuration error: {e}")
    # "id_algorithm must be 'md5' or 'sha256', got 'blake2'"

try:
    entry = index_path(Path("/nonexistent/path"))
except IndexerTargetError as e:
    print(f"Target error: {e}")
    # "Target does not exist: /nonexistent/path"
```

#### Exception hierarchy

The library defines a small exception hierarchy for programmatic error handling. All exceptions inherit from a common base class to enable catch-all handling when fine-grained distinction is unnecessary.

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

These exceptions are defined in `core/entry.py` (for target, runtime, and cancellation errors), `config/loader.py` (for config errors), and `core/rename.py` (for rename errors). The base `IndexerError` is defined in the top-level `__init__.py` and re-exported by each module that defines a subclass. `IndexerCancellationError` is also re-exported from the top-level namespace for convenience.

The exception hierarchy maps directly to the CLI exit codes (Ã‚Â§8.10): `IndexerConfigError` Ã¢â€ â€™ exit code 2, `IndexerTargetError` Ã¢â€ â€™ exit code 3, `IndexerRuntimeError` Ã¢â€ â€™ exit code 4, `IndexerCancellationError` Ã¢â€ â€™ exit code 5 (`INTERRUPTED`). `RenameError` is a subclass of `IndexerRuntimeError` for exit code purposes but is distinct for programmatic callers who want to handle rename failures specifically. `IndexerCancellationError` is raised when the `cancel_event` parameter (available on `index_path()` and `build_directory_entry()`) is set by a caller. In the GUI, the cancel event is set by the Cancel button (Ã‚Â§10.5). In the CLI, it is set by the `SIGINT` handler when the user presses `Ctrl+C` (Ã‚Â§8.11).

> **Improvement over original:** The original communicates errors through `Vbs` log messages and PowerShell's unstructured error stream. There are no typed exceptions, no error hierarchy, and no programmatic way to distinguish between "target not found," "configuration invalid," and "runtime failure." The port's typed exceptions enable callers to implement precise error recovery strategies.

## 6. Core Operations

This section defines the behavioral contract for every operation in the indexing engine — the inputs each operation accepts, the outputs it produces, the invariants it maintains, the error conditions it handles, and the deviations it makes from the original implementation. Each subsection corresponds to one operation category from the Operations Catalog (§1.5) and to one or more `core/` modules from the source package layout (§3.2). Together, these subsections constitute the complete specification of what the `core/` subpackage does and how it does it.

The operations are presented in dependency order: foundational operations (traversal, path manipulation, hashing) before the operations that depend on them (entry construction, serialization). An implementer working through these subsections top-to-bottom will build the leaf modules first and the orchestrator last, with each module's dependencies already specified by the time it is reached.

§4 (Architecture) defines the structural relationships between modules — who calls whom. This section defines the behavioral detail within each module — what each function does when called. §5 (Output Schema) defines the data structures that these operations produce. The three sections are complementary: §4 provides the wiring diagram, §6 provides the logic, and §5 provides the output contract.

### 6.1. Filesystem Traversal and Discovery

**Module:** `core/traversal.py`
**Operations Catalog:** Category 1
**Original functions:** `MakeDirectoryIndexLogic`, `MakeDirectoryIndexRecursiveLogic`, `MakeFileIndex`

#### Purpose

Enumerates the set of filesystem items (files and subdirectories) to be indexed within a target path. The traversal module is Stage 3 of the processing pipeline (§4.1) — it sits between target resolution (Stage 2) and entry construction (Stage 4). It does not build index entries; it produces an ordered sequence of `Path` objects that the entry builder will process.

#### Public interface

The traversal module exposes one primary function:

```python
def list_children(
    directory: Path,
    config: IndexerConfig,
) -> tuple[list[Path], list[Path]]:
    """Enumerate immediate children of a directory.

    Returns (files, directories) as two separate sorted lists.
    Items matching the configured exclusion filters are omitted.
    """
```

The caller — `core/entry.build_directory_entry()` — invokes `list_children()` once per directory being indexed. For recursive mode, the caller recurses into each returned subdirectory; for flat mode, the caller processes only the immediate children. The traversal module itself does not recurse — recursion is controlled by the entry builder (§6.8), consistent with the separation of traversal from construction described in §4.1.

> **Deviation from original (DEV-03):** The original has two near-identical traversal code paths: `MakeDirectoryIndexRecursiveLogic` (which calls itself for child directories) and `MakeDirectoryIndexLogic` (which does not recurse). Both paths enumerate children, separate files from directories, filter exclusions, and feed items to `MakeObject` — with almost completely duplicated logic. The port replaces both with a single `list_children()` function that returns files and directories. The recursive/flat distinction is handled by the caller, not by the traversal module. This eliminates the duplication without changing the logical behavior.

#### Enumeration strategy

`list_children()` enumerates directory contents using `os.scandir()` in a single pass. Each `DirEntry` object returned by `os.scandir()` is classified as a file or directory using `DirEntry.is_file(follow_symlinks=False)` and `DirEntry.is_dir(follow_symlinks=False)`. The `follow_symlinks=False` argument ensures that symlinks are classified based on the link itself, not the link target — a symlink to a directory appears in the files list (or the directories list if it is a directory symlink), and its symlink status is resolved later during entry construction (§6.4).

`os.scandir()` is preferred over `Path.iterdir()` because `DirEntry` objects cache the results of `is_file()` and `is_dir()` from the underlying `readdir` call on platforms that support it, avoiding redundant `stat()` calls. For large directories (tens of thousands of entries), this caching produces a measurable performance improvement.

> **Improvement over original:** The original performs two separate `Get-ChildItem` calls — one with `-File` and one with `-Directory` — to separate files from directories. This iterates the directory twice. `os.scandir()` classifies entries in a single pass.

#### Ordering

The returned file list and directory list are each sorted lexicographically by name (case-insensitive). Files are processed before directories by convention — the caller iterates the file list first, then the directory list. This matches the original's traversal order and produces output where file entries precede subdirectory entries within any `items` array.

The sort is performed via `sorted(entries, key=lambda e: e.name.lower())`. The case-insensitive comparison ensures consistent ordering across platforms (Windows is case-insensitive by default; Linux is case-sensitive).

#### Filesystem exclusion filters

Before returning, `list_children()` removes entries whose names match the configured exclusion set. The exclusion set is defined in `config.filesystem_excludes` — a set of case-insensitive name patterns. The default exclusion set covers cross-platform system artifacts:

| Platform | Default exclusions |
|----------|-------------------|
| Windows | `$RECYCLE.BIN`, `System Volume Information`, `desktop.ini`, `Thumbs.db` |
| macOS | `.DS_Store`, `.Spotlight-V100`, `.Trashes`, `.fseventsd`, `.TemporaryItems`, `.DocumentRevisions-V100` |
| Linux | `.Trash-*` (glob pattern) |
| All | `.git` (optional, configurable) |

The default set includes all platform-specific entries regardless of the current platform. Filtering a macOS entry on Windows is a no-op (the entry will not exist), but including it in the default list ensures that indexes produced from cross-platform network shares or external drives are clean. See §7 for the configuration schema and override mechanism.

> **Deviation from original (DEV-10):** The original hardcodes only `$RECYCLE.BIN` and `System Volume Information` as inline `Where-Object` filters. The port externalizes the exclusion list into configuration and expands the default set to cover all three target platforms.

Exclusion matching is performed by checking `entry.name.lower()` against the set of lowercased exclusion names. For glob-pattern exclusions (e.g., `.Trash-*`), `fnmatch.fnmatch()` is used. Simple string exclusions use direct set membership for O(1) matching. The exclusion check runs once per entry and is a negligible fraction of the traversal cost.

#### Error handling

If `os.scandir()` raises `PermissionError` or `OSError` for the directory itself, the error is a **fatal** condition for that directory — the directory cannot be enumerated. The error propagates to the caller (`build_directory_entry`), which handles it according to the item-level error tier (§4.5): the directory is either skipped or included with an empty `items` list and a warning logged.

If an individual `DirEntry` raises an exception during `.is_file()` or `.is_dir()` (rare but possible on network filesystems or corrupted directories), that single entry is skipped with a warning. The remaining entries are still returned.

#### Single-file scenario

When the target is a single file (§4.6), the traversal module is not called. The entry builder processes the file directly without enumeration. The `list_children()` function is only invoked for directory targets.

---

### 6.2. Path Resolution and Manipulation

**Module:** `core/paths.py`
**Operations Catalog:** Category 2
**Original functions:** `ResolvePath`, `FileId-ResolvePath`, `DirectoryId-ResolvePath`, `GetParentPath`, path manipulation in `MakeObject`

#### Purpose

Provides all path-related operations used by the rest of the indexing engine: resolving paths to canonical absolute form, extracting path components (name, stem, suffix, parent), validating file extensions, and constructing derived paths for output files. This is the single source of truth for path handling — no other module performs its own path manipulation.

#### Public interface

```python
def resolve_path(path: Path) -> Path:
    """Resolve a path to its canonical absolute form.

    Resolves symlinks, normalizes separators, and collapses
    '..' and '.' components. Raises IndexerError if the path
    does not exist and cannot be resolved.
    """

def extract_components(path: Path) -> PathComponents:
    """Extract all path components needed by the entry builder.

    Returns a PathComponents object containing:
      name: str         - Full filename including extension (Path.name)
      stem: str         - Filename without extension (Path.stem)
      suffix: str|None  - Extension without leading dot, or None
      parent_name: str  - Name of the parent directory (Path.parent.name)
      parent_path: Path - Absolute path of the parent directory
    """

def validate_extension(suffix: str, config: IndexerConfig) -> str | None:
    """Validate a file extension against the configured regex pattern.

    Returns the validated extension string (lowercase, no leading dot)
    if valid; returns None if the extension is empty or fails validation.
    """

def build_sidecar_path(item_path: Path, item_type: str) -> Path:
    """Construct the path for an in-place sidecar output file.

    For files: <item_path>_meta2.json
    For directories: <item_path>/_directorymeta2.json
    """

def build_storage_path(
    item_path: Path, storage_name: str
) -> Path:
    """Construct the target path for a rename operation.

    Returns item_path.parent / storage_name.
    """
```

> **Deviation from original (DEV-04):** The original contains three independent copies of path-resolution logic: `ResolvePath` inside `MakeIndex`, `FileId-ResolvePath` inside `FileId`, and `DirectoryId-ResolvePath` inside `DirectoryId`. All three do the same thing — call `Resolve-Path` with a `GetFullPath()` fallback for non-existent paths. The port provides exactly one `resolve_path()` function, called from everywhere. The original also uses `GetParentPath` (a manual `Split-Path` wrapper) and direct `[System.IO.Path]` calls for component extraction. The port consolidates all of these into `extract_components()` using `pathlib` properties.

#### Path resolution behavior

`resolve_path()` calls `Path.resolve(strict=True)` for paths that exist on the filesystem. This resolves symlinks, normalizes directory separators, and produces an absolute path. If the path does not exist, `resolve_path()` falls back to `Path.resolve(strict=False)`, which normalizes the path without verifying existence. If neither resolution produces a usable path, an `IndexerError` is raised.

The `strict=True` → `strict=False` fallback mirrors the original's `Resolve-Path` → `GetFullPath()` fallback pattern, but without requiring a try/except around the initial resolution — `pathlib` handles the dispatch cleanly.

#### Component extraction

`extract_components()` derives all components from `pathlib.Path` properties rather than string manipulation:

| Component | `pathlib` property | Notes |
|-----------|-------------------|-------|
| `name` | `path.name` | Full filename including extension. |
| `stem` | `path.stem` | Filename without the final extension. |
| `suffix` | `path.suffix` | The final extension, including the leading dot. Converted to lowercase and stripped of the leading dot before returning. Empty string → `None`. |
| `parent_name` | `path.parent.name` | The leaf name of the parent directory. For root-level items (e.g., `C:\file.txt`), this is an empty string — the caller handles this as the "no parent" case. |
| `parent_path` | `path.parent` | The absolute path to the parent directory. |

The suffix is always lowercased for consistency. The original lowercases extensions via `.ToLower()` in `MakeObject`; the port does the same via `.lower()`.

#### Extension validation

`validate_extension()` matches the extracted suffix against a configurable regex pattern. The default pattern reproduces the intent of the original's hardcoded regex:

```
Original: ^(([a-z0-9]){1,2}|([a-z0-9]){1}([a-z0-9\-]){1,12}([a-z0-9]){1})$
```

This pattern accepts extensions that are 1–2 alphanumeric characters, or 3–14 characters where the first and last are alphanumeric and interior characters may include hyphens. The purpose is to reject malformed or suspiciously long extensions that might indicate corrupted filenames or path components misidentified as extensions.

The port uses `re.fullmatch()` with the pattern compiled once from `config.extension_validation_pattern`. This is the same regex content as the original's but applied via Python's `re` module rather than PowerShell's `-match` operator.

> **Deviation from original (DEV-14):** The extension validation regex is externalized into the configuration system rather than hardcoded. Users who encounter legitimate long extensions (e.g., `.numbers`, `.download`, `.crdownload`) can adjust the pattern without editing source code.

When validation fails, the extension is treated as absent — the entry's `extension` field is set to `null` and the `storage_name` is constructed from the `id` alone (no extension appended). A debug-level log message is emitted noting the rejected extension.

#### Path construction

`build_sidecar_path()` constructs the in-place output path using the v2 naming convention:

| Item type | Sidecar path pattern | Example |
|-----------|---------------------|---------|
| File | `{parent_dir}/{filename}_meta2.json` | `photos/sunset.jpg` → `photos/sunset.jpg_meta2.json` |
| Directory | `{directory}/_directorymeta2.json` | `photos/vacation/` → `photos/vacation/_directorymeta2.json` |

The `2` suffix in `_meta2.json` and `_directorymeta2.json` prevents collision with existing v1 sidecar files (`_meta.json`, `_directorymeta.json`) during a migration period. See §5.13.

`build_storage_path()` constructs the rename-target path by joining the item's parent directory with its `storage_name`. No separator management is needed — `pathlib`'s `/` operator handles platform-correct path construction.

> **Improvement over original:** The original constructs renamed paths by concatenating strings with the `$Sep` global variable. The port uses `pathlib` path arithmetic, eliminating manual separator handling entirely.

---

### 6.3. Hashing and Identity Generation

**Module:** `core/hashing.py`
**Operations Catalog:** Category 3
**Original functions:** `FileId` (and 8 sub-functions), `DirectoryId` (and 7 sub-functions), `ReadMetaFile-GetNameHashMD5`, `ReadMetaFile-GetNameHashSHA256`, `MetaFileRead-Sha256-File`, `MetaFileRead-Sha256-String`

#### Purpose

Computes cryptographic hash digests of file contents and name strings, and from those digests produces the deterministic unique identifiers (`id` field) that are the foundation of the indexing system. This is the most dependency-consolidated module in the port — it replaces four separate locations in the original where hashing logic was independently implemented.

> **Deviation from original (DEV-01):** The original has no fewer than four independent implementations of the same hashing logic: `FileId` (8 sub-functions for file content and name hashing), `DirectoryId` (4 sub-functions for directory name hashing), `ReadMetaFile-GetNameHashMD5` / `-SHA256` (sidecar file name hashing inside MakeIndex), and `MetaFileRead-Sha256-File` / `-Sha256-String` (content and name hashing inside MetaFileRead). The port provides one hashing module with reusable functions, called from everywhere.

#### Public interface

```python
def hash_file(path: Path, algorithms: tuple[str, ...] = ("md5", "sha256")) -> HashSet:
    """Compute content hashes of a file.

    Reads the file in chunks and feeds each chunk to all requested
    hash algorithms simultaneously. Returns a HashSet with the
    computed digests.
    """

def hash_string(value: str, algorithms: tuple[str, ...] = ("md5", "sha256")) -> HashSet:
    """Compute hashes of a UTF-8 encoded string.

    Encodes the string to UTF-8 bytes and computes the requested
    digests. Returns a HashSet.
    """

def hash_directory_id(
    name: str,
    parent_name: str,
    algorithms: tuple[str, ...] = ("md5", "sha256"),
) -> HashSet:
    """Compute directory identity using the two-layer hashing scheme.

    Algorithm:
      1. hash(name)       → name_digest
      2. hash(parent_name) → parent_digest
      3. hash(name_digest + parent_digest) → final_digest

    Returns a HashSet containing the final digests.
    """

def select_id(
    hashes: HashSet,
    algorithm: str,
    prefix: str,
) -> str:
    """Select and prefix an identity value from a HashSet.

    Returns prefix + hashes[algorithm], e.g., "yA8A8C089...".
    """

# Module-level constants (computed once at import time)
NULL_HASHES: HashSet  # Hash of empty string b'' for each algorithm
```

#### Algorithms

The port computes MD5 and SHA256 by default for all hash operations. SHA512 is computed when explicitly enabled in the configuration (`config.compute_sha512 = True`). SHA1 is not computed.

> **Deviation from original:** The original's `FileId` and `DirectoryId` accept an `IncludeHashTypes` parameter defaulting to `@('md5', 'sha256')`, and the output schema defines fields for SHA1 and SHA512 that remain empty at runtime. The port drops SHA1 entirely (see §5.2.1 for the rationale — SHA1 serves no unique purpose and adds overhead). SHA512 is available as an opt-in for consumers who want high-strength digests. MD5 and SHA256 are always computed because they serve the identity system: MD5 is the legacy default `id_algorithm`, and SHA256 is the recommended alternative.

#### Multi-algorithm single-pass hashing

`hash_file()` reads the file in fixed-size chunks and feeds each chunk to all active hash objects simultaneously. This is the core performance optimization described in §17.1:

```python
# Illustrative — not the exact implementation.
def hash_file(path: Path, algorithms: tuple[str, ...] = ("md5", "sha256")) -> HashSet:
    hashers = {alg: hashlib.new(alg) for alg in algorithms}
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            for h in hashers.values():
                h.update(chunk)
    return HashSet(
        md5=hashers["md5"].hexdigest().upper(),
        sha256=hashers["sha256"].hexdigest().upper(),
        sha512=hashers.get("sha512", _Absent).hexdigest().upper() if "sha512" in hashers else None,
    )
```

The chunk size (`CHUNK_SIZE`) defaults to 65,536 bytes (64 KB). This value balances memory usage against read-call overhead — Python's `hashlib` documentation recommends chunk sizes between 4 KB and 128 KB for stream hashing. The chunk size is not configurable; it is an implementation detail of the hashing module.

> **Improvement over original (DEV-02):** The original computes each hash algorithm in a separate pass, opening and reading the file once per algorithm. For a file hashed with two algorithms, this means two complete reads. The port reads the file once and updates all hash objects from each chunk, halving the I/O for the default two-algorithm case.

#### String hashing

`hash_string()` encodes the input string to UTF-8 bytes via `value.encode("utf-8")` and computes the requested digests in a single pass. This mirrors the original's `[System.Text.Encoding]::UTF8.GetBytes()` conversion.

For `None` or empty-string inputs, `hash_string()` returns the `NULL_HASHES` constant rather than computing the hash of an empty byte sequence. The result is identical (the hash of `b""` is the null-hash constant for each algorithm), but returning the precomputed constant avoids unnecessary hash construction.

#### Null-hash constants

The `NULL_HASHES` module-level constant is computed once at import time:

```python
NULL_HASHES = HashSet(
    md5=hashlib.md5(b"").hexdigest().upper(),
    sha256=hashlib.sha256(b"").hexdigest().upper(),
    sha512=hashlib.sha512(b"").hexdigest().upper(),
)
```

> **Deviation from original (DEV-09):** The original hardcodes null-hash constants as literal hex strings in multiple locations (e.g., `D41D8CD98F00B204E9800998ECF8427E` for MD5). The port computes them once from `hashlib`, which is self-documenting, immune to copy-paste errors, and automatically correct if the algorithm set changes.

#### Directory identity scheme

`hash_directory_id()` implements the original's two-layer directory identity algorithm:

1. Compute `hash(directory_name)` → `name_digest` (a hex string).
2. Compute `hash(parent_directory_name)` → `parent_digest` (a hex string).
3. Concatenate the two hex strings: `combined = name_digest + parent_digest`.
4. Compute `hash(combined)` → `final_digest`.

This is performed independently for each active hash algorithm. Step 3 concatenates the uppercase hex representations of the digests (not the raw bytes), matching the original's `[BitConverter]::ToString()` output concatenation. The concatenation order is name-first, parent-second.

When the parent name is an empty string (the directory is at a filesystem root), step 2 produces the null-hash constant. This matches the original's behavior — `DirectoryId-HashString` returns the hardcoded null-hash for empty inputs.

#### Identity prefix convention

| Item type | Prefix | Example |
|-----------|--------|---------|
| File | `y` | `yA8A8C089A6A8583B24C85F5A4A41F5AC` |
| Directory | `x` | `x3B4F479E9F880E438882FC34B67D352C` |
| Generated metadata | `z` | `z7E240DE74FB1ED08FA08D38063F6A6A9` |

The `select_id()` function applies the appropriate prefix to the digest selected by `config.id_algorithm` (either `"md5"` or `"sha256"`). The prefix is prepended as a literal character — `f"{prefix}{digest}"` — producing the `id` field value for the output schema.

The `z` prefix for generated metadata entries (exiftool output) is a v2 addition. In v1, generated metadata entries use the `y` prefix (same as files) because their identity is derived from content hashing. In v2, the `z` prefix provides a namespace that distinguishes generated entries from sidecar entries without inspecting the `origin` field.

#### Uppercase convention

All hex digest strings are uppercased via `hexdigest().upper()`. The original uses `.ToUpper()` on `[BitConverter]::ToString()` output (which produces hyphen-separated uppercase hex, with the hyphens stripped via `.Replace('-', '')`). Python's `hashlib.hexdigest()` produces lowercase hex without separators; the `.upper()` call normalizes to the convention established by the original.

#### Symlink hashing fallback

When a file is a symlink, content hashing is replaced by name hashing — `hash_file()` is not called, and `hash_string(filename)` is used instead to produce the `hashes` field. The symlink detection itself is handled by the entry builder (§6.8) or by a dedicated check described in §6.4; the hashing module does not detect symlinks. It simply provides `hash_file()` for content and `hash_string()` for names, and the caller chooses which to invoke.

This matches the original's behavior in `FileId`, where the `ReparsePoint` attribute check gates whether the content hash or name hash is used.

---

### 6.4. Symlink Detection

**Module:** `core/entry.py` (inline within entry construction), also consulted in `core/hashing.py` call decisions
**Operations Catalog:** Category 4
**Original functions:** `FileId` (ReparsePoint attribute check), `DirectoryId` (hardcoded `IsLink = $false`), `MakeObject` (reads `.IsLink` from identity result)

#### Purpose

Determines whether a file or directory is a symbolic link. This determination controls two downstream behaviors: the hashing strategy (content hashing vs. name hashing fallback for files) and the `attributes.is_link` field in the output schema.

#### Detection mechanism

Symlink detection uses a single call: `path.is_symlink()`. This works cross-platform:

| Platform | Underlying mechanism |
|----------|---------------------|
| Windows | Detects NTFS reparse points (symlinks, junctions). Equivalent to the original's `Attributes -band ReparsePoint` check. |
| Linux/macOS | Detects POSIX symbolic links via `lstat()`. |

The call is performed on the original path (before symlink resolution) using `os.lstat()` semantics — `Path.is_symlink()` does not follow the link.

> **Improvement over original:** The original uses `(Get-Item).Attributes -band [System.IO.FileAttributes]::ReparsePoint`, a Windows-specific bitwise attribute check. `Path.is_symlink()` is the correct cross-platform equivalent and is strictly simpler.

#### Behavioral effects

When `is_symlink` is `True`:

| Operation | Normal behavior | Symlink behavior |
|-----------|----------------|------------------|
| File content hashing (§6.3) | `hash_file(path)` — hash file bytes | `hash_string(filename)` — hash name string instead |
| EXIF extraction (§6.6) | Invoke exiftool | Skip entirely — return `None` |
| Timestamp extraction (§6.5) | `os.stat()` (follows symlink) | `os.lstat()` (reads symlink metadata itself) |
| `hashes` field in output | Content hash digest set | Name hash digest set (same values as `name.hashes`) |

For directory symlinks, the identity scheme is unchanged — directory identity is always based on name hashing (the two-layer scheme in §6.3), so no fallback is needed.

#### Dead code: `ValidateIsLink`

The original lists `ValidateIsLink` as a dependency of `MakeIndex` but never calls it. The `is_symlink` check is performed inline within `FileId` and `DirectoryId`. The port does not carry `ValidateIsLink` forward (DEV-13).

#### Dangling symlinks

A dangling symlink (one whose target does not exist) is treated as an item-level warning. `Path.is_symlink()` returns `True` for dangling symlinks (it reads the link itself, not its target). The entry builder proceeds with degraded fields: `hashes` are computed from the name, `size` is `null`, timestamps come from `os.lstat()` (the symlink's own metadata), and exif/sidecar operations are skipped. A warning is logged identifying the dangling link.

> **Improvement over original:** The original does not explicitly handle dangling symlinks. A missing link target causes `Get-Item` to fail, producing platform-dependent error behavior. The port's explicit handling is a robustness improvement.

---

### 6.5. Filesystem Timestamps and Date Conversion

**Module:** `core/timestamps.py`
**Operations Catalog:** Category 5
**Original functions:** `MakeObject` (timestamp reading and formatting), `Date2UnixTime` (string-to-Unix conversion)

#### Purpose

Extracts filesystem timestamps from stat results and produces both Unix-millisecond integers and ISO 8601 formatted strings for each of the three standard timestamp types: accessed, created, and modified. The output populates the `timestamps` field of the v2 schema (`TimestampsObject` containing three `TimestampPair` values — see §5.7).

#### Public interface

```python
def extract_timestamps(
    stat_result: os.stat_result,
    *,
    is_symlink: bool = False,
) -> TimestampsObject:
    """Derive all timestamps from an os.stat_result.

    Returns a TimestampsObject containing accessed, created, and
    modified TimestampPairs, each with both ISO 8601 and Unix
    millisecond representations.

    When is_symlink is True, the stat_result is expected to come
    from os.lstat() (symlink metadata) rather than os.stat()
    (target metadata).
    """
```

The stat result is obtained by the entry builder (§6.8) before calling this function. The entry builder chooses between `os.stat()` (for regular files/directories) and `os.lstat()` (for symlinks) and passes the result.

#### Derivation — Unix timestamps

Unix timestamps are derived directly from the stat result's floating-point values, converted to milliseconds:

| Timestamp | Stat attribute | Conversion |
|-----------|---------------|------------|
| `accessed.unix` | `st_atime` | `int(stat_result.st_atime * 1000)` |
| `modified.unix` | `st_mtime` | `int(stat_result.st_mtime * 1000)` |
| `created.unix` | See below | See below |

> **Deviation from original (DEV-07):** The original performs an unnecessary round-trip: it formats a datetime to a string via `.ToString($DateFormat)`, then passes that string to `Date2UnixTime`, which parses it back into a `DateTimeOffset` to call `.ToUnixTimeMilliseconds()`. The port derives Unix timestamps directly from the stat float values — no intermediate string representation, no round-trip parsing, and `Date2UnixTime` (along with its entire internal dependency chain: `Date2FormatCode`, `Date2UnixTimeSquash`, `Date2UnixTimeCountDigits`, `Date2UnixTimeFormatCode`) is eliminated.

#### Creation time portability

Creation time handling varies by platform and is one of the primary portability concerns for the timestamp module (see §15.5 for the full platform analysis). The resolution strategy is:

1. Attempt `stat_result.st_birthtime`. This is the true file creation time and is available on macOS (all filesystems), Windows (NTFS), and some Linux configurations (kernel 4.11+ with `statx` support on ext4/XFS/Btrfs). If the attribute exists, use it.

2. Fall back to `stat_result.st_ctime`. On Windows, `st_ctime` is the creation time (Python's Windows `stat()` maps it correctly). On Linux and macOS, `st_ctime` is the inode change time (metadata modification), not the creation time — but it is the best available approximation.

The implementation wraps the `st_birthtime` access in a try/except for `AttributeError`, since the attribute is absent on platforms that do not support it. This is not a per-file error condition — it is a platform characteristic discovered once. The timestamps module MAY cache the platform's creation-time capability after the first successful or failed `st_birthtime` access to avoid redundant exception handling on subsequent calls.

```python
# Illustrative — not the exact implementation.
def _get_creation_time(stat_result: os.stat_result) -> float:
    try:
        return stat_result.st_birthtime
    except AttributeError:
        return stat_result.st_ctime
```

No warning is emitted for the `st_ctime` fallback — it is expected behavior on most Linux systems and would produce noise without actionable information.

#### Derivation — ISO 8601 strings

ISO strings are produced from `datetime` objects constructed from the same stat float values:

```python
# Illustrative — not the exact implementation.
from datetime import datetime, timezone

def _stat_to_iso(timestamp_float: float) -> str:
    dt = datetime.fromtimestamp(timestamp_float, tz=timezone.utc).astimezone()
    return dt.isoformat(timespec="microseconds")
```

The `datetime.fromtimestamp()` call interprets the float as seconds since the Unix epoch and attaches the UTC timezone. The `.astimezone()` call converts to the local timezone, producing an ISO 8601 string with the local timezone offset (e.g., `2024-03-15T14:30:22.123456-04:00`).

The `timespec="microseconds"` argument produces 6-digit fractional seconds. The original's .NET format string `yyyy-MM-ddTHH:mm:ss.fffffffzzz` produces 7-digit fractional seconds. Python's `datetime` provides microsecond precision (6 digits); .NET provides tick precision (7 digits). This is a minor, acceptable deviation — the 7th digit is always zero in practice for filesystem timestamps, which have at most microsecond resolution.

#### The `TimestampPair` assembly

For each of the three timestamp types, the module constructs a `TimestampPair` (§5.2.4):

```python
TimestampPair(
    iso=_stat_to_iso(timestamp_float),
    unix=int(timestamp_float * 1000),
)
```

These are assembled into a `TimestampsObject` (§5.2.5):

```python
TimestampsObject(
    accessed=TimestampPair(...),
    created=TimestampPair(...),
    modified=TimestampPair(...),
)
```

The complete `TimestampsObject` is returned to the entry builder, which places it directly into the `IndexEntry.timestamps` field.

---

### 6.6. EXIF and Embedded Metadata Extraction

**Module:** `core/exif.py`
**Operations Catalog:** Category 6
**Original functions:** `GetFileExif`, `GetFileExifArgsWrite`, `GetFileExifRun`

#### Purpose

Invokes the `exiftool` binary to extract embedded EXIF, XMP, and IPTC metadata from a file. The extracted metadata is returned as a Python dictionary (parsed from exiftool's JSON output), with unwanted system keys removed. The result is wrapped into a `MetadataEntry` with `origin: "generated"` and `attributes.type: "exiftool.json_metadata"` during entry construction (§6.8).

#### Public interface

```python
def extract_exif(
    path: Path,
    config: IndexerConfig,
) -> dict | None:
    """Extract embedded metadata from a file using exiftool.

    Returns a dict of metadata key-value pairs, or None if:
      - exiftool is not available
      - the file extension is in the exclusion list
      - exiftool returns an error or no data
      - the item is a symlink
    """
```

#### Exiftool availability probe

Before the first exiftool invocation, the module checks whether `exiftool` is available on the system PATH. This probe happens once per process lifetime (not once per file) and the result is cached in a module-level variable.

```python
# Illustrative — not the exact implementation.
_exiftool_available: bool | None = None  # None = not yet checked

def _check_exiftool() -> bool:
    global _exiftool_available
    if _exiftool_available is None:
        _exiftool_available = shutil.which("exiftool") is not None
        if not _exiftool_available:
            logger.warning(
                "exiftool not found on PATH; embedded metadata extraction disabled"
            )
    return _exiftool_available
```

> **Improvement over original:** The original invokes exiftool for every eligible file without checking availability first. If exiftool is missing, each invocation fails independently, producing a per-file error. The port's probe-once approach avoids spawning doomed subprocesses and reduces log noise to a single warning. See §4.5 for the full discussion.

#### Extension exclusion

Before invoking exiftool, the module checks `path.suffix.lower()` (without the leading dot) against `config.exiftool_exclude_extensions`. The default exclusion set, carried forward from the original's `$global:MetadataFileParser.Exiftool.Exclude`, includes file types where exiftool tends to dump the entire file content into the metadata output rather than extracting meaningful embedded metadata:

`csv`, `htm`, `html`, `json`, `tsv`, `xml`

The exclusion list is configurable (§7.4). When a file is excluded, the function returns `None` and a debug-level message is logged.

#### Invocation

Exiftool is invoked via `subprocess.run()` with arguments passed as a Python list:

```python
# Illustrative — not the exact implementation.
result = subprocess.run(
    [
        "exiftool",
        "-json",
        "-n",
        "-extractEmbedded",
        "-scanForXMP",
        "-unknown2",
        "-G3:1",
        "-struct",
        "-ignoreMinorErrors",
        "-charset", "filename=utf8",
        "-api", "requestall=3",
        "-api", "largefilesupport=1",
        str(path),
    ],
    capture_output=True,
    text=True,
    timeout=30,
)
```

> **Deviation from original (DEV-05):** The original stores exiftool arguments as Base64-encoded strings in the PowerShell source, decodes them at runtime via `Base64DecodeString` (which itself calls `certutil` on Windows), writes them to a temporary file via `TempOpen`, passes the temporary file to exiftool via its `-@` argfile switch, and cleans up via `TempClose`. The port defines the arguments as a plain Python list and passes them directly to `subprocess.run()`. This eliminates four dependencies in one stroke: `Base64DecodeString`, `certutil`, `TempOpen`, and `TempClose`. The temporary argument file is also eliminated — `subprocess` handles argument passing on all platforms without an intermediary file.

The `-quiet` flag is appended when the logging level is above DEBUG, matching the original's behavior of suppressing exiftool's informational output when verbosity is off.

The `timeout=30` parameter prevents a hung exiftool process from blocking the indexer indefinitely. If the timeout is exceeded, the function returns `None` and a warning is logged. The timeout value is not currently configurable but MAY be exposed in a future configuration update if users encounter legitimate long-running extractions.

#### Output parsing and key filtering

Exiftool's `-json` flag produces a JSON array containing one object per input file. Since the port processes one file at a time, the output is always a single-element array. The module parses the output via `json.loads()` and extracts the first element.

> **Deviation from original (DEV-06):** The original pipes exiftool output through `jq` for two purposes: compacting the JSON (`jq -c '.[] | .'`) and deleting unwanted keys via a second `jq` pass (`jq -c 'del(.ExifToolVersion, .FileSequence, ...)'`). The port eliminates `jq` entirely. `json.loads()` handles parsing natively, and unwanted keys are removed with a dict comprehension.

The unwanted key set, carried forward from the original's `jq` deletion list, includes:

`ExifToolVersion`, `FileSequence`, `NewGUID`, `Directory`, `FileName`, `FilePath`, `BaseName`, `FilePermissions`

These keys are exiftool operational metadata (not embedded metadata from the file) and are removed to keep the output clean. The filtering is a single dict comprehension:

```python
EXIFTOOL_EXCLUDED_KEYS = frozenset({
    "ExifToolVersion", "FileSequence", "NewGUID", "Directory",
    "FileName", "FilePath", "BaseName", "FilePermissions",
})

filtered = {k: v for k, v in raw_data.items() if k not in EXIFTOOL_EXCLUDED_KEYS}
```

The excluded key set is not currently configurable. Unlike the extension exclusion list (which users may legitimately need to modify), the key exclusion list is a fixed property of exiftool's output format. If future exiftool versions add new operational keys, the set can be extended in a maintenance update.

#### Error handling

| Condition | Behavior | Severity tier |
|-----------|----------|---------------|
| Exiftool not on PATH | Return `None`. Single warning on first probe. | Field-level |
| Extension in exclusion list | Return `None`. Debug log. | Diagnostic |
| Item is a symlink | Return `None`. Debug log. | Diagnostic |
| Exiftool returns non-zero | Return `None`. Warning with stderr content. | Field-level |
| Exiftool output is not valid JSON | Return `None`. Warning with parse error. | Field-level |
| Exiftool times out | Return `None`. Warning. | Field-level |
| Exiftool returns empty metadata | Return `None`. Debug log. | Diagnostic |

In all cases, the entry builder proceeds with `metadata` containing no exiftool entry (or with the exiftool entry omitted from the metadata array). No exiftool failure is fatal.

#### Batch mode consideration

For large directory trees, spawning a new exiftool process per file introduces significant overhead. The `PyExifTool` library maintains a persistent exiftool process and communicates via stdin/stdout, which is substantially faster for batch operations. The port SHOULD support both modes: direct `subprocess` invocation (default, zero third-party dependencies) and `PyExifTool` batch mode (optional, enabled when the library is installed). The batch mode implementation is deferred to a performance optimization pass — the `subprocess` mode is sufficient for MVP.

---

### 6.7. Sidecar Metadata File Handling

**Module:** `core/sidecar.py`
**Operations Catalog:** Category 7
**Original functions:** `GetFileMetaSiblings`, `ReadMetaFile`, `MetaFileRead` (and its 20+ sub-functions)

#### Purpose

Discovers, classifies, reads, and parses sidecar metadata files that live alongside the files they describe. A sidecar file is any file in the same directory as the indexed item whose name matches a known metadata suffix pattern (e.g., `video.mp4.info.json`, `photo.jpg_thumbnail.jpg`, `document.pdf.description`). The module produces `MetadataEntry` objects (§5.10) for each discovered sidecar, carrying the full provenance information needed for MetaMergeDelete reversal.

#### Public interface

```python
def discover_and_parse(
    item_path: Path,
    item_name: str,
    siblings: list[Path],
    config: IndexerConfig,
    delete_queue: list[Path] | None = None,
) -> list[MetadataEntry]:
    """Discover and parse sidecar metadata files for an item.

    Args:
        item_path: Absolute path to the indexed item.
        item_name: The item's filename (used for suffix matching).
        siblings: Pre-enumerated list of all files in the same directory.
        config: Configuration containing identification patterns and
                exclusion rules.
        delete_queue: When MetaMergeDelete is active, sidecar paths are
                      appended here for deferred deletion.

    Returns a list of MetadataEntry objects, one per discovered sidecar.
    Returns an empty list if no sidecars are found.
    """
```

The `siblings` list is provided by the entry builder, which already has the directory listing from `list_children()`. This avoids re-scanning the directory for each file being indexed — a significant optimization for directories containing many files with few sidecars.

#### Sidecar discovery

Discovery matches sibling filenames against the indexed item's name combined with known metadata suffix patterns. The identification patterns are defined in `config.metadata_identify` — a dict mapping type names to lists of compiled regex patterns. These patterns are ported from the original `$global:MetadataFileParser.Identify` configuration.

The discovery algorithm:

1. Escape the indexed item's filename for use in regex: `escaped_name = re.escape(item_name)`.
2. For each sibling file in the directory, check whether its name matches any pattern in the identification configuration. A match means the sibling is a sidecar of the identified type.
3. Exclude sidecars whose names match the configured exclusion patterns (`config.metadata_exclude_patterns`).
4. Return the matched sidecars grouped by type.

> **Improvement over original:** The original's `GetFileMetaSiblings` rescans the parent directory via `Get-ChildItem` for every indexed file. In a directory with 1,000 files, this means 1,000 redundant directory reads. The port's approach — passing the pre-enumerated `siblings` list — performs the directory read once.

#### Type detection

Each discovered sidecar is classified into exactly one type by matching its filename against the type identification patterns. The recognized types (carried forward from the original `$global:MetadataFileParser.Identify` keys) are:

| Type key | Description | Data handling |
|----------|-------------|---------------|
| `description` | Text description files (youtube-dl `.description`) | JSON → text → binary fallback |
| `desktop_ini` | Windows `desktop.ini` files | Text |
| `generic_metadata` | Generic config/metadata (`.cfg`, `.conf`, `.yaml`, `.meta`) | JSON → text → binary fallback |
| `hash` | Hash/checksum files (`.md5`, `.sha256`, `.crc32`) | Lines (non-empty lines only) |
| `json_metadata` | JSON metadata (`.info.json`, `.meta.json`) | JSON |
| `link` | URL shortcuts (`.url`) and filesystem shortcuts (`.lnk`) | URL/path extraction |
| `screenshot` | Screen capture images | Base64-encoded binary |
| `subtitles` | Subtitle tracks (`.srt`, `.sub`, `.vtt`, `.lrc`) | JSON → text → binary fallback |
| `thumbnail` | Thumbnail/cover images (`.cover`, `.thumb`) | Base64-encoded binary |
| `torrent` | Torrent files | Base64-encoded binary |

If a sidecar matches zero patterns, it is ignored (not an error — the file simply is not a recognized sidecar type). If a sidecar matches multiple patterns, it is logged as a warning and classified as the first match, consistent with the original's behavior (which also takes the first match from iterating `$MetadataFileParser.Identify` keys).

#### Format-specific readers

After type detection, the sidecar's content is read by a format-specific handler. The handler selection follows a type-to-reader mapping:

**JSON reader.** Reads the file content and parses it via `json.loads()`. Used directly for `json_metadata` type. Used as the first attempt in the fallback chain for `description`, `generic_metadata`, and `subtitles`.

> **Improvement over original:** The original's `MetaFileRead-Data-ReadJson` pipes the file through `jq -c '.'` and then `ConvertFrom-Json`. The port uses `json.loads()` directly, eliminating the `jq` dependency for sidecar parsing as well.

**Text reader.** Reads the file as UTF-8 text via `path.read_text(encoding="utf-8")`. Returns the content as a string. Used for `description` (when JSON parsing fails), `generic_metadata` (same), and `desktop_ini`.

**Lines reader.** Reads the file as UTF-8 text and splits into a list of non-empty lines. Used for `hash` files and `subtitles` (when JSON and text fallbacks are exhausted).

**Binary reader.** Reads the file as raw bytes and Base64-encodes them via `base64.b64encode(path.read_bytes()).decode("ascii")`. Used for `screenshot`, `thumbnail`, and `torrent` types, and as the final fallback for types where text and JSON reading both fail.

> **Improvement over original:** The original's binary reader (`MetaFileRead-Data-Base64Encode`) uses `certutil -encode` to convert binary data to Base64, writing to a temporary file and stripping the header/footer lines that `certutil` adds. The port uses `base64.b64encode()` directly — one function call, no external binary, no temporary file.

**Link reader.** For `.url` files, parses the INI-format content to extract the `URL=` value. For `.lnk` files on Windows, the port MAY use `pylnk3` or `comtypes` to resolve the shortcut target; on non-Windows platforms, `.lnk` files are read as binary (Base64-encoded), since the `.lnk` format is Windows-specific. The original uses the external pslib functions `UrlFile2Url` and `Lnk2Path` for this; the port internalizes the logic.

#### Fallback chain

For types that support multiple formats (`description`, `generic_metadata`, `subtitles`), the reader attempts formats in order:

1. JSON → if valid JSON, store as `format: "json"` with `transforms: ["json_compact"]`.
2. Text → if readable as UTF-8 text, store as `format: "text"` with `transforms: []`.
3. Binary → Base64-encode the raw bytes, store as `format: "base64"` with `transforms: ["base64_encode"]`.

Each step catches the relevant exception (JSON parse error, Unicode decode error) and falls to the next. Only if all three fail is the sidecar recorded with `attributes.type: "error"` and `data: null`.

#### MetadataEntry construction

For each successfully read sidecar, the module constructs a `MetadataEntry` (§5.10) with full provenance:

| MetadataEntry field | Source |
|---------------------|--------|
| `id` | `"y" + hash_file(sidecar_path).sha256` (sidecar content hash) |
| `origin` | `"sidecar"` |
| `name` | `NameObject(text=sidecar_filename, hashes=hash_string(sidecar_filename))` |
| `hashes` | `hash_file(sidecar_path)` (content hashes of the original sidecar file) |
| `file_system` | `{"relative": relative_path_from_index_root}` |
| `size` | `SizeObject(bytes=sidecar_stat.st_size, text=human_readable_size)` |
| `timestamps` | `extract_timestamps(sidecar_stat)` |
| `attributes.type` | Detected type (e.g., `"json_metadata"`, `"thumbnail"`) |
| `attributes.format` | Data format (`"json"`, `"text"`, `"base64"`, `"lines"`) |
| `attributes.transforms` | Applied transforms (e.g., `["base64_encode"]`, `["json_compact"]`) |
| `attributes.source_media_type` | MIME type of binary sidecars (e.g., `"image/jpeg"` for thumbnails); `null` for text-based sidecars |
| `data` | Parsed content (varies by format) |

The provenance fields (`file_system`, `size`, `timestamps`) are the v2 additions that enable MetaMergeDelete reversal (§5.10, principle P3). They are present only for sidecar entries (`origin: "sidecar"`) and absent for generated entries.

#### MetaMergeDelete queue

When `config.meta_merge_delete` is `True` and the `delete_queue` parameter is not `None`, each successfully parsed sidecar's absolute path is appended to the delete queue. The actual deletion is deferred to Stage 6 post-processing (§4.4) — the sidecar module only records the path. This separation ensures that if the process is interrupted, no sidecar files have been deleted while their parent entries may be only partially written.

The original's `$global:DeleteQueue` pattern is preserved but with explicit parameter passing rather than global state.

---

### 6.8. Index Entry Construction

**Module:** `core/entry.py`
**Operations Catalog:** Category 8
**Original functions:** `MakeObject`, `MakeFileIndex`, `MakeDirectoryIndex`, `MakeDirectoryIndexLogic`, `MakeDirectoryIndexRecursive`, `MakeDirectoryIndexRecursiveLogic`

#### Purpose

Orchestrates the assembly of a complete `IndexEntry` (the v2 schema object defined in §5) from a filesystem path. This is the hub of the hub-and-spoke architecture described in §4.2 — `entry.py` is the sole module that calls into the component modules (`paths`, `hashing`, `timestamps`, `exif`, `sidecar`) and wires their outputs together into the final schema object. No component module calls another component module directly; all coordination flows through `entry.py`.

#### Public interface

```python
def build_file_entry(
    path: Path,
    config: IndexerConfig,
    siblings: list[Path] | None = None,
    delete_queue: list[Path] | None = None,
) -> IndexEntry:
    """Build a complete IndexEntry for a single file.

    Args:
        path: Absolute path to the file.
        config: Resolved configuration.
        siblings: Pre-enumerated sibling files in the same directory
                  (for sidecar discovery). If None, the module will
                  enumerate the parent directory.
        delete_queue: MetaMergeDelete accumulator (see §6.7).

    Returns a fully populated IndexEntry conforming to the v2 schema.
    """

def build_directory_entry(
    path: Path,
    config: IndexerConfig,
    recursive: bool = False,
    delete_queue: list[Path] | None = None,
) -> IndexEntry:
    """Build a complete IndexEntry for a directory.

    When recursive=True, descends into subdirectories and populates
    the items field with a fully nested tree of child IndexEntry objects.
    When recursive=False, populates items with only immediate children.

    Args:
        path: Absolute path to the directory.
        config: Resolved configuration.
        recursive: Whether to descend into subdirectories.
        delete_queue: MetaMergeDelete accumulator.

    Returns a fully populated IndexEntry conforming to the v2 schema.
    """

def index_path(
    target: Path,
    config: IndexerConfig,
) -> IndexEntry:
    """Top-level entry point: classify target and dispatch.

    This is the single function consumed by the CLI, GUI, and public API.
    Resolves the target, determines whether it is a file or directory,
    and delegates to build_file_entry() or build_directory_entry().
    """
```

#### File entry construction sequence

`build_file_entry()` executes the following steps in order. Each step calls into a component module and contributes one or more fields to the final `IndexEntry`.

**Step 1 — Path components.** Call `paths.extract_components(path)` to obtain `name`, `stem`, `suffix`, `parent_name`, and `parent_path`. Validate the extension via `paths.validate_extension()`.

**Step 2 — Stat and symlink detection.** Call `path.is_symlink()` to determine symlink status. Call `path.stat()` (or `path.lstat()` for symlinks) to obtain the stat result for timestamp and size extraction.

**Step 3 — Hashing.** If the file is not a symlink, call `hashing.hash_file(path)` to compute content hashes. If it is a symlink, call `hashing.hash_string(name)` to compute name hashes as the fallback. Also call `hashing.hash_string(name)` unconditionally to produce the `name.hashes` field.

**Step 4 — Identity selection.** Call `hashing.select_id(content_hashes, config.id_algorithm, "y")` to derive the `id` field.

**Step 5 — Timestamps.** Call `timestamps.extract_timestamps(stat_result, is_symlink=...)` to produce the `TimestampsObject`.

**Step 6 — Size.** Construct a `SizeObject` from `stat_result.st_size`. The `text` field is a human-readable representation (e.g., `"1.23 MB"`). For symlinks where the stat result comes from `lstat()`, the size reflects the symlink entry itself, not the target.

**Step 7 — Parent identity.** Compute the parent directory's identity via `hashing.hash_directory_id(parent_name, grandparent_name)`, then `hashing.select_id(..., "x")`. Construct a `ParentObject`. When the file is at a filesystem root (empty parent name), set `parent` to `null`.

**Step 8 — EXIF metadata.** If `config.extract_exif` is `True` and the file is not a symlink, call `exif.extract_exif(path, config)`. If the result is non-None, wrap it in a `MetadataEntry` with `origin: "generated"`, `attributes.type: "exiftool.json_metadata"`, `attributes.format: "json"`, and `attributes.transforms: ["key_filter"]`.

**Step 9 — Sidecar metadata.** If `config.meta_merge` is `True`, call `sidecar.discover_and_parse(path, name, siblings, config, delete_queue)`. Collect the returned `MetadataEntry` objects.

**Step 10 — Metadata assembly.** Combine the exiftool entry (if any) and sidecar entries into the `metadata` array. If metadata processing was active but produced no results, `metadata` is an empty list `[]`. If metadata processing was not active (neither exif nor sidecar flags enabled), `metadata` is `null`. See §5.10 for the semantic distinction.

**Step 11 — Storage name.** Construct `attributes.storage_name` from the `id` and `extension`: `f"{id}.{extension}"` for files with extensions, or just `id` for files without.

**Step 12 — Assembly.** Construct the final `IndexEntry` with all fields populated. Set `schema_version` to `2`, `type` to `"file"`, `items` to `null`.

> **Deviation from original:** The original's `MakeObject` contains a `switch` statement with five near-identical branches (`makeobjectfile`, `makeobjectdirectory`, `makeobjectdirectoryrecursive`, plus defaults) that all construct the same `[PSCustomObject]@{...}` with minor variations. The port uses a single construction path per item type — `build_file_entry()` for files and `build_directory_entry()` for directories — with no switch duplication.

#### Directory entry construction sequence

`build_directory_entry()` follows the same steps as file entry construction with these differences:

| Step | File behavior | Directory behavior |
|------|--------------|-------------------|
| 3 — Hashing | `hash_file()` for content | `hash_directory_id(name, parent_name)` for name-based identity |
| 4 — Identity | Prefix `y` | Prefix `x` |
| 6 — Size | `stat_result.st_size` | Sum of all child sizes (computed after child entries are built) |
| 8 — EXIF | Active for eligible files | Skipped (directories have no embedded metadata) |
| 9 — Sidecar | Active for files | Not applicable for the directory itself (but active for child files) |
| 12 — Items | `items = null` | `items = [child entries]` |

After constructing its own identity and timestamps, `build_directory_entry()` enumerates children via `traversal.list_children(path, config)` and recursively builds child entries:

1. For each child file: call `build_file_entry(child, config, siblings=all_child_files, delete_queue=...)`.
2. For each child subdirectory (when `recursive=True`): call `build_directory_entry(child, config, recursive=True, delete_queue=...)`.
3. Collect all child `IndexEntry` objects into the `items` list (files first, then directories, each group sorted by name).
4. Compute the directory's `size.bytes` as the sum of all child `size.bytes` values (recursive — includes all descendants).

When `recursive=False` (flat mode), child subdirectories are still processed by `build_directory_entry()` but with `recursive=False`, so they have a single level of children (or none, depending on implementation — the original processes immediate children only in flat mode). The flat-mode behavior produces a two-level tree: the target directory containing its immediate children, with child directories having their own identity and timestamps but no populated `items`.

#### Error handling during construction

Per-item error handling follows the strategy defined in §4.5:

| Error condition | Behavior |
|----------------|----------|
| `stat()` fails (permission denied, I/O error) | Item is skipped entirely. Warning logged. Item excluded from parent's `items` array. |
| Content hashing fails (I/O error on read) | `hashes` field set to `null`. Warning logged. Entry included with degraded fields. |
| Exiftool fails for this file | Exiftool entry omitted from `metadata`. Warning logged. |
| Sidecar file cannot be read | That sidecar's `MetadataEntry` has `attributes.type: "error"` and `data: null`. Warning logged. Other sidecars unaffected. |
| Child entry construction fails | Child excluded from parent's `items`. Warning logged. Remaining children processed. |

The entry builder never raises exceptions for item-level or field-level failures. Only fatal conditions (target path does not exist, configuration is invalid) produce exceptions that propagate to the caller.

---

### 6.9. JSON Serialization and Output Routing

**Module:** `core/serializer.py`
**Operations Catalog:** Category 9
**Original functions:** `MakeIndex` top-level output logic, `ConvertTo-Json` calls in traversal functions

#### Purpose

Converts `IndexEntry` model instances to JSON text and routes the result to one or more output destinations. This is Stage 5 of the processing pipeline (§4.1). The serializer is a pure presentation layer — it does not modify the `IndexEntry` data, only formats and delivers it.

#### Public interface

```python
def serialize_entry(
    entry: IndexEntry,
    *,
    compact: bool = False,
) -> str:
    """Serialize an IndexEntry to a JSON string.

    When compact=False, output is pretty-printed with 2-space indent.
    When compact=True, output is a single line.
    """

def write_output(
    entry: IndexEntry,
    config: IndexerConfig,
) -> None:
    """Route serialized output to configured destinations.

    Examines config.output_stdout, config.output_file, and
    config.output_inplace to determine where output goes.
    Multiple destinations may be active simultaneously.
    """

def write_inplace(
    entry: IndexEntry,
    item_path: Path,
    item_type: str,
) -> None:
    """Write a single in-place sidecar file alongside an item.

    Called during traversal for each item when inplace mode is active.
    The sidecar path is constructed via paths.build_sidecar_path().
    """
```

#### Serialization

Serialization converts an `IndexEntry` dataclass to JSON via a two-step process: `dataclasses.asdict(entry)` to produce a plain dict, followed by `json.dumps()` to produce the JSON string.

The serialization helper applies the invariants defined in §5.12:

1. `schema_version` is placed first in the output by using an `OrderedDict` or a custom key-sorting function. JSON objects are unordered, but the serializer places `schema_version` first by convention for human readability.

2. Optional `HashSet.sha512` fields are omitted (not emitted as `null`) when their value is `None`.

3. Sidecar-only `MetadataEntry` fields (`file_system`, `size`, `timestamps`) are present for sidecar entries and absent for generated entries, controlled by the `origin` discriminator.

4. `ensure_ascii=False` is passed to `json.dumps()` to produce UTF-8 output with non-ASCII characters preserved, matching the original's `Out-File -Encoding UTF8`.

When the `orjson` package is available, the serializer MAY use it as a drop-in replacement for faster serialization of large entry trees. `orjson` handles dataclasses natively and produces bytes rather than strings; the serializer wraps the output appropriately. The `orjson` path is gated by a try/except import and is transparent to callers.

> **Improvement over original:** The original uses `ConvertTo-Json -Depth 100` for serialization, which has a known memory ceiling for very large nested structures (documented in the original's own source comments). Python's `json.dumps()` handles arbitrarily deep nesting without this limitation. The `-Depth 100` workaround is unnecessary.

#### Output routing

The output routing model simplifies the original's seven-scenario matrix into three independent boolean flags that compose naturally:

| Flag | Config field | Behavior |
|------|-------------|----------|
| `--stdout` | `config.output_stdout` | Write the serialized JSON to `sys.stdout`. |
| `--outfile PATH` | `config.output_file` | Write the serialized JSON to the specified file path. |
| `--inplace` | `config.output_inplace` | Write individual sidecar files alongside each processed item. |

Any combination of these flags is valid. When no output flags are specified, the default is `--stdout` only (matching the original's default behavior).

> **Improvement over original:** The original's 7-scenario routing switch (`StandardOutput`/`NoStandardOutput` combined with `OutFile`/`OutFileInPlace`/both/neither) is replaced by three independent flags. The routing logic becomes a simple check-and-write for each enabled destination, with no complex scenario matrix. The `NoStandardOutput` negative flag is eliminated — the absence of `--stdout` is sufficient.

#### Timing of writes

| Destination | When written |
|-------------|-------------|
| `--stdout` | After the complete entry tree is assembled (end of Stage 4). The entire tree is serialized and written in one operation. |
| `--outfile` | After the complete entry tree is assembled. The entire tree is serialized and written to the file in one operation. |
| `--inplace` | During traversal (within the Stage 3–4 loop). Each item's sidecar file is written as soon as that item's `IndexEntry` is complete, before the next item is processed. |

The in-place write timing is a deliberate design choice preserved from the original: it ensures that partial results survive process interruption. If the indexer is killed mid-traversal, the sidecar files written so far are valid and usable. Stdout and outfile writes, by contrast, happen only after full completion — there is no meaningful partial-output behavior for a single JSON document.

#### File encoding

All output files are written as UTF-8 without a BOM, using `Path.write_text(json_string, encoding="utf-8")`. The original uses `Out-File -Encoding UTF8` on Windows, which also produces UTF-8 (with or without BOM depending on PowerShell version). The port normalizes to UTF-8-no-BOM across all platforms.

---

### 6.10. File Rename and In-Place Write Operations

**Module:** `core/rename.py`
**Operations Catalog:** Category 10
**Original functions:** Rename logic in `MakeDirectoryIndexLogic` / `MakeDirectoryIndexRecursiveLogic`, `Move-Item` calls

#### Purpose

Implements the `StorageName` rename operation: renames files and directories from their original names to their deterministic, hash-based `storage_name` values (§5.8). The rename operation is destructive — the original filename is replaced on disk — but the original name is preserved in the `IndexEntry.name.text` field of the in-place sidecar file that is always written alongside a rename (since the sidecar serves as the manifest for reversal).

#### Public interface

```python
def rename_item(
    original_path: Path,
    entry: IndexEntry,
    *,
    dry_run: bool = False,
) -> Path:
    """Rename a file or directory to its storage_name.

    Returns the new path after renaming. If dry_run=True, returns
    the would-be new path without performing the rename.

    Raises RenameError if the target path already exists and is not
    the same file (collision detection).
    """
```

#### Rename behavior

The rename operation constructs the target path via `paths.build_storage_path(original_path, entry.attributes.storage_name)` and executes `original_path.rename(target_path)`.

`Path.rename()` performs an atomic rename when the source and target are on the same filesystem. For cross-filesystem moves (which should not occur in normal usage — the rename target is always in the same directory), the operation falls back to `shutil.move()`.

#### Collision detection

Before renaming, the module checks whether the target path already exists. If it does, and it is not the same inode as the source (checked via `os.stat()` comparison), a `RenameError` is raised. This prevents data loss from two files that happen to produce the same `storage_name` (which would require an identity hash collision — astronomically unlikely, but the guard is cheap and worth having).

If the target path exists and is the same inode as the source (meaning the file was already renamed in a previous run), the rename is a no-op and the existing path is returned.

#### Rename implies in-place output

When the `--rename` flag is active, the configuration MUST also activate `--inplace` output. The rename module does not write sidecar files itself — that is handled by `serializer.write_inplace()`. The configuration loader enforces the implication: `config.rename = True` → `config.output_inplace = True`. This matches the original's safety behavior (`MakeIndex` forces `OutFileInPlace = $true` when `Rename = $true`).

The sidecar file written alongside each renamed item serves as the reversal manifest: it contains the original filename in `name.text`, allowing a future revert operation to reconstruct the original path.

#### Safety: MetaMergeDelete guard

When MetaMergeDelete is active, the configuration MUST require that at least one output mechanism (`--outfile` or `--inplace`) is enabled. This prevents the scenario where sidecar metadata files are deleted without their content being captured in any output. The original enforces this via the `$MMDSafe` variable; the port enforces it as a configuration validation rule during Stage 1.

If MetaMergeDelete is requested with no output mechanism, the configuration loader raises a fatal error before any processing begins.

#### Dry-run mode

The `dry_run` parameter causes the function to compute and return the target path without performing the actual rename. The serializer still writes the sidecar file (using the would-be new path), and the `IndexEntry` still contains the `storage_name`. Dry-run mode allows users to preview what a rename operation would do before committing to it.

> **Improvement over original:** The original does not support dry-run for renames. The port adds this as a safety feature, particularly useful for users running rename operations on large directory trees for the first time.

#### Revert capability

The original's source comments include a "To-Do" note about adding a `Revert` parameter. The v2 schema's enriched `MetadataEntry` provenance fields (§5.10, principle P3) and the in-place sidecar files provide the data foundation for reversal. A `revert_rename()` function that reads the sidecar's `name.text` field and renames the file back to its original name is a natural post-MVP enhancement. The architecture supports it without structural changes — the sidecar file is the revert manifest.

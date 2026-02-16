# Operations Catalog — MakeIndex Port to Python

> **Purpose:** Categorize all logical operations found in the original MakeIndex function (and its dependency tree) into defined groups, correlate each group to recommended Python modules/libraries, and flag improvements over the original implementation.  
> **Audience:** AI-first, Human-second  
> **Scope:** Covers MakeIndex, its 8 external pslib dependencies (Base64DecodeString, Date2UnixTime, DirectoryId, FileId, MetaFileRead, TempOpen, TempClose, Vbs), 2 external binaries (exiftool, jq), and all internal sub-functions.  
> **Schema Reference:** `MakeIndex_OutputSchema.json` — the `Encoding` key is intentionally excluded from the ported software per project requirements.

---

## How to Read This Document

Each operation category below contains:

- **What It Does:** A summary of the original behavior across MakeIndex and its dependencies.
- **Where It Lives (Original):** The specific functions/sub-functions in the PowerShell source that implement the operation.
- **Python Modules:** The recommended Python standard-library or third-party modules for the ported implementation.
- **Improvement Notes:** Where the original logic was inefficient, fragile, or platform-locked, and how the Python port should diverge.

Categories are ordered by architectural importance (foundational operations first, output/presentation operations last).

---

## Category Index

| #  | Category | Primary Python Modules |
|----|----------|----------------------|
| 1  | Filesystem Traversal & Discovery | `pathlib`, `os` |
| 2  | Path Resolution & Manipulation | `pathlib` |
| 3  | Hashing & Identity Generation | `hashlib` |
| 4  | Symlink Detection | `pathlib` |
| 5  | Filesystem Timestamps & Date Conversion | `datetime` |
| 6  | EXIF / Embedded Metadata Extraction | `subprocess` + `exiftool`, `json` |
| 7  | Sidecar Metadata File Handling | `json`, `re`, `pathlib` |
| 8  | Output Object Construction & Schema | `dataclasses`, `json` |
| 9  | JSON Serialization & Output Routing | `json` (or `orjson`), `pathlib`, `sys` |
| 10 | File Rename & In-Place Write Operations | `pathlib`, `shutil` |
| 11 | Configuration Management | `dataclasses`, `tomllib` (or `pyyaml`) |
| 12 | Logging & Verbosity | `logging` |
| 13 | Progress Reporting | `tqdm` (or `rich`) |
| 14 | CLI Argument Parsing & Entry Point | `click` (or `argparse`) |
| 15 | Temporary File Management | `tempfile` |

---

## 1. Filesystem Traversal & Discovery

### What It Does

Enumerates files and directories within a target path. Supports recursive and non-recursive modes. Filters out system artifacts (`$RECYCLE.BIN`, `System Volume Information`). Separates child items into file and directory lists. Counts items for progress reporting. Handles the three input scenarios: single file, single directory (flat), and directory tree (recursive).

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `MakeDirectoryIndexRecursiveLogic` | Recursive tree walk via `Get-ChildItem -Force -Recurse` combined with self-recursive calls per child directory |
| `MakeDirectoryIndexLogic` | Non-recursive single-directory enumeration via `Get-ChildItem -Force` |
| `MakeFileIndex` | Single-file path; skips traversal entirely, calls `Get-Item` on one file |
| `Where-Object` filters | Excludes `$RECYCLE.BIN` and `System Volume Information` by name match |
| `[System.Collections.ArrayList]` | Combines file and directory child arrays into a single ordered collection |

### Python Modules

| Module | Usage |
|--------|-------|
| `pathlib.Path.iterdir()` | Non-recursive directory listing |
| `pathlib.Path.rglob('*')` | Recursive traversal (replaces `Get-ChildItem -Recurse`) |
| `os.scandir()` | High-performance directory iteration when `pathlib` overhead matters (large trees) |
| `pathlib.Path.is_file()` / `.is_dir()` | Item type classification (replaces `Where-Object` separation) |

### Improvement Notes

The original uses two entirely separate code paths for recursive vs. non-recursive traversal (`MakeDirectoryIndexRecursiveLogic` which calls itself, vs. `MakeDirectoryIndexLogic`). This created near-complete code duplication. The Python port should use a single traversal function parameterized by a `recursive: bool` flag. When `recursive=True`, use `Path.rglob('*')` or `os.walk()`. When `recursive=False`, use `Path.iterdir()`. Both paths feed into the same object-construction pipeline.

The original manually assembles an `ArrayList` from two separate `Get-ChildItem` calls (one for files, one for directories). Python's `os.scandir()` returns `DirEntry` objects that already expose `.is_file()` and `.is_dir()` without additional stat calls, making the separation trivially cheap in a single pass.

The hardcoded exclusion of `$RECYCLE.BIN` and `System Volume Information` is Windows-specific. The port should externalize the exclusion list into configuration (see Category 11) and default to a cross-platform set that also covers `.DS_Store`, `.Spotlight-V100`, `.Trashes`, and similar platform artifacts.

---

## 2. Path Resolution & Manipulation

### What It Does

Resolves relative, hypothetical, or symbolic paths into absolute canonical forms. Extracts parent directories, basenames, extensions, and filenames from path strings. Constructs new paths for renamed files and sidecar metadata outputs. Validates extension strings against a regex pattern to reject malformed or suspiciously long extensions.

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `ResolvePath` | Resolves real paths via `Resolve-Path`; falls back to `[System.IO.Path]::GetFullPath()` for hypothetical (non-existent) paths |
| `GetParentPath` | Extracts parent directory via `Split-Path` |
| `MakeObject` | Extracts extension, basename, filename via `[System.IO.Path]` methods; validates extension with regex `^(([a-z0-9]){1,2}\|([a-z0-9]){1}([a-z0-9\-]){1,12}([a-z0-9]){1})$` |
| `FileId-ResolvePath` / `DirectoryId-ResolvePath` | Redundant copies of the same resolve logic inside FileId and DirectoryId |
| `$Sep` (global) | `[System.IO.Path]::DirectorySeparatorChar` used for manual string concatenation of paths |

### Python Modules

| Module | Usage |
|--------|-------|
| `pathlib.Path.resolve()` | Canonical absolute path resolution (replaces `Resolve-Path` + `GetFullPath` fallback) |
| `pathlib.Path.parent` | Parent directory extraction (replaces `Split-Path` and `GetParentPath`) |
| `pathlib.Path.name` / `.stem` / `.suffix` | Filename, basename, and extension extraction (replaces all `[System.IO.Path]` calls) |
| `pathlib.PurePosixPath` / `PureWindowsPath` | Cross-platform path construction without touching the filesystem |

### Improvement Notes

The original has three independent copies of the "resolve path" logic: `ResolvePath` in MakeIndex, `FileId-ResolvePath` in FileId, and `DirectoryId-ResolvePath` in DirectoryId. All three do the same thing. The Python port should have exactly one path resolution utility.

The original constructs paths by string-concatenating components with `$Sep` as a manual separator character. This is brittle and unnecessary. `pathlib` operator overloading (`parent / filename`) handles path construction correctly across platforms with no separator management.

The extension validation regex in the original rejects extensions longer than 14 characters or those containing non-alphanumeric characters (beyond hyphens). This is reasonable but should be made configurable rather than hardcoded, as some legitimate extensions (e.g., `.numbers`, `.download`) may be affected.

---

## 3. Hashing & Identity Generation

### What It Does

Computes cryptographic hashes of file contents and name strings to produce deterministic unique identifiers. Files get content-based IDs (prefixed `y`); directories get name-based IDs computed from a two-layer scheme: `hash( hash(dirName) + hash(parentDirName) )` (prefixed `x`). Handles null/empty inputs with known null-hash constants. Handles symlinks by falling back to name hashing instead of content hashing.

The original only computes MD5 and SHA256 at runtime, despite the output schema defining fields for SHA1 and SHA512 as well.

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `FileId` + 8 nested hash sub-functions | File content hashing (MD5, SHA1, SHA256, SHA512) via `[System.Security.Cryptography.*]::Create()` + `[System.IO.File]::OpenRead()` stream hashing; name string hashing via same algorithms on UTF-8 byte encoding |
| `DirectoryId` + 8 nested hash sub-functions | Directory name hashing using the two-layer `hash(hash(name) + hash(parentName))` scheme |
| `ReadMetaFile-GetNameHashMD5` / `ReadMetaFile-GetNameHashSHA256` | Yet more copies of string hashing logic, duplicated inside `ReadMetaFile` |
| `MetaFileRead-Sha256-File` / `MetaFileRead-Sha256-String` | Even more copies inside `MetaFileRead` itself |
| Null-hash constants | Hardcoded per-algorithm empty-string hash values for edge cases |

### Python Modules

| Module | Usage |
|--------|-------|
| `hashlib` | All hash computation: `hashlib.md5()`, `hashlib.sha1()`, `hashlib.sha256()`, `hashlib.sha512()` — supports both file stream hashing (via `.update()` in chunks) and string hashing (via `.update(s.encode('utf-8'))`) |
| `hashlib.file_digest()` | Python 3.11+ convenience function for hashing file contents directly from a file object; ideal for the file content hashing path |

### Improvement Notes

**Critical code duplication problem.** The original has no fewer than four separate locations where hashing logic is independently implemented: `FileId`, `DirectoryId`, `ReadMetaFile` sub-functions, and `MetaFileRead` sub-functions. Each reimplements the same `Create() → ComputeHash() → ToString() → replace('-','')` pattern. The Python port should provide exactly one hashing utility module exposing functions like `hash_file(path, algorithm) -> str` and `hash_string(value, algorithm) -> str`, called from everywhere.

**Expand runtime hash coverage.** The original only computes MD5 and SHA256 at runtime, but the output schema defines SHA1 and SHA512 fields. Since `hashlib` can compute all four algorithms in a single file read pass (feeding the same byte chunks to four hash objects simultaneously), the Python port should compute all four by default with near-zero marginal cost. This fills the previously-empty schema fields and enables downstream consumers to select their preferred algorithm.

**Chunked file reading.** The original opens the entire file stream and calls `ComputeHash()` on it in one pass. For very large files this is fine at the .NET level (it streams internally), but the Python port should be explicit about chunked reads (e.g., 8 KB or 64 KB chunks fed to `hashlib.update()`) to keep memory usage bounded and to enable multi-algorithm hashing in a single pass.

**The `x`/`y` prefix convention** for directory vs. file IDs is a design choice carried forward from the original. It should be preserved for backward compatibility with the output schema.

**Null-hash constants** should not be hardcoded. Instead, the Python port can compute them once at module load time: `hashlib.md5(b'').hexdigest().upper()`, etc. This is self-documenting and eliminates the risk of copy-paste errors in long hex strings.

---

## 4. Symlink Detection

### What It Does

Determines whether a file or directory is a symbolic link (reparse point). When a file is a symlink, the identity system falls back to hashing the file's name string rather than its content (because the link target may not be accessible). The `IsLink` boolean is included in the output schema.

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `FileId` | Checks `(Get-Item).Attributes -band [System.IO.FileAttributes]::ReparsePoint` |
| `DirectoryId` | Same reparse point check for directories |
| `ValidateIsLink` | Listed as a dependency but never directly called; `FileId` and `DirectoryId` perform the check inline |
| `MakeObject` | Reads `.IsLink` from the `FileId`/`DirectoryId` return object; skips encoding detection and exiftool for symlinks |

### Python Modules

| Module | Usage |
|--------|-------|
| `pathlib.Path.is_symlink()` | Single cross-platform call; returns `True` for both file and directory symlinks |
| `os.path.islink()` | Alternative for string-path interfaces |

### Improvement Notes

The original checks for the `ReparsePoint` attribute, which is a Windows-specific concept that covers symlinks but also covers junction points and other reparse point types. `pathlib.Path.is_symlink()` is the correct cross-platform equivalent. On Windows it still detects reparse points; on Linux/macOS it detects POSIX symlinks. This is a strict improvement in portability.

The `ValidateIsLink` function listed in the original docstring but never called is dead code. It should not be carried forward.

---

## 5. Filesystem Timestamps & Date Conversion

### What It Does

Reads filesystem timestamps (created, modified, accessed) from file/directory stat data. Formats them as ISO 8601 strings with timezone offset (format: `yyyy-MM-ddTHH:mm:ss.fffffffzzz`). Converts those formatted strings to Unix timestamps (milliseconds since epoch) via the external `Date2UnixTime` function.

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `MakeObject` | Reads `.LastAccessTime`, `.CreationTime`, `.LastWriteTime` from `Get-Item`; formats via `.ToString($DateFormat)` |
| `Date2UnixTime` (external pslib) | Parses formatted date strings back into `[DateTimeOffset]` objects and calls `.ToUnixTimeMilliseconds()` |

### Python Modules

| Module | Usage |
|--------|-------|
| `datetime.datetime` | Timestamp formatting via `.isoformat()` or `.strftime()` |
| `datetime.datetime.timestamp()` | Direct conversion to Unix epoch seconds (multiply by 1000 for milliseconds) |
| `os.stat_result` / `pathlib.Path.stat()` | Reading `st_mtime`, `st_atime`, `st_ctime` (or `st_birthtime` on macOS) |

### Improvement Notes

**The original performs an unnecessary round-trip.** It formats a datetime to a string, then passes that string to `Date2UnixTime` which parses it back into a datetime object just to call `.ToUnixTimeMilliseconds()`. The Python port should extract the Unix timestamp directly from the stat result's float value: `int(stat_result.st_mtime * 1000)`. The formatted ISO string can be produced separately from the same source datetime. No round-trip parsing needed.

**Creation time portability.** Windows provides a true creation time (`CreationTime`). Linux typically does not expose birth time in `os.stat()` unless the filesystem and kernel support `st_birthtime` (available on some systems via `os.stat_result.st_birthtime`). The port should attempt `st_birthtime` and fall back to `st_ctime` (metadata change time on Linux) with a documented caveat. This is a platform reality, not a bug.

**The date format string** `yyyy-MM-ddTHH:mm:ss.fffffffzzz` uses .NET formatting tokens. The Python equivalent is `%Y-%m-%dT%H:%M:%S.%f%z`, noting that Python's `%f` gives microseconds (6 digits) rather than .NET's 7-digit fractional seconds. For backward compatibility, the port should zero-pad to 7 digits if exact schema match is required, or accept the 6-digit microsecond precision as a minor, acceptable deviation.

---

## 6. EXIF / Embedded Metadata Extraction

### What It Does

Invokes the `exiftool` binary against individual files to extract embedded EXIF/XMP/IPTC metadata. The exiftool arguments are Base64-encoded in the source and decoded at runtime, written to a temporary argument file, and passed to exiftool via its `-@` (argfile) switch. The raw JSON output from exiftool is piped through `jq` to compact it and strip unwanted system keys (ExifToolVersion, FileName, FilePath, Directory, FilePermissions, etc.). Certain file types (`.csv`, `.htm`, `.html`, `.json`, `.tsv`, `.xml`) are excluded because exiftool tends to dump their entire content into the metadata output.

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `GetFileExif` | Orchestrator: decodes args, manages temp file lifecycle, calls runner |
| `GetFileExifArgsWrite` | Decodes Base64 argument strings via `Base64DecodeString`, writes them to a temp file via `Add-Content` |
| `GetFileExifRun` | Executes `exiftool -@ $ArgsFile` and pipes output through `jq -c '.[] \| .'` then a second `jq` pass to delete unwanted keys |
| `Base64DecodeString` (external pslib) | URL-decodes and Base64-decodes the argument strings with UTF-8 encoding support |
| `TempOpen` / `TempClose` (external pslib) | Creates and deletes the temporary argument file |

### Python Modules

| Module | Usage |
|--------|-------|
| `subprocess.run()` | Invoking `exiftool` with arguments passed directly (no temp file needed) |
| `json` | Parsing exiftool's `-json` output directly (replaces `jq` entirely) |
| `PyExifTool` (third-party, optional) | A Python wrapper around exiftool that manages a persistent exiftool process for batch operations; significantly faster for large directory trees |

### Improvement Notes

**Eliminate jq dependency entirely.** The original pipes exiftool output through `jq` for two purposes: JSON compaction and key deletion. Python's `json.loads()` handles the parsing natively, and unwanted keys can be removed with a simple dict comprehension: `{k: v for k, v in data.items() if k not in EXCLUDED_KEYS}`. This eliminates a binary dependency with zero functionality loss.

**Eliminate the Base64 argument encoding scheme.** The original stores exiftool arguments as Base64-encoded strings and decodes them at runtime via `Base64DecodeString` (which itself has a complex OpsCode-based branching pattern and calls `certutil` on Windows). This appears to have been a mechanism for safely embedding complex argument strings in the PowerShell source. In Python, we can simply define the arguments as a list of strings and pass them directly to `subprocess.run()`. This eliminates the entire `Base64DecodeString` → `TempOpen` → write-args → `TempClose` pipeline.

**Eliminate the temporary argument file.** The original writes decoded arguments to a temp `.txt` file and passes it to exiftool via `-@`. The Python port should pass arguments directly via `subprocess.run(['exiftool', ...args, filepath])`. If argument lists are very long, `subprocess` handles them correctly on all platforms.

**Consider PyExifTool for batch mode.** When indexing large directory trees, the original invokes `exiftool` once per file (a separate process spawn each time). `PyExifTool` keeps a single exiftool process alive and communicates with it via stdin/stdout, which is dramatically faster for batch operations. The port should support both modes: direct `subprocess` invocation for single-file use, and `PyExifTool` batch mode for directory traversal.

**The extension exclusion list** (`.csv`, `.htm`, `.html`, `.json`, `.tsv`, `.xml`) should be externalized into configuration (see Category 11) rather than hardcoded, so users can customize it.

---

## 7. Sidecar Metadata File Handling

### What It Does

Discovers, reads, parses, and optionally merges external metadata "sidecar" files that live alongside the files they describe. Sidecar files are identified by regex patterns matching known suffixes (defined in `$global:MetadataFileParser`). Each sidecar file undergoes type detection (matching against the `Identify` configuration), format-specific reading (JSON, plain text, binary/Base64, subtitles, hash files, URL/LNK shortcuts), and construction of a metadata entry object with source attribution, type, name, name hashes, and data payload. When `MetaMerge` is active, sidecar metadata is folded into the parent item's `Metadata` array. When `MetaMergeDelete` is active, merged sidecar files are queued for deletion after processing.

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `GetFileMetaSiblings` | Scans the parent directory for files matching the target basename + known metadata suffixes; uses regex with `[System.Text.RegularExpressions.Regex]::Escape()` for basename escaping |
| `ReadMetaFile` | Wrapper: calls `MetaFileRead`, adds name hashes, constructs standardized metadata entry objects |
| `MetaFileRead` (external pslib) | The actual parser: type detection, format-specific readers (`ReadJson`, `ReadText`, `ReadBinary`, `ReadText-Hash`, `ReadText-Subtitles`, `ReadLink`), parent file resolution, SHA256 hashing |
| `ReadMetaFile-GetNameHashMD5` / `-SHA256` | Hash the sidecar filename for the `NameHashes` field |
| `$global:MetadataFileParser` | Configuration object defining suffix patterns, exclusion patterns, and type identification rules |
| `$global:DeleteQueue` | Runtime accumulator for sidecar file paths to delete when `MetaMergeDelete` is active |

### Python Modules

| Module | Usage |
|--------|-------|
| `re` | Regex pattern matching for sidecar file identification and type detection |
| `json` | Reading JSON-format sidecar files (replaces `jq -c '.'` piped through `ConvertFrom-Json`) |
| `pathlib` | Directory scanning for sibling files, basename extraction, suffix matching |
| `hashlib` | Name hashing for sidecar files (shared with Category 3) |
| `base64` | Reading binary sidecar files as Base64-encoded data (replaces `certutil -encode`) |

### Improvement Notes

**Eliminate certutil dependency.** The original uses `certutil -encode` to convert binary sidecar file data to Base64 strings. Python's `base64.b64encode()` does this natively and portably.

**Simplify type detection.** The original iterates through all keys in `$MetadataFileParser.Identify` and matches each file against regex pattern arrays. This is fine algorithmically but the Python port should express this as a clean mapping structure (a dict of `{type_name: [compiled_regex_patterns]}`) rather than the deeply nested ordered hashtable structure of the original.

**The DeleteQueue pattern** (accumulate paths during traversal, delete after completion) is sound and should be preserved. In Python this is simply a `list[Path]` built up during traversal and iterated at the end with `Path.unlink()`.

---

## 8. Output Object Construction & Schema

### What It Does

Assembles a structured data object (the "index entry") for every file and directory processed. Each entry contains identity fields (`_id`, `Ids`, `NameHashes`, `ContentHashes`), filesystem metadata (`Name`, `BaseName`, `Extension`, `StorageName`, `Size`, `IsDirectory`, `IsLink`), relationship fields (`ParentId`, `ParentIds`, `ParentName`, `ParentNameHashes`), timestamps (`TimeAccessed/Created/Modified`, `UnixTimeAccessed/Created/Modified`), child items (`Items` array for directories), and extracted metadata (`Metadata` array).

The original output schema also includes an `Encoding` key (a complex object describing file encoding properties from BOM detection). **This key is being intentionally dropped from the ported software.**

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `MakeObject` | The core builder. Contains a massive `switch` on `$ObjectType` (`makeobjectfile`, `makeobjectdirectory`, `makeobjectdirectoryrecursive`) that constructs `[PSCustomObject]@{...}` with all schema fields. Repeated near-identically across 5+ switch branches. |
| `VariableStringify` | Null-safe string conversion used before inserting values into the output object |
| `GetFileEncoding` | BOM byte inspection for the `Encoding` field (being dropped) |

### Python Modules

| Module | Usage |
|--------|-------|
| `dataclasses` | Define the output schema as `@dataclass` classes with type annotations; provides `asdict()` for JSON serialization. Strongly preferred for a project of this scope. |
| `pydantic` (third-party, optional) | Alternative to dataclasses with built-in validation, JSON schema generation, and serialization. More powerful but heavier dependency. Worth considering if schema validation against legacy consumers is important. |
| `typing` | Type annotations for nullable fields, union types, and recursive structures (`Items` referencing the same schema) |

### Improvement Notes

**Eliminate the ObjectType switch duplication.** The original `MakeObject` constructs the output object inside a `switch` statement with 5+ branches (`makeobjectfile`, `makeobjectdirectory`, `makeobjectdirectoryrecursive`, plus `default` branches). The actual fields are nearly identical across all branches — the only differences are: directories get `Items = @()` while files do not, and recursive directories get `Items = @()` for later population. The Python port should define one `IndexEntry` dataclass and conditionally populate `Items` and `Metadata` based on item type. One class, one construction path.

**Drop the `Encoding` key.** As specified. The `GetFileEncoding` sub-function (BOM byte inspection) and all `$IEncoding` variable assignments are omitted from the port. For backward compatibility, the output schema can include `"Encoding": null` for all items if legacy consumers expect the field to exist. Alternatively, omit it entirely and let legacy consumers handle the missing key. This is a project decision to be made when we address backward compatibility testing.

**Typed schema definition.** The original `[PSCustomObject]@{...}` has no compile-time type checking. Using Python `dataclasses` gives us type annotations, IDE support, and `dataclasses.asdict()` for clean JSON serialization. A rough sketch of the core structure:

```
IndexEntry:
    _id: str
    Ids: HashIds            # {MD5: str, SHA256: str, ...}
    Name: str
    NameHashes: HashIds | None
    ContentHashes: HashIds | None
    Extension: str | None
    BaseName: str
    StorageName: str
    Size: int
    IsDirectory: bool
    IsLink: bool
    ParentId: str | None
    ParentIds: HashIds | None
    ParentName: str | None
    ParentNameHashes: HashIds | None
    UnixTimeAccessed: int
    UnixTimeCreated: int
    UnixTimeModified: int
    TimeAccessed: str
    TimeCreated: str
    TimeModified: str
    Items: list[IndexEntry] | None   # Recursive reference; None for files
    Metadata: list[MetadataEntry] | None
```

This sketch is illustrative. The actual implementation should be derived from the output schema JSON with adjustments for the dropped `Encoding` key and expanded hash fields.

---

## 9. JSON Serialization & Output Routing

### What It Does

Converts the assembled index tree into JSON format and routes it to one or more output destinations. The original supports 7 distinct output scenarios combining three flags: `StandardOutput` (write to stdout), `OutFile` (write to a single aggregate file), and `OutFileInPlace` (write individual `_meta.json` sidecar files alongside each processed item). The `ConvertTo-Json -Depth 100` cmdlet is used for serialization, with a documented known issue: extremely large output trees can cause out-of-memory errors.

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `MakeIndex` (top-level output logic) | The 7-scenario routing switch at the end of the function; calls `ConvertTo-Json -Depth 100` and `Out-File -Encoding UTF8` or writes to stdout |
| `MakeDirectoryIndexLogic` / `MakeDirectoryIndexRecursiveLogic` | In-place sidecar writing via `ConvertTo-Json -Depth 100 \| Set-Content -LiteralPath $FileMetaPath` |

### Python Modules

| Module | Usage |
|--------|-------|
| `json` | Standard library JSON serialization via `json.dumps()` with `indent` and `ensure_ascii=False` for UTF-8 output |
| `orjson` (third-party, optional) | Significantly faster JSON serialization for large trees; outputs bytes directly; handles `dataclasses` natively |
| `sys.stdout` | Standard output routing |
| `pathlib.Path.write_text()` | Writing JSON to output files and in-place sidecar files |

### Improvement Notes

**The ConvertTo-Json memory problem does not exist in Python.** Python's `json.dumps()` handles arbitrarily large nested structures without the memory ceiling that plagues PowerShell's `ConvertTo-Json`. If performance is a concern for very large trees (hundreds of thousands of items), `orjson` is a drop-in replacement that serializes 5-10x faster and produces bytes directly. The note in the original docstring about "good luck, take it up with Microsoft" can be retired.

**Simplify the output routing model.** The original's 7-scenario matrix is confusing. The Python port should express this as three independent boolean flags that compose naturally: `--stdout`, `--outfile PATH`, `--inplace`. Any combination is valid. The routing logic becomes a simple loop over enabled destinations after the index tree is built (or during traversal for in-place writes).

**Streaming in-place writes.** For in-place mode, the original writes each sidecar file as it processes items within the traversal loop. This is correct and should be preserved — it means partial results are available even if the process is interrupted. The aggregate output file and stdout writes happen after traversal completes, which is also correct.

---

## 10. File Rename & In-Place Write Operations

### What It Does

When the `Rename` flag is active, processed files are renamed from their original name to their hash-based `StorageName` (format: `<_id>.<extension>`). The original file is destroyed and replaced with the renamed version. A sidecar `_meta.json` file is written alongside each renamed file. Directory items get `_directorymeta.json` sidecar files. The `Rename` flag implies `OutFileInPlace`.

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `MakeDirectoryIndexLogic` / `MakeDirectoryIndexRecursiveLogic` | Contains the rename-or-not branching logic using `Move-Item -LiteralPath -Destination -Force` for renames and `Set-Content -LiteralPath -Force` for sidecar writes |
| `MakeIndex` (parameter validation) | Forces `OutFileInPlace = $true` when `Rename = $true` (safety measure) |

### Python Modules

| Module | Usage |
|--------|-------|
| `pathlib.Path.rename()` | Atomic file rename (same filesystem) |
| `shutil.move()` | Cross-filesystem move if needed (fallback) |
| `pathlib.Path.write_text()` | Writing sidecar `_meta.json` files |

### Improvement Notes

**The rename operation is destructive and irreversible** in the original. The original docstring includes a "To-Do" note about adding a `Revert` parameter. The Python port should consider implementing revert capability from the start, since the in-place sidecar files contain the original filename in the `Name` field and can serve as the revert manifest.

**Safety: MetaMergeDelete guard.** The original has a `$MMDSafe` variable that prevents `MetaMergeDelete` from activating unless an output mechanism (`OutFile` or `OutFileInPlace`) is specified, protecting against accidental metadata file deletion when no output is being captured. This safety logic should be preserved.

---

## 11. Configuration Management

### What It Does

Loads and provides access to the parser configuration that governs metadata file behavior: which file suffixes are recognized as sidecar files, which types they map to, which file extensions are excluded from exiftool processing, and the regex patterns used for identification. The original stores this in a large `[ordered]@{}` hashtable (`$global:MetadataFileParser`) defined at the script level and promoted to global scope for access by deeply nested sub-functions.

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `$global:MetadataFileParser` (script-level variable, line ~16977) | The master configuration object containing `.Exiftool.Exclude`, `.Indexer.Include/Exclude/IncludeString/ExcludeString`, `.Identify.<Key>` sub-objects |
| `MakeIndex` (parameter block) | Copies sub-properties from `$MetadataFileParser` into global variables (`$global:ExiftoolRejectList`, `$global:MetaSuffixInclude`, etc.) at function start; cleans them up via `Remove-Variable` at function end |

### Python Modules

| Module | Usage |
|--------|-------|
| `dataclasses` | Define configuration as typed `@dataclass` objects that can be validated at load time |
| `tomllib` (Python 3.11+ stdlib) | Load configuration from a TOML file; human-readable, well-suited for this kind of structured config |
| `pyyaml` (third-party, optional) | Alternative config format if TOML is insufficient |
| `json` | Alternative config format; the least human-friendly but the most schema-compatible |

### Improvement Notes

**Eliminate global variable promotion entirely.** The original promotes configuration values to `$global:` scope because PowerShell's nested function scoping makes it difficult to pass data into deeply nested sub-functions cleanly. Python has no such limitation. The configuration object should be instantiated once and passed through the call chain via function parameters, or held on a class instance if using an OOP architecture. No global state needed.

**Externalize the configuration to a file.** The original hardcodes the configuration in the script source. The Python port should load it from an external file (TOML recommended) that ships alongside the tool as a default but can be overridden by the user. This makes the extension exclusion lists, sidecar suffix patterns, and type identification rules user-customizable without modifying source code.

**Provide sensible defaults.** The port should include a built-in default configuration that matches the original's behavior, so the tool works out of the box without requiring a config file. The external config file should only be needed for customization.

---

## 12. Logging & Verbosity

### What It Does

Provides structured log output with severity levels (info, debug, warning, error, critical, success), caller identification via a colon-delimited call stack string, session IDs, colorized console output, and persistent log file writing. The `Vbs` function is the single most widely-called function in the entire pslib library — virtually every other function routes its output through it.

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `Vbs` (external pslib) | The terminal logging endpoint. Accepts `Caller`, `Status`, `Message`, `Verbosity`, `LogDir`, `LibName`, `VbsSessionID`. Writes to log files and optionally to colorized console output. |
| `UpdateFunctionStack` | Maintains the colon-delimited call-stack string (e.g., `"MakeIndex:MakeObject:GetFileExif"`) for the `Caller` parameter |
| `VbsFormatter` (inside MetaFileRead) | Wrapper that prepends a progress string to messages before passing them to `Vbs` |
| `$LibSessionID` / `$D_PSLIB_LOGS` (global variables) | Session identifier (GUID) and log directory path |

### Python Modules

| Module | Usage |
|--------|-------|
| `logging` | Python's standard logging framework. Supports named loggers (replacing the manual call-stack string), severity levels, file handlers, console handlers with formatting, and session-scoped context via `LogRecord` attributes or `logging.LoggerAdapter`. |
| `rich` (third-party, optional) | Colorized console output, progress bars, and structured logging. If the port wants to replicate the colorized console output of `Vbs`, `rich.logging.RichHandler` is an excellent drop-in handler. |

### Improvement Notes

**Eliminate `UpdateFunctionStack` entirely.** The original manually builds a colon-delimited string (`"MakeIndex:MakeObject:GetFileExif"`) and passes it through every function call. Python's `logging` module automatically captures the call location via `%(funcName)s`, `%(module)s`, and `%(pathname)s` format tokens. For hierarchical logger names, the port should use Python's dotted-name logger convention (e.g., `logging.getLogger('indexer.make_object.get_file_exif')`). This gives the same traceability with zero manual bookkeeping.

**Replace the `Verbosity` boolean with standard log levels.** The original has a binary verbosity toggle (`$true` / `$false`) that gates console output. Python's `logging` already supports `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` levels, controlled by configuring the handler's level. The CLI can expose `--verbose` / `--debug` / `--quiet` flags that map to log levels.

**Session IDs** are useful for correlating log entries across a single run. The Python port should generate one via `uuid.uuid4().hex` at startup and inject it into all log records using a `logging.Filter` or `LoggerAdapter`.

---

## 13. Progress Reporting

### What It Does

Tracks and reports processing progress during directory traversal: counts total items, computes percentage complete, measures elapsed time, and formats progress strings for log messages.

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `MakeDirectoryIndexLogic` / `MakeDirectoryIndexRecursiveLogic` | Maintains counters (`$ChildrenCountProcessed`, `$ChildrenCountTotal`), computes `[math]::Round()` percentage, formats progress strings like `"[42/100 (42%)]"` |
| `MakeIndex` (top-level) | Captures `$TimeStart` at the beginning, computes elapsed time at end using `(Get-Date) - $TimeStart` formatted as `H:M:S.ms` |

### Python Modules

| Module | Usage |
|--------|-------|
| `tqdm` (third-party) | Progress bars for iterables. Clean, minimal, widely used. Wrap the item iterator in `tqdm(items)` and progress reporting is automatic. |
| `rich.progress` (third-party, optional) | More visually sophisticated progress bars with elapsed time, ETA, and transfer rate. Pairs naturally with `rich` logging (see Category 12). |
| `time.perf_counter()` | High-resolution elapsed time measurement (replaces `Get-Date` arithmetic) |

### Improvement Notes

The original manually formats progress strings and injects them into log messages, creating tight coupling between progress tracking and logging. The Python port should separate these concerns: use a progress bar library (`tqdm` or `rich`) for user-facing progress display, and use the logging system for structured log output. They can coexist cleanly — `tqdm` even has a `tqdm.write()` method for printing messages without disrupting the progress bar, and `rich` integrates both natively.

---

## 14. CLI Argument Parsing & Entry Point

### What It Does

Accepts user input specifying the target path, output mode, recursion behavior, metadata options, rename flag, ID type, and verbosity level. Validates input combinations (e.g., `File` and `Directory` are mutually exclusive; `Rename` implies `OutFileInPlace`). Routes execution to the appropriate traversal entry point based on the resolved target type (file, directory flat, directory recursive).

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `MakeIndex` (Param block) | Declares 14 parameters with aliases, types, defaults, and switch behaviors |
| `MakeIndex` (validation and routing logic) | ~200 lines of input validation, mutual exclusion checks, output scenario determination, and `TargetTyp` (0/1/2) routing |

### Python Modules

| Module | Usage |
|--------|-------|
| `click` (third-party) | Decorator-based CLI framework. Clean syntax for defining commands, options, arguments, and mutual exclusions. Recommended for new Python CLI tools. |
| `argparse` (stdlib) | Standard library alternative. More verbose but zero dependencies. |

### Improvement Notes

The original's parameter validation contains a significant amount of defensive logic to handle conflicting flags (e.g., `Recursive` with `File`, `StandardOutput` with `NoStandardOutput`). `click` handles mutual exclusions declaratively, reducing the validation boilerplate. The original's 7 output scenarios can be expressed as three independent `--stdout` / `--outfile` / `--inplace` boolean flags with natural composition rules.

The `IdType` parameter (selecting MD5 vs. SHA256 as the `_id` field source) should be preserved for backward compatibility. However, since the port will compute all four hash algorithms (see Category 3), this becomes a presentation choice rather than a computation toggle.

---

## 15. Temporary File Management

### What It Does

Creates and deletes temporary files used as intermediaries during exiftool argument passing and Base64 encoding operations. Temp files use UUID-based naming in a dedicated temp directory.

### Where It Lives (Original)

| Function | Role |
|----------|------|
| `TempOpen` (external pslib) | Creates a temp file using UUID+timestamp naming in `$D_PSLIB_TEMP`; supports type suffixes |
| `TempClose` (external pslib) | Deletes a temp file by path with error suppression |
| `MetaFileRead-Temp-Open` / `MetaFileRead-Temp-Close` | Duplicated temp file logic inside `MetaFileRead` |

### Python Modules

| Module | Usage |
|--------|-------|
| `tempfile` | `tempfile.NamedTemporaryFile()` or `tempfile.mkstemp()` for creating temp files with automatic cleanup. Context manager support ensures cleanup even on exceptions. |

### Improvement Notes

**This category may be largely unnecessary in the Python port.** The primary consumers of temp files in the original are (a) exiftool argument passing (eliminated by passing args directly to `subprocess`) and (b) `certutil` Base64 encoding (eliminated by using `base64.b64encode()`). If no operations remain that require temp files, this entire category can be dropped. If temp files are needed for any future operation, `tempfile.NamedTemporaryFile(delete=True)` with a context manager provides automatic cleanup that is strictly superior to the manual `TempOpen`/`TempClose` pattern.

---

## Eliminated Dependencies Summary

The following original dependencies are **not carried forward** into the Python port because their functionality is absorbed by Python's standard library or rendered unnecessary by architectural improvements:

| Original Dependency | Reason for Elimination | Replaced By |
|---------------------|----------------------|-------------|
| `jq` (binary) | JSON parsing and filtering done natively | `json` stdlib |
| `certutil` (binary) | Base64 encoding done natively | `base64` stdlib |
| `Base64DecodeString` (pslib function) | Exiftool args passed directly; no encoding round-trip needed | Direct argument lists |
| `TempOpen` / `TempClose` (pslib functions) | No temp files needed for arg passing or Base64 ops | `tempfile` (if needed at all) |
| `Date2UnixTime` (pslib function) | Timestamp conversion done directly from stat results | `datetime` stdlib |
| `Vbs` (pslib function) | Replaced by Python's logging framework | `logging` stdlib |
| `ValidateIsLink` (pslib function) | Never actually called in the original; dead code | (removed) |
| `GetFileEncoding` (internal sub-function) | `Encoding` key dropped from output schema | (removed) |
| `UpdateFunctionStack` (internal sub-function) | Manual call-stack tracking replaced by logging's built-in caller info | `logging` stdlib |
| `VariableStringify` (internal sub-function) | Python's native `str()` and `None` handling cover this | Built-in `str()` / `repr()` |

---

## Cross-Reference: Output Schema Fields → Operation Categories

This table maps every field in the output schema to the operation category that produces it, confirming full coverage.

| Schema Field | Category | Notes |
|---|---|---|
| `_id` | 3 (Hashing) | Selected from `Ids` based on `IdType` parameter |
| `Ids` | 3 (Hashing) | `{MD5, SHA1, SHA256, SHA512}` — expanded from original's MD5+SHA256 only |
| `Name` | 2 (Path Manipulation) | `Path.name` |
| `NameHashes` | 3 (Hashing) | Hash of the `Name` string |
| `ContentHashes` | 3 (Hashing) | Hash of file contents; `null` for directories |
| `Extension` | 2 (Path Manipulation) | `Path.suffix` with validation |
| `BaseName` | 2 (Path Manipulation) | `Path.stem` |
| `StorageName` | 3 (Hashing) + 2 (Path) | `f"{_id}{extension}"` for files; `_id` for directories |
| ~~`Encoding`~~ | ~~(Dropped)~~ | **Intentionally omitted from port** |
| `Size` | 1 (Traversal) | `Path.stat().st_size` for files; sum of children for directories |
| `IsDirectory` | 1 (Traversal) | `Path.is_dir()` |
| `IsLink` | 4 (Symlink) | `Path.is_symlink()` |
| `ParentId` | 3 (Hashing) | Directory ID of parent |
| `ParentIds` | 3 (Hashing) | Hash IDs of parent directory |
| `ParentName` | 2 (Path Manipulation) | `Path.parent.name` |
| `ParentNameHashes` | 3 (Hashing) | Hash of parent directory name |
| `UnixTimeAccessed` | 5 (Timestamps) | `int(stat.st_atime * 1000)` |
| `UnixTimeCreated` | 5 (Timestamps) | `int(stat.st_birthtime * 1000)` or `st_ctime` fallback |
| `UnixTimeModified` | 5 (Timestamps) | `int(stat.st_mtime * 1000)` |
| `TimeAccessed` | 5 (Timestamps) | ISO 8601 formatted string |
| `TimeCreated` | 5 (Timestamps) | ISO 8601 formatted string |
| `TimeModified` | 5 (Timestamps) | ISO 8601 formatted string |
| `Items` | 1 (Traversal) + 8 (Object Construction) | Recursive child entries for directories; `null` for files |
| `Metadata` | 6 (EXIF) + 7 (Sidecar) | Array of metadata entries from exiftool and sidecar files |

---

## Minimum Viable Dependency Set

For a Python port that achieves full feature parity (minus the intentionally dropped `Encoding` key) with the original MakeIndex:

### Required (Standard Library Only)

| Module | Categories Served |
|--------|------------------|
| `pathlib` | 1, 2, 4, 7, 9, 10 |
| `hashlib` | 3 |
| `datetime` | 5 |
| `json` | 6, 7, 8, 9 |
| `subprocess` | 6 |
| `re` | 7, 11 |
| `logging` | 12 |
| `os` | 1, 5 |
| `sys` | 9 |
| `tempfile` | 15 (if needed) |
| `base64` | 7 |
| `dataclasses` | 8, 11 |
| `typing` | 8 |
| `tomllib` | 11 (Python 3.11+) |
| `uuid` | 12 |
| `time` | 13 |

### Required (External)

| Module | Categories Served | Notes |
|--------|------------------|-------|
| `exiftool` (binary) | 6 | Must be in system PATH; the only external binary dependency |

### Recommended (Third-Party, Optional)

| Module | Categories Served | Justification |
|--------|------------------|---------------|
| `click` | 14 | Cleaner CLI definition than `argparse`; widely adopted |
| `tqdm` | 13 | Progress bars with minimal code |
| `orjson` | 9 | 5-10x faster JSON serialization for large trees |
| `PyExifTool` | 6 | Persistent exiftool process for batch performance |
| `rich` | 12, 13 | Colorized logging + progress bars in one package; alternative to `tqdm` + custom log formatting |
| `pydantic` | 8, 11 | Schema validation and JSON schema generation; heavier alternative to `dataclasses` |

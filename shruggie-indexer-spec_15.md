## 15. Platform Portability

This section defines the cross-platform design principles, platform-specific behaviors, and filesystem abstraction strategies that enable `shruggie-indexer` to run correctly on Windows, Linux, and macOS from a single codebase. It is the normative reference for how the indexer handles the platform differences that affect filesystem traversal, path manipulation, timestamp extraction, symlink detection, hashing, and output generation.

The original `MakeIndex` runs exclusively on Windows. It depends on PowerShell, .NET Framework types (`System.IO.Path`, `System.IO.FileAttributes`, `DateTimeOffset`), Windows system utilities (`certutil`), and Windows-specific filesystem assumptions (NTFS semantics, backslash separators, the `ReparsePoint` attribute for symlink detection, reliable creation time via `CreationTime`). The port eliminates every one of these Windows-specific dependencies through Python's cross-platform standard library. This section documents the residual platform differences that Python's abstractions cannot fully hide — the behavioral variations in filesystem semantics that produce different observable output depending on which operating system the indexer runs on.

Design goal G2 (§2.3) states: *The port MUST run on Windows, Linux, and macOS without platform-specific code branches in the core indexing engine.* This section specifies how that goal is achieved and where platform differences still surface in the output. §6 (Core Operations) defines what each operation does; this section defines how those operations behave differently across platforms and what the implementer must account for. §14.5 (Cross-Platform Test Matrix) defines how platform-specific behaviors are tested; this section defines what those tests are verifying.

### 15.1. Cross-Platform Design Principles

Five design principles govern the port's approach to platform portability. These principles are not aspirational guidelines — they are hard constraints that the implementation MUST satisfy.

**Principle P1 — No platform-conditional logic in the core engine.** The `core/` and `config/` subpackages MUST NOT contain `if sys.platform == ...` or `if os.name == ...` branches. All platform variation is absorbed by Python standard library abstractions (`pathlib`, `os.stat`, `os.scandir`, `hashlib`, `subprocess`) or by the configuration system. When a platform behavior cannot be abstracted away — such as creation time availability — the code uses a uniform strategy (try/fallback) that works on all platforms without branching on the OS identity.

The rationale for this constraint is maintainability: platform-conditional branches in hot-path code are a persistent source of bugs that are only discoverable when running on the affected platform. Python's standard library already provides cross-platform abstractions for every operation the indexer performs. The port leverages these abstractions rather than reimplementing platform detection.

The one permitted exception is the `cli/main.py` and `gui/app.py` entry points, which MAY contain platform-conditional logic for presentation-layer concerns: console encoding setup, Windows console virtual terminal processing, macOS application bundle registration, and similar concerns that do not affect indexing behavior. These are cosmetic entry-point adjustments, not core-engine branches.

**Principle P2 — Output determinism across platforms.** For the same input file content, the indexer MUST produce identical values for `_id`, `hashes`, `name`, `size`, `extension`, and `storage_name` regardless of the platform. These are the identity and content fields — they are derived from file bytes and name strings, which are platform-independent. If the same file is indexed on Windows and on Linux, its `_id` MUST match.

Fields that are inherently platform-dependent — `timestamps`, `file_system.absolute`, `attributes.is_link` — are permitted to vary between platforms. The variation is documented and expected, not a compatibility bug. Consumers that require cross-platform comparability SHOULD use `_id` (content identity) or `name.hashes` (name identity), not timestamps or absolute paths.

**Principle P3 — Forward-slash normalization in output.** All path strings written to the output JSON use forward-slash (`/`) separators, regardless of the host platform. This applies to `file_system.relative` and to any path components embedded in metadata entries. `file_system.absolute` retains the platform-native separator because it is a verbatim filesystem reference that consumers may use for local file access — converting it to forward slashes would make it unusable on Windows. The normalization strategy is:

| Output field | Separator convention | Rationale |
|---|---|---|
| `file_system.relative` | Always `/` | Portable relative paths for cross-platform index consumption. |
| `file_system.absolute` | Platform-native (`\` on Windows, `/` on Linux/macOS) | Usable as a local filesystem reference on the originating platform. |
| `parent.name` | N/A (leaf name, no separators) | Single directory name component, separator-free. |
| `name.text` | N/A (leaf name, no separators) | Single filename component, separator-free. |

The relative-path normalization is performed by `core/paths.py` using `PurePosixPath(relative_path).as_posix()` or equivalent string replacement (`str.replace(os.sep, "/")`). This is a deviation from the original, which produces Windows-native backslash paths in all output.

**Principle P4 — Graceful degradation for unavailable features.** When a platform does not support a feature required by a specific output field — such as creation time on older Linux kernels — the indexer populates the field with the best available approximation rather than `null`. The approximation is documented (§15.5) and the degradation is transparent: a debug-level log message is emitted on the first occurrence, and the output field is populated with the fallback value. No per-file warnings are produced for known platform limitations.

**Principle P5 — Test once, verify everywhere.** The test suite (§14) includes a `tests/platform/` category with tests that exercise platform-specific code paths. These tests use pytest markers (`@pytest.mark.platform_windows`, `@pytest.mark.platform_linux`, `@pytest.mark.platform_macos`) and are executed on the corresponding platform in CI. Platform tests verify that the abstractions described in this section produce correct results on each target OS. Unit tests in `tests/unit/` exercise core logic that is platform-independent and run on all platforms without markers.

### 15.2. Windows-Specific Considerations

Windows is the original's native platform and the only platform it supports. The port must produce equivalent output on Windows while also running correctly on Linux and macOS. This subsection documents the Windows-specific behaviors that the port accounts for.

#### Path separators and `pathlib`

Windows uses backslash (`\`) as the native directory separator. The original explicitly manages separators via the `$Sep` global variable, assigned as `[System.IO.Path]::DirectorySeparatorChar`, and used in string concatenation throughout the codebase (e.g., `$FileRenamedPath = -join("$FileParentDirectory","$Sep","$FileRenamed")`). This manual separator management is entirely eliminated by the port — `pathlib.Path` uses the platform-correct separator for all path operations, and the `/` operator constructs paths without string concatenation:

```python
# Port: pathlib handles separators automatically
target_path = parent_dir / storage_name
sidecar_path = item_path.parent / f"{item_path.name}_meta2.json"
```

No code in the port references `os.sep` directly for path construction. The only use of `os.sep` is in the output normalization described in Principle P3, where `file_system.relative` paths are converted from platform-native separators to forward slashes.

#### Long path support

Windows has two path length regimes:

| Regime | Maximum length | Applies when |
|---|---|---|
| Legacy (Win32 API) | 260 characters (`MAX_PATH`) | Default on Windows 10 before 1607; applications that do not declare long-path awareness. |
| Extended | 32,767 characters | Windows 10 1607+ with the `LongPathsEnabled` registry key set, or paths prefixed with `\\?\`. |

The original checks for the 260-character limit in `Base64DecodeString` (line 635) but does not implement general long-path handling. Python 3.6+ on Windows automatically uses the extended-length path prefix (`\\?\`) for paths exceeding 260 characters when the application manifest declares long-path awareness. CPython 3.6+ includes this manifest.

The port does not implement its own path-length management. It relies on Python's built-in long-path support, which is transparent to the application code. If a user encounters path-length errors on older Windows configurations where `LongPathsEnabled` is not set, the resolution is a Windows configuration change, not a code change in the indexer. A diagnostic message SHOULD be added to the error handler for `OSError` with `winerror 206` (filename or extension too long) that suggests enabling long paths.

#### UNC paths

Universal Naming Convention paths (`\\server\share\path`) are valid input targets on Windows. `pathlib.PureWindowsPath` handles UNC paths correctly — `Path("\\\\server\\share\\folder").parts` returns `("\\\\server\\share\\", "folder")`, and `Path.resolve()` preserves the UNC prefix.

The port does not special-case UNC paths. They flow through `resolve_path()` (§6.2) and `extract_components()` like any other path. The only behavioral difference is that the `parent_path` for a root-level item on a UNC share will be the share root (`\\server\share`) rather than a drive letter.

UNC paths are not applicable on Linux or macOS. CIFS/SMB mounts on those platforms appear as local paths (e.g., `/mnt/share/folder`), and the mount abstraction is transparent to the indexer.

#### Case preservation, case insensitivity

NTFS is case-preserving but case-insensitive by default. A file created as `Photo.JPG` retains that casing in directory listings, but `photo.jpg`, `PHOTO.JPG`, and `Photo.JPG` all resolve to the same file. This affects two operations:

**Filesystem exclusion matching (§6.1).** The exclusion filter uses case-insensitive comparison (`entry.name.lower() in excludes_set`) on all platforms. This is correct for Windows (where the filesystem is case-insensitive) and conservative for Linux (where it filters slightly more aggressively than the filesystem requires). The minor over-filtering on Linux — excluding a file literally named `$RECYCLE.BIN` on a case-sensitive filesystem — is harmless and simplifies the implementation.

**Sorting order (§6.1).** The traversal sort key (`lambda e: e.name.lower()`) produces consistent ordering across platforms. On Windows, the OS already returns entries in case-insensitive order from most NTFS directories; the explicit sort ensures the same order on case-sensitive filesystems.

**Rename collision detection (§6.10).** `storage_name` values are lowercase hex strings, so case-insensitivity does not affect rename collisions — the hash output is already normalized to a single case. The collision check (`os.stat()` inode comparison) works correctly on both case-sensitive and case-insensitive filesystems.

#### Console encoding

Windows console applications default to the OEM code page (e.g., CP437 or CP850) for stdout, which cannot represent the full Unicode range. The CLI entry point (`cli/main.py`) SHOULD set the console output encoding to UTF-8 at startup:

```python
# Illustrative — not the exact implementation.
import sys, os
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    # Enable ANSI escape sequences for colored output on Windows 10+
    os.system("")  # Triggers VT processing mode
```

This is one of the permitted entry-point platform branches (Principle P1 exception). It does not affect core engine behavior — it ensures that filenames containing non-ASCII characters are displayed correctly when output is piped to the console.

#### Windows Defender and real-time scanning

On Windows systems with real-time antivirus scanning enabled (Windows Defender, third-party AV), the file open operations during hashing may trigger per-file scanning. For large directory trees, this can significantly increase indexing time. The indexer cannot control or bypass real-time scanning. If users report unexpectedly slow performance on Windows, the documentation SHOULD mention AV scanning as a potential cause and suggest excluding the target directory from real-time scanning during indexing.

This is a documentation concern, not a code concern. The port does not implement AV-avoidance strategies.

### 15.3. Linux and macOS Considerations

Linux and macOS share POSIX filesystem semantics but differ from each other in several ways that affect the indexer.

#### Linux: filesystem diversity

Linux supports dozens of filesystem types. The filesystems most likely to be encountered by the indexer — and their relevant behavioral differences — are:

| Filesystem | Creation time (`st_birthtime`) | Access time | Max filename length | Case sensitivity |
|---|---|---|---|---|
| ext4 | Available on kernel 4.11+ via `statx`; Python 3.12+ exposes as `st_birthtime` | Configurable: `noatime`, `relatime` (default), `strictatime` | 255 bytes | Case-sensitive |
| XFS | Available on kernel 4.11+ via `statx` | Configurable | 255 bytes | Case-sensitive |
| Btrfs | Available on kernel 4.11+ via `statx` | Configurable | 255 bytes | Case-sensitive |
| tmpfs | Not available | Configurable | 255 bytes | Case-sensitive |
| NFS | Depends on server filesystem | Depends on server | Depends on server | Depends on server |
| FAT32/exFAT | Not available | Not reliable | 255 characters (LFN) | Case-insensitive |

The indexer does not detect or adapt to the underlying filesystem type. It uses the uniform `os.stat()` / `os.lstat()` interface and relies on the kernel to provide whatever timestamp precision and attribute support the filesystem offers. When `st_birthtime` is unavailable, the `st_ctime` fallback (§15.5) activates transparently.

**Access time caveat.** The `relatime` mount option, which is the default on most Linux distributions since around 2009, only updates `atime` when the previous access time is older than the modification time. This means `accessed` timestamps in the index output may not reflect the most recent access. The indexer reports whatever `os.stat()` provides without attempting to validate accuracy. This is documented in §5.7 and is not a portability bug.

#### macOS: HFS+ and APFS

macOS uses APFS (on SSDs since macOS 10.13) or HFS+ (on HDDs and older systems). Both filesystems are case-preserving and, by default, case-insensitive — the same behavior as NTFS on Windows.

| Filesystem | Creation time | Max filename | Case sensitivity | Unicode normalization |
|---|---|---|---|---|
| APFS | `st_birthtime` always available | 255 UTF-8 bytes | Case-insensitive (default) | Preserves original form (NFD or NFC) |
| HFS+ | `st_birthtime` always available | 255 UTF-16 code units | Case-insensitive (default) | Normalizes to NFD on storage |

**Unicode normalization (HFS+).** HFS+ normalizes filenames to Unicode NFD (decomposed form) on storage. A file created as `café.txt` (NFC, single `é` code point U+00E9) is stored as `café.txt` (NFD, `e` + combining acute accent U+0301). This normalization is visible to `os.scandir()` — the returned `DirEntry.name` reflects the filesystem's stored form, not the form originally used at creation.

APFS does not normalize — it preserves whatever form was used at creation. Most macOS tools use NFC, so APFS filenames are typically NFC.

This normalization difference affects name hashing: `hash_string("café")` produces different results depending on whether the name is NFC or NFD, because the UTF-8 byte sequences differ. The indexer hashes the name exactly as returned by the filesystem — it does not normalize to NFC or NFD before hashing. This means the same conceptual filename can produce different `name.hashes` values on HFS+ (NFD) vs. APFS (NFC) or Linux/Windows (NFC).

This is an acceptable deviation. Normalizing all names to a canonical form before hashing would ensure cross-platform hash consistency, but would break the invariant that re-indexing the same file on the same filesystem produces the same identity. The implementer SHOULD add a comment in `core/hashing.hash_string()` documenting this behavior. A future enhancement could add an optional `--normalize-unicode` flag that forces NFC normalization before hashing, with a clear warning that it changes identity values.

#### macOS: extended attributes and quarantine

macOS assigns extended attributes (`com.apple.quarantine`, `com.apple.metadata:*`) to downloaded files and files with Finder tags. These attributes are not part of the standard `os.stat()` result and are not read by the indexer. They do not affect any indexed fields.

The `.DS_Store` file, which macOS Finder creates in every directory it visits, is excluded by the default filesystem exclusion set (§6.1, §7.2). Similarly, `.Spotlight-V100`, `.Trashes`, `.fseventsd`, `.TemporaryItems`, and `.DocumentRevisions-V100` are excluded by default. These are all macOS system artifacts that should not appear in index output.

#### macOS and Linux: file permissions

The indexer requires read permission on every file it hashes and every directory it traverses. On Linux and macOS, files may have restrictive permissions that prevent the indexer (running as the current user) from reading them. The error handling strategy (§4.5) applies: a `PermissionError` during `hash_file()` or `os.scandir()` is treated as an item-level error — the item is included in the output with degraded fields (`null` hashes, empty `items` list for directories), and a warning is logged.

On Windows, file permissions are managed through ACLs rather than POSIX mode bits, but the behavioral outcome is the same: a `PermissionError` is raised by the OS if the current user lacks read access, and the same error handling applies.

### 15.4. Filesystem Behavior Differences

This subsection consolidates the filesystem behaviors that vary across platforms and affect indexer output. Each behavior is described in terms of its observable effect on the output schema fields, not in terms of internal implementation details (which are covered in §6).

#### Path separator in `file_system.absolute`

| Platform | Example `file_system.absolute` value |
|---|---|
| Windows | `"C:\\Users\\alice\\photos\\sunset.jpg"` |
| Linux | `"/home/alice/photos/sunset.jpg"` |
| macOS | `"/Users/alice/photos/sunset.jpg"` |

The `file_system.relative` field always uses forward slashes, regardless of platform (Principle P3). The `file_system.absolute` field uses the platform-native separator because it serves as a local reference.

#### File size consistency

`os.stat().st_size` returns the logical file size in bytes on all platforms. This value is consistent across platforms for the same file content — a 1,024-byte file reports `st_size = 1024` on Windows, Linux, and macOS. The `size.bytes` output field is platform-independent.

Sparse files are a minor exception: `st_size` reports the logical size (including sparse regions), not the physical disk allocation. The indexer reports the logical size, which is the same across platforms. Content hashing of sparse files reads the logical content (including zero-filled sparse regions), so hash values are also consistent.

#### Filename length limits

| Platform/FS | Max filename length | Max path length |
|---|---|---|
| NTFS | 255 UTF-16 code units | 32,767 characters (extended) |
| ext4 | 255 bytes (UTF-8) | No fixed limit (kernel `PATH_MAX` = 4,096 bytes) |
| APFS | 255 UTF-8 bytes | No fixed limit |
| HFS+ | 255 UTF-16 code units | No fixed limit |

The indexer does not validate filename lengths. If the filesystem accepts a filename, the indexer can process it. Filenames that exceed the target filesystem's limit when writing sidecar files (the original name plus `_meta2.json` suffix, or `_directorymeta2.json`) will produce an `OSError` that is handled as a file-level error (§4.5).

#### Hidden files and dot-files

On Linux and macOS, files and directories whose names begin with a dot (`.`) are conventionally hidden. On Windows, hidden status is an NTFS attribute (`FILE_ATTRIBUTE_HIDDEN`) independent of the filename.

The indexer does not distinguish between hidden and visible files. All files and directories within the target path are indexed, including dot-files on Linux/macOS and hidden files on Windows. The filesystem exclusion filters (§6.1) handle specific system artifacts (`.DS_Store`, `Thumbs.db`, etc.) by name, not by hidden status.

The `Get-ChildItem -Force` flag used in the original includes hidden files; the port's `os.scandir()` includes all entries by default. The behavior is equivalent.

#### Atomic rename guarantees

`Path.rename()` delegates to the platform's rename system call:

| Platform | System call | Atomicity | Cross-device support |
|---|---|---|---|
| Windows | `MoveFileExW` | Atomic on same volume (NTFS) | Fails with `OSError` if source and target are on different volumes. |
| Linux | `rename(2)` | Atomic on same filesystem | Fails with `EXDEV` if source and target are on different filesystems. |
| macOS | `rename(2)` | Atomic on same filesystem | Fails with `EXDEV` if source and target are on different filesystems. |

The rename operation in §6.10 always targets the same directory as the source file (`item_path.parent / storage_name`), so the source and target are guaranteed to be on the same filesystem. Cross-device rename failures are not expected in normal operation. The `shutil.move()` fallback exists as a safety net but should never be reached during standard rename operations.

On Windows, `Path.rename()` will fail if the target file already exists and is a different file (unlike POSIX, where `rename(2)` atomically replaces the target). The collision detection in §6.10 — which checks for target existence before calling `rename()` — handles this Windows-specific behavior correctly: if the target exists and is a different inode, a `RenameError` is raised; if it is the same inode (already renamed), the operation is a no-op.

> **Deviation from original:** The original uses PowerShell's `Move-Item`, which delegates to `MoveFileExW` on Windows. The port's `Path.rename()` uses the same underlying system call on Windows and the POSIX `rename(2)` on Linux/macOS. The behavioral difference — Windows `rename` failing on existing targets vs. POSIX `rename` atomically replacing them — is handled by the collision detection layer, making the observable behavior identical across platforms.

### 15.5. Creation Time Portability

Creation time is the single most significant cross-platform behavioral difference that surfaces in the indexer's output. The original relies on .NET's `CreationTime` property, which is always available on Windows. The port must handle platforms where true creation time may not be available.

#### Platform availability matrix

| Platform | Python attribute | Source | Reliability |
|---|---|---|---|
| Windows (NTFS) | `st_birthtime` (Python 3.12+) | NTFS `$STANDARD_INFORMATION.CreationTime` | Always available. This is the true file creation time. |
| Windows (NTFS) | `st_ctime` | Same as `st_birthtime` on Windows | Always available. On Windows, Python maps `st_ctime` to the NTFS creation time, not the inode change time. |
| macOS (APFS/HFS+) | `st_birthtime` | Filesystem creation timestamp | Always available. macOS has supported `st_birthtime` in its `stat` structure since OS X 10.6. |
| Linux (ext4/XFS/Btrfs, kernel 4.11+) | `st_birthtime` (Python 3.12+) | `statx` system call with `STATX_BTIME` | Available when the kernel supports `statx` and the filesystem records birth time. Python 3.12 added `st_birthtime` on Linux via `statx`. |
| Linux (older kernels or tmpfs/NFS) | Not available | — | `st_birthtime` raises `AttributeError`. Fallback to `st_ctime` is required. |

#### Resolution strategy

The implementation uses a two-tier approach defined in §6.5:

```python
# Illustrative — not the exact implementation.
def _get_creation_time(stat_result: os.stat_result) -> float:
    try:
        return stat_result.st_birthtime
    except AttributeError:
        return stat_result.st_ctime
```

This pattern is platform-independent — it does not check `sys.platform`. It simply attempts `st_birthtime` and falls back to `st_ctime` if the attribute does not exist. The fallback is silent at the per-file level; a debug-level log message is emitted on the first fallback occurrence per invocation to inform the user that creation times are approximate.

#### Semantic difference of the fallback

When `st_ctime` is used as the creation time fallback, the value's meaning differs by platform:

| Platform | `st_ctime` meaning | Relationship to creation time |
|---|---|---|
| Windows | NTFS creation time | Identical — `st_ctime` IS the creation time on Windows. This is not a fallback in practice; it is a second path to the same value. |
| Linux | Inode change time (ctime) | Different — ctime updates when file metadata changes (permissions, ownership, hard link count), not when the file is created. For files that have never had metadata changes, `ctime` ≈ `mtime` ≈ creation time. For files that have been `chmod`ed or `chown`ed, `ctime` may be more recent than the actual creation time. |
| macOS | Inode change time (ctime) | Same as Linux, but the fallback is rarely reached because `st_birthtime` is available on all macOS filesystems. |

The practical impact is limited: most files processed by the indexer are media files and documents that are created once and rarely have their metadata changed. For these files, `st_ctime` on Linux is a good approximation of creation time. The deviation is most visible for files that have undergone `chmod`, `chown`, or hard link operations — these will show a `created` timestamp that reflects the most recent metadata change, not the original creation.

#### Output implications

The `timestamps.created` field in the v2 schema (§5.7) always contains a value — it is never `null` due to platform limitations. The value is either the true creation time (from `st_birthtime`) or the best available approximation (from `st_ctime`). The output schema does not include a field indicating which source was used, because distinguishing the two would require consumers to handle the ambiguity and provides limited actionable value.

If a future version requires explicit provenance tracking for creation times, a `timestamps.created_source` field (with values like `"birthtime"` or `"ctime_fallback"`) could be added to the schema without breaking backward compatibility.

#### Interaction with backward compatibility testing

Backward compatibility tests (§14.6) that validate timestamp equivalence between the port and the original MUST account for the creation-time difference. The original always uses .NET `CreationTime` (true creation time on Windows NTFS). When the port runs on Linux without `st_birthtime` support, the `created` timestamp may differ from the reference value. The test tolerance (±1 second for ISO strings, ±1000 for Unix milliseconds) applies to the numerical precision of the timestamp, not to the semantic difference between creation time and ctime.

Platform-specific tests in `tests/platform/` SHOULD include a test that verifies:

1. On Windows: `timestamps.created` matches the NTFS creation time.
2. On macOS: `timestamps.created` uses `st_birthtime`.
3. On Linux (kernel 4.11+, ext4): `timestamps.created` uses `st_birthtime` when available.
4. On Linux (fallback): `timestamps.created` uses `st_ctime` and a debug log message is emitted on the first occurrence.

### 15.6. Symlink and Reparse Point Handling

Symlink semantics differ significantly between Windows and POSIX systems. The original detects symlinks by checking the `ReparsePoint` attribute in the NTFS file attribute bitmask — a Windows-specific mechanism. The port uses `Path.is_symlink()`, which delegates to the appropriate platform mechanism. This subsection documents the platform-specific behaviors that affect symlink handling.

#### Platform mechanisms

| Platform | Creation mechanism | Detection API | Privilege required |
|---|---|---|---|
| Windows | `mklink` (cmd), `New-Item -ItemType SymbolicLink` (PowerShell), `os.symlink()` (Python) | `Path.is_symlink()` → checks `FILE_ATTRIBUTE_REPARSE_POINT` via `GetFileAttributesW` | Creating symlinks requires either administrator privileges or Developer Mode enabled (Windows 10 1703+). Reading/detecting symlinks requires no special privileges. |
| Linux | `ln -s`, `os.symlink()` | `Path.is_symlink()` → `lstat()` checks `S_IFLNK` in `st_mode` | No special privileges for creation or detection. |
| macOS | `ln -s`, `os.symlink()` | `Path.is_symlink()` → `lstat()` checks `S_IFLNK` in `st_mode` | No special privileges for creation or detection. |

The `Path.is_symlink()` call is the correct cross-platform abstraction. It returns `True` for symbolic links on all platforms and is the only symlink detection mechanism used by the port.

#### Windows: junctions vs. symlinks

Windows has two types of reparse points that behave like symlinks:

| Type | Target | Created by | Detected by `is_symlink()` |
|---|---|---|---|
| Symbolic link (symlink) | File or directory, absolute or relative | `mklink /D` (directory), `mklink` (file), `os.symlink()` | Yes — `Path.is_symlink()` returns `True`. |
| Junction (mount point) | Directory only, absolute path only | `mklink /J`, `os.path.join()` with junction semantics | Yes — `Path.is_symlink()` returns `True` on Python 3.12+. |

Both junction points and symbolic links have the `FILE_ATTRIBUTE_REPARSE_POINT` attribute set, and Python's `Path.is_symlink()` detects both as of Python 3.12. The original's `Attributes -band ReparsePoint` check also detects both types. The port's behavior matches the original for both junctions and symlinks.

The indexer does not distinguish between junctions and symlinks in the output — both set `attributes.is_link = true` and trigger the same behavioral changes (name hashing instead of content hashing, skipped EXIF extraction, `os.lstat()` for timestamps). This is correct behavior: both types redirect to a different filesystem location, and hashing the link target's content would produce an identity that depends on the target rather than the link itself.

#### Symlink targets across filesystems

A symlink can point to a target on a different filesystem or a different volume. The original does not explicitly handle this case — it simply switches to name hashing when the `ReparsePoint` attribute is detected, regardless of the target's location.

The port preserves this behavior. When `is_symlink()` returns `True`, content hashing is replaced by name hashing, and the link target is not followed for any content-dependent operation (hashing, EXIF extraction). The only operation that follows the link is `Path.resolve()`, which resolves the symlink to its target for the `file_system.absolute` field. If the symlink target does not exist (dangling symlink), `Path.resolve(strict=False)` returns the normalized path without verifying existence, and the entry is populated with degraded fields as documented in §6.4.

#### Symlink traversal safety

The indexer does not follow symlinks during directory traversal. The `list_children()` function (§6.1) uses `os.scandir()` with `follow_symlinks=False` for entry classification. A symlink to a directory appears in the traversal results but is not descended into — it is processed as a single entry with `is_link = True` and an empty `items` list. This prevents symlink loops (where directory A symlinks to B and B symlinks to A) from causing infinite recursion.

This is consistent with the original's behavior. The original's `Get-ChildItem -Force` does not follow symlinks into directories by default — it lists the symlink as an entry without descending into it.

> **Improvement over original:** The original does not explicitly document or test its symlink traversal behavior — the non-descent is a side effect of `Get-ChildItem`'s default behavior rather than a deliberate design decision. The port's explicit `follow_symlinks=False` parameter makes the safety behavior intentional and testable.

#### Symlink metadata sources

When processing a symlink, the timestamps module (§6.5) uses `os.lstat()` instead of `os.stat()`. The distinction:

| Call | Returns metadata for |
|---|---|
| `os.stat(path)` | The symlink's target. If the target is another symlink, follows the chain to the final target. Raises `FileNotFoundError` for dangling symlinks. |
| `os.lstat(path)` | The symlink itself. Never follows the link. Always succeeds for an existing symlink, even if the target is missing. |

On all three platforms, `os.lstat()` returns the symlink's own modification time, access time, and (where available) creation time. These timestamps reflect when the symlink was created or modified, not when the target was created or modified.

The `size` field for symlinks varies by platform:

| Platform | `os.lstat().st_size` for a symlink |
|---|---|
| Windows | 0 (reparse points report zero size) |
| Linux | Length of the target path string in bytes |
| macOS | Length of the target path string in bytes |

This difference is inherent to the platform's symlink implementation and is documented here for completeness. Consumers SHOULD NOT rely on the `size` field for symlinks — it does not represent the size of the target file.

#### Creating test symlinks across platforms

The platform-specific tests in `tests/platform/` need to create symlinks for validation. On Windows, symlink creation requires either administrator privileges or Developer Mode. The test infrastructure uses `os.symlink()` with a try/except for `OSError` — if symlink creation fails due to insufficient privileges, the test is skipped with `pytest.skip("Symlink creation requires elevated privileges on Windows")`. This is handled by the test fixture, not by repeating the privilege check in every test function.

On Linux and macOS, `os.symlink()` works without special privileges. Symlink creation for tests is straightforward and does not require any special handling.

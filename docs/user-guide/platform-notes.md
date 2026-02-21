# Platform Notes

shruggie-indexer runs on Windows, Linux, and macOS from a single codebase. This page documents platform-specific behaviors, filesystem differences, and the strategies used to produce consistent output across operating systems.

## Cross-Platform Design Principles

Five principles govern how the tool handles platform portability:

| Principle | Summary |
|-----------|---------|
| **P1 — No platform branches in core** | The `core/` and `config/` packages contain no `if sys.platform` checks. All platform variation is absorbed by Python standard library abstractions (`pathlib`, `os.stat`, `hashlib`). Entry points (`cli/`, `gui/`) may contain platform adjustments for presentation. |
| **P2 — Output determinism** | For identical file content, `id`, `hashes`, `name`, `size`, `extension`, and `storage_name` are identical across platforms. Inherently platform-dependent fields (`timestamps`, `file_system.absolute`, `attributes.is_link`) may vary. |
| **P3 — Forward-slash normalization** | `file_system.relative` always uses `/` separators. `file_system.absolute` retains the platform-native separator (`\` on Windows, `/` elsewhere). |
| **P4 — Graceful degradation** | When a platform lacks a feature (e.g., creation time on older Linux kernels), the nearest available approximation is used. No `null` values due to platform limitations. |
| **P5 — Test once, verify everywhere** | Platform-specific tests use pytest markers (`@pytest.mark.platform_windows`, etc.) and run on each OS in CI. |

## Path Separator Convention

| Output field | Separator | Rationale |
|---|---|---|
| `file_system.relative` | Always `/` | Portable relative paths for cross-platform index consumption. |
| `file_system.absolute` | Platform-native | Usable as a local filesystem reference on the originating platform. |
| `parent.name` | N/A (leaf name) | Single directory name component — no separators. |
| `name.text` | N/A (leaf name) | Single filename component — no separators. |

## Windows

### Path handling

Windows uses backslash (`\`) as the native separator. The tool uses `pathlib.Path` for all path operations, eliminating manual separator management entirely. No code references `os.sep` for path construction.

### Long path support

| Regime | Maximum length | Applies when |
|--------|----------------|-------------|
| Legacy (Win32) | 260 characters | Default before Windows 10 1607 |
| Extended | 32,767 characters | Windows 10 1607+ with `LongPathsEnabled`, or `\\?\` prefix |

Python 3.6+ on Windows automatically uses extended-length paths. The tool relies on this built-in support. If path-length errors occur on older configurations, enable `LongPathsEnabled` in the Windows registry.

### UNC paths

Universal Naming Convention paths (`\\server\share\path`) are valid input targets. They flow through path resolution without special handling. On Linux and macOS, CIFS/SMB mounts appear as local paths (e.g., `/mnt/share/folder`).

### Case sensitivity

NTFS is case-preserving but case-insensitive by default. The tool uses case-insensitive comparison for filesystem exclusion matching on all platforms — this is correct for Windows and conservative for case-sensitive Linux filesystems.

### Console encoding

The CLI entry point sets console output to UTF-8 on Windows to ensure correct display of non-ASCII filenames. This is one of the permitted entry-point platform adjustments (Principle P1 exception).

### Performance note

On systems with real-time antivirus scanning (Windows Defender), file open operations during hashing may trigger per-file scanning, increasing indexing time for large trees. Consider excluding the target directory from real-time scanning during indexing if performance is a concern.

## Linux

### Filesystem diversity

Linux supports many filesystem types with varying capabilities:

| Filesystem | Creation time (`st_birthtime`) | Case sensitivity |
|---|---|---|
| ext4 | Kernel 4.11+ via `statx`; Python 3.12+ | Case-sensitive |
| XFS | Kernel 4.11+ via `statx` | Case-sensitive |
| Btrfs | Kernel 4.11+ via `statx` | Case-sensitive |
| tmpfs | Not available | Case-sensitive |
| NFS | Depends on server | Depends on server |
| FAT32/exFAT | Not available | Case-insensitive |

The tool does not detect the underlying filesystem type. It uses the uniform `os.stat()` interface and relies on the kernel to provide available attributes.

### Access time caveat

The default `relatime` mount option (standard since ~2009) only updates `atime` when the previous access time is older than the modification time. The `accessed` timestamp in the output reflects whatever `os.stat()` provides, without attempting to validate accuracy.

### File permissions

The tool requires read permission on every file it hashes and every directory it traverses. A `PermissionError` during hashing or enumeration results in the item being included with degraded fields (`null` hashes, empty `items` list), and a warning is logged.

## macOS

### Filesystems

| Filesystem | Creation time | Case sensitivity | Unicode normalization |
|---|---|---|---|
| APFS | `st_birthtime` (always available) | Case-insensitive (default) | Preserves original form |
| HFS+ | `st_birthtime` (always available) | Case-insensitive (default) | Normalizes to NFD on storage |

### Unicode normalization

HFS+ normalizes filenames to Unicode NFD (decomposed form) on storage. A file created as `café.txt` (NFC) is stored as `café.txt` (NFD, `e` + combining accent).

To ensure cross-platform hash determinism, the tool applies `unicodedata.normalize('NFC', value)` unconditionally on **all platforms** before encoding filenames to UTF-8 for hashing. This guarantees that a file named `café.txt` produces identical identity hashes regardless of the filesystem's normalization behavior.

!!! info "NFC Normalization"
    NFC normalization is applied on all platforms — not just macOS — because the goal is cross-platform determinism: the same logical filename produces the same hash everywhere.

### System exclusions

The following macOS system artifacts are excluded by default:

`.DS_Store`, `.Spotlight-V100`, `.Trashes`, `.fseventsd`, `.TemporaryItems`, `.DocumentRevisions-V100`

Extended attributes (`com.apple.quarantine`, Finder tags) are not read by the tool and do not affect indexed fields.

## Creation Time Portability

Creation time is the most significant cross-platform behavioral difference that surfaces in the output.

### Availability matrix

| Platform | Python attribute | Reliability |
|----------|-----------------|-------------|
| Windows (NTFS) | `st_birthtime` (3.12+) or `st_ctime` | Always available. On Windows, `st_ctime` maps to NTFS creation time. |
| macOS (APFS/HFS+) | `st_birthtime` | Always available. |
| Linux (kernel 4.11+, ext4/XFS/Btrfs) | `st_birthtime` (Python 3.12+) | Available when the kernel supports `statx` and the filesystem records birth time. |
| Linux (older kernels, tmpfs, NFS) | Not available | `st_birthtime` raises `AttributeError`. Fallback to `st_ctime`. |

### Resolution strategy

The implementation tries `st_birthtime` first and falls back to `st_ctime` without platform branching:

```python
def _get_creation_time(stat_result: os.stat_result) -> float:
    try:
        return stat_result.st_birthtime
    except AttributeError:
        return stat_result.st_ctime
```

A debug-level log message is emitted on the first fallback occurrence per invocation.

### Fallback semantics

When `st_ctime` is used as the fallback, the meaning differs by platform:

| Platform | `st_ctime` meaning |
|----------|-------------------|
| Windows | NTFS creation time (identical — not a true fallback) |
| Linux | Inode change time — updates on `chmod`, `chown`, hard link changes |
| macOS | Inode change time (rare — `st_birthtime` is always available) |

For most media files and documents (created once, metadata rarely changed), `st_ctime` on Linux is a good approximation. The most visible deviation is for files that have undergone `chmod` or `chown` operations.

The `timestamps.created` field is never `null` due to platform limitations — it always contains either the true creation time or the best available approximation.

## Symlink Handling

### Detection

Symlinks are detected via `Path.is_symlink()`, which delegates to the platform-appropriate mechanism:

| Platform | Mechanism |
|----------|-----------|
| Windows | `FILE_ATTRIBUTE_REPARSE_POINT` via `GetFileAttributesW` |
| Linux / macOS | `lstat()` checks `S_IFLNK` in `st_mode` |

On Windows, both symbolic links and junction points are detected as symlinks (Python 3.12+).

### Behavioral changes for symlinks

When a symlink is detected:

- `attributes.is_link` is set to `true`
- Content hashing is replaced by name hashing
- EXIF extraction is skipped
- `os.lstat()` is used for timestamps (symlink's own timestamps, not the target's)
- Directory symlinks are not descended into during traversal (prevents symlink loops)

### Size field for symlinks

| Platform | `lstat().st_size` for a symlink |
|----------|--------------------------------|
| Windows | 0 (reparse points report zero size) |
| Linux / macOS | Length of the target path string in bytes |

!!! warning
    Do not rely on the `size` field for symlinks — it does not represent the target file's size.

### Dangling symlinks

If a symlink target does not exist, `Path.resolve(strict=False)` returns the normalized path without verifying existence. The entry is populated with degraded fields.

## Filesystem Behavior Summary

| Behavior | Windows (NTFS) | Linux (ext4) | macOS (APFS) |
|----------|----------------|--------------|--------------|
| Path separator | `\` | `/` | `/` |
| Case sensitivity | Case-insensitive | Case-sensitive | Case-insensitive (default) |
| Creation time | Always available | Kernel 4.11+ / Python 3.12+ | Always available |
| Max filename | 255 UTF-16 code units | 255 bytes | 255 UTF-8 bytes |
| Max path | 32,767 (extended) | ~4,096 (PATH_MAX) | No fixed limit |
| Unicode normalization | NFC (Windows standard) | Preserves original | NFD (HFS+) / original (APFS) |
| Symlink creation privilege | Admin or Developer Mode | None | None |
| Atomic rename | Same volume (NTFS) | Same filesystem | Same filesystem |
| Hidden files | NTFS attribute | Dot-prefix convention | Dot-prefix convention |

# ExifTool Setup

## What Is ExifTool?

[ExifTool](https://exiftool.org/) by Phil Harvey is a platform-independent Perl library and command-line tool for reading, writing, and editing metadata in a wide variety of file formats — including EXIF, XMP, IPTC, GPS, and maker notes from camera manufacturers.

shruggie-indexer uses ExifTool to extract embedded metadata from indexed files when the `--meta` flag is active. ExifTool is the sole external binary dependency and is required **only** for embedded metadata extraction. All other functionality — hashing, timestamp capture, sidecar file handling, renaming — works without it.

## Installation

### Windows

**Option 1 — Direct download:**

1. Download the standalone Windows executable from [https://exiftool.org/](https://exiftool.org/).
2. Extract the downloaded archive.
3. Rename `exiftool(-k).exe` to `exiftool.exe`.
4. Place `exiftool.exe` in a directory on your system `PATH` (e.g., `C:\Windows\` or a custom directory you have added to `PATH`).

**Option 2 — Chocolatey:**

```
choco install exiftool
```

**Option 3 — winget:**

```
winget install OliverBetz.ExifTool
```

### macOS

Install via [Homebrew](https://brew.sh/):

```bash
brew install exiftool
```

### Linux

**Debian / Ubuntu:**

```bash
sudo apt install libimage-exiftool-perl
```

**Fedora / RHEL:**

```bash
sudo dnf install perl-Image-ExifTool
```

**Arch Linux:**

```bash
sudo pacman -S perl-image-exiftool
```

## Verification

After installing, verify that ExifTool is accessible on your `PATH` and meets the minimum version requirement (12.0+):

```bash
exiftool -ver
```

This should print a version number of `12.00` or higher (e.g., `12.87`).

## Behavior When ExifTool Is Not Installed

When ExifTool is not found on `PATH`, shruggie-indexer logs a single warning at startup:

```
WARNING: exiftool not found on PATH; embedded metadata extraction disabled
```

The indexing operation continues normally. The `metadata` array in output entries simply omits the `exiftool.json_metadata` entry that would otherwise be present. This is a **graceful degradation**, not a fatal error — the tool is fully functional for hashing, timestamping, sidecar handling, and renaming without ExifTool.

!!! tip "Check once, not per-file"
    The ExifTool availability check happens once at startup and the result is cached. You will not see repeated warnings for each file.

## Invocation Backends

shruggie-indexer supports two ExifTool invocation backends, selected automatically based on package availability:

### Primary: pyexiftool batch mode

When the `pyexiftool` Python package is installed (it is a required runtime dependency of shruggie-indexer), the tool uses ExifTool's `-stay_open` protocol to maintain a single persistent Perl process for the entire indexing run. File paths and arguments are communicated via stdin/stdout pipes.

This approach reduces per-file overhead from 200–500 ms (process startup) to roughly 20–50 ms (metadata extraction only), making it significantly faster for large directory trees.

### Fallback: subprocess per file

If `pyexiftool` is unavailable or the persistent process cannot be maintained, the tool falls back to spawning a new ExifTool subprocess for each file. Arguments are passed via a temporary argfile using ExifTool's `-@` switch. This is slower but functionally equivalent.

!!! note "Backend selection"
    The backend is selected once at startup and logged at `DEBUG` level. Use `-vv` to see which backend is active.

## File Extension Exclusion List

By default, shruggie-indexer skips ExifTool invocation for certain file types where ExifTool tends to dump the entire file content as metadata rather than extracting meaningful embedded metadata:

| Extension | Reason |
|-----------|--------|
| `csv` | Text data — no embedded metadata |
| `htm` | HTML markup |
| `html` | HTML markup |
| `json` | JSON data |
| `tsv` | Tab-separated text data |
| `xml` | XML markup |

This exclusion list is configurable. See the [Configuration](../user-guide/configuration.md) page for details on modifying the `exiftool.exclude_extensions` setting.

## Next Steps

- [Quick Start](quickstart.md) — Try `--meta` with a real file.
- [CLI Reference](../user-guide/cli-reference.md) — Full `--meta`, `--meta-merge`, and `--meta-merge-delete` documentation.
- [Configuration](../user-guide/configuration.md) — Customize ExifTool arguments and exclusion lists.

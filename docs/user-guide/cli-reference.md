# CLI Reference

shruggie-indexer is invoked as a single command with options and an optional target path.

## Command Structure

```
shruggie-indexer [OPTIONS] [TARGET]
```

`TARGET` is an optional positional argument specifying the file or directory to index. When omitted, the current working directory is used.

## Target Options

### `TARGET` (positional argument)

The filesystem path to index. shruggie-indexer auto-detects whether the path is a file or directory and dispatches to the appropriate indexing logic.

- If omitted, defaults to the current working directory.
- Must point to an existing path (validated at invocation time).

### `--file` / `--directory`

Force the target to be treated as a file or directory, overriding auto-detection.

```bash
# Force file interpretation (useful for symlinks)
shruggie-indexer --file path/to/ambiguous-item

# Force directory interpretation
shruggie-indexer --directory path/to/target
```

If the forced type does not match the actual filesystem type, a warning is logged but processing continues.

### `--recursive` / `--no-recursive`

Control recursive directory traversal. Default: `--recursive`.

```bash
# Index a directory and all its subdirectories (default)
shruggie-indexer path/to/dir --recursive

# Index only the directory's immediate children
shruggie-indexer path/to/dir --no-recursive
```

For single-file targets, this option has no effect.

## Output Options

Three independent output flags control where JSON output is written. Multiple output destinations can be active simultaneously.

### `--stdout` / `--no-stdout`

Write the complete JSON index to standard output.

- **Default behavior:** Enabled when no other output destination (`--outfile`, `--inplace`) is specified. Disabled when another output destination is active.
- **Explicit `--stdout`:** Forces stdout output alongside other destinations.
- **Explicit `--no-stdout`:** Suppresses stdout output entirely.

### `--outfile`, `-o`

Write the combined JSON output to the specified file path.

```bash
shruggie-indexer path/to/target --outfile index.json
shruggie-indexer path/to/target -o index.json
```

- The parent directory must exist.
- Existing files are overwritten without prompting.
- Disables stdout output by default (use `--stdout` to re-enable).

### `--inplace`

Write individual sidecar JSON files alongside each indexed item.

```bash
shruggie-indexer path/to/directory/ --inplace
```

For files, the sidecar is named `<filename>_meta2.json`. For directories, the sidecar is named `<dirname>_directorymeta2.json` and placed inside the directory. The root target directory does not receive an in-place sidecar — the aggregate output file (`--outfile`) serves that purpose.

| Item | Sidecar path |
|------|-------------|
| `photos/sunset.jpg` | `photos/sunset.jpg_meta2.json` |
| `photos/vacation/` | `photos/vacation/vacation_directorymeta2.json` |

Disables stdout output by default (use `--stdout` to re-enable).

### `--dir-meta` / `--no-dir-meta`

Control whether `_directorymeta2.json` directory sidecar files are written.

```bash
# Suppress directory metadata — only per-file sidecars are written
shruggie-indexer path/to/directory/ --inplace --no-dir-meta

# Explicitly enable (default behavior)
shruggie-indexer path/to/directory/ --inplace --dir-meta
```

- **Default:** Enabled (`--dir-meta`). All directory sidecars are written normally.
- **`--no-dir-meta`:** Suppresses directory-level `_directorymeta2.json` sidecars during `--inplace` output. Per-file `_meta2.json` sidecars are unaffected.
- Auto-generated aggregate output files (those ending in `_directorymeta2.json` produced by the output path defaulting logic) are also suppressed.
- Explicitly specified `--outfile` paths are never suppressed, regardless of this flag.
- Stdout output is never affected by this flag.
- Maps to the `write_directory_meta` configuration key.

## Metadata Options

These options control embedded metadata extraction and sidecar metadata processing.

!!! warning "Implication chain"
    The metadata flags form an implication chain:

    - `--meta-merge-delete` implies `--meta-merge`
    - `--meta-merge` implies `--meta`

    You only need to specify the highest-level flag you want. The implied flags are activated automatically.

### `--meta`, `-m`

Extract embedded EXIF/XMP/IPTC metadata from files via [ExifTool](../getting-started/exiftool.md).

```bash
shruggie-indexer path/to/file.jpg --meta
```

When active, each file entry's `metadata` array includes an `exiftool.json_metadata` entry containing the extracted metadata as a JSON object. If ExifTool is not installed, a warning is logged and the entry is omitted — this is not a fatal error.

### `--meta-merge`

Discover sidecar metadata files alongside each indexed item and merge their content into the parent entry's `metadata` array. Implies `--meta`.

```bash
shruggie-indexer path/to/directory/ --meta-merge
```

Sidecar files (`.info.json`, `.description`, thumbnails, subtitles, etc.) are identified by configurable filename patterns. The original sidecar files remain on disk.

### `--meta-merge-delete`

Merge sidecar metadata into parent entries and delete the original sidecar files from disk after indexing completes. Implies `--meta-merge` (and therefore `--meta`).

```bash
shruggie-indexer path/to/directory/ --meta-merge-delete --outfile index.json
```

!!! warning "Requires persistent output"
    `--meta-merge-delete` requires at least one of `--outfile` or `--inplace` to be active. Without a persistent output destination, the merged metadata would be lost when the sidecar files are deleted. Violating this constraint produces a fatal error (exit code 2).

Each merged sidecar entry carries full filesystem provenance — path, size, timestamps, and content hashes — sufficient to reverse the deletion if needed.

The pipeline executes in a fixed order: **index → write sidecars → rename → delete**. Sidecar deletion occurs only after all other phases complete successfully. Each successful deletion is logged at `INFO` level; failures are logged at `ERROR` level and do not abort the remaining deletions.

## Rename Options

### `--rename`

Rename files to their deterministic, hash-based `storage_name` values.

```bash
shruggie-indexer path/to/directory/ --rename
```

For a file with `id` of `yA8A8C089A6A8583B24C85F5A4A41F5AC` and extension `exe`, the storage name is `yA8A8C089A6A8583B24C85F5A4A41F5AC.exe`. Directories are renamed to their `id` (e.g., `x3B4F479E9F880E438882FC34B67D352C`).

!!! note "Rename implies in-place"
    `--rename` automatically enables `--inplace` so that sidecar files are written alongside each renamed item, preserving the original filename in the index entry.

### `--dry-run`

Preview rename operations without modifying any files.

```bash
shruggie-indexer path/to/directory/ --rename --dry-run
```

Logs each proposed rename at `INFO` level. Only meaningful when used with `--rename`.

## Identity Options

### `--id-type`

Select which hash algorithm is used for the `id` field and `storage_name`. Choices: `md5` (default) or `sha256`.

```bash
shruggie-indexer path/to/file --id-type sha256
```

| `--id-type` | `id` example | `id` length |
|-------------|-------------|-------------|
| `md5` | `yA8A8C089A6A8583B24C85F5A4A41F5AC` | 33 chars (1 prefix + 32 hex) |
| `sha256` | `yB6BA115C2B43D87AADDF0060C44726E7AF1A12C9501FC63DE652A9517D7367DB` | 65 chars (1 prefix + 64 hex) |

Both algorithms are always computed regardless of this setting. This option only controls which digest is promoted to the `id` field.

### `--compute-sha512`

Include SHA-512 in the computed `HashSet` objects. SHA-512 is excluded by default to reduce output size.

```bash
shruggie-indexer path/to/file --compute-sha512
```

When enabled, every `hashes` and `name.hashes` object in the output includes a `sha512` field.

## Configuration

### `--config`

Path to a TOML configuration file. Overrides the default config file resolution.

```bash
shruggie-indexer path/to/target --config my-config.toml
```

See the [Configuration](configuration.md) page for the file format and available settings.

## Logging Options

### `-v`, `--verbose`

Increase logging verbosity. Repeatable.

| Flag | Log level | Output |
|------|-----------|--------|
| (none) | `WARNING` | Warnings and errors only |
| `-v` | `INFO` | Informational messages (progress, implications) |
| `-vv` | `DEBUG` | Detailed diagnostic output |
| `-vvv` | `DEBUG` (all) | Full trace-level logging including internal modules |

### `-q`, `--quiet`

Suppress all non-error output. Sets log level to `CRITICAL`. Overrides `--verbose` if both are specified.

```bash
shruggie-indexer path/to/target -q
```

In quiet mode, the exit code is the primary success/failure signal.

### `--log-file`

Write log output to a persistent file for later analysis.

```bash
# Write to the default app data directory
shruggie-indexer path/to/target --log-file

# Write to a specific file
shruggie-indexer path/to/target --log-file /path/to/output.log
```

| Usage | Behavior |
|-------|----------|
| `--log-file` (no argument) | Write to the default platform-specific log directory |
| `--log-file <path>` | Write to the specified file path |

**Default log directory by platform:**

| Platform | Directory |
|----------|-----------|
| Windows | `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\logs\` |
| macOS | `~/Library/Application Support/shruggie-tech/shruggie-indexer/logs/` |
| Linux | `~/.config/shruggie-tech/shruggie-indexer/logs/` |

Log files are named by date and session: `YYYY-MM-DD_HHMMSS.log`. The log level written to the file matches the currently configured verbosity.

Log file output can also be enabled via the TOML configuration file:

```toml
[logging]
file_enabled = true
# file_path = ""  # empty = use default app data location
```

## General Options

### `--version`

Print the installed version and exit.

```bash
shruggie-indexer --version
```

### `--help`

Print the help text and exit.

```bash
shruggie-indexer --help
```

## Mutual Exclusion Rules

The following constraints are enforced at invocation time:

| Rule | Behavior |
|------|----------|
| `--file` and `--directory` | Mutually exclusive. Only one may be specified. |
| `--stdout` and `--no-stdout` | Mutually exclusive. Click handles this automatically. |
| `--recursive` and `--no-recursive` | Mutually exclusive. Click handles this automatically. |
| `--meta-merge-delete` without `--outfile` or `--inplace` | Fatal error (exit code 2). |
| `--dry-run` without `--rename` | Silently ignored. |
| `TARGET` does not exist | Fatal error (exit code 3). |
| `--outfile` parent directory does not exist | Fatal error (exit code 2). |

## Output Scenarios

The three output flags (`--stdout`, `--outfile`, `--inplace`) combine into the following scenarios:

| Scenario | Flags | Stdout | Outfile | In-place |
|----------|-------|:------:|:-------:|:--------:|
| 1 — Default | (none) | ✔ | — | — |
| 2 — File only | `--outfile index.json` | — | ✔ | — |
| 3 — File + stdout | `--outfile index.json --stdout` | ✔ | ✔ | — |
| 4 — In-place only | `--inplace` | — | — | ✔ |
| 5 — File + in-place | `--outfile index.json --inplace` | — | ✔ | ✔ |
| 6 — In-place + stdout | `--inplace --stdout` | ✔ | — | ✔ |
| 7 — All three | `--outfile index.json --inplace --stdout` | ✔ | ✔ | ✔ |
| Silent | `--no-stdout` | — | — | — |

## Exit Codes

| Code | Name | Meaning |
|------|------|---------|
| `0` | `SUCCESS` | Completed successfully. All items processed. |
| `1` | `PARTIAL_FAILURE` | Completed with one or more item-level errors (skipped items, failed extractions). |
| `2` | `CONFIGURATION_ERROR` | Invalid configuration or flag combination. No processing began. |
| `3` | `TARGET_ERROR` | Target path does not exist or is not accessible. |
| `4` | `RUNTIME_ERROR` | Unexpected error during processing. |
| `5` | `INTERRUPTED` | Cancelled by user via Ctrl+C. |

## Signal Handling

shruggie-indexer implements a two-phase interruption model for graceful cancellation:

**First Ctrl+C (cooperative):** Sets a cancellation flag. The engine finishes processing the current item and then stops cleanly. A message is printed to stderr:

```
Interrupt received — finishing current item. Press Ctrl+C again to force quit.
```

**Second Ctrl+C (forced):** Restores the default signal handler and raises `KeyboardInterrupt` for immediate termination.

### Cancellation and output state

| Output mode | State after interruption |
|-------------|------------------------|
| `--stdout` | No output produced (the entry tree was incomplete). |
| `--outfile` | No output produced. |
| `--inplace` | Partial output — sidecar files for completed items are valid on disk. |

If `--meta-merge-delete` is active, the deletion queue is discarded on cancellation — no sidecar files are deleted.

If `--rename` is active, files renamed before the interrupt retain their new names with valid sidecar manifests. Unreached files keep their original names. Re-running the same command is safe and idempotent.

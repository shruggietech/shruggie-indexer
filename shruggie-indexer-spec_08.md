## 8. CLI Interface

This section defines the command-line interface for `shruggie-indexer` — the command structure, every option and argument, their interactions, validation rules, output scenarios, and exit codes. The CLI is a thin presentation layer over the library API (§9) and the core indexing engine (§6). No indexing logic lives in the CLI module — it is responsible only for parsing user input, constructing an `IndexerConfig` object (§7), calling `index_path()`, and routing output to the requested destinations. This separation is design goal G3 (§2.3).

The CLI module is `cli/main.py` (§3.2). The entry point is registered as `shruggie-indexer = "shruggie_indexer.cli.main:main"` in `pyproject.toml` (§2.1), and `python -m shruggie_indexer` invokes the same function via `__main__.py`.

**CLI framework:** The CLI uses `click` as its argument parsing framework. `click` is declared as an optional dependency in `pyproject.toml` under the `cli` extra (§12.3). If `click` is not installed, the CLI entry point MUST fail with a clear error message directing the user to install the dependency (`pip install shruggie-indexer[cli]`). The core library does not depend on `click` — consumers who use `shruggie_indexer` as a Python library never import it.

> **Deviation from original:** The original's CLI is the `Param()` block of a PowerShell function — 14 parameters with aliases, switches, and manual validation logic spanning ~200 lines. The port replaces this with `click` decorators, which handle type conversion, mutual exclusion, default propagation, and help text generation declaratively. The port also adds capabilities absent from the original: `--version`, `--dry-run`, `--config`, `--no-stdout`, and structured exit codes.

### 8.1. Command Structure

`shruggie-indexer` exposes a single top-level command with no subcommands. All behavior is controlled via options and a single positional argument.

```
shruggie-indexer [OPTIONS] [TARGET]
```

The command name when installed via `pip install -e ".[cli]"` is `shruggie-indexer` (hyphenated). The `python -m shruggie_indexer` invocation behaves identically.

#### Help output

The `--help` flag produces a usage summary organized into logical option groups. The following is the canonical help layout — the implementation MUST produce output equivalent to this structure, though minor whitespace or wrapping differences are acceptable:

```
Usage: shruggie-indexer [OPTIONS] [TARGET]

  Index files and directories, producing structured JSON output with hash-based
  identities, filesystem metadata, EXIF data, and sidecar metadata.

Arguments:
  [TARGET]  Path to the file or directory to index. Defaults to the current
            working directory if not specified.

Target Options:
  --file / --directory    Force TARGET to be treated as a file or directory.
                          Normally inferred from the filesystem. Useful for
                          disambiguating symlinks.
  --recursive / --no-recursive
                          Enable or disable recursive traversal for directory
                          targets. Default: recursive.

Output Options:
  --stdout / --no-stdout  Write JSON output to stdout. Default: enabled when no
                          other output is specified; disabled when --outfile or
                          --inplace is used.
  --outfile, -o PATH      Write combined JSON output to the specified file.
  --inplace               Write individual sidecar JSON files alongside each
                          processed item.

Metadata Options:
  --meta, -m              Extract embedded metadata via exiftool.
  --meta-merge            Merge sidecar metadata into parent entries. Implies
                          --meta.
  --meta-merge-delete     Merge and delete sidecar files. Implies --meta-merge.
                          Requires --outfile or --inplace.

Rename:
  --rename                Rename files to their storage_name. Implies --inplace.
  --dry-run               Preview rename operations without executing them.

Identity:
  --id-type [md5|sha256]  Hash algorithm for the id field. Default: md5.
  --compute-sha512        Include SHA-512 in hash output. Default: disabled.

Configuration:
  --config PATH           Path to a TOML configuration file. Overrides the
                          default file resolution.

Logging:
  -v, --verbose           Increase verbosity. Repeat for more detail (-vv, -vvv).
  -q, --quiet             Suppress all non-error output.

General:
  --version               Show version and exit.
  --help                  Show this message and exit.
```

### 8.2. Target Input Options

#### Positional argument: `TARGET`

The `TARGET` argument specifies the file or directory to index. It is optional — when omitted, the current working directory is used as the target, matching the original's default behavior.

```python
@click.argument("target", required=False, default=None, type=click.Path(exists=True))
```

If a `TARGET` is provided but does not exist on the filesystem, `click.Path(exists=True)` raises a `click.BadParameter` error before the indexing engine is invoked. The error message includes the path and the specific reason for failure (does not exist, permission denied, etc.).

When `TARGET` is `None` (omitted), the CLI sets it to `Path.cwd()`. This matches the original's behavior where `$Directory` defaults to the current directory when neither `-Directory` nor `-File` is specified.

> **Deviation from original:** The original uses two separate parameters (`-Directory` and `-File`) that are mutually exclusive. The port uses a single positional argument and infers the target type from the filesystem. The `--file` / `--directory` flags (below) provide explicit disambiguation when needed but are not the primary input mechanism.

#### Target type disambiguation: `--file` / `--directory`

```python
@click.option("--file/--directory", "target_type", default=None)
```

When omitted (the common case), the CLI resolves the target type from the filesystem: `Path.is_file()` → file target, `Path.is_dir()` → directory target. This auto-detection handles the vast majority of use cases without requiring the user to specify the target type.

The `--file` and `--directory` flags override auto-detection. They exist for two scenarios:

1. **Symlink disambiguation.** A symlink could point to either a file or a directory. When the user wants to force the classification (e.g., treat a symlink-to-a-directory as a file-like entry), the explicit flag overrides the filesystem inference.

2. **Scripting predictability.** Automated pipelines may prefer to state the expected target type explicitly rather than relying on filesystem inference, particularly when the target might not exist yet at script-authoring time.

If `--file` is specified but the target is a directory (or vice versa), the CLI logs a warning and proceeds with the user's explicit classification. This is a deliberate choice — the user may have a valid reason for the override (e.g., testing edge cases). The warning ensures visibility into the mismatch.

> **Deviation from original:** The original raises a fatal error when `-File` is specified but the path is not a file (`"The specified file does not exist"`). The port relaxes this to a warning when the explicit flag conflicts with the filesystem type, since the positional argument already validates path existence. The hard error remains only when the target path does not exist at all.

#### Recursion control: `--recursive` / `--no-recursive`

```python
@click.option("--recursive/--no-recursive", default=None)
```

Controls whether directory targets are traversed recursively. When omitted, the default is `True` (recursive), matching both the original's default behavior and the `IndexerConfig.recursive` default (§7.1).

For file targets, the recursion flag is silently ignored — there is nothing to recurse into. The original enforces this the same way (the `-Recursive` switch has no effect when `-File` is specified).

The `None` default (tri-state: `True`, `False`, or unspecified) allows the CLI to distinguish between "user explicitly requested non-recursive" and "user didn't specify" — relevant for configuration layering (§7.7), where a user config file setting `recursive = false` should be overridden by an explicit `--recursive` CLI flag but not by the CLI's default.

### 8.3. Output Mode Options

Output mode is controlled by three independent boolean flags that compose naturally. This replaces the original's seven-scenario routing matrix (§6.9) with a simpler model: each flag independently enables a destination, and any combination is valid.

#### `--stdout` / `--no-stdout`

```python
@click.option("--stdout/--no-stdout", default=None)
```

Enables or disables writing the complete JSON output to `sys.stdout`. The tri-state default (`None`) triggers the output mode defaulting logic defined in §7.1:

- If neither `--outfile` nor `--inplace` is specified and the user did not pass `--no-stdout`, stdout is enabled.
- If `--outfile` or `--inplace` is specified, stdout is disabled unless the user explicitly passes `--stdout`.

This matches the original's behavior where `StandardOutput` defaults to `True` when no output files are specified, and defaults to `False` when `OutFile` or `OutFileInPlace` is present.

> **Improvement over original:** The original provides both `-StandardOutput` and `-NoStandardOutput` switches — a positive and negative flag for the same boolean, requiring a 10-line sanity check to resolve conflicts. The port uses `click`'s built-in flag pair syntax (`--stdout/--no-stdout`), which enforces mutual exclusion at the parser level and produces the correct tri-state value without manual conflict resolution.

#### `--outfile`, `-o`

```python
@click.option("--outfile", "-o", type=click.Path(dir_okay=False, writable=True), default=None)
```

Specifies a file path for the combined JSON output. The complete index entry tree is serialized and written to this file after all processing is complete (§6.9, timing of writes). The path is resolved to an absolute form before being stored in `IndexerConfig.output_file`.

If the parent directory of the specified path does not exist, the CLI raises a `click.BadParameter` error. The tool does not create parent directories — this is a deliberate safety choice to prevent accidental writes to unexpected locations.

If the file already exists, it is overwritten without prompting. The original behaves the same way (`Out-File -Force`).

#### `--inplace`

```python
@click.option("--inplace", is_flag=True, default=False)
```

Enables writing individual sidecar JSON files alongside each processed item during traversal (§6.9, timing of writes). File entries receive sidecar files named `<id>.<extension>_meta2.json`. Directory entries receive sidecar files named `<id>_directorymeta2.json`. The `2` suffix in the sidecar filenames distinguishes v2 sidecar output from any pre-existing v1 sidecar files (`_meta.json`, `_directorymeta.json`), preventing filename collisions during a transition period where both v1 and v2 indexes may coexist in the same directory tree.

### 8.4. Metadata Processing Options

These three flags control metadata extraction and sidecar file handling. They form an implication chain: `--meta-merge-delete` implies `--meta-merge`, which implies `--meta`. The configuration loader (§7.1) enforces these implications — the CLI passes only the flags the user explicitly specified, and the loader propagates the chain.

#### `--meta`, `-m`

```python
@click.option("--meta", "-m", is_flag=True, default=False)
```

Enables embedded metadata extraction via `exiftool`. When active, the `metadata` array of each file entry's `IndexEntry` includes an entry with `source: "exiftool"` containing the exiftool output (§5.10). When inactive, the `metadata` array contains only sidecar-derived entries (if `--meta-merge` is also inactive, the array is empty or absent depending on the target type).

If `exiftool` is not available on the system `PATH`, the `--meta` flag does not cause a fatal error. A single warning is emitted at startup, and all EXIF metadata fields are populated with `null` for the entire invocation (§4.5, exiftool availability).

#### `--meta-merge`

```python
@click.option("--meta-merge", is_flag=True, default=False)
```

Enables sidecar metadata merging. When active, sidecar metadata files discovered alongside indexed files are parsed and merged into the parent file's `metadata` array as entries with `origin: "sidecar"` (§6.7). The sidecar files themselves remain on disk — they are not deleted. Implies `--meta`.

#### `--meta-merge-delete`

```python
@click.option("--meta-merge-delete", is_flag=True, default=False)
```

Extends `--meta-merge` by queuing the original sidecar files for deletion after their content has been merged into the parent entry's metadata array. Deletion occurs during Stage 6 (post-processing, §4.1), after all indexing is complete and all output has been written.

This flag carries a safety requirement: at least one persistent output mechanism (`--outfile` or `--inplace`) MUST be active when `--meta-merge-delete` is specified. Without a persistent output, the sidecar file content would be captured only in stdout — which is volatile and cannot be reliably recovered. If this safety condition is not met, the CLI exits with a fatal configuration error before any processing begins (§7.1, validation rules).

> **Deviation from original:** The original silently disables MetaMergeDelete when the safety condition is not met (`$MetaMergeDelete = $false`) and continues processing. The port treats this as a fatal error. The rationale: silently disabling a destructive flag is surprising behavior that could lead a user to believe their sidecar files are safe for manual deletion when they are not. An explicit error forces the user to acknowledge the safety requirement.

### 8.5. Rename Option

#### `--rename`

```python
@click.option("--rename", is_flag=True, default=False)
```

Enables the StorageName rename operation (§6.10): files are renamed from their original names to their hash-based `storage_name` values (e.g., `photo.jpg` → `yA8A8C089A6A8583B24C85F5A4A41F5AC.jpg`). Directories are not renamed — this matches the original's behavior. The `--rename` flag implies `--inplace`, because the in-place sidecar file written alongside each renamed item serves as the reversal manifest (containing the original filename in `name.text`).

The rename operation is destructive — the original filename is lost on disk. The in-place sidecar is the recovery mechanism. This implication is enforced by the configuration loader (§7.1): `rename=True` → `output_inplace=True`.

#### `--dry-run`

```python
@click.option("--dry-run", is_flag=True, default=False)
```

Previews rename operations without executing them. When active, the rename module computes and logs the target path for each file but does not perform the actual `Path.rename()` call. The in-place sidecar files are still written (using the would-be new path), and the `IndexEntry` still contains the `storage_name`. This allows users to inspect the sidecar output and verify the rename plan before committing.

The `--dry-run` flag is only meaningful when `--rename` is also active. If `--dry-run` is specified without `--rename`, it is silently ignored — there is nothing to preview.

> **Improvement over original:** The original does not support dry-run for renames. The port adds this as a safety feature, particularly valuable for users running rename operations on large directory trees for the first time.

### 8.6. ID Type Selection

#### `--id-type`

```python
@click.option("--id-type", type=click.Choice(["md5", "sha256"], case_sensitive=False), default=None)
```

Selects which hash algorithm is used to derive the `id` field of each `IndexEntry`. The `id` field is the primary unique identifier for an item — it determines the `storage_name` (for rename operations), the in-place sidecar filename, and the parent identity reference in child entries.

Valid values are `md5` and `sha256`. The input is case-insensitive (`MD5`, `Md5`, `md5` are all accepted and normalized to lowercase). When omitted, the value is resolved from the configuration file or the compiled default (`"md5"`, §7.2).

Both MD5 and SHA256 hashes are always computed regardless of this setting (§6.3). This flag is a presentation choice — it selects which pre-computed hash is promoted to the `id` field. The full `HashSet` containing all computed algorithms is always available in the entry's `hashes` sub-objects.

> **Deviation from original:** The original defaults `IdType` to `"SHA256"`. The port defaults to `"md5"` (§7.1). MD5 produces shorter identifiers (32 hex characters vs. 64), resulting in shorter `storage_name` values and shorter sidecar filenames. For the identity use case (uniquely naming files within a local index), MD5's collision resistance is more than sufficient. Users who prefer SHA256 identifiers can set `--id-type sha256` or configure it in the TOML file.

#### `--compute-sha512`

```python
@click.option("--compute-sha512", is_flag=True, default=False)
```

Includes SHA-512 in the computed `HashSet` for all indexed items. SHA-512 is excluded from the default hash computation because it produces 128-character hex strings that significantly inflate output size without serving a practical purpose for most indexing use cases. When this flag is active, the `sha512` field of every `HashSet` in the output is populated; when inactive, the field is omitted (§5.2.1).

SHA-512 computation is folded into the same single-pass read used for MD5 and SHA-256 (§6.3), so the marginal CPU cost is minimal. The flag controls output inclusion, not computation strategy.

### 8.7. Verbosity and Logging Options

#### `-v`, `--verbose`

```python
@click.option("-v", "--verbose", count=True)
```

Increases logging verbosity. The flag is repeatable — each occurrence increases the detail level by one step. Logging output is written to `stderr`, keeping `stdout` clean for JSON output.

| Flag | Effective log level | Description |
|------|-------------------|-------------|
| (none) | `WARNING` | Default. Only warnings and errors are emitted. |
| `-v` | `INFO` | Progress messages: items processed, traversal decisions, output destinations. |
| `-vv` | `DEBUG` | Detailed internal state: hash values, exiftool commands, sidecar discovery, configuration resolution. |
| `-vvv` | `DEBUG` (all) | Maximum verbosity. Includes all `DEBUG` messages including internal timing and per-item trace data. |

The mapping from `-v` count to Python `logging` level is:

```python
log_level = {0: logging.WARNING, 1: logging.INFO}.get(verbose, logging.DEBUG)
```

Any count ≥ 2 maps to `DEBUG`. The distinction between `-vv` and `-vvv` is handled within the logging configuration by enabling or disabling specific logger names, not by defining additional log levels.

> **Deviation from original:** The original uses a binary `$Verbosity` boolean (`$true`/`$false`). The port adopts a graduated verbosity model consistent with Unix CLI conventions and Python's `logging` framework. The original's `$Verbosity = $true` maps approximately to `-v` (INFO level) in the port.

#### `-q`, `--quiet`

```python
@click.option("-q", "--quiet", is_flag=True, default=False)
```

Suppresses all logging output except fatal errors. Equivalent to setting the log level to `CRITICAL`. When `--quiet` is active, only errors that prevent the tool from producing output are emitted to `stderr`.

If both `--verbose` and `--quiet` are specified, `--quiet` wins. This follows the principle that silence is an explicit request and should not be overridden by another flag.

### 8.8. Mutual Exclusion Rules and Validation

The CLI validates flag combinations before passing them to the configuration loader. Some validations are enforced by `click` declaratively; others are checked programmatically in the CLI's main function body.

#### Parser-level enforcement (handled by `click`)

| Constraint | Mechanism |
|-----------|-----------|
| `--file` and `--directory` are mutually exclusive | `click.option("--file/--directory")` flag pair |
| `--recursive` and `--no-recursive` are mutually exclusive | `click.option("--recursive/--no-recursive")` flag pair |
| `--stdout` and `--no-stdout` are mutually exclusive | `click.option("--stdout/--no-stdout")` flag pair |
| `--id-type` accepts only `md5` or `sha256` | `click.Choice(["md5", "sha256"])` |
| `--verbose` and `--quiet` coexistence | Programmatic: `--quiet` overrides `--verbose` |

#### Programmatic validation (checked before config construction)

| Rule | Behavior |
|------|----------|
| `--meta-merge-delete` requires `--outfile` or `--inplace` | Fatal error with exit code 2 (§8.10). Error message explains the safety requirement. |
| `--dry-run` without `--rename` | Silently ignored. No error, no warning — the flag simply has no effect. |
| `TARGET` does not exist | Fatal error raised by `click.Path(exists=True)` before main function body executes. |
| `--outfile` parent directory does not exist | Fatal error raised by the CLI after path resolution. |

#### Implication propagation (handled by configuration loader)

The CLI does NOT perform implication propagation itself. It passes the user's raw flag values to the configuration loader (§7.1), which applies the implication chain:

- `--rename` → `output_inplace = True`
- `--meta-merge-delete` → `meta_merge = True`
- `--meta-merge` → `extract_exif = True`

The CLI communicates these implications to the user through log messages at the `INFO` level when an implied flag is activated. For example, when the user specifies `--rename` without `--inplace`, the log emits: `"--rename implies --inplace; enabling in-place output"`. This visibility mirrors the original's `Vbs` warnings for the same conditions.

### 8.9. Output Scenarios

The three output flags (`--stdout`, `--outfile`, `--inplace`) compose into all valid output configurations. The following table enumerates the practical scenarios, mapped to the original's seven-scenario numbering for traceability.

| Scenario | Flags | Stdout | Outfile | Inplace | Original equivalent |
|----------|-------|--------|---------|---------|-------------------|
| 1 (default) | (none) | ✓ | — | — | Scenario 1: `StandardOutput` only |
| 2 | `--outfile index.json` | — | ✓ | — | Scenario 2: `OutFile` only |
| 3 | `--outfile index.json --stdout` | ✓ | ✓ | — | Scenario 3: `OutFile` + `StandardOutput` |
| 4 | `--inplace` | — | — | ✓ | Scenario 4: `OutFileInPlace` only |
| 5 | `--outfile index.json --inplace` | — | ✓ | ✓ | Scenario 5: `OutFile` + `OutFileInPlace` |
| 6 | `--inplace --stdout` | ✓ | — | ✓ | Scenario 6: `OutFileInPlace` + `StandardOutput` |
| 7 | `--outfile index.json --inplace --stdout` | ✓ | ✓ | ✓ | Scenario 7: all three |
| Silent | `--no-stdout` | — | — | — | Original: `NoStandardOutput` without output files |

The "Silent" scenario (no output of any kind) is valid but produces a warning: `"No output destinations are enabled. The indexing operation will execute but produce no output."` The original similarly warns when this condition occurs. The scenario is not prevented because it can be useful for side-effect-only invocations (e.g., `--rename` without needing the JSON output) or for measuring indexing performance without I/O overhead.

#### Example invocations

```bash
# Index the current directory recursively, output to stdout (default)
shruggie-indexer

# Index a specific directory, write to a file
shruggie-indexer /path/to/photos --outfile index.json

# Index a single file with metadata extraction
shruggie-indexer /path/to/photo.jpg --meta

# Index recursively with metadata merge, write in-place sidecars
shruggie-indexer /path/to/media --meta-merge --inplace

# Rename files to storage names (dry run)
shruggie-indexer /path/to/files --rename --dry-run -v

# Merge and delete sidecars, write both in-place and aggregate
shruggie-indexer /path/to/archive --meta-merge-delete --outfile archive.json --inplace

# Index non-recursively with SHA-256 identifiers
shruggie-indexer /path/to/dir --no-recursive --id-type sha256

# Index with maximum verbosity and custom config
shruggie-indexer /path/to/dir -vvv --config my-config.toml

# Quiet mode — errors only, output to file
shruggie-indexer /path/to/dir --outfile out.json -q
```

### 8.10. Exit Codes

The CLI uses structured exit codes to communicate outcome status to calling processes. Exit codes are integers in the range 0–4.

| Code | Name | Meaning |
|------|------|---------|
| 0 | `SUCCESS` | Indexing completed successfully. All requested items were processed and all output destinations were written. |
| 1 | `PARTIAL_FAILURE` | Indexing completed with one or more item-level errors. The output was produced but some items may have degraded fields (null hashes, missing metadata) or may have been skipped entirely. The count of failed items is logged at the `WARNING` level. |
| 2 | `CONFIGURATION_ERROR` | The invocation failed before any processing began due to invalid configuration: invalid flag combination (e.g., `--meta-merge-delete` without a persistent output), unreadable configuration file, invalid TOML syntax, or unrecognized `--id-type` value. No output is produced. |
| 3 | `TARGET_ERROR` | The target path does not exist, is not accessible, or is neither a file nor a directory. This is the exit code produced when `click.Path(exists=True)` rejects the target, or when the resolved target fails classification (§4.6). No output is produced. |
| 4 | `RUNTIME_ERROR` | An unexpected error occurred during processing that prevented the tool from completing. This covers unhandled exceptions, filesystem errors that affect the entire operation (e.g., the output file path becomes unwritable mid-operation), or `exiftool` crashes that propagate beyond the per-item error boundary. Partial output may exist for `--inplace` mode (sidecar files written before the failure); `--stdout` and `--outfile` output is not produced. |

Exit codes are defined as an `IntEnum` in `cli/main.py`:

```python
from enum import IntEnum

class ExitCode(IntEnum):
    SUCCESS = 0
    PARTIAL_FAILURE = 1
    CONFIGURATION_ERROR = 2
    TARGET_ERROR = 3
    RUNTIME_ERROR = 4
```

The `main()` function wraps the entire invocation in a `try`/`except` structure that maps exception types to exit codes:

```python
# Illustrative — not the exact implementation.
def main():
    try:
        # ... click CLI setup, config construction, index_path() call ...
        if failed_items > 0:
            sys.exit(ExitCode.PARTIAL_FAILURE)
        sys.exit(ExitCode.SUCCESS)
    except ConfigurationError:
        sys.exit(ExitCode.CONFIGURATION_ERROR)
    except TargetError:
        sys.exit(ExitCode.TARGET_ERROR)
    except Exception:
        logger.exception("Unexpected error during indexing")
        sys.exit(ExitCode.RUNTIME_ERROR)
```

> **Improvement over original:** The original does not define exit codes. It uses PowerShell's default `return` behavior, which yields `$null` for most error conditions and relies on `Vbs` log messages for error visibility. Scripts calling `MakeIndex` cannot programmatically distinguish between "completed with warnings" and "failed entirely." The port's structured exit codes enable reliable error handling in automation pipelines.

#### Exit code interaction with `--quiet`

When `--quiet` is active, the exit code becomes the primary signal for success or failure. The calling process MUST inspect `$?` (shell) or the subprocess return code (Python) to determine the outcome. Fatal error messages (exit codes 2–4) are still emitted to `stderr` even in quiet mode — `--quiet` suppresses informational and warning messages, not fatal errors.

#### Exit code interaction with `--inplace`

Because `--inplace` writes sidecar files incrementally during traversal (§6.9), a `RUNTIME_ERROR` (exit code 4) does not necessarily mean zero output was produced. Sidecar files written before the failure point are valid and usable. Calling processes that use `--inplace` SHOULD handle exit code 4 by checking for partial sidecar output rather than assuming complete failure.

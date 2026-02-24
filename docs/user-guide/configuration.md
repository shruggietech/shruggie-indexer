# Configuration

shruggie-indexer uses a layered configuration system. All behavior is configurable without editing source code, and the tool operates correctly with no configuration file — sensible defaults are built in.

## Configuration Hierarchy

Configuration values are resolved in the following order. Higher-priority layers override lower-priority ones:

| Priority | Source | Description |
|----------|--------|-------------|
| 1 (lowest) | Compiled defaults | Built into the tool. Always present. |
| 2 | User config file | Platform-standard location (see below). |
| 3 | Project-local config file | `.shruggie-indexer.toml` in the target directory or its ancestors. |
| 4 (highest) | CLI flags / API arguments | Command-line options or `load_config(overrides=...)`. |

### Config file locations

| Platform | User config path |
|----------|-----------------|
| Linux / macOS | `~/.config/shruggie-indexer/config.toml` |
| Windows | `%APPDATA%\shruggie-indexer\config.toml` |

Project-local config files (`.shruggie-indexer.toml`) are searched starting from the target directory and walking up to the filesystem root.

To specify a config file explicitly from the command line:

```bash
shruggie-indexer path/to/target --config my-config.toml
```

## Configuration File Format

Configuration files use [TOML](https://toml.io/) format, parsed by Python's built-in `tomllib` module (Python 3.11+).

### Complete example

The following shows all available configuration options with their default values:

```toml
# ── Traversal and identity ──────────────────────────────────

[traversal]
recursive = true
id_algorithm = "md5"         # "md5" or "sha256"
compute_sha512 = false

# ── Output routing ──────────────────────────────────────────

[output]
stdout = true                # Conditional default (see docs)
# file = "index.json"       # No default; set to enable file output
inplace = false

# ── Metadata processing ────────────────────────────────────

[metadata]
extract_exif = false
meta_merge = false
meta_merge_delete = false

# ── Rename ──────────────────────────────────────────────────

[rename]
enabled = false
dry_run = false

# ── Logging ─────────────────────────────────────────────────

[logging]
file_enabled = false         # Enable persistent log file output
# file_path = ""             # Empty = default app data directory

# ── Extension validation ───────────────────────────────────

[extensions]
validation_pattern = '^(([a-z0-9]){1,2}|([a-z0-9])([a-z0-9\-]){1,12}([a-z0-9]))$'

# ── Filesystem exclusion filters ───────────────────────────

[filesystem_excludes]
names = [
    "$recycle.bin",
    "system volume information",
    "desktop.ini",
    "thumbs.db",
    ".ds_store",
    ".spotlight-v100",
    ".trashes",
    ".fseventsd",
    ".temporaryitems",
    ".documentrevisions-v100",
    ".git",
]
globs = [".trash-*"]

# ── ExifTool configuration ─────────────────────────────────

[exiftool]
exclude_extensions = ["csv", "htm", "html", "json", "tsv", "xml"]
# exclude_keys = [...]          # Replace the entire key exclusion set (advanced)
# exclude_keys_append = [...]   # Append additional keys to the default exclusion set
base_args = [
    "-extractEmbedded3",
    "-scanForXMP",
    "-unknown2",
    "-json",
    "-G3:1",
    "-struct",
    "-ignoreMinorErrors",
    "-charset", "filename=utf8",
    "-api", "requestall=3",
    "-api", "largefilesupport=1",
    "--",
]

# ── Extension groups ────────────────────────────────────────

# Seven groups: archive, audio, font, image, link, subtitles, video
# Each maps to a list of lowercase extensions (without leading dots).
# See the technical specification §7.3 for the complete default lists.
```

## Default Configuration Values

### Scalar defaults

| Setting | Default | Description |
|---------|---------|-------------|
| `traversal.recursive` | `true` | Recurse into subdirectories. |
| `traversal.id_algorithm` | `"md5"` | Hash algorithm for the `id` field. |
| `traversal.compute_sha512` | `false` | Compute SHA-512 (not computed by default for performance). |
| `output.stdout` | `true` (conditional) | Write to stdout when no other output is specified. |
| `output.inplace` | `false` | Write in-place sidecar files. |
| `metadata.extract_exif` | `false` | Extract embedded metadata via ExifTool. |
| `metadata.meta_merge` | `false` | Merge sidecar metadata into parent entries. |
| `metadata.meta_merge_delete` | `false` | Merge and delete sidecar files. |
| `rename.enabled` | `false` | Rename files to storage names. |
| `rename.dry_run` | `false` | Preview rename operations. |

### Extension validation pattern

The default pattern accepts extensions of 1–2 alphanumeric characters, or 3–14 characters where the first and last are alphanumeric and interior characters may include hyphens:

```
^(([a-z0-9]){1,2}|([a-z0-9])([a-z0-9\-]){1,12}([a-z0-9]))$
```

Extensions that fail validation are recorded in the output's `extension` field but are treated as unrecognized for ExifTool processing purposes.

### Logging configuration

The `[logging]` section controls persistent log file output. By default, shruggie-indexer does not write log files — diagnostic output goes to stderr (CLI) or the in-app log panel (GUI).

| Key | Default | Description |
|-----|---------|-------------|
| `logging.file_enabled` | `false` | Enable persistent log file output. |
| `logging.file_path` | `""` (empty) | Path to the log file. Empty uses the default platform-specific directory. |

**Default log directory by platform:**

| Platform | Directory |
|----------|-----------|
| Windows | `%LOCALAPPDATA%\ShruggieTech\shruggie-indexer\logs\` |
| macOS | `~/Library/Application Support/ShruggieTech/shruggie-indexer/logs/` |
| Linux | `~/.local/share/shruggie-indexer/logs/` |

Log files are named by date and session: `YYYY-MM-DD_HHMMSS.log`. The log file format includes timestamps, session ID, log level, logger name, and message:

```
2026-02-23 14:30:02  abc123  INFO      shruggie_indexer.core.hasher  Hashing file: photo.jpg
```

The CLI equivalent is the `--log-file` flag. In the GUI, enable "Write log files" in Settings.

### Filesystem exclusion defaults

The default exclusion set covers system artifacts across all supported platforms:

| Platform | Excluded items |
|----------|---------------|
| Windows | `$RECYCLE.BIN`, `System Volume Information`, `desktop.ini`, `Thumbs.db` |
| macOS | `.DS_Store`, `.Spotlight-V100`, `.Trashes`, `.fseventsd`, `.TemporaryItems`, `.DocumentRevisions-V100` |
| Linux | `.Trash-*` (glob pattern) |
| All | `.git` |

All platform-specific exclusions are applied regardless of the current platform, ensuring clean output from cross-platform network shares and external drives.

### ExifTool exclusion defaults

These file extensions are skipped for ExifTool invocation because ExifTool tends to dump the entire file content rather than extracting meaningful metadata:

`csv`, `htm`, `html`, `json`, `tsv`, `xml`

## MetadataFileParser Configuration

The metadata file parser configuration controls how sidecar files are discovered and classified. It defines the regex patterns that match sidecar filenames and the behavioral attributes for each type.

### Recognized sidecar types

| Type | Description | Data handling |
|------|-------------|---------------|
| `description` | Text description files (youtube-dl `.description`) | JSON → text → binary fallback |
| `desktop_ini` | Windows `desktop.ini` files | Text |
| `generic_metadata` | Generic config/metadata (`.cfg`, `.conf`, `.yaml`, `.meta`) | JSON → text → binary fallback |
| `hash` | Hash/checksum files (`.md5`, `.sha256`, `.crc32`) | Lines (non-empty lines only) |
| `json_metadata` | JSON metadata (`.info.json`, `.meta.json`) | JSON |
| `link` | URL shortcuts (`.url`), filesystem shortcuts (`.lnk`) | URL/path extraction |
| `screenshot` | Screen capture images | Base64-encoded binary |
| `subtitles` | Subtitle tracks (`.srt`, `.sub`, `.vtt`, `.lrc`) | JSON → text → binary fallback |
| `thumbnail` | Thumbnail/cover images (`.cover`, `.thumb`) | Base64-encoded binary |
| `torrent` | Torrent/magnet link files | Base64-encoded binary |

### Type identification patterns

Each sidecar type is identified by one or more regex patterns matched against the sibling filename. The patterns are applied in the order listed above — the first match wins.

Patterns are specified as regex strings in the configuration. All patterns are compiled with `re.IGNORECASE`. See the [Technical Specification §7.3](https://github.com/shruggietech/shruggie-indexer/blob/main/shruggie-indexer-spec.md) for the complete default pattern inventory, including the BCP 47 language code alternation for subtitle detection.

### Type behavioral attributes

Each sidecar type has behavioral attributes that control how its content is read:

| Attribute | Description |
|-----------|-------------|
| `expect_json` | Attempt JSON parsing first. |
| `expect_text` | Attempt UTF-8 text reading. |
| `expect_binary` | Attempt binary reading (Base64 encode). |
| `parent_can_be_file` | This sidecar type can be associated with a file. |
| `parent_can_be_directory` | This sidecar type can be associated with a directory. |

For types where multiple formats are expected, the reader attempts formats in order: JSON → text → binary, falling through on parse failures.

## ExifTool Exclusion Lists

### Extension exclusions

`exiftool.exclude_extensions` controls which file types are skipped for ExifTool invocation. Default: `["csv", "htm", "html", "json", "tsv", "xml"]`.

### Key exclusions

After ExifTool returns metadata, certain operational and OS-specific keys are filtered out before storage. Because exiftool with `-G` flags emits group-prefixed keys (e.g. `System:FileName`), the filter matches by **base key name** (the portion after the last `:` separator).

The key exclusion set is configurable via two TOML keys:

| Config key | Behavior |
|------------|----------|
| `exiftool.exclude_keys = [...]` | **Replace** — the specified list becomes the complete exclusion set. |
| `exiftool.exclude_keys_append = [...]` | **Append** — entries are added to the compiled default set below. |

Example — append additional keys:

```toml
[exiftool]
exclude_keys_append = ["Copyright", "Artist"]
```

Example — replace the entire set (advanced):

```toml
[exiftool]
exclude_keys = ["SourceFile", "Directory", "FileName"]
```

The compiled default exclusion set:

| Base key | Category |
|----------|----------|
| `ExifToolVersion` | ExifTool operational |
| `FileSequence` | ExifTool operational |
| `NewGUID` | ExifTool operational |
| `Now` | ExifTool operational |
| `ProcessingTime` | ExifTool operational |
| `Directory` | Filesystem path |
| `FileName` | Filesystem path |
| `FilePath` | Filesystem path |
| `BaseName` | Filesystem path |
| `SourceFile` | Filesystem path |
| `FilePermissions` | OS-specific |
| `FileSize` | Redundant (in `size` object) |
| `FileModifyDate` | Redundant (in `timestamps`) |
| `FileAccessDate` | Redundant (in `timestamps`) |
| `FileCreateDate` | Redundant (in `timestamps`) |
| `FileAttributes` | OS-specific |
| `FileDeviceNumber` | OS-specific |
| `FileInodeNumber` | OS-specific |
| `FileHardLinks` | OS-specific |
| `FileUserID` | OS-specific |
| `FileGroupID` | OS-specific |
| `FileDeviceID` | OS-specific |
| `FileBlockSize` | OS-specific |
| `FileBlockCount` | OS-specific |

All embedded metadata keys (e.g. `File:FileType`, `File:MIMEType`, `QuickTime:*`, `Composite:*`) are preserved.

## Override and Merging Behavior

### Scalar fields: last-writer-wins

The highest-priority layer that specifies a value wins. Omitted fields in a configuration file preserve the value from the layer below (ultimately the compiled default).

### Collection fields: replace by default, append on request

Collection fields (lists and sets) use two strategies depending on the key name:

| Config key | Behavior |
|------------|----------|
| `exclude_extensions = [...]` | **Replace** — the specified list becomes the complete set. |
| `exclude_extensions_append = [...]` | **Append** — entries are added to the existing set. |

This convention applies to all collection fields: `filesystem_excludes.names`, `filesystem_excludes.globs`, `exiftool.exclude_extensions`, `exiftool.exclude_keys`, `exiftool.base_args`, `metadata_exclude.patterns`, and `extension_groups.*`.

### Unknown fields

Unrecognized keys in configuration files are logged as a warning and ignored. They are not fatal errors, which allows forward compatibility when older tool versions encounter config files written for newer versions.

## Parameter Implications

Certain configuration values automatically enable dependent settings:

| If this is `true`... | ...then this is forced to `true` |
|---|---|
| `rename.enabled` | `output.inplace` |
| `metadata.meta_merge_delete` | `metadata.meta_merge` |
| `metadata.meta_merge` | `metadata.extract_exif` |

These implications are applied during configuration construction, after all layers are merged. The CLI logs the activated implications at `INFO` level when verbose output is enabled.

## Validation Rules

The configuration loader validates the fully-resolved configuration before returning:

1. **MetaMergeDelete safety:** If `meta_merge_delete` is `true`, at least one of `output.file` or `output.inplace` must also be `true`.
2. **ID type validity:** `id_algorithm` must be either `"md5"` or `"sha256"`.
3. **Regex compilation:** All regex strings in the metadata identification and exclusion pattern lists must compile without error.
4. **Path conflicts:** If `output.file` is specified, it must not point inside the target directory when `output.inplace` is also active.

Validation failures produce a fatal `IndexerConfigError` (CLI exit code 2).

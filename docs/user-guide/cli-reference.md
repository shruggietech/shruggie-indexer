# CLI Reference

`shruggie-indexer` is subcommand-based. If no subcommand is provided, `index` is used.

## Command Structure

```bash
shruggie-indexer [OPTIONS] COMMAND [ARGS]...
```

## Subcommands

- `index` (default): Index files/directories and emit JSON output
- `rollback`: Restore files from sidecar/aggregate metadata manifests

## Index Synopsis

```bash
shruggie-indexer index [OPTIONS] [TARGET]
```

## Output Options

- `--stdout/--no-stdout`
- `--outfile, -o PATH`
- `--inplace`
- `--dir-meta/--no-dir-meta`

In-place naming (v4):

- File outputs: `<filename>_idx.json`
- Directory outputs: `<dirname>_idxd.json`

## Metadata And Relationship Options

- `--meta, -m`: Extract embedded metadata via ExifTool
- `--no-sidecar-detection`: Disable relationship classification entirely
- `--cleanup-legacy-sidecars`: After successful in-place v4 writes, remove legacy output artifacts (`_meta.json`, `_meta2.json`, `_meta3.json`, etc.) in touched directories

The legacy merge/delete flags from pre-v4 releases are not part of the current CLI surface.

## Rename Options

- `--rename`
- `--dry-run`

Implication rule:

- `--rename` implies `--inplace`

## Identity Options

- `--id-type [md5|sha256]`
- `--compute-sha512`

## Encoding Options

- `--no-detect-encoding`
- `--no-detect-charset`

## Configuration And Logging

- `--config PATH`
- `-v/--verbose` (repeatable)
- `-q/--quiet`
- `--log-file [PATH]`

## Rollback Synopsis

```bash
shruggie-indexer rollback [OPTIONS] META2_PATH
```

The argument name is historical, but rollback accepts current v4 sidecar and aggregate files as inputs.

Key rollback options:

- `-t, --target PATH`
- `--source PATH`
- `--recursive`
- `--flat`
- `--dry-run`
- `--no-verify`
- `--force`
- `--skip-duplicates`
- `--no-restore-sidecars`

## Common Examples

```bash
# Index with in-place v4 output
shruggie-indexer index media/ --inplace

# Index with relationships disabled
shruggie-indexer index media/ --no-sidecar-detection --outfile index.json

# In-place write and remove old _meta* artifacts in touched directories
shruggie-indexer index media/ --inplace --cleanup-legacy-sidecars

# Rename (implies --inplace)
shruggie-indexer index media/ --rename

# Rollback from a sidecar set
shruggie-indexer rollback media/ --target restored/
```
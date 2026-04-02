# Rollback Guide

Rollback restores files from index outputs back to original names/paths.

## v4 Behavior

For v4 (`schema_version: 4`) inputs, rollback is a uniform file-copy workflow:

- resolve source bytes
- copy to target path
- restore timestamps

No sidecar reconstruction pipeline is required for native v4 entries.

## Input Shapes

Rollback accepts:

- Per-file sidecars (`*_idx.json`)
- Directory sidecars (`*_idxd.json`)
- Legacy sidecars (`*_meta2.json`, `*_meta3.json`)
- Directories containing sidecar files

## Legacy Compatibility

When loading legacy schema versions (2 or 3), rollback uses backward-compatible logic for old formats.

## CLI Examples

```bash
# Restore from a directory of sidecars
shruggie-indexer rollback vault/ --target restored/

# Flat restore
shruggie-indexer rollback vault/ --flat --target restored/

# Dry run
shruggie-indexer rollback vault/ --dry-run -v
```

## Cleanup Option (Index Side)

Legacy cleanup is triggered during indexing, not rollback:

```bash
shruggie-indexer index media/ --inplace --cleanup-legacy-sidecars
```

Cleanup removes old `_meta*.json` artifacts only when matching v4 replacements were written in the same run and directory scope.
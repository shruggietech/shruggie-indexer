# Quick Start

This guide covers common v4 workflows. For full details, see the [CLI Reference](../user-guide/cli-reference.md).

## Index a Single File

```bash
shruggie-indexer index path/to/file.jpg
```

## Index a Directory

```bash
shruggie-indexer index path/to/directory/
```

Disable recursion:

```bash
shruggie-indexer index path/to/directory/ --no-recursive
```

## Save Aggregate Output

```bash
shruggie-indexer index path/to/target --outfile index.json
```

## Write In-Place v4 Outputs

```bash
shruggie-indexer index path/to/directory/ --inplace
```

This produces `_idx.json` and `_idxd.json` files.

## Extract Embedded Metadata

```bash
shruggie-indexer index path/to/file.jpg --meta
```

When ExifTool is unavailable, indexing continues and generated metadata entries are omitted.

## Sidecar Relationship Classification

Sidecar detection is enabled by default. Files that match rules are annotated via `relationships[]`.

To disable relationship classification entirely:

```bash
shruggie-indexer index path/to/directory/ --no-sidecar-detection
```

## Clean Up Legacy Output Artifacts

After successful in-place v4 writes, optionally remove old `_meta*.json` outputs in touched directories:

```bash
shruggie-indexer index path/to/directory/ --inplace --cleanup-legacy-sidecars
```

## Rename to Deterministic Storage Names

```bash
shruggie-indexer index path/to/directory/ --rename --dry-run
```

Execute renames:

```bash
shruggie-indexer index path/to/directory/ --rename
```

`--rename` implies `--inplace`.

## Example v4 Output (Abbreviated)

```json
{
  "schema_version": 4,
  "id": "yA8A8C089A6A8583B24C85F5A4A41F5AC",
  "id_algorithm": "md5",
  "type": "file",
  "name": { "text": "video.info.json", "hashes": { "md5": "...", "sha256": "..." } },
  "extension": "json",
  "size": { "text": "6.21 KB", "bytes": 6358 },
  "hashes": { "md5": "...", "sha256": "..." },
  "file_system": { "relative": "video.info.json", "parent": { "id": "x...", "name": { "text": "media", "hashes": { "md5": "...", "sha256": "..." } } } },
  "timestamps": {
    "created": { "iso": "2026-04-01T10:12:20.000000-05:00", "unix": 1775056340000 },
    "modified": { "iso": "2026-04-01T10:12:20.000000-05:00", "unix": 1775056340000 },
    "accessed": { "iso": "2026-04-01T10:12:20.000000-05:00", "unix": 1775056340000 }
  },
  "attributes": { "is_link": false, "storage_name": "yA8A8C089A6A8583B24C85F5A4A41F5AC.json" },
  "relationships": [
    {
      "target_id": "yF19...",
      "type": "json_metadata",
      "rule": "yt-dlp-info",
      "rule_source": "builtin",
      "confidence": 3,
      "predicates": []
    }
  ],
  "metadata": null
}
```

## Next Steps

- [CLI Reference](../user-guide/cli-reference.md)
- [Configuration](../user-guide/configuration.md)
- [Schema Reference](../schema/index.md)
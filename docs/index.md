# shruggie-indexer

shruggie-indexer indexes files and directories into structured JSON with deterministic identity hashes, filesystem evidence, optional ExifTool metadata, and v4 relationship annotations for sidecar-like files.

The v4 architecture treats every discovered file as a first-class `IndexEntry`. Instead of ingesting sidecar files into parent metadata, the indexer records believed associations in `relationships[]`.

## Key Features

- Deterministic hash-based identity for files and directories (`id`, `id_algorithm`, `storage_name`)
- Recursive filesystem inventory with platform-aware timestamps and path normalization
- Optional ExifTool extraction into `metadata[]` (`origin: "generated"`)
- Sidecar relationship classification via rule engine (`relationships[]` with rule source, confidence, predicate detail)
- Uniform rename and rollback workflows across all files
- v4 output sidecar conventions: `_idx.json` (file scope), `_idxd.json` (directory scope)
- CLI, GUI, and Python API frontends backed by one core engine

## Quick Example

```bash
shruggie-indexer index path/to/library --inplace
```

This writes v4 per-item outputs beside indexed content:

- `movie.mkv_idx.json`
- `movie.mkv.info.json_idx.json`
- `videos_idxd.json`

If sidecar detection is enabled (default), sidecar-like entries may include:

```json
"relationships": [
  {
    "target_id": "yABC...",
    "type": "json_metadata",
    "rule": "yt-dlp-info",
    "rule_source": "builtin",
    "confidence": 3,
    "predicates": []
  }
]
```

## Documentation

- [Getting Started](getting-started/installation.md)
- [User Guide](user-guide/index.md)
- [Schema Reference](schema/index.md)
- [Porting Reference](porting-reference/index.md)
- [Changelog](changelog.md)

## Quick Links

- [GitHub Repository](https://github.com/shruggietech/shruggie-indexer)
- [V4 JSON Schema (canonical)](https://schemas.shruggie.tech/data/shruggie-indexer-v4.schema.json)
- [Local v4 schema copy](schema/shruggie-indexer-v4.schema.json)
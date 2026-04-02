# Schema Reference

The current output contract is schema v4.

## Canonical Schemas

- v4 (current): [https://schemas.shruggie.tech/data/shruggie-indexer-v4.schema.json](https://schemas.shruggie.tech/data/shruggie-indexer-v4.schema.json)
- Local v4 copy: [shruggie-indexer-v4.schema.json](shruggie-indexer-v4.schema.json)
- v2 (legacy reference): [shruggie-indexer-v2.schema.json](shruggie-indexer-v2.schema.json)

## Top-Level Model

Each `IndexEntry` represents exactly one indexed filesystem item.

Required identity and structure fields include:

- `schema_version` (const `4`)
- `id`, `id_algorithm`, `type`
- `name`, `extension`, `size`, `hashes`
- `file_system`, `timestamps`, `attributes`

Optional fields include:

- `items`
- `metadata`
- `relationships`
- `duplicates`
- `encoding`, `mime_type`, `session_id`, `indexed_at`

## Relationship Annotations

`relationships[]` is present only when a rule match exists.

`RelationshipAnnotation` fields:

- `target_id`: referenced related entry ID
- `type`: relationship classification (for example `json_metadata`, `subtitles`)
- `rule`: matched rule name
- `rule_source`: `builtin`, `user`, or `pack:<name>`
- `confidence`: integer enum `1|2|3`
- `predicates`: array of `PredicateResult`

`PredicateResult` fields:

- `name` (required)
- `satisfied` (required)
- `pattern` (optional)
- `patterns` (optional)

Confidence semantics:

- `3`: all predicates satisfied, or no predicates declared
- `2`: partial predicate satisfaction
- `1`: no predicates satisfied

## MetadataEntry in v4

`MetadataEntry` remains available for generated metadata (for example ExifTool output), while sidecar relationships are represented in `relationships[]` instead of sidecar-ingested metadata records.

## Removed/Restructured v2/v3-Era Concepts

In the v4 model, active output no longer relies on:

- legacy `_meta2.json` / `_meta3.json` naming for new outputs
- sidecar ingest/merge as primary representation
- pre-v4 merge/delete operation modes

Legacy artifacts remain relevant only for compatibility workflows.

## Output File Naming

- File entries: `<name>_idx.json`
- Directory entries: `<dirname>_idxd.json`

## Examples

- [flashplayer.exe_idx.json](examples/flashplayer.exe_idx.json)
- [deduplicated_idx.json](examples/deduplicated_idx.json)
- [video.info.json_idx.json](examples/video.info.json_idx.json)
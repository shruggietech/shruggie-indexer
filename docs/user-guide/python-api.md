# Python API

The CLI and GUI both call the same core Python API.

## Primary Entry Points

```python
from shruggie_indexer import index_path, load_config, serialize_entry
```

- `load_config(...)` resolves layered config
- `index_path(...)` builds an `IndexEntry` tree
- `serialize_entry(...)` renders JSON output

## v4 Data Model Highlights

- `IndexEntry.schema_version` is `4`
- `IndexEntry.relationships` is optional and present when a file matches relationship rules
- `MetadataEntry` is simplified for v4-generated metadata usage
- Relationship annotations use:
  - `RelationshipAnnotation`
  - `PredicateResult`

## Config Fields Of Interest

- `no_sidecar_detection: bool`
- `cleanup_legacy_sidecars: bool`
- `sidecar_rules: tuple[SidecarRuleConfig, ...]`

Legacy pre-v4 merge/delete configuration knobs are no longer part of the active API guidance.

## Example: Index With Relationships Enabled

```python
from pathlib import Path
from shruggie_indexer import index_path, load_config

config = load_config(overrides={
    "extract_exif": True,
    "no_sidecar_detection": False,
})

entry = index_path(Path("media"), config)
print(entry.schema_version)  # 4
```

## Example: Disable Relationship Detection

```python
config = load_config(overrides={"no_sidecar_detection": True})
entry = index_path("media", config)
```

When disabled, entries omit `relationships`.

## Rule Authoring Note

Define relationship rules in TOML via `[sidecar_rules.<name>]` and load them through `load_config(config_file=...)`.

## Rollback API

```python
from shruggie_indexer import load_sidecar, plan_rollback, execute_rollback
```

Rollback supports v4 sidecars and legacy v2/v3 compatibility paths.
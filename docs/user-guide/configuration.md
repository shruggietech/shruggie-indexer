# Configuration

shruggie-indexer uses layered TOML configuration.

Priority order (low to high):

1. Compiled defaults
2. User config file
3. Project-local `.shruggie-indexer.toml`
4. CLI/API overrides

## v4-Oriented Keys

- `no_sidecar_detection` (bool, default `false`): disable relationship classification
- `cleanup_legacy_sidecars` (bool, default `false`): remove legacy output artifacts after successful v4 in-place writes
- `write_directory_meta` (bool, default `true`): emit directory `_idxd.json` outputs in in-place mode

Legacy merge/delete configuration keys from pre-v4 releases are no longer active.

## Example

```toml
[traversal]
recursive = true
id_algorithm = "md5"
compute_sha512 = false

[output]
stdout = true
inplace = false
write_directory_meta = true

[metadata]
extract_exif = false
no_sidecar_detection = false
cleanup_legacy_sidecars = false

[rename]
enabled = false
dry_run = false
```

Note: CLI/API fields map directly to internal config names (`no_sidecar_detection`, `cleanup_legacy_sidecars`).

## Sidecar Rules

User rules are declared under `[sidecar_rules.<rule_name>]`.

Supported fields:

- `match` (required when enabled)
- `type` (required when enabled)
- `scope` (`"file"` or `"directory"`, default `"file"`)
- `requires_sibling`
- `requires_sibling_any`
- `excludes_sibling`
- `min_siblings` (reserved; ignored in current confidence computation)
- `enabled` (default `true`)
- `extends` (for override/disable workflows)

### Example: Add Custom Rule

```toml
[sidecar_rules.custom-notes]
match = "{stem}.notes.txt"
type = "generic_metadata"
scope = "file"
requires_sibling = "{stem}.*"
```

### Example: Override Built-In Rule

```toml
[sidecar_rules.yt-dlp-info]
extends = "yt-dlp-info"
match = "{stem}.info.json"
type = "json_metadata"
scope = "file"
requires_sibling = "{stem}.mp4"
```

### Example: Disable Built-In Rule

```toml
[sidecar_rules.any-url]
extends = "any-url"
enabled = false
```

## Rule Resolution Order

1. User rules
2. Pack rules (`pack:<name>`)
3. Built-in rules

First matching rule wins.

## Community Rule Packs

Packs are TOML files loaded from the pack directory and evaluated between user and built-in rules. Pack CLI management is planned; current workflow is manual installation.

## Legacy Note

`metadata_identify` is legacy and ignored in v4; migrate to `sidecar_rules`.
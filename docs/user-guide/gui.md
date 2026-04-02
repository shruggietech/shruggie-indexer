# Desktop Application Guide

The GUI is a visual frontend over the same core engine used by CLI and Python API.

## Operation Types

The operation dropdown has two values:

- `Index`
- `Rollback`

Meta Merge and Meta Merge Delete are no longer available operations in v4.

## Index Workflow

1. Select a file or directory target.
2. Choose output mode (`View only`, `Single file`, or `Multi-file`).
3. Configure options such as `Extract EXIF metadata`, `Rename files`, and hash preferences.
4. Run the job and review Output/Log tabs.

Relationship classification is automatic in Index mode unless sidecar detection is disabled in configuration.

## Output Conventions

When in-place output is active, the GUI writes:

- File scope: `<filename>_idx.json`
- Directory scope: `<dirname>_idxd.json`

Legacy `_meta*.json` naming is not used for new output.

## Rename Behavior

- Rename is available with `Index` operations.
- Enabling rename performs deterministic storage-name renames and dedup-aware handling where applicable.
- Dry-run can preview rename activity without disk mutations.

## Rollback Workflow

Rollback restores files from sidecar/aggregate metadata sources and supports:

- Flat restore
- Hash verification toggle
- Force overwrite
- Skip duplicates
- Restore sidecars toggle (legacy path support)

Rollback result output is a human-readable summary plus execution log.

## Session Compatibility

If a saved session contains legacy pre-v4 merge operation values, the GUI falls back to `index` on load.

## Notes For Future UI Review

With only two operation types, a segmented control may eventually replace the dropdown. Current behavior intentionally preserves layout stability.
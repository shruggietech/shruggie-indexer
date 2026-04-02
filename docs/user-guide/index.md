# User Guide

The User Guide documents runtime behavior for the v4 architecture.

Core model summary:

- Every discovered file is indexed as its own `IndexEntry`.
- Sidecar-like relationships are annotated via `relationships[]`.
- In-place outputs use `_idx.json` and `_idxd.json`.
- GUI operations are now `Index` and `Rollback` only.

## Sections

- [Desktop Application](gui.md)
- [CLI Reference](cli-reference.md)
- [Configuration](configuration.md)
- [Python API](python-api.md)
- [Rollback Guide](rollback.md)
- [Platform Notes](platform-notes.md)
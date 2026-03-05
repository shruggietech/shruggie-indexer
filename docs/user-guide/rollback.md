# Rollback Guide

The rollback feature reverses shruggie-indexer rename and de-duplication operations by reading `_meta2.json` sidecar files and restoring files to their original names, directory structure, and timestamps. It also reconstructs absorbed sidecar metadata files that were consumed by MetaMergeDelete.

Rollback is available via the CLI (`shruggie-indexer rollback`), the GUI (Rollback operation type), and the Python API (`plan_rollback()`, `execute_rollback()`).

!!! tip "Non-Destructive"
    Rollback only **copies** files to the target directory. Source files and sidecar manifests remain untouched. You inspect the result and clean up originals manually.

---

## How It Works

Rollback operates in two phases:

1. **Plan** — `plan_rollback()` reads the sidecar metadata and computes the full set of file operations (copies, directory creations, sidecar reconstructions) without touching the filesystem.
2. **Execute** — `execute_rollback()` carries out the plan. In dry-run mode, it logs every action without writing anything.

This plan-then-execute pattern gives you dry-run, inspection, and selective execution for free.

---

## Scenario Walkthroughs

### Single Renamed File

You indexed and renamed a file:

```
vault/yA8A8C089A6A8583B24C85F5A4A41F5AC.exe          ← renamed content
vault/yA8A8C089A6A8583B24C85F5A4A41F5AC.exe_meta2.json  ← sidecar manifest
```

The sidecar records that the original filename was `setup-installer.exe`. To restore it:

```bash
shruggie-indexer rollback vault/yA8A8C089A6A8583B24C85F5A4A41F5AC.exe_meta2.json
```

Result (default target = parent of meta2 file):

```
vault/setup-installer.exe   ← restored with original name
```

The `mtime` and `atime` on the restored file are set from the sidecar's timestamp fields.

### Renamed Directory

You indexed an entire directory tree with `--rename --inplace`:

```
vault/
├── yAAA.jpg
├── yAAA.jpg_meta2.json
├── yBBB.png
├── yBBB.png_meta2.json
└── x1234/
    ├── yCCC.txt
    ├── yCCC.txt_meta2.json
    └── x1234_directorymeta2.json
```

The sidecars record original names and `file_system.relative` paths. To restore the full tree:

```bash
shruggie-indexer rollback vault/ --target restored/
```

Result:

```
restored/
├── photos/
│   └── beach.jpg          ← from file_system.relative
├── documents/
│   └── readme.txt
└── notes.txt
```

The directory structure is faithfully reconstructed from the `file_system.relative` field of each entry.

### Deduplicated Files

You had three identical copies of `report.pdf` that were de-duplicated during rename. The canonical entry's sidecar contains a `duplicates` array with the other two entries:

```bash
shruggie-indexer rollback vault/yDDD.pdf_meta2.json --target restored/
```

Result — all three copies are restored:

```
restored/
├── reports/Q1/report.pdf       ← canonical
├── reports/Q2/report.pdf       ← duplicate restored
└── archive/old-report.pdf      ← duplicate restored
```

Each restored copy has the same bytes (copied from the single canonical file) but its own original name, path, and timestamps.

To restore only canonical entries without duplicates:

```bash
shruggie-indexer rollback vault/yDDD.pdf_meta2.json --skip-duplicates --target restored/
```

### Aggregate Output

You produced an aggregate output file (`_directorymeta2.json`) containing the full directory tree. The content files are in a separate vault directory:

```bash
shruggie-indexer rollback output/photos_directorymeta2.json \
    --source vault/ \
    --target restored/
```

The `--source` flag tells the engine where to find the content files (by `storage_name`). The tree structure is reconstructed from the aggregate's nested `items[]` hierarchy.

### Non-Renamed Files

Not all indexed files are renamed. If a file was indexed without `--rename`, the sidecar still records its metadata. Rollback handles this transparently — the `LocalSourceResolver` looks for the file by `storage_name` first, then falls back to `name.text`. Non-renamed files are simply copied with their original name:

```bash
shruggie-indexer rollback vault/readme.txt_meta2.json --target restored/
```

Result:

```
restored/readme.txt   ← same name, timestamps restored from sidecar
```

### Mixed-Session Chimera

When rollback processes sidecars from multiple distinct indexing sessions in structured mode, the `file_system.relative` paths may not share a common root — each session had its own index root. The planner detects this and emits a warning:

```
WARNING: 3 entries span 3 distinct indexing sessions. Relative paths may not
share a common root. Restored directory tree may be incoherent. Consider using
--flat or specifying --target explicitly.
```

The operation proceeds — the warning is advisory. If the result is incoherent, use flat mode instead:

```bash
shruggie-indexer rollback mixed-sidecars/ --flat --target flat_output/
```

!!! note "Warning suppression"
    The mixed-session warning is NOT emitted in flat mode, because `file_system.relative` is ignored entirely.

### Flat Mode

Flat mode (`--flat`) ignores the `file_system.relative` field and restores every file directly into the target directory using only `name.text`:

```bash
shruggie-indexer rollback vault/ --flat --target flat_output/
```

Result:

```
flat_output/
├── beach.jpg
├── readme.txt
└── notes.txt
```

No subdirectories are created. This is useful for:

- **Vault delivery** — Delivering a single file or small batch to an end user without the original directory context.
- **Mixed-session input** — When sidecars from different sessions produce incoherent relative paths.
- **Simplicity** — When you just want the original filenames back.

**Collision handling:** If two entries have the same `name.text`, the second is skipped with a warning:

```
WARNING: Flat restore collision: beach.jpg already exists in target
(from a different entry). Skipped.
```

Switch to structured mode or use a different target to resolve collisions.

### Default Target Behavior

The `--target` flag is optional. When omitted, the target defaults to:

| Input shape | Default target |
|---|---|
| Single meta2 file (`/vault/yAAA.jpg_meta2.json`) | `/vault/` (parent of the file) |
| Directory of sidecars (`/vault/`) | `/vault/` (the directory itself) |
| Aggregate output file (`/output/photos_directorymeta2.json`) | `/output/` (parent of the file) |

This enables single-command in-place rollback:

```bash
# No --target needed — restores into the same directory
shruggie-indexer rollback vault/yABC.jpg_meta2.json
```

### Vault Delivery Use Case

The `shruggie-vault` project uses the rollback API programmatically to deliver files to end users in their original form. The typical flow is:

1. **Look up** — Find the file in the vault catalog by content hash.
2. **Retrieve** — Locate the renamed file and its sidecar in the vault.
3. **Rollback** — Use `plan_rollback(flat=True)` to compute a flat restore into a delivery directory.
4. **Deliver** — The file at the delivery path has its original name and timestamps.

```python
from pathlib import Path
from shruggie_indexer import load_meta2, plan_rollback, execute_rollback

entries = load_meta2(Path("/vault/yABC.jpg_meta2.json"))
plan = plan_rollback(
    entries,
    target_dir=Path("/delivery/output"),
    source_dir=Path("/vault"),
    flat=True,
)
result = execute_rollback(plan)
# /delivery/output/original-photo.jpg is ready for the user
```

The `SourceResolver` protocol enables custom retrieval logic — a vault implementation could download files from remote storage before the rollback copies them to the delivery directory.

---

## Sidecar Reconstruction

When MetaMergeDelete absorbs sidecar files (e.g., `.info.json`, `.description`), their content is preserved in the parent entry's `metadata` array as `MetadataEntry` objects with `origin == "sidecar"`. Rollback reconstructs these files from the stored data:

| `attributes.format` | Restoration |
|---|---|
| `"json"` | JSON (style-aware — see below) |
| `"text"` | UTF-8 text |
| `"base64"` | Base64-decoded binary |
| `"lines"` | Lines joined with newlines (UTF-8) |

### JSON Style Preservation

JSON sidecar files are restored using the formatting style recorded during indexing. The `attributes.json_style` field controls the output:

- **`"pretty"`** — Indented JSON (`indent=2`), matching the original's whitespace convention.
- **`"compact"`** — Minified JSON (no whitespace), preserving the original's compact representation.
- **Absent** — Defaults to compact serialization for backward compatibility with entries created before `json_style` tracking was added.

This prevents compact JSON sidecars (e.g., minified `.info.json` files) from inflating in size during rollback.

Sidecar reconstruction is on by default. Use `--no-restore-sidecars` to skip it.

---

## Timestamp Restoration

Rollback restores file timestamps from the sidecar's `timestamps` object:

- **`mtime`** (modified time) — Set from `timestamps.modified.unix` via `os.utime()`.
- **`atime`** (accessed time) — Set from `timestamps.accessed.unix` via `os.utime()`.
- **`ctime`** (creation time, Windows only) — Set from `timestamps.created.unix` via `ctypes.windll.kernel32` (`CreateFileW` / `SetFileTime` / `CloseHandle`). This uses only the Python standard library and requires no external dependency. On non-Windows platforms, creation time restoration is not attempted (POSIX provides no standard API for setting file creation time).

Sidecar timestamps are stored as millisecond Unix timestamps; they are divided by 1000 before passing to `os.utime()`.

---

## Hash Verification

By default, the rollback engine verifies the content hash of each source file against the value recorded in the sidecar before copying. This catches:

- **Corruption** — The file was modified after indexing.
- **Wrong file** — A different file occupies the expected path.

A hash mismatch logs a warning but does not prevent the restore (the file is still copied). Use `--no-verify` to skip hash computation entirely for faster operation.

---

## Conflict Resolution

When the target path already exists:

| Situation | Behavior |
|---|---|
| Target exists, same content hash | Skipped (logged at DEBUG). |
| Target exists, different content | Skipped with WARNING, unless `--force` is active. |
| `--force` active | Target is overwritten. |
| Flat mode, same `name.text` from different entries | Second entry skipped with WARNING. |

---

## Error Handling

- **Source not found** — If the content file cannot be located, the entry is skipped with a warning. Other entries continue processing.
- **Copy failure** — If `shutil.copy2()` fails (permissions, disk full), the error is logged and the entry is marked as failed. Other entries continue processing.
- **Path traversal** — If `file_system.relative` contains `..` segments that would escape the target directory, the entry is rejected.
- **v1 sidecars** — If a sidecar lacks `schema_version` or has `schema_version != 2`, loading fails with a clear error directing the user to the future `migrate` tool.

---

## CLI Quick Reference

```bash
# Restore a single renamed file
shruggie-indexer rollback vault/yABC.jpg_meta2.json

# Restore into a specific directory
shruggie-indexer rollback vault/ --target restored/

# Flat restore (no directory structure)
shruggie-indexer rollback vault/ --flat --target flat_output/

# Dry-run preview
shruggie-indexer rollback vault/ --dry-run -v

# Restore from aggregate with explicit source
shruggie-indexer rollback output/photos_directorymeta2.json --source vault/ --target restored/

# Skip duplicates, force overwrite
shruggie-indexer rollback vault/ --skip-duplicates --force --target restored/

# Recursive directory search
shruggie-indexer rollback vault/ --recursive --target restored/
```

See the [CLI Reference](cli-reference.md#rollback-options) for the full option set.

---

## Legacy Compatibility

Rollback automatically handles `_meta2.json` files produced by older indexer versions that computed `file_system.relative` from the *parent* of the target directory (prepending the target's own name as a prefix).

When all loaded entries share a common first path component matching the source directory name, rollback detects this as a legacy prefix and strips it before planning. An informational log message is emitted:

```
INFO: Detected legacy relative path prefix 'data'. Stripping prefix for rollback.
```

This ensures files are restored directly under the target directory without an extra nesting level, regardless of which indexer version produced the sidecar files.

---

## Session-ID Validation

When `_meta2.json` files from multiple indexing sessions coexist in the same directory (e.g., stale metadata from a prior run was not cleaned up), rollback detects content-hash collisions — entries where the same file content appears with the same `attributes.storage_name` but different `file_system.relative` paths. Two entries that share a content hash but have **different** storage names (e.g., byte-identical `slippers.gif` and `slippers.png`) are treated as distinct canonical files and are **not** flagged as collisions.

When a collision is detected, rollback applies tiebreaking rules:

1. **Majority session wins** — The entry whose `session_id` matches the most common session across all loaded entries is kept.
2. **Session over no session** — An entry with a `session_id` is preferred over one without.
3. **First encountered** — If neither has a `session_id`, the first entry is kept.

Discarded entries are logged at WARNING level with a message that accurately describes whether the collision is cross-session or intra-session. This prevents duplicate or misplaced file restores caused by stale metadata.

---

## Known Limitations

- **Empty directories are not reconstructed.** The indexer catalogues *files* and their containing directory hierarchy. Directories that contain no files (directly or transitively) produce no entries in `_meta2.json` output and therefore cannot be restored by rollback. This is intentional — shruggie-indexer focuses on the preservation and cataloguing of files, not the replication of directory trees.

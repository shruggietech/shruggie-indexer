## 16. Security and Safety

This section defines the security boundaries and safety mechanisms that protect the filesystem, the user's data, and the indexer's own output integrity during operation. The indexer is not a network-facing service and does not process untrusted input in the traditional web-security sense — its primary threat model involves unintended filesystem mutation, resource exhaustion, and data loss through operational error. The safeguards described here are engineering guardrails, not defense-in-depth against a hostile actor.

The indexer performs five categories of operation that carry safety implications: traversal across symlink boundaries (§16.1), path resolution from user-supplied and filesystem-derived strings (§16.2), temporary file creation during output writes (§16.3), destructive deletion of sidecar files during MetaMergeDelete (§16.4), and resource consumption when processing large files or deeply nested directory trees (§16.5). Each subsection specifies the threat, the mitigation, and the relationship to the behavioral contracts defined in earlier sections.

§6 (Core Operations) defines what each operation does. §4.5 (Error Handling Strategy) defines the per-item isolation model. §15 (Platform Portability) defines how platform-specific filesystem behaviors affect safety-relevant operations. This section consolidates the safety-specific aspects of those behaviors into a single normative reference for implementers and auditors.

### 16.1. Symlink Traversal Safety

#### Threat

Symbolic links introduce three categories of safety risk during filesystem traversal:

**Infinite recursion.** A directory symlink that targets an ancestor of itself creates a cycle. If the traversal follows the symlink, it enters an unbounded loop: `A/ → B/ → symlink-to-A/ → B/ → symlink-to-A/ → ...`. On the original Windows-only platform, this risk was limited to NTFS junctions and developer-mode symlinks. On Linux and macOS, symlinks are ubiquitous and cycles are trivially constructible.

**Scope escape.** A symlink inside the target directory may point to a location outside the intended indexing scope — a parent directory, a different filesystem, a sensitive system directory, or a network mount. Following the symlink would cause the indexer to read (and hash) file content that the user did not intend to include in the index.

**Dangling references.** A symlink whose target has been deleted or moved causes `stat()`, `open()`, and `resolve()` to fail with `FileNotFoundError` or `OSError`. If the traversal does not anticipate this, the failure may propagate beyond the item-level error boundary and abort the entire operation.

#### Mitigation: non-following traversal

The indexer does not follow symlinks during directory traversal. This is the single, comprehensive mitigation for all three risks.

`list_children()` (§6.1) enumerates directory contents using `os.scandir()` with `follow_symlinks=False` for entry classification. A symlink to a directory appears in the traversal results as a single item — it is processed as an `IndexEntry` with `attributes.is_link = True` and an empty `items` list. The traversal does not descend into the symlink target. A symlink to a file likewise appears as a single item with `is_link = True` and is processed using name hashing rather than content hashing (§6.3), since reading the target's content would follow the link.

This behavior is consistent with the original's `Get-ChildItem -Force` semantics, which do not follow symlinks into directories by default. The difference is intentionality: the original's non-following behavior is an emergent side effect of PowerShell's default `Get-ChildItem` behavior, while the port's non-following behavior is an explicit `follow_symlinks=False` parameter — a deliberate, testable design decision (§15.6).

#### Symlink processing boundaries

When a symlink is encountered during traversal, the following operations are affected:

| Operation | Symlink behavior | Rationale |
|---|---|---|
| Content hashing (`hash_file`) | Replaced by name hashing (`hash_string`) | Reading the target's content would follow the link. Name hashing produces an identity that depends on the link, not its target. |
| EXIF extraction (`extract_exif`) | Skipped — returns `None` | `exiftool` would follow the link to read the target file. Metadata from the target does not belong to the link. |
| Timestamp extraction | Uses `os.lstat()` instead of `os.stat()` | `lstat()` reads the symlink's own metadata without following the link. `stat()` would return the target's metadata (or raise `FileNotFoundError` for dangling links). |
| Path resolution (`resolve_path`) | Uses `Path.resolve(strict=False)` for the `file_system.absolute` field | `strict=False` normalizes the path without requiring the target to exist, handling dangling symlinks gracefully. |
| Directory descent | Not performed | The symlink entry has an empty `items` list regardless of whether the target is a directory. |

#### Dangling symlink handling

When `is_symlink()` returns `True` and the symlink target does not exist, the item is processed with degraded fields. The specific degradation:

- `hashes`: Populated from name hashing (which does not require the target to exist). Not `null`.
- `_id`: Derived from the name hash. Valid and deterministic.
- `size.bytes`: The value from `os.lstat().st_size` — the size of the symlink itself (0 on Windows, target-path-length on POSIX). Not the size of the (nonexistent) target.
- `timestamps`: From `os.lstat()`. Reflects the symlink's own filesystem metadata.
- `metadata`: Empty list — no EXIF extraction, no sidecar discovery (the item is a symlink).

A debug-level log message is emitted noting the dangling symlink. The entry is included in the output with no `null` fields — dangling symlinks are a normal condition, not an error.

#### Testing symlink safety

The test suite (§14) includes dedicated symlink safety tests in `tests/platform/`:

- **Cycle detection.** Create `A/ → B/ → link-to-A`. Index `A/` recursively. Verify that the traversal terminates, that the symlink entry has an empty `items` list, and that no infinite recursion occurs.
- **Scope boundary.** Create a symlink inside the target directory that points outside it. Verify that the external target is not hashed or traversed.
- **Dangling symlink.** Create a symlink whose target does not exist. Verify that the entry is populated with name hashes and `lstat()` timestamps, and that no exception propagates.

These tests use pytest markers for platform-conditional execution (§14.5) and handle the Windows symlink privilege requirement documented in §15.6.

### 16.2. Path Validation and Sanitization

#### Threat

The indexer processes paths from two sources: user-supplied target paths (from CLI arguments, GUI input, or API parameters) and filesystem-derived paths (from `os.scandir()` during traversal). Both sources can produce paths that are malformed, adversarial, or problematic for specific platforms.

Specific risks include path traversal components (`..`) that escape the intended scope, embedded null bytes that truncate strings in C-level filesystem calls, excessively long paths that exceed platform limits, and filenames containing characters that are legal on the source filesystem but illegal on the output filesystem (relevant when indexes are consumed cross-platform).

#### Target path validation (Stage 2)

The target path supplied by the user undergoes validation during Stage 2 of the processing pipeline (§4.1). The validation sequence:

1. **Resolution.** `resolve_path()` (§6.2) calls `Path.resolve(strict=True)`, which resolves symlinks, collapses `.` and `..` components, and produces a canonical absolute path. The `..` components are fully resolved by the OS before the indexer sees the path — there is no string-level `..` manipulation that an adversarial input could exploit.

2. **Existence check.** After resolution, `resolved.exists()` verifies that the path refers to an actual filesystem object. If the path does not exist, a `TargetError` is raised and the process exits with code 3 (§8.10). No traversal or file reading occurs.

3. **Type classification.** `resolved.is_file()` and `resolved.is_dir()` classify the target. If the target is neither a file nor a directory (e.g., a character device, a named pipe, or a socket), an `IndexerError` is raised. The indexer processes only regular files, directories, and symlinks to those types.

4. **Null byte rejection.** Python 3 raises `ValueError: embedded null character` when a `Path` object is constructed from a string containing `\x00`. This rejection happens before any filesystem call, preventing null-byte injection into OS-level path APIs. The port does not need to add explicit null-byte checking — Python's `pathlib` and `os` modules enforce this invariant automatically.

#### Filesystem-derived path handling

Paths returned by `os.scandir()` during traversal are filesystem-authoritative — they reflect the actual names stored by the filesystem and do not contain traversal components. No sanitization is applied to these paths because they originate from the filesystem kernel, not from user input. The entry builder (§6.8) processes them through the same `extract_components()` function (§6.2), which uses `pathlib` properties rather than string splitting, avoiding injection risks from filenames containing path separator characters.

#### Output path sanitization

The indexer writes output files to two categories of destination, each with its own path construction rules:

**Aggregate output file (`--outfile`).** The path is user-specified and resolved via `Path.resolve()` before writing. The configuration validation (§7.1, rule 3) rejects output paths that fall inside the target directory when `--inplace` is also active, preventing the output file from being indexed on subsequent runs. Beyond this conflict check, no further sanitization is applied — the user controls the output path.

**In-place sidecar files (`--inplace`).** Sidecar paths are constructed by `paths.build_sidecar_path()` (§6.2), which appends a fixed suffix (`_meta2.json` or `_directorymeta2.json`) to the item's existing path. The construction uses `pathlib` path arithmetic (`item_path.parent / sidecar_name`), not string concatenation. The sidecar filename is derived deterministically from the item filename, so there is no opportunity for path injection — a filename like `../../etc/passwd` on the filesystem would produce a sidecar named `../../etc/passwd_meta2.json` in the same directory (not a traversal to `/etc/`), because `pathlib`'s `/` operator joins relative to the parent, not relative to the working directory.

#### Rename path safety

The `rename_item()` function (§6.10) constructs the target path via `paths.build_storage_path()`, which joins the item's parent directory with its `storage_name`. Since `storage_name` is a hex string derived from a cryptographic hash (`y` + MD5/SHA256 hexdigest + optional extension), it cannot contain path separators, traversal components, or special characters. The only characters in a `storage_name` are `[a-zA-Z0-9.]`, making it safe for all target filesystems.

Collision detection (§6.10) verifies that the rename target does not already exist as a different file before executing the rename. This prevents accidental data loss from hash collisions (astronomically unlikely but guarded against at negligible cost) and from repeated runs where some files have already been renamed.

### 16.3. Temporary File Handling

#### Original approach and its problems

The original `MakeIndex` creates temporary files via `TempOpen` and deletes them via `TempClose` for a single purpose: passing exiftool arguments through an intermediary argfile. The `TempOpen` function writes to a fixed directory (`$D_PSLIB_TEMP = C:\bin\pslib\temp`) using a UUID-based naming scheme, and `TempClose` deletes the file by path. The `TempOpen` docstring warns that failing to call `TempClose` will leave orphaned temp files, and `TempClose -ForceAll` exists as a bulk cleanup mechanism — an acknowledgment that the manual open/close protocol is leak-prone.

This pattern has three safety problems. First, the fixed temp directory path (`C:\bin\pslib\temp`) is outside the standard OS temp location and requires manual creation — if the directory does not exist, `TempOpen` fails. Second, the manual open-then-close protocol has no automatic cleanup guarantee: an exception between `TempOpen` and `TempClose` leaks a temp file. Third, the entire pattern is unnecessary — subprocess argument passing does not require an intermediary file.

#### Port approach: elimination

The port eliminates temporary file creation entirely for the exiftool use case. Exiftool arguments are defined as a Python list and passed directly to `subprocess.run()` (§6.6, DEV-05). The `-@` argfile switch, the Base64 encoding/decoding pipeline, and the `TempOpen`/`TempClose` lifecycle are all removed. This is the cleanest safety improvement: no temporary files means no orphaned files, no cleanup races, no fixed-path dependencies.

#### Remaining temporary file scenarios

Two scenarios in the port may still involve temporary file creation:

**Atomic file writes.** When writing the aggregate output file (`--outfile`), the serializer SHOULD use an atomic write pattern: write to a temporary file in the same directory as the target, then rename the temporary file to the final path. This prevents partial writes from producing a corrupt output file if the process is interrupted during serialization. The implementation uses Python's `tempfile.NamedTemporaryFile(dir=target_dir, delete=False)` to create the temporary file in the correct directory (ensuring the rename is atomic on the same filesystem), writes the complete JSON content, calls `os.replace()` to atomically swap the file into place, and cleans up the temporary file in a `finally` block if the rename fails.

The `tempfile` module creates files with restrictive permissions (mode `0o600` on POSIX) and uses OS-provided mechanisms for unique naming, avoiding the collision and permission issues of the original's manual UUID scheme.

**Exiftool batch mode (future).** If the optional `PyExifTool` batch mode (§6.6) is implemented in a future optimization pass, it maintains a persistent exiftool process communicating via stdin/stdout pipes rather than argfiles. No temporary files are involved — the batch protocol is entirely in-memory.

#### Cleanup guarantee

For any scenario where temporary files are created, the port uses context managers or `try`/`finally` blocks to guarantee cleanup:

```python
# Illustrative — not the exact implementation.
import tempfile, os

def atomic_write(target_path: Path, content: str) -> None:
    target_dir = target_path.parent
    fd = None
    tmp_path = None
    try:
        fd = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_dir,
            suffix=".tmp",
            prefix=".shruggie-indexer-",
            delete=False,
        )
        tmp_path = Path(fd.name)
        fd.write(content)
        fd.flush()
        os.fsync(fd.fileno())
        fd.close()
        fd = None
        os.replace(tmp_path, target_path)
        tmp_path = None  # rename succeeded — nothing to clean up
    finally:
        if fd is not None:
            fd.close()
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
```

The `finally` block ensures that the temporary file is removed even if serialization fails, the process receives a signal, or an unexpected exception occurs. The `missing_ok=True` parameter to `unlink()` prevents a secondary exception if the file was already removed.

> **Improvement over original:** The original's `TempOpen`/`TempClose` protocol relies on manual discipline to avoid leaks. The port's context-manager approach makes cleanup automatic and exception-safe, consistent with Python's resource management conventions.

### 16.4. Metadata Merge-Delete Safeguards

#### Threat

MetaMergeDelete is the only destructive data operation in the indexer. When active, it deletes sidecar metadata files (`.info.json`, `.description`, thumbnails, subtitles, etc.) from the filesystem after their content has been merged into the parent item's `metadata` array. If the merged content is not persisted to a durable output — because no output file was specified, because the output file write failed, or because the process was interrupted before the output was committed — the sidecar data is irrecoverably lost. The original labels this risk explicitly: the `$MMDSafe` variable gates the entire operation on whether a persistent output mechanism is active.

#### Safeguard 1: Configuration-time output requirement

The configuration loader (§7.1, validation rule 1) enforces a hard prerequisite: if `meta_merge_delete` is `True`, at least one of `output_file` or `output_inplace` MUST also be `True`. This validation runs during Stage 1 — before any file is read, hashed, or modified. If the prerequisite is not met, the process terminates with exit code 2 (`CONFIGURATION_ERROR`) and a diagnostic message:

```
Error: --meta-merge-delete requires --outfile or --inplace to ensure
sidecar content is preserved before deletion.
```

This prevents the most straightforward data-loss scenario: a user running `shruggie-indexer --meta-merge-delete --stdout` (stdout-only output, no persistent file), where the sidecar content would exist only in the transient stdout stream.

The original enforces this via the `$MMDSafe` variable (lines ~9354–9427 in `MakeIndex`). The port's enforcement is equivalent but implemented as a declarative validation rule rather than an imperative flag check embedded in the output-routing logic.

#### Safeguard 2: Deferred deletion

Sidecar file deletion is deferred to Stage 6 of the processing pipeline (§4.1, §4.4) — after all indexing is complete and all output has been written. During Stage 3–4 traversal, the sidecar module (§6.7) appends each successfully merged sidecar's path to the delete queue (a `list[Path]` owned by the top-level orchestrator). The actual `Path.unlink()` calls happen only after the traversal loop exits and the serializer has finished writing all output.

This temporal separation provides an interruption safety window: if the process is killed during traversal (Ctrl+C, `SIGTERM`, system crash), no sidecar files have been deleted yet. The partially-written in-place sidecar files may be incomplete, but the original sidecar source files remain intact on disk. The user can re-run the indexer to produce a complete index without data loss.

The deferral order is:

1. All items traversed, all `IndexEntry` objects constructed, all in-place sidecar files written.
2. Aggregate output file written (if `--outfile` is active).
3. Delete queue drained: each sidecar path is unlinked.

Step 3 only executes if steps 1 and 2 complete without fatal error. If an unrecoverable error occurs during traversal or output writing, the delete queue is not drained and the sidecar files remain.

#### Safeguard 3: Per-file deletion error isolation

When draining the delete queue, each `Path.unlink()` call is wrapped in a `try`/`except`. If a single sidecar file cannot be deleted (permission denied, file already removed, filesystem error), the failure is logged as a warning and the queue continues with the next entry. A deletion failure for one sidecar does not prevent deletion of the remaining sidecars, and does not change the exit code from `SUCCESS` to a failure code — the indexing itself completed successfully; the deletion failure is a post-processing anomaly.

```python
# Illustrative — not the exact implementation.
def drain_delete_queue(queue: list[Path]) -> int:
    failed = 0
    for sidecar_path in queue:
        try:
            sidecar_path.unlink()
            logger.debug("Deleted sidecar: %s", sidecar_path)
        except OSError as exc:
            logger.warning("Failed to delete sidecar %s: %s", sidecar_path, exc)
            failed += 1
    return failed
```

If any deletions fail, the count is included in the final status log line so the user is aware that cleanup was incomplete.

#### Safeguard 4: v2 schema provenance for reversal

The v2 output schema (§5.10) enriches sidecar `MetadataEntry` objects with filesystem provenance fields (`file_system`, `size`, `timestamps`) that the v1 schema lacked. These fields record the sidecar file's original relative path, byte size, and modification timestamps at the time of merging. This provenance data serves as a reversal manifest: a future `revert` operation (§6.10) can reconstruct deleted sidecar files by writing the `data` field content back to the original path, restoring the file size, and setting the timestamps.

Without the v2 provenance fields, MetaMergeDelete would be a one-way operation — the merged data would be present in the parent entry's `metadata` array, but the information needed to reconstruct the original files (path, size, timestamps) would be lost. The v2 schema's enrichment is a safety feature, not merely a schema improvement.

The reversibility guarantee is structural: the provenance fields are populated for every sidecar entry with `origin: "sidecar"`, regardless of whether MetaMergeDelete is active. Even when MetaMerge (without Delete) is used, the provenance data is recorded, allowing a future Delete operation to be applied to an existing index without re-indexing.

#### Safeguard 5: Dry-run mode interaction

When `--dry-run` is active alongside `--rename`, the rename operation is simulated without executing (§6.10). However, `--dry-run` does NOT interact with MetaMergeDelete — there is no `--dry-run` equivalent for sidecar deletion. If a user requests `--meta-merge-delete --dry-run`, the `--dry-run` flag applies only to renames; sidecar deletion still occurs if the configuration validation passes.

This is a deliberate design constraint, not an oversight. Simulating MetaMergeDelete without actually deleting would produce the same output as MetaMerge (without Delete) — there is no observable difference in a dry-run. If a user wants to preview the effect of MetaMergeDelete, they should run with `--meta-merge` first (which merges without deleting), inspect the output to verify correctness, and then run with `--meta-merge-delete` to commit the deletion. The documentation SHOULD make this workflow explicit.

### 16.5. Large File and Deep Recursion Handling

#### Large file hashing

The primary resource risk during file hashing is memory consumption. A naïve implementation that reads an entire file into memory before hashing would fail catastrophically for files larger than available RAM. The port's `hash_file()` function (§6.3) reads files in fixed-size chunks (64 KB default, §17.2) and feeds each chunk to all active hash objects. Peak memory usage is bounded by the chunk size plus the hash objects' internal state — approximately 70 KB regardless of file size. A 100 GB video file and a 1 KB text file consume the same amount of memory during hashing.

The chunk-based approach also provides natural interruption points. If a `cancel_event` is checked between chunks (the GUI entry point may implement this for responsiveness), cancellation latency is bounded by the time to read one chunk, not the time to read the entire file.

No file size limit is enforced by the indexer. The practical ceiling is the filesystem's maximum file size (16 TB for NTFS, 16 TiB for ext4, 8 EiB for APFS). Files approaching these limits will take proportionally longer to hash, but the indexer will not run out of memory, crash, or produce incorrect results.

The `exiftool` invocation (§6.6) includes the `-api largefilesupport=1` argument in the default argument list (§7.4), which enables exiftool's large-file handling for files exceeding 2 GB. Without this flag, exiftool truncates metadata extraction at the 2 GB boundary for certain file formats.

#### Base64-encoded sidecar size

When the sidecar module (§6.7) reads a binary sidecar file (thumbnails, screenshots, torrent files) for Base64 encoding, the entire file is read into memory via `path.read_bytes()` and then Base64-encoded. Base64 encoding expands the data by approximately 33%, so a 100 MB thumbnail would consume roughly 133 MB of memory during encoding and remain in memory as part of the `MetadataEntry.data` field throughout the entry's lifetime.

For typical sidecar files — thumbnails are usually under 1 MB, torrent files under 10 MB — this is not a concern. For pathological cases where a user has multi-hundred-megabyte binary sidecars, memory consumption could become significant. The port does not implement streaming Base64 encoding for sidecar files because the encoded data must be held in memory as a JSON-serializable string regardless of how it was encoded. The mitigation is documentation: the user-facing documentation SHOULD note that very large binary sidecars contribute directly to memory usage and output file size, and that excluding them via the metadata exclusion configuration (§7.5) is appropriate when memory constraints are tight.

#### Deep directory recursion

Python's default recursion limit is 1,000 frames. The port's recursive traversal in `build_directory_entry()` (§6.8) adds one Python call frame per level of directory nesting. A directory tree nested 900 levels deep would approach the default recursion limit, and a 1,000-level tree would hit it, producing a `RecursionError`.

Directory trees deeper than a few hundred levels are virtually nonexistent in real-world filesystems. The deepest common nesting — `node_modules` dependency trees — rarely exceeds 30–50 levels. Nevertheless, the implementation SHOULD handle the edge case gracefully rather than crashing with an unhandled `RecursionError`.

Two mitigation strategies are available:

**Strategy A — Increase the recursion limit.** At the start of the indexing operation, call `sys.setrecursionlimit(max(sys.getrecursionlimit(), 10_000))`. This raises the ceiling to 10,000 levels, which exceeds any realistic directory depth. The cost is a trivially larger thread stack allocation.

**Strategy B — Iterative traversal.** Replace the recursive `build_directory_entry()` call with an iterative depth-first traversal using an explicit stack. This eliminates the recursion limit entirely and is the more robust approach, but it adds implementation complexity (the explicit stack must maintain the same parent–child assembly semantics as the recursive version).

The specification recommends **Strategy A** for the MVP, with a comment in the code noting that Strategy B is the long-term solution if the recursion limit proves insufficient. Strategy A is sufficient for all realistic workloads and requires a single line of code. Strategy B is a refactoring exercise that can be deferred without safety risk.

If a `RecursionError` does occur despite the raised limit, it is caught by the top-level exception handler (§8.10) and produces exit code 4 (`RUNTIME_ERROR`) with a diagnostic message suggesting that the user reduce directory depth or report the issue.

#### Large directory enumeration

A single directory containing a very large number of entries — tens or hundreds of thousands of files — does not pose a recursion risk but does affect memory usage and performance. `os.scandir()` returns an iterator that yields `DirEntry` objects lazily, so the directory listing is not loaded entirely into memory at once. However, the `list_children()` function (§6.1) collects all entries into two sorted lists (files and directories), which does materialize the full listing.

For a directory with 100,000 entries, the materialized lists consume approximately 10–20 MB of memory (one `Path` object per entry). This is within acceptable bounds for any system that can run the indexer. For directories with millions of entries — rare but possible on large media servers or backup volumes — the memory consumption scales linearly and may become significant on constrained systems.

The port does not implement streaming or batched entry processing for single-directory enumeration. The sorted-list approach is required for deterministic output ordering (§6.1), and the memory overhead is proportional to the directory size, not the total tree size. A directory with 1,000,000 files but only 10 levels of nesting requires ~100 MB for the single largest directory listing, not for the entire tree.

#### JSON serialization memory

For recursive directory indexing, the complete `IndexEntry` tree is held in memory until serialization is complete (§6.9). The tree's memory footprint is proportional to the total number of items indexed multiplied by the average entry size. A rough estimate: each `IndexEntry` consumes 2–5 KB of memory (hash strings, paths, timestamps, metadata references), so a tree of 100,000 items occupies 200–500 MB.

For very large trees (millions of items), this memory footprint may exceed available RAM. The mitigation is the `--inplace` output mode, which writes each item's sidecar file immediately after construction and does not require the full tree to be held in memory simultaneously. When `--inplace` is the sole output mode (no `--stdout`, no `--outfile`), the entry builder can release child entries after writing their sidecars, reducing peak memory to the depth of the tree rather than its breadth.

This streaming release optimization is not required for MVP. The MVP implementation MAY hold the full tree in memory for all output modes. The optimization SHOULD be implemented in a performance pass if users report memory issues with large trees. The architectural separation between entry construction (§6.8) and serialization (§6.9) supports this optimization without structural changes — the serializer already writes in-place sidecars during traversal, so the change is to release the child reference after the write completes.

The `--outfile` and `--stdout` output modes inherently require the full tree in memory (the aggregate JSON document must be complete before serialization). For users indexing very large trees, the documentation SHOULD recommend `--inplace` as the memory-efficient alternative, with a post-processing step to aggregate the individual sidecar files if a single output document is needed.

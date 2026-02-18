## 17. Performance Considerations

This section defines the performance characteristics, optimization strategies, and resource consumption boundaries of `shruggie-indexer`. It is the normative reference for how the indexer manages computational cost across its five performance-sensitive operations: cryptographic hashing, file I/O, directory enumeration, JSON serialization, and external process invocation. Each subsection describes the optimization approach, the rationale behind the chosen strategy, the measurable impact relative to the original implementation, and the bounds within which the optimization holds.

The original `MakeIndex` has no documented performance design — its performance characteristics are emergent side effects of implementation choices made for convenience (separate file reads per hash algorithm, piping through `jq`, writing Base64-encoded arguments to temporary files for exiftool). The port improves on three of these incidental costs significantly and maintains parity on the others. This section makes the performance design explicit so that implementers do not inadvertently regress to the original's approach and so that future optimization work can target the areas with the highest payoff.

§6 (Core Operations) defines what each operation does. §14.7 (Performance Benchmarks) defines how performance is measured and what the baseline expectations are. §16.5 (Large File and Deep Recursion Handling) defines the resource consumption safety boundaries. This section sits between those references — it explains *why* the implementation is structured for performance, *how* the key optimizations work, and *where* the remaining performance bottlenecks lie.

### 17.1. Multi-Algorithm Hashing in a Single Pass

#### The problem

The indexer computes multiple cryptographic hash digests for every file: MD5 and SHA256 by default, with SHA512 as an opt-in (§6.3). A naïve implementation — computing each algorithm in a separate pass — reads the file from disk once per algorithm. For a 1 GB file with two algorithms, this means 2 GB of I/O. For three algorithms, 3 GB. File I/O is overwhelmingly the dominant cost of hashing for any file larger than a few kilobytes; the CPU time spent computing digests is negligible by comparison. The naïve multi-pass approach doubles or triples the I/O cost for zero additional information — every pass reads the same bytes.

This is exactly what the original does. `FileId` defines independent sub-functions for each algorithm (`FileId-HashMd5`, `FileId-HashSha256`, etc.), each of which opens the file via `[System.IO.File]::OpenRead()`, reads it to completion, computes the digest, and closes the file. When two algorithms are requested (the default), the file is opened, read, and closed twice. The .NET `CryptoStream` class supports chaining multiple hash transforms on a single stream, but the original does not use this capability.

#### The optimization

The port reads each file exactly once, regardless of how many hash algorithms are active. `hash_file()` (§6.3) creates one `hashlib` hash object per algorithm, reads the file in chunks, and feeds each chunk to every hash object before reading the next chunk:

```python
# Illustrative — not the exact implementation.
def hash_file(path: Path, algorithms: tuple[str, ...] = ("md5", "sha256")) -> HashSet:
    hashers = {alg: hashlib.new(alg) for alg in algorithms}
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            for h in hashers.values():
                h.update(chunk)
    return HashSet(**{alg: h.hexdigest().upper() for alg, h in hashers.items()})
```

The key insight is that `hashlib` hash objects accept incremental `update()` calls — they maintain internal state across multiple chunk submissions and produce the same digest as if the entire content had been submitted in a single call. This is a property of all Merkle–Damgård hash constructions (which MD5, SHA-1, SHA-256, and SHA-512 all are). The per-chunk CPU cost of calling `update()` on N hash objects is linear in N, but the per-chunk I/O cost is constant — the same bytes are in memory regardless of how many hash objects consume them.

#### Impact

For the default two-algorithm case (MD5 + SHA256), the single-pass approach halves total file I/O compared to the original. For the three-algorithm case (MD5 + SHA256 + SHA512), it reduces I/O to one-third. The absolute time savings depend on storage throughput: on an SSD reading at 500 MB/s, hashing a 1 GB file takes approximately 2 seconds in single-pass versus approximately 4 seconds in dual-pass. On spinning disks (100–150 MB/s) or network storage, the savings are proportionally larger because the I/O penalty of additional passes is more severe.

The CPU overhead of feeding each chunk to multiple hash objects is negligible. Python's `hashlib` delegates to OpenSSL's C implementations, which process a 64 KB chunk in microseconds. The overhead of iterating a 2- or 3-element dict per chunk is immeasurable relative to the `read()` system call latency.

#### When this matters — and when it does not

The single-pass optimization has no impact for string hashing (`hash_string()`) or directory identity computation (`hash_directory_id()`), both of which operate on short in-memory byte sequences that are hashed instantaneously. The optimization is meaningful only for `hash_file()` on files large enough that I/O time dominates — roughly, files larger than 100 KB. For smaller files, the cost is dominated by file-open/close overhead, and the difference between one pass and two is imperceptible. The benchmarks in §14.7 validate this expectation: the small-file benchmark (1 KB) measures < 10 ms regardless of algorithm count, while the large-file benchmark (100 MB) measures throughput that approaches raw `hashlib` speed.

### 17.2. Chunked File Reading

#### Chunk size selection

`hash_file()` reads files in fixed-size chunks of 65,536 bytes (64 KB). This value is not configurable — it is an implementation constant internal to `core/hashing.py`.

The chunk size represents a balance between two opposing costs. Smaller chunks increase the number of `read()` system calls per file, each of which carries kernel-transition overhead. Larger chunks increase the per-read memory allocation and, past the OS file cache page size, offer diminishing returns because the OS prefetcher is already streaming data ahead of the application's read position. Python's `hashlib` documentation recommends chunk sizes between 4 KB and 128 KB for stream hashing. Empirical testing on Linux (ext4, SSD) and Windows (NTFS, SSD) shows throughput plateaus above approximately 32 KB; 64 KB was chosen as a comfortable margin above the plateau that works well across all three target platforms.

The following data points informed the selection:

| Chunk size | Approximate throughput (SHA256, SSD) | Notes |
|------------|--------------------------------------|-------|
| 4 KB | ~200 MB/s | Syscall overhead visible. |
| 16 KB | ~400 MB/s | Improving rapidly. |
| 32 KB | ~480 MB/s | Near plateau. |
| 64 KB | ~500 MB/s | At plateau. Chosen value. |
| 128 KB | ~500 MB/s | No further gain. |
| 1 MB | ~500 MB/s | No further gain; higher per-chunk memory. |

These figures are illustrative and vary by platform, filesystem, and storage medium. The 64 KB value is not performance-critical in the sense that a different choice would produce a dramatically different outcome — any value between 32 KB and 256 KB produces comparable throughput. The value is fixed rather than configurable because exposing it as a tuning parameter invites cargo-cult optimization without measurable benefit and adds configuration complexity for no user-facing gain.

#### Memory bound

The chunk-based approach bounds peak memory consumption during hashing to approximately `CHUNK_SIZE` (64 KB) plus the internal state of the active hash objects (a few hundred bytes each). A 100 GB file and a 100-byte file consume the same peak memory during hashing. This property is the memory safety guarantee described in §16.5 — the hashing module cannot cause an out-of-memory condition regardless of file size.

The chunk boundary also provides natural interruption points. If the GUI entry point implements a cancellation check between chunks (§10.5), cancellation latency is bounded by the time to read one 64 KB chunk — under 1 millisecond on any local storage device. This responsiveness is not achievable with a whole-file-read approach.

### 17.3. Large Directory Tree Handling

#### Traversal performance

The traversal module (`core/traversal.py`, §6.1) enumerates directory contents using `os.scandir()` in a single pass. This is both a correctness improvement and a performance improvement over the original's dual-pass `Get-ChildItem` approach.

The original performs two separate `Get-ChildItem` calls per directory — one with the `-File` flag to retrieve files, one with the `-Directory` flag to retrieve directories. Each call independently enumerates the entire directory, applies its filter, and returns the matching subset. For a directory with 10,000 entries, this means two complete readdir traversals, two complete filter passes, and two result-set materializations. The data that distinguishes files from directories (the `d_type` field in POSIX `readdir`, the `dwFileAttributes` field in Windows `FindNextFile`) is available on both passes but only consulted on one.

The port's `os.scandir()` reads the directory once. Each `DirEntry` object returned by `scandir` caches the file/directory classification from the underlying OS call, so `entry.is_file(follow_symlinks=False)` and `entry.is_dir(follow_symlinks=False)` resolve without an additional `stat()` call on platforms that provide `d_type` (Linux, macOS) or `dwFileAttributes` (Windows). Classification and separation into the files and directories lists happen in a single iteration.

For a directory with N entries, the original performs 2 × O(N) directory reads plus 2 × O(N) filter passes. The port performs 1 × O(N) directory read plus 1 × O(N) classification pass. On spinning disks where directory reads are seek-limited, or on network filesystems where each readdir round-trip has latency, the single-pass approach can be up to twice as fast for large directories.

#### Sorting cost

After enumeration, the port sorts both the file list and the directory list lexicographically by name (case-insensitive). The sort uses Python's Timsort (`sorted()` with a `key` function), which runs in O(N log N) for N entries. For 10,000 entries, this is approximately 130,000 comparisons — completed in milliseconds. For 100,000 entries, approximately 1.7 million comparisons — still well under one second. The sorting cost is negligible relative to the per-item entry construction cost (hashing, stat, potential exiftool invocation).

The original does not explicitly sort — `Get-ChildItem` returns entries in filesystem order (which on NTFS is B-tree sorted, but on ext4 and APFS is effectively directory-creation order). The port's explicit sort ensures deterministic output ordering across platforms, at a cost that is imperceptible for any realistic directory size.

#### Memory consumption during traversal

`list_children()` materializes the complete file and directory lists for each directory being processed. For a directory with N entries, this allocates approximately N `Path` objects — each consuming roughly 100–200 bytes of Python heap (the object header plus the string path data). A directory with 100,000 entries thus requires 10–20 MB of memory for the materialized lists.

This memory is allocated per-directory, not per-tree. When processing a recursive tree, only the listing for the *currently-active directory* is materialized at any given time. The file and directory lists for a parent directory are held in memory while child directories are being processed (because the parent's file list has already been iterated, but the directory list is being iterated), so the peak listing memory is proportional to the *maximum directory width at any single level along the current depth-first path*, not to the total entry count of the tree. For a tree with 1,000,000 entries distributed across 1,000 directories of 1,000 entries each, the peak listing memory is approximately 200 KB per directory × the number of directories on the current recursive stack — typically under 10 MB.

The §16.5 discussion of streaming release for `--inplace` mode applies to the *entry tree* held in memory after construction, not to the traversal listings. The traversal listings are transient and released as each directory finishes processing.

### 17.4. JSON Serialization for Large Output Trees

#### Serialization cost

The serializer (§6.9) converts a completed `IndexEntry` tree to JSON text via `dataclasses.asdict()` followed by `json.dumps()`. For small to medium trees (up to a few hundred entries), serialization time is negligible — a 100-entry tree serializes in under 100 milliseconds. For large trees, serialization can become a measurable fraction of total runtime because the standard library `json.dumps()` operates in pure Python for dict traversal, even though the string encoding is implemented in C.

The following estimates illustrate the cost scaling for pretty-printed JSON output (`indent=2`, `ensure_ascii=False`):

| Tree size (entries) | Approximate output size | `json.dumps()` time | Notes |
|---------------------|------------------------|---------------------|-------|
| 100 | ~400 KB | < 100 ms | Negligible. |
| 1,000 | ~4 MB | ~500 ms | Measurable but acceptable. |
| 10,000 | ~40 MB | ~5 seconds | Noticeable. Approaches the hashing cost of the tree. |
| 100,000 | ~400 MB | ~50 seconds | Significant. May exceed the hashing time for SSD-backed trees. |

These estimates assume approximately 4 KB of JSON per entry (the average for entries with two hash algorithms, timestamps, path components, and no metadata). Entries with large EXIF metadata or Base64-encoded sidecar content will be proportionally larger.

#### The `orjson` acceleration path

When the optional `orjson` package is installed (via the `perf` extra, §12.3), the serializer uses `orjson.dumps()` as a drop-in replacement. `orjson` is a Rust-backed JSON library that serializes Python dicts 3–10× faster than `json.dumps()` for typical workloads. For a 10,000-entry tree, serialization drops from approximately 5 seconds to under 1 second.

The `orjson` path is gated by a try/except import and is transparent to callers (§12.5):

```python
# Illustrative — not the exact implementation.
try:
    import orjson
except ImportError:
    orjson = None

def serialize_entry(entry: IndexEntry, *, compact: bool = False) -> str:
    entry_dict = dataclasses.asdict(entry)
    if orjson is not None:
        option = 0 if compact else orjson.OPT_INDENT_2
        return orjson.dumps(entry_dict, option=option).decode("utf-8")
    return json.dumps(entry_dict, indent=None if compact else 2, ensure_ascii=False)
```

The `orjson` path returns bytes, which are decoded to a UTF-8 string for API compatibility. The decode cost is minor relative to the serialization savings.

For users who index large trees (10,000+ entries) and use `--stdout` or `--outfile` output modes, installing the `perf` extra is the single highest-impact performance improvement available. Users of `--inplace` mode (which serializes one entry at a time) see proportionally less benefit because individual entry serialization is already fast.

#### `dataclasses.asdict()` overhead

The `dataclasses.asdict()` call is itself a non-trivial cost for large trees. It performs a recursive deep-copy of the entire entry tree, converting every dataclass instance to a plain dict and every list to a new list. For a 10,000-entry tree, this deep copy can take 1–2 seconds and temporarily doubles the memory footprint of the tree (the original dataclass tree and the dict copy coexist until `asdict()` returns and serialization begins).

If `orjson` is available, this overhead can be eliminated entirely: `orjson` serializes dataclasses natively, without requiring a `dataclasses.asdict()` conversion step. The implementation MAY bypass `asdict()` when `orjson` is the active serializer, passing the root `IndexEntry` directly to `orjson.dumps()` with `option=orjson.OPT_PASSTHROUGH_DATACLASS` (or equivalent). This requires that all fields on all dataclass types are `orjson`-serializable (which they are — the schema uses only strings, ints, floats, bools, lists, dicts, and `None`).

The `json.dumps()` fallback path cannot bypass `asdict()` because `json.dumps()` does not handle dataclass instances without a custom encoder. The overhead is accepted for the stdlib path; the `orjson` path eliminates it.

#### Compact vs. pretty-printed output

Pretty-printed output (`indent=2`) produces approximately 40% more bytes than compact output for typical `IndexEntry` data — the indentation whitespace and newlines add up across deeply nested structures. The serialization time difference between compact and pretty-printed is minimal (the formatter's whitespace insertion is trivial), but the I/O cost of writing a 40% larger file is not.

The `--compact` flag (§8.3) selects compact output. For large trees written to `--outfile`, compact output reduces both serialization time (less string concatenation) and file write time. For `--stdout` piped to a downstream consumer, compact output reduces pipe throughput requirements. The default is pretty-printed for human readability; the recommendation for automated pipelines processing large trees is `--compact`.

### 17.5. Exiftool Invocation Strategy

#### The dominant cost

For files that have embedded metadata, the `exiftool` invocation (§6.6) is overwhelmingly the most expensive per-file operation in the indexing pipeline. Hashing a 10 MB JPEG takes approximately 20–40 ms (limited by file read speed). Extracting EXIF metadata from the same file via `exiftool` takes 200–500 ms — an order of magnitude more. The cost is almost entirely `exiftool` process startup: the Perl interpreter loads, exiftool's module tree initializes, the file is read, metadata is extracted, and JSON output is produced. For a directory of 1,000 JPEG files, exiftool invocations alone can account for 3–8 minutes of total runtime, dwarfing the combined cost of hashing, stat calls, sidecar discovery, and serialization.

This cost profile is inherited from the original, which invokes exiftool once per file via `GetFileExifRun`. The original routes the invocation through a Base64-decoded argument file and a `jq` post-processing pipeline, adding further per-file overhead (temporary file creation, `certutil` invocation for Base64 decoding, `jq` process startup, and temporary file cleanup). The port eliminates the argument-file machinery and the `jq` pipeline (DEV-05, DEV-06), reducing the per-invocation overhead to the subprocess spawn plus exiftool execution.

#### Per-file invocation: the MVP approach

The MVP implementation invokes `exiftool` as a separate `subprocess.run()` call for each eligible file. This is the simplest correct implementation and matches the original's one-file-per-invocation behavior (minus the argument-file indirection).

```python
# Illustrative — not the exact implementation.
result = subprocess.run(
    ["exiftool", "-json", "-n", ...flags..., str(path)],
    capture_output=True,
    text=True,
    timeout=30,
)
```

The per-file approach has one significant advantage: error isolation. If exiftool crashes, hangs, or produces corrupt output for a single file, the failure is contained to that file — the next file gets a fresh exiftool process. The `timeout=30` parameter (§6.6) bounds the worst-case latency for a single invocation. This isolation property matches the item-level error boundary defined in §4.5: a single file's exiftool failure does not affect any other file.

#### Batch invocation: the post-MVP optimization

Exiftool supports a `-stay_open` mode that keeps a single Perl process alive across multiple file inputs, amortizing the startup cost over the entire invocation. In this mode, the caller writes file paths to exiftool's stdin (one per line, terminated by a sentinel), and exiftool writes JSON output to stdout for each file as it completes. The per-file cost drops from 200–500 ms (dominated by process startup) to 20–50 ms (dominated by actual metadata extraction).

The optional `pyexiftool` package (declared in the `perf` extra alongside `orjson`, §12.3) provides a Python wrapper around `-stay_open` mode. When `pyexiftool` is available, the exif module MAY use it as an alternative backend:

```python
# Illustrative — not the exact implementation.
try:
    import exiftool as pyexiftool
except ImportError:
    pyexiftool = None

# If pyexiftool is available, use batch mode:
# with pyexiftool.ExifToolHelper() as et:
#     metadata_list = et.get_metadata(paths)
```

The batch optimization is deferred to post-MVP for three reasons.

First, the `pyexiftool` dependency introduces a long-lived subprocess that complicates error handling. If the exiftool process dies mid-batch, all remaining files in the batch fail — breaking the per-file error isolation that the MVP's per-invocation approach provides. The batch wrapper must implement reconnection logic and per-file timeout enforcement that the simple `subprocess.run()` approach gets for free.

Second, the batch approach changes the invocation model from synchronous one-file-at-a-time (which fits naturally into the Stage 4 entry-construction loop) to an asynchronous or pre-batched model that requires either collecting file paths ahead of entry construction or restructuring the pipeline to separate EXIF extraction from entry assembly. Both of these are manageable but represent non-trivial architectural changes that should not be attempted in the initial port.

Third, the per-file approach is correct and complete. Users who need faster EXIF extraction for large media libraries can install the `perf` extra and benefit from the batch optimization when it ships, without any change to the output format or behavioral contract. The architecture supports the upgrade path without structural changes — `core/exif.py` already encapsulates all exiftool interaction behind the `extract_exif()` interface, so swapping the backend from subprocess-per-file to `pyexiftool` batch mode is an implementation change within a single module.

#### Availability probe cost

The exiftool availability probe (`shutil.which("exiftool")`, §6.6) runs once per process lifetime. On most systems, `shutil.which()` resolves in under 1 millisecond by scanning the `PATH` directories. The cost is amortized over the entire invocation and is never repeated — the result is cached in a module-level variable.

The original has no availability probe (§4.5). It discovers exiftool's absence through per-file failure: each `GetFileExifRun` call spawns a subprocess that immediately fails, producing a per-file error and the associated overhead of process creation and error-string construction. For a directory of 10,000 files with no exiftool installed, the original spawns and fails 10,000 subprocesses. The port's probe-once approach converts this from O(N) failed subprocess invocations to a single `shutil.which()` call — a performance improvement that is also a usability improvement (one warning message instead of 10,000 error messages).

#### Extension exclusion as a performance gate

Before invoking exiftool, the module checks the file's extension against the exclusion list (§7.4). The default exclusion set (`csv`, `htm`, `html`, `json`, `tsv`, `xml`) targets file types where exiftool tends to dump the entire file content into the metadata output rather than extracting meaningful embedded metadata. Excluding these types avoids both the subprocess cost and the downstream cost of serializing and storing the bloated metadata output.

The exclusion check is a `frozenset` membership test — O(1) per file. For a mixed-content directory where 30–50% of files are non-media types (a common scenario in project directories that contain code, data, and media), the exclusion filter can eliminate a significant fraction of exiftool invocations without any loss of useful metadata. This is a carry-forward from the original's `$global:MetadataFileParser.Exiftool.Exclude` list, and it serves the same purpose — the port preserves this gate exactly as-is because it is one of the original's better performance decisions.

#### Timeout as a safety bound

The 30-second timeout on `subprocess.run()` (§6.6) serves as both a safety mechanism (§16.5) and a performance bound. Without a timeout, a pathological file — a multi-gigabyte video with deeply nested metadata structures, or a corrupted file that causes exiftool to enter an infinite analysis loop — could block the indexer indefinitely. The timeout ensures that no single file can consume more than 30 seconds of exiftool processing time. When the timeout fires, the file's metadata is recorded as `None` (the exiftool `MetadataEntry` is omitted from the `metadata` array), a warning is logged, and processing continues with the next file.

The 30-second value is generous for normal operations — typical EXIF extraction completes in under 1 second for even large media files — but it could be exceeded for very large video files with embedded subtitle tracks or chapter metadata. The timeout is currently not configurable. If users report legitimate timeout hits on files that exiftool can process (just slowly), the value MAY be exposed as a configuration parameter in a future update. For the MVP, 30 seconds provides a wide safety margin without requiring user tuning.

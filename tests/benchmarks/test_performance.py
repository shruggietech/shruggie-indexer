"""Performance benchmark tests for shruggie-indexer.

All tests are decorated with ``@pytest.mark.slow`` and excluded from default
test runs.  Execute with ``pytest tests/benchmarks/ -m slow`` to include them.

These benchmarks produce timing data via ``time.perf_counter()``.  They do
NOT assert hard pass/fail thresholds — results are printed for manual review.
Future iterations may integrate ``pytest-benchmark`` (post-MVP).

See §14.7 for the full specification.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import IndexerConfig
from shruggie_indexer.core.hashing import hash_file
from shruggie_indexer.core.serializer import serialize_entry


@pytest.fixture()
def default_config() -> IndexerConfig:
    """Return default configuration for benchmarks."""
    return load_config()


# ---------------------------------------------------------------------------
# Benchmark 1: Single small file hash
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_bench_small_file_hash(tmp_path: Path) -> None:
    """Hash a 1 KB file with MD5 + SHA-256.

    Baseline expectation: <10 ms.
    """
    p = tmp_path / "small.bin"
    p.write_bytes(b"x" * 1024)

    start = time.perf_counter()
    hashes = hash_file(p, algorithms=("md5", "sha256"))
    elapsed = time.perf_counter() - start

    assert hashes.md5 is not None
    print(f"\n  small file hash (1 KB): {elapsed * 1000:.2f} ms")


# ---------------------------------------------------------------------------
# Benchmark 2: Single large file hash
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_bench_large_file_hash(tmp_path: Path) -> None:
    """Hash a 100 MB file with MD5 + SHA-256.

    Baseline expectation: within 50% of raw hashlib throughput.
    """
    p = tmp_path / "large.bin"
    # Write 100 MB in 1 MB chunks to avoid excessive memory usage.
    chunk = b"\x00" * (1024 * 1024)
    with open(p, "wb") as f:
        for _ in range(100):
            f.write(chunk)

    start = time.perf_counter()
    hashes = hash_file(p, algorithms=("md5", "sha256"))
    elapsed = time.perf_counter() - start
    throughput_mb = 100 / elapsed if elapsed > 0 else float("inf")

    assert hashes.md5 is not None
    print(f"\n  large file hash (100 MB): {elapsed:.3f} s ({throughput_mb:.0f} MB/s)")


# ---------------------------------------------------------------------------
# Benchmark 3: Flat directory traversal (1000 files)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_bench_flat_directory_traversal(tmp_path: Path, default_config: IndexerConfig) -> None:
    """Index a flat directory with 1000 small files.

    Baseline expectation: <5 s (excluding exiftool).
    """
    from shruggie_indexer.core.entry import build_directory_entry

    root = tmp_path / "flat_dir"
    root.mkdir()
    for i in range(1000):
        (root / f"file_{i:04d}.txt").write_bytes(b"content")

    start = time.perf_counter()
    entry = build_directory_entry(root, default_config, recursive=False)
    elapsed = time.perf_counter() - start

    assert entry.items is not None
    assert len(entry.items) == 1000
    print(f"\n  flat dir (1000 files): {elapsed:.3f} s")


# ---------------------------------------------------------------------------
# Benchmark 4: Recursive directory traversal (nested 5 levels)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_bench_recursive_directory_traversal(
    tmp_path: Path, default_config: IndexerConfig
) -> None:
    """Index a directory tree 5 levels deep with files at each level.

    Baseline expectation: no stack overflow, completes successfully.
    """
    from shruggie_indexer.core.entry import build_directory_entry

    root = tmp_path / "deep_tree"
    current = root
    for depth in range(5):
        current.mkdir(parents=True, exist_ok=True)
        for i in range(10):
            (current / f"file_{depth}_{i}.txt").write_bytes(b"nested content")
        current = current / f"level_{depth}"
    current.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    entry = build_directory_entry(root, default_config, recursive=True)
    elapsed = time.perf_counter() - start

    assert entry.items is not None
    print(f"\n  recursive dir (5 levels): {elapsed:.3f} s")


# ---------------------------------------------------------------------------
# Benchmark 5: Exiftool extraction throughput
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.requires_exiftool
def test_bench_exiftool_throughput(tmp_path: Path, default_config: IndexerConfig) -> None:
    """Measure per-file exiftool extraction time on 10 JPEG stubs.

    Baseline expectation: <50 ms per file after startup (batch mode).
    Requires exiftool on PATH.
    """
    from shruggie_indexer.core.exif import extract_exif

    # Create minimal JPEG files (JFIF header stub).
    jfif_header = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xd9"
    )
    files = []
    for i in range(10):
        p = tmp_path / f"photo_{i:02d}.jpg"
        p.write_bytes(jfif_header)
        files.append(p)

    times = []
    for p in files:
        start = time.perf_counter()
        _ = extract_exif(p, default_config)
        times.append(time.perf_counter() - start)

    avg_ms = (sum(times) / len(times)) * 1000
    print(f"\n  exiftool per-file avg: {avg_ms:.1f} ms (10 JPEGs)")


# ---------------------------------------------------------------------------
# Benchmark 6: Sidecar discovery throughput
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_bench_sidecar_discovery(tmp_path: Path, default_config: IndexerConfig) -> None:
    """Measure sidecar discovery time for a directory with 100 primary files,
    each with 3 sidecar-like siblings.

    Baseline expectation: completes quickly; discovery is regex-based.
    """
    from shruggie_indexer.core.sidecar import discover_and_parse

    root = tmp_path / "sidecar_bench"
    root.mkdir()
    for i in range(100):
        stem = f"item_{i:03d}"
        (root / f"{stem}.mp4").write_bytes(b"primary")
        (root / f"{stem}.description").write_text("desc", encoding="utf-8")
        (root / f"{stem}.info.json").write_text('{"key": "val"}', encoding="utf-8")
        (root / f"{stem}.srt").write_text("1\n00:00:01 --> 00:00:02\nhi", encoding="utf-8")

    siblings = list(root.iterdir())
    primaries = [p for p in siblings if p.suffix == ".mp4"]

    start = time.perf_counter()
    for p in primaries:
        discover_and_parse(p, p.name, siblings, default_config, index_root=root)
    elapsed = time.perf_counter() - start

    print(f"\n  sidecar discovery (100 files x 3 sidecars): {elapsed:.3f} s")


# ---------------------------------------------------------------------------
# Benchmark 7: Serialization throughput
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_bench_serialization_throughput(tmp_path: Path, default_config: IndexerConfig) -> None:
    """Serialize 1000 entries and measure total time.

    Baseline expectation: <2 s for json.dumps on 1000 entries.
    """
    from shruggie_indexer.core.entry import build_file_entry

    # Create a single reference file and build one entry.
    ref = tmp_path / "serialize_ref.txt"
    ref.write_text("serialization benchmark content", encoding="utf-8")
    entry = build_file_entry(ref, default_config)

    start = time.perf_counter()
    for _ in range(1000):
        _ = serialize_entry(entry)
    elapsed = time.perf_counter() - start

    print(f"\n  serialization (1000 entries): {elapsed:.3f} s")


# ---------------------------------------------------------------------------
# Benchmark 8: Rename dry-run throughput
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_bench_rename_dry_run(tmp_path: Path, default_config: IndexerConfig) -> None:
    """Perform dry-run renames on 100 files and measure throughput.

    Baseline expectation: rename_item in dry-run should be near-instant
    since it only computes paths.
    """
    from shruggie_indexer.core.entry import build_file_entry
    from shruggie_indexer.core.rename import rename_item

    files = []
    for i in range(100):
        p = tmp_path / f"rename_target_{i:03d}.txt"
        p.write_text(f"content {i}", encoding="utf-8")
        files.append(p)

    # Build entries for all files.
    entries = [(p, build_file_entry(p, default_config)) for p in files]

    start = time.perf_counter()
    for original, entry in entries:
        rename_item(original, entry, dry_run=True)
    elapsed = time.perf_counter() - start

    print(f"\n  rename dry-run (100 files): {elapsed * 1000:.1f} ms")

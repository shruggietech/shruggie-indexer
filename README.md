# shruggie-indexer

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI](https://github.com/shruggietech/shruggie-indexer/actions/workflows/release.yml/badge.svg)](https://github.com/shruggietech/shruggie-indexer/actions/workflows/release.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

Filesystem indexer with hash-based identity, metadata extraction, and structured JSON output.

`shruggie-indexer` scans files and directories to produce deterministic, schema-validated JSON index entries. Each entry captures cryptographic hashes (MD5, SHA-256, optional SHA-512), filesystem timestamps, EXIF metadata (via exiftool), sidecar file content, and a computed storage name — all structured under the [v2 JSON Schema](https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json).

## Installation

### Standalone Executables (Recommended)

Download pre-built executables from [GitHub Releases](https://github.com/shruggietech/shruggie-indexer/releases). Available for Windows, Linux, and macOS (x64 + ARM64) — no Python installation required.

### From Source (Contributors)

```bash
git clone https://github.com/shruggietech/shruggie-indexer.git
cd shruggie-indexer
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[dev,cli]"
```

For the GUI application:

```bash
pip install -e ".[dev,cli,gui]"
```

## Quick Start

### Index a Single File

```bash
shruggie-indexer path/to/file.ext
```

### Index a Directory (Recursive)

```bash
shruggie-indexer path/to/directory --recursive
```

### Write Output to a File

```bash
shruggie-indexer path/to/target --outfile index.json
```

### Write Sidecar Files In-Place

```bash
shruggie-indexer path/to/directory --inplace
```

### Include EXIF Metadata

```bash
shruggie-indexer path/to/file.jpg --meta
```

### Rename Files to Storage Names (Dry Run)

```bash
shruggie-indexer path/to/directory --rename --dry-run
```

## CLI Options

| Option | Description |
|--------|-------------|
| `--file` / `--directory` | Force target type interpretation |
| `--recursive` / `--no-recursive` | Enable or disable recursive directory traversal |
| `--stdout` / `--no-stdout` | Control JSON output to stdout |
| `-o, --outfile PATH` | Write combined JSON to a file |
| `--inplace` | Write sidecar `_meta2.json` files alongside each item |
| `-m, --meta` | Extract embedded metadata via exiftool |
| `--meta-merge` | Merge sidecar metadata into parent entries |
| `--meta-merge-delete` | Merge and delete sidecar files |
| `--rename` | Rename files to their computed `storage_name` |
| `--dry-run` | Preview rename operations without modifying files |
| `--id-type {md5,sha256}` | Hash algorithm for the `id` field (default: md5) |
| `--compute-sha512` | Include SHA-512 in hash output |
| `--config PATH` | Path to a TOML configuration file |
| `-v, --verbose` | Increase verbosity (repeat: `-vv`, `-vvv`) |
| `-q, --quiet` | Suppress all non-error output |
| `--version` | Show version and exit |

## Python API

```python
from pathlib import Path

from shruggie_indexer import index_path, load_config, serialize_entry

config = load_config()
entry = index_path(Path("path/to/target"), config)
json_output = serialize_entry(entry, pretty=True)
print(json_output)
```

## Documentation

- [User Guide](https://shruggietech.github.io/shruggie-indexer/user/)
- [Schema Reference](https://shruggietech.github.io/shruggie-indexer/schema/)
- [Porting Reference](https://shruggietech.github.io/shruggie-indexer/porting-reference/)
- [Technical Specification](shruggie-indexer-spec.md)

## License

Copyright 2024–2026 ShruggieTech LLC. Licensed under the [Apache License 2.0](LICENSE).
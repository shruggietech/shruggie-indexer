# Installation

## System Requirements

| Requirement | Details |
|-------------|---------|
| **Python** | 3.12 or later |
| **Operating System** | Windows 10/11 (x64), Linux x64 (Ubuntu 22.04+, Fedora 38+), macOS x64/ARM64 (13 Ventura+) |
| **External binary** | [ExifTool](https://exiftool.org/) ≥ 12.0 (optional — required only for EXIF metadata extraction) |

## Install via pip

The recommended way for Python developers to install shruggie-indexer:

```bash
pip install shruggie-indexer
```

This installs the core tool with its required dependencies: `click`, `orjson`, `pyexiftool`, and `tqdm`.

### Optional dependency groups

Install additional features via extras:

```bash
# GUI application (CustomTkinter-based desktop interface)
pip install shruggie-indexer[gui]

# Development tools (pytest, ruff, jsonschema, pydantic, rich)
pip install shruggie-indexer[dev]

# Documentation tools (mkdocs, mkdocs-material)
pip install shruggie-indexer[docs]

# Everything (GUI + all optional extras)
pip install shruggie-indexer[all]
```

## Install from Source

Clone the repository and install in editable mode:

```bash
git clone https://github.com/shruggietech/shruggie-indexer.git
cd shruggie-indexer
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

Install with development dependencies:

```bash
pip install -e ".[dev]"
```

For the GUI application:

```bash
pip install -e ".[dev,gui]"
```

## Standalone Executables

Pre-built executables are available on the [GitHub Releases](https://github.com/shruggietech/shruggie-indexer/releases) page. These require no Python installation.

| Platform | Artifact | Notes |
|----------|----------|-------|
| Windows x64 | `shruggie-indexer.exe` | Primary build target. Single-file executable. |
| Linux x64 | `shruggie-indexer` | Tested on Ubuntu 22.04+. |
| macOS ARM64 | `shruggie-indexer` | Apple Silicon native. |

Download the appropriate binary, place it in a directory on your `PATH`, and run it directly.

!!! tip "GUI executables"
    Standalone GUI executables (`shruggie-indexer-gui`) are also available on the Releases page for each platform.

## Verification

After installation, verify the tool is accessible:

```bash
shruggie-indexer --version
```

This should print the installed version (e.g., `shruggie-indexer, version 0.1.0`).

## ExifTool (Optional)

ExifTool is required only for embedded EXIF/XMP/IPTC metadata extraction (the `--meta` flag). All other functionality — hashing, timestamps, sidecar handling, renaming — works without it.

See the [ExifTool Setup](exiftool.md) page for detailed installation instructions on each platform.

## Next Steps

- [Quick Start](quickstart.md) — Index your first file or directory.
- [ExifTool Setup](exiftool.md) — Install ExifTool for metadata extraction.
- [CLI Reference](../user-guide/cli-reference.md) — Full command-line option documentation.

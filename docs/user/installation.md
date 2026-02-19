# Installation

!!! note "Work in Progress"
    This page will be populated as the project reaches a stable release. For current installation guidance, see the [README](https://github.com/shruggietech/shruggie-indexer/blob/main/README.md).

## System Requirements

- Python 3.12 or later
- `exiftool` (optional, for EXIF metadata extraction)

## Installation Methods

### From PyPI

```bash
pip install shruggie-indexer
```

### From Source

```bash
git clone https://github.com/shruggietech/shruggie-indexer.git
cd shruggie-indexer
pip install -e ".[dev,gui]"
```

### Standalone Executable

Pre-built executables for Windows, macOS, and Linux are available on the [Releases](https://github.com/shruggietech/shruggie-indexer/releases) page.

## Verification

```bash
shruggie-indexer --version
```

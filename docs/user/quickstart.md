# Quick Start

!!! note "Work in Progress"
    This page will be populated as the CLI interface stabilizes. For current usage information, see the [README](https://github.com/shruggietech/shruggie-indexer/blob/main/README.md).

## Index a Single File

```bash
shruggie-indexer file path/to/file.txt
```

## Index a Directory

```bash
shruggie-indexer dir path/to/directory/
```

## Index a Directory Recursively

```bash
shruggie-indexer tree path/to/directory/
```

## Output Modes

By default, index output is written to stdout as JSON. See the [Configuration](configuration.md) page for output mode options including file output and in-place sidecar writes.

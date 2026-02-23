# User Guide

The User Guide provides comprehensive reference documentation for shruggie-indexer. Choose a section below based on what you need.

## Sections

### [Desktop Application](gui.md)

Visual guide to the desktop (GUI) application. Covers launching the app, navigating the interface, choosing operation types, understanding the output panel, keyboard shortcuts, and troubleshooting — written for users who prefer a graphical interface over the command line.

### [CLI Reference](cli-reference.md)

Complete documentation for every command-line option, flag, and argument. Includes the output scenarios table, exit codes, mutual exclusion rules, and signal handling behavior.

### [Configuration](configuration.md)

The TOML-based configuration system: file format, default values, the layered resolution hierarchy (CLI flags > config file > defaults), metadata file parser patterns, ExifTool exclusion lists, and override/merge behavior.

### [Python API](python-api.md)

Public API reference for using shruggie-indexer as a Python library. Covers `index_path()`, `load_config()`, `serialize_entry()`, and all data classes (`IndexEntry`, `HashSet`, `NameObject`, and more).

### [Platform Notes](platform-notes.md)

Cross-platform behavior details for Windows, Linux, and macOS — including creation time portability, symlink handling, filesystem attribute differences, and path normalization.

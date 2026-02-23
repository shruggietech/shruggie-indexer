# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- ExifTool key filtering now correctly handles group-prefixed keys (e.g. `System:FileName`) by matching on the base key name after the last `:` separator. Previously, the `-G3:1` flag caused all keys to carry group prefixes, which bypassed the exact-match exclusion check and leaked sensitive filesystem details into output.

### Changed

- Expanded `EXIFTOOL_EXCLUDED_KEYS` from 8 to 24 entries. Added `SourceFile`, redundant timestamp/size keys already captured in IndexEntry fields, OS-specific filesystem attributes (`FileAttributes`, `FileDeviceNumber`, `FileInodeNumber`, etc.), and ExifTool operational keys (`Now`, `ProcessingTime`).
- **GUI: Consolidated tab layout** — Replaced four separate operation tabs (Index, Meta Merge, Meta Merge Delete, Rename) with a single Operations page using an operation-type selector dropdown. Sidebar now contains three tabs: Operations, Settings, and About.
- **GUI: Destructive-operation indicator** — Added a real-time visual indicator (green/red dot) that reflects whether the selected operation and dry-run state combination is destructive.
- **GUI: Labeled control groups** — Reorganized controls into bordered, labeled groups (Operation, Target, Options, Output) with contextual descriptions. Controls show or hide dynamically based on the selected operation type.
- **GUI: Dual browse buttons** — Target input now shows separate "File…" and "Folder…" browse buttons when the target type is "auto", and a single context-appropriate button otherwise.
- **GUI: Persistent output file entry** — Output file path field is always visible with auto-suggested paths that update as target and operation change, while preserving manual user edits.
- **GUI: Auto-clear output on run** — Output panel is automatically cleared when starting a new operation.
- **GUI: Output panel clear button** — Added a "Clear" toolbar button alongside the existing Save and Copy buttons.
- **GUI: Save-mode completion message** — When output mode is "save", the completion panel now shows a status message instead of attempting to render an empty JSON result.
- **GUI: About tab** — New About tab displaying project description, version, Python and ExifTool info, documentation and website links, and attribution.
- **GUI: Sidebar version label** — Application version displayed at the bottom of the sidebar in a muted font.
- **GUI: Library log capture** — Core library log messages are now captured via a queue handler attached to the `shruggie_indexer` logger and streamed to both the progress and output panels. Verbosity level is controlled from Settings.
- **GUI: Copy button feedback** — Copy button briefly changes to "Copied ✓" with a green highlight for 1.5 seconds after clicking.
- **GUI: Resizable output panel** — Output panel includes a drag handle for vertical resizing (100–600 px range). Panel height is persisted across sessions.
- **GUI: Tooltips** — Descriptive hover tooltips added to all interactive controls, with a global enable/disable toggle in Settings.
- **Documentation: GUI usage guide** — Added a dedicated desktop application guide (`docs/user-guide/gui.md`) covering launch, interface navigation, all operation types, output panel usage, keyboard shortcuts, session persistence, and troubleshooting. Includes Windows SmartScreen unblocking instructions. Placed prominently in the MkDocs navigation under User Guide.

## [0.1.0] - 2026-02-20

### Added

- Initial `shruggie-indexer` release with CLI, GUI, and Python API delivery surfaces.
- Deterministic v2 schema output with hash-based IDs, timestamp capture, and storage names.
- Filesystem traversal for files/directories with recursive mode and platform-aware behavior.
- Metadata features: sidecar discovery/parse/merge flows and optional ExifTool extraction.
- Output routing modes for stdout, combined outfile, and in-place sidecar JSON writes.
- Rename flow with dry-run support and configurable identity algorithm (`md5` or `sha256`).
- Config loading with layered defaults and TOML overrides.
- Cross-platform build-and-release CI that publishes standalone executables for Windows, Linux, and macOS.

[Unreleased]: https://github.com/shruggietech/shruggie-indexer/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/shruggietech/shruggie-indexer/releases/tag/v0.1.0
# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- ExifTool key filtering now correctly handles group-prefixed keys (e.g. `System:FileName`) by matching on the base key name after the last `:` separator. Previously, the `-G3:1` flag caused all keys to carry group prefixes, which bypassed the exact-match exclusion check and leaked sensitive filesystem details into output.

### Changed

- Expanded `EXIFTOOL_EXCLUDED_KEYS` from 8 to 24 entries. Added `SourceFile`, redundant timestamp/size keys already captured in IndexEntry fields, OS-specific filesystem attributes (`FileAttributes`, `FileDeviceNumber`, `FileInodeNumber`, etc.), and ExifTool operational keys (`Now`, `ProcessingTime`).

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
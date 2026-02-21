# Changelog

All notable changes to `shruggie-indexer` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Placeholder for upcoming unreleased changes.

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

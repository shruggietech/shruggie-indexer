# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Tests: Sidecar handling and MetaMergeDelete test infrastructure** — Created three permanent test files covering sidecar exclusion, MetaMergeDelete pipeline, and full integration scenarios: `tests/test_sidecar_exclusion.py` (14 tests across 3 classes), `tests/test_meta_merge_delete.py` (7 tests across 2 classes), and `tests/test_integration_mmd_pipeline.py` (9 tests across 3 classes). Tests exercise Layer 1 (metadata_exclude_patterns) and Layer 2 (metadata_identify sidecar) filtering, delete queue population/execution, full MMD pipeline, MMD+rename pipeline, in-place sidecar naming, and idempotency. Added 4 new pytest markers: `sidecar`, `mmd`, `integration`, `destructive`.
- **Tests: `sidecar-testbed` fixture** — Created `tests/fixtures/sidecar-testbed/` directory tree with 19 files across 3 subdirectories, exercising all sidecar exclusion, merge, delete, and rename scenarios. Includes content files, sidecar variants (json_metadata, description, screenshot, hash, yaml), prior-run indexer output artifacts, and false-positive candidates (`standalone_notes.txt`).
- **Core: `rename_inplace_sidecar()` function** — New public function in `core/rename.py` that renames an in-place `_meta2.json` sidecar file from `{original_name}_meta2.json` to `{storage_name}_meta2.json` after a content file is renamed. Prevents orphaned sidecars and incorrect sidecar naming when rename is active. Exported via `shruggie_indexer.__init__`.
- **Core: Rename phase diagnostic logging** — Added comprehensive `DEBUG`-level logging to `_rename_tree()` in both GUI and CLI. Each rename candidate now logs its type and storage_name. Directory entries log item count on descent and skip reason when empty.

### Fixed

- **Core: In-place directory sidecar naming** — `build_sidecar_path()` in `core/paths.py` constructed directory sidecar paths as `<dir>/_directorymeta2.json` (bare name with no identifying prefix). Every directory in the tree received an identically named file, making them indistinguishable in file managers and inconsistent with both the aggregate output naming (`{dirname}_directorymeta2.json`) and file sidecar naming (`{filename}_meta2.json`). Fixed to produce `<dir>/{dirname}_directorymeta2.json`. The `metadata_exclude_patterns` regex continues to match the corrected filenames because the pattern is end-anchored.
- **Core: Sidecar files indexed as standalone items** — `list_children()` in `traversal.py` was not applying `metadata_exclude_patterns` during item enumeration. Indexer output artifacts (`_meta.json`, `_meta2.json`, `_directorymeta2.json`) were being treated as regular files — fully indexed, hashed, EXIF-checked, renamed, and given their own sidecar output (creating absurd filenames like `file_meta.json_meta2.json`). Fixed by adding Layer 1 filtering: files matching `metadata_exclude_patterns` are now unconditionally excluded during traversal.
- **Core: Sidecar companion files indexed as standalone items when MetaMerge active** — When MetaMerge was enabled, files matching `metadata_identify` sidecar patterns (e.g., `.info.json`, `.description`, `_screen.jpg`, `.md5`, `.yaml`) appeared as both standalone index entries AND sidecar metadata sources. Fixed by adding Layer 2 filtering in `build_directory_entry()`: recognized sidecar files are excluded from the entry-building iteration while remaining in the full `siblings` list for sidecar discovery. This ensures sidecars are consumed exclusively through the merge system without breaking sidecar discovery's sibling enumeration.
- **GUI/CLI: MetaMergeDelete log levels incorrect** — `_drain_delete_queue()` in both GUI and CLI used `logger.debug` for successful deletions and `logger.warning` for failures. Per spec, successful deletions must be logged at `INFO` (`Sidecar deleted: {path}`) and failures at `ERROR` (`Sidecar delete FAILED: {path}: {exception}`). Fixed in both entry points.
- **GUI/CLI: In-place sidecar files named using pre-rename filename** — When both rename and in-place output were active, `_meta2.json` sidecar files were written using the original filename (e.g., `photo.jpg_meta2.json`) instead of the post-rename storage name (e.g., `yABC123.jpg_meta2.json`). This created orphaned sidecars with no on-disk association to the renamed content file. Fixed by wiring `rename_inplace_sidecar()` into the rename phase of both GUI and CLI, renaming the sidecar file alongside its content file.
- **GUI/CLI: Pipeline ordering for rename + in-place output** — In-place sidecar writes were happening independently of the rename phase. Swapped ordering so in-place writes occur before rename, and the rename phase handles both the content file and its sidecar atomically. This preserves partial-result survival for non-rename cases while ensuring correct sidecar naming when rename is active.
- **Core: Rename collision logging** — When multiple files share an identical content hash and the rename target already exists on disk, the collision was previously either raised as a `RenameError` (caught silently by callers) or skipped with no log output. `rename_item()` now logs a `WARNING`-level message (`Rename SKIPPED (collision): {original_name} → {storage_name} (target already exists)`) and returns the original path without raising. Callers in both GUI and CLI now check the return value to skip in-place sidecar rename for collision-skipped files, preserving the original filename as the sidecar base.

### Changed

- **Core: `build_directory_entry()` Layer 2 sidecar filtering** — Moved sidecar-pattern exclusion (Layer 2) from `list_children()` into `build_directory_entry()`. The full file list from `list_children()` is preserved as `siblings` for sidecar discovery, while a filtered `entry_files` list (excluding recognized sidecar patterns) is used for child entry construction. This architectural change ensures sidecar discovery can find companion files while preventing them from being indexed as standalone items.
- **Core: `list_children()` now applies Layer 1 filtering** — `list_children()` in `traversal.py` now applies `metadata_exclude_patterns` (compiled regexes) against all filenames after the scandir loop, before sorting. This is a new filtering step that was previously absent from the traversal module.

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

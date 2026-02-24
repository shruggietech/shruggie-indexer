# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Docs: GUI screenshot infrastructure** — Created `docs/assets/images/gui/` directory for storing annotated GUI screenshots. Added a "To Do" section to the GUI documentation page (`docs/user-guide/gui.md`) listing the required screenshots.
- **Config: User-customizable ExifTool key exclusions** — Added `exiftool.exclude_keys` (replace) and `exiftool.exclude_keys_append` (extend) configuration keys for controlling which metadata keys are filtered from ExifTool output. The compiled default set is unchanged; users can now extend or replace it via TOML configuration files or API overrides without modifying source code. Added `exiftool_exclude_keys` field to `IndexerConfig`, `DEFAULT_EXIFTOOL_EXCLUDE_KEYS` to compiled defaults, and TOML merge logic for both replace and append modes. Includes eight new unit tests covering replace mode, append mode, TOML loading, config loader round-tripping, and end-to-end extraction with custom sets.
- **Tests: Non-zero exit metadata recovery** — Added `TestNonZeroExitMetadataRecovery` test class with five cases covering batch recovery, subprocess recovery, empty-stdout fallback, helper reset on unrecoverable errors, and `Error` key exclusion.
- **CLI: `--log-file` flag** — New option to write log output to a persistent file. `--log-file` (no argument) writes to the default platform-specific app data directory; `--log-file <path>` writes to a custom location. Log files are named `YYYY-MM-DD_HHMMSS.log` and include timestamps, session ID, and logger name.
- **TOML: `[logging]` configuration section** — Added `logging.file_enabled` and `logging.file_path` keys to enable persistent log file output via configuration files.
- **GUI: "Write log files" settings toggle** — New checkbox in the Settings page Logging section. When enabled, each operation writes a timestamped log file to the app data directory. Toggle state is persisted across sessions.

### Fixed

- **GUI: Progress bar layout stability** — Replaced the swappable progress/output panel arrangement with a fixed-height progress region embedded directly within the Operations page. The region uses `pack_propagate(False)` to maintain a constant 120 px allocation, toggling between idle (START button) and running (progress bar + cancel) sub-frames without reflowing surrounding controls.
- **ExifTool: Metadata recovery on non-zero exit** — ExifTool invocations that exit with a non-zero status (e.g. unsupported file types producing partial JSON on stdout) now attempt to recover valid metadata from the output before falling back. Previously, any non-zero exit discarded all data. Added `_recover_metadata_from_error()` and `_log_exiftool_error_field()` helpers; "Unknown file type" warnings are now logged at INFO instead of WARNING. Added `"Error"` to `EXIFTOOL_EXCLUDED_KEYS`.
- **GUI: Log capture pipeline** — Core library log messages and progress event messages now both appear in the output panel's log view with timestamps. Previously, most diagnostic output was silently dropped or consumed by the progress panel without forwarding to the log stream.
- **GUI: Log entry timestamps and formatting** — Log entries in the GUI log panel now use the `HH:MM:SS  LEVEL  message` format with color coding: red for ERROR/CRITICAL, amber for WARNING, muted gray for DEBUG, and default text color for INFO.
- **GUI: Log auto-scroll behavior** — The log panel now auto-scrolls to the bottom when new content arrives, pauses auto-scroll when the user scrolls upward, and resumes when scrolled back to the bottom.
- **GUI: Log panel Save and Copy buttons** — Save and Copy buttons are now enabled whenever the active view (Output or Log) contains content. Previously they were permanently disabled in the log view. Save in log view opens a save-as dialog for `.log` files.
- ExifTool key filtering now correctly handles group-prefixed keys (e.g. `System:FileName`) by matching on the base key name after the last `:` separator. Previously, the `-G3:1` flag caused all keys to carry group prefixes, which bypassed the exact-match exclusion check and leaked sensitive filesystem details into output.

### Changed

- **Spec SS1–SS9: Technical specification tone overhaul (Phases A–C)** — Rewrote Sections 1 through 9 of the technical specification to shift the document's voice from a porting diary to an authoritative standalone tool specification. All "Deviation from original" and "Improvement over original" callouts are relabeled to "Historical note" blockquotes. References to "the port" are replaced with "the tool" or "shruggie-indexer"; references to "the original" are demoted into Historical note callouts or rephrased as "the legacy implementation." Body text now leads with what the tool does, not how it differs from the PowerShell predecessor. DEV-XX codes and SS X.Y cross-references are preserved throughout.
- **ExifTool: `_filter_keys()` accepts configurable exclusion set** — `_filter_keys()` now takes an `exclude_keys` parameter instead of referencing the module-level constant. The exclusion set is resolved from `IndexerConfig.exiftool_exclude_keys` and threaded through all backend call paths (`_extract_batch`, `_extract_subprocess`, `_parse_json_output`, `_recover_metadata_from_error`). The module-level `EXIFTOOL_EXCLUDED_KEYS` constant is retained for backward compatibility and reference.
- **GUI: Centralized control reconciliation** — Replaced `_update_controls()` with `_reconcile_controls()`, a single method implementing the full dependency matrix for all Operations page controls. Manages recursive toggle state across five target scenarios, in-place sidecar forcing for Meta Merge Delete, SHA-512 settings sync, output placeholder text, and destructive indicator updates. All control-change callbacks now route through this method.
- Expanded `EXIFTOOL_EXCLUDED_KEYS` from 8 to 24 entries. Added `SourceFile`, redundant timestamp/size keys already captured in IndexEntry fields, OS-specific filesystem attributes (`FileAttributes`, `FileDeviceNumber`, `FileInodeNumber`, etc.), and ExifTool operational keys (`Now`, `ProcessingTime`).
- **GUI: Consolidated tab layout** — Replaced four separate operation tabs (Index, Meta Merge, Meta Merge Delete, Rename) with a single Operations page using an operation-type selector dropdown. Sidebar now contains three tabs: Operations, Settings, and About.
- **GUI: Destructive-operation indicator** — Added a real-time visual indicator (green/red dot) that reflects whether the selected operation and dry-run state combination is destructive.
- **GUI: Labeled control groups** — Reorganized controls into bordered, labeled groups (Operation, Target, Options, Output) with contextual descriptions. Controls show or hide dynamically based on the selected operation type.
- **GUI: Always-visible controls with enable/disable** — All input controls (Target, Options, Output) are now always visible regardless of the selected operation type. Controls that do not apply to the current operation are disabled with a brief explanatory label instead of being hidden. This makes the full option space discoverable at all times.
- **GUI: Rename as feature toggle** — Rename is no longer a standalone operation type. It is now a "Rename files" checkbox in the Options group that can be combined with any of the three operation types (Index, Meta Merge, Meta Merge Delete). The operation type dropdown has been reduced from four entries to three.
- **GUI: Target/Type validation** — The application now detects file-vs-directory conflicts between the target path and the selected type. A red inline error message appears below the type selector, and the START button is disabled until the conflict is resolved. The Recursive checkbox is automatically disabled when the target is a single file.
- **GUI: SHA-512 settings sync** — When "Compute SHA-512 by default" is enabled in Settings, the SHA-512 checkbox on the Operations page is forced on and cannot be unchecked, with a "(Enabled in Settings)" explanation label. Changing the setting syncs immediately.
- **GUI: Green START button** — The action button now always displays "▶  START" (green) regardless of operation type, centered with a max width of 50% of the window. During execution it changes to "■ Cancel" (red). The label no longer varies by operation.
- **GUI: Removed static scrollbar** — The Operations page input area now uses a plain frame instead of a scrollable frame, eliminating a persistent scrollbar that appeared even when content fit without scrolling.
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
- **Spec SS3.1: Repository layout sync** — Updated the top-level layout tree diagram and table to reflect the current repository state. Added entries for `.archive/`, `CHANGELOG.md`, PyInstaller spec files, generated spec renderings (`.html`/`.pdf`), and VS Code workspace file. Corrected `docs/` subdirectory names (`user/` → `user-guide/`, added `getting-started/`). Broadened `.github/` entry to cover `copilot-instructions.md`.
- **Spec SS1.5: Archived implementation plan** — Updated the reference documents table to point to the archived location (`.archive/shruggie-indexer-plan.md`) and note that all sprints are complete.
- **Spec SS3.7: Documentation site nav** — Updated the `nav` YAML example to match the current `mkdocs.yml` structure: added Getting Started section, Desktop Application under User Guide, corrected doc paths, and promoted Changelog to top-level nav item.
- **Spec SS10: GUI Application** — Comprehensive spec update to reflect the consolidated GUI architecture implemented in Sections 1–5. Rewrote SS10 introduction, SS10.1 session persistence (v2 format), SS10.2 window layout (3-tab sidebar, version label), SS10.3 target selection (consolidated operations page, dual browse, auto-suggest output, context-sensitive controls), SS10.4 configuration panel (removed embedded About, added Interface/tooltips section), SS10.5 action button and job exclusivity (single Operations page model), SS10.6 output display (Clear button, copy feedback, resizable panel, auto-clear, post-job display modes), SS10.7 keyboard shortcuts (Ctrl+1–3 for pages, Ctrl+Shift+C for copy). Added new SS10.8 supplemental components subsection covering destructive indicator, About tab, tooltips, labeled group frames, and debug logging. Updated to reflect rename as feature toggle (not standalone operation), always-visible controls with enable/disable paradigm, green START button, target/type validation, and SHA-512 settings sync.
- **Spec SS10.9: GUI Design Standards** — Added new subsection to the technical specification codifying GUI design governance. Adopts Jakob Nielsen's 10 Usability Heuristics by reference as the baseline evaluation framework. Defines seven project-specific UI standards: layout stability, state-driven control visibility, control interdependency transparency, output handling clarity, destructive operation safeguards, progress/feedback area allocation, and log/output panel behavior. Includes a directive requiring all GUI implementation work (including AI agent sessions) to comply with these standards.
- **Deprecated `shruggie-indexer-plan.md`** — Moved the completed implementation plan from the repository root to `.archive/`. Added `.archive/`, `shruggie-indexer-spec.html`, and `shruggie-indexer-spec.pdf` to `.gitignore`.

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
# v4 Sidecar Architecture Pivot - After-Action Report

| Field | Value |
|---|---|
| **Date** | 2026-04-02 |
| **Sprint** | 20260401-003 |
| **Release** | v1.0.0 |
| **Phases Completed** | 9/9 |

## Summary

The v4 sidecar architecture pivot was completed across nine phases, culminating in release-preparation updates for v1.0.0. The implementation replaced sidecar embedding with first-class per-file indexing plus relationship annotations. The release work in this phase finalized changelog content, synchronized docs changelog output, updated README release messaging, and bumped package version to 1.0.0.

Session metrics (Phase 9 execution context):

- Files changed for release prep: 4 modified, 2 reports created.
- Release delta in this phase: +103 / -9 lines across tracked release files.
- Verification status in this phase:
  - Tests: 456 passed, 63 skipped, 3 warnings.
  - Docs build: strict build successful.
  - Lint/format: failing due pre-existing repository issues unrelated to Phase 9 file set.

## Phase Execution Log

1. **Phase 1 (Schema and Core Model)**
- Added v4 schema (`schema_version = 4`) and relationship annotation model.
- Updated core data model and serializer ordering to support `relationships`.

2. **Phase 2 (Sidecar Rule Engine)**
- Implemented rule engine and built-in rule library.
- Added rule evaluation and predicate confidence tracking.

3. **Phase 3 (Discovery Pipeline Integration)**
- Removed sidecar exclusion from discovery.
- Integrated relationship classification pass after entry construction.

4. **Phase 4 (Rename and Output Simplification)**
- Standardized output suffixes to `_idx.json` and `_idxd.json`.
- Removed special sidecar rename coupling.

5. **Phase 5 (Rollback and Legacy Cleanup)**
- Simplified v4 rollback to uniform file-copy behavior.
- Retained legacy v2/v3 fallback path.
- Added legacy output cleanup feature.

6. **Phase 6 (CLI and GUI Cleanup)**
- Removed meta-merge operations from CLI and GUI.
- Added `--no-sidecar-detection` and `--cleanup-legacy-sidecars`.

7. **Phase 7 (Comprehensive Test Validation)**
- Reworked test suite toward v4 model.
- Added v4 conformance and integration coverage.

8. **Phase 8 (Documentation Site)**
- Updated docs for v4 architecture, new suffixes, and new operation model.

9. **Phase 9 (CHANGELOG, Release, After-Action)**
- Added v1.0.0 changelog section (Added/Changed/Removed with breaking notes).
- Synced docs changelog from root changelog and added explicit auto-sync header.
- Updated README architecture and CLI option documentation to v4 behavior.
- Bumped `src/shruggie_indexer/_version.py` to `1.0.0`.

## Issues Encountered

1. **Release gate mismatch due existing lint baseline**
- `ruff check src/ tests/` fails on pre-existing lint issues outside Phase 9 edits.
- `ruff format --check src/ tests/` reports 30 files needing reformat.
- This prevented a fully clean "all gates pass" release handoff in this session.

2. **Tool output truncation during long test run**
- Initial verbose test invocation output was truncated in the terminal tool.
- Mitigation: reran test suite in compact mode and captured explicit exit code.

## Observations for Future Work

- Stabilize and enforce a repository-wide Ruff baseline before release-tag workflows.
- Add CI job that separately reports "new lint introduced" versus "pre-existing lint debt".
- Consider codifying docs changelog header injection in CI to prevent drift.
- Reassess whether README should include a compact JSON v4 output snippet for downstream integrators.

## Ecosystem Implications

For metadexer and downstream consumers:

- Input contract now assumes v4 first-class entries for all files; sidecars are no longer embedded payloads.
- Consumers should treat `relationships[]` as advisory association metadata, not strict graph truth.
- Legacy v2/v3 rollback compatibility remains in indexer, but new production outputs should be treated as v4-only.
- Output artifact discovery should prioritize `_idx.json` and `_idxd.json` and treat `_meta*` as legacy.
- Parsing pipelines should no longer depend on sidecar-origin metadata fields removed in v4.

Recommended metadexer spec alignment targets:

- Entry ingestion contract: identity, metadata, relationships.
- Relationship confidence usage and downgrade behavior.
- Legacy artifact handling and migration guidance.
- Catalog update logic for v4 suffix conventions.

## Test Summary

Phase 9 verification execution:

- Command: `pytest tests/ --tb=short -q`
- Result: **456 passed, 63 skipped, 3 warnings, exit code 0**

- Command: `mkdocs build --strict`
- Result: **passed**

- Command: `ruff check src/ tests/`
- Result: **failed** (pre-existing lint findings not introduced by Phase 9 file set)

- Command: `ruff format --check src/ tests/`
- Result: **failed** (repository-wide formatting drift; 30 files reported)

Net: runtime and docs quality gates pass; lint/format baseline requires dedicated cleanup before final release tagging on a fully clean gate set.

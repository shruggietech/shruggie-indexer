# Phase 2 Test Suite Audit Report

| Field | Value |
|---|---|
| **Date** | 2026-04-02 |
| **Sprint** | 20260402-001 |
| **Phase** | Phase 2: Test Suite Audit |
| **Status** | Complete |

## Summary

Phase 2 audited all skipped tests and warnings from the post-Phase-1 baseline. The skip inventory now has explicit, categorized reasons with no unexplained skips. The three pytest warnings were traced to a schema draft URI mismatch and resolved in project files (no warning suppression needed).

## Before/After Counts

- Skipped tests (before): 63
- Skipped tests (after): 63
- Warnings (before): 3
- Warnings (after): 0
- Failures (before): 0
- Failures (after): 0

## Skip Inventory (After)

- Platform skip: 6
- ExifTool skip: 0
- Intentional deferral: 57
- Resolved stale skips: 0
- Unknown or unexplained: 0

### Category Notes

- Platform skip (6): macOS-only/Linux-only timestamp tests, non-Windows rollback branch, and Windows symlink privilege-sensitive tests.
- Intentional deferral (57):
- Legacy schema conformance tracks for v2/v3 kept as backward-compat references while v4 is the active target.
- Backward-compat scaffold tests that require MakeIndex-derived fixture corpus not currently published in `tests/fixtures/reference`.
- ExifTool skip (0): no skips caused by missing ExifTool in this environment.
- Unknown skip (0): verified no bare skip markers and no vague skip reasons in active summary.

## Actions Taken

1. Updated six backward-compat scaffold skip reasons in `tests/conformance/test_backward_compat.py` from "Reference data not yet generated" to explicit intentional-deferral wording tied to missing MakeIndex fixture corpus.
2. Resolved warning source by updating Draft-07 metaschema URI from `https://json-schema.org/draft-07/schema#` to canonical `http://json-schema.org/draft-07/schema#` in:
- `docs/schema/shruggie-indexer-v4.schema.json`
- `tests/fixtures/shruggie-indexer-v4.schema.json`
3. Verified no bare `@pytest.mark.skip` decorators without `reason=` remain.

## Warning Investigation

### Warning Type

- `DeprecationWarning` (3 occurrences) from `jsonschema.validators.validator_for()` during v4 schema conformance tests.

### Root Cause

- The v4 schema `$schema` URI used `https://json-schema.org/draft-07/schema#`, which was not found in jsonschema's metaschema registry in this environment.

### Resolution

- Updated schema URI to canonical Draft-07 metaschema identifier (`http://json-schema.org/draft-07/schema#`) in both canonical and fixture copies.

### Outcome

- `pytest tests/ --tb=short -q -W default` now reports no warnings.

## Verification

- `pytest tests/ -v --tb=short -ra` -> `456 passed, 63 skipped`
- `pytest tests/ --tb=short -q -W default` -> `456 passed, 63 skipped` (0 warnings)
- `pytest tests/ -v --tb=short -q` -> `456 passed, 63 skipped`
- `ruff check src/ tests/` -> pass
- `ruff format --check src/ tests/` -> pass

## Acceptance Criteria Check

1. Every skipped test categorized in report: **pass**
2. No skip due to incomplete v4 migration: **pass** (remaining skips are platform constraints or explicit intentional deferral)
3. No bare `@pytest.mark.skip` without reason: **pass**
4. All 3 warnings investigated/resolved/documented: **pass** (resolved in code)
5. Zero test failures: **pass**
6. Ruff lint/format still clean: **pass**
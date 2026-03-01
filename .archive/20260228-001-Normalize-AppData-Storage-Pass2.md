# Normalize AppData Storage — Pass 2 (Remediation)

**Date:** 2026-02-28
**Type:** One-off named update (single sprint)
**Scope:** Remediate incomplete path normalization from prior sprint; address log buffering defect
**Predecessor:** `20260227-004-Normalize-AppData-Storage.md`

---

## Executive Directive

> **READ THIS FIRST. THIS IS NOT OPTIONAL.**
>
> This document is a **remediation sprint**. A prior AI coding agent was given the full set of instructions in `20260227-004-Normalize-AppData-Storage.md` and reported the work as complete. **It was not complete.** Multiple acceptance criteria from that sprint remain unfulfilled. The user has manually cleaned up orphaned files and consolidated data to the canonical location, but the application continues to write to incorrect paths and exhibit incorrect GUI behavior.
>
> **You MUST treat every section of this document as a mandatory, non-negotiable task.** Do not skip items because they "look like they were already done." The prior agent's work is untrustworthy — you must independently verify each item against the actual codebase state before marking anything as complete. If an item's code changes are genuinely already in place and working, say so explicitly with the evidence (file path, line number, function name). If they are not, implement them.
>
> **Do not close this sprint until every acceptance criterion at the end of this document passes.**

---

## Observed Defects (Post-Pass 1)

The following defects were observed on **2026-02-28** after the Pass 1 sprint was reported as complete and all instructions were provided to the implementing agent. The user has independently verified each of these by running the application and inspecting the filesystem.

### Defect 1: Log files written to wrong path

**Evidence:** File Explorer screenshot showing log files accumulating at:
```
%LOCALAPPDATA%\ShruggieTech\shruggie-indexer\logs\
```

**Expected behavior:** Log files should be written to:
```
%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\logs\
```

**Root cause hypothesis:** Either `log_file.py` still contains inline path resolution using the `ShruggieTech` namespace, or it is not actually importing from `app_paths.get_log_dir()` at runtime despite the code appearing correct in the repository. Possible causes include: (a) the refactoring was committed to spec/docs but not to the actual source file, (b) a stale `.pyc` cache is masking the change, or (c) the installed/frozen executable was not rebuilt after the source change.

### Defect 2: Settings page log path display shows wrong path

**Evidence:** GUI screenshot showing the read-only "Log file path" field displaying:
```
C:\Users\h8rt3rmin8r\AppData\Local\ShruggieTech\shruggie-indexer\logs\<timestamp>.log
```

**Expected behavior:** The field should display:
```
C:\Users\h8rt3rmin8r\AppData\Local\shruggie-tech\shruggie-indexer\logs\<timestamp>.log
```

**Root cause:** This field is populated by `SettingsPage._update_log_path_display()`, which calls `get_default_log_dir()`. If Defect 1 exists, this defect follows automatically — they share the same underlying path resolution chain.

### Defect 3: "Open Config Folder" opens wrong directory

**Evidence:** User reports that pressing the "Open Config Folder" button on the Settings page opens a File Explorer window at:
```
%APPDATA%\Roaming\...
```

**Expected behavior:** The button should open:
```
%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\
```

**Root cause hypothesis:** The `_open_config_folder()` method derives its path from `SessionManager._resolve_path().parent`. If `SessionManager._resolve_path()` is still referencing `%APPDATA%` instead of calling `app_paths.get_app_data_dir()`, this defect follows directly. Alternatively, `SessionManager` may have been updated in spec but not in the actual source code.

### Defect 4: Spec §10.4 still references `%APPDATA%`

**Evidence:** The technical specification's §10.4 (Configuration Panel — Open Config Folder) contains:

> Opens the platform-specific application data directory (`%APPDATA%\shruggie-tech\shruggie-indexer\` on Windows...

**Expected:** This should reference `%LOCALAPPDATA%`, consistent with the canonical path table in §3.3a.

### Defect 5: Log file buffering / delayed write behavior (NEW)

**Evidence:** The user observed the following sequence:

1. Opened the `logs/` directory while the GUI application was running.
2. The most recent log file showed a size of **0 KB**.
3. Navigated to the Settings page within the GUI, then navigated back.
4. The same log file now showed a size of **2,019 KB**.

**Implication:** Log data is not being written to disk in real time. The `FileHandler` is either: (a) not attached to the logger at startup, with records accumulating in a buffer or being silently dropped until a Settings page interaction triggers `_sync_file_logging()`, or (b) the file is opened at startup but records are not reaching it because the handler isn't added to the logger's handler list until a later lifecycle event.

**This is not a cosmetic issue.** If the application crashes or is force-killed before the Settings page is visited, the log file for that session will be 0 bytes — containing no diagnostic information whatsoever.

---

## Required Actions

> **IMPLEMENTATION RULE:** For every task below, you MUST first inspect the current state of the relevant source file(s) in the repository. Do not assume that because `app_paths.py` exists and is correct, the consumer modules are actually importing from it. **Grep the codebase** for residual occurrences of `ShruggieTech`, `APPDATA` (without the `LOCAL` prefix in non-legacy-fallback contexts), and any inline path resolution that should have been replaced.

### 1. Full Codebase Audit (Priority: CRITICAL — Do This First)

Before making any changes, execute the following audit commands and record their output. This establishes ground truth.

#### 1.1. Search for `ShruggieTech` (PascalCase)

```bash
grep -rn "ShruggieTech" src/ tests/ docs/ shruggie-indexer-spec.md CHANGELOG.md
```

**Expected result:** Zero matches. If any matches are found outside of legacy-path fallback comments or migration documentation, they represent unfixed defects from Pass 1.

#### 1.2. Search for inline `APPDATA` usage (non-legacy)

```bash
grep -rn "APPDATA" src/shruggie_indexer/ --include="*.py" | grep -v "LOCALAPPDATA" | grep -v "legacy" | grep -v "_legacy_roaming_base" | grep -v "# v0.1"
```

**Expected result:** Zero matches outside of `app_paths.py` fallback logic and `SessionManager._legacy_roaming_base()`. Any match in `log_file.py`, `config/loader.py` main path resolution, or `gui/app.py` `SessionManager._resolve_path()` is a Pass 1 failure.

#### 1.3. Search for inline path resolution

```bash
grep -rn "os.environ.get.*APPDATA\|os.environ\[.*APPDATA\]" src/shruggie_indexer/ --include="*.py"
```

**Expected result:** Matches ONLY in:
- `app_paths.py` → `os.environ.get("LOCALAPPDATA", ...)`
- `gui/app.py` → `SessionManager._legacy_roaming_base()` → `os.environ.get("APPDATA", ...)`
- `config/loader.py` → `_legacy_roaming_base()` → `os.environ.get("APPDATA", ...)`

Any `os.environ.get("APPDATA", ...)` in a primary (non-legacy-fallback) code path is a defect.

#### 1.4. Verify `app_paths.py` is the sole authority

```bash
grep -rn "from shruggie_indexer.app_paths import\|from shruggie_indexer import app_paths" src/shruggie_indexer/ --include="*.py"
```

**Expected result:** At minimum, matches in:
- `log_file.py`
- `gui/app.py`
- `config/loader.py`

If any of these files do NOT import from `app_paths`, that file was not refactored during Pass 1.

#### 1.5. Record audit results

**YOU MUST** paste the output of each grep command into the commit message or a summary comment before proceeding with fixes. This creates an evidence trail showing what was and was not completed by the prior agent.

---

### 2. Fix Log File Path Resolution (Priority: CRITICAL)

#### 2.1. Verify `log_file.py`

Open `src/shruggie_indexer/log_file.py` and confirm:

1. The file contains `from shruggie_indexer.app_paths import get_log_dir` (or equivalent).
2. The `get_default_log_dir()` function body is `return get_log_dir()` — a thin delegation with no inline path logic.
3. There is **no** occurrence of the string `ShruggieTech` anywhere in the file.
4. There is **no** `os.environ.get("LOCALAPPDATA", ...)` or `platform.system()` branching for path resolution in this file (that logic lives exclusively in `app_paths.py`).

If any of these conditions are not met, fix them. The target state for this file is documented in `20260227-004-Normalize-AppData-Storage.md` §1.2.C and is reproduced here for reference:

```python
"""Persistent log file support for shruggie-indexer.

Provides a factory for creating ``logging.FileHandler`` instances with
the correct format.  Log directory resolution is delegated to
:func:`shruggie_indexer.app_paths.get_log_dir` — the single source of
truth for all application data paths.

See spec §11.1 — Logging Architecture.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from shruggie_indexer.app_paths import get_log_dir

__all__ = [
    "get_default_log_dir",
    "make_file_handler",
]


def get_default_log_dir() -> Path:
    """Return the platform-appropriate log directory.

    Delegates to :func:`shruggie_indexer.app_paths.get_log_dir`.
    """
    return get_log_dir()
```

#### 2.2. Verify `app_paths.py`

Open `src/shruggie_indexer/app_paths.py` and confirm:

1. `_ECOSYSTEM_DIR = "shruggie-tech"` (kebab-case, NOT `ShruggieTech`).
2. `get_app_data_dir()` uses `os.environ.get("LOCALAPPDATA", ...)` on Windows.
3. `get_log_dir()` returns `get_app_data_dir() / "logs"`.

If this file is correct, no changes are needed here.

#### 2.3. Clear stale bytecode

After confirming or applying source changes, delete all `__pycache__` directories and `.pyc` files:

```bash
find src/ -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find src/ -name "*.pyc" -delete 2>/dev/null
```

This eliminates the possibility that a stale compiled module is masking source changes.

---

### 3. Fix "Open Config Folder" Button (Priority: CRITICAL)

#### 3.1. Verify `SessionManager._resolve_path()`

Open `src/shruggie_indexer/gui/app.py` and locate the `SessionManager._resolve_path()` static method. Confirm:

1. It imports from `app_paths`: `from shruggie_indexer.app_paths import get_app_data_dir`
2. It returns `get_app_data_dir() / SessionManager._SESSION_FILENAME`
3. There is **no** reference to `os.environ.get("APPDATA", ...)` in this method.
4. The old `_config_base()` method does NOT exist. If it still exists, it is dead code from before Pass 1 and must be deleted.
5. The class constants `_ECOSYSTEM_DIR` and `_TOOL_DIR` do NOT exist on `SessionManager`. If they still exist, they are dead code and must be deleted — these constants are now owned exclusively by `app_paths.py`.

#### 3.2. Verify `_open_config_folder()`

In the same file, locate `SettingsPage._open_config_folder()`. Confirm it derives its path from `SessionManager._resolve_path().parent`:

```python
def _open_config_folder(self) -> None:
    session_path = SessionManager._resolve_path()
    folder = session_path.parent
    folder.mkdir(parents=True, exist_ok=True)
    # ... platform-specific open command
```

If `_open_config_folder()` resolves its own path (e.g., by calling `os.environ.get("APPDATA", ...)` directly), replace it with the derivation above.

#### 3.3. Verify the button actually opens the right directory

After applying any fixes, the path opened by this button on Windows MUST resolve to:

```
%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\
```

This directory should now contain `gui-session.json`, optionally `config.toml`, and the `logs/` subdirectory.

---

### 4. Fix Config Loader Path Resolution (Priority: HIGH)

#### 4.1. Verify `config/loader.py`

Open `src/shruggie_indexer/config/loader.py` and confirm:

1. The `_find_user_config()` function's **primary** path (Tier 1) uses `app_paths.get_app_data_dir() / "config.toml"`.
2. The old `_resolve_config_base()` function does NOT exist. If it still exists, it must be replaced with the `_find_user_config()` three-tier fallback.
3. The only references to `os.environ.get("APPDATA", ...)` are inside `_legacy_roaming_base()`, which is used exclusively for fallback tiers 2 and 3.

---

### 5. Fix Spec §10.4 Path Reference (Priority: HIGH)

#### 5.1. Problem

The specification's §10.4 (Configuration Panel — "Open Config Folder") still references `%APPDATA%` in the path description for the button's behavior.

#### 5.2. Required Change

Locate the "Open Config Folder" paragraph in `shruggie-indexer-spec.md` §10.4 and replace the Windows path. Change:

```
`%APPDATA%\shruggie-tech\shruggie-indexer\`
```

to:

```
`%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\`
```

Also update the descriptive text to reference the canonical application data directory (§3.3a) rather than stating the path inline, consistent with the spec hardening done in Pass 1 §3.2.

Add an `> **Updated 2026-02-28:**` callout noting the correction.

---

### 6. Fix Log File Buffering / Delayed Write (Priority: HIGH)

#### 6.1. Problem Analysis

The 0 KB log file observation indicates that the persistent `FileHandler` is either:

**(a)** Created at startup (file opened on disk, hence the 0-byte file appears) but not attached to the `shruggie_indexer` logger until a later event — specifically, until `SettingsPage._sync_file_logging()` fires, which only happens when the Settings page widgets are interacted with or when the page is rendered.

**(b)** Created and attached, but with the logger's effective level set such that no records pass through until a later reconfiguration.

Based on the code architecture, hypothesis (a) is most likely. Here is the relevant lifecycle:

1. `ShruggiApp.__init__()` calls `_restore_session()`, then `_setup_file_logging()`.
2. `_setup_file_logging()` checks `hasattr(self, "_settings_tab")`. If the Settings tab hasn't been constructed yet (which depends on tab initialization order), the guard is bypassed and the handler is created unconditionally.
3. However, `_setup_file_logging()` calls `make_file_handler()`, which opens the file — creating the 0-byte file on disk.
4. The handler is added to the logger via `lib_logger.addHandler(...)`.
5. But the logger level or handler level might not be set correctly at this point, preventing records from reaching the handler.
6. When the user navigates to Settings, `_sync_file_logging()` fires, which may re-attach or reconfigure the handler, at which point buffered or new records start flowing.

#### 6.2. Root Cause Verification

**YOU MUST** inspect the following before implementing a fix:

1. In `_setup_file_logging()`: After the handler is created and added, is `lib_logger.setLevel(logging.DEBUG)` called? If not, the logger's default level (WARNING) will filter out INFO and DEBUG records before they reach the handler.
2. Is the handler's own level set via `handler.setLevel(logging.DEBUG)`?
3. Does any code path between `_setup_file_logging()` and the first log record call `lib_logger.removeHandler(...)` on the persistent handler?
4. Is there a timing issue where `_settings_tab` is constructed AFTER `_setup_file_logging()` runs, and the Settings tab's `__init__` calls `_sync_file_logging()` which detaches and re-creates the handler?

#### 6.3. Required Fix

The persistent file handler MUST be fully functional from the moment it is created. Log records MUST appear in the file in real time (or near-real-time, subject only to OS-level I/O buffering which is typically sub-second for small writes). Specifically:

**A. Ensure the handler is attached and levels are correct immediately after creation.**

In `_setup_file_logging()`, after creating the handler:

```python
self._persistent_file_handler = make_file_handler()
self._persistent_file_handler.setLevel(logging.DEBUG)
lib_logger.setLevel(logging.DEBUG)
lib_logger.addHandler(self._persistent_file_handler)
```

All four lines must execute as a unit. No early return or conditional should prevent the `addHandler` call after the handler has been created.

**B. Ensure no subsequent initialization step silently detaches the handler.**

If `SettingsPage.__init__()` calls `_sync_file_logging()`, and that method's logic determines that logging should be disabled (e.g., because the checkbox variable hasn't been restored from the session yet), it will call `lib_logger.removeHandler(self._persistent_file_handler)` — undoing what `_setup_file_logging()` just did. This is the most likely cause of the 0-byte observation.

The fix is to ensure that `_sync_file_logging()` does NOT run during `SettingsPage.__init__()` construction. Session values must be fully restored into the Settings tab's widget variables BEFORE `_sync_file_logging()` is called for the first time. If the Settings tab is constructed before session restore, `_sync_file_logging()` must be deferred.

**C. Add explicit flush after handler creation.**

After the first log record is written via the persistent handler, call:

```python
self._persistent_file_handler.flush()
```

Python's `logging.FileHandler` calls `self.stream.write()` + `self.flush()` on every `emit()`, so individual records should already be flushed. However, if the handler's stream is line-buffered or block-buffered (which can happen on some platforms), an explicit flush after the initial "GUI started" log record ensures the file is non-empty on disk immediately.

**D. Consider setting the FileHandler to unbuffered mode.**

When creating the `FileHandler` in `make_file_handler()`, the underlying file stream can be forced to unbuffered or line-buffered mode. The simplest approach is to ensure the existing `logging.FileHandler(log_path, encoding="utf-8")` call produces an unbuffered stream. Since `FileHandler` inherits from `StreamHandler` and calls `self.flush()` in `emit()`, this should already be the case — but verify by checking whether the stream's `write_through` attribute (Python 3.7+) is set.

If additional assurance is needed, add a post-creation step:

```python
handler = logging.FileHandler(log_path, encoding="utf-8")
# Force line-buffered mode for real-time log visibility
if hasattr(handler.stream, 'reconfigure'):
    handler.stream.reconfigure(line_buffering=True)
```

#### 6.4. Verification Test

After the fix, the following sequence MUST produce a non-zero log file:

1. Launch the GUI application.
2. Wait 3 seconds (do NOT interact with the GUI).
3. Inspect the latest log file in `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\logs\`.
4. The file MUST be non-zero and MUST contain at least the "Shruggie Indexer GUI vX.Y.Z started" line.

If the file is 0 bytes after step 3, the fix is incomplete.

---

### 7. Comprehensive Spec & Documentation Audit (Priority: MEDIUM)

The Pass 1 document specified documentation updates for multiple files. Verify each one was actually completed.

#### 7.1. Spec file (`shruggie-indexer-spec.md`)

| Check | Section | What to verify |
|-------|---------|---------------|
| A | §3.3 / §3.3a | Canonical path table exists with `%LOCALAPPDATA%` for Windows. No `%APPDATA%` in primary path entries. |
| B | §10.1 | Session persistence references §3.3a for paths, not inline `%APPDATA%`. |
| C | §10.4 | "Open Config Folder" description uses `%LOCALAPPDATA%`, not `%APPDATA%`. **(Known defect — see Section 5 above.)** |
| D | §11.1 | Log directory path table references §3.3a or shows `%LOCALAPPDATA%\shruggie-tech\...`. No `ShruggieTech`. |
| E | §3.2 | Source package layout lists `app_paths.py`. |
| F | §12 (Tests) | `test_app_paths.py` is documented. |

For each check: open the spec, locate the section, and verify. If the text is wrong, fix it and add a `> **Updated 2026-02-28:**` callout.

#### 7.2. Documentation site files

| File | What to verify |
|------|---------------|
| `docs/user-guide/configuration.md` | Config file path table shows `%LOCALAPPDATA%`, not `%APPDATA%`. No `ShruggieTech`. |
| `docs/user-guide/gui.md` | Session persistence path shows `%LOCALAPPDATA%`. "Open Config Folder" description is correct. |
| `docs/user-guide/cli-reference.md` | `--log-file` default directory shows `%LOCALAPPDATA%\shruggie-tech\...`. No `ShruggieTech`. |

For each file: open it, search for `APPDATA` (without `LOCAL` prefix) and `ShruggieTech`. Any matches (outside of explicit legacy/migration context) are defects.

#### 7.3. CHANGELOG

Verify that `CHANGELOG.md` (and `docs/changelog.md` if it is a separate file) contains an entry documenting the path consolidation. If the Pass 1 agent did not add this entry, add one now referencing both Pass 1 and Pass 2:

```markdown
### Changed
- **Application data directory consolidation.** All application data (session files,
  configuration, and log files) is now stored under a single canonical directory per
  platform. On Windows, this is `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\`.
  The `ShruggieTech` (PascalCase) namespace and the `%APPDATA%` (Roaming) storage
  location are no longer used for new data. Legacy files at old locations are
  discovered via fallback and migrated on next save.
- **Log file handler lifecycle fix.** The persistent file logging handler is now
  fully attached and writing from application startup, eliminating a race condition
  that could produce 0-byte log files.
```

---

### 8. Test Verification (Priority: MEDIUM)

#### 8.1. Existing tests

Run the full test suite:

```bash
python -m pytest tests/ -v
```

All tests must pass. Pay specific attention to:

- `tests/unit/test_app_paths.py` — Validates canonical path resolution.
- `tests/unit/test_log_file.py` — Validates log directory resolution delegates to `app_paths`.
- `tests/unit/test_config.py` — Validates config file resolution fallback chain.

If `test_app_paths.py` does not exist, it was not created during Pass 1. Create it per the specification in `20260227-004-Normalize-AppData-Storage.md` §2.3 and the test spec in the technical specification's §12 (`test_app_paths.py`).

#### 8.2. No-PascalCase assertion

Verify that the following test case exists in `test_app_paths.py`:

```python
def test_no_pascalcase_namespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Path string does not contain 'ShruggieTech' on any platform."""
    for system in ("Windows", "Darwin", "Linux"):
        monkeypatch.setattr("shruggie_indexer.app_paths.platform.system", lambda s=system: s)
        if system == "Windows":
            monkeypatch.setenv("LOCALAPPDATA", "/tmp/test")
        result = str(get_log_dir())
        assert "ShruggieTech" not in result, f"PascalCase namespace found on {system}: {result}"
```

If this test does not exist, add it.

#### 8.3. Log delegation test

Verify that the following test case exists (in either `test_app_paths.py` or `test_log_file.py`):

```python
def test_log_file_delegates_to_app_paths(self) -> None:
    """log_file.get_default_log_dir() returns the same value as app_paths.get_log_dir()."""
    from shruggie_indexer.app_paths import get_log_dir
    from shruggie_indexer.log_file import get_default_log_dir
    assert get_default_log_dir() == get_log_dir()
```

---

## Affected Files Summary

| File | Nature of change |
|------|------------------|
| `src/shruggie_indexer/log_file.py` | **Verify and fix:** Must delegate to `app_paths.get_log_dir()`. No inline path logic. No `ShruggieTech`. |
| `src/shruggie_indexer/gui/app.py` | **Verify and fix:** `SessionManager._resolve_path()` must use `app_paths.get_app_data_dir()`. No residual `_config_base()`. No residual `_ECOSYSTEM_DIR`/`_TOOL_DIR` constants. Fix `_setup_file_logging()` lifecycle for immediate handler attachment. |
| `src/shruggie_indexer/config/loader.py` | **Verify and fix:** `_find_user_config()` Tier 1 must use `app_paths.get_app_data_dir()`. No residual `_resolve_config_base()`. |
| `src/shruggie_indexer/app_paths.py` | **Verify only:** Should be correct from Pass 1. Confirm `_ECOSYSTEM_DIR = "shruggie-tech"` and `LOCALAPPDATA`. |
| `shruggie-indexer-spec.md` | **Fix:** §10.4 `%APPDATA%` → `%LOCALAPPDATA%`. Audit §3.3, §10.1, §11.1 for completeness. |
| `docs/user-guide/configuration.md` | **Verify and fix:** Path tables. |
| `docs/user-guide/gui.md` | **Verify and fix:** Path tables and "Open Config Folder" description. |
| `docs/user-guide/cli-reference.md` | **Verify and fix:** `--log-file` default path. |
| `CHANGELOG.md` | **Verify and fix:** Consolidation entry exists. Add Pass 2 entry if needed. |
| `docs/changelog.md` | **Verify and fix:** Synced from `CHANGELOG.md`. |
| `tests/unit/test_app_paths.py` | **Verify:** Exists and includes PascalCase / delegation tests. |
| `tests/unit/test_log_file.py` | **Verify:** Expected paths updated. |
| `tests/unit/test_config.py` | **Verify:** Expected paths updated. |

---

## Acceptance Criteria

> **Every item below must be independently verified against the actual codebase and runtime behavior. Do not carry forward "already done" assertions from the Pass 1 sprint without re-verification.**

### Code-level criteria

- [ ] `app_paths.py` is the sole source of truth for application data paths. Confirmed by grep: no inline `os.environ.get("APPDATA"...)` or `os.environ.get("LOCALAPPDATA"...)` in any file except `app_paths.py` itself and legacy-fallback functions.
- [ ] `log_file.py` contains `from shruggie_indexer.app_paths import get_log_dir` and `get_default_log_dir()` returns `get_log_dir()` with no other logic.
- [ ] `SessionManager._resolve_path()` calls `app_paths.get_app_data_dir()`. No residual `_config_base()`, `_ECOSYSTEM_DIR`, or `_TOOL_DIR`.
- [ ] `config/loader.py` `_find_user_config()` uses `app_paths.get_app_data_dir()` for Tier 1. No residual `_resolve_config_base()`.
- [ ] The string `ShruggieTech` (PascalCase) does not appear anywhere in `src/` except in legacy migration comments or documentation about the old path.
- [ ] All `__pycache__` directories have been purged after source changes.

### Runtime behavior criteria (Windows)

- [ ] Log files are created at `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\logs\`.
- [ ] The Settings page "Log file path" field displays `...\shruggie-tech\shruggie-indexer\logs\<timestamp>.log`.
- [ ] The "Open Config Folder" button opens `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\` in File Explorer.
- [ ] The `gui-session.json` file is written to `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\`.
- [ ] Session files at legacy paths (`%APPDATA%\shruggie-tech\...` and `%APPDATA%\shruggie-indexer\...`) are discovered via fallback and migrated on save.

### Log handler lifecycle criteria

- [ ] The persistent `FileHandler` is attached to the `shruggie_indexer` logger and writing records **immediately after application startup**, without requiring any user interaction with the GUI.
- [ ] A log file created by a fresh GUI launch is **non-zero bytes** within 3 seconds of startup, containing at least the "GUI started" log line.
- [ ] The handler remains attached and functional throughout the application's lifetime, regardless of which GUI pages are visited.
- [ ] Navigating between GUI pages does NOT cause the handler to be detached and re-attached (no record loss window).

### Spec and documentation criteria

- [ ] §10.4 references `%LOCALAPPDATA%` (not `%APPDATA%`).
- [ ] §3.3 / §3.3a canonical path table is correct and complete.
- [ ] §10.1 references §3.3a for session paths.
- [ ] §11.1 references §3.3a for log paths and contains no `ShruggieTech`.
- [ ] `docs/user-guide/configuration.md` shows `%LOCALAPPDATA%` for Windows paths.
- [ ] `docs/user-guide/gui.md` shows `%LOCALAPPDATA%` for session/config paths.
- [ ] `docs/user-guide/cli-reference.md` shows `%LOCALAPPDATA%\shruggie-tech\...` for log paths.
- [ ] `CHANGELOG.md` documents the consolidation (Pass 1 + Pass 2).

### Test criteria

- [ ] `test_app_paths.py` exists and all tests pass.
- [ ] `test_log_file.py` expected paths reference `shruggie-tech` (not `ShruggieTech`).
- [ ] `test_config.py` expected paths reference `shruggie-tech` (not `ShruggieTech`).
- [ ] A test exists asserting that `log_file.get_default_log_dir() == app_paths.get_log_dir()`.
- [ ] A test exists asserting no PascalCase `ShruggieTech` namespace on any platform.
- [ ] Full test suite passes: `python -m pytest tests/ -v` exits 0.

---

## Spec References

| Section | Relevance |
|---------|-----------|
| §3.3 / §3.3a — Application Data Directory | Canonical path table (single source of truth) |
| §10.1 — GUI Framework and Architecture | Session persistence paths |
| §10.4 — Configuration Panel | "Open Config Folder" button behavior **(known defect)** |
| §10.8.5 — Debug Logging | Queue-based handler architecture |
| §11.1 — Logging Architecture | Persistent file logging, Principle 3 |
| §3.2 — Source Package Layout | `app_paths.py` module listing |

---

## Risk Notes

- **Stale bytecode.** The most likely explanation for "code looks correct but behavior is wrong" is stale `.pyc` files. The audit in Section 1 and the cache purge in Section 2.3 address this, but the implementing agent must also ensure that if a PyInstaller build is being used, the executable is **rebuilt** after source changes. Simply editing `.py` files does not affect a frozen executable.

- **Session restore / handler lifecycle interaction.** The log buffering fix (Section 6) touches the same initialization sequence that was modified in Batch 3 (20260227-003) to resolve the original 0-byte orphan bug. The Pass 1 risk notes flagged this interaction. The fix described here preserves the Batch 3 architecture (deferred `_setup_file_logging()` after `_restore_session()`) but adds a constraint: `_sync_file_logging()` must not run during `SettingsPage.__init__()` if session values haven't been restored yet. Test this interaction explicitly by launching the app with and without an existing session file.

- **Cross-platform verification.** The defects were observed on Windows. The canonical path logic in `app_paths.py` affects all platforms. After applying fixes, verify (at minimum via the unit tests with mocked `platform.system()`) that Linux and macOS paths are also correct.

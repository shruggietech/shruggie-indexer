# Normalize AppData Storage Paths

**Date:** 2026-02-27
**Type:** One-off named update (single sprint)
**Scope:** Application data directory consolidation, namespace normalization, spec hardening

---

## Background Research: `AppData\Local` vs `AppData\Roaming`

### What they are

On Windows, per-user application data is stored under `%USERPROFILE%\AppData\` in three subdirectories. Only two are relevant here:

| Directory | Environment Variable | Purpose |
|-----------|---------------------|---------|
| `AppData\Roaming` | `%APPDATA%` | Data intended to follow the user across machines in a Windows domain environment. Synced to a network server on logout and pulled down on login when roaming profiles are configured. |
| `AppData\Local` | `%LOCALAPPDATA%` | Data bound to the local machine. Never synced. Appropriate for caches, logs, large files, and anything machine-specific or not worth syncing. |

### What the conventions say

Microsoft's own guidance (via KNOWNFOLDERID, CSIDL, and the ApplicationData API documentation) draws the line as follows:

- **Roaming** is for small, machine-independent user preferences that should travel with the user across domain-joined workstations. Examples: custom dictionaries, application preferences, toolbar layouts.
- **Local** is for data that is machine-specific, too large to sync efficiently, or not meaningful on another machine. Examples: caches, temporary files, logs, locally-generated databases.

There is no hard byte-count threshold, but Microsoft advises keeping roaming data small because large roaming profiles cause slow logins and logout-only sync creates surprises.

### The Windows 11 reality

**Roaming profile sync is deprecated as of Windows 11.** Microsoft's own documentation for `ApplicationData.RoamingFolder` now states: *"Roaming data and settings is no longer supported as of Windows 11. The recommended replacement is Azure App Service."* The `Roaming` directory still exists and is still writable, but the sync mechanism that gave it meaning is gone for the current OS. The distinction between Local and Roaming is now effectively vestigial on standalone machines, which is what the vast majority of shruggie-indexer users will be running.

### What `platformdirs` does

The `platformdirs` library (the actively maintained successor to `appdirs`, and the de facto Python standard for resolving platform-appropriate application data paths) defaults to `AppData\Local` for all path types on Windows:

| `platformdirs` function | Windows path |
|------------------------|--------------|
| `user_data_dir()` | `%LOCALAPPDATA%\{author}\{app}` |
| `user_config_dir()` | `%LOCALAPPDATA%\{author}\{app}` |
| `user_cache_dir()` | `%LOCALAPPDATA%\{author}\{app}\Cache` |
| `user_log_dir()` | `%LOCALAPPDATA%\{author}\{app}\Logs` |

`Roaming` is only used when the caller explicitly opts in with `roaming=True`. The library's changelog documents this as a deliberate design choice: *"Because a large roaming profile can cause login speed issues."*

### Recommendation for shruggie-indexer

shruggie-indexer is a standalone desktop tool. It is not designed for Windows domain roaming scenarios. Its settings, session data, and logs are all machine-local concerns. Given that Windows 11 has deprecated roaming sync, that `platformdirs` defaults to `Local`, and that consolidating everything under one root simplifies both the implementation and the user's mental model, the correct choice is:

**Use `%LOCALAPPDATA%` (i.e., `AppData\Local`) for all application data on Windows.**

---

## Problem Statement

The GUI application currently writes application data to two different AppData roots using two different namespace conventions. This was never an intentional design decision — it was introduced across separate sprints by different AI agent sessions that each resolved paths independently without cross-referencing each other's choices.

### Current state (Windows)

| Data type | Current path | AppData root | Namespace |
|-----------|-------------|--------------|-----------|
| GUI session file | `%APPDATA%\shruggie-tech\shruggie-indexer\gui-session.json` | **Roaming** | `shruggie-tech` |
| TOML config file | `%APPDATA%\shruggie-tech\shruggie-indexer\config.toml` | **Roaming** | `shruggie-tech` |
| Log files | `%LOCALAPPDATA%\ShruggieTech\shruggie-indexer\logs\` | **Local** | `ShruggieTech` |

### Current state (macOS)

| Data type | Current path | Namespace |
|-----------|-------------|-----------|
| GUI session / config | `~/Library/Application Support/shruggie-tech/shruggie-indexer/` | `shruggie-tech` |
| Log files | `~/Library/Application Support/ShruggieTech/shruggie-indexer/logs/` | `ShruggieTech` |

### Current state (Linux)

| Data type | Current path | XDG base | Namespace |
|-----------|-------------|----------|-----------|
| GUI session / config | `~/.config/shruggie-tech/shruggie-indexer/` | `XDG_CONFIG_HOME` | `shruggie-tech` |
| Log files | `~/.local/share/shruggie-indexer/logs/` | `XDG_DATA_HOME` | _(missing `shruggie-tech` parent entirely)_ |

### Three distinct defects

1. **Inconsistent namespace casing.** The session/config layer uses `shruggie-tech` (kebab-case, correct per project convention). The logging layer uses `ShruggieTech` (PascalCase, incorrect — this string appears nowhere in the project's identity conventions). On Linux, the logging layer omits the ecosystem namespace parent entirely.

2. **Split storage locations on Windows.** Settings live under `Roaming`; logs live under `Local`. This means the "Open Config Folder" button in the GUI shows the user one directory, but logs are silently written to a completely different directory tree. The user has no reasonable way to discover this.

3. **No single source of truth in the spec.** The specification documents the session path (§10.1) and the log path (§11.1) in separate sections, using different environment variables and different namespace strings. There is no unified "Application Data Directory" section that defines the canonical base path for all tool-generated data. This is how the inconsistency was introduced in the first place — each sprint's AI agent resolved its own path independently.

### User-facing impact

The "Open Config Folder" button on the Settings page currently opens `%APPDATA%\shruggie-tech\shruggie-indexer\`. This directory contains the session file and (if present) the TOML config. It does **not** contain the logs directory. A user who clicks this button to find their logs will see no `logs/` folder and reasonably conclude that no logs exist. This is exactly what happened — the log files were being written the entire time, but to a different location that the GUI never surfaces.

---

## Target State

All application data consolidated under a single directory per platform, using the canonical `shruggie-tech` ecosystem namespace:

### Target paths

| Platform | Base path | Resolved via |
|----------|-----------|--------------|
| Windows | `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\` | `os.environ["LOCALAPPDATA"]` with fallback to `~/AppData/Local` |
| Linux | `~/.config/shruggie-tech/shruggie-indexer/` | `$XDG_CONFIG_HOME` with fallback to `~/.config` |
| macOS | `~/Library/Application Support/shruggie-tech/shruggie-indexer/` | Hardcoded `~/Library/Application Support` |

### Target directory layout (all platforms)

```
<base>/shruggie-tech/
├── shared.toml                         # (future — cross-tool config)
├── shruggie-indexer/
│   ├── gui-session.json
│   ├── config.toml                     # (if present)
│   └── logs/
│       ├── 2026-02-27_143002.log
│       └── ...
├── shruggie-catalog/                   # (future)
└── ...
```

### What changes per platform

| Platform | Config/session change | Logging change |
|----------|----------------------|----------------|
| Windows | `%APPDATA%` → `%LOCALAPPDATA%`; no namespace change | `%LOCALAPPDATA%\ShruggieTech\` → `%LOCALAPPDATA%\shruggie-tech\`; logs move into unified directory |
| Linux | No base change | `~/.local/share/shruggie-indexer/logs/` → `~/.config/shruggie-tech/shruggie-indexer/logs/` |
| macOS | No base change | `ShruggieTech` → `shruggie-tech` (case fix only) |

---

## Sprint: Normalize Application Data Storage

### 1. Unified Path Resolution (Priority: Critical)

#### 1.1. Problem

There are currently two independent path resolution functions that produce inconsistent results:

- `SessionManager._config_base()` in `gui/app.py` — returns `%APPDATA%` on Windows.
- `get_default_log_dir()` in `log_file.py` — returns `%LOCALAPPDATA%\ShruggieTech\...` on Windows.
- `_resolve_config_base()` in `config/loader.py` — returns `%APPDATA%` on Windows.

Each was written in isolation. None references the others.

#### 1.2. Required Changes

**A. Create a single canonical path resolver.** Add a new module `src/shruggie_indexer/app_paths.py` that defines the one and only source of truth for all application data directories:

```python
"""Canonical application data paths for shruggie-indexer.

Every module that needs to read or write to the application data
directory MUST import from this module.  Do not resolve paths
independently.

See spec §3.3 for the full specification.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

_ECOSYSTEM_DIR = "shruggie-tech"
_TOOL_DIR = "shruggie-indexer"


def get_app_data_dir() -> Path:
    """Return the canonical application data directory.

    All tool-generated data (session files, configuration, logs)
    lives under this directory or its subdirectories.

    | Platform | Path |
    |----------|------|
    | Windows  | ``%LOCALAPPDATA%\\shruggie-tech\\shruggie-indexer`` |
    | macOS    | ``~/Library/Application Support/shruggie-tech/shruggie-indexer`` |
    | Linux    | ``~/.config/shruggie-tech/shruggie-indexer`` |
    """
    system = platform.system()
    if system == "Windows":
        base = Path(
            os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"),
        )
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"),
        )
    return base / _ECOSYSTEM_DIR / _TOOL_DIR


def get_log_dir() -> Path:
    """Return the log file directory: ``<app_data_dir>/logs/``."""
    return get_app_data_dir() / "logs"
```

**B. Refactor all consumers to import from `app_paths`.** Remove the inline path resolution from each module and replace with imports:

| File | Current path resolution | Replace with |
|------|------------------------|--------------|
| `gui/app.py` — `SessionManager._config_base()` | Inline `os.environ.get("APPDATA", ...)` | `from shruggie_indexer.app_paths import get_app_data_dir` |
| `log_file.py` — `get_default_log_dir()` | Inline `os.environ.get("LOCALAPPDATA", ...)` with per-platform branching | `from shruggie_indexer.app_paths import get_log_dir` |
| `config/loader.py` — `_resolve_config_base()` | Inline `os.environ.get("APPDATA", ...)` | `from shruggie_indexer.app_paths import get_app_data_dir` |

**C. Simplify `log_file.py`.** The `get_default_log_dir()` function becomes a thin wrapper (or is eliminated entirely in favor of direct `get_log_dir()` calls). The per-platform branching and the `ShruggieTech` namespace string are removed.

**D. Update `SessionManager`.** Replace `_config_base()` with a call to `get_app_data_dir()`. The `_ECOSYSTEM_DIR` and `_TOOL_DIR` class constants on `SessionManager` are removed — the canonical path is now owned by `app_paths.py`.

**E. Update `config/loader.py`.** Replace `_resolve_config_base()` with `get_app_data_dir().parent.parent` ... no, that's fragile. Instead, `_resolve_config_base()` should return `get_app_data_dir().parent` (which gives the `shruggie-tech/` directory, under which `shruggie-indexer/config.toml` lives). Actually, the cleanest approach: `_find_user_config()` should look for `get_app_data_dir() / "config.toml"` directly. This eliminates the intermediate `_resolve_config_base()` function entirely.

#### 1.3. Design Rationale

A single module that owns all path resolution:

- Makes it impossible for future sprints to introduce new inconsistencies.
- Gives the spec a single section to reference for all data paths.
- Is trivially testable (mock the environment variable or `platform.system()`).
- Follows the same "single source of truth" pattern used for compiled defaults (`config/defaults.py`).

#### 1.4. Deviation Notice

**DEVIATION: `%APPDATA%` → `%LOCALAPPDATA%` on Windows.** The config loader (`config/loader.py`) and session manager (`gui/app.py`) currently use `%APPDATA%` (Roaming). This sprint changes both to `%LOCALAPPDATA%` (Local). The rationale is documented in the Background Research section above. In brief: roaming sync is deprecated on Windows 11, `platformdirs` defaults to Local, and consolidating all data under one root eliminates the split-directory problem.

**DEVIATION: `ShruggieTech` → `shruggie-tech` for logging namespace.** The `log_file.py` module uses `ShruggieTech` as the namespace directory. This was never the project's convention — all other ecosystem references use `shruggie-tech` (kebab-case). This sprint corrects the casing.

### 2. Legacy Path Migration (Priority: High)

#### 2.1. Problem

This sprint introduces a third generation of path locations. The migration fallback chain now has three tiers:

| Generation | Windows config/session path | Introduced in |
|------------|----------------------------|--------------|
| v0.1.0 | `%APPDATA%\shruggie-indexer\` | Sprint 1.x |
| v0.1.1 (current) | `%APPDATA%\shruggie-tech\shruggie-indexer\` | Sprint 3 (20260225-003) |
| v0.1.1 (corrected) | `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\` | This sprint |

For logs, there is also a legacy path at `%LOCALAPPDATA%\ShruggieTech\shruggie-indexer\logs\` (incorrect namespace). However, unlike session/config files, log files are write-only artifacts — the application never reads them back. There is no migration concern for logs; they simply start appearing at the new correct path.

#### 2.2. Required Changes

**A. Three-tier read fallback for session files.** `SessionManager._resolve_read_path()` must check paths in this order:

1. `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\gui-session.json` (new canonical)
2. `%APPDATA%\shruggie-tech\shruggie-indexer\gui-session.json` (v0.1.1 Roaming)
3. `%APPDATA%\shruggie-indexer\gui-session.json` (v0.1.0 flat)

On Linux/macOS, tiers 1 and 2 collapse to the same path (no Local/Roaming distinction), so the effective check is two-tier: new namespaced → legacy flat.

**B. Three-tier read fallback for TOML config.** `_find_user_config()` in `config/loader.py` must check:

1. `<canonical_app_data_dir>/config.toml` (new)
2. `%APPDATA%\shruggie-tech\shruggie-indexer\config.toml` (v0.1.1 Roaming — Windows only)
3. `%APPDATA%\shruggie-indexer\config.toml` (v0.1.0 flat — Windows only)

On Linux/macOS, only tiers 1 and 3 apply.

**C. Writes always target the canonical path.** As with the existing migration strategy, all writes go to the new canonical location. Legacy files are preserved.

**D. Log an INFO-level message** when a legacy path is used, consistent with the existing migration messaging pattern.

**E. No migration for log files.** New log files are written to the canonical `<app_data_dir>/logs/` directory. Old log files at the `ShruggieTech` path (or the Linux `~/.local/share` path) are orphaned but harmless. The user can delete them manually. Do not auto-delete or auto-move log files.

#### 2.3. Testing

- Mock `LOCALAPPDATA`, `APPDATA`, and `XDG_CONFIG_HOME` environment variables to test each fallback tier.
- Confirm that a session file at the v0.1.1 Roaming path is read correctly and migrated to the new Local path on the next save.
- Confirm that a config file at the v0.1.0 flat path is discovered and used.

### 3. Spec Hardening (Priority: High)

#### 3.1. Problem

The technical specification documents session paths in §10.1 and log paths in §11.1, but there is no unified section that establishes the canonical application data directory for all tool-generated data. This structural gap allowed the inconsistency to be introduced — two separate sprint agents each chose a path independently because the spec did not define one authoritatively.

#### 3.2. Required Changes

**A. Add a new spec section: "§3.3a Application Data Directory" (or integrate into §3.3).** This section must:

- Define `get_app_data_dir()` as the single source of truth.
- Provide the platform-resolved path table for all three platforms.
- List every data artifact written to this directory (session file, config file, logs).
- State explicitly that all future application data MUST be written under this directory.
- State explicitly that no other module may resolve application data paths independently.

**B. Update §3.3 (Configuration File Locations).** Replace `%APPDATA%` references with `%LOCALAPPDATA%` for Windows. Update the path table.

**C. Update §10.1 (Session Persistence).** Replace the path table with references to the new §3.3a section. Update the legacy migration table to include the three-tier fallback.

**D. Update §11.1 (Logging Architecture — Principle 3).** Replace the log directory path table with a reference to §3.3a. Remove the per-platform inline path resolution description.

**E. Update the `> **Updated** ...` callout on each affected section** with the current date and a note about the consolidation.

#### 3.3. Spec Path Table (final, canonical)

This table should appear exactly once in the spec, in §3.3 or §3.3a:

| Platform | Application data directory | Environment variable |
|----------|---------------------------|---------------------|
| Windows | `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\` | `LOCALAPPDATA` |
| Linux | `~/.config/shruggie-tech/shruggie-indexer/` | `XDG_CONFIG_HOME` (fallback: `~/.config`) |
| macOS | `~/Library/Application Support/shruggie-tech/shruggie-indexer/` | _(hardcoded)_ |

Contents:

| Artifact | Relative path | Written by |
|----------|--------------|------------|
| GUI session state | `gui-session.json` | `SessionManager.save()` |
| User config file | `config.toml` | User (manual placement) |
| Persistent log files | `logs/YYYY-MM-DD_HHMMSS.log` | `log_file.make_file_handler()` |

### 4. Documentation Updates (Priority: Medium)

#### 4.1. Required Changes

**A. `docs/user-guide/configuration.md`** — Update the config file location table. Replace `%APPDATA%` with `%LOCALAPPDATA%`.

**B. `docs/user-guide/gui.md`** — Update the session persistence path table. Update the "Open Config Folder" description.

**C. `docs/user-guide/cli-reference.md`** — Update the `--log-file` default directory table. Replace `%LOCALAPPDATA%\ShruggieTech\` with `%LOCALAPPDATA%\shruggie-tech\`.

**D. `CHANGELOG.md` / `docs/changelog.md`** — Add entries documenting the path consolidation and the namespace fix.

### 5. GUI "Open Config Folder" Verification (Priority: Medium)

#### 5.1. Problem

The "Open Config Folder" button derives its path from `SessionManager._resolve_path().parent`. After this sprint, the button must open `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\` — which will now also contain the `logs/` subdirectory. This is the desired behavior: the user can find everything in one place.

#### 5.2. Required Changes

No code change to the button itself should be necessary — it already derives from `SessionManager`, which will be updated in Section 1. Verify that the button opens the correct new path after the refactor.

#### 5.3. Settings Page Log Path Display

The Settings page displays a read-only "Log file path" label showing the computed log directory. Verify this displays the new canonical path after the refactor.

---

## Affected Files Summary

| File | Nature of change |
|------|------------------|
| `src/shruggie_indexer/app_paths.py` | **NEW.** Canonical path resolver module. |
| `src/shruggie_indexer/log_file.py` | Replace inline path resolution with `app_paths.get_log_dir()`. Remove `ShruggieTech` string. Simplify `get_default_log_dir()`. |
| `src/shruggie_indexer/gui/app.py` | Replace `SessionManager._config_base()` with `app_paths.get_app_data_dir()`. Remove `_ECOSYSTEM_DIR` / `_TOOL_DIR` class constants. Update three-tier migration fallback. |
| `src/shruggie_indexer/config/loader.py` | Replace `_resolve_config_base()` with `app_paths.get_app_data_dir()`. Update `_find_user_config()` fallback chain. |
| `shruggie-indexer-spec.md` | Add/update §3.3 with canonical path table. Update §10.1 and §11.1 path references. Add amendment callouts. |
| `docs/user-guide/configuration.md` | Update config file path table. |
| `docs/user-guide/gui.md` | Update session persistence path table. |
| `docs/user-guide/cli-reference.md` | Update `--log-file` default directory table. |
| `CHANGELOG.md` | Add consolidation entry. |
| `docs/changelog.md` | Sync from `CHANGELOG.md`. |
| `tests/unit/test_app_paths.py` | **NEW.** Tests for the canonical path resolver. |
| `tests/unit/test_log_file.py` | Update expected paths in existing log directory tests. |
| `tests/unit/test_config.py` | Update expected paths in config resolution tests. |

---

## Acceptance Criteria

- [ ] A single module (`app_paths.py`) owns all application data path resolution. No other module resolves these paths independently.
- [ ] On Windows, all application data is written to `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\` — not to `%APPDATA%` (Roaming) and not to `ShruggieTech` (PascalCase).
- [ ] On Linux, all application data is written to `~/.config/shruggie-tech/shruggie-indexer/` — not to `~/.local/share/shruggie-indexer/`.
- [ ] On macOS, all application data is written to `~/Library/Application Support/shruggie-tech/shruggie-indexer/` — not to `ShruggieTech`.
- [ ] The namespace directory is `shruggie-tech` (kebab-case) on all platforms, with no occurrence of `ShruggieTech` (PascalCase) anywhere in the codebase.
- [ ] Session files at the v0.1.1 Roaming path (`%APPDATA%\shruggie-tech\...`) are read via fallback and migrated to the canonical Local path on next save.
- [ ] Session files at the v0.1.0 flat path (`%APPDATA%\shruggie-indexer\...`) are read via fallback and migrated on next save.
- [ ] TOML config files at legacy paths are discovered via fallback.
- [ ] Legacy files are never deleted or moved automatically.
- [ ] The "Open Config Folder" button opens the canonical directory, which now contains session, config, and logs.
- [ ] The Settings page "Log file path" display shows the canonical log directory.
- [ ] The technical specification has a single authoritative path table for all application data, referenced by §10.1 and §11.1 rather than duplicated.
- [ ] All documentation site pages reflect the corrected paths.
- [ ] All existing tests pass. New tests validate the path resolver and migration fallbacks.
- [ ] No file in the codebase contains the string `ShruggieTech` (PascalCase) as a directory name.
- [ ] `CHANGELOG.md` documents the consolidation.

---

## Spec References

| Section | Relevance |
|---------|-----------|
| §3.3 — Configuration File Locations | Primary section to update with canonical path table |
| §10.1 — GUI Framework and Architecture (Session Persistence) | Session file paths, migration fallback |
| §10.4 — Configuration Panel (Open Config Folder) | GUI button behavior |
| §11.1 — Logging Architecture (Principle 3) | Log file directory paths |
| §3.2 — Source Package Layout | New `app_paths.py` module |

---

## Risk Notes

- **Log file fix interaction.** The most recent batch (20260227-003) included a fix to the GUI's persistent file logging handler that resolved a bug where log files were created as 0-byte orphans. The fix involved deferring `_setup_file_logging()` until after `_restore_session()`. This sprint changes _where_ logs are written, not _when_ or _how_ the file handler is created. The handler creation flow (`_setup_file_logging()` → `make_file_handler()` → `get_default_log_dir()`) is preserved — only the final path returned by `get_default_log_dir()` changes. The fix from Batch 3 should not be affected, but this interaction must be verified.

- **PyInstaller builds.** Environment variable resolution (`LOCALAPPDATA`, `APPDATA`) works identically in frozen (PyInstaller) executables and standard Python. No special handling is needed.

- **Orphaned legacy directories.** After migration, users will have up to three orphaned directories on Windows: `%APPDATA%\shruggie-indexer\`, `%APPDATA%\shruggie-tech\shruggie-indexer\`, and `%LOCALAPPDATA%\ShruggieTech\shruggie-indexer\`. These are harmless but untidy. A future release could surface a one-time cleanup prompt. This is out of scope for this sprint.

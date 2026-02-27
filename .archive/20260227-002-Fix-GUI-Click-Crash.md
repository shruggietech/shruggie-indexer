# Fix: GUI PyInstaller Binary Crashes with `ModuleNotFoundError: No module named 'click'`

## Problem

The compiled GUI binary (`shruggie-indexer-gui.exe`) crashes on launch with:

```
ModuleNotFoundError: No module named 'click'
```

The traceback chain is:

```
app.py _update_log_path_display()
  → from shruggie_indexer.cli.log_file import get_default_log_dir
    → Python loads shruggie_indexer/cli/__init__.py
      → from shruggie_indexer.cli.main import ExitCode, main
        → import click  ← BOOM (click is in GUI spec's excludes list)
```

## Root Cause

`log_file.py` is shared logging infrastructure used by both the GUI and the CLI. It has **zero dependency** on `click` or any CLI-specific code. Placing it under `cli/` was a packaging error that creates a transitive dependency on `click` via `cli/__init__.py`'s eager re-exports.

This violates the spec's architectural Rule 5: `gui/` should only import from `core/`, `models/`, `config/`, and top-level package modules — never from `cli/`.

## Fix (3 files changed, 0 logic changes)

### Step 1 — Move the file

Move `src/shruggie_indexer/cli/log_file.py` → `src/shruggie_indexer/log_file.py` (package root level, alongside `_version.py` and `exceptions.py`).

**No changes to the file's contents are required.** The module has no internal imports from `cli/`.

### Step 2 — Update the GUI import

In `src/shruggie_indexer/gui/app.py`, find the lazy import inside `_update_log_path_display()`:

```python
from shruggie_indexer.cli.log_file import get_default_log_dir
```

Replace with:

```python
from shruggie_indexer.log_file import get_default_log_dir
```

There may be other imports of `log_file` elsewhere in `app.py` (e.g., `_setup_file_logging` or the GUI startup code that creates the persistent debug log handler). Search the entire file for `shruggie_indexer.cli.log_file` and update **all** occurrences to `shruggie_indexer.log_file`.

### Step 3 — Update the CLI import

In `src/shruggie_indexer/cli/main.py`, search for any import of `log_file` from the sibling module:

```python
from shruggie_indexer.cli.log_file import ...
```

Replace with:

```python
from shruggie_indexer.log_file import ...
```

If `main.py` uses a relative import like `from .log_file import ...`, replace it with the absolute form `from shruggie_indexer.log_file import ...`.

### Step 4 — Verify no other references remain

Run a project-wide search for `cli.log_file` and `cli/log_file` to catch any remaining references (tests, other modules, etc.). Update all of them to point to `shruggie_indexer.log_file`.

### What NOT to do

- Do **not** remove `click` from the GUI spec's `excludes` list. The exclusion is correct — the GUI does not use `click` and should not bundle it.
- Do **not** modify `cli/__init__.py` to use lazy imports. The eager re-export of `ExitCode` and `main` is fine for the CLI package's own consumers; the problem is that the GUI was reaching into `cli/` for something that doesn't belong there.
- Do **not** change any logic in `log_file.py` itself. The move is purely organizational.

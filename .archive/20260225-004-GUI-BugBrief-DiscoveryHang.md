# Bug Brief: GUI Discovery Hang, Broken Cancel, Missing Logging

**Date:** 2026-02-25
**Severity:** Critical — application is non-functional for this operation
**Attempt:** 3 (two prior fix attempts failed)
**Repository:** `github.com/shruggietech/shruggie-indexer`
**Primary file under investigation:** `src/shruggie_indexer/gui/app.py`

---

## Executive Summary

Three interconnected issues prevent the GUI from completing a Meta Merge Delete operation on a recursive directory target. The application hangs indefinitely during the "Discovering items..." phase, the Cancel button does not terminate the hung operation, and no diagnostic logging is produced anywhere (neither the GUI log panel nor a log file), leaving the developer with zero visibility into what the code is actually doing. All three issues must be resolved in this sprint.

---

## Issue 1: GUI Hangs During Discovery Phase

### Observed Behavior

The user starts a **Meta Merge Delete** operation against a directory target (`A:\Code\shruggie-indexer-testing\data`, recursive). The progress bar enters indeterminate mode and the status label reads "Discovering items..." The timer reaches 0:22+ and continues climbing. The GUI becomes unresponsive — the main thread event loop is blocked or starved. The operation never transitions from the discovery phase to the processing phase.

### What the Test Case Contains

The target directory is small and should index in under 2 seconds. Here is the exact structure:

```
data/                                   (root — 748 MB total, but see note on .7z)
├── 123.nfo                             (2.6 MB binary)
├── 123.nfo_meta.json                   (sidecar, _meta suffix)
├── 123.nfo_meta2.json                  (sidecar, _meta2 suffix)
├── 123.txt                             (13 bytes)
├── 123.txt_meta.json                   (sidecar)
├── 123.txt_meta2.json                  (sidecar)
├── empty/
│   └── pdf/
│       └── pdf/                        (empty directory, depth 3)
├── images/
│   ├── slippers.gif                    (454 KB)
│   ├── slippers.png                    (454 KB)
│   ├── slippers.webm                   (74 KB)
│   ├── slippers_01.gif                 (454 KB, duplicate content)
│   ├── slippers_01.png                 (454 KB, duplicate content)
│   ├── slippers_01.webm                (74 KB, duplicate content)
│   ├── slippers_02.gif                 (454 KB, duplicate content)
│   ├── slippers_02.png                 (454 KB, duplicate content)
│   └── slippers_02.webm                (74 KB, duplicate content)
└── not-empty/
    ├── FeedsExport.7z                  (728 MB — single large binary)
    ├── FeedsExport.7z_info.json        (sidecar, _info suffix)
    ├── FeedsExport.7z_meta.json        (sidecar)
    ├── FeedsExport.7z_meta2.json       (sidecar)
    ├── FeedsExport_info.json           (47 KB)
    ├── FeedsExport_meta.json           (sidecar)
    ├── FeedsExport_meta2.json          (sidecar)
    ├── pdf/
    │   └── pdf/
    │       ├── [a] {b} (c)_1.pdf       (296 KB, special chars in filename)
    │       ├── [a] {b} (c)_1.pdf_meta.json
    │       ├── [a] {b} (c)_1.pdf_meta2.json
    │       ├── [a] {b} (c)_2.pdf       (1.6 MB)
    │       ├── [a] {b} (c)_2.pdf_meta.json
    │       └── [a] {b} (c)_2.pdf_meta2.json
    ├── unicode-file-names/
    │   ├── 💀💀💀.png                  (23 KB, emoji filename)
    │   └── 💀💀💀.webp                 (17 KB, emoji filename)
    └── yt-dlp/
        ├── How_the_DNS_works-[2ZUxoi7YNgs].mp4             (11 MB)
        ├── How_the_DNS_works-[2ZUxoi7YNgs]_screen.jpg
        ├── How_the_DNS_works-[2ZUxoi7YNgs].description
        ├── How_the_DNS_works-[2ZUxoi7YNgs].en-en.vtt
        ├── How_the_DNS_works-[2ZUxoi7YNgs].en-orig.vtt
        ├── How_the_DNS_works-[2ZUxoi7YNgs].en.vtt
        ├── How_the_DNS_works-[2ZUxoi7YNgs].info.json       (805 KB)
        └── How_the_DNS_works-[2ZUxoi7YNgs].url
```

**Summary:** 38 files, 10 directories, max depth 4. 14 distinct file extensions. Total size ~748 MB but 728 MB of that is a single `.7z` archive. The CLI tool (`data_tree.json` runtime stats) processed the full tree traversal in **0.759 seconds**.

**Edge cases present in this test data:**

- Filenames with brackets, braces, and parentheses: `[a] {b} (c)_1.pdf`
- Filenames with emoji/Unicode: `💀💀💀.png`
- Filenames with square brackets (yt-dlp convention): `How_the_DNS_works-[2ZUxoi7YNgs].mp4`
- Empty nested directories: `empty/pdf/pdf/` (zero files, zero bytes)
- Existing `_meta.json` and `_meta2.json` sidecar files already present alongside parent files
- A very large single binary file (728 MB `.7z`)
- Multiple sidecar suffix patterns: `_meta.json`, `_meta2.json`, `_info.json`

### GUI Settings at Time of Hang (from screenshot)

| Setting | Value |
|---------|-------|
| Operation | Meta Merge Delete |
| Target path | `A:/Code/shruggie-indexer-testing/data` |
| Target type | Directory (radio button) |
| Recursive | Checked |
| ID Algorithm | md5 |
| Compute SHA-512 | Checked (forced on by Settings) |
| Extract EXIF metadata | Checked |
| Rename files | Checked |
| Output Mode | Multi-file |
| Output file | `A:\Code\shruggie-indexer-testing\data_directorymeta2.json` |

### Where to Look

The hang is in the interaction between the GUI's background thread and the core engine. Trace the exact code path:

1. **START button click handler** → creates `threading.Event` (cancel_event), creates `threading.Thread`, starts thread
2. **Background thread entry point** → constructs `IndexerConfig` from GUI widget values, calls `index_path()`
3. **`index_path()`** → determines target type (directory), calls `build_directory_entry()`
4. **`build_directory_entry()`** → performs filesystem traversal (the "discovery" phase), then processes each item

The hang is during step 3 or 4. Possible root causes to investigate:

- **Blocking the main thread:** Is `index_path()` or any setup code accidentally running on the main (UI) thread instead of the background thread? Check if `thread.start()` is actually called, or if someone called `thread.run()` (which executes synchronously on the calling thread).
- **Discovery loop stuck:** Is the traversal code entering an infinite loop? The `empty/pdf/pdf/` nested empty directory structure, or the sidecar file matching logic during discovery, could cause a cycle if sidecar files are being treated as parent files that themselves need sidecar resolution.
- **Sidecar resolution during discovery:** For Meta Merge Delete, the engine must discover sidecar files alongside their parent files. If the sidecar matching algorithm is re-scanning the directory for each file, or if it is treating `_meta.json` files as indexable items that themselves trigger sidecar discovery, this creates O(n²) or recursive behavior.
- **ExifTool subprocess hang:** The `FeedsExport.7z` file is 728 MB. If ExifTool is being invoked during the discovery phase (it should only run during processing), it could be hanging on reading this large binary file. ExifTool on a 728 MB `.7z` may take a very long time or hang altogether.
- **Queue deadlock:** The 50ms `after()` polling loop drains a `queue.Queue`. If the background thread is producing events faster than the main thread can consume them, or if a blocking `queue.put()` is waiting for a full queue, this could cause a deadlock.
- **`ProgressEvent` callback exception:** If the progress callback raises an unhandled exception on the background thread, the thread dies silently and the GUI stays in the "discovering" state forever.

### Fix Requirements

- The GUI must not hang on this test case. A 38-file directory should complete discovery in well under 1 second.
- The progress bar must transition from indeterminate (discovery) to determinate (processing) once the item count is known.
- The 728 MB `.7z` file must not cause disproportionate delays during discovery (hashing happens during processing, not discovery).
- Verify that ExifTool is NOT invoked during the discovery phase.
- Verify that `threading.Thread.start()` is called, not `threading.Thread.run()`.
- Add exception handling around the entire background thread entry point so that unhandled exceptions are caught, logged, and reported to the GUI (not silently swallowed).

---

## Issue 2: Cancel Button Does Not Kill the Operation

### Observed Behavior

While the GUI is hung in the "Discovering items..." state, clicking the Cancel button (which should replace the START button during execution) has no effect. The operation continues running (or hanging). The GUI does not return to the idle state.

### Architecture (from spec §10.5)

The cancellation mechanism is designed as follows:

1. GUI creates a `threading.Event` called `cancel_event` before spawning the background thread.
2. `cancel_event` is passed to `index_path()` (via `IndexerConfig` or as a direct parameter).
3. The engine checks `cancel_event.is_set()` at item boundaries in `build_directory_entry()`.
4. When set, the engine raises `IndexerCancellationError`.
5. The background thread catches `IndexerCancellationError` and signals the main thread with a "cancelled" status.
6. The main thread transitions back to idle.

### Where to Look

- **Is the Cancel button wired up?** Check the button's `command` callback. It must call `cancel_event.set()`. Verify the button widget actually exists during execution (it may not have been swapped in from START → Cancel).
- **Is `cancel_event` passed to the engine?** Trace from the background thread's entry point through to `index_path()` and into `build_directory_entry()`. If the event object is not passed through, the engine has nothing to check.
- **Is the engine checking the event during discovery?** The spec says the check happens "at the start of each item's processing loop." But if the engine is stuck in a filesystem traversal call (e.g., `os.scandir()` or `Path.iterdir()`) or a subprocess call (ExifTool), it will never reach the check point. **The cancel_event must also be checked during the discovery/traversal phase**, not only during the per-item processing loop.
- **Is the background thread dead?** If the thread crashed with an unhandled exception, `cancel_event.set()` has no effect because there is no thread running to observe it. The main thread's polling loop will never receive the "cancelled" status message.

### Fix Requirements

- Clicking Cancel must set `cancel_event` and the operation must stop within 1–2 seconds.
- Add `cancel_event.is_set()` checks inside the discovery/traversal loop, not just the per-item processing loop.
- If the background thread has died (thread.is_alive() returns False), the Cancel button handler must detect this and force-transition the GUI back to idle immediately, displaying an error message.
- Wrap the entire background thread entry point in a try/except that catches ALL exceptions, enqueues an error status to the main thread's queue, and ensures the thread exits cleanly.

---

## Issue 3: No Logging Output Anywhere

### Observed Behavior

The GUI's Log tab (visible in the screenshot at the bottom of the window) shows no output at all. There is no log file being written to the appdata directory. The developer has zero diagnostic information about what the application is doing internally.

### Architecture (from spec §11.1, §10.4, §10.5)

The spec defines:

- The GUI's `__init__` method should configure a `logging.Handler` subclass that enqueues log records into the same `queue.Queue` used by the progress display.
- The Settings tab has a Verbosity radio group: Normal (WARNING), Verbose (INFO), Debug (DEBUG). Default is Normal.
- The CLI supports `--log-file` for persistent file logging to the platform appdata directory.
- Log files go to: `%LOCALAPPDATA%\ShruggieTech\shruggie-indexer\logs\` (Windows).

### What Needs to Change

The current defaults are wrong for a v0.1.0 application in active development. Two changes are required:

**Change 1: Force DEBUG-level logging to a file by default in the GUI.**

Do NOT make file logging opt-in for the GUI. The GUI must always write a debug-level log file to the appdata log directory on every invocation, regardless of the Verbosity setting on the Settings tab. The Verbosity setting controls the GUI log panel's verbosity (what the user sees in the app), but the file log always runs at DEBUG level. This is the opposite of the CLI's design (where file logging is opt-in), and that is intentional — the GUI user cannot see stderr and needs a persistent diagnostic trail.

Implementation:

- On application startup (`__init__` or equivalent), create a `logging.FileHandler` pointing to `{appdata_logs_dir}/YYYY-MM-DD_HHMMSS.log`.
- Set the file handler's level to `DEBUG`.
- Attach it to the root logger (or the `shruggie_indexer` logger).
- This handler runs in parallel with the GUI queue handler.
- Use `platformdirs` to resolve the log directory. Create the directory if it does not exist.
- The Settings tab Verbosity control only affects the GUI panel handler's level, not the file handler.

**Change 2: Log comprehensively — every user action and every logical branch.**

The following events must produce log messages (at appropriate levels):

| Event | Level | Example message |
|-------|-------|-----------------|
| Application startup | INFO | `"Shruggie Indexer GUI v0.1.0 started"` |
| Application shutdown | INFO | `"Application exiting"` |
| Sidebar tab clicked | DEBUG | `"Tab selected: Operations"` |
| Operation type changed | DEBUG | `"Operation type changed to: Meta Merge Delete"` |
| Target path changed | DEBUG | `"Target path set to: A:\Code\shruggie-indexer-testing\data"` |
| Target type changed | DEBUG | `"Target type changed to: Directory"` |
| Recursive toggled | DEBUG | `"Recursive: enabled"` |
| Any checkbox toggled | DEBUG | `"Option changed: Rename files = True"` |
| Any dropdown changed | DEBUG | `"Option changed: ID Algorithm = md5"` |
| Output mode changed | DEBUG | `"Output mode changed to: Multi-file"` |
| START button clicked | INFO | `"Operation started: Meta Merge Delete on A:\...\data (directory, recursive)"` |
| Config constructed | DEBUG | `"IndexerConfig: {serialized config object}"` |
| Background thread created | DEBUG | `"Background thread created: {thread.name}"` |
| Background thread started | DEBUG | `"Background thread started"` |
| Cancel button clicked | INFO | `"Cancel requested by user"` |
| cancel_event set | DEBUG | `"cancel_event.set() called"` |
| Discovery phase begins | INFO | `"Discovery phase started for: {path}"` |
| Discovery phase ends | INFO | `"Discovery complete: {n} items found in {elapsed:.3f}s"` |
| Processing phase begins | INFO | `"Processing phase started: {n} items"` |
| Per-item processing | DEBUG | `"Processing [{i}/{n}]: {path}"` |
| Per-item complete | DEBUG | `"Completed [{i}/{n}]: {path} in {elapsed:.3f}s"` |
| ExifTool invoked | DEBUG | `"ExifTool invoked for: {path}"` |
| Sidecar file discovered | DEBUG | `"Sidecar discovered: {sidecar_path} → parent: {parent_path}"` |
| Sidecar file deleted | INFO | `"Sidecar deleted: {path}"` |
| Output written | INFO | `"Output written to: {path}"` |
| Operation complete | INFO | `"Operation completed in {elapsed:.1f}s"` |
| Operation cancelled | INFO | `"Operation cancelled by user"` |
| Operation failed | ERROR | `"Operation failed: {exception}"` |
| Background thread exception | ERROR | `"Unhandled exception in background thread: {traceback}"` |
| Background thread exited | DEBUG | `"Background thread exited"` |
| Settings changed | DEBUG | `"Setting changed: {key} = {value}"` |
| Session loaded | DEBUG | `"Session restored from: {path}"` |
| Session saved | DEBUG | `"Session saved to: {path}"` |
| Browse button clicked | DEBUG | `"Browse dialog opened for: file\|folder"` |
| Browse result | DEBUG | `"Browse result: {path or 'cancelled'}"` |
| Validation error | WARNING | `"Validation: {message}"` |
| Widget state change | DEBUG | `"Widget state: START button disabled (validation failed)"` |

This is not an exhaustive list. The principle is: **log every entry point into a logical operation and every decision branch.** When something goes wrong, the log file must contain enough information to reconstruct the exact sequence of events that led to the failure without reproducing the bug interactively.

---

## Execution Order

These three issues are interdependent. Fix them in this order:

1. **Logging (Issue 3) first.** Without logging, you cannot verify whether the other two fixes work correctly. Implement the file handler and add log statements throughout `app.py` and the core engine entry points before touching anything else.
2. **Discovery hang (Issue 1) second.** With logging in place, run the test case and read the log file to identify the exact point of failure. Fix the root cause.
3. **Cancel (Issue 2) third.** With the hang fixed, verify that Cancel works during normal (non-hung) operations. Also add the safety net: if the background thread is dead, Cancel must force-reset the GUI to idle.

---

## Acceptance Criteria

All three criteria must pass against the test directory described above:

- [ ] Running Meta Merge Delete on the test directory completes successfully (discovery + processing + output) without hanging.
- [ ] Clicking Cancel during an active operation stops the operation and returns the GUI to idle within 2 seconds.
- [ ] A DEBUG-level log file is written to the appdata logs directory on every GUI launch, containing timestamped entries for every user action and every phase of the indexing pipeline. The log file must be readable and useful for diagnosing this class of issue without the developer needing to reproduce the bug.

---

## Reference Files

| File | Purpose |
|------|---------|
| `src/shruggie_indexer/gui/app.py` | GUI application — primary file to modify |
| `src/shruggie_indexer/core/entry.py` | `build_file_entry()`, `build_directory_entry()` — discovery and processing |
| `src/shruggie_indexer/core/api.py` or equivalent | `index_path()` entry point |
| `src/shruggie_indexer/config/types.py` | `IndexerConfig` dataclass |
| `shruggie-indexer-spec.md` §10.5 | GUI execution and progress spec |
| `shruggie-indexer-spec.md` §11.1 | Logging architecture spec |
| `shruggie-indexer-spec.md` §8.4 | Meta Merge Delete operation spec |

## 10. GUI Application

This section defines the standalone desktop GUI for `shruggie-indexer` — a visual frontend to the same library code consumed by the CLI (§8) and the public API (§9). The GUI is modeled after the `shruggie-feedtools` GUI (§1.5, External References) and shares its CustomTkinter foundation, dark theme, font stack, and two-panel layout pattern. Where this specification does not explicitly define a visual convention — such as padding values, border radii, or widget spacing — the `shruggie-feedtools` GUI serves as the normative reference.

The GUI serves a fundamentally different user need than the CLI. The CLI is a power-user and automation tool — its flag-based interface composes naturally in scripts but requires the user to internalize the full option space, understand the implication chain (`--meta-merge-delete` → `--meta-merge` → `--meta`), and manage output routing mentally. The GUI eliminates this cognitive overhead by organizing the indexer's capabilities into dedicated operation tabs, each exposing only the options relevant to that operation with safe defaults pre-applied. The GUI is the recommended entry point for users who are unfamiliar with the tool's option space or who want visual confirmation of their configuration before executing.

**Module location:** `gui/app.py` (§3.2). The GUI is a single-module implementation for the MVP. If the GUI grows in complexity (custom widgets, asset files, reusable components), additional modules and an `assets/` subdirectory can be added under `gui/` without restructuring (§3.2).

**Dependency isolation:** The `customtkinter` dependency is declared as an optional extra (`pip install shruggie-indexer[gui]`) and is imported only within the `gui/` subpackage. No module outside `gui/` imports from it. The core library, CLI, and public API function without any GUI dependency installed (design goal G5, §2.3). If the user launches the GUI entry point without `customtkinter` installed, the application MUST fail with a clear error message directing the user to install the dependency (`pip install shruggie-indexer[gui]`).

> **Deviation note on outline structure:** The outline (§10.1–10.7) was drafted before the full GUI requirements were finalized. This section follows the outline's subsection headings but expands their content significantly to accommodate the tab-per-operation architecture, session persistence, job control with cancellation, and the progress display system. Sub-subsections are added where the original heading's scope is insufficient.

### 10.1. GUI Framework and Architecture

#### Framework selection

The GUI uses [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) as its widget toolkit, consistent with `shruggie-feedtools`. CustomTkinter wraps Python's standard `tkinter` library with modern-styled widgets, dark/light theme support, and DPI scaling. It requires no additional runtime beyond Python itself and `tkinter` — both of which are available in standard CPython distributions and in PyInstaller bundles.

The choice of CustomTkinter over alternatives (PyQt, wxPython, Kivy) is inherited from the ShruggieTech project family and driven by three factors: zero licensing restrictions (MIT-licensed, compatible with Apache 2.0), no binary compilation step (pure Python distribution), and minimal bundle size impact in PyInstaller builds. This decision is not reconsidered here — the `shruggie-feedtools` GUI has validated the framework for this class of desktop tool.

#### Architectural role

The GUI is a thin presentation layer over the library API — identical in architectural role to the CLI (design goal G3, §2.3). The boundary is explicit:

- The GUI constructs `IndexerConfig` objects via `load_config()` (§9.3), translating widget state into configuration overrides.
- The GUI calls `index_path()` (§9.2) to perform indexing, receiving an `IndexEntry` in return.
- The GUI calls `serialize_entry()` (§9.2) to convert the entry to JSON for display.
- The GUI handles output routing (writing to files) using the same logic as the CLI, but through user-driven save actions rather than automatic flag-based routing.

No indexing logic lives in the GUI module. The GUI does not import from `core/` directly — it interacts exclusively through the public API surface defined in §9.1. This constraint ensures that the GUI cannot introduce behavioral divergence from the CLI or the library.

#### Threading model

All indexing operations run in a background thread to keep the UI responsive. The GUI uses Python's `threading.Thread` for background execution, not `asyncio` or multiprocessing. This matches the `shruggie-feedtools` threading model and avoids the complexity of cross-thread tkinter access patterns that arise with process-based parallelism.

The threading contract:

1. The main thread owns all widget state. Only the main thread creates, reads, or modifies tkinter widgets.
2. Background threads perform indexing via `index_path()` and communicate results back to the main thread through `tkinter`'s `after()` method (polling a thread-safe queue) or by setting a `threading.Event` that the main thread checks on a timer.
3. Background threads MUST NOT touch any widget directly. Widget updates — progress messages, output population, button re-enabling — are always dispatched to the main thread via `widget.after(0, callback)` or an equivalent event-loop-safe mechanism.
4. Only one background indexing thread may be active at any time (see §10.5, job exclusivity). The GUI enforces this by disabling all operation tabs and action buttons when a job is in flight.

> **Improvement over shruggie-feedtools:** The `shruggie-feedtools` GUI uses a simple fire-and-forget `threading.Thread` with a boolean "running" flag. The `shruggie-indexer` GUI requires a more sophisticated model because indexing operations can be long-running (minutes for large directory trees), cancellable, and produce incremental progress data. The threading model described here adds a cancellation mechanism and a structured progress callback channel that `shruggie-feedtools` did not need.

#### Session persistence

The GUI persists user session settings — window geometry, last-used operation tab, per-tab input values, and settings panel preferences — to a JSON file in the platform-appropriate application data directory. This ensures the GUI reopens in the state the user left it.

**Session file location:**

| Platform | Path |
|----------|------|
| Windows | `%APPDATA%\shruggie-indexer\gui-session.json` |
| Linux | `~/.config/shruggie-indexer/gui-session.json` |
| macOS | `~/Library/Application Support/shruggie-indexer/gui-session.json` |

This uses the same platform directory resolution as the indexer's TOML configuration file (§3.3), under the same `shruggie-indexer` application directory. The session file is a separate file from the TOML configuration — it stores GUI-specific presentation state, not indexing configuration. The TOML file governs indexing behavior; the session file governs window preferences.

**Session file format:** Plain JSON with a `session_version` discriminator for forward compatibility. The file is written on application exit (window close) and on each successful operation completion. It is read once at startup. If the file does not exist, is unreadable, or has an unrecognized `session_version`, the GUI starts with default values and does not produce an error — the file is purely a convenience optimization.

```json
{
  "session_version": "1",
  "window": {
    "geometry": "1100x750+200+100",
    "active_tab": "index"
  },
  "tabs": {
    "index": {
      "target_path": "/path/to/last/target",
      "target_type": "auto",
      "recursive": true,
      "extract_exif": false,
      "id_algorithm": "md5"
    },
    "meta_merge": {
      "target_path": "",
      "recursive": true,
      "id_algorithm": "md5"
    },
    "meta_merge_delete": {
      "target_path": "",
      "recursive": true,
      "id_algorithm": "md5",
      "output_file": ""
    },
    "rename": {
      "target_path": "",
      "recursive": true,
      "id_algorithm": "md5",
      "dry_run": true
    }
  },
  "settings": {
    "default_id_algorithm": "md5",
    "compute_sha512": false,
    "json_indent": 2,
    "verbosity": 0
  }
}
```

**Session state isolation:** Each operation tab maintains its own input state in the session file. Switching between tabs does NOT clear or reset input fields — the user can configure an Index operation, switch to the Rename tab, configure that, switch back, and find their Index inputs exactly as they left them. This isolation extends to the runtime — tab state is stored in per-tab state dictionaries in memory, and tab switches simply show/hide pre-populated frames without reconstruction.

> **Deviation from shruggie-feedtools:** The `shruggie-feedtools` GUI does not persist session state — it starts fresh every launch. The indexer's GUI adds persistence because the tool's input space is significantly more complex (target paths, multiple flag combinations, per-operation configurations) and users benefit from resuming where they left off, especially when iterating on large directory trees.

#### Module structure

For the MVP, the GUI is a single file: `gui/app.py`. This file contains the `ShruggiIndexerApp` class (the top-level application window), all tab frame classes, the progress display logic, and the session persistence code. The `gui/__init__.py` file exports a single `main()` function that instantiates and runs the application.

```python
# gui/__init__.py
def main():
    """Launch the shruggie-indexer GUI application."""
    try:
        from shruggie_indexer.gui.app import ShruggiIndexerApp
    except ImportError as e:
        print(
            "The GUI requires customtkinter. "
            "Install it with: pip install shruggie-indexer[gui]",
            file=sys.stderr,
        )
        sys.exit(1)
    app = ShruggiIndexerApp()
    app.mainloop()
```

If the GUI outgrows a single file during implementation, the recommended decomposition is: `app.py` (main window and tab container), `tabs/` subdirectory with one module per operation tab, `widgets/` for reusable custom widgets (progress bar, JSON viewer), and `session.py` for persistence logic. This decomposition is optional for the MVP — the single-file approach is acceptable if the file remains under ~1500 lines.

---

### 10.2. Window Layout

#### Overall structure

The window uses a two-panel layout: a narrow left sidebar for operation tab selection and a main working area on the right. This is the same structural pattern used by `shruggie-feedtools`, adapted for the indexer's multi-operation architecture.

```
┌──────────────────────────────────────────────────────────────────┐
│  Shruggie Indexer                                       [—][□][×]│
├─────────────┬────────────────────────────────────────────────────┤
│             │  ┌────────────────────────────────────────────────┐│
│  ┌────────┐ │  │  Target: [________________________] [Browse]  ││
│  │ Index  │ │  │  Type: (•) Auto  ( ) File  ( ) Directory      ││
│  └────────┘ │  │  [✓] Recursive                                ││
│             │  ├────────────────────────────────────────────────┤│
│  ┌────────┐ │  │  Options:                                     ││
│  │ Meta   │ │  │  ID Algorithm: [md5 ▾]                        ││
│  │ Merge  │ │  │  [ ] Extract EXIF metadata                    ││
│  └────────┘ │  │  [ ] Compute SHA-512                          ││
│             │  │                                                ││
│  ┌────────┐ │  │  Output:                                      ││
│  │ Meta   │ │  │  (•) View only  ( ) Save to file  ( ) Both    ││
│  │ Merge  │ │  │                                               ││
│  │ Delete │ │  │                    ┌──────────────────────┐   ││
│  └────────┘ │  │                    │    ▶ Run Index       │   ││
│             │  │                    └──────────────────────┘   ││
│  ┌────────┐ │  ├────────────────────────────────────────────────┤│
│  │Rename  │ │  │  Output                          [Copy] [Save]││
│  └────────┘ │  │  ┌────────────────────────────────────────────┐││
│             │  │  │{                                           │││
│  ─────────  │  │  │  "schema_version": "2",                   │││
│             │  │  │  "type": "directory",                      │││
│  ┌────────┐ │  │  │  "id": "x3B4F479E9F880E438882...",        │││
│  │Settings│ │  │  │  ...                                      │││
│  └────────┘ │  │  └────────────────────────────────────────────┘││
│             │  └────────────────────────────────────────────────┘│
└─────────────┴────────────────────────────────────────────────────┘
```

#### Window properties

| Property | Value | Notes |
|----------|-------|-------|
| Window title | `"Shruggie Indexer"` | No version in the title bar — keeps it clean. Version is available in the Settings panel. |
| Minimum size | `1000×700` | Slightly larger than `shruggie-feedtools` (900×600) to accommodate the additional input complexity of the operation tabs. |
| Default size | `1100×750` | Restored from session file if available. |
| Resizable | Yes | The output panel expands to fill available vertical space. The sidebar width is fixed. |
| Appearance mode | Dark | `customtkinter.set_appearance_mode("dark")`. Matches `shruggie-feedtools`. |
| Color theme | Default CustomTkinter dark | No custom theme for the MVP. |

#### Sidebar

The left sidebar is a fixed-width panel (140px) containing vertically stacked navigation buttons for each operation tab, a visual separator, and a Settings button at the bottom. The sidebar background uses the CustomTkinter frame default for the dark theme.

Each sidebar button is a `CTkButton` styled as a navigation element — the active tab's button is visually distinguished (highlighted background, bold text) from inactive tabs. Clicking a sidebar button switches the visible frame in the working area without destroying or recreating the frame — the frame is hidden/shown via `pack_forget()` / `pack()` (or equivalent grid management), preserving all widget state.

**Sidebar navigation order (top to bottom):**

| Button label | Tab identifier | Description |
|-------------|---------------|-------------|
| Index | `index` | Basic indexing with optional EXIF extraction. |
| Meta Merge | `meta_merge` | Index with sidecar metadata merging. |
| Meta Merge Delete | `meta_merge_delete` | Index with sidecar merge and deletion. |
| Rename | `rename` | Index with file renaming to storage names. |
| _(separator)_ | — | A horizontal rule or spacing element visually separating the operation tabs from the utility navigation. |
| Settings | `settings` | Application preferences and persistent configuration. |

#### Working area

The working area occupies the remaining space to the right of the sidebar. It contains a frame container that holds one frame per tab. Only the active tab's frame is visible at any time. Each tab frame is instantiated once at application startup and persists for the lifetime of the application — tab switches show and hide pre-built frames, they do not reconstruct them.

Every operation tab (Index, Meta Merge, Meta Merge Delete, Rename) shares a common vertical layout structure:

1. **Input section** (top) — Target path, operation-specific options, and output mode selection.
2. **Action button** (middle) — A single prominently-styled button to execute the operation.
3. **Output section** (bottom, expandable) — The JSON viewer and progress display area, shared via a common output panel component.

The Settings tab has its own layout (§10.4) and does not include an action button or output section.

#### Tab frame architecture

Each operation tab is implemented as a class inheriting from `customtkinter.CTkFrame`. The tab classes share no state with each other — each tab owns its own input widgets, its own state dictionary, and its own reference to the shared output panel. The shared output panel is a single widget instance that is reparented or referenced by whichever tab is currently active.

> **Architectural decision: shared vs. per-tab output panels.** A per-tab output panel would allow users to run an Index operation, view the output, switch to the Rename tab, run that, and switch back to see the Index output still present. However, this introduces memory pressure for large outputs (index trees can produce megabytes of JSON), complicates the "one job at a time" invariant (§10.5), and adds visual confusion about which output corresponds to which operation. The shared output panel is the simpler, more predictable design — it always shows the result of the most recent operation, regardless of which tab initiated it. The panel is cleared at the start of each new operation, matching `shruggie-feedtools` behavior.

---

### 10.3. Target Selection and Input

Every operation tab requires a target path — the file or directory to index. Rather than duplicating the target selection widgets across four tabs, each tab instantiates its own target selection widget group from a shared factory or base class. The widgets are visually identical across tabs but maintain independent state — the path entered on the Index tab is separate from the path entered on the Rename tab, and switching tabs does not transfer or synchronize paths.

#### Target path widget group

Each tab's input section begins with the same target selection layout:

```
  Target: [__________________________________] [Browse]
  Type:   (•) Auto  ( ) File  ( ) Directory
  [✓] Recursive
```

**Target entry field.** A `CTkEntry` widget for the filesystem path. The user can type a path directly or use the Browse button to open a directory/file picker. The field supports drag-and-drop of files and directories from the system file manager where the platform supports it (Windows Explorer, macOS Finder, Linux file managers). Drag-and-drop is a SHOULD requirement — if the CustomTkinter/tkinter implementation does not support native DnD on a given platform, the Browse button is the primary input method.

**Browse button.** Opens a platform-native file/directory picker dialog. The dialog type (file picker vs. directory picker) is determined by the Type radio selection: when "File" is selected, the Browse button opens a file picker; when "Directory" is selected, it opens a directory picker; when "Auto" is selected, it opens a directory picker (the more common target type) with a secondary "Select File" option if the underlying dialog supports it, or defaults to directory picker. After selection, the path is populated into the Target entry field.

**Type radio buttons.** Three options: Auto (default), File, Directory. These map directly to the CLI's target type disambiguation (§8.2): Auto infers the type from the filesystem, File forces `--file`, Directory forces `--directory`. The Auto option is pre-selected on all tabs.

**Recursive checkbox.** A `CTkCheckBox` for enabling/disabling recursive traversal. Default: checked (matching `IndexerConfig.recursive` default, §7.2). This checkbox is only meaningful when the target is a directory — when "File" is selected in the Type radio group, the Recursive checkbox is visually dimmed (disabled but visible) to indicate it has no effect. It re-enables when the type selection changes back to Auto or Directory.

#### Per-tab input forms

Below the shared target selection group, each operation tab presents its own set of options relevant to that operation. These forms are designed to expose only the flags that are meaningful for the selected operation, with safe defaults pre-applied. The implication chain (§7.1) is handled transparently — the GUI does not show the implied flags as separate controls because they are always active for that tab's operation.

##### Index tab

The Index tab provides the basic indexing operation with optional EXIF extraction. It is the simplest tab and the default active tab on first launch.

| Control | Type | Default | Maps to |
|---------|------|---------|---------|
| ID Algorithm | `CTkComboBox` (`md5`, `sha256`) | `md5` | `IndexerConfig.id_algorithm` |
| Extract EXIF metadata | `CTkCheckBox` | Unchecked | `IndexerConfig.extract_exif` |
| Compute SHA-512 | `CTkCheckBox` | Unchecked | `IndexerConfig.compute_sha512` |
| Output mode | `CTkRadioButton` group: View only / Save to file / Both | View only | Controls `output_stdout` / `output_file` routing |

When "Save to file" or "Both" is selected, an additional file path field and Browse button appear (slide-down reveal or visibility toggle) for the output file destination.

The Index tab does NOT expose `--meta-merge`, `--meta-merge-delete`, `--rename`, or `--inplace` controls. These belong to their respective dedicated tabs. This is a deliberate simplification — the Index tab is for "show me the index output," not for "perform side effects on my filesystem."

##### Meta Merge tab

The Meta Merge tab performs indexing with sidecar metadata merged into parent entries. It automatically implies `--meta` (EXIF extraction) — the "Extract EXIF" checkbox is not shown because it is always active for this operation.

| Control | Type | Default | Maps to |
|---------|------|---------|---------|
| ID Algorithm | `CTkComboBox` | `md5` | `IndexerConfig.id_algorithm` |
| Compute SHA-512 | `CTkCheckBox` | Unchecked | `IndexerConfig.compute_sha512` |
| Output mode | `CTkRadioButton` group: View only / Save to file / Both | View only | Output routing |

This tab sets `extract_exif=True` and `meta_merge=True` in the configuration overrides. The user does not need to know about the implication chain — the tab's purpose is self-evident from its name.

##### Meta Merge Delete tab

The Meta Merge Delete tab performs sidecar merging with post-indexing deletion of the original sidecar files. This is a destructive operation and the GUI reflects this with visual safety cues.

| Control | Type | Default | Maps to |
|---------|------|---------|---------|
| ID Algorithm | `CTkComboBox` | `md5` | `IndexerConfig.id_algorithm` |
| Compute SHA-512 | `CTkCheckBox` | Unchecked | `IndexerConfig.compute_sha512` |
| Output file | `CTkEntry` + Browse | _(required)_ | `IndexerConfig.output_file` |
| Also write in-place sidecars | `CTkCheckBox` | Checked | `IndexerConfig.output_inplace` |

**Key differences from Meta Merge:**

1. **Output file is mandatory.** The "View only" output mode is not available on this tab. The safety requirement from §7.1 — MetaMergeDelete requires at least one persistent output — is enforced structurally by the form design rather than by validation after the fact. The output file field is always visible and the action button is disabled until a valid output path is entered.

2. **In-place sidecar checkbox defaults to checked.** Because MetaMergeDelete removes the original sidecar files, writing in-place sidecar JSON files alongside each item provides a secondary recovery path. The checkbox defaults to checked as a safety measure but can be unchecked by users who only want the aggregate output file.

3. **Visual warning.** A cautionary label is displayed below the action button: _"This operation will delete sidecar metadata files after merging their content. Ensure your output file path is correct before proceeding."_ The label uses a warning color (amber/yellow in dark theme) to draw attention without blocking execution.

This tab sets `extract_exif=True`, `meta_merge=True`, and `meta_merge_delete=True` in the configuration overrides.

##### Rename tab

The Rename tab performs file renaming to `storage_name` values (§6.10). This is the most destructive operation the tool offers and the GUI reflects this with the strongest safety defaults.

| Control | Type | Default | Maps to |
|---------|------|---------|---------|
| ID Algorithm | `CTkComboBox` | `md5` | `IndexerConfig.id_algorithm` |
| Compute SHA-512 | `CTkCheckBox` | Unchecked | `IndexerConfig.compute_sha512` |
| Dry run (preview only) | `CTkCheckBox` | **Checked** | `IndexerConfig.dry_run` |

**Key differences from other tabs:**

1. **Dry run defaults to checked.** The user must explicitly uncheck the dry-run checkbox to perform actual renames. This is the inverse of the CLI default (where `--dry-run` must be explicitly specified) because the GUI audience is assumed to be less experienced and the consequences of an unintended rename are severe. When dry run is active, the action button label reads "▶ Preview Renames" instead of "▶ Run Rename."

2. **In-place output is always active.** The Rename tab does not expose an in-place checkbox — `output_inplace=True` is always set because the rename operation implies it (§7.1). The user is informed of this via a label: _"In-place sidecar files will be written alongside each renamed item."_

3. **No output file option.** The Rename tab's primary output is the rename side effect, not a JSON file. The output panel shows the JSON result for inspection, and the user can save it via the output panel's Save button if needed. A dedicated output-file field would add clutter without adding value.

4. **Visual warning (when dry run is unchecked).** When the user unchecks the dry-run checkbox, a warning label appears: _"Renaming is destructive — original filenames will be replaced. In-place sidecar files contain the original names for recovery."_ The label uses a warning color consistent with the Meta Merge Delete tab.

This tab sets `rename=True` and `output_inplace=True` in the configuration overrides. When dry run is checked, `dry_run=True` is also set.

> **Deviation from CLI parity:** The CLI treats `--dry-run` as opt-in (default off). The GUI inverts this to default on. This is a deliberate UX decision: the GUI user is more likely to be exploring the tool's behavior and less likely to understand the implications of an irreversible rename. The CLI user, by contrast, has already read the help text and constructed a command deliberately. The behavioral outcome of the indexing engine is identical — only the default is different.

---

### 10.4. Configuration Panel

The Settings tab is accessed via the bottom sidebar button and provides a persistent configuration interface for preferences that apply across all operations and across sessions. Unlike the operation tabs, the Settings tab has no action button and no output panel — it is a pure configuration surface.

#### Settings layout

```
┌──────────────────────────────────────────────────────┐
│  Settings                                            │
│                                                      │
│  Indexing Defaults                                   │
│  ─────────────────────────────────────────────       │
│  Default ID Algorithm:    [md5 ▾]                    │
│  Compute SHA-512:         [ ]                        │
│                                                      │
│  Output Preferences                                  │
│  ─────────────────────────────────────────────       │
│  JSON Indentation:        [2 ▾]  (spaces)            │
│  Pretty-print by default: [✓]                        │
│                                                      │
│  Logging                                             │
│  ─────────────────────────────────────────────       │
│  Verbosity:               [Normal ▾]                 │
│                                                      │
│  Configuration                                       │
│  ─────────────────────────────────────────────       │
│  Config file:   [_________________________] [Browse] │
│  (Optional. Overrides compiled defaults.)            │
│                                                      │
│  About                                               │
│  ─────────────────────────────────────────────       │
│  Version: 0.1.0                                      │
│  Python:  3.12.x                                     │
│  exiftool: /usr/bin/exiftool (v12.85)  ✓             │
│            — or —                                    │
│  exiftool: Not found on PATH  ⚠                     │
│                                                      │
│  ┌────────────────────┐  ┌──────────────────────┐   │
│  │  Reset to Defaults │  │  Open Config Folder  │   │
│  └────────────────────┘  └──────────────────────┘   │
│                                                      │
└──────────────────────────────────────────────────────┘
```

#### Settings fields

| Section | Field | Type | Default | Behavior |
|---------|-------|------|---------|----------|
| Indexing Defaults | Default ID Algorithm | `CTkComboBox` | `md5` | Pre-populates the ID Algorithm selector on all operation tabs. Per-tab overrides take precedence. |
| Indexing Defaults | Compute SHA-512 | `CTkCheckBox` | Unchecked | Pre-populates the SHA-512 checkbox on all operation tabs. |
| Output Preferences | JSON Indentation | `CTkComboBox` (`2`, `4`, `None`) | `2` | Controls the `indent` parameter passed to `serialize_entry()`. `None` produces compact (single-line) JSON. |
| Output Preferences | Pretty-print by default | `CTkCheckBox` | Checked | When unchecked, forces `indent=None` regardless of the indentation selector. |
| Logging | Verbosity | `CTkComboBox` (`Normal`, `Verbose`, `Debug`) | `Normal` | Maps to log level: Normal → WARNING, Verbose → INFO, Debug → DEBUG. Log output is directed to the progress display area (§10.5), not to a separate console window. |
| Configuration | Config file | `CTkEntry` + Browse | _(empty)_ | Optional path to a TOML configuration file. When set, this path is passed to `load_config(config_file=...)` for all operations. When empty, the standard resolution chain (§3.3) applies. |

#### Settings persistence

Settings values are saved to the session file (§10.1, session persistence) when the user navigates away from the Settings tab or when the application exits. Settings changes take effect immediately — there is no "Apply" button. When a setting changes, the affected operation tabs are notified to update their default widget values if the user has not already overridden them on that tab.

**Default propagation rule:** Settings provide defaults, not overrides. If the user has explicitly changed the ID Algorithm on the Index tab to `sha256`, and then changes the Settings default to `md5`, the Index tab retains `sha256`. Only tabs where the user has not touched the field inherit the new default. This is tracked via a "user-modified" flag on each per-tab widget.

#### Utility buttons

**Reset to Defaults.** Resets all Settings fields to their compiled default values. Does NOT reset per-tab input state — only the Settings panel's own fields. Presents a confirmation dialog before proceeding: _"Reset all settings to defaults? Per-tab inputs will not be affected."_

**Open Config Folder.** Opens the platform-specific application data directory (`%APPDATA%\shruggie-indexer\` on Windows, `~/.config/shruggie-indexer/` on Linux, `~/Library/Application Support/shruggie-indexer/` on macOS) in the system file manager. This is a convenience for users who want to edit the TOML configuration file directly. If the directory does not exist, it is created before opening.

#### About section

The About section at the bottom of the Settings panel displays static environment information useful for debugging:

- **Version:** Read from `shruggie_indexer.__version__` at startup.
- **Python:** `sys.version` truncated to major.minor.patch.
- **exiftool:** The result of a startup availability check (§4.5). Displays the resolved path and version if found (via `exiftool -ver`), or a warning icon with "Not found on PATH" if absent. This check is performed once at application startup, not on each operation invocation.

---

### 10.5. Indexing Execution and Progress

This subsection defines how the GUI executes indexing operations, displays progress, enforces job exclusivity, and supports cancellation.

#### Action button behavior

Each operation tab has a single action button at the bottom of its input section. The button label reflects the operation:

| Tab | Button label (idle) | Button label (dry run) |
|-----|-------------------|----------------------|
| Index | ▶ Run Index | — |
| Meta Merge | ▶ Run Meta Merge | — |
| Meta Merge Delete | ▶ Run Meta Merge Delete | — |
| Rename | ▶ Run Rename | ▶ Preview Renames |

When clicked, the action button:

1. Validates the current tab's input fields (target path exists, required fields are populated).
2. Constructs an `IndexerConfig` via `load_config()` with the appropriate overrides.
3. Transitions the UI to the "running" state (§10.5, job exclusivity).
4. Spawns a background thread that calls `index_path()`.
5. Updates the progress display as the operation proceeds.
6. On completion, populates the output panel and transitions the UI back to the "idle" state.

If input validation fails, the action button does not spawn a thread. Instead, the first invalid field is highlighted (border color change to red/error color) and a brief validation message is displayed adjacent to the field or at the top of the input section. The validation message disappears when the user corrects the field.

#### Job exclusivity

Only one indexing operation may execute at a time. The GUI enforces this by entering a "running" state when any operation begins and exiting it when the operation completes (successfully, with error, or by cancellation).

**Running state effects:**

| UI element | Behavior during running state |
|------------|------------------------------|
| All sidebar operation tab buttons | Visually dimmed and non-clickable. The active tab remains highlighted but all other tab buttons are disabled. |
| Settings sidebar button | Remains clickable — users can view settings while an operation runs, but cannot change settings that would affect the in-flight operation. Settings changes during a running operation are deferred until the operation completes. |
| Action button on the active tab | Changes label to "■ Cancel" and changes color to a warning/stop color (red tint). Clicking it initiates cancellation (see below). |
| Action buttons on inactive tabs | Disabled (non-interactive). Not visible since those tabs are hidden, but disabled in state to prevent race conditions if the user switches tabs immediately after an operation completes. |
| Input fields on the active tab | Disabled (non-editable). The user cannot modify the configuration of a running operation. |
| Output panel | Cleared at operation start. Displays incremental progress information during execution. Populated with final JSON output on completion. |

The running state is tracked by a single boolean flag (`_job_running: bool`) on the application instance. All UI transitions check this flag before allowing state changes.

#### Progress display

The progress display area occupies the output panel during operation execution. It provides real-time feedback about the indexing operation's progress, replacing the blank or previous-output state of the output panel.

**Progress display layout:**

```
┌────────────────────────────────────────────────────────┐
│  Progress                                    [Cancel]  │
│  ──────────────────────────────────────────────        │
│  ┌────────────────────────────────────────────────┐   │
│  │ ████████████████████░░░░░░░░░░░░  67%  342/512 │   │
│  └────────────────────────────────────────────────┘   │
│                                                        │
│  Status: Processing file 342 of 512                    │
│  Current: /path/to/current/file.jpg                    │
│  Elapsed: 00:01:23                                     │
│                                                        │
│  ┌────────────────────────────────────────────────────┐│
│  │ 00:01:23  INFO   Indexing /path/to/dir             ││
│  │ 00:01:23  INFO   Discovered 512 items              ││
│  │ 00:01:24  INFO   Processing file 1/512: a.jpg      ││
│  │ 00:01:24  WARN   exiftool timeout for b.raw        ││
│  │ ...                                                ││
│  │ 00:02:41  INFO   Processing file 342/512: f.jpg    ││
│  └────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────┘
```

The progress display has three visual components:

**1. Progress bar.** A `CTkProgressBar` widget showing a determinate percentage when the total item count is known (directory targets after discovery), or an indeterminate animation (pulsing/marquee) when the total is not yet known (during the discovery phase of directory traversal, or for single-file targets where the operation is effectively instantaneous).

For directory targets, the progress percentage is `items_completed / total_items_discovered`. The total is known after the traversal discovery phase (Stage 3, §4.1) completes. During discovery, the progress bar shows indeterminate animation and the status line reads "Discovering items..." with a running count of items found so far. Once discovery completes, the bar switches to determinate mode and the status line shows the fraction.

**2. Status summary.** Three text labels displaying:
- **Status:** A one-line human-readable description of what the engine is currently doing ("Discovering items...", "Processing file 342 of 512", "Writing output...", "Deleting sidecar files...").
- **Current:** The path of the item currently being processed. Truncated with an ellipsis prefix if it exceeds the available width (`...very/long/path/to/file.jpg`).
- **Elapsed:** A running wall-clock timer in `HH:MM:SS` format, updated every second via a `tkinter.after()` timer.

**3. Log stream.** A scrollable, read-only `CTkTextbox` that displays log messages from the indexing engine in real time. This textbox uses the same monospaced font as the JSON output panel (JetBrains Mono → Consolas fallback). Messages are formatted as `HH:MM:SS  LEVEL  message` and are appended incrementally. The log stream auto-scrolls to the bottom as new messages arrive, unless the user has manually scrolled up to inspect earlier messages (auto-scroll pauses when the user scrolls away from the bottom and resumes when they scroll back to the end).

**Progress callback integration:** The GUI installs a progress callback on the `IndexerConfig` (or passes it as an argument to `index_path()`) that the core engine invokes at defined intervals during processing. The callback is a callable with the signature:

```python
def on_progress(event: ProgressEvent) -> None:
    """Called by the indexing engine to report progress."""
```

Where `ProgressEvent` is a lightweight dataclass:

```python
@dataclass
class ProgressEvent:
    phase: str           # "discovery", "processing", "output", "cleanup"
    items_total: int | None    # None during discovery
    items_completed: int
    current_path: Path | None  # The item currently being processed
    message: str | None        # Optional log-level message
    level: str                 # "info", "warning", "error", "debug"
```

The progress callback is invoked on the background thread. It MUST NOT touch widgets directly. Instead, it enqueues events into a `queue.Queue`, which the main thread drains on a 50ms `after()` timer to update the progress display widgets. This polling interval provides visually smooth progress updates without excessive main-thread load.

> **Architectural note:** The public API (§9) does not currently define a progress callback parameter on `index_path()`. The GUI will require the core engine to support this callback. The recommended approach is to add an optional `progress_callback: Callable[[ProgressEvent], None] | None = None` parameter to `index_path()` and `build_directory_entry()`, defaulting to `None` (no callback, matching CLI behavior). The callback is invoked after each item is processed. This is a GUI-driven addition to the core API that also benefits CLI users who want progress reporting via `tqdm` or `rich`. The §9 and §6 specifications should be updated to reflect this addition when the GUI sprint is implemented.

#### Cancellation

Long-running operations can be cancelled by clicking the "■ Cancel" button that replaces the action button during execution. Cancellation is cooperative — the indexing engine checks a cancellation flag at defined checkpoints and raises a `CancellationError` when cancellation is requested.

**Cancellation mechanism:**

1. The GUI creates a `threading.Event` object (`cancel_event`) before spawning the background thread.
2. The `cancel_event` is passed to the indexing engine (via the same mechanism as the progress callback — an optional parameter on `index_path()` or a field on `IndexerConfig`).
3. The engine checks `cancel_event.is_set()` at the start of each item's processing loop. If set, the engine stops processing and raises `IndexerCancellationError`.
4. The background thread catches `IndexerCancellationError` and signals completion to the main thread with a "cancelled" status.
5. The main thread updates the progress display to show "Operation cancelled" and transitions back to the idle state.

**Cancellation granularity:** Cancellation is per-item, not mid-item. Once the engine begins processing a single file or directory entry (hashing, exiftool invocation, etc.), that item runs to completion before the cancellation flag is checked. This ensures that partial items are never written to output — every item in the output is complete. For single-file operations, cancellation is not meaningful (the operation is essentially atomic).

**Cancellation and MetaMergeDelete:** If a MetaMergeDelete operation is cancelled, NO sidecar files are deleted — the deletion queue (Stage 6, §4.1) is discarded. The output produced before cancellation (in-place sidecars, partial aggregate file) may exist on disk but the sidecar source files are preserved. This is the safe default.

**Cancellation exception:**

```python
class IndexerCancellationError(IndexerError):
    """The operation was cancelled by the user."""
```

This exception is added to the hierarchy defined in §9.5 and maps to a new GUI-specific status rather than a CLI exit code (the CLI does not currently support mid-operation cancellation, though it could be extended to handle `SIGINT` in a future version).

#### Completion states

When the background thread finishes (successfully, with error, or by cancellation), it signals the main thread via the progress queue with a terminal event. The main thread then:

1. Transitions the UI back to the idle state (re-enable sidebar tabs, restore action button, re-enable input fields).
2. Updates the progress display:

| Outcome | Progress bar | Status text | Log stream | Output panel |
|---------|-------------|-------------|------------|--------------|
| Success | 100%, green tint | "Completed — N items indexed in MM:SS" | Final summary appended | Populated with JSON output |
| Partial failure | 100%, amber tint | "Completed with N warnings — M of N items indexed" | Warning summary appended | Populated with JSON output (with degraded fields) |
| Error | Red tint, stopped | "Failed — [error message]" | Error details appended | Displays error JSON or message |
| Cancelled | Amber tint, stopped | "Cancelled after N of M items" | Cancellation notice appended | Empty or partial output (not displayed) |

For the success and partial-failure cases, the progress display is replaced by the JSON output in the output panel after a brief delay (500ms) to allow the user to see the completion status. The user can toggle back to the progress/log view via a tab or toggle button at the top of the output panel (see §10.6).

---

### 10.6. Output Display and Export

#### Output panel

The output panel occupies the lower portion of the working area on all operation tabs. It serves dual purpose: displaying progress/logs during execution (§10.5) and displaying the JSON result after completion. A toggle at the top of the panel switches between the two views:

```
  [ Output ▾ ]  [ Log ▾ ]                    [Copy] [Save]
```

The "Output" tab shows the JSON viewer. The "Log" tab shows the log stream from the most recent operation (preserved after completion so the user can review warnings and timing information). The toggle defaults to "Output" after a successful operation and to "Log" after an error or cancellation.

#### JSON viewer

The JSON viewer is a scrollable, read-only `CTkTextbox` configured with a monospaced font (JetBrains Mono → Consolas fallback, matching `shruggie-feedtools`). It displays the serialized JSON output from `serialize_entry()` with the indentation level configured in the Settings panel.

**Syntax highlighting:** The JSON viewer SHOULD apply basic syntax highlighting to improve readability. At minimum: keys in one color, string values in another, numeric values in a third, and `null`/`true`/`false` in a fourth. CustomTkinter's `CTkTextbox` supports tag-based coloring via the underlying tkinter `Text` widget's `tag_configure()` and `tag_add()` methods. A lightweight JSON token scanner (not a full parser — just regex-based token identification) applies color tags after the JSON text is loaded.

Syntax highlighting is a SHOULD requirement, not a MUST. If implementation complexity is prohibitive for the MVP, plain monospaced text without coloring is acceptable. The `shruggie-feedtools` GUI does not implement syntax highlighting in its output panel, so this would be a visual improvement over the reference implementation.

**Large output handling:** For large index trees (thousands of items), the JSON output can be several megabytes. The JSON viewer MUST remain responsive — it SHOULD NOT attempt to load the entire output into the textbox if doing so would cause a visible UI freeze. The recommended approach:

1. For outputs under 1 MB, load the full text into the textbox.
2. For outputs between 1 MB and 10 MB, load the text but disable syntax highlighting (tag application is the expensive operation, not text insertion).
3. For outputs over 10 MB, display a summary message in the viewer: _"Output is [size] — too large for inline display. Use Save to export."_ The full output is held in memory and available via the Save button.

These thresholds are approximate and SHOULD be tuned during implementation based on observed performance.

#### Copy button

Copies the full JSON output to the system clipboard via `widget.clipboard_clear()` / `widget.clipboard_append()`. For large outputs (>10 MB), the copy button displays a brief "Copying..." state and performs the clipboard operation in a short background task to avoid UI freeze. If the output exceeds the platform's clipboard size limit (rare but possible on some Linux configurations), a warning is displayed.

The Copy button is disabled when no output is present (before any operation has completed or after a cancellation).

#### Save button

Opens a platform-native save-as dialog defaulting to `.json` extension and a filename derived from the target: `{target_stem}-index.json` for the most recent operation. The dialog remembers the last-used save directory across sessions (stored in the session file).

The Save button writes the full JSON output (regardless of whether the output panel is displaying a truncated preview) to the selected file using UTF-8 encoding. After a successful save, a brief toast/notification message appears near the Save button: _"Saved to {filename}"_ (auto-dismisses after 3 seconds).

The Save button is disabled when no output is present.

#### Output panel interaction with tabs

The output panel is a shared widget instance — there is one output panel, and it displays the result of the most recent operation regardless of which tab initiated it. When the user switches tabs, the output panel retains its current content. This means:

- User runs an Index operation → output panel shows the Index result.
- User switches to the Rename tab → output panel still shows the Index result.
- User runs a Rename preview → output panel is cleared and then shows the Rename result.

This behavior is consistent with `shruggie-feedtools`, where the output panel always shows the most recent operation's result.

---

### 10.7. Keyboard Shortcuts and Accessibility

#### Keyboard shortcuts

The GUI defines a minimal set of keyboard shortcuts for common actions. Shortcuts use platform-standard modifier keys: `Ctrl` on Windows/Linux, `Cmd` on macOS.

| Shortcut | Action | Notes |
|----------|--------|-------|
| `Ctrl+R` / `Cmd+R` | Execute the current tab's action | Equivalent to clicking the action button. Disabled during running state. |
| `Ctrl+C` / `Cmd+C` | Copy output to clipboard | Only when the output panel has focus or content. Standard copy behavior in text fields takes precedence when an input field has focus. |
| `Ctrl+S` / `Cmd+S` | Save output to file | Opens the save-as dialog. |
| `Ctrl+.` / `Cmd+.` | Cancel running operation | Equivalent to clicking the Cancel button. No-op when idle. |
| `Ctrl+1` through `Ctrl+4` | Switch to operation tab 1–4 | `Ctrl+1` = Index, `Ctrl+2` = Meta Merge, `Ctrl+3` = Meta Merge Delete, `Ctrl+4` = Rename. Disabled during running state. |
| `Ctrl+,` / `Cmd+,` | Open Settings | Standard "preferences" shortcut. Always available. |
| `Ctrl+Q` / `Cmd+Q` | Quit application | Prompts for confirmation if an operation is running. |
| `Escape` | Cancel running operation | Secondary cancel shortcut. No-op when idle. |

Keyboard shortcuts MUST NOT conflict with standard text-editing shortcuts within input fields (`Ctrl+A` for select all, `Ctrl+V` for paste, `Ctrl+Z` for undo). The shortcuts above are chosen to avoid these conflicts.

#### Tab order

All interactive widgets follow a logical tab order (keyboard `Tab` key navigation) within each operation tab. The tab order proceeds top-to-bottom, left-to-right: Target path → Browse button → Type radio group → Recursive checkbox → per-tab options → action button. The output panel is excluded from the tab order (it is read-only).

#### Accessibility notes

The GUI makes reasonable accommodations for keyboard-only operation but does not target formal accessibility compliance (WCAG, Section 508) for the MVP. CustomTkinter inherits `tkinter`'s native accessibility support, which varies by platform — Windows provides the best screen reader integration via UI Automation, Linux/macOS support is limited.

**Minimum requirements for MVP:**

- All interactive controls are reachable via keyboard tab navigation.
- All buttons have descriptive text labels (no icon-only buttons without tooltips).
- Warning labels use both color AND text to convey their message (not color alone).
- The progress bar's percentage is exposed as text in the adjacent status label.
- Focus indicators are visible on all interactive widgets (CustomTkinter provides this by default in dark theme).

Formal accessibility improvements are a post-MVP consideration.

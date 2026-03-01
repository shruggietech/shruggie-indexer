# Desktop Application Guide

The shruggie-indexer desktop application provides a visual interface for indexing files and folders, extracting metadata, and managing sidecar files — all without touching a command line. This guide walks you through every part of the application.

---

## Launching the Application

How you start the application depends on how you installed it.

### Standalone Executable (Recommended for Most Users)

Download the pre-built executable for your platform from the [GitHub Releases](https://github.com/shruggietech/shruggie-indexer/releases) page. No Python installation is required.

- **Windows:** Run `shruggie-indexer-gui.exe`
- **Linux:** Run `./shruggie-indexer-gui`
- **macOS:** Run `./shruggie-indexer-gui`

### Installed via pip

If you installed shruggie-indexer with the GUI extra (`pip install shruggie-indexer[gui]`), launch it from a terminal:

```
shruggie-indexer-gui
```

!!! note "Windows SmartScreen Warning"
    When running the standalone executable on Windows for the first time, you may see a
    **"Windows protected your PC"** popup from Microsoft Defender SmartScreen. This is
    normal for applications that have not yet accumulated a reputation with Microsoft's
    cloud-based trust system. It does **not** mean the application is harmful.

    To proceed:

    1. Click **"More info"** in the SmartScreen dialog.
    2. Click **"Run anyway"**.

    This only needs to be done once. After the first launch, Windows remembers your
    choice and will not show the warning again.

    **Why does this happen?** SmartScreen flags executables that are new or not digitally
    signed by a recognized certificate authority. Because shruggie-indexer is an
    open-source project, it does not carry a commercial code-signing certificate. You can
    verify the download's integrity by checking its SHA-256 hash against the value
    published on the GitHub release page.

---

## Window Layout

The application window is divided into three areas:

1. **Sidebar** (left) — Navigation between the three main tabs: **Operations**, **Settings**, and **About**. An **Exit** button (red accent color) is positioned near the bottom of the sidebar, above the version label. Clicking it triggers the same close/cleanup sequence as the window's close button. The application version is displayed at the very bottom of the sidebar.
2. **Main content area** (center/right) — Changes depending on which sidebar tab is selected.
3. **Output panel** (bottom) — Displays results and log messages after an operation finishes. This panel is only visible on the Operations tab.

---

## Operations Tab

The Operations tab is where you configure and run indexing jobs. It is organized into labeled card sections. The **Target**, **Options**, and **Output** cards are **collapsible** — click anywhere on a card's header row to collapse or expand it. A small caret icon (▶ collapsed / ▼ expanded) on the left side of each header indicates the current state. Collapsed/expanded states are remembered between sessions. All three cards are expanded by default.

### Choosing an Operation Type

At the top of the Operations tab, a dropdown lets you choose one of three operation types:

| Operation | What it does | Destructive? |
|-----------|-------------|:------------:|
| **Index** | Scans files or folders and produces a structured JSON report containing hashes, timestamps, sizes, and (optionally) embedded metadata. Nothing on disk is changed. | No |
| **Meta Merge** | Same as Index, but also discovers sidecar files (small companion files that sit alongside your media) and merges their contents into the report. Original files are untouched. | No |
| **Meta Merge Delete** | Same as Meta Merge, but **deletes the sidecar files** from disk after merging them into the report. The merged data is preserved in the output file. | **Yes** |

!!! info "Pipeline execution order"
    When Meta Merge Delete runs, the pipeline proceeds in a fixed order:

    1. **Index** — Discover and process all items; sidecar files are identified, parsed, and queued for deletion.
    2. **Write sidecars** — In-place `_meta2.json` and `_directorymeta2.json` output files are written alongside each item (if multi-file output is selected).
    3. **Rename** — Files are renamed to their `storage_name` values (if rename is enabled). In-place sidecar files are renamed alongside their content files.
    4. **Delete** — Consumed sidecar files are removed from disk. Each deletion is logged.

    If the operation is cancelled, steps that have not yet started are skipped. In particular, the delete step is never reached if the operation is interrupted — no sidecar files are deleted until all preceding steps complete successfully.

A small colored dot next to the dropdown indicates whether the current configuration is **destructive** (red) or **non-destructive** (green). This indicator updates in real time as you change settings — including when the rename feature is toggled (see Options Section below).

### Target Section

This is where you tell the application what to process.

- **Path field** — Type or paste a file or folder path, or use the Browse buttons to pick one.
- **Browse buttons** — When the target type is set to "Auto", two buttons appear: **File…** and **Folder…**, letting you pick either. When the type is set to "File" or "Directory", a single Browse button appears.
- **Type** — A dropdown menu to choose how the target path should be interpreted:
    - **Auto** — The application figures out whether the path is a file or folder.
    - **File** — Treat the path as a single file.
    - **Directory** — Treat the path as a folder (processes all items inside).
- **Recursive** — When checked (the default), subfolders are also processed. Uncheck this to process only the top-level contents of a folder. This option is automatically disabled when the target type is "File" (recursion has no meaning for single files).

!!! tip "Target/Type Validation"
    The application automatically detects whether the selected path is a file or directory. If the detected kind conflicts with the selected type (e.g., you select "File" type but point to a directory), a red error message appears below the type dropdown and the START button is disabled until the conflict is resolved.

### Options Section

All option controls are always visible regardless of the selected operation type. Controls that do not apply to the current operation are disabled with a brief explanation.

- **ID Algorithm** — Choose between `md5` (faster, shorter IDs) and `sha256` (stronger, longer IDs). This controls how file identifiers are generated.
- **Compute SHA-512** — When checked, an additional high-strength hash is computed for each file. If the "Compute SHA-512 by default" setting is enabled on the Settings tab, this checkbox is forced on with an explanation ("Enabled in Settings") and cannot be unchecked from the Operations tab.
- **Extract EXIF metadata** — When checked, embedded metadata (camera settings, GPS coordinates, creation dates, etc.) is extracted from media files using ExifTool. Requires ExifTool to be installed. Automatically forced on for Meta Merge and Meta Merge Delete operations.
- **Rename files** — When checked, files are renamed to unique, content-based names ("storage names") after indexing. This feature can be combined with any operation type. Enabling rename makes the operation destructive (the indicator dot turns red) unless dry-run is also enabled.
- **Dry run** — Only shown when "Rename files" is checked. When enabled, previews what files *would* be renamed without actually changing anything. This is on by default as a safety measure.

### Output Section

The Output section uses a dropdown menu to select where results are written:

- **Output mode** (dropdown):
    - **Single file** — All results are written to one aggregate JSON file. The file path is shown in a read-only display below the dropdown.
    - **Multi-file** — Results are written as individual sidecar JSON files alongside each processed file (e.g., `photo.jpg_meta2.json`) and inside each subdirectory (e.g., `images_directorymeta2.json`). The root target directory does not receive an in-place sidecar — use **Single file** mode for the aggregate output. Only available when the target is a directory.
    - **View only** — Results are displayed in the output panel at the bottom of the window. Nothing is written to disk. Not available when Meta Merge Delete or Rename is active.
- **Output path** — A read-only field showing the auto-computed output path based on your target. For "View only" mode, this displays "(displayed in viewer)". For "Multi-file" mode, a note explains that sidecar files are written alongside originals.

!!! tip "Output mode constraints"
    The available modes adjust automatically based on your target and operation type:

    - **Multi-file** requires a directory target (not available for single files).
    - **View only** is not available for Meta Merge Delete (destructive operations require a persistent output record) or when Rename is active (rename requires writing files to disk). The option remains visible in the dropdown but selecting it snaps back to the appropriate default with an explanatory message.

### Running an Operation

Once everything is configured, click the green **▶  START** button at the bottom of the Operations area. The button is centered and uses a distinct green color to differentiate it from other controls.

!!! note "Validation Required"
    The START button is disabled if the target path is empty or if a target/type conflict
    exists. Resolve any red error messages before running.

While the operation runs:

- A **progress panel** replaces the output area, showing:
    - Current status ("Discovering items…", "Processing: 5/12 (42%)")
    - Elapsed time
    - A progress bar
    - The file currently being processed
    - A scrolling log of activity
- The action button changes to a red **■ Cancel** button with the same dimensions as the START button. Click it (or press ++escape++) to stop the operation after the current file finishes.
- All input controls on the Operations tab are disabled during execution.

When the operation completes, the progress panel disappears and the result data is populated. The active Output/Log tab is preserved — if you were viewing the Log tab during the operation, the Log tab remains active. The Output button briefly highlights green to signal that new content is available.

---

## Output Panel

The output panel appears at the bottom of the Operations tab after a job finishes. It has two views, switchable via toggle buttons in the toolbar:

- **Output** — The JSON result data, with color-coded syntax highlighting for readability.
- **Log** — Messages generated during the operation (progress updates, warnings, errors).

### Toolbar Buttons

| Button | What it does |
|--------|-------------|
| **Save** | Opens a file picker to save the current view content (JSON output or log) to disk. Enabled when the active view has content. |
| **Copy** | Copies the currently visible content (output or log) to the clipboard. The button briefly turns green and shows "Copied ✓" to confirm. Enabled when the active view has content. |
| **Clear** | Clears both the output and log content. |

### Resizing

A **drag handle** with a centered grip indicator (three small dots) sits between the scrollable input area and the START button. Drag it up or down to resize the output panel below. The application remembers your preferred size between sessions.

---

## Settings Tab

The Settings tab lets you customize default behavior. Changes take effect immediately and are remembered between sessions. Settings are organized into four card sections, with an additional collapsible Advanced section below.

The **Reset to Defaults** and **Open Config Folder** buttons are anchored in a fixed (non-scrollable) region at the bottom of the Settings page, separated from the scrollable cards by a visible divider. They remain accessible at all scroll positions.

### Indexing

- **Default ID Algorithm** — Sets the default hash algorithm (`md5` or `sha256`) for new operations.
- **Compute SHA-512 by default** — When checked, SHA-512 computation is enabled by default for new operations.

### Output & Logging

- **JSON Indentation** — Controls formatting of the JSON output:
    - **2 spaces** — Compact but readable (default).
    - **4 spaces** — More spacious, easier to scan visually.
    - **Compact** — No extra whitespace. Smaller file sizes but harder to read.
- **Write log files** — When checked (default: on), each operation writes a timestamped log file to the platform-specific app data directory. Startup messages are also captured. No log file is written when Log Level is "None", even if this checkbox is checked.
- **Log Level** — A dropdown controlling how much detail appears in the log view:
    - **None** — Suppresses all logging. The log panel displays a static notice instead of log messages. No log file is written.
    - **Normal** — Shows only warnings and errors (default).
    - **Verbose** — Adds informational messages about each processing step.
    - **Debug** — Maximum detail, including per-file processing events, hash computation, ExifTool calls, and sidecar discovery. Useful for troubleshooting.
- **Log file path** — A read-only field showing the computed path where log files are written. The text appears greyed out when logging to file is disabled.

### Interface

- **Show tooltips on hover** — When checked, hovering over any control shows a brief description of what it does. Uncheck to hide all tooltips.

### Configuration

- **Custom Config File** — Optionally specify a TOML configuration file to load custom settings. Use the Browse button to pick one. A clickable link to the [Configuration File Format](https://shruggietech.github.io/shruggie-indexer/user-guide/configuration/#configuration-file-format) documentation is displayed below the field for reference.

### Global Action Buttons

- **Reset to Defaults** — Resets all settings to their factory values (asks for confirmation first).
- **Open Config Folder** — Opens the folder where the application stores its session data.

### Advanced Configuration

Below the standard settings, a collapsed **Advanced Configuration** section provides visibility into the full set of TOML-configurable behaviors. Expanding the section reveals six independently collapsible subsections, each with a disclosure caret and a brief description:

| Group | Description |
|-------|-------------|
| **Filesystem Exclusions** | Directories and file patterns skipped during traversal. |
| **Metadata Identification** | Regex patterns used to identify sidecar metadata files. |
| **Metadata Exclusion** | Regex patterns for excluding non-sidecar files from indexing. |
| **ExifTool** | ExifTool arguments, excluded keys, and excluded extensions. |
| **Extension Groups** | File extension to logical group mappings (e.g., image, video). |
| **Extension Validation** | Regex pattern defining valid file extensions. |

Each subsection displays the complete, untruncated compiled default values in read-only monospace textboxes sized to show all content without scrolling (capped at a maximum height for very large groups). Subsections are individually collapsible — clicking a subsection header toggles only that subsection. The parent "Advanced Configuration" toggle controls overall visibility. All subsections default to collapsed and their states persist across sessions.

The section includes a "Shared Settings" / "Indexer-Specific Settings" separator preparing for future cross-tool configuration via `shared.toml`. The "Shared Settings (not yet available)" label is displayed in red text to clearly indicate that this feature is not yet functional.

!!! note "Editing Deferred"
    The Advanced Configuration section is read-only in this release. Full editing,
    data binding, and persistence will be added in a future version. Each group
    includes a disabled "Reset to Defaults" button placeholder.

---

## About Tab

The About tab displays:

- Project name, description, and version number.
- Python version and ExifTool availability status.
- A **Documentation** button that opens this documentation site in your web browser.
- A **shruggie.tech** button that opens the developer's website.
- Attribution: "Built by ShruggieTech LLC".

---

## Keyboard Shortcuts

The application supports the following keyboard shortcuts:

| Shortcut | Action |
|----------|--------|
| ++ctrl+r++ | Run the current operation |
| ++ctrl+s++ | Save output to a file |
| ++ctrl+shift+c++ | Copy current output or log to the clipboard |
| ++ctrl+period++ | Cancel the running operation |
| ++escape++ | Cancel the running operation |
| ++ctrl+q++ | Quit the application |
| ++ctrl+comma++ | Switch to Settings tab |
| ++ctrl+1++ | Switch to Operations tab |
| ++ctrl+2++ | Switch to Settings tab |
| ++ctrl+3++ | Switch to About tab |

---

## Session Persistence

The application automatically saves your window size, position, selected tab, operation settings, card collapsed/expanded states, Advanced Configuration section states, and output panel height when you close it. The next time you open the application, everything is restored to where you left off.

Session data is stored in your operating system's standard application data directory under the shared shruggie-tech ecosystem namespace:

| Platform | Location |
|----------|----------|
| Windows | `%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\gui-session.json` |
| macOS | `~/Library/Application Support/shruggie-tech/shruggie-indexer/gui-session.json` |
| Linux | `~/.config/shruggie-tech/shruggie-indexer/gui-session.json` |

This is the same directory that contains the `config.toml` configuration file and the `logs/` subdirectory. The **Open Config Folder** button on the Settings page opens this directory.

If the session file is missing or becomes corrupted, the application starts with default settings.

!!! info "Migration from earlier versions"
    If you are upgrading from v0.1.1 or v0.1.0, existing session data at the
    old path (e.g., `%APPDATA%\shruggie-tech\shruggie-indexer\gui-session.json`
    or `%APPDATA%\shruggie-indexer\gui-session.json`) is read automatically.
    On the next save (application exit or operation completion), the session file
    is written to the new location. The old file is preserved — it is safe to
    delete manually after confirming the new file has been created.

---

## Tips and Troubleshooting

### ExifTool Is Not Detected

If the About tab shows "ExifTool: Not found", metadata extraction will be unavailable. Install ExifTool and make sure it is on your system PATH. See the [ExifTool Setup](../getting-started/exiftool.md) guide for instructions.

### Large Directories Are Slow

When indexing directories with thousands of files, the initial discovery phase may take a moment. The progress bar will be indeterminate (animated) during discovery, then switch to a percentage-based bar once processing begins. You can cancel at any time.

### Output Is Too Large to Display

If the JSON output exceeds 10 MB, the output panel will show a "too large to display" message and prompt you to save the results to a file instead. Use the **Save** button or switch the output mode to "Single file" before running.

### Application Appears Frozen

Long-running operations process files one at a time in the background. The interface should remain responsive. If you see no progress updates, check the log view for error messages. You can always cancel with ++escape++ or the Cancel button.

---

## To Do

!!! note "Screenshots Needed"
    This page requires annotated screenshots of the GUI application to illustrate
    the interface elements described above. Screenshots should cover:

    - The Operations page in idle state
    - The Operations page during an active indexing run (progress bar, log stream)
    - The Settings page
    - The About page
    - The output panel showing JSON output and log view
    - A destructive operation confirmation dialog

    Screenshot assets will be stored in `docs/assets/images/gui/`.

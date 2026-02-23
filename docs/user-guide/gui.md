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

1. **Sidebar** (left) — Navigation between the three main tabs: **Operations**, **Settings**, and **About**. The application version is displayed at the bottom of the sidebar.
2. **Main content area** (center/right) — Changes depending on which sidebar tab is selected.
3. **Output panel** (bottom) — Displays results and log messages after an operation finishes. This panel is only visible on the Operations tab.

---

## Operations Tab

The Operations tab is where you configure and run indexing jobs. It is organized into labeled sections.

### Choosing an Operation Type

At the top of the Operations tab, a dropdown lets you choose one of four operation types:

| Operation | What it does | Destructive? |
|-----------|-------------|:------------:|
| **Index** | Scans files or folders and produces a structured JSON report containing hashes, timestamps, sizes, and (optionally) embedded metadata. Nothing on disk is changed. | No |
| **Meta Merge** | Same as Index, but also discovers sidecar files (small companion files that sit alongside your media) and merges their contents into the report. Original files are untouched. | No |
| **Meta Merge Delete** | Same as Meta Merge, but **deletes the sidecar files** from disk after merging them into the report. The merged data is preserved in the output file. | **Yes** |
| **Rename** | Renames files to unique, content-based names (called "storage names"). Useful for deduplication and archival workflows. Has a preview mode that shows what *would* happen without actually renaming anything. | **Yes** (unless preview mode is on) |

A small colored dot next to the dropdown indicates whether the current configuration is **destructive** (red) or **non-destructive** (green). This indicator updates in real time as you change settings.

### Target Section

This is where you tell the application what to process.

- **Path field** — Type or paste a file or folder path, or use the Browse buttons to pick one.
- **Browse buttons** — When the target type is set to "Auto", two buttons appear: **File…** and **Folder…**, letting you pick either. When the type is set to "File" or "Directory", a single Browse button appears.
- **Type** — Choose how the target path should be interpreted:
    - **Auto** — The application figures out whether the path is a file or folder.
    - **File** — Treat the path as a single file.
    - **Directory** — Treat the path as a folder (processes all items inside).
- **Recursive** — When checked (the default), subfolders are also processed. Uncheck this to process only the top-level contents of a folder.

### Options Section

Available options change depending on the selected operation type.

- **ID Algorithm** — Choose between `md5` (faster, shorter IDs) and `sha256` (stronger, longer IDs). This controls how file identifiers are generated.
- **Compute SHA-512** — When checked, an additional high-strength hash is computed for each file. Useful for verification workflows; not needed for most users.
- **Extract EXIF metadata** — When checked, embedded metadata (camera settings, GPS coordinates, creation dates, etc.) is extracted from media files using ExifTool. Requires ExifTool to be installed. This option is automatically enabled for Meta Merge operations.
- **Dry run** (Rename only) — When checked, the application shows a preview of what files *would* be renamed without actually changing anything. This is on by default as a safety measure. Uncheck it to perform the actual rename.
- **Write in-place** (Meta Merge Delete only) — When checked, writes output as sidecar JSON files alongside the originals instead of a single combined file.

### Output Section

Controls where the results go after the operation completes.

- **Output mode:**
    - **View only** — Results are displayed in the output panel at the bottom of the window. Nothing is written to disk.
    - **Save to file** — Results are written to a file on disk. A brief confirmation message appears in the output panel.
    - **Both** — Results are both displayed and saved to a file.
- **Output file** — When saving to a file, this field shows the destination path. It is automatically filled in with a suggested name based on your target (e.g., `my-folder_directorymeta2.json`), but you can change it to anything you like.

### Running an Operation

Once everything is configured, click the action button at the bottom of the Operations area. The button label changes depending on the operation type:

- **▶ Run Index**
- **▶ Run Meta Merge**
- **▶ Run Meta Merge Delete**
- **▶ Preview Renames** (dry run on) / **▶ Run Rename** (dry run off)

While the operation runs:

- A **progress panel** replaces the output area, showing:
    - Current status ("Discovering items…", "Processing: 5/12 (42%)")
    - Elapsed time
    - A progress bar
    - The file currently being processed
    - A scrolling log of activity
- The action button changes to a red **■ Cancel** button. Click it (or press ++escape++) to stop the operation after the current file finishes.

When the operation completes, the progress panel disappears and the output panel shows the results.

---

## Output Panel

The output panel appears at the bottom of the Operations tab after a job finishes. It has two views, switchable via toggle buttons in the toolbar:

- **Output** — The JSON result data, with color-coded syntax highlighting for readability.
- **Log** — Messages generated during the operation (progress updates, warnings, errors).

### Toolbar Buttons

| Button | What it does |
|--------|-------------|
| **Save** | Opens a file picker to save the current JSON output to disk. |
| **Copy** | Copies the currently visible content (output or log) to the clipboard. The button briefly turns green and shows "Copied ✓" to confirm. |
| **Clear** | Clears both the output and log content. |

### Resizing

You can drag the top edge of the output panel up or down to resize it. The application remembers your preferred size between sessions.

---

## Settings Tab

The Settings tab lets you customize default behavior. Changes take effect immediately and are remembered between sessions.

### Indexing Defaults

- **Default ID Algorithm** — Sets the default hash algorithm (`md5` or `sha256`) for new operations.
- **Compute SHA-512 by default** — When checked, SHA-512 computation is enabled by default for new operations.

### Output Preferences

- **JSON Indentation** — Controls formatting of the JSON output:
    - **2 spaces** — Compact but readable (default).
    - **4 spaces** — More spacious, easier to scan visually.
    - **Compact** — No extra whitespace. Smaller file sizes but harder to read.

### Logging

- **Verbosity** — Controls how much detail appears in the log view:
    - **Normal** — Shows only warnings and errors.
    - **Verbose** — Adds informational messages about each processing step.
    - **Debug** — Maximum detail, including per-file processing events, hash computation, ExifTool calls, and sidecar discovery. Useful for troubleshooting.

### Interface

- **Show tooltips on hover** — When checked, hovering over any control shows a brief description of what it does. Uncheck to hide all tooltips.

### Configuration

- **Config File** — Optionally specify a TOML configuration file to load custom settings. Use the Browse button to pick one.
- **Reset to Defaults** — Resets all settings to their factory values (asks for confirmation first).
- **Open Config Folder** — Opens the folder where the application stores its session data.

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

The application automatically saves your window size, position, selected tab, operation settings, and output panel height when you close it. The next time you open the application, everything is restored to where you left off.

Session data is stored in your operating system's standard configuration directory:

| Platform | Location |
|----------|----------|
| Windows | `%APPDATA%\shruggie-indexer\gui-session.json` |
| macOS | `~/Library/Application Support/shruggie-indexer/gui-session.json` |
| Linux | `~/.config/shruggie-indexer/gui-session.json` |

If the session file is missing or becomes corrupted, the application starts with default settings.

---

## Tips and Troubleshooting

### ExifTool Is Not Detected

If the About tab shows "ExifTool: Not found", metadata extraction will be unavailable. Install ExifTool and make sure it is on your system PATH. See the [ExifTool Setup](../getting-started/exiftool.md) guide for instructions.

### Large Directories Are Slow

When indexing directories with thousands of files, the initial discovery phase may take a moment. The progress bar will be indeterminate (animated) during discovery, then switch to a percentage-based bar once processing begins. You can cancel at any time.

### Output Is Too Large to Display

If the JSON output exceeds 10 MB, the output panel will show a "too large to display" message and prompt you to save the results to a file instead. Use the **Save** button or switch the output mode to "Save to file" before running.

### Application Appears Frozen

Long-running operations process files one at a time in the background. The interface should remain responsive. If you see no progress updates, check the log view for error messages. You can always cancel with ++escape++ or the Cancel button.

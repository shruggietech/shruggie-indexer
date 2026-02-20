"""Shruggie Indexer — CustomTkinter desktop GUI application.

Thin presentation layer over the ``shruggie_indexer`` public API.  The GUI
constructs an ``IndexerConfig`` via ``load_config()``, calls ``index_path()``,
and formats results via ``serialize_entry()``.  No direct ``core/`` imports —
only the public API surface exposed by ``shruggie_indexer.__init__``.

Module structure follows spec §10.1: a single ``app.py`` for the MVP.
Decompose into ``tabs/``, ``widgets/``, ``session.py`` if the file exceeds
~1500 lines.

See spec sections 10.1-10.7 for full behavioral guidance.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from shruggie_indexer import (
    IndexerCancellationError,
    IndexerConfig,
    IndexerError,
    ProgressEvent,
    __version__,
    index_path,
    load_config,
    serialize_entry,
)

__all__ = ["ShruggiIndexerApp", "main"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_WINDOW_TITLE = "Shruggie Indexer"
_DEFAULT_GEOMETRY = "1100x750"
_MIN_WIDTH = 1000
_MIN_HEIGHT = 700
_SIDEBAR_WIDTH = 140
_POLL_INTERVAL_MS = 50
_TOAST_DURATION_MS = 3000
_COMPLETION_DELAY_MS = 500

# Output size thresholds (bytes)
_HIGHLIGHT_LIMIT = 1_000_000  # 1 MB
_DISPLAY_LIMIT = 10_000_000  # 10 MB

_MONOSPACE_FONTS = ("JetBrains Mono", "Consolas", "Courier New", "monospace")

# Sidebar tab identifiers
_TAB_INDEX = "index"
_TAB_META_MERGE = "meta_merge"
_TAB_META_MERGE_DELETE = "meta_merge_delete"
_TAB_RENAME = "rename"
_TAB_SETTINGS = "settings"

_OPERATION_TABS = (_TAB_INDEX, _TAB_META_MERGE, _TAB_META_MERGE_DELETE, _TAB_RENAME)

_TAB_LABELS = {
    _TAB_INDEX: "Index",
    _TAB_META_MERGE: "Meta Merge",
    _TAB_META_MERGE_DELETE: "Meta Merge\nDelete",
    _TAB_RENAME: "Rename",
    _TAB_SETTINGS: "Settings",
}


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------


class SessionManager:
    """Read/write GUI session state to a platform-appropriate JSON file.

    Session stores: window geometry, active tab, per-tab input values, and
    settings.  Gracefully falls back to defaults when the file is missing or
    corrupt.
    """

    def __init__(self) -> None:
        self._path = self._resolve_path()
        self._data: dict[str, Any] = {}

    # -- Platform paths -----------------------------------------------------

    @staticmethod
    def _resolve_path() -> Path:
        system = platform.system()
        if system == "Windows":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif system == "Darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / "shruggie-indexer" / "gui-session.json"

    # -- Public API ---------------------------------------------------------

    def load(self) -> dict[str, Any]:
        """Load session data.  Returns empty dict on any failure."""
        try:
            if self._path.exists():
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            self._data = {}
        return self._data

    def save(self, data: dict[str, Any]) -> None:
        """Persist session data.  Silently ignores write failures."""
        self._data = data
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    @property
    def data(self) -> dict[str, Any]:
        return self._data


# ---------------------------------------------------------------------------
# JSON syntax highlighting helpers
# ---------------------------------------------------------------------------

# Simple regex token patterns for JSON coloring
_JSON_PATTERNS: list[tuple[str, str]] = [
    ("json_key", r'"[^"\\]*(?:\\.[^"\\]*)*"\s*:'),
    ("json_string", r'"[^"\\]*(?:\\.[^"\\]*)*"'),
    ("json_number", r"-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b"),
    ("json_bool", r"\b(?:true|false)\b"),
    ("json_null", r"\bnull\b"),
]

# Dark-theme colors for syntax tokens
_JSON_COLORS: dict[str, str] = {
    "json_key": "#9CDCFE",  # light blue
    "json_string": "#CE9178",  # orange
    "json_number": "#B5CEA8",  # light green
    "json_bool": "#569CD6",  # blue
    "json_null": "#808080",  # grey
}

_JSON_RE = re.compile("|".join(f"(?P<{n}>{p})" for n, p in _JSON_PATTERNS))


def _apply_json_highlighting(textbox: ctk.CTkTextbox, text: str) -> None:
    """Apply tag-based syntax coloring to *textbox* containing *text*."""
    inner = textbox._textbox
    for tag_name, color in _JSON_COLORS.items():
        inner.tag_configure(tag_name, foreground=color)
    for match in _JSON_RE.finditer(text):
        tag = match.lastgroup
        if tag is None:
            continue
        start_idx = f"1.0+{match.start()}c"
        end_idx = f"1.0+{match.end()}c"
        inner.tag_add(tag, start_idx, end_idx)


# ---------------------------------------------------------------------------
# Reusable widget groups
# ---------------------------------------------------------------------------


class TargetInputGroup(ctk.CTkFrame):
    """Shared target-selection widget group (path, type radios, recursive).

    Each operation tab gets its own independent instance.
    """

    def __init__(self, master: ctk.CTkFrame, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._build_widgets()

    def _build_widgets(self) -> None:
        # Path row
        path_frame = ctk.CTkFrame(self, fg_color="transparent")
        path_frame.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(path_frame, text="Target Path:").pack(side="left", padx=(0, 6))
        self.path_entry = ctk.CTkEntry(path_frame, placeholder_text="Select a file or folder...")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.browse_btn = ctk.CTkButton(
            path_frame, text="Browse", width=80, command=self._browse
        )
        self.browse_btn.pack(side="right")

        # Options row
        opts_frame = ctk.CTkFrame(self, fg_color="transparent")
        opts_frame.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(opts_frame, text="Type:").pack(side="left", padx=(0, 6))
        self.type_var = ctk.StringVar(value="auto")
        for label, val in [("Auto", "auto"), ("File", "file"), ("Directory", "directory")]:
            ctk.CTkRadioButton(opts_frame, text=label, variable=self.type_var, value=val).pack(
                side="left", padx=(0, 10)
            )

        self.recursive_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts_frame, text="Recursive", variable=self.recursive_var
        ).pack(side="left", padx=(20, 0))

    def _browse(self) -> None:
        target_type = self.type_var.get()
        if target_type == "directory":
            path = filedialog.askdirectory(title="Select Directory")
        else:
            path = filedialog.askopenfilename(title="Select File")
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)

    def get_path(self) -> str:
        return self.path_entry.get().strip()

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.path_entry.configure(state=state)
        self.browse_btn.configure(state=state)

    def get_state(self) -> dict[str, Any]:
        return {
            "path": self.get_path(),
            "type": self.type_var.get(),
            "recursive": self.recursive_var.get(),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        if "path" in state:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, state["path"])
        if "type" in state:
            self.type_var.set(state["type"])
        if "recursive" in state:
            self.recursive_var.set(state["recursive"])


# ---------------------------------------------------------------------------
# Output panel
# ---------------------------------------------------------------------------


class OutputPanel(ctk.CTkFrame):
    """Shared output panel with JSON/Log toggle, Copy, and Save buttons."""

    def __init__(self, master: ctk.CTkFrame, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._json_text = ""
        self._log_lines: list[str] = []
        self._showing_json = True
        self._build_widgets()

    def _build_widgets(self) -> None:
        # Toolbar
        toolbar = ctk.CTkFrame(self, fg_color="transparent", height=32)
        toolbar.pack(fill="x", pady=(0, 4))

        self.output_btn = ctk.CTkButton(
            toolbar, text="Output", width=80, command=self._show_json
        )
        self.output_btn.pack(side="left", padx=(0, 4))
        self.log_btn = ctk.CTkButton(
            toolbar, text="Log", width=60, command=self._show_log,
            fg_color="transparent", text_color=("gray50", "gray70"),
        )
        self.log_btn.pack(side="left", padx=(0, 16))

        self.copy_btn = ctk.CTkButton(
            toolbar, text="Copy", width=60, command=self._copy, state="disabled"
        )
        self.copy_btn.pack(side="right", padx=(4, 0))
        self.save_btn = ctk.CTkButton(
            toolbar, text="Save", width=60, command=self._save, state="disabled"
        )
        self.save_btn.pack(side="right", padx=(4, 0))

        # Text display
        self.textbox = ctk.CTkTextbox(
            self, state="disabled", wrap="none",
            font=ctk.CTkFont(family=_MONOSPACE_FONTS[0], size=12),
        )
        self.textbox.pack(fill="both", expand=True)

    def set_json(self, text: str) -> None:
        """Set the JSON result text and switch to output view."""
        self._json_text = text
        self._showing_json = True
        self._refresh_view()
        state = "normal" if text else "disabled"
        self.copy_btn.configure(state=state)
        self.save_btn.configure(state=state)

    def append_log(self, line: str) -> None:
        """Append a line to the log buffer.  If log view active, update."""
        self._log_lines.append(line)
        if not self._showing_json:
            self.textbox.configure(state="normal")
            self.textbox.insert("end", line + "\n")
            self.textbox.see("end")
            self.textbox.configure(state="disabled")

    def clear(self) -> None:
        """Clear both JSON and log content."""
        self._json_text = ""
        self._log_lines.clear()
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
        self.copy_btn.configure(state="disabled")
        self.save_btn.configure(state="disabled")

    def _show_json(self) -> None:
        self._showing_json = True
        self._update_toggle_style()
        self._refresh_view()

    def _show_log(self) -> None:
        self._showing_json = False
        self._update_toggle_style()
        self._refresh_view()

    def _update_toggle_style(self) -> None:
        if self._showing_json:
            self.output_btn.configure(
                fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
                text_color=ctk.ThemeManager.theme["CTkButton"]["text_color"],
            )
            self.log_btn.configure(
                fg_color="transparent", text_color=("gray50", "gray70")
            )
        else:
            self.log_btn.configure(
                fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
                text_color=ctk.ThemeManager.theme["CTkButton"]["text_color"],
            )
            self.output_btn.configure(
                fg_color="transparent", text_color=("gray50", "gray70")
            )

    def _refresh_view(self) -> None:
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        if self._showing_json:
            text = self._json_text
            size = len(text.encode("utf-8", errors="replace"))
            if size > _DISPLAY_LIMIT:
                self.textbox.insert(
                    "1.0",
                    f"Output is {size / 1_000_000:.1f} MB — too large to display.\n"
                    "Use the Save button to export.",
                )
            else:
                self.textbox.insert("1.0", text)
                if text and size <= _HIGHLIGHT_LIMIT:
                    with contextlib.suppress(Exception):
                        _apply_json_highlighting(self.textbox, text)
        else:
            self.textbox.insert("1.0", "\n".join(self._log_lines))
            self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def _copy(self) -> None:
        text = self._json_text if self._showing_json else "\n".join(self._log_lines)
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)

    def _save(self) -> None:
        if not self._json_text:
            return
        path = filedialog.asksaveasfilename(
            title="Save JSON Output",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            try:
                Path(path).write_text(self._json_text + "\n", encoding="utf-8")
                self._show_toast(f"Saved to {Path(path).name}")
            except OSError as exc:
                messagebox.showerror("Save Error", str(exc))

    def _show_toast(self, message: str) -> None:
        """Display a brief toast notification at the bottom of the output."""
        toast = ctk.CTkLabel(
            self, text=f"  {message}  ",
            fg_color=("green", "#2d5a2d"), corner_radius=6,
        )
        toast.place(relx=0.5, rely=0.95, anchor="center")
        self.after(_TOAST_DURATION_MS, toast.destroy)


# ---------------------------------------------------------------------------
# Progress panel
# ---------------------------------------------------------------------------


class ProgressPanel(ctk.CTkFrame):
    """Progress display shown during background indexing execution."""

    def __init__(self, master: ctk.CTkFrame, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._start_time: float = 0.0
        self._build_widgets()

    def _build_widgets(self) -> None:
        # Status labels
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(fill="x", pady=(0, 6))

        self.status_label = ctk.CTkLabel(info_frame, text="Preparing...", anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)
        self.elapsed_label = ctk.CTkLabel(info_frame, text="0:00", anchor="e", width=60)
        self.elapsed_label.pack(side="right")

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.pack(fill="x", pady=(0, 4))
        self.progress_bar.set(0)

        # Current item label
        self.current_label = ctk.CTkLabel(
            self, text="", anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        )
        self.current_label.pack(fill="x", pady=(0, 6))

        # Log stream
        self.log_text = ctk.CTkTextbox(
            self, state="disabled", wrap="word", height=100,
            font=ctk.CTkFont(family=_MONOSPACE_FONTS[0], size=11),
        )
        self.log_text.pack(fill="both", expand=True)

    def start(self) -> None:
        """Reset and start the progress display."""
        self._start_time = time.monotonic()
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.status_label.configure(text="Discovering items...")
        self.current_label.configure(text="")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def update_progress(self, event: ProgressEvent) -> None:
        """Handle a ProgressEvent from the background thread."""
        # Update elapsed time
        elapsed = time.monotonic() - self._start_time
        mins, secs = divmod(int(elapsed), 60)
        self.elapsed_label.configure(text=f"{mins}:{secs:02d}")

        # Update phase / progress bar
        if event.phase == "discovery":
            self.progress_bar.configure(mode="indeterminate")
            self.status_label.configure(text="Discovering items...")
        elif event.items_total and event.items_total > 0:
            # Switch to determinate mode
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            fraction = event.items_completed / event.items_total
            self.progress_bar.set(fraction)
            pct = int(fraction * 100)
            self.status_label.configure(
                text=f"Processing: {event.items_completed}/{event.items_total} ({pct}%)"
            )

        # Update current path
        if event.current_path is not None:
            display_path = str(event.current_path)
            if len(display_path) > 80:
                display_path = "..." + display_path[-77:]
            self.current_label.configure(text=display_path)

        # Append log message
        if event.message:
            self.log_text.configure(state="normal")
            self.log_text.insert("end", event.message + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

    def stop(self) -> None:
        """Stop progress animation."""
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(1.0)
        elapsed = time.monotonic() - self._start_time
        mins, secs = divmod(int(elapsed), 60)
        self.elapsed_label.configure(text=f"{mins}:{secs:02d}")


# ---------------------------------------------------------------------------
# Operation tabs
# ---------------------------------------------------------------------------


class _BaseOperationTab(ctk.CTkFrame):
    """Abstract base for the four operation tabs.

    Subclasses implement ``_build_options`` and ``_get_config_overrides`` to
    define tab-specific controls and configuration.
    """

    _action_label: str = "▶ Run"
    _action_label_running: str = "■ Cancel"

    def __init__(
        self,
        master: ctk.CTkFrame,
        app: ShruggiIndexerApp,
        tab_id: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._app = app
        self._tab_id = tab_id
        self._build_widgets()

    def _build_widgets(self) -> None:
        # Header
        ctk.CTkLabel(
            self, text=_TAB_LABELS[self._tab_id].replace("\n", " "),
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 12))

        # Target input
        self.target_input = TargetInputGroup(self)
        self.target_input.pack(fill="x", pady=(0, 8))

        # Tab-specific options
        self.options_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.options_frame.pack(fill="x", pady=(0, 12))
        self._build_options(self.options_frame)

        # Action button
        self.action_btn = ctk.CTkButton(
            self, text=self._action_label, height=36,
            font=ctk.CTkFont(size=14), command=self._on_action,
        )
        self.action_btn.pack(fill="x", pady=(0, 8))

    def _build_options(self, frame: ctk.CTkFrame) -> None:
        """Override in subclass to add tab-specific option controls."""

    def _get_config_overrides(self) -> dict[str, Any]:
        """Override in subclass to return config override dict."""
        return {}

    def _on_action(self) -> None:
        """Handle action button click — delegates to the app."""
        if self._app.is_running:
            self._app.request_cancel()
        else:
            self._app.run_operation(self)

    def build_config(self, base: IndexerConfig) -> IndexerConfig:
        """Construct the final IndexerConfig for this tab's operation."""
        target_state = self.target_input.get_state()
        overrides: dict[str, Any] = {
            "recursive": target_state["recursive"],
        }
        overrides.update(self._get_config_overrides())
        return replace(base, **overrides)

    def get_target_path(self) -> str:
        return self.target_input.get_path()

    def set_running(self, running: bool) -> None:
        """Toggle visual state between idle and running."""
        self.target_input.set_enabled(not running)
        if running:
            self.action_btn.configure(
                text=self._action_label_running,
                fg_color=("#cc3333", "#cc3333"),
            )
        else:
            self.action_btn.configure(
                text=self._action_label,
                fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
            )

    def get_state(self) -> dict[str, Any]:
        """Serialize tab state for session persistence."""
        return {"target": self.target_input.get_state()}

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore tab state from session data."""
        if "target" in state:
            self.target_input.restore_state(state["target"])


class IndexTab(_BaseOperationTab):
    """Index tab — basic filesystem indexing."""

    _action_label = "▶ Run Index"

    def _build_options(self, frame: ctk.CTkFrame) -> None:
        row1 = ctk.CTkFrame(frame, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(row1, text="ID Algorithm:").pack(side="left", padx=(0, 6))
        self.id_algo_var = ctk.StringVar(value="md5")
        self.id_algo_combo = ctk.CTkComboBox(
            row1, values=["md5", "sha256"], variable=self.id_algo_var, width=120
        )
        self.id_algo_combo.pack(side="left", padx=(0, 20))

        self.exif_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row1, text="Extract EXIF", variable=self.exif_var).pack(
            side="left", padx=(0, 20)
        )

        self.sha512_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row1, text="Compute SHA-512", variable=self.sha512_var).pack(
            side="left"
        )

        row2 = ctk.CTkFrame(frame, fg_color="transparent")
        row2.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(row2, text="Output:").pack(side="left", padx=(0, 6))
        self.output_mode_var = ctk.StringVar(value="view")
        for label, val in [("View only", "view"), ("Save to file", "save"), ("Both", "both")]:
            ctk.CTkRadioButton(
                row2, text=label, variable=self.output_mode_var, value=val
            ).pack(side="left", padx=(0, 10))

    def _get_config_overrides(self) -> dict[str, Any]:
        overrides: dict[str, Any] = {
            "id_algorithm": self.id_algo_var.get(),
            "compute_sha512": self.sha512_var.get(),
            "extract_exif": self.exif_var.get(),
            "output_stdout": False,
            "output_file": None,
            "output_inplace": False,
        }
        mode = self.output_mode_var.get()
        if mode in ("save", "both"):
            path = filedialog.asksaveasfilename(
                title="Save Index Output",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if path:
                overrides["output_file"] = Path(path)
        return overrides

    def get_state(self) -> dict[str, Any]:
        state = super().get_state()
        state["id_algorithm"] = self.id_algo_var.get()
        state["extract_exif"] = self.exif_var.get()
        state["sha512"] = self.sha512_var.get()
        state["output_mode"] = self.output_mode_var.get()
        return state

    def restore_state(self, state: dict[str, Any]) -> None:
        super().restore_state(state)
        if "id_algorithm" in state:
            self.id_algo_var.set(state["id_algorithm"])
        if "extract_exif" in state:
            self.exif_var.set(state["extract_exif"])
        if "sha512" in state:
            self.sha512_var.set(state["sha512"])
        if "output_mode" in state:
            self.output_mode_var.set(state["output_mode"])


class MetaMergeTab(_BaseOperationTab):
    """Meta Merge tab — index with metadata sidecar merging."""

    _action_label = "▶ Run Meta Merge"

    def _build_options(self, frame: ctk.CTkFrame) -> None:
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(row, text="ID Algorithm:").pack(side="left", padx=(0, 6))
        self.id_algo_var = ctk.StringVar(value="md5")
        self.id_algo_combo = ctk.CTkComboBox(
            row, values=["md5", "sha256"], variable=self.id_algo_var, width=120
        )
        self.id_algo_combo.pack(side="left", padx=(0, 20))

        self.sha512_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row, text="Compute SHA-512", variable=self.sha512_var).pack(
            side="left", padx=(0, 20)
        )

        row2 = ctk.CTkFrame(frame, fg_color="transparent")
        row2.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(row2, text="Output:").pack(side="left", padx=(0, 6))
        self.output_mode_var = ctk.StringVar(value="view")
        for label, val in [("View only", "view"), ("Save to file", "save"), ("Both", "both")]:
            ctk.CTkRadioButton(
                row2, text=label, variable=self.output_mode_var, value=val
            ).pack(side="left", padx=(0, 10))

    def _get_config_overrides(self) -> dict[str, Any]:
        overrides: dict[str, Any] = {
            "id_algorithm": self.id_algo_var.get(),
            "compute_sha512": self.sha512_var.get(),
            "extract_exif": True,
            "meta_merge": True,
            "output_stdout": False,
            "output_file": None,
            "output_inplace": False,
        }
        mode = self.output_mode_var.get()
        if mode in ("save", "both"):
            path = filedialog.asksaveasfilename(
                title="Save Meta Merge Output",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if path:
                overrides["output_file"] = Path(path)
        return overrides

    def get_state(self) -> dict[str, Any]:
        state = super().get_state()
        state["id_algorithm"] = self.id_algo_var.get()
        state["sha512"] = self.sha512_var.get()
        state["output_mode"] = self.output_mode_var.get()
        return state

    def restore_state(self, state: dict[str, Any]) -> None:
        super().restore_state(state)
        if "id_algorithm" in state:
            self.id_algo_var.set(state["id_algorithm"])
        if "sha512" in state:
            self.sha512_var.set(state["sha512"])
        if "output_mode" in state:
            self.output_mode_var.set(state["output_mode"])


class MetaMergeDeleteTab(_BaseOperationTab):
    """Meta Merge Delete tab — merge + delete sidecars after indexing."""

    _action_label = "▶ Run Meta Merge Delete"

    def _build_options(self, frame: ctk.CTkFrame) -> None:
        row1 = ctk.CTkFrame(frame, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(row1, text="ID Algorithm:").pack(side="left", padx=(0, 6))
        self.id_algo_var = ctk.StringVar(value="md5")
        self.id_algo_combo = ctk.CTkComboBox(
            row1, values=["md5", "sha256"], variable=self.id_algo_var, width=120
        )
        self.id_algo_combo.pack(side="left", padx=(0, 20))

        self.sha512_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row1, text="Compute SHA-512", variable=self.sha512_var).pack(
            side="left"
        )

        # Output file (mandatory)
        row2 = ctk.CTkFrame(frame, fg_color="transparent")
        row2.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(row2, text="Output File:").pack(side="left", padx=(0, 6))
        self.outfile_entry = ctk.CTkEntry(
            row2, placeholder_text="Required: output file path"
        )
        self.outfile_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            row2, text="Browse", width=80, command=self._browse_outfile
        ).pack(side="right")

        # In-place sidecar checkbox
        row3 = ctk.CTkFrame(frame, fg_color="transparent")
        row3.pack(fill="x", pady=(4, 0))

        self.inplace_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            row3, text="Write in-place sidecar files", variable=self.inplace_var
        ).pack(side="left")

        # Warning
        self.warning_label = ctk.CTkLabel(
            frame,
            text="⚠ WARNING: This operation will DELETE matched sidecar files after merging.",
            text_color=("#cc8800", "#ffaa00"),
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        )
        self.warning_label.pack(fill="x", pady=(8, 0))

    def _browse_outfile(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Meta Merge Delete Output",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.outfile_entry.delete(0, "end")
            self.outfile_entry.insert(0, path)

    def _get_config_overrides(self) -> dict[str, Any]:
        outfile = self.outfile_entry.get().strip()
        return {
            "id_algorithm": self.id_algo_var.get(),
            "compute_sha512": self.sha512_var.get(),
            "extract_exif": True,
            "meta_merge": True,
            "meta_merge_delete": True,
            "output_stdout": False,
            "output_file": Path(outfile) if outfile else None,
            "output_inplace": self.inplace_var.get(),
        }

    def validate(self) -> str | None:
        """Return error message if invalid, else None."""
        if not self.outfile_entry.get().strip():
            return "Meta Merge Delete requires an output file path."
        return None

    def get_state(self) -> dict[str, Any]:
        state = super().get_state()
        state["id_algorithm"] = self.id_algo_var.get()
        state["sha512"] = self.sha512_var.get()
        state["outfile"] = self.outfile_entry.get()
        state["inplace"] = self.inplace_var.get()
        return state

    def restore_state(self, state: dict[str, Any]) -> None:
        super().restore_state(state)
        if "id_algorithm" in state:
            self.id_algo_var.set(state["id_algorithm"])
        if "sha512" in state:
            self.sha512_var.set(state["sha512"])
        if "outfile" in state:
            self.outfile_entry.delete(0, "end")
            self.outfile_entry.insert(0, state["outfile"])
        if "inplace" in state:
            self.inplace_var.set(state["inplace"])


class RenameTab(_BaseOperationTab):
    """Rename tab — hash-based file renaming with dry-run support."""

    _action_label = "▶ Preview Renames"

    def _build_options(self, frame: ctk.CTkFrame) -> None:
        row1 = ctk.CTkFrame(frame, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(row1, text="ID Algorithm:").pack(side="left", padx=(0, 6))
        self.id_algo_var = ctk.StringVar(value="md5")
        self.id_algo_combo = ctk.CTkComboBox(
            row1, values=["md5", "sha256"], variable=self.id_algo_var, width=120
        )
        self.id_algo_combo.pack(side="left", padx=(0, 20))

        self.sha512_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row1, text="Compute SHA-512", variable=self.sha512_var).pack(
            side="left"
        )

        # Dry-run checkbox (default CHECKED)
        row2 = ctk.CTkFrame(frame, fg_color="transparent")
        row2.pack(fill="x", pady=(4, 0))

        self.dry_run_var = ctk.BooleanVar(value=True)
        self.dry_run_cb = ctk.CTkCheckBox(
            row2, text="Dry run (preview only)", variable=self.dry_run_var,
            command=self._on_dry_run_changed,
        )
        self.dry_run_cb.pack(side="left")

        # Warning shown when dry-run is unchecked
        self.warning_label = ctk.CTkLabel(
            frame,
            text="⚠ WARNING: Files will be renamed on disk. This cannot be undone.",
            text_color=("#cc3333", "#ff4444"),
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        )
        # Hidden by default (dry_run starts checked)

    def _on_dry_run_changed(self) -> None:
        if self.dry_run_var.get():
            self.warning_label.pack_forget()
            self.action_btn.configure(text="▶ Preview Renames")
        else:
            self.warning_label.pack(fill="x", pady=(8, 0))
            self.action_btn.configure(text="▶ Run Rename")

    def _get_config_overrides(self) -> dict[str, Any]:
        return {
            "id_algorithm": self.id_algo_var.get(),
            "compute_sha512": self.sha512_var.get(),
            "rename": True,
            "dry_run": self.dry_run_var.get(),
            "output_stdout": False,
            "output_file": None,
            "output_inplace": True,
        }

    def get_state(self) -> dict[str, Any]:
        state = super().get_state()
        state["id_algorithm"] = self.id_algo_var.get()
        state["sha512"] = self.sha512_var.get()
        state["dry_run"] = self.dry_run_var.get()
        return state

    def restore_state(self, state: dict[str, Any]) -> None:
        super().restore_state(state)
        if "id_algorithm" in state:
            self.id_algo_var.set(state["id_algorithm"])
        if "sha512" in state:
            self.sha512_var.set(state["sha512"])
        if "dry_run" in state:
            self.dry_run_var.set(state["dry_run"])
            self._on_dry_run_changed()


# ---------------------------------------------------------------------------
# Settings tab
# ---------------------------------------------------------------------------


class SettingsTab(ctk.CTkFrame):
    """Settings tab — defaults, output prefs, logging, config, about."""

    def __init__(
        self,
        master: ctk.CTkFrame,
        app: ShruggiIndexerApp,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._app = app
        self._build_widgets()

    def _build_widgets(self) -> None:
        ctk.CTkLabel(
            self, text="Settings",
            font=ctk.CTkFont(size=18, weight="bold"), anchor="w",
        ).pack(fill="x", pady=(0, 16))

        # Scrollable container for settings sections
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # ── Indexing Defaults ──────────────────────────────────────────
        self._section_header(scroll, "Indexing Defaults")

        row = ctk.CTkFrame(scroll, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row, text="Default ID Algorithm:").pack(side="left", padx=(0, 6))
        self.id_algo_var = ctk.StringVar(value="md5")
        ctk.CTkComboBox(
            row, values=["md5", "sha256"], variable=self.id_algo_var, width=120
        ).pack(side="left")

        self.sha512_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            scroll, text="Compute SHA-512 by default", variable=self.sha512_var
        ).pack(fill="x", pady=(0, 8))

        # ── Output Preferences ─────────────────────────────────────────
        self._section_header(scroll, "Output Preferences")

        row2 = ctk.CTkFrame(scroll, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row2, text="JSON Indentation:").pack(side="left", padx=(0, 6))
        self.indent_var = ctk.StringVar(value="2")
        for label, val in [("2 spaces", "2"), ("4 spaces", "4"), ("Compact", "none")]:
            ctk.CTkRadioButton(
                row2, text=label, variable=self.indent_var, value=val
            ).pack(side="left", padx=(0, 10))

        # ── Logging ────────────────────────────────────────────────────
        self._section_header(scroll, "Logging")

        row3 = ctk.CTkFrame(scroll, fg_color="transparent")
        row3.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row3, text="Verbosity:").pack(side="left", padx=(0, 6))
        self.verbosity_var = ctk.StringVar(value="normal")
        for label, val in [("Normal", "normal"), ("Verbose", "verbose"), ("Debug", "debug")]:
            ctk.CTkRadioButton(
                row3, text=label, variable=self.verbosity_var, value=val
            ).pack(side="left", padx=(0, 10))

        # ── Configuration ──────────────────────────────────────────────
        self._section_header(scroll, "Configuration")

        row4 = ctk.CTkFrame(scroll, fg_color="transparent")
        row4.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row4, text="Config File:").pack(side="left", padx=(0, 6))
        self.config_entry = ctk.CTkEntry(
            row4, placeholder_text="Optional TOML config path"
        )
        self.config_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            row4, text="Browse", width=80, command=self._browse_config
        ).pack(side="right")

        # Utility buttons
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(8, 8))
        ctk.CTkButton(
            btn_frame, text="Reset to Defaults", width=140,
            command=self._reset_defaults,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            btn_frame, text="Open Config Folder", width=140,
            command=self._open_config_folder,
        ).pack(side="left")

        # ── About ──────────────────────────────────────────────────────
        self._section_header(scroll, "About")

        about_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        about_frame.pack(fill="x", pady=(0, 8))

        self._about_label(about_frame, "Version:", __version__)
        self._about_label(
            about_frame, "Python:",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
        exiftool_status = "Available" if shutil.which("exiftool") else "Not found"
        self._about_label(about_frame, "ExifTool:", exiftool_status)

    @staticmethod
    def _section_header(parent: ctk.CTkFrame | ctk.CTkScrollableFrame, text: str) -> None:
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w",
        ).pack(fill="x", pady=(12, 4))

    @staticmethod
    def _about_label(parent: ctk.CTkFrame, label: str, value: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(row, text=label, anchor="w", width=80).pack(side="left")
        ctk.CTkLabel(row, text=value, anchor="w", text_color=("gray40", "gray60")).pack(
            side="left"
        )

    def _browse_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Configuration File",
            filetypes=[("TOML files", "*.toml"), ("All files", "*.*")],
        )
        if path:
            self.config_entry.delete(0, "end")
            self.config_entry.insert(0, path)

    def _reset_defaults(self) -> None:
        if messagebox.askyesno(
            "Reset Settings",
            "Reset all settings to their default values?",
        ):
            self.id_algo_var.set("md5")
            self.sha512_var.set(False)
            self.indent_var.set("2")
            self.verbosity_var.set("normal")
            self.config_entry.delete(0, "end")

    def _open_config_folder(self) -> None:
        session_path = SessionManager._resolve_path()
        folder = session_path.parent
        folder.mkdir(parents=True, exist_ok=True)
        if platform.system() == "Windows":
            os.startfile(folder)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def get_state(self) -> dict[str, Any]:
        return {
            "id_algorithm": self.id_algo_var.get(),
            "sha512": self.sha512_var.get(),
            "indent": self.indent_var.get(),
            "verbosity": self.verbosity_var.get(),
            "config_file": self.config_entry.get(),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        if "id_algorithm" in state:
            self.id_algo_var.set(state["id_algorithm"])
        if "sha512" in state:
            self.sha512_var.set(state["sha512"])
        if "indent" in state:
            self.indent_var.set(state["indent"])
        if "verbosity" in state:
            self.verbosity_var.set(state["verbosity"])
        if "config_file" in state:
            self.config_entry.delete(0, "end")
            self.config_entry.insert(0, state["config_file"])


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------


class ShruggiIndexerApp(ctk.CTk):
    """Shruggie Indexer — CustomTkinter dark-theme desktop application.

    Provides a visual frontend to the ``shruggie_indexer`` library with four
    operation tabs (Index, Meta Merge, Meta Merge Delete, Rename) and a
    Settings panel.  See spec sections 10.1-10.7 for full requirements.
    """

    def __init__(self) -> None:
        super().__init__()

        # State
        self._job_running = False
        self._cancel_event = threading.Event()
        self._result_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._active_tab_id: str = _TAB_INDEX
        self._tabs: dict[str, _BaseOperationTab | SettingsTab] = {}
        self._sidebar_buttons: dict[str, ctk.CTkButton] = {}
        self._session = SessionManager()

        # Window setup
        self.title(_WINDOW_TITLE)
        self.geometry(_DEFAULT_GEOMETRY)
        self.minsize(_MIN_WIDTH, _MIN_HEIGHT)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._build_layout()
        self._bind_shortcuts()
        self._restore_session()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- Layout construction ------------------------------------------------

    def _build_layout(self) -> None:
        # Sidebar
        self._sidebar = ctk.CTkFrame(self, width=_SIDEBAR_WIDTH, corner_radius=0)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        # App branding
        ctk.CTkLabel(
            self._sidebar, text="¯\\_(ツ)_/¯",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(16, 4))
        ctk.CTkLabel(
            self._sidebar, text="Indexer",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).pack(pady=(0, 16))

        # Operation tab buttons
        for tab_id in _OPERATION_TABS:
            btn = ctk.CTkButton(
                self._sidebar,
                text=_TAB_LABELS[tab_id],
                width=_SIDEBAR_WIDTH - 16,
                height=36,
                corner_radius=6,
                command=lambda t=tab_id: self._switch_tab(t),
                fg_color="transparent",
                text_color=("gray10", "gray90"),
            )
            btn.pack(pady=2, padx=8)
            self._sidebar_buttons[tab_id] = btn

        # Separator
        sep = ctk.CTkFrame(self._sidebar, height=1, fg_color=("gray70", "gray30"))
        sep.pack(fill="x", padx=12, pady=12)

        # Settings button
        settings_btn = ctk.CTkButton(
            self._sidebar,
            text=_TAB_LABELS[_TAB_SETTINGS],
            width=_SIDEBAR_WIDTH - 16,
            height=36,
            corner_radius=6,
            command=lambda: self._switch_tab(_TAB_SETTINGS),
            fg_color="transparent",
            text_color=("gray10", "gray90"),
        )
        settings_btn.pack(pady=2, padx=8)
        self._sidebar_buttons[_TAB_SETTINGS] = settings_btn

        # Main area
        self._main_area = ctk.CTkFrame(self, fg_color="transparent")
        self._main_area.pack(side="right", fill="both", expand=True, padx=16, pady=16)

        # Tab content container
        self._tab_container = ctk.CTkFrame(self._main_area, fg_color="transparent")
        self._tab_container.pack(fill="both", expand=True)

        # Create operation tabs
        self._tabs[_TAB_INDEX] = IndexTab(self._tab_container, app=self, tab_id=_TAB_INDEX)
        self._tabs[_TAB_META_MERGE] = MetaMergeTab(
            self._tab_container, app=self, tab_id=_TAB_META_MERGE
        )
        self._tabs[_TAB_META_MERGE_DELETE] = MetaMergeDeleteTab(
            self._tab_container, app=self, tab_id=_TAB_META_MERGE_DELETE
        )
        self._tabs[_TAB_RENAME] = RenameTab(self._tab_container, app=self, tab_id=_TAB_RENAME)
        self._tabs[_TAB_SETTINGS] = SettingsTab(self._tab_container, app=self)

        # Shared output panel (below tabs for operation tabs)
        self._output_panel = OutputPanel(self._main_area)

        # Progress panel (replaces output during execution)
        self._progress_panel = ProgressPanel(self._main_area)

        # Show the default tab
        self._switch_tab(_TAB_INDEX)

    def _switch_tab(self, tab_id: str) -> None:
        """Show the specified tab and update sidebar highlighting."""
        # Don't switch during a running operation to other tabs
        # (settings is always accessible)
        if self._job_running and tab_id != _TAB_SETTINGS and tab_id != self._active_tab_id:
            return

        # Hide all tabs
        for tab in self._tabs.values():
            tab.pack_forget()

        # Update sidebar button styles
        for tid, btn in self._sidebar_buttons.items():
            if tid == tab_id:
                btn.configure(
                    fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
                    text_color=ctk.ThemeManager.theme["CTkButton"]["text_color"],
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=("gray10", "gray90"),
                )

        # Show selected tab
        self._tabs[tab_id].pack(fill="both", expand=True)
        self._active_tab_id = tab_id

        # Show/hide output panel (settings has no output)
        if tab_id == _TAB_SETTINGS:
            self._output_panel.pack_forget()
            self._progress_panel.pack_forget()
        elif not self._job_running:
            self._progress_panel.pack_forget()
            self._output_panel.pack(fill="both", expand=True, pady=(12, 0))

    # -- Keyboard shortcuts -------------------------------------------------

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-r>", lambda _: self._shortcut_run())
        self.bind("<Control-R>", lambda _: self._shortcut_run())
        self.bind("<Control-s>", lambda _: self._output_panel._save())
        self.bind("<Control-S>", lambda _: self._output_panel._save())
        # Ctrl+C for copy output (only when not in a text entry)
        self.bind("<Control-Shift-C>", lambda _: self._output_panel._copy())
        self.bind("<Control-period>", lambda _: self.request_cancel())
        self.bind("<Escape>", lambda _: self.request_cancel())
        self.bind("<Control-q>", lambda _: self._on_close())
        self.bind("<Control-Q>", lambda _: self._on_close())
        self.bind("<Control-comma>", lambda _: self._switch_tab(_TAB_SETTINGS))

        # Tab switching: Ctrl+1 through Ctrl+4
        for i, tab_id in enumerate(_OPERATION_TABS):
            self.bind(f"<Control-Key-{i + 1}>", lambda _, t=tab_id: self._switch_tab(t))

    def _shortcut_run(self) -> None:
        """Ctrl+R — run the currently active operation tab."""
        if self._active_tab_id in _OPERATION_TABS and not self._job_running:
            tab = self._tabs[self._active_tab_id]
            if isinstance(tab, _BaseOperationTab):
                self.run_operation(tab)

    # -- Job execution ------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._job_running

    def run_operation(self, tab: _BaseOperationTab) -> None:
        """Validate inputs, construct config, and launch the background job."""
        # Validate target path
        target_path_str = tab.get_target_path()
        if not target_path_str:
            messagebox.showwarning("Missing Target", "Please select a target path.")
            return

        target = Path(target_path_str)
        if not target.exists():
            messagebox.showerror("Invalid Target", f"Path does not exist:\n{target}")
            return

        # Tab-specific validation
        if isinstance(tab, MetaMergeDeleteTab):
            err = tab.validate()
            if err:
                messagebox.showwarning("Validation Error", err)
                return

        # Build config
        try:
            base_config = load_config()
            config = tab.build_config(base_config)
        except IndexerError as exc:
            messagebox.showerror("Configuration Error", str(exc))
            return

        # Transition to running state
        self._job_running = True
        self._cancel_event.clear()
        tab.set_running(True)
        self._set_sidebar_enabled(False)

        # Show progress, hide output
        self._output_panel.pack_forget()
        self._output_panel.clear()
        self._progress_panel.pack(fill="both", expand=True, pady=(12, 0))
        self._progress_panel.start()

        # Start background thread
        thread = threading.Thread(
            target=self._background_job,
            args=(target, config),
            daemon=True,
        )
        thread.start()

        # Start polling
        self._poll_results()

    def _background_job(self, target: Path, config: IndexerConfig) -> None:
        """Run the indexing operation in a background thread."""
        result: dict[str, Any] = {"status": "error", "message": "Unknown error"}
        try:
            entry = index_path(
                target,
                config,
                progress_callback=self._on_progress,
                cancel_event=self._cancel_event,
            )
            json_str = serialize_entry(entry)

            # Write output file if configured
            if config.output_file is not None:
                config.output_file.write_text(json_str + "\n", encoding="utf-8")

            result = {"status": "success", "json": json_str}

        except IndexerCancellationError:
            result = {"status": "cancelled", "message": "Operation cancelled by user."}

        except IndexerError as exc:
            result = {"status": "error", "message": str(exc)}

        except Exception as exc:
            result = {"status": "error", "message": f"Unexpected error: {exc}"}

        self._result_queue.put(result)

    def _on_progress(self, event: ProgressEvent) -> None:
        """Progress callback — invoked on the background thread.

        Schedules the update on the main thread via ``after()``.
        """
        self.after(0, lambda: self._handle_progress(event))

    def _handle_progress(self, event: ProgressEvent) -> None:
        """Process a progress event on the main thread."""
        self._progress_panel.update_progress(event)
        if event.message:
            self._output_panel.append_log(event.message)

    def _poll_results(self) -> None:
        """50ms polling loop to check for background job completion."""
        try:
            result = self._result_queue.get_nowait()
        except queue.Empty:
            self.after(_POLL_INTERVAL_MS, self._poll_results)
            return

        # Job complete — schedule transition after delay
        self.after(_COMPLETION_DELAY_MS, lambda: self._on_job_complete(result))

    def _on_job_complete(self, result: dict[str, Any]) -> None:
        """Handle completion of a background job."""
        self._progress_panel.stop()

        status = result.get("status", "error")

        if status == "success":
            self._progress_panel.status_label.configure(
                text="Complete", text_color=("green", "#00cc00")
            )
            json_text = result.get("json", "")
            self._output_panel.set_json(json_text)
        elif status == "cancelled":
            self._progress_panel.status_label.configure(
                text="Cancelled", text_color=("#cc8800", "#ffaa00")
            )
            self._output_panel.append_log(result.get("message", "Cancelled."))
        else:
            self._progress_panel.status_label.configure(
                text="Error", text_color=("#cc3333", "#ff4444")
            )
            self._output_panel.append_log(f"ERROR: {result.get('message', 'Unknown error')}")

        # Restore idle state
        self._job_running = False
        active_tab = self._tabs.get(self._active_tab_id)
        if isinstance(active_tab, _BaseOperationTab):
            active_tab.set_running(False)
        self._set_sidebar_enabled(True)

        # Switch from progress to output
        self._progress_panel.pack_forget()
        self._output_panel.pack(fill="both", expand=True, pady=(12, 0))

        # Save session after operation
        self._save_session()

    def request_cancel(self) -> None:
        """Request cancellation of the running operation."""
        if self._job_running:
            self._cancel_event.set()

    def _set_sidebar_enabled(self, enabled: bool) -> None:
        """Dim sidebar buttons when a job is running."""
        for tab_id, btn in self._sidebar_buttons.items():
            if tab_id == _TAB_SETTINGS:
                continue  # Settings always accessible
            if enabled:
                btn.configure(state="normal")
            else:
                btn.configure(state="disabled")

    # -- Session persistence ------------------------------------------------

    def _save_session(self) -> None:
        data: dict[str, Any] = {
            "geometry": self.geometry(),
            "active_tab": self._active_tab_id,
            "tab_states": {},
            "settings": {},
        }
        for tab_id, tab in self._tabs.items():
            data["tab_states"][tab_id] = tab.get_state()
        settings_tab = self._tabs.get(_TAB_SETTINGS)
        if isinstance(settings_tab, SettingsTab):
            data["settings"] = settings_tab.get_state()
        self._session.save(data)

    def _restore_session(self) -> None:
        data = self._session.load()
        if not data:
            return
        # Restore geometry
        if "geometry" in data:
            with contextlib.suppress(tk.TclError):
                self.geometry(data["geometry"])
        # Restore tab states
        tab_states = data.get("tab_states", {})
        for tab_id, state in tab_states.items():
            tab = self._tabs.get(tab_id)
            if tab is not None:
                tab.restore_state(state)
        # Restore settings
        settings = data.get("settings", {})
        settings_tab = self._tabs.get(_TAB_SETTINGS)
        if isinstance(settings_tab, SettingsTab) and settings:
            settings_tab.restore_state(settings)
        # Restore active tab
        if "active_tab" in data and data["active_tab"] in self._tabs:
            self._switch_tab(data["active_tab"])

    # -- Window close -------------------------------------------------------

    def _on_close(self) -> None:
        """Handle window close — confirm if a job is running."""
        if self._job_running:
            if not messagebox.askyesno(
                "Quit",
                "An operation is running. Do you want to cancel and quit?",
            ):
                return
            self._cancel_event.set()
        self._save_session()
        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Launch the Shruggie Indexer GUI application."""
    app = ShruggiIndexerApp()
    app.mainloop()


if __name__ == "__main__":
    main()

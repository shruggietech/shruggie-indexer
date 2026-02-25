"""Shruggie Indexer — CustomTkinter desktop GUI application.

Thin presentation layer over the ``shruggie_indexer`` public API.  The GUI
constructs an ``IndexerConfig`` via ``load_config()``, calls ``index_path()``,
and formats results via ``serialize_entry()``.  No direct ``core/`` imports —
only the public API surface exposed by ``shruggie_indexer.__init__``.

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
import webbrowser
from dataclasses import replace
from functools import partial
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
    rename_item,
    serialize_entry,
    shutdown_exiftool,
    write_inplace,
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
_SIDEBAR_WIDTH = 160
_POLL_INTERVAL_MS = 50
_TOAST_DURATION_MS = 3000
_COMPLETION_DELAY_MS = 500
_COPY_FEEDBACK_MS = 1500
_TOOLTIP_DELAY_MS = 600
_DEFAULT_OUTPUT_HEIGHT = 250
_MIN_OUTPUT_HEIGHT = 100
_MAX_OUTPUT_HEIGHT = 600

# Fixed height for the progress/action region (SS10.9 Standard 1.3.6).
# Must accommodate the tallest state: status row + progress bar + current
# file label + cancel button, with internal padding.
_PROGRESS_REGION_HEIGHT = 120

# Compact control sizing — controls modestly larger than adjacent label text
_CTRL_HEIGHT = 26
_CB_SIZE = 16
_RB_SIZE = 16

# Output size thresholds (bytes)
_HIGHLIGHT_LIMIT = 1_000_000  # 1 MB
_DISPLAY_LIMIT = 10_000_000  # 10 MB

_MONOSPACE_FONTS = ("JetBrains Mono", "Consolas", "Courier New", "monospace")

# Muted fill colour for checkboxes that are forced on and disabled.
_FORCED_CHECK_FG = ("gray55", "gray45")

# Sidebar tab identifiers
_TAB_OPERATIONS = "operations"
_TAB_SETTINGS = "settings"
_TAB_ABOUT = "about"

# Operation type display labels (used by CTkOptionMenu)
_OP_INDEX = "Index"
_OP_META_MERGE = "Meta Merge"
_OP_META_MERGE_DELETE = "Meta Merge Delete"

_OPERATION_LABELS: list[str] = [
    _OP_INDEX, _OP_META_MERGE, _OP_META_MERGE_DELETE,
]

# Display label <-> internal key for session persistence
_OP_KEY_MAP: dict[str, str] = {
    _OP_INDEX: "index",
    _OP_META_MERGE: "meta_merge",
    _OP_META_MERGE_DELETE: "meta_merge_delete",
}
_OP_LABEL_MAP: dict[str, str] = {v: k for k, v in _OP_KEY_MAP.items()}

# Output mode labels for the new three-mode selector
_OUT_SINGLE = "Single file"
_OUT_MULTI = "Multi-file"
_OUT_VIEW = "View only"
_OUTPUT_MODE_LABELS: list[str] = [_OUT_SINGLE, _OUT_MULTI, _OUT_VIEW]

# Output mode internal key mapping for session persistence
_OUT_KEY_MAP: dict[str, str] = {
    _OUT_SINGLE: "single",
    _OUT_MULTI: "multi",
    _OUT_VIEW: "view",
}
_OUT_LABEL_MAP: dict[str, str] = {v: k for k, v in _OUT_KEY_MAP.items()}

_TAB_LABELS: dict[str, str] = {
    _TAB_OPERATIONS: "Operations",
    _TAB_SETTINGS: "Settings",
    _TAB_ABOUT: "About",
}

_DOCS_URL = "https://shruggietech.github.io/shruggie-indexer/"
_WEBSITE_URL = "https://shruggie.tech"

_ACTION_LABEL_START = "\u25b6  START"
_ACTION_LABEL_RUNNING = "\u25a0  Cancel"

# Compact widget constructors — controls sized modestly larger than labels.
# Explicit ``height``/size kwargs on individual widgets override these defaults.
_CtkCheckBox = partial(ctk.CTkCheckBox, checkbox_width=_CB_SIZE, checkbox_height=_CB_SIZE)
_CtkRadioButton = partial(
    ctk.CTkRadioButton, radiobutton_width=_RB_SIZE, radiobutton_height=_RB_SIZE,
)
_CtkButton = partial(ctk.CTkButton, height=_CTRL_HEIGHT)
_CtkEntry = partial(ctk.CTkEntry, height=_CTRL_HEIGHT)
_CtkComboBox = partial(ctk.CTkComboBox, height=_CTRL_HEIGHT)
_CtkOptionMenu = partial(ctk.CTkOptionMenu, height=_CTRL_HEIGHT)


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------


class SessionManager:
    """Read/write GUI session state to a platform-appropriate JSON file.

    Session stores: window geometry, active tab, operation state, settings,
    and output panel height.  Gracefully falls back to defaults when the
    file is missing or corrupt.
    """

    def __init__(self) -> None:
        self._path = self._resolve_path()
        self._data: dict[str, Any] = {}

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

_JSON_PATTERNS: list[tuple[str, str]] = [
    ("json_key", r'"[^"\\]*(?:\\.[^"\\]*)*"\s*:'),
    ("json_string", r'"[^"\\]*(?:\\.[^"\\]*)*"'),
    ("json_number", r"-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b"),
    ("json_bool", r"\b(?:true|false)\b"),
    ("json_null", r"\bnull\b"),
]

_JSON_COLORS: dict[str, str] = {
    "json_key": "#9CDCFE",
    "json_string": "#CE9178",
    "json_number": "#B5CEA8",
    "json_bool": "#569CD6",
    "json_null": "#808080",
}

_JSON_RE = re.compile("|".join(f"(?P<{n}>{p})" for n, p in _JSON_PATTERNS))


def _apply_json_highlighting(textbox: ctk.CTkTextbox, text: str) -> None:
    """Apply tag-based syntax coloring to *textbox* containing *text*."""
    inner = textbox._textbox  # noqa: SLF001
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
# Tooltip
# ---------------------------------------------------------------------------


class _Tooltip:
    """Hover tooltip for CustomTkinter widgets.

    All instances are tracked so tooltips can be globally enabled/disabled
    via the Settings tab toggle.
    """

    _all_tooltips: list[_Tooltip] = []
    _enabled: bool = True

    def __init__(self, widget: Any, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip_window: tk.Toplevel | None = None
        self._after_id: str | None = None

        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Button-1>", self._on_leave, add="+")

        _Tooltip._all_tooltips.append(self)

    @classmethod
    def set_enabled(cls, enabled: bool) -> None:
        """Globally enable or disable all tooltips."""
        cls._enabled = enabled
        if not enabled:
            for tip in cls._all_tooltips:
                tip._hide()

    def _on_enter(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if not _Tooltip._enabled:
            return
        self._after_id = self._widget.after(_TOOLTIP_DELAY_MS, self._show)

    def _on_leave(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._after_id:
            self._widget.after_cancel(self._after_id)
            self._after_id = None
        self._hide()

    def _show(self) -> None:
        if self._tip_window or not _Tooltip._enabled:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip_window = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw, text=self._text, justify="left",
            background="#333333", foreground="#ffffff",
            relief="solid", borderwidth=1,
            font=("Segoe UI", 9), padx=6, pady=4,
        ).pack()

    def _hide(self) -> None:
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None


# ---------------------------------------------------------------------------
# Labeled group frame
# ---------------------------------------------------------------------------


class _LabeledGroup(ctk.CTkFrame):
    """A frame with a label header, optional description, and content area."""

    def __init__(
        self,
        master: Any,
        label: str,
        description: str = "",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", ("gray75", "gray30"))
        super().__init__(master, **kwargs)

        ctk.CTkLabel(
            self, text=label,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(6, 0))

        if description:
            ctk.CTkLabel(
                self, text=description,
                font=ctk.CTkFont(size=11),
                text_color=("gray40", "gray60"),
                anchor="w",
            ).pack(fill="x", padx=12, pady=(0, 1))

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="x", padx=12, pady=(2, 6))


# ---------------------------------------------------------------------------
# Destructive operation indicator
# ---------------------------------------------------------------------------


class _DestructiveIndicator(ctk.CTkFrame):
    """Small indicator showing whether current config is destructive."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", height=24, **kwargs)

        self._dot = ctk.CTkLabel(self, text="\u25cf", width=16, font=ctk.CTkFont(size=11))
        self._dot.pack(side="left", padx=(0, 4))

        self._label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11))
        self._label.pack(side="left")

        self.set_destructive(False)

    def set_destructive(self, destructive: bool) -> None:
        if destructive:
            self._dot.configure(text_color=("#cc3333", "#ff4444"))
            self._label.configure(
                text="Destructive",
                text_color=("#cc3333", "#ff4444"),
            )
        else:
            self._dot.configure(text_color=("#228822", "#44cc44"))
            self._label.configure(
                text="Non-Destructive",
                text_color=("#228822", "#44cc44"),
            )


# ---------------------------------------------------------------------------
# Drag handle for resizable output panel
# ---------------------------------------------------------------------------


class _DragHandle(ctk.CTkFrame):
    """Thin horizontal bar the user drags to resize the output panel."""

    def __init__(
        self,
        master: Any,
        on_drag: Any,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("height", 6)
        kwargs.setdefault("cursor", "sb_v_double_arrow")
        kwargs.setdefault("fg_color", ("gray75", "gray30"))
        kwargs.setdefault("corner_radius", 2)
        super().__init__(master, **kwargs)

        self._on_drag = on_drag
        self._drag_start_y = 0

        self.bind("<Button-1>", self._start_drag)
        self.bind("<B1-Motion>", self._do_drag)

    def _start_drag(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._drag_start_y = event.y_root

    def _do_drag(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        delta = self._drag_start_y - event.y_root
        self._drag_start_y = event.y_root
        self._on_drag(delta)


# ---------------------------------------------------------------------------
# Auto-scroll frame (conditional scrollbar + scroll isolation)
# ---------------------------------------------------------------------------


class _AutoScrollFrame(ctk.CTkFrame):
    """Scrollable frame that shows a scrollbar only when content overflows.

    Pack child widgets into the ``.content`` frame.  Mousewheel events are
    isolated — scrolling inside this frame does not propagate to any
    surrounding scrollable panel.
    """

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)

        # Resolve background colour for the raw tk Canvas
        mode_idx = 1 if ctk.get_appearance_mode() == "Dark" else 0
        canvas_bg = ctk.ThemeManager.theme["CTk"]["fg_color"][mode_idx]

        self._canvas = tk.Canvas(
            self, highlightthickness=0, borderwidth=0,
            background=canvas_bg, yscrollincrement=1,
        )
        self._scrollbar = ctk.CTkScrollbar(self, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self.content = ctk.CTkFrame(self._canvas, fg_color="transparent")
        self._window_id = self._canvas.create_window(
            (0, 0), window=self.content, anchor="nw",
        )

        self._canvas.pack(side="left", fill="both", expand=True)
        # Scrollbar is NOT packed initially; shown only when needed.

        self.content.bind("<Configure>", self._on_content_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Scroll isolation: capture mousewheel only while pointer is inside.
        self._canvas.bind("<Enter>", self._on_enter)
        self._canvas.bind("<Leave>", self._on_leave)

    # -- geometry callbacks -------------------------------------------------

    def _on_content_configure(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._refresh_scrollbar()

    def _on_canvas_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._canvas.itemconfigure(self._window_id, width=event.width)
        self._refresh_scrollbar()

    def _refresh_scrollbar(self) -> None:
        """Show scrollbar only when content is taller than the viewport."""
        self.update_idletasks()
        if self.content.winfo_reqheight() > self._canvas.winfo_height():
            if not self._scrollbar.winfo_ismapped():
                self._scrollbar.pack(side="right", fill="y")
        else:
            if self._scrollbar.winfo_ismapped():
                self._scrollbar.pack_forget()
            self._canvas.yview_moveto(0)

    # -- scroll isolation ---------------------------------------------------

    def _on_enter(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_leave(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        self._canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event: tk.Event) -> str:  # type: ignore[type-arg]
        if self.content.winfo_reqheight() > self._canvas.winfo_height():
            self._canvas.yview_scroll(int(-event.delta / 4), "units")
        return "break"


# ---------------------------------------------------------------------------
# Queue-based logging handler for GUI
# ---------------------------------------------------------------------------


class _LogQueueHandler(logging.Handler):
    """Logging handler that pushes formatted messages to a queue."""

    def __init__(self, log_queue: queue.Queue[str]) -> None:
        super().__init__()
        self._queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._queue.put_nowait(msg)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Output panel
# ---------------------------------------------------------------------------


class OutputPanel(ctk.CTkFrame):
    """Shared output panel with JSON/Log toggle, Copy, Save, and Clear."""

    # Log level color coding (SS11.5)
    _LOG_COLORS: dict[str, str] = {
        "ERROR": "#ff4444",
        "CRITICAL": "#ff4444",
        "WARNING": "#ffaa00",
        "DEBUG": "#888888",
    }

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._json_text = ""
        self._log_lines: list[str] = []
        self._showing_json = True
        self._auto_scroll = True
        self._build_widgets()

    def _build_widgets(self) -> None:
        # Toolbar
        toolbar = ctk.CTkFrame(self, fg_color="transparent", height=32)
        toolbar.pack(fill="x", pady=(0, 4))

        self.output_btn = _CtkButton(
            toolbar, text="Output", width=80, command=self._show_json,
        )
        self.output_btn.pack(side="left", padx=(0, 4))
        self.log_btn = _CtkButton(
            toolbar, text="Log", width=60, command=self._show_log,
            fg_color="transparent", text_color=("gray50", "gray70"),
        )
        self.log_btn.pack(side="left", padx=(0, 16))

        # Clear button (item 2.7)
        self.clear_btn = _CtkButton(
            toolbar, text="Clear", width=60, command=self.clear,
        )
        self.clear_btn.pack(side="right", padx=(4, 0))
        _Tooltip(self.clear_btn, "Clear both output and log content.")

        self.copy_btn = _CtkButton(
            toolbar, text="Copy", width=60, command=self._copy, state="disabled",
        )
        self.copy_btn.pack(side="right", padx=(4, 0))
        _Tooltip(self.copy_btn, "Copy current view to clipboard.")

        self.save_btn = _CtkButton(
            toolbar, text="Save", width=60, command=self._save, state="disabled",
        )
        self.save_btn.pack(side="right", padx=(4, 0))
        _Tooltip(self.save_btn, "Save current view content to a file.")

        # Text display
        self.textbox = ctk.CTkTextbox(
            self, state="disabled", wrap="none",
            font=ctk.CTkFont(family=_MONOSPACE_FONTS[0], size=12),
        )
        self.textbox.pack(fill="both", expand=True)

        # Configure log-level color tags
        for level, color in self._LOG_COLORS.items():
            self.textbox._textbox.tag_configure(f"log_{level}", foreground=color)

        # Auto-scroll detection: pause when user scrolls up
        self.textbox._textbox.bind("<MouseWheel>", self._on_scroll)
        self.textbox._textbox.bind("<Button-4>", self._on_scroll)
        self.textbox._textbox.bind("<Button-5>", self._on_scroll)
        self.textbox._textbox.bind("<ButtonRelease-1>", self._on_scroll)

    def set_json(self, text: str) -> None:
        """Set the JSON result text.  Does NOT force-switch to output view.

        If the user is currently viewing the log, they remain on the log
        tab.  A subtle indicator on the Output button signals new content.
        """
        self._json_text = text
        if self._showing_json:
            # Already viewing output — refresh in place.
            self._refresh_view()
        else:
            # User is on the log tab — highlight the Output button to
            # indicate new output is available without switching.
            self._highlight_output_button()
        state = "normal" if text else "disabled"
        self.copy_btn.configure(state=state)
        self.save_btn.configure(state=state)

    def _highlight_output_button(self) -> None:
        """Flash the Output button to signal new content is available."""
        self.output_btn.configure(
            fg_color=("#228822", "#2d5a2d"),
            text_color="white",
        )
        self.after(
            _TOAST_DURATION_MS,
            lambda: self._reset_output_button_style(),
        )

    def _reset_output_button_style(self) -> None:
        """Restore Output button to its default style."""
        if self._showing_json:
            self.output_btn.configure(
                fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
                text_color=ctk.ThemeManager.theme["CTkButton"]["text_color"],
            )
        else:
            self.output_btn.configure(
                fg_color="transparent",
                text_color=("gray50", "gray70"),
            )

    def set_status_message(self, message: str) -> None:
        """Display a brief status message in the output view."""
        self._json_text = message
        self._showing_json = True
        self._update_toggle_style()
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", message)
        self.textbox.configure(state="disabled")
        self.copy_btn.configure(state="disabled")
        self.save_btn.configure(state="disabled")

    def append_log(self, line: str) -> None:
        """Append a line to the log buffer.  If log view active, update."""
        self._log_lines.append(line)
        if not self._showing_json:
            self.textbox.configure(state="normal")
            start_idx = self.textbox._textbox.index("end-1c")
            self.textbox.insert("end", line + "\n")
            end_idx = self.textbox._textbox.index("end-1c")
            # Apply color tag based on log level
            tag = self._detect_level_tag(line)
            if tag:
                self.textbox._textbox.tag_add(tag, start_idx, end_idx)
            if self._auto_scroll:
                self.textbox.see("end")
            self.textbox.configure(state="disabled")
        self._update_button_state()

    def _detect_level_tag(self, line: str) -> str | None:
        """Return the tag name for a log line's level, or None for INFO."""
        # Format: "HH:MM:SS  LEVEL    message" — level starts after timestamp
        for level in ("ERROR", "CRITICAL", "WARNING", "DEBUG"):
            if f"  {level}" in line:
                return f"log_{level}"
        return None

    def _on_scroll(self, _event: Any = None) -> None:
        """Detect user scroll and pause/resume auto-scroll."""
        if not self._showing_json:
            # Check if scrollbar is at the bottom
            self.after(10, self._check_scroll_position)

    def _check_scroll_position(self) -> None:
        """Check if the textbox is scrolled to the bottom."""
        try:
            _, ymax = self.textbox._textbox.yview()
            self._auto_scroll = ymax >= 0.98
        except Exception:  # noqa: BLE001
            self._auto_scroll = True

    def clear(self) -> None:
        """Clear both JSON and log content."""
        self._json_text = ""
        self._log_lines.clear()
        self._auto_scroll = True
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
        self.copy_btn.configure(state="disabled")
        self.save_btn.configure(state="disabled")

    def _update_button_state(self) -> None:
        """Enable Save/Copy when the active view has content."""
        if self._showing_json:
            has_content = bool(self._json_text)
        else:
            has_content = bool(self._log_lines)
        state = "normal" if has_content else "disabled"
        self.copy_btn.configure(state=state)
        self.save_btn.configure(state=state)

    def _show_json(self) -> None:
        self._showing_json = True
        self._update_toggle_style()
        self._refresh_view()
        self._update_button_state()

    def _show_log(self) -> None:
        self._showing_json = False
        self._auto_scroll = True
        self._update_toggle_style()
        self._refresh_view()
        self._update_button_state()

    def _update_toggle_style(self) -> None:
        if self._showing_json:
            self.output_btn.configure(
                fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
                text_color=ctk.ThemeManager.theme["CTkButton"]["text_color"],
            )
            self.log_btn.configure(
                fg_color="transparent", text_color=("gray50", "gray70"),
            )
        else:
            self.log_btn.configure(
                fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
                text_color=ctk.ThemeManager.theme["CTkButton"]["text_color"],
            )
            self.output_btn.configure(
                fg_color="transparent", text_color=("gray50", "gray70"),
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
                    f"Output is {size / 1_000_000:.1f} MB \u2014 too large to display.\n"
                    "Use the Save button to export.",
                )
            else:
                self.textbox.insert("1.0", text)
                if text and size <= _HIGHLIGHT_LIMIT:
                    with contextlib.suppress(Exception):
                        _apply_json_highlighting(self.textbox, text)
        else:
            content = "\n".join(self._log_lines)
            self.textbox.insert("1.0", content)
            # Apply color tags to each log line
            for i, line in enumerate(self._log_lines):
                tag = self._detect_level_tag(line)
                if tag:
                    line_num = i + 1
                    self.textbox._textbox.tag_add(
                        tag, f"{line_num}.0", f"{line_num}.end",
                    )
            self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def _copy(self) -> None:
        """Copy current view to clipboard with visual feedback (item 2.12)."""
        text = self._json_text if self._showing_json else "\n".join(self._log_lines)
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)

        # Visual feedback
        original_fg = self.copy_btn.cget("fg_color")
        self.copy_btn.configure(text="Copied!", fg_color=("#228822", "#2d5a2d"))
        self.copy_btn.after(
            _COPY_FEEDBACK_MS,
            lambda: self.copy_btn.configure(text="Copy", fg_color=original_fg),
        )

    def _save(self) -> None:
        if self._showing_json:
            text = self._json_text
            if not text:
                return
            path = filedialog.asksaveasfilename(
                title="Save JSON Output",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
        else:
            text = "\n".join(self._log_lines)
            if not text:
                return
            path = filedialog.asksaveasfilename(
                title="Save Log Output",
                defaultextension=".log",
                filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")],
            )
        if path:
            try:
                Path(path).write_text(text + "\n", encoding="utf-8")
                self._show_toast(f"Saved to {Path(path).name}")
            except OSError as exc:
                messagebox.showerror("Save Error", str(exc))

    def _show_toast(self, message: str) -> None:
        toast = ctk.CTkLabel(
            self, text=f"  {message}  ",
            fg_color=("green", "#2d5a2d"), corner_radius=6,
        )
        toast.place(relx=0.5, rely=0.95, anchor="center")
        self.after(_TOAST_DURATION_MS, toast.destroy)


# ---------------------------------------------------------------------------
# Progress panel — compact, fixed-height, embeddable in the operations page
# ---------------------------------------------------------------------------


class ProgressPanel(ctk.CTkFrame):
    """Compact progress display embedded in the fixed-height action region.

    Does NOT contain a log textbox — all log output goes to the shared
    ``OutputPanel``.  This panel displays only the progress bar, status
    label, elapsed timer, and current-file indicator.
    """

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._start_time: float = 0.0
        self._has_started_processing: bool = False
        self._elapsed_after_id: str | None = None
        self._global_total: int = 0
        self._global_completed: int = 0
        self._build_widgets()

    def _build_widgets(self) -> None:
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(fill="x", pady=(0, 4))

        self.status_label = ctk.CTkLabel(info_frame, text="Preparing...", anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)
        self.elapsed_label = ctk.CTkLabel(info_frame, text="0:00", anchor="e", width=60)
        self.elapsed_label.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.pack(fill="x", pady=(0, 4))
        self.progress_bar.set(0)

        self.current_label = ctk.CTkLabel(
            self, text="", anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        )
        self.current_label.pack(fill="x")

    def start(self) -> None:
        self._start_time = time.monotonic()
        self._has_started_processing = False
        self._global_total = 0
        self._global_completed = 0
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.status_label.configure(
            text="Discovering items...",
            text_color=ctk.ThemeManager.theme["CTkLabel"]["text_color"],
        )
        self.current_label.configure(text="")
        self._tick_elapsed()

    def update_progress(self, event: ProgressEvent) -> None:
        if event.phase == "discovery":
            if not self._has_started_processing:
                # First discovery event — show indeterminate bar.
                self.progress_bar.configure(mode="indeterminate")
                self.status_label.configure(text="Discovering items...")
            # Accumulate discovered totals from each directory.
            if event.items_total is not None and event.items_total > 0:
                self._global_total += event.items_total
        elif event.phase == "processing":
            if not self._has_started_processing:
                self._has_started_processing = True
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
            # Track global completed count across all subdirectories.
            # Only increment when an item was actually processed
            # (items_completed=0 is a mode-transition signal).
            if event.items_completed and event.items_completed > 0:
                self._global_completed += 1
            if self._global_total > 0:
                fraction = min(self._global_completed / self._global_total, 1.0)
                self.progress_bar.set(fraction)
                pct = int(fraction * 100)
                self.status_label.configure(
                    text=f"Processing: {self._global_completed}/{self._global_total} ({pct}%)",
                )

        if event.current_path is not None:
            display_path = str(event.current_path)
            if len(display_path) > 80:
                display_path = "..." + display_path[-77:]
            self.current_label.configure(text=display_path)

    def _tick_elapsed(self) -> None:
        """Update the elapsed timer independently of progress events."""
        elapsed = time.monotonic() - self._start_time
        mins, secs = divmod(int(elapsed), 60)
        self.elapsed_label.configure(text=f"{mins}:{secs:02d}")
        self._elapsed_after_id = self.after(1000, self._tick_elapsed)

    def stop(self) -> None:
        if self._elapsed_after_id is not None:
            self.after_cancel(self._elapsed_after_id)
            self._elapsed_after_id = None
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(1.0)
        elapsed = time.monotonic() - self._start_time
        mins, secs = divmod(int(elapsed), 60)
        self.elapsed_label.configure(text=f"{mins}:{secs:02d}")


# ---------------------------------------------------------------------------
# Operations page (consolidated from 4 separate tabs -- item 2.1)
# ---------------------------------------------------------------------------


class OperationsPage(ctk.CTkFrame):
    """Consolidated operations view with inline operation type selector.

    All controls are always visible.  Controls that do not apply to the
    current operation/target configuration are *disabled* (greyed-out)
    with explanatory fine-print labels — they are never hidden.

    Rename is an optional feature toggle that can be combined with any
    of the three core operations (Index, Meta Merge, Meta Merge Delete),
    not a standalone operation type.
    """

    def __init__(self, master: Any, app: ShruggiIndexerApp, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._app = app
        self._target_validation_error: str | None = None
        self._build_widgets()
        # Apply initial control state
        self._reconcile_controls()

    # -- Widget construction ------------------------------------------------

    def _build_widgets(self) -> None:
        # Header
        ctk.CTkLabel(
            self, text="Operations",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        # Fixed-height progress/action region pinned at bottom (SS10.9 1.3.6).
        # Packed before the scroll area so it claims space first.
        self._progress_region = ctk.CTkFrame(
            self, height=_PROGRESS_REGION_HEIGHT,
        )
        self._progress_region.pack(fill="x", side="bottom", pady=(8, 0))
        self._progress_region.pack_propagate(False)

        # -- Idle sub-frame (START button, centered) --
        self._idle_frame = ctk.CTkFrame(
            self._progress_region, fg_color="transparent",
        )
        self.action_btn = _CtkButton(
            self._idle_frame, text=_ACTION_LABEL_START, height=36,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#1b8a1b", "#22882a"),
            hover_color=("#167016", "#1d6e23"),
            command=self._on_action,
        )
        self.action_btn.pack(anchor="center", expand=True)
        _Tooltip(self.action_btn, "Start the selected operation on the target path.")
        # Constrain width to 50 % of parent on resize
        self._idle_frame.bind(
            "<Configure>",
            lambda e: self.action_btn.configure(
                width=min(350, max(180, int(e.width * 0.45))),
            ),
        )

        # -- Running sub-frame (progress + cancel) --
        self._running_frame = ctk.CTkFrame(
            self._progress_region, fg_color="transparent",
        )
        self._progress_panel = ProgressPanel(self._running_frame)
        self._progress_panel.pack(fill="x", pady=(4, 2))
        self._cancel_btn = _CtkButton(
            self._running_frame, text=_ACTION_LABEL_RUNNING, height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#cc3333", "#cc3333"),
            hover_color=("#aa2222", "#aa2222"),
            command=self._on_action,
        )
        self._cancel_btn.pack(anchor="center", pady=(2, 4))

        # Start in idle state
        self._idle_frame.pack(fill="both", expand=True)

        # Auto-scrollable frame — scrollbar only appears when content
        # overflows; mousewheel events do not propagate to the output panel.
        self._scroll = _AutoScrollFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True)

        self._build_operation_group()
        self._build_target_group()
        self._build_options_group()
        self._build_output_group()

    def _build_operation_group(self) -> None:
        group = _LabeledGroup(
            self._scroll.content, "Operation",
            "Select the indexing operation to perform.",
        )
        group.pack(fill="x", pady=(0, 6))
        c = group.content

        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x")

        ctk.CTkLabel(row, text="Type:", anchor="w").pack(side="left", padx=(0, 8))
        self._op_type_var = ctk.StringVar(value=_OP_INDEX)
        self._op_menu = _CtkOptionMenu(
            row, variable=self._op_type_var,
            values=_OPERATION_LABELS,
            command=self._on_operation_changed,
            width=180,
        )
        self._op_menu.pack(side="left", padx=(0, 16))
        _Tooltip(self._op_menu, "Choose Index, Meta Merge, or Meta Merge Delete.")

        self._indicator = _DestructiveIndicator(row)
        self._indicator.pack(side="left")

    def _build_target_group(self) -> None:
        group = _LabeledGroup(
            self._scroll.content, "Target",
            "Choose the file or directory to index.",
        )
        group.pack(fill="x", pady=(0, 6))
        c = group.content

        # Path entry row
        path_frame = ctk.CTkFrame(c, fg_color="transparent")
        path_frame.pack(fill="x", pady=(0, 2))

        ctk.CTkLabel(path_frame, text="Path:", width=40, anchor="w").pack(
            side="left", padx=(0, 6),
        )
        self._path_entry = _CtkEntry(
            path_frame, placeholder_text="Select a file or folder...",
        )
        self._path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        _Tooltip(self._path_entry, "Enter the file or directory path to index.")

        # Bind focus-out and key-release for validation + auto-suggest
        self._path_entry.bind("<FocusOut>", lambda _: self._on_target_or_type_change())
        self._path_entry.bind("<KeyRelease>", lambda _: self._on_target_or_type_change())

        # Browse buttons -- single button for file/directory, dual for auto
        self._browse_single_btn = _CtkButton(
            path_frame, text="Browse", width=80, command=self._browse_by_type,
        )
        self._browse_file_btn = _CtkButton(
            path_frame, text="File\u2026", width=60, command=self._browse_file,
        )
        self._browse_dir_btn = _CtkButton(
            path_frame, text="Folder\u2026", width=70, command=self._browse_dir,
        )
        _Tooltip(self._browse_single_btn, "Open a file or directory picker.")
        _Tooltip(self._browse_file_btn, "Open a file picker dialog.")
        _Tooltip(self._browse_dir_btn, "Open a directory picker dialog.")

        # Target validation error label (red fine-print, always present)
        self._target_error_label = ctk.CTkLabel(
            c, text="",
            font=ctk.CTkFont(size=10),
            text_color=("#cc3333", "#ff4444"),
            anchor="w",
        )
        self._target_error_label.pack(fill="x", padx=(46, 0), pady=(0, 2))

        # Type + recursive row
        opts_frame = ctk.CTkFrame(c, fg_color="transparent")
        opts_frame.pack(fill="x", pady=(0, 2))

        ctk.CTkLabel(opts_frame, text="Type:", width=40, anchor="w").pack(
            side="left", padx=(0, 6),
        )
        self._type_var = ctk.StringVar(value="auto")
        self._type_radios: dict[str, ctk.CTkRadioButton] = {}
        for label, val in [("Auto", "auto"), ("File", "file"), ("Directory", "directory")]:
            rb = _CtkRadioButton(
                opts_frame, text=label, variable=self._type_var, value=val,
                command=self._on_type_changed,
            )
            rb.pack(side="left", padx=(0, 10))
            self._type_radios[val] = rb
            _Tooltip(rb, {
                "auto": "Detect target type automatically from the path.",
                "file": "Treat target as a single file.",
                "directory": "Treat target as a directory.",
            }[val])

        # Recursive row (separate so hint aligns under the checkbox)
        recursive_row = ctk.CTkFrame(c, fg_color="transparent")
        recursive_row.pack(fill="x", pady=(2, 0))

        self._recursive_var = ctk.BooleanVar(value=True)
        self._recursive_cb = _CtkCheckBox(
            recursive_row, text="Recursive", variable=self._recursive_var,
        )
        self._recursive_cb.pack(anchor="w")
        _Tooltip(self._recursive_cb, "Include subdirectories when indexing a directory.")

        # Recursive disabled explanation (fine-print, aligned under checkbox)
        self._recursive_info_label = ctk.CTkLabel(
            recursive_row, text="",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self._recursive_info_label.pack(anchor="w", padx=(26, 0))

        # Apply initial browse button state
        self._update_browse_buttons()

    def _build_options_group(self) -> None:
        self._opts_group = _LabeledGroup(
            self._scroll.content, "Options",
            "Configure indexing parameters.",
        )
        self._opts_group.pack(fill="x", pady=(0, 6))
        c = self._opts_group.content

        # Row 1: ID Algorithm + SHA-512 (always visible)
        row1 = ctk.CTkFrame(c, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 2))

        ctk.CTkLabel(row1, text="ID Algorithm:", anchor="w").pack(
            side="left", padx=(0, 6),
        )
        self._id_algo_var = ctk.StringVar(value="md5")
        self._algo_combo = _CtkComboBox(
            row1, values=["md5", "sha256"], variable=self._id_algo_var, width=120,
        )
        self._algo_combo.pack(side="left", padx=(0, 20))
        _Tooltip(self._algo_combo, "Hash algorithm used for generating file identity.")

        # Row 2: SHA-512 (own row for hint alignment)
        sha512_row = ctk.CTkFrame(c, fg_color="transparent")
        sha512_row.pack(fill="x", pady=(2, 0))

        self._sha512_var = ctk.BooleanVar(value=False)
        self._sha512_cb = _CtkCheckBox(
            sha512_row, text="Compute SHA-512", variable=self._sha512_var,
        )
        self._sha512_cb.pack(anchor="w")
        _Tooltip(self._sha512_cb, "Compute an additional SHA-512 hash for each file.")

        # SHA-512 override info label (fine-print, aligned under checkbox)
        self._sha512_override_label = ctk.CTkLabel(
            sha512_row, text="",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self._sha512_override_label.pack(anchor="w", padx=(26, 0))

        # Row 3: Extract EXIF (always visible, user-controlled)
        exif_row = ctk.CTkFrame(c, fg_color="transparent")
        exif_row.pack(fill="x", pady=(2, 0))
        self._exif_var = ctk.BooleanVar(value=False)
        self._exif_cb = _CtkCheckBox(
            exif_row, text="Extract EXIF metadata",
            variable=self._exif_var,
        )
        self._exif_cb.pack(anchor="w")
        _Tooltip(self._exif_cb, "Extract embedded metadata using ExifTool.")

        self._exif_info_label = ctk.CTkLabel(
            exif_row, text="",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self._exif_info_label.pack(anchor="w", padx=(26, 0))

        # Row 4: Rename toggle (feature, not operation)
        rename_row = ctk.CTkFrame(c, fg_color="transparent")
        rename_row.pack(fill="x", pady=(2, 0))
        self._rename_var = ctk.BooleanVar(value=False)
        self._rename_cb = _CtkCheckBox(
            rename_row, text="Rename files",
            variable=self._rename_var,
            command=self._on_rename_changed,
        )
        self._rename_cb.pack(anchor="w")
        _Tooltip(self._rename_cb, "Rename files to content-based storage names after indexing.")

        self._rename_info_label = ctk.CTkLabel(
            rename_row, text="",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self._rename_info_label.pack(anchor="w", padx=(26, 0))

    def _build_output_group(self) -> None:
        self._output_group = _LabeledGroup(
            self._scroll.content, "Output",
            "Control how results are produced.",
        )
        self._output_group.pack(fill="x", pady=(0, 6))
        c = self._output_group.content

        # Output mode selector (three-mode: Single file / Multi-file / View only)
        mode_row = ctk.CTkFrame(c, fg_color="transparent")
        mode_row.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(mode_row, text="Mode:", anchor="w").pack(
            side="left", padx=(0, 8),
        )
        self._output_mode_var = ctk.StringVar(value=_OUT_SINGLE)
        self._output_mode_menu = _CtkOptionMenu(
            mode_row, variable=self._output_mode_var,
            values=_OUTPUT_MODE_LABELS,
            command=self._on_output_mode_changed,
            width=180,
        )
        self._output_mode_menu.pack(side="left", padx=(0, 16))
        _Tooltip(
            self._output_mode_menu,
            "Single file: one output file, no sidecars.\n"
            "Multi-file: summary file + per-file sidecar files.\n"
            "View only: display in viewer, nothing written to disk.",
        )

        # Output mode info label (constraint explanation)
        self._output_mode_info_label = ctk.CTkLabel(
            c, text="",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self._output_mode_info_label.pack(fill="x", padx=(4, 0), pady=(0, 2))

        # Read-only output path display
        self._outpath_display = _CtkEntry(
            c, state="disabled",
            placeholder_text="Select a target to see the output path.",
        )
        self._outpath_display.pack(fill="x", pady=(2, 0))

        # Output path note (small font, e.g. sidecar info)
        self._outpath_note = ctk.CTkLabel(
            c, text="",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self._outpath_note.pack(fill="x", padx=(4, 0), pady=(0, 2))

    # -- Browse helpers -----------------------------------------------------

    def _update_browse_buttons(self) -> None:
        """Show appropriate browse buttons based on target type selection."""
        target_type = self._type_var.get()
        self._browse_single_btn.pack_forget()
        self._browse_file_btn.pack_forget()
        self._browse_dir_btn.pack_forget()

        if target_type == "auto":
            self._browse_dir_btn.pack(side="right", padx=(2, 0))
            self._browse_file_btn.pack(side="right", padx=(2, 0))
        else:
            self._browse_single_btn.pack(side="right")

    def _browse_by_type(self) -> None:
        """Browse using the currently selected target type."""
        target_type = self._type_var.get()
        if target_type == "directory":
            self._browse_dir()
        else:
            self._browse_file()

    def _browse_file(self) -> None:
        logger.debug("Browse dialog opened for: file")
        path = filedialog.askopenfilename(title="Select File")
        if path:
            logger.debug("Browse result: %s", path)
            self._set_target_path(path)
        else:
            logger.debug("Browse result: cancelled")

    def _browse_dir(self) -> None:
        logger.debug("Browse dialog opened for: folder")
        path = filedialog.askdirectory(title="Select Directory")
        if path:
            logger.debug("Browse result: %s", path)
            self._set_target_path(path)
        else:
            logger.debug("Browse result: cancelled")

    def _set_target_path(self, path: str) -> None:
        logger.debug("Target path set to: %s", path)
        self._path_entry.delete(0, "end")
        self._path_entry.insert(0, path)
        self._on_target_or_type_change()

    # -- Auto-suggest output path (item 2.5) --------------------------------

    def _compute_output_path(self) -> str:
        """Compute the output file path based on current target and mode."""
        target_path = self._path_entry.get().strip()
        if not target_path:
            return ""
        mode = self._output_mode_var.get()
        if mode == _OUT_VIEW:
            return ""
        target_kind = self._detect_target_kind()
        p = Path(target_path.rstrip("/\\"))
        if target_kind == "directory":
            normalized = str(p).rstrip("/\\")
            if not normalized or normalized == "/":
                return str(Path.home() / "root_directorymeta2.json")
            return normalized + "_directorymeta2.json"
        return str(p) + "_meta2.json"

    # -- Target / Type validation -------------------------------------------

    def _detect_target_kind(self) -> str | None:
        """Return 'file', 'directory', or None if indeterminate."""
        target = self._path_entry.get().strip()
        if not target:
            return None
        p = Path(target)
        if p.exists():
            return "directory" if p.is_dir() else "file"
        # Heuristic: trailing separator → directory, has extension → file
        if target.endswith(("/", "\\")):
            return "directory"
        if "." in p.name and not p.name.startswith("."):
            return "file"
        return None

    def _validate_target_type(self) -> str | None:
        """Return an error message string if the target conflicts with Type.

        The error is stored in ``_target_validation_error`` and controls
        whether the START button is enabled.
        """
        selected_type = self._type_var.get()
        target = self._path_entry.get().strip()
        if not target:
            return None

        kind = self._detect_target_kind()
        if kind is None:
            return None

        if kind == "file" and selected_type == "directory":
            return (
                "Target appears to be a file, but Type is set to "
                "\"Directory\". Change the target or select a different Type."
            )
        if kind == "directory" and selected_type == "file":
            return (
                "Target appears to be a directory, but Type is set to "
                "\"File\". Change the target or select a different Type."
            )
        return None

    # -- Control state updates (enable/disable, never hide) -----------------

    def _on_operation_changed(self, _choice: str) -> None:
        """Update control state for the selected operation."""
        logger.debug("Operation type changed to: %s", self._op_type_var.get())
        self._reconcile_controls()

    def _on_type_changed(self) -> None:
        """Handle target type radio change."""
        logger.debug("Target type changed to: %s", self._type_var.get())
        self._update_browse_buttons()
        self._on_target_or_type_change()

    def _on_target_or_type_change(self) -> None:
        """Re-validate target/type combo, refresh controls."""
        self._reconcile_controls()

    def _on_output_mode_changed(self, _choice: str = "") -> None:
        """Update output path display based on mode."""
        logger.debug("Output mode changed to: %s", self._output_mode_var.get())
        self._reconcile_controls()

    def _on_rename_changed(self) -> None:
        """Rename checkbox toggled — refresh dependent controls."""
        logger.debug("Option changed: Rename files = %s", self._rename_var.get())
        self._reconcile_controls()

    @staticmethod
    def _disable_cb(cb: ctk.CTkCheckBox, *, select: bool = False) -> None:
        """Disable a checkbox with a muted fill when checked.

        If *select* is ``True`` the checkbox is force-checked first.
        Checked-and-disabled checkboxes use a grey fill so they do not
        appear interactive.
        """
        if select:
            cb.select()
        cb.configure(state="disabled")
        if cb.get():
            cb.configure(fg_color=_FORCED_CHECK_FG)

    @staticmethod
    def _enable_cb(cb: ctk.CTkCheckBox) -> None:
        """Re-enable a checkbox and restore its theme accent colour."""
        cb.configure(
            state="normal",
            fg_color=ctk.ThemeManager.theme["CTkCheckBox"]["fg_color"],
        )

    def _reconcile_controls(self) -> None:
        """Centralized state reconciliation — single source of truth.

        Reads all control values and sets the enabled/disabled state, default
        values, placeholder text, and info labels for every dependent control.
        Implements the output mode constraint matrix from the output system
        overhaul specification.

        Called on initial construction, whenever any input changes, and after
        restoring session state.

        **SS10.9 Standard 1.3.3** — Control Interdependency Transparency.
        """
        op = self._op_type_var.get()
        rename_on = self._rename_var.get()
        selected_type = self._type_var.get()
        target_kind = self._detect_target_kind()
        target_path = self._path_entry.get().strip()

        # -- Target validation --
        err = self._validate_target_type()
        self._target_validation_error = err
        self._target_error_label.configure(text=err or "")

        # -- Recursive toggle (§3.2.1) --
        if selected_type == "directory":
            self._enable_cb(self._recursive_cb)
            if not target_path:
                self._recursive_var.set(True)
            self._recursive_info_label.configure(text="")
        elif selected_type == "file":
            self._recursive_var.set(False)
            self._disable_cb(self._recursive_cb)
            self._recursive_info_label.configure(
                text="Recursive is not applicable to single-file targets.",
            )
        elif selected_type == "auto":
            if target_kind == "file":
                self._recursive_var.set(False)
                self._disable_cb(self._recursive_cb)
                self._recursive_info_label.configure(
                    text="Recursive is not applicable to single-file targets.",
                )
            elif target_kind == "directory":
                self._enable_cb(self._recursive_cb)
                self._recursive_info_label.configure(text="")
            else:
                self._enable_cb(self._recursive_cb)
                self._recursive_info_label.configure(text="")

        # -- SHA-512 override from Settings --
        self._sync_sha512_from_settings()

        # -- EXIF -- (user-controlled for all operation types)
        self._enable_cb(self._exif_cb)
        self._exif_info_label.configure(text="")

        # -- Rename --
        self._enable_cb(self._rename_cb)
        self._rename_info_label.configure(text="")

        # -- Output mode constraint matrix --
        # Determine effective target type for constraint evaluation.
        effective_type = selected_type
        if effective_type == "auto":
            effective_type = target_kind or "unknown"

        is_dir = effective_type == "directory"
        is_mmd = op == _OP_META_MERGE_DELETE
        mode = self._output_mode_var.get()

        # Build list of available modes for this combination.
        available_modes = [_OUT_SINGLE]
        if is_dir:
            available_modes.append(_OUT_MULTI)
        if not is_mmd:
            available_modes.append(_OUT_VIEW)

        # Enforce fallback if current mode is no longer valid.
        if mode not in available_modes:
            # Determine default: Multi-file for directories, Single for files.
            if is_dir and _OUT_MULTI in available_modes:
                mode = _OUT_MULTI
            else:
                mode = _OUT_SINGLE
            self._output_mode_var.set(mode)

        # Update the selector to show only available modes.
        self._output_mode_menu.configure(values=available_modes)

        # Info label for constraint explanation.
        info_parts = []
        if not is_dir:
            info_parts.append("Multi-file is only available for directory targets.")
        if is_mmd:
            info_parts.append(
                "View only is not available for Meta Merge Delete "
                "(destructive operations require a persistent output record).",
            )
        self._output_mode_info_label.configure(
            text="  ".join(info_parts),
        )

        # -- Output path display --
        self._update_output_path_display()

        # -- Destructive indicator --
        destructive = op == _OP_META_MERGE_DELETE or rename_on
        self._indicator.set_destructive(destructive)

        # -- Action button enabled state --
        if self._target_validation_error:
            self.action_btn.configure(state="disabled")
        else:
            self.action_btn.configure(state="normal")

    def _update_output_path_display(self) -> None:
        """Set the read-only output path display and note label."""
        target_path = self._path_entry.get().strip()
        mode = self._output_mode_var.get()
        target_kind = self._detect_target_kind()

        # Temporarily enable the entry to update its contents.
        self._outpath_display.configure(state="normal")
        self._outpath_display.delete(0, "end")

        if mode == _OUT_VIEW:
            self._outpath_display.insert(
                0, "Output will be displayed in the viewer panel.",
            )
            self._outpath_note.configure(text="")
        elif not target_path:
            self._outpath_display.insert(0, "")
            self._outpath_display.configure(
                placeholder_text="Select a target to see the output path.",
            )
            self._outpath_note.configure(text="")
        else:
            computed = self._compute_output_path()
            self._outpath_display.insert(0, computed)
            # Set note based on mode and target kind.
            if target_kind == "directory":
                if mode == _OUT_MULTI:
                    self._outpath_note.configure(
                        text="Summary output file. Per-file sidecar files "
                             "will also be written within the directory tree.",
                    )
                else:
                    self._outpath_note.configure(
                        text="Summary output file. No sidecar files will be written.",
                    )
            else:
                self._outpath_note.configure(text="")

        self._outpath_display.configure(state="disabled")

    def _sync_sha512_from_settings(self) -> None:
        """Force-enable SHA-512 checkbox if Settings says 'always compute'."""
        settings_sha512 = False
        if hasattr(self._app, "_settings_tab"):
            settings_sha512 = self._app._settings_tab.sha512_var.get()

        if settings_sha512:
            self._sha512_var.set(True)
            self._disable_cb(self._sha512_cb, select=True)
            self._sha512_override_label.configure(
                text="Forced on by Settings -> \"Compute SHA-512 by default\".",
            )
        else:
            self._enable_cb(self._sha512_cb)
            self._sha512_override_label.configure(text="")

    # -- Action button handler ----------------------------------------------

    def _on_action(self) -> None:
        if self._app.is_running:
            self._app.request_cancel()
        else:
            self._app.run_operation(self)

    # -- Config building ----------------------------------------------------

    def build_config(self, base: IndexerConfig) -> IndexerConfig:
        """Construct the final IndexerConfig for the current operation."""
        op = self._op_type_var.get()
        rename_on = self._rename_var.get()
        mode = self._output_mode_var.get()
        overrides: dict[str, Any] = {
            "id_algorithm": self._id_algo_var.get(),
            "compute_sha512": self._sha512_var.get(),
            "recursive": self._recursive_var.get(),
            "extract_exif": self._exif_var.get(),
            "output_stdout": False,
        }

        # Rename feature (applies to any operation)
        if rename_on:
            overrides["rename"] = True

        # Operation-specific flags
        if op == _OP_META_MERGE:
            overrides["meta_merge"] = True
        elif op == _OP_META_MERGE_DELETE:
            overrides["meta_merge"] = True
            overrides["meta_merge_delete"] = True

        # Output mode → config mapping
        if mode == _OUT_VIEW:
            overrides["output_file"] = None
            overrides["output_inplace"] = False
        elif mode == _OUT_MULTI:
            computed_path = self._compute_output_path()
            overrides["output_file"] = Path(computed_path) if computed_path else None
            overrides["output_inplace"] = True
        else:
            # _OUT_SINGLE (default)
            computed_path = self._compute_output_path()
            overrides["output_file"] = Path(computed_path) if computed_path else None
            overrides["output_inplace"] = False

        return replace(base, **overrides)

    def get_target_path(self) -> str:
        return self._path_entry.get().strip()

    def get_output_mode(self) -> str:
        """Return the effective output mode for post-job display logic."""
        return self._output_mode_var.get()

    def get_output_file(self) -> str:
        """Return the computed output file path."""
        return self._compute_output_path()

    def validate(self) -> str | None:
        """Return error message if invalid, else ``None``."""
        if self._target_validation_error:
            return self._target_validation_error
        return None

    # -- Running state ------------------------------------------------------

    def set_running(self, running: bool) -> None:
        """Toggle the progress region between idle and running states.

        **SS10.9 Standard 1.3.6:** The progress region occupies the same
        fixed-height space in all states — no layout shift occurs.
        """
        state = "normal" if not running else "disabled"
        self._path_entry.configure(state=state)
        self._browse_single_btn.configure(state=state)
        self._browse_file_btn.configure(state=state)
        self._browse_dir_btn.configure(state=state)

        if running:
            # Switch to running sub-frame within the fixed region
            self._idle_frame.pack_forget()
            self._running_frame.pack(fill="both", expand=True)
        else:
            # Switch to idle sub-frame within the fixed region
            self._running_frame.pack_forget()
            self._idle_frame.pack(fill="both", expand=True)

    # -- Session persistence ------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "operation_type": _OP_KEY_MAP.get(
                self._op_type_var.get(), "index",
            ),
            "target_path": self._path_entry.get(),
            "target_type": self._type_var.get(),
            "recursive": self._recursive_var.get(),
            "id_algorithm": self._id_algo_var.get(),
            "sha512": self._sha512_var.get(),
            "extract_exif": self._exif_var.get(),
            "rename": self._rename_var.get(),
            "output_mode": _OUT_KEY_MAP.get(
                self._output_mode_var.get(), "single",
            ),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        op_type = state.get("operation_type", "index")
        # Backward compat: old "rename" operation → Index + rename feature
        if op_type == "rename":
            op_type = "index"
            state.setdefault("rename", True)
        label = _OP_LABEL_MAP.get(op_type, _OP_INDEX)
        self._op_type_var.set(label)

        if "target_path" in state:
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, state["target_path"])
        if "target_type" in state:
            self._type_var.set(state["target_type"])
        if "recursive" in state:
            self._recursive_var.set(state["recursive"])
        if "id_algorithm" in state:
            self._id_algo_var.set(state["id_algorithm"])
        if "sha512" in state:
            self._sha512_var.set(state["sha512"])
        if "extract_exif" in state:
            self._exif_var.set(state["extract_exif"])
        if "rename" in state:
            self._rename_var.set(state["rename"])
        if "output_mode" in state:
            # Backward compat: map old "view"/"save"/"both" to new modes.
            mode_val = state["output_mode"]
            mode_label = _OUT_LABEL_MAP.get(mode_val, mode_val)
            if mode_label not in _OUTPUT_MODE_LABELS:
                mode_label = _OUT_SINGLE
            self._output_mode_var.set(mode_label)
        # Update controls for the restored state
        self._update_browse_buttons()
        self._reconcile_controls()

    def restore_from_old_session(
        self, old_active_tab: str, tab_states: dict[str, Any],
    ) -> None:
        """Migrate from the old per-tab session format."""
        if old_active_tab == "rename":
            self._op_type_var.set(_OP_INDEX)
            self._rename_var.set(True)
        else:
            label = _OP_LABEL_MAP.get(old_active_tab, _OP_INDEX)
            self._op_type_var.set(label)

        old_state = tab_states.get(old_active_tab, {})
        target = old_state.get("target", {})
        if "path" in target:
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, target["path"])
        if "type" in target:
            self._type_var.set(target["type"])
        if "recursive" in target:
            self._recursive_var.set(target["recursive"])
        if "id_algorithm" in old_state:
            self._id_algo_var.set(old_state["id_algorithm"])
        if "sha512" in old_state:
            self._sha512_var.set(old_state["sha512"])
        if "extract_exif" in old_state:
            self._exif_var.set(old_state["extract_exif"])

        self._update_browse_buttons()
        self._reconcile_controls()


# ---------------------------------------------------------------------------
# Settings tab
# ---------------------------------------------------------------------------


class SettingsTab(ctk.CTkFrame):
    """Settings tab -- defaults, output prefs, logging, interface, config."""

    def __init__(self, master: Any, app: ShruggiIndexerApp, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._app = app
        self._build_widgets()

    def _build_widgets(self) -> None:
        ctk.CTkLabel(
            self, text="Settings",
            font=ctk.CTkFont(size=18, weight="bold"), anchor="w",
        ).pack(fill="x", pady=(0, 16))

        self._scroll = _AutoScrollFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True)
        scroll = self._scroll.content

        # -- Indexing Defaults ---
        self._section_header(scroll, "Indexing Defaults")

        row = ctk.CTkFrame(scroll, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row, text="Default ID Algorithm:").pack(side="left", padx=(0, 6))
        self.id_algo_var = ctk.StringVar(value="md5")
        algo_combo = _CtkComboBox(
            row, values=["md5", "sha256"], variable=self.id_algo_var, width=120,
        )
        algo_combo.pack(side="left")
        _Tooltip(algo_combo, "Default hash algorithm for new operations.")

        self.sha512_var = ctk.BooleanVar(value=False)
        sha512_cb = _CtkCheckBox(
            scroll, text="Compute SHA-512 by default", variable=self.sha512_var,
            command=self._on_sha512_changed,
        )
        sha512_cb.pack(fill="x", pady=(0, 8))
        _Tooltip(sha512_cb, "Enable SHA-512 computation by default for new operations.")

        # -- Output Preferences ---
        self._section_header(scroll, "Output Preferences")

        row2 = ctk.CTkFrame(scroll, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row2, text="JSON Indentation:").pack(side="left", padx=(0, 6))
        self.indent_var = ctk.StringVar(value="2")
        for label, val in [("2 spaces", "2"), ("4 spaces", "4"), ("Compact", "none")]:
            rb = _CtkRadioButton(
                row2, text=label, variable=self.indent_var, value=val,
            )
            rb.pack(side="left", padx=(0, 10))
            _Tooltip(rb, {
                "2": "Indent JSON output with 2 spaces.",
                "4": "Indent JSON output with 4 spaces.",
                "none": "Produce compact single-line JSON.",
            }[val])

        # -- Logging ---
        self._section_header(scroll, "Logging")

        row3 = ctk.CTkFrame(scroll, fg_color="transparent")
        row3.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row3, text="Verbosity:").pack(side="left", padx=(0, 6))
        self.verbosity_var = ctk.StringVar(value="normal")
        for label, val in [("Normal", "normal"), ("Verbose", "verbose"), ("Debug", "debug")]:
            rb = _CtkRadioButton(
                row3, text=label, variable=self.verbosity_var, value=val,
            )
            rb.pack(side="left", padx=(0, 10))
            _Tooltip(rb, {
                "normal": "Show warnings and errors only.",
                "verbose": "Show informational messages during processing.",
                "debug": "Show detailed per-item processing log.",
            }[val])

        self.log_to_file_var = ctk.BooleanVar(value=False)
        log_file_cb = _CtkCheckBox(
            scroll, text="Write log files",
            variable=self.log_to_file_var,
        )
        log_file_cb.pack(fill="x", pady=(0, 8))
        _Tooltip(
            log_file_cb,
            "When enabled, each operation writes a log file to the app data "
            "directory for later analysis.",
        )

        # -- Interface ---
        self._section_header(scroll, "Interface")

        self.tooltips_var = ctk.BooleanVar(value=True)
        tooltips_cb = _CtkCheckBox(
            scroll, text="Show tooltips on hover",
            variable=self.tooltips_var,
            command=self._on_tooltips_changed,
        )
        tooltips_cb.pack(fill="x", pady=(0, 8))
        _Tooltip(tooltips_cb, "Enable or disable hover tooltips for all controls.")

        # -- Configuration ---
        self._section_header(scroll, "Configuration")

        row4 = ctk.CTkFrame(scroll, fg_color="transparent")
        row4.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row4, text="Config File:").pack(side="left", padx=(0, 6))
        self.config_entry = _CtkEntry(
            row4, placeholder_text="Optional TOML config path",
        )
        self.config_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        _Tooltip(self.config_entry, "Path to a TOML configuration file for custom defaults.")

        config_browse = _CtkButton(
            row4, text="Browse", width=80, command=self._browse_config,
        )
        config_browse.pack(side="right")
        _Tooltip(config_browse, "Select a TOML configuration file.")

        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(8, 8))
        reset_btn = _CtkButton(
            btn_frame, text="Reset to Defaults", width=140,
            command=self._reset_defaults,
        )
        reset_btn.pack(side="left", padx=(0, 10))
        _Tooltip(reset_btn, "Reset all settings to factory defaults.")

        open_btn = _CtkButton(
            btn_frame, text="Open Config Folder", width=140,
            command=self._open_config_folder,
        )
        open_btn.pack(side="left")
        _Tooltip(open_btn, "Open the configuration directory in your file manager.")

    @staticmethod
    def _section_header(
        parent: ctk.CTkFrame, text: str,
    ) -> None:
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w",
        ).pack(fill="x", pady=(12, 4))

    def _on_tooltips_changed(self) -> None:
        _Tooltip.set_enabled(self.tooltips_var.get())

    def _on_sha512_changed(self) -> None:
        """Notify Operations page to sync SHA-512 override state."""
        logger.debug("Setting changed: sha512 = %s", self.sha512_var.get())
        if hasattr(self._app, "_ops_page"):
            self._app._ops_page._sync_sha512_from_settings()

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
            self.log_to_file_var.set(False)
            self.tooltips_var.set(True)
            self.config_entry.delete(0, "end")
            _Tooltip.set_enabled(True)
            self._on_sha512_changed()

    def _open_config_folder(self) -> None:
        session_path = SessionManager._resolve_path()
        folder = session_path.parent
        folder.mkdir(parents=True, exist_ok=True)
        if platform.system() == "Windows":
            os.startfile(folder)  # noqa: S606
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(folder)])  # noqa: S603, S607
        else:
            subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603, S607

    def get_state(self) -> dict[str, Any]:
        return {
            "id_algorithm": self.id_algo_var.get(),
            "sha512": self.sha512_var.get(),
            "indent": self.indent_var.get(),
            "verbosity": self.verbosity_var.get(),
            "log_to_file": self.log_to_file_var.get(),
            "tooltips": self.tooltips_var.get(),
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
        if "log_to_file" in state:
            self.log_to_file_var.set(state["log_to_file"])
        if "tooltips" in state:
            self.tooltips_var.set(state["tooltips"])
            _Tooltip.set_enabled(state["tooltips"])
        if "config_file" in state:
            self.config_entry.delete(0, "end")
            self.config_entry.insert(0, state["config_file"])


# ---------------------------------------------------------------------------
# About tab (item 2.9)
# ---------------------------------------------------------------------------


class AboutTab(ctk.CTkFrame):
    """About page displaying project info, version, and links."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._build_widgets()

    def _build_widgets(self) -> None:
        ctk.CTkLabel(
            self, text="About",
            font=ctk.CTkFont(size=18, weight="bold"), anchor="w",
        ).pack(fill="x", pady=(0, 16))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True)

        # Branding
        ctk.CTkLabel(
            content, text="\u00af\\_(\u30c4)_/\u00af",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).pack(pady=(20, 4))
        ctk.CTkLabel(
            content, text="Shruggie Indexer",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(0, 16))

        # Description
        ctk.CTkLabel(
            content,
            text=(
                "A filesystem indexer with hash-based identity, metadata\n"
                "extraction, and structured JSON output."
            ),
            font=ctk.CTkFont(size=13),
            text_color=("gray30", "gray70"),
            justify="center",
        ).pack(pady=(0, 20))

        # Info rows
        info_frame = ctk.CTkFrame(content, fg_color="transparent")
        info_frame.pack(pady=(0, 20))

        self._info_row(info_frame, "Version:", __version__)
        self._info_row(
            info_frame, "Python:",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
        exiftool_status = "Available" if shutil.which("exiftool") else "Not found"
        self._info_row(info_frame, "ExifTool:", exiftool_status)

        # Links
        links_frame = ctk.CTkFrame(content, fg_color="transparent")
        links_frame.pack(pady=(0, 20))

        docs_btn = _CtkButton(
            links_frame, text="Documentation",
            width=160, command=lambda: webbrowser.open(_DOCS_URL),
        )
        docs_btn.pack(side="left", padx=(0, 10))
        _Tooltip(docs_btn, "Open the project documentation in your browser.")

        website_btn = _CtkButton(
            links_frame, text="shruggie.tech",
            width=160, command=lambda: webbrowser.open(_WEBSITE_URL),
        )
        website_btn.pack(side="left")
        _Tooltip(website_btn, "Visit the ShruggieTech LLC website.")

        # Attribution
        ctk.CTkLabel(
            content,
            text="Built by ShruggieTech LLC",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).pack(pady=(10, 0))

    @staticmethod
    def _info_row(parent: ctk.CTkFrame, label: str, value: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text=label, anchor="e", width=80).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            row, text=value, anchor="w", text_color=("gray30", "gray70"),
        ).pack(side="left")

    def get_state(self) -> dict[str, Any]:
        return {}

    def restore_state(self, _state: dict[str, Any]) -> None:
        pass


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------


class ShruggiIndexerApp(ctk.CTk):
    """Shruggie Indexer -- CustomTkinter dark-theme desktop application.

    Provides a visual frontend to the ``shruggie_indexer`` library with a
    consolidated Operations tab, a Settings tab, and an About tab.
    See spec sections 10.1-10.7 for full requirements.
    """

    def __init__(self) -> None:
        super().__init__()

        # State
        self._job_running = False
        self._cancel_event = threading.Event()
        self._result_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._progress_queue: queue.Queue[ProgressEvent] = queue.Queue()
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._active_tab_id: str = _TAB_OPERATIONS
        self._tabs: dict[str, ctk.CTkFrame] = {}
        self._sidebar_buttons: dict[str, ctk.CTkButton] = {}
        self._session = SessionManager()
        self._output_height = _DEFAULT_OUTPUT_HEIGHT
        self._last_output_mode = "view"  # Track for post-job display

        # Logging handler — GUI panel (item 2.11)
        self._log_handler = _LogQueueHandler(self._log_queue)
        self._log_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)-7s  %(message)s",
                datefmt="%H:%M:%S",
            ),
        )

        # Worker thread reference for health checks
        self._worker_thread: threading.Thread | None = None

        # Persistent DEBUG-level file handler — always on (Issue 3)
        self._persistent_file_handler: logging.FileHandler | None = None
        self._setup_file_logging()

        # Window setup
        self.title(_WINDOW_TITLE)
        self.geometry(_DEFAULT_GEOMETRY)
        self.minsize(_MIN_WIDTH, _MIN_HEIGHT)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._build_layout()
        self._bind_shortcuts()
        self._restore_session()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- Persistent file logging (Issue 3) ----------------------------------

    def _setup_file_logging(self) -> None:
        """Set up a persistent DEBUG-level log file on every GUI launch.

        The file handler always runs at DEBUG regardless of the Settings
        tab Verbosity control (which only affects the GUI log panel).
        """
        try:
            from shruggie_indexer.cli.log_file import make_file_handler

            self._persistent_file_handler = make_file_handler()
            self._persistent_file_handler.setLevel(logging.DEBUG)
            lib_logger = logging.getLogger("shruggie_indexer")
            lib_logger.setLevel(logging.DEBUG)
            lib_logger.addHandler(self._persistent_file_handler)
            logger.info("Shruggie Indexer GUI v%s started", __version__)
            logger.info(
                "Platform: %s %s, Python %s",
                platform.system(),
                platform.release(),
                f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            )
            logger.debug(
                "Log file: %s",
                self._persistent_file_handler.baseFilename,
            )
        except Exception:
            logger.warning("Failed to set up persistent file logging", exc_info=True)

    # -- Layout construction ------------------------------------------------

    def _build_layout(self) -> None:
        # Sidebar
        self._sidebar = ctk.CTkFrame(self, width=_SIDEBAR_WIDTH, corner_radius=0)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        # App branding
        ctk.CTkLabel(
            self._sidebar, text="\u00af\\_(\u30c4)_/\u00af",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(16, 4))
        ctk.CTkLabel(
            self._sidebar, text="Indexer",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).pack(pady=(0, 16))

        # Tab buttons
        for tab_id in (_TAB_OPERATIONS, _TAB_SETTINGS, _TAB_ABOUT):
            btn = _CtkButton(
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

        # Version label at bottom of sidebar (item 2.10)
        # Spacer to push version to the bottom
        spacer = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        ctk.CTkLabel(
            self._sidebar,
            text=f"v{__version__}",
            font=ctk.CTkFont(size=10),
            text_color=("gray55", "gray45"),
        ).pack(pady=(0, 12))

        # Main area
        self._main_area = ctk.CTkFrame(self, fg_color="transparent")
        self._main_area.pack(side="right", fill="both", expand=True, padx=16, pady=16)

        # Tab content container
        self._tab_container = ctk.CTkFrame(self._main_area, fg_color="transparent")
        self._tab_container.pack(fill="both", expand=True)

        # Create tabs
        self._ops_page = OperationsPage(self._tab_container, app=self)
        self._settings_tab = SettingsTab(self._tab_container, app=self)
        self._about_tab = AboutTab(self._tab_container)

        self._tabs[_TAB_OPERATIONS] = self._ops_page
        self._tabs[_TAB_SETTINGS] = self._settings_tab
        self._tabs[_TAB_ABOUT] = self._about_tab

        # Drag handle for resizable output panel (item 2.13)
        self._drag_handle = _DragHandle(
            self._main_area, on_drag=self._on_output_resize,
        )

        # Shared output panel
        self._output_panel = OutputPanel(self._main_area)
        self._output_panel.pack_propagate(False)
        self._output_panel.configure(height=self._output_height)

        # Show the default tab
        self._switch_tab(_TAB_OPERATIONS)

    def _switch_tab(self, tab_id: str) -> None:
        """Show the specified tab and update sidebar highlighting."""
        if self._job_running and tab_id not in (_TAB_SETTINGS, _TAB_ABOUT) and tab_id != self._active_tab_id:
            return

        for tab in self._tabs.values():
            tab.pack_forget()

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

        self._tabs[tab_id].pack(fill="both", expand=True)
        self._active_tab_id = tab_id
        logger.debug("Tab selected: %s", _TAB_LABELS.get(tab_id, tab_id))

        # Show/hide output panel
        if tab_id in (_TAB_SETTINGS, _TAB_ABOUT):
            self._drag_handle.pack_forget()
            self._output_panel.pack_forget()
        else:
            self._output_panel.configure(height=self._output_height)
            self._output_panel.pack(side="bottom", fill="x")
            self._drag_handle.pack(side="bottom", fill="x", pady=(2, 2))

    def _on_output_resize(self, delta: int) -> None:
        """Adjust output panel height by delta pixels (item 2.13)."""
        new_height = max(
            _MIN_OUTPUT_HEIGHT,
            min(_MAX_OUTPUT_HEIGHT, self._output_height + delta),
        )
        self._output_height = new_height
        self._output_panel.configure(height=new_height)

    # -- Keyboard shortcuts -------------------------------------------------

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-r>", lambda _: self._shortcut_run())
        self.bind("<Control-R>", lambda _: self._shortcut_run())
        self.bind("<Control-s>", lambda _: self._output_panel._save())
        self.bind("<Control-S>", lambda _: self._output_panel._save())
        self.bind("<Control-Shift-C>", lambda _: self._output_panel._copy())
        self.bind("<Control-period>", lambda _: self.request_cancel())
        self.bind("<Escape>", lambda _: self.request_cancel())
        self.bind("<Control-q>", lambda _: self._on_close())
        self.bind("<Control-Q>", lambda _: self._on_close())
        self.bind("<Control-comma>", lambda _: self._switch_tab(_TAB_SETTINGS))
        self.bind("<Control-Key-1>", lambda _: self._switch_tab(_TAB_OPERATIONS))
        self.bind("<Control-Key-2>", lambda _: self._switch_tab(_TAB_SETTINGS))
        self.bind("<Control-Key-3>", lambda _: self._switch_tab(_TAB_ABOUT))

    def _shortcut_run(self) -> None:
        if self._active_tab_id == _TAB_OPERATIONS and not self._job_running:
            self.run_operation(self._ops_page)

    # -- Logging setup (item 2.11) ------------------------------------------

    def _start_log_capture(self) -> None:
        """Attach the queue-based handler to the library logger.

        The GUI panel handler level is controlled by Settings Verbosity.
        The persistent file handler (set up at startup) always runs at
        DEBUG — it is not affected by this method.
        """
        settings = self._settings_tab
        verbosity = settings.verbosity_var.get()
        level = {
            "debug": logging.DEBUG,
            "verbose": logging.INFO,
            "normal": logging.WARNING,
        }.get(verbosity, logging.WARNING)

        lib_logger = logging.getLogger("shruggie_indexer")
        # Keep logger at DEBUG so the persistent file handler receives
        # everything.  The GUI panel handler filters by its own level.
        lib_logger.setLevel(logging.DEBUG)
        self._log_handler.setLevel(level)
        lib_logger.addHandler(self._log_handler)

        logger.debug("Log capture started (GUI panel level: %s)", verbosity)

        # Start polling log queue
        self._poll_log_messages()

    def _stop_log_capture(self) -> None:
        """Remove the GUI queue handler from the library logger.

        The persistent file handler is NOT removed — it stays active for
        the lifetime of the application.
        """
        lib_logger = logging.getLogger("shruggie_indexer")
        lib_logger.removeHandler(self._log_handler)
        # Drain any remaining messages
        self._drain_log_queue()
        logger.debug("Log capture stopped")

    def _poll_log_messages(self) -> None:
        """Poll the log queue and forward messages to the output panel."""
        self._drain_log_queue()
        if self._job_running:
            self.after(_POLL_INTERVAL_MS, self._poll_log_messages)

    def _drain_log_queue(self) -> None:
        """Drain all pending log messages from the queue."""
        count = 0
        while count < 200:
            try:
                msg = self._log_queue.get_nowait()
                self._output_panel.append_log(msg)
            except queue.Empty:
                break
            count += 1

    # -- Job execution ------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._job_running

    def run_operation(self, ops: OperationsPage) -> None:
        """Validate inputs, construct config, and launch the background job."""
        target_path_str = ops.get_target_path()
        if not target_path_str:
            logger.warning("Validation: no target path provided")
            messagebox.showwarning("Missing Target", "Please select a target path.")
            return

        target = Path(target_path_str)
        if not target.exists():
            logger.warning("Validation: path does not exist: %s", target)
            messagebox.showerror("Invalid Target", f"Path does not exist:\n{target}")
            return

        err = ops.validate()
        if err:
            logger.warning("Validation: %s", err)
            messagebox.showwarning("Validation Error", err)
            return

        try:
            base_config = load_config()
            config = ops.build_config(base_config)
        except IndexerError as exc:
            logger.error("Configuration error: %s", exc)
            messagebox.showerror("Configuration Error", str(exc))
            return

        op_label = ops._op_type_var.get()
        logger.info(
            "Operation started: %s on %s (%s%s)",
            op_label,
            target_path_str,
            ops._type_var.get(),
            ", recursive" if ops._recursive_var.get() else "",
        )
        logger.debug("IndexerConfig: %s", config)

        # Store output mode for post-job display logic (item 2.8)
        self._last_output_mode = ops.get_output_mode()
        self._last_output_file = ops.get_output_file()

        # Transition to running state
        self._job_running = True
        self._cancel_event.clear()
        ops.set_running(True)
        self._set_sidebar_enabled(False)

        # Auto-clear output (item 2.6)
        self._output_panel.clear()

        # Start progress display in the ops page's embedded progress region
        self._ops_page._progress_panel.start()

        # Start log capture (item 2.11)
        self._start_log_capture()

        # Background thread
        thread = threading.Thread(
            target=self._background_job,
            args=(target, config),
            daemon=True,
            name="shruggie-worker",
        )
        self._worker_thread = thread
        logger.debug("Background thread created: %s", thread.name)
        thread.start()
        logger.debug("Background thread started")
        self._poll_results()

    def _background_job(self, target: Path, config: IndexerConfig) -> None:
        """Run the indexing operation in a background thread.

        Executes the full pipeline including Stage 6 post-processing:
        rename, in-place sidecar writes, and sidecar deletion for
        MetaMergeDelete.
        """
        result: dict[str, Any] = {"status": "error", "message": "Unknown error"}
        logger.debug("Background thread entry: target=%s", target)
        _job_start = time.monotonic()
        try:
            # ── Prepare delete queue for MetaMergeDelete ────────────────
            delete_queue: list[Path] | None = (
                [] if config.meta_merge_delete else None
            )

            # ── Execute indexing ────────────────────────────────────────
            logger.info("Indexing started for: %s", target)
            entry = index_path(
                target,
                config,
                delete_queue=delete_queue,
                progress_callback=self._on_progress,
                cancel_event=self._cancel_event,
            )

            # ── Stage 6: Rename (spec §6.10) ───────────────────────────
            if config.rename:
                logger.info("Rename phase started")
                if entry.type == "file":
                    rename_item(target, entry)
                elif entry.items is not None:
                    for child in entry.items:
                        if child.type == "file":
                            child_path = target / child.file_system.relative
                            try:
                                rename_item(child_path, child)
                            except Exception:
                                logger.warning(
                                    "Rename failed for %s",
                                    child_path,
                                    exc_info=True,
                                )

            # ── In-place sidecar output ─────────────────────────────────
            if config.output_inplace:
                self._write_inplace_tree(entry, target)

            # ── Aggregate output ────────────────────────────────────────
            json_str = serialize_entry(entry)

            if config.output_file is not None:
                config.output_file.write_text(json_str + "\n", encoding="utf-8")
                logger.info("Output written to: %s", config.output_file)

            # ── MetaMergeDelete: drain deletion queue (Stage 6) ─────────
            if delete_queue:
                deleted = self._drain_delete_queue(delete_queue)
                logger.info("Deleted %d merged sidecar files", deleted)

            result = {"status": "success", "json": json_str}
            _job_elapsed = time.monotonic() - _job_start
            logger.info("Operation completed in %.1fs", _job_elapsed)

        except IndexerCancellationError:
            logger.info("Operation cancelled by user")
            result = {"status": "cancelled", "message": "Operation cancelled by user."}

        except IndexerError as exc:
            logger.error("Operation failed: %s", exc)
            result = {"status": "error", "message": str(exc)}

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Unhandled exception in background thread: %s",
                exc,
                exc_info=True,
            )
            result = {"status": "error", "message": f"Unexpected error: {exc}"}

        logger.debug("Background thread exited")
        self._result_queue.put(result)

    @staticmethod
    def _drain_delete_queue(queue: list[Path]) -> int:
        """Delete all sidecar files accumulated in the MetaMergeDelete queue.

        Returns the count of files successfully deleted.
        """
        deleted = 0
        for path in queue:
            try:
                path.unlink()
                logger.debug("Deleted merged sidecar: %s", path)
                deleted += 1
            except OSError as exc:
                logger.warning("Failed to delete sidecar %s: %s", path, exc)
        return deleted

    @staticmethod
    def _write_inplace_tree(entry: Any, root_path: Path) -> None:
        """Recursively write in-place sidecar files for an entry tree."""
        if entry.type == "file":
            item_path = root_path.parent / entry.file_system.relative
            write_inplace(entry, item_path, "file")
        elif entry.type == "directory":
            dir_path = root_path.parent / entry.file_system.relative
            write_inplace(entry, dir_path, "directory")
            if entry.items:
                for child in entry.items:
                    ShruggiIndexerApp._write_inplace_tree(child, root_path)

    def _on_progress(self, event: ProgressEvent) -> None:
        # Thread-safe: put on queue instead of calling self.after() from
        # the background thread.  Drained by _poll_results on the main
        # thread every _POLL_INTERVAL_MS.
        self._progress_queue.put_nowait(event)

    def _drain_progress_queue(self) -> None:
        """Drain pending progress events (main thread only)."""
        for _ in range(200):
            try:
                event = self._progress_queue.get_nowait()
            except queue.Empty:
                break
            self._ops_page._progress_panel.update_progress(event)
            if event.message:
                ts = time.strftime("%H:%M:%S")
                self._output_panel.append_log(f"{ts}  INFO     {event.message}")

    def _poll_results(self) -> None:
        # Drain progress events first (main-thread safe).
        self._drain_progress_queue()

        try:
            result = self._result_queue.get_nowait()
        except queue.Empty:
            # Safety net: if the worker thread died without posting a
            # result, detect and force-complete with an error.
            if (
                self._worker_thread is not None
                and not self._worker_thread.is_alive()
            ):
                logger.error(
                    "Background thread died without posting a result"
                )
                result = {
                    "status": "error",
                    "message": "Background thread terminated unexpectedly.",
                }
                self._drain_progress_queue()
                self.after(
                    _COMPLETION_DELAY_MS,
                    lambda: self._on_job_complete(result),
                )
                return
            self.after(_POLL_INTERVAL_MS, self._poll_results)
            return
        # Final drain to capture any trailing progress events.
        self._drain_progress_queue()
        self.after(_COMPLETION_DELAY_MS, lambda: self._on_job_complete(result))

    def _on_job_complete(self, result: dict[str, Any]) -> None:
        """Handle completion of a background job.

        Does NOT force-switch the active panel tab.  Output content is
        loaded into the Output view in the background; if the user is on
        the Log tab, a subtle indicator on the Output button signals
        that new content is available.
        """
        progress = self._ops_page._progress_panel
        progress.stop()
        self._stop_log_capture()

        status = result.get("status", "error")
        output_mode = self._last_output_mode

        if status == "success":
            progress.status_label.configure(
                text="Complete", text_color=("green", "#00cc00"),
            )
            logger.info("Operation completed successfully")
            json_text = result.get("json", "")

            # Route based on output mode
            if output_mode == _OUT_VIEW:
                # View only → display in viewer panel
                self._output_panel.set_json(json_text)
            elif output_mode in (_OUT_SINGLE, _OUT_MULTI):
                # File output — show save confirmation
                outfile = self._last_output_file
                msg = f"Output saved to: {outfile}" if outfile else "Output saved."
                self._output_panel.set_status_message(msg)
            else:
                # Fallback (should not happen)
                self._output_panel.set_json(json_text)

        elif status == "cancelled":
            progress.status_label.configure(
                text="Cancelled", text_color=("#cc8800", "#ffaa00"),
            )
            logger.info("Operation cancelled")
            self._output_panel.append_log(result.get("message", "Cancelled."))

        else:
            progress.status_label.configure(
                text="Error", text_color=("#cc3333", "#ff4444"),
            )
            logger.error("Operation failed: %s", result.get("message", "Unknown error"))
            self._output_panel.append_log(
                f"ERROR: {result.get('message', 'Unknown error')}",
            )

        # Restore idle state
        self._job_running = False
        if isinstance(self._ops_page, OperationsPage):
            self._ops_page.set_running(False)
        self._set_sidebar_enabled(True)

        self._save_session()

    def request_cancel(self) -> None:
        if not self._job_running:
            return
        logger.info("Cancel requested by user")
        self._cancel_event.set()
        logger.debug("cancel_event.set() called")
        # Safety net: if the worker thread already died, force-reset the
        # GUI to idle immediately.
        if (
            self._worker_thread is not None
            and not self._worker_thread.is_alive()
        ):
            logger.warning(
                "Worker thread already dead — forcing GUI to idle"
            )
            result = {
                "status": "error",
                "message": "Background thread terminated unexpectedly.",
            }
            self._on_job_complete(result)

    def _set_sidebar_enabled(self, enabled: bool) -> None:
        for tab_id, btn in self._sidebar_buttons.items():
            if tab_id in (_TAB_SETTINGS, _TAB_ABOUT):
                continue
            btn.configure(state="normal" if enabled else "disabled")

    # -- Session persistence ------------------------------------------------

    def _save_session(self) -> None:
        data: dict[str, Any] = {
            "geometry": self.geometry(),
            "active_tab": self._active_tab_id,
            "operations_state": self._ops_page.get_state(),
            "settings": self._settings_tab.get_state(),
            "output_panel_height": self._output_height,
        }
        self._session.save(data)
        logger.debug("Session saved to: %s", self._session._path)

    def _restore_session(self) -> None:
        data = self._session.load()
        if not data:
            logger.debug("No session to restore")
            return
        logger.debug("Session restored from: %s", self._session._path)

        # Geometry
        if "geometry" in data:
            with contextlib.suppress(tk.TclError):
                self.geometry(data["geometry"])

        # New format
        if "operations_state" in data:
            self._ops_page.restore_state(data["operations_state"])
        elif "tab_states" in data:
            # Backward compatibility: migrate from old per-tab session format
            old_active = data.get("active_tab", "index")
            if old_active in ("index", "meta_merge", "meta_merge_delete", "rename"):
                self._ops_page.restore_from_old_session(
                    old_active, data["tab_states"],
                )

        # Settings
        settings = data.get("settings", {})
        if settings:
            self._settings_tab.restore_state(settings)

        # Output panel height
        if "output_panel_height" in data:
            self._output_height = max(
                _MIN_OUTPUT_HEIGHT,
                min(_MAX_OUTPUT_HEIGHT, data["output_panel_height"]),
            )

        # Active tab
        active = data.get("active_tab", _TAB_OPERATIONS)
        if active in (_TAB_OPERATIONS, _TAB_SETTINGS, _TAB_ABOUT):
            self._switch_tab(active)
        else:
            # Old format active tab -- always go to operations
            self._switch_tab(_TAB_OPERATIONS)

    # -- Window close -------------------------------------------------------

    def _on_close(self) -> None:
        if self._job_running:
            if not messagebox.askyesno(
                "Quit",
                "An operation is running. Do you want to cancel and quit?",
            ):
                return
            self._cancel_event.set()
        logger.info("Application exiting")
        self._save_session()
        # Explicitly terminate the persistent ExifTool process to prevent
        # orphaned child processes (the atexit handler is a safety net but
        # explicit cleanup is preferred on graceful exit).
        shutdown_exiftool()
        self.destroy()
        # Close persistent file handler before exit.
        if self._persistent_file_handler is not None:
            self._persistent_file_handler.close()
        # Force-terminate the process.  When a background job is blocked in
        # an uncancellable operation (large file hashing, exiftool IPC), the
        # daemon thread keeps the process alive even after the Tk mainloop
        # ends.  os._exit() bypasses normal cleanup but is the only reliable
        # way to prevent zombie processes visible in Task Manager.
        os._exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Launch the Shruggie Indexer GUI application."""
    app = ShruggiIndexerApp()
    app.mainloop()


if __name__ == "__main__":
    main()

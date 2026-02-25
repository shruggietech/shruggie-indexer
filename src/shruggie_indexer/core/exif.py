"""EXIF and embedded metadata extraction for shruggie-indexer.

Extracts embedded metadata from files using ``exiftool``.  Two backends are
supported in priority order:

1. **PyExifTool batch mode** (``exiftool.ExifToolHelper``) — persistent
   process with ``-stay_open``, amortizing per-file overhead from 200-500ms
   to 20-50ms (DEV-16).
2. **Subprocess fallback** (``subprocess.run()`` with ``-@`` argfile) — used
   when ``pyexiftool`` is not importable but ``exiftool`` is on PATH.

JSON output is parsed directly via ``json.loads()`` — ``jq`` is eliminated
entirely (DEV-06).

All failures are non-fatal.  ``extract_exif()`` returns ``None`` on any error
and logs an appropriate message.

See spec §6.6 for full behavioral guidance.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import logging
import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from shruggie_indexer.config.types import IndexerConfig

__all__ = [
    "EXIFTOOL_COMMON_ARGS",
    "EXIFTOOL_EXCLUDED_KEYS",
    "_base_key",
    "_filter_keys",
    "extract_exif",
    "shutdown_exiftool",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXIFTOOL_COMMON_ARGS: tuple[str, ...] = (
    "-json",
    "-n",
    "-extractEmbedded",
    "-scanForXMP",
    "-unknown2",
    "-G3:1",
    "-struct",
    "-ignoreMinorErrors",
    "-charset",
    "filename=utf8",
    "-api",
    "requestall=3",
    "-api",
    "largefilesupport=1",
)
"""Common exiftool arguments used by both backends.

These are the arguments specified in §6.6 of the spec.  The config's
``exiftool_args`` may override or extend this set; these are used only
when the config args are not sufficient.
"""

EXIFTOOL_EXCLUDED_KEYS: frozenset[str] = frozenset({
    # Original v1 jq deletion list
    "ExifToolVersion",
    "FileSequence",
    "NewGUID",
    "Directory",
    "FileName",
    "FilePath",
    "BaseName",
    "FilePermissions",
    # Absolute path exposure
    "SourceFile",
    # Redundant — captured in IndexEntry size/timestamps objects
    "FileSize",
    "FileModifyDate",
    "FileAccessDate",
    "FileCreateDate",
    # OS-specific filesystem attributes (not embedded metadata)
    "FileAttributes",
    "FileDeviceNumber",
    "FileInodeNumber",
    "FileHardLinks",
    "FileUserID",
    "FileGroupID",
    "FileDeviceID",
    "FileBlockSize",
    "FileBlockCount",
    # ExifTool operational metadata
    "Now",
    "ProcessingTime",
    "Error",
})
"""Keys filtered from exiftool output before returning.

Keys are matched by their base name (the portion after the last ``:``).
This handles group-prefixed output from ``-G`` flags (e.g.
``"System:FileName"`` matches ``"FileName"``).
"""

_EXIFTOOL_TIMEOUT: int = 30
"""Subprocess timeout in seconds."""


# ---------------------------------------------------------------------------
# Module-level state — backend selection and availability
# ---------------------------------------------------------------------------

# Sentinel values for lazy initialization.
_NOT_PROBED = object()

_exiftool_path: str | None | object = _NOT_PROBED
"""Cached path to exiftool binary, or ``None`` if absent."""

_pyexiftool_available: bool | object = _NOT_PROBED
"""Whether ``pyexiftool`` is importable."""

_backend: str | None | object = _NOT_PROBED
"""Selected backend: ``"batch"``, ``"subprocess"``, or ``None``."""

# pyexiftool helper instance managed by the batch backend.
_batch_helper: Any = None


def shutdown_exiftool() -> None:
    """Terminate the persistent ExifTool batch process, if running.

    Safe to call multiple times.  Registered as an ``atexit`` handler
    automatically and should also be called explicitly during application
    shutdown sequences (e.g., GUI ``on_closing()``).
    """
    global _batch_helper
    if _batch_helper is not None:
        with contextlib.suppress(Exception):
            _batch_helper.__exit__(None, None, None)
        _batch_helper = None
        logger.debug("ExifTool batch process shut down.")


# Register atexit handler as a safety net for abnormal termination.
atexit.register(shutdown_exiftool)


def _probe_exiftool() -> None:
    """Detect exiftool availability and select backend.

    Called once on first invocation of ``extract_exif()``.  Results are
    cached in module-level variables.
    """
    global _exiftool_path, _pyexiftool_available, _backend

    # 1. Is exiftool on PATH?
    _exiftool_path = shutil.which("exiftool")
    if _exiftool_path is None:
        _pyexiftool_available = False
        _backend = None
        logger.warning(
            "exiftool not found on PATH — embedded metadata extraction disabled"
        )
        return

    # 2. Is pyexiftool importable?
    try:
        import exiftool  # noqa: F401

        _pyexiftool_available = True
    except ImportError:
        _pyexiftool_available = False

    # 3. Backend selection
    if _pyexiftool_available:
        _backend = "batch"
        logger.debug("EXIF backend: pyexiftool batch mode")
    else:
        _backend = "subprocess"
        logger.info(
            "pyexiftool not installed — using subprocess fallback for exiftool"
        )


def _ensure_probed() -> None:
    """Ensure the exiftool probe has been performed."""
    if _exiftool_path is _NOT_PROBED:
        _probe_exiftool()


# ---------------------------------------------------------------------------
# Batch backend
# ---------------------------------------------------------------------------


def _get_batch_helper() -> Any:
    """Get or create the persistent ExifToolHelper instance.

    Returns ``None`` if the helper cannot be created.
    """
    global _batch_helper

    if _batch_helper is not None:
        return _batch_helper

    try:
        import exiftool

        _batch_helper = exiftool.ExifToolHelper(
            common_args=list(EXIFTOOL_COMMON_ARGS),
        )
        _batch_helper.__enter__()
        return _batch_helper
    except Exception as exc:
        logger.warning("Failed to start pyexiftool batch process: %s", exc)
        return None


def _extract_batch(path: Path, config: IndexerConfig) -> dict[str, Any] | None:
    """Extract metadata using pyexiftool batch mode.

    Handles ``ExifToolExecuteError`` (non-zero exit) by attempting to
    recover valid metadata from the exception's stdout.  ExifTool returns
    exit code 1 for "unknown file type" but still produces usable system-
    level metadata — discarding it is a behavioral regression vs. the
    original MakeIndex.
    """
    helper = _get_batch_helper()
    if helper is None:
        # Fall through to subprocess if batch mode fails.
        return _extract_subprocess(path, config)

    exclude_keys = config.exiftool_exclude_keys

    try:
        result = helper.get_metadata(str(path))
        if not result:
            logger.debug("exiftool returned empty metadata for %s", path)
            return None
        return _filter_keys(result[0], exclude_keys)
    except Exception as exc:
        # Attempt metadata recovery from ExifToolExecuteError on non-zero
        # exit.  Do NOT reset the persistent process — a per-file non-zero
        # exit code does not indicate process failure (§3.3.2-C).
        recovered = _recover_metadata_from_error(exc, path, exclude_keys)
        if recovered is not None:
            return recovered

        # True process failure — reset helper for next call.
        global _batch_helper
        logger.warning("pyexiftool error for %s: %s — resetting", path, exc)
        with contextlib.suppress(Exception):
            _batch_helper.__exit__(None, None, None)
        _batch_helper = None
        return None


def _recover_metadata_from_error(
    exc: Exception, path: Path, exclude_keys: frozenset[str],
) -> dict[str, Any] | None:
    """Attempt to extract valid metadata from an ExifToolExecuteError.

    Returns filtered metadata if the exception's stdout contains valid JSON
    with meaningful keys beyond ``SourceFile``.  Returns ``None`` if
    recovery is not possible (true process failure, no stdout, invalid JSON).
    """
    # Check if this is an ExifToolExecuteError with stdout data.
    stdout = getattr(exc, "stdout", None)
    if not stdout:
        return None

    # pyexiftool may provide stdout as bytes depending on version;
    # decode to str before attempting JSON parse.
    if isinstance(stdout, bytes):
        try:
            stdout = stdout.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return None
    if not isinstance(stdout, str):
        return None

    # Attempt to parse the stdout as JSON.
    parsed = _parse_json_output(stdout, path, exclude_keys)
    if parsed is None:
        return None

    # Check for ExifTool:Error informational field.
    _log_exiftool_error_field(parsed, path)

    return parsed


def _log_exiftool_error_field(
    data: dict[str, Any], path: Path,
) -> None:
    """Log ExifTool:Error fields at INFO level when metadata was recovered.

    The ``ExifTool:Error`` field with value ``"Unknown file type"`` is
    informational — exiftool still returns system-level metadata (§3.3.2-D).
    """
    for key, value in data.items():
        if _base_key(key) == "Error" and isinstance(value, str):
            if "unknown file type" in value.lower():
                logger.info(
                    "ExifTool: unknown file type for %s; system metadata preserved",
                    path.name,
                )
            else:
                logger.info(
                    "ExifTool: %s for %s; metadata recovered",
                    value, path.name,
                )
            break


# ---------------------------------------------------------------------------
# Subprocess fallback backend
# ---------------------------------------------------------------------------


def _extract_subprocess(path: Path, config: IndexerConfig) -> dict[str, Any] | None:
    """Extract metadata using subprocess + argfile fallback."""
    exclude_keys = config.exiftool_exclude_keys
    try:
        # Write arguments to a temporary argfile for exiftool's -@ switch.
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".args",
            encoding="utf-8",
            delete=False,
        ) as argfile:
            for arg in EXIFTOOL_COMMON_ARGS:
                argfile.write(arg + "\n")
            argfile.write(str(path) + "\n")
            argfile_path = argfile.name

        assert isinstance(_exiftool_path, str)  # guaranteed by _ensure_probed
        result = subprocess.run(
            [_exiftool_path, "-@", argfile_path],
            capture_output=True,
            text=True,
            timeout=_EXIFTOOL_TIMEOUT,
        )

        # Clean up argfile.
        try:
            import os

            os.unlink(argfile_path)
        except OSError:
            pass

        if result.returncode != 0:
            # Non-zero exit does not mean no output.  ExifTool exit code 1
            # signals warnings (e.g., "Unknown file type") but stdout may
            # still contain valid system-level metadata (§3.3.2-A).
            recovered = _parse_json_output(result.stdout, path, exclude_keys)
            if recovered is not None:
                _log_exiftool_error_field(recovered, path)
                return recovered
            logger.warning(
                "exiftool exited with code %d for %s: %s",
                result.returncode,
                path,
                result.stderr.strip(),
            )
            return None

        return _parse_json_output(result.stdout, path, exclude_keys)

    except subprocess.TimeoutExpired:
        logger.warning("exiftool timed out after %ds for %s", _EXIFTOOL_TIMEOUT, path)
        return None
    except OSError as exc:
        logger.warning("exiftool subprocess error for %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Output parsing and filtering
# ---------------------------------------------------------------------------


def _parse_json_output(
    stdout: str, path: Path, exclude_keys: frozenset[str],
) -> dict[str, Any] | None:
    """Parse exiftool JSON output and extract the first element."""
    if not stdout or not stdout.strip():
        logger.debug("exiftool produced no output for %s", path)
        return None

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON from exiftool for %s: %s", path, exc)
        return None

    if not isinstance(data, list) or not data:
        logger.warning("Unexpected exiftool output structure for %s", path)
        return None

    result = data[0]
    if not isinstance(result, dict):
        logger.warning("Unexpected exiftool result type for %s", path)
        return None

    filtered = _filter_keys(result, exclude_keys)
    if not filtered:
        logger.debug("exiftool returned only excluded keys for %s", path)
        return None

    return filtered


def _base_key(key: str) -> str:
    """Extract the base key name, stripping any group prefix.

    ExifTool with ``-G`` flags emits keys like ``"System:FileName"``.
    This returns ``"FileName"`` so filtering works regardless of
    whether a group prefix is present.
    """
    return key.rsplit(":", 1)[-1]


def _filter_keys(
    data: dict[str, Any], exclude_keys: frozenset[str],
) -> dict[str, Any]:
    """Remove excluded keys from exiftool output.

    Keys are matched by their base name (after the last ``:``) to
    handle group-prefixed output from ``-G`` flags.
    """
    return {
        k: v for k, v in data.items()
        if _base_key(k) not in exclude_keys
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_exif(
    path: Path,
    config: IndexerConfig,
) -> dict[str, Any] | None:
    """Extract embedded metadata using exiftool.

    Returns a dict of key-value pairs, or ``None`` if the extraction was
    skipped (extension excluded, symlink, exiftool absent) or failed.

    No exiftool failure is fatal — all error conditions result in ``None``
    with an appropriate log message.

    Args:
        path: Absolute path to the file to examine.
        config: The active :class:`~shruggie_indexer.config.types.IndexerConfig`.

    Returns:
        Filtered metadata dict, or ``None``.
    """
    _ensure_probed()

    # Disabled — exiftool not found.
    if _backend is None:
        return None

    # Extension exclusion gate.
    ext = path.suffix.lstrip(".").lower()
    if ext and ext in config.exiftool_exclude_extensions:
        logger.debug("EXIF extraction skipped — extension excluded: %s", ext)
        return None

    # Symlink gate — entry builder should not call us for symlinks, but
    # guard defensively.
    if path.is_symlink():
        logger.debug("EXIF extraction skipped — symlink: %s", path)
        return None

    # Dispatch to selected backend.
    if _backend == "batch":
        return _extract_batch(path, config)
    return _extract_subprocess(path, config)

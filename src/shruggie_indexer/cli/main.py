"""Command-line interface for shruggie-indexer.

Provides the single ``main()`` click command that serves as the entry point
for ``shruggie-indexer`` (console script) and ``python -m shruggie_indexer``.

See spec sections 8.1-8.11 for full behavioral guidance.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
import uuid
from enum import IntEnum
from pathlib import Path
from typing import Any

import click

from shruggie_indexer._version import __version__

__all__ = [
    "ExitCode",
    "main",
]

logger = logging.getLogger("shruggie_indexer")


# ---------------------------------------------------------------------------
# Exit codes (spec section 8.10)
# ---------------------------------------------------------------------------


class ExitCode(IntEnum):
    """Structured exit codes for CLI invocations."""

    SUCCESS = 0
    PARTIAL_FAILURE = 1
    CONFIGURATION_ERROR = 2
    TARGET_ERROR = 3
    RUNTIME_ERROR = 4
    INTERRUPTED = 5


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


class SessionFilter(logging.Filter):
    """Logging filter that attaches a session identifier to each record.

    The session ID is set once per invocation and carried on every log
    message for correlation in interleaved or persistent log streams.
    """

    def __init__(self, session_id: str = "") -> None:
        super().__init__()
        self.session_id = session_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = self.session_id  # type: ignore[attr-defined]
        return True


def configure_logging(
    *,
    verbose: int = 0,
    quiet: bool = False,
    log_file: Path | str | None = None,
) -> None:
    """Set up package-scoped logging to stderr and optionally to a file.

    Args:
        verbose: Verbosity count (0 = WARNING, 1 = INFO, 2+ = DEBUG).
        quiet: When ``True``, overrides *verbose* and sets CRITICAL.
        log_file: When set, also write log output to a persistent file.
            Pass ``True`` or an empty string to use the default app data
            directory; pass a path string or ``Path`` to write to a specific
            file.
    """
    if quiet:
        level = logging.CRITICAL
    else:
        level = {0: logging.WARNING, 1: logging.INFO}.get(verbose, logging.DEBUG)

    pkg_logger = logging.getLogger("shruggie_indexer")
    pkg_logger.setLevel(level)

    # Remove existing handlers to avoid duplicate output on re-invocation
    for handler in pkg_logger.handlers[:]:
        pkg_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    fmt = "%(levelname)s: %(message)s"
    if verbose >= 2:
        fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

    handler.setFormatter(logging.Formatter(fmt))
    pkg_logger.addHandler(handler)

    # Persistent log file (SS11.1)
    if log_file is not None:
        from shruggie_indexer.log_file import make_file_handler

        file_path: Path | None = None
        if isinstance(log_file, (str, Path)) and str(log_file).strip():
            file_path = Path(log_file)
        # None -> use default app data directory
        file_handler = make_file_handler(file_path)
        file_handler.setLevel(level)
        pkg_logger.addHandler(file_handler)
        pkg_logger.info("Log file: %s", file_handler.baseFilename)

    # Silence overly chatty trace loggers at -vv (only visible at -vvv)
    if verbose == 2:
        for name in ("shruggie_indexer.trace",):
            logging.getLogger(name).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Signal handling (spec section 8.11)
# ---------------------------------------------------------------------------


def _install_signal_handlers(cancel_event: threading.Event) -> None:
    """Install two-phase SIGINT handler for cooperative cancellation.

    First ``Ctrl+C``: set *cancel_event* so the engine stops at the next
    item boundary.  Second ``Ctrl+C``: restore default behavior and
    re-raise, forcing immediate termination.
    """

    def _handle_sigint(signum: int, frame: Any) -> None:
        if cancel_event.is_set():
            # Second interrupt — force quit
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            raise KeyboardInterrupt
        cancel_event.set()
        print(
            "\nInterrupt received — finishing current item. "
            "Press Ctrl+C again to force quit.",
            file=sys.stderr,
        )

    signal.signal(signal.SIGINT, _handle_sigint)


# ---------------------------------------------------------------------------
# Progress callback
# ---------------------------------------------------------------------------


def _make_progress_callback(
    verbose: int,
) -> Any:
    """Create a progress callback appropriate for the verbosity level.

    When running on a TTY with ``tqdm`` available and ``verbose >= 1``,
    returns a callback that updates a ``tqdm`` progress bar.  Otherwise
    returns ``None`` (no progress reporting).
    """
    if verbose < 1 or not sys.stderr.isatty():
        return None

    try:
        from tqdm import tqdm
    except ImportError:
        return None

    pbar: Any = None

    def _callback(event: Any) -> None:
        nonlocal pbar
        if event.phase == "discovery" and event.items_total is not None:
            pbar = tqdm(
                total=event.items_total,
                desc="Indexing",
                file=sys.stderr,
                unit="item",
                leave=True,
            )
        elif pbar is not None and event.phase == "processing":
            pbar.update(1)

    return _callback


def _close_progress(callback: Any) -> None:
    """Close the tqdm progress bar if one was created."""
    if callback is not None and hasattr(callback, "__self__"):
        pass  # Direct tqdm reference not stored; tqdm cleans up on GC
    # The tqdm bar is closed automatically when GC'd.  For explicit cleanup
    # we'd need a reference, but the callback closure approach makes this
    # tricky.  In practice tqdm handles this gracefully.


# ---------------------------------------------------------------------------
# MetaMergeDelete queue draining (spec section 4.1, Stage 6)
# ---------------------------------------------------------------------------


def _drain_delete_queue(queue: list[Path]) -> int:
    """Delete all sidecar files accumulated in the MetaMergeDelete queue.

    Returns the count of files successfully deleted.  Failed deletions
    do not abort the loop — remaining files are still attempted.
    """
    deleted = 0
    for path in queue:
        try:
            path.unlink()
            logger.info("Sidecar deleted: %s", path)
            deleted += 1
        except OSError as exc:
            logger.error("Sidecar delete FAILED: %s: %s", path, exc)
    return deleted


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@click.command(
    name="shruggie-indexer",
    help=(
        "Index files and directories, producing structured JSON output with "
        "hash-based identities, filesystem metadata, EXIF data, and sidecar "
        "metadata."
    ),
)
@click.argument(
    "target",
    required=False,
    default=None,
    type=click.Path(exists=True),
)
# -- Target options --
@click.option(
    "--file/--directory",
    "target_type",
    default=None,
    help="Force TARGET to be treated as a file or directory.",
)
@click.option(
    "--recursive/--no-recursive",
    default=None,
    help="Enable or disable recursive traversal. Default: recursive.",
)
# -- Output options --
@click.option(
    "--stdout/--no-stdout",
    default=None,
    help="Write JSON output to stdout.",
)
@click.option(
    "--outfile",
    "-o",
    type=click.Path(dir_okay=False, writable=True),
    default=None,
    help="Write combined JSON output to the specified file.",
)
@click.option(
    "--inplace",
    is_flag=True,
    default=False,
    help="Write individual sidecar JSON files alongside each item.",
)
# -- Metadata options --
@click.option(
    "--meta",
    "-m",
    is_flag=True,
    default=False,
    help="Extract embedded metadata via exiftool.",
)
@click.option(
    "--meta-merge",
    is_flag=True,
    default=False,
    help="Merge sidecar metadata into parent entries. Implies --meta.",
)
@click.option(
    "--meta-merge-delete",
    is_flag=True,
    default=False,
    help="Merge and delete sidecar files. Implies --meta-merge.",
)
# -- Rename options --
@click.option(
    "--rename",
    is_flag=True,
    default=False,
    help="Rename files to their storage_name. Implies --inplace.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview rename operations without executing them.",
)
# -- Identity options --
@click.option(
    "--id-type",
    type=click.Choice(["md5", "sha256"], case_sensitive=False),
    default=None,
    help="Hash algorithm for the id field. Default: md5.",
)
@click.option(
    "--compute-sha512",
    is_flag=True,
    default=False,
    help="Include SHA-512 in hash output.",
)
# -- Configuration --
@click.option(
    "--config",
    "config_file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a TOML configuration file.",
)
# -- Logging --
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase verbosity. Repeat for more detail (-vv, -vvv).",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    default=False,
    help="Suppress all non-error output.",
)
@click.option(
    "--log-file",
    "log_file",
    default=None,
    is_flag=False,
    flag_value="",
    help=(
        "Write log output to a persistent file. Without a path argument, "
        "writes to the default app data directory. With a path, writes to "
        "the specified file."
    ),
)
# -- General --
@click.version_option(version=__version__, prog_name="shruggie-indexer")
def main(
    target: str | None,
    target_type: bool | None,
    recursive: bool | None,
    stdout: bool | None,
    outfile: str | None,
    inplace: bool,
    meta: bool,
    meta_merge: bool,
    meta_merge_delete: bool,
    rename: bool,
    dry_run: bool,
    id_type: str | None,
    compute_sha512: bool,
    config_file: str | None,
    verbose: int,
    quiet: bool,
    log_file: str | None,
) -> None:
    """Index files and directories with hash-based identities."""
    from shruggie_indexer.config.loader import load_config
    from shruggie_indexer.core.entry import index_path
    from shruggie_indexer.core.rename import rename_item
    from shruggie_indexer.core.serializer import write_inplace, write_output
    from shruggie_indexer.exceptions import (
        IndexerCancellationError,
        IndexerConfigError,
        IndexerTargetError,
    )

    # ── Logging ─────────────────────────────────────────────────────────
    # Resolve log-file from TOML config if not set via CLI
    effective_log_file = log_file
    if effective_log_file is None and config_file is not None:
        # Peek at TOML for [logging] section before full config load
        try:
            import tomllib
            toml_data = tomllib.loads(
                Path(config_file).read_text(encoding="utf-8"),
            )
            logging_section = toml_data.get("logging", {})
            if isinstance(logging_section, dict) and logging_section.get("file_enabled", False):
                effective_log_file = logging_section.get("file_path", "")
        except Exception:
            pass  # Config errors are handled later by load_config

    configure_logging(
        verbose=verbose, quiet=quiet, log_file=effective_log_file,
    )

    # ── Signal handling ─────────────────────────────────────────────────
    cancel_event = threading.Event()
    _install_signal_handlers(cancel_event)

    try:
        # ── Resolve target ──────────────────────────────────────────────
        target_path = Path(target).resolve() if target else Path.cwd()

        # ── Programmatic validation (spec section 8.8) ──────────────────
        if meta_merge_delete and not outfile and not inplace:
            logger.error(
                "--meta-merge-delete requires --outfile or --inplace "
                "to ensure sidecar content is preserved before deletion."
            )
            sys.exit(ExitCode.CONFIGURATION_ERROR)

        # ── Build configuration overrides ───────────────────────────────
        overrides: dict[str, Any] = {}

        if recursive is not None:
            overrides["recursive"] = recursive
        if id_type is not None:
            overrides["id_algorithm"] = id_type.lower()
        if compute_sha512:
            overrides["compute_sha512"] = True
        if meta:
            overrides["extract_exif"] = True
        if meta_merge:
            overrides["meta_merge"] = True
        if meta_merge_delete:
            overrides["meta_merge_delete"] = True
        if rename:
            overrides["rename"] = True
        if dry_run:
            overrides["dry_run"] = True
        if inplace:
            overrides["output_inplace"] = True
        if outfile is not None:
            overrides["output_file"] = Path(outfile).resolve()

        # Resolve stdout default: enabled when no other output specified
        if stdout is None:
            if outfile is not None or inplace:
                overrides["output_stdout"] = False
            else:
                overrides["output_stdout"] = True
        else:
            overrides["output_stdout"] = stdout

        # ── Load configuration ──────────────────────────────────────────
        config = load_config(
            config_file=config_file,
            target_directory=(
                target_path if target_path.is_dir() else target_path.parent
            ),
            overrides=overrides,
        )

        # Log implication propagation (spec section 8.8)
        if config.rename and not inplace:
            logger.info("--rename implies --inplace; enabling in-place output")
        if config.meta_merge_delete and not meta_merge:
            logger.info(
                "--meta-merge-delete implies --meta-merge; enabling sidecar merging"
            )
        if config.meta_merge and not meta:
            logger.info(
                "--meta-merge implies --meta; enabling EXIF extraction"
            )

        # Warn if no output destinations are enabled
        if (
            not config.output_stdout
            and config.output_file is None
            and not config.output_inplace
        ):
            logger.warning(
                "No output destinations are enabled. The indexing operation "
                "will execute but produce no output."
            )

        # ── Prepare delete queue ────────────────────────────────────────
        delete_queue: list[Path] | None = (
            [] if config.meta_merge_delete else None
        )

        # ── Progress callback ───────────────────────────────────────────
        progress_cb = _make_progress_callback(verbose)

        # ── Session ID ──────────────────────────────────────────────────
        session_id = str(uuid.uuid4())

        # ── Execute indexing ────────────────────────────────────────────
        logger.info("Indexing target: %s", target_path)
        entry = index_path(
            target_path,
            config,
            delete_queue=delete_queue,
            progress_callback=progress_cb,
            cancel_event=cancel_event,
            session_id=session_id,
        )

        # ── In-place output ─────────────────────────────────────────────
        # Written BEFORE rename so the rename phase can also rename
        # the sidecar file from {original}_meta2.json to
        # {storage_name}_meta2.json.  (Batch 6, §4.)
        if config.output_inplace:
            _write_inplace_tree(entry, target_path, write_inplace)

        # ── Rename (spec section 6.10) ──────────────────────────────────
        if config.rename and entry.type == "file":
            result_path = rename_item(target_path, entry, dry_run=config.dry_run)
            if not config.dry_run and config.output_inplace and result_path != target_path:
                from shruggie_indexer.core.rename import rename_inplace_sidecar
                rename_inplace_sidecar(target_path, entry)
        elif config.rename and entry.items is not None:
            _rename_tree(entry, target_path, config)

        # ── Aggregate output (stdout + outfile) ─────────────────────────
        write_output(entry, config)

        # ── MetaMergeDelete: drain deletion queue (Stage 6) ─────────────
        if delete_queue:
            deleted = _drain_delete_queue(delete_queue)
            logger.info("Deleted %d merged sidecar files", deleted)

        logger.info("Indexing complete.")
        sys.exit(ExitCode.SUCCESS)

    except IndexerCancellationError:
        logger.warning("Operation interrupted — exiting cleanly.")
        sys.exit(ExitCode.INTERRUPTED)

    except IndexerConfigError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(ExitCode.CONFIGURATION_ERROR)

    except IndexerTargetError as exc:
        logger.error("Target error: %s", exc)
        sys.exit(ExitCode.TARGET_ERROR)

    except KeyboardInterrupt:
        logger.warning("Forced termination.")
        sys.exit(ExitCode.INTERRUPTED)

    except SystemExit:
        raise

    except Exception:
        logger.exception("Unexpected error during indexing")
        sys.exit(ExitCode.RUNTIME_ERROR)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_inplace_tree(
    entry: Any,
    root_path: Path,
    write_fn: Any,
    *,
    _is_root: bool = True,
) -> None:
    """Recursively write in-place sidecar files for an entry tree.

    Walks the ``items`` tree and writes a sidecar file for each entry.
    The root directory entry is skipped because its in-place sidecar
    (written inside the target) duplicates the aggregate output file
    (written alongside the target).  Child sidecars are unaffected.
    """
    if entry.type == "file":
        item_path = root_path.parent / entry.file_system.relative
        write_fn(entry, item_path, "file")
    elif entry.type == "directory":
        if not _is_root:
            dir_path = root_path.parent / entry.file_system.relative
            write_fn(entry, dir_path, "directory")
        if entry.items:
            for child in entry.items:
                _write_inplace_tree(child, root_path, write_fn, _is_root=False)


def _rename_tree(
    entry: Any,
    root_path: Path,
    config: Any,
) -> None:
    """Recursively rename all file entries in the tree.

    Mirrors the recursive traversal of ``_write_inplace_tree`` but
    performs rename operations instead of sidecar writes.  Directories
    are not renamed (spec §6.10).

    Path reconstruction uses ``root_path.parent / relative`` — the
    same formula used by ``_write_inplace_tree`` — because
    ``file_system.relative`` is computed relative to the *parent*
    of the target directory (the ``index_root``).
    """
    from shruggie_indexer.core.rename import rename_item

    if entry.items is None:
        return
    for child in entry.items:
        if child.type == "file":
            child_path = root_path.parent / child.file_system.relative
            storage_name = child.attributes.storage_name
            logger.debug(
                "Rename candidate: %s (type=%s, storage_name=%s)",
                child_path, child.type, storage_name,
            )
            try:
                result_path = rename_item(child_path, child, dry_run=config.dry_run)
                # Rename the in-place sidecar to match (Batch 6, §4).
                # Skip sidecar rename when the content file was collision-skipped.
                if not config.dry_run and config.output_inplace and result_path != child_path:
                    from shruggie_indexer.core.rename import rename_inplace_sidecar
                    rename_inplace_sidecar(child_path, child)
            except Exception:
                logger.warning(
                    "Rename failed for %s", child_path, exc_info=True,
                )
        elif child.type == "directory":
            if child.items:
                logger.debug(
                    "Rename candidate: %s (type=directory, descending, %d items)",
                    child.name.text, len(child.items),
                )
                _rename_tree(child, root_path, config)
            else:
                logger.debug(
                    "Rename candidate: %s (type=directory, skip_reason=no items)",
                    child.name.text,
                )

"""CLI rollback subcommand for shruggie-indexer.

Provides a thin Click command that delegates to the core rollback engine
(:mod:`~shruggie_indexer.core.rollback`).  Handles argument parsing, default
resolution (e.g. ``--target`` defaults to the parent of the meta2 path), and
human-readable output formatting.

See spec sections 3.1–3.7 of batch 005 for the full design.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import click

from shruggie_indexer.cli.main import (
    ExitCode,
    _install_signal_handlers,
    configure_logging,
)

__all__ = ["rollback_cmd"]


# ---------------------------------------------------------------------------
# Output formatting helpers
# ---------------------------------------------------------------------------


def _print_plan_summary(plan) -> None:  # noqa: ANN001 — avoid core import at module level
    """Print a human-readable summary of the rollback plan before execution."""
    stats = plan.stats
    lines: list[str] = []
    lines.append("Rollback plan:")
    lines.append(f"  Entries loaded:       {stats.total_entries}")
    lines.append(f"  Files to restore:     {stats.files_to_restore}")
    if stats.duplicates_to_restore:
        lines.append(f"  Duplicates to restore:{stats.duplicates_to_restore}")
    if stats.sidecars_to_restore:
        lines.append(f"  Sidecars to restore:  {stats.sidecars_to_restore}")
    if stats.directories_to_create:
        lines.append(f"  Directories to create:{stats.directories_to_create}")
    skipped_total = (
        stats.skipped_unresolvable
        + stats.skipped_conflict
        + stats.skipped_already_exists
    )
    if skipped_total:
        lines.append(f"  Skipped:              {skipped_total}")
    click.echo("\n".join(lines), err=True)


def _print_result_summary(result) -> None:  # noqa: ANN001
    """Print a human-readable summary of the rollback execution result."""
    parts: list[str] = []
    parts.append(f"{result.restored} restored")
    if result.duplicates_restored:
        parts.append(f"{result.duplicates_restored} duplicates")
    if result.sidecars_restored:
        parts.append(f"{result.sidecars_restored} sidecars")
    if result.directories_created:
        parts.append(f"{result.directories_created} directories")
    if result.skipped:
        parts.append(f"{result.skipped} skipped")
    if result.failed:
        parts.append(f"{result.failed} failed")
    click.echo(f"Rollback complete: {', '.join(parts)}.", err=True)

    if result.errors:
        click.echo("", err=True)
        click.echo("Errors:", err=True)
        for error in result.errors:
            click.echo(f"  - {error}", err=True)


# ---------------------------------------------------------------------------
# rollback subcommand
# ---------------------------------------------------------------------------


@click.command("rollback")
@click.argument(
    "meta2_path",
    type=click.Path(exists=True),
)
@click.option(
    "-t",
    "--target",
    type=click.Path(),
    default=None,
    help=(
        "Target directory for restored files. "
        "[default: parent directory of META2_PATH]"
    ),
)
@click.option(
    "--source",
    type=click.Path(exists=True),
    default=None,
    help="Explicit source directory containing content files.",
)
@click.option(
    "--recursive",
    is_flag=True,
    default=False,
    help=(
        "Search META2_PATH subdirectories for sidecar files "
        "(only when META2_PATH is a directory)."
    ),
)
@click.option(
    "--flat",
    is_flag=True,
    default=False,
    help=(
        "Restore files using original names only, without "
        "reconstructing directory structure."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview restore operations without writing.",
)
@click.option(
    "--no-verify",
    is_flag=True,
    default=False,
    help="Skip hash verification of source files.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing files in target directory.",
)
@click.option(
    "--skip-duplicates",
    is_flag=True,
    default=False,
    help="Do not restore files from duplicates[] arrays.",
)
@click.option(
    "--no-restore-sidecars",
    is_flag=True,
    default=False,
    help="Do not restore absorbed sidecar metadata files.",
)
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
def rollback_cmd(
    meta2_path: str,
    target: str | None,
    source: str | None,
    recursive: bool,
    flat: bool,
    dry_run: bool,
    no_verify: bool,
    force: bool,
    skip_duplicates: bool,
    no_restore_sidecars: bool,
    verbose: int,
    quiet: bool,
    log_file: str | None,
) -> None:
    """Restore files from shruggie-indexer metadata to their original names and directory structure."""
    from shruggie_indexer.core.rollback import (
        execute_rollback,
        load_meta2,
        plan_rollback,
    )
    from shruggie_indexer.exceptions import (
        IndexerCancellationError,
        IndexerConfigError,
        IndexerTargetError,
    )

    # ── Logging ─────────────────────────────────────────────────────────
    configure_logging(verbose=verbose, quiet=quiet, log_file=log_file)

    # ── Signal handling ─────────────────────────────────────────────────
    cancel_event = threading.Event()
    _install_signal_handlers(cancel_event)

    try:
        meta2 = Path(meta2_path).resolve()

        # 1. Resolve target default
        if target is None:
            target_dir = meta2.parent if meta2.is_file() else meta2
        else:
            target_dir = Path(target).resolve()

        # Validate target directory is writable (or creatable)
        if target_dir.exists() and not target_dir.is_dir():
            click.echo(
                f"ERROR: Target path exists but is not a directory: {target_dir}",
                err=True,
            )
            sys.exit(ExitCode.TARGET_ERROR)

        # 2. Load
        entries = load_meta2(meta2, recursive=recursive)

        # 3. Resolve source directory
        #    When --source is not specified, default to the directory containing
        #    the meta2 file (for file inputs) or the directory itself (for
        #    directory inputs).  This is where the content files live alongside
        #    their sidecars.
        if source:
            source_dir = Path(source).resolve()
        elif meta2.is_file():
            source_dir = meta2.parent
        else:
            source_dir = meta2

        # 4. Plan
        plan = plan_rollback(
            entries,
            target_dir=target_dir,
            source_dir=source_dir,
            verify=not no_verify,
            force=force,
            flat=flat,
            skip_duplicates=skip_duplicates,
            restore_sidecars=not no_restore_sidecars,
        )

        # 5. Report plan warnings
        for warning in plan.warnings:
            click.echo(f"WARNING: {warning}", err=True)

        _print_plan_summary(plan)

        # 6. Execute (or dry-run)
        result = execute_rollback(
            plan,
            dry_run=dry_run,
            cancel_event=cancel_event,
        )

        # 7. Report result
        _print_result_summary(result)

        sys.exit(ExitCode.SUCCESS if result.failed == 0 else ExitCode.PARTIAL_FAILURE)

    except IndexerCancellationError:
        click.echo("Operation interrupted — exiting cleanly.", err=True)
        sys.exit(ExitCode.INTERRUPTED)

    except IndexerConfigError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        sys.exit(ExitCode.CONFIGURATION_ERROR)

    except IndexerTargetError as exc:
        click.echo(f"Target error: {exc}", err=True)
        sys.exit(ExitCode.TARGET_ERROR)

    except KeyboardInterrupt:
        click.echo("Forced termination.", err=True)
        sys.exit(ExitCode.INTERRUPTED)

    except SystemExit:
        raise

    except Exception as exc:
        click.echo(f"Unexpected error: {exc}", err=True)
        sys.exit(ExitCode.RUNTIME_ERROR)

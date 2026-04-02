"""Legacy output cleanup for v4 in-place index artifacts.

Deletes obsolete legacy indexer outputs only when the matching v4 output file
was successfully written in the current run. This is intentionally narrower
than the old stale-artifact sweep: it does not scan unrelated directories and
it never removes orphaned legacy files for items the current run did not touch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

from shruggie_indexer.core.constants import OUTPUT_SUFFIX_DIR, OUTPUT_SUFFIX_FILE
from shruggie_indexer.core.paths import build_sidecar_path

__all__ = ["cleanup_legacy_outputs"]

logger = logging.getLogger(__name__)

_LEGACY_FILE_SUFFIXES = ("_meta.json", "_meta2.json", "_meta3.json")
_LEGACY_DIRECTORY_SUFFIXES = (
    "_directorymeta.json",
    "_directorymeta2.json",
    "_directorymeta3.json",
)


def _iter_current_run_outputs(
    entry: Any,
    root_path: Path,
    *,
    write_directory_meta: bool,
    _is_root: bool = True,
) -> Iterator[tuple[Path, str]]:
    if entry.type == "file":
        item_path = root_path / entry.file_system.relative
        candidates = [build_sidecar_path(item_path, "file")]
        storage_name = getattr(getattr(entry, "attributes", None), "storage_name", "")
        if storage_name:
            candidates.append(item_path.parent / f"{storage_name}{OUTPUT_SUFFIX_FILE}")
        for candidate in candidates:
            if candidate.exists():
                yield candidate, "file"
        return

    if entry.type != "directory":
        return

    if not _is_root and write_directory_meta:
        dir_path = root_path / entry.file_system.relative
        candidate = build_sidecar_path(dir_path, "directory")
        if candidate.exists():
            yield candidate, "directory"

    for child in getattr(entry, "items", None) or []:
        yield from _iter_current_run_outputs(
            child,
            root_path,
            write_directory_meta=write_directory_meta,
            _is_root=False,
        )


def _legacy_candidates(output_path: Path, item_type: str) -> list[Path]:
    if item_type == "directory":
        base_name = output_path.name.removesuffix(OUTPUT_SUFFIX_DIR)
        return [
            output_path.parent / f"{base_name}{suffix}" for suffix in _LEGACY_DIRECTORY_SUFFIXES
        ]

    base_name = output_path.name.removesuffix(OUTPUT_SUFFIX_FILE)
    return [output_path.parent / f"{base_name}{suffix}" for suffix in _LEGACY_FILE_SUFFIXES]


def cleanup_legacy_outputs(
    entry: Any,
    root_path: Path,
    *,
    write_directory_meta: bool,
) -> int:
    """Delete matching legacy outputs for v4 files written in this run.

    Args:
        entry: Root entry or entry tree from the current indexing run.
        root_path: Directory used as the base for in-place output.
        write_directory_meta: Whether directory-level ``_idxd.json`` files were written.

    Returns:
        Count of removed legacy files.
    """
    deleted = 0
    seen: set[Path] = set()

    for output_path, item_type in _iter_current_run_outputs(
        entry,
        root_path,
        write_directory_meta=write_directory_meta,
    ):
        for legacy_path in _legacy_candidates(output_path, item_type):
            if legacy_path in seen or not legacy_path.exists():
                continue
            seen.add(legacy_path)
            try:
                legacy_path.unlink()
                logger.info("Legacy output removed: %s", legacy_path)
                deleted += 1
            except OSError as exc:
                logger.warning("Failed to remove legacy output %s: %s", legacy_path, exc)

    return deleted

"""Filesystem traversal and discovery for shruggie-indexer.

Provides a single traversal function that enumerates immediate children of a
directory, applying configurable exclusion filters and returning separate
sorted lists of files and directories.

This replaces the original's two near-identical traversal paths
(``MakeDirectoryIndexRecursiveLogic`` / ``MakeDirectoryIndexLogic``) with a
single ``list_children()`` function (DEV-03).  The caller controls recursion
depth — this module does not recurse.

The exclusion filter set covers Windows, macOS, and Linux filesystem artifacts
via externalized configuration (DEV-10), replacing the original's hardcoded
``$RECYCLE.BIN`` and ``System Volume Information`` filters.

See spec §6.1 for full behavioral guidance.
"""

from __future__ import annotations

import fnmatch
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from shruggie_indexer.config.types import IndexerConfig

__all__ = [
    "list_children",
]

logger = logging.getLogger(__name__)


def list_children(
    directory: Path,
    config: IndexerConfig,
) -> tuple[list[Path], list[Path]]:
    """Enumerate immediate children of a directory.

    Uses ``os.scandir()`` in a single pass for efficient classification.
    Symlinks are classified based on the link itself (``follow_symlinks=False``),
    not the target.  Items matching the configured exclusion filters are
    omitted from both returned lists.

    The caller (``core/entry.build_directory_entry()``) invokes this once per
    directory.  For recursive mode the caller recurses into each returned
    subdirectory; for flat mode only immediate children are used.

    Args:
        directory: Absolute path to the directory to enumerate.
        config: The active :class:`~shruggie_indexer.config.types.IndexerConfig`.

    Returns:
        A ``(files, directories)`` tuple.  Each list is sorted
        lexicographically by name (case-insensitive).  Files appear before
        directories in processing order, though they are returned separately.

    Raises:
        PermissionError: If the directory cannot be opened.
        OSError: If ``os.scandir()`` fails for the directory.
    """
    files: list[Path] = []
    directories: list[Path] = []

    excludes = config.filesystem_excludes
    exclude_globs = config.filesystem_exclude_globs

    with os.scandir(directory) as scanner:
        for entry in scanner:
            # --- Exclusion filtering ---
            name_lower = entry.name.lower()

            # O(1) set membership against lowercased exclusion names.
            if name_lower in excludes:
                logger.debug("Excluded by name filter: %s", entry.path)
                continue

            # Glob pattern matching for pattern-based exclusions.
            if _matches_glob(name_lower, exclude_globs):
                logger.debug("Excluded by glob filter: %s", entry.path)
                continue

            # --- Classification ---
            try:
                if entry.is_file(follow_symlinks=False):
                    files.append(directory / entry.name)
                elif entry.is_dir(follow_symlinks=False):
                    directories.append(directory / entry.name)
                elif entry.is_symlink():
                    # Symlink that is neither file nor directory when not
                    # following links.  Classify by resolving the target type.
                    try:
                        if entry.is_file(follow_symlinks=True):
                            files.append(directory / entry.name)
                        elif entry.is_dir(follow_symlinks=True):
                            directories.append(directory / entry.name)
                        else:
                            # Dangling or unresolvable symlink — treat as file.
                            files.append(directory / entry.name)
                    except OSError:
                        # Dangling symlink — treat as file.
                        files.append(directory / entry.name)
                else:
                    # Special file (socket, device, etc.) — skip silently.
                    logger.debug("Skipping special file: %s", entry.path)
            except OSError as exc:
                logger.warning(
                    "Cannot classify entry %s — skipping: %s",
                    entry.path,
                    exc,
                )

    # Sort lexicographically by name, case-insensitive.
    files.sort(key=lambda p: p.name.lower())
    directories.sort(key=lambda p: p.name.lower())

    return files, directories


def _matches_glob(name_lower: str, patterns: tuple[str, ...]) -> bool:
    """Test a lowercased name against glob exclusion patterns.

    Uses ``fnmatch.fnmatch()`` with lowercased patterns for case-insensitive
    matching.
    """
    return any(fnmatch.fnmatch(name_lower, pattern.lower()) for pattern in patterns)

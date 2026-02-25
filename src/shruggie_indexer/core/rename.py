"""File rename operations for shruggie-indexer.

Implements the ``StorageName`` rename operation: renames files and directories
from their original names to their deterministic, hash-based ``storage_name``
values (spec section 5.8).

The rename operation is destructive — the original filename is replaced on
disk — but the original name is preserved in the ``IndexEntry.name.text``
field of the in-place sidecar file that is always written alongside a rename.

See spec section 6.10 for full behavioral guidance.
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import TYPE_CHECKING

from shruggie_indexer.core.paths import build_storage_path
from shruggie_indexer.exceptions import RenameError

if TYPE_CHECKING:
    from pathlib import Path

    from shruggie_indexer.models.schema import IndexEntry

__all__ = [
    "rename_item",
]

logger = logging.getLogger(__name__)


def rename_item(
    original_path: Path,
    entry: IndexEntry,
    *,
    dry_run: bool = False,
) -> Path:
    """Rename a file or directory to its ``storage_name``.

    Returns the new path after renaming.  If ``dry_run=True``, returns
    the would-be new path without performing the rename.

    Collision detection:
      - If the target path exists and is a **different** inode, raises
        ``RenameError`` to prevent data loss.
      - If the target path exists and is the **same** inode (already
        renamed in a previous run), the rename is a no-op.

    Cross-filesystem moves fall back to ``shutil.move()`` when
    ``Path.rename()`` raises ``OSError`` (should not occur in normal
    usage since the target is in the same directory).

    Args:
        original_path: Absolute path to the item to rename.
        entry: The completed ``IndexEntry`` containing ``attributes.storage_name``.
        dry_run: When ``True``, compute and return the target path without
            performing the rename.

    Returns:
        The new :class:`~pathlib.Path` after renaming (or the would-be path
        in dry-run mode).

    Raises:
        RenameError: If the target path already exists and is not the same
            file (collision detected).
    """
    storage_name = entry.attributes.storage_name
    target_path = build_storage_path(original_path, storage_name)

    if dry_run:
        logger.info(
            "Dry run — would rename: %s → %s", original_path.name, storage_name,
        )
        return target_path

    # Collision detection
    if target_path.exists():
        try:
            src_stat = os.stat(original_path)
            dst_stat = os.stat(target_path)
        except OSError as exc:
            raise RenameError(
                f"Cannot stat paths for collision check: "
                f"{original_path} → {target_path}: {exc}"
            ) from exc

        # Same inode = already renamed (no-op)
        if _same_inode(src_stat, dst_stat):
            logger.debug(
                "Rename no-op (same inode): %s already is %s",
                original_path,
                target_path,
            )
            return target_path

        # Different inode = collision
        raise RenameError(
            f"Rename collision: target {target_path} already exists "
            f"and is a different file than {original_path}"
        )

    # Perform the rename
    try:
        renamed = original_path.rename(target_path)
        logger.info("File renamed: %s → %s", original_path.name, storage_name)
        return renamed
    except OSError:
        # Cross-filesystem fallback
        logger.warning(
            "Path.rename() failed, falling back to shutil.move: %s → %s",
            original_path,
            target_path,
        )
        try:
            result = shutil.move(str(original_path), str(target_path))
            logger.info(
                "File renamed (fallback): %s → %s",
                original_path.name, storage_name,
            )
            return type(original_path)(result)
        except Exception as move_exc:
            logger.error(
                "File rename FAILED: %s → %s: %s",
                original_path, target_path, move_exc,
            )
            raise RenameError(
                f"Both Path.rename() and shutil.move() failed: "
                f"{original_path} → {target_path}: {move_exc}"
            ) from move_exc


def _same_inode(a: os.stat_result, b: os.stat_result) -> bool:
    """Check whether two stat results refer to the same inode.

    On Windows, ``st_ino`` may be zero for some filesystems (e.g. FAT32).
    When both values are zero, fall back to comparing device + file index
    (which may also be zero — in that case we conservatively return
    ``False`` to avoid suppressing a real collision).
    """
    if a.st_ino != 0 and b.st_ino != 0:
        return a.st_ino == b.st_ino and a.st_dev == b.st_dev

    # Windows fallback: both zero means we cannot determine sameness.
    return False

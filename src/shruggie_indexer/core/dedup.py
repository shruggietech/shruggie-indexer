"""Provenance-preserving de-duplication for shruggie-indexer.

Provides session-scoped de-duplication of files with identical content hashes
(identical ``storage_name`` values) during rename operations. When multiple
files share the same content hash, the first file encountered is designated
the **canonical** copy; subsequent duplicates are absorbed into the canonical
entry's ``duplicates`` array, preserving their complete identity metadata.

This module is designed for standalone importability by downstream projects
(specifically ``shruggie-catalog``). It operates on ``IndexEntry`` objects and
has no dependencies on CLI, GUI, or filesystem I/O.

Usage (indexer — single session)::

    registry = DedupRegistry()
    actions = scan_tree(root_entry, registry)
    apply_dedup(actions)
    # registry is discarded when the process exits

Usage (catalog — cross-session)::

    registry = DedupRegistry()
    for existing in catalog.get_all_entries():
        registry.register(existing)
    actions = scan_tree(new_batch_root, registry)
    apply_dedup(actions)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shruggie_indexer.models.schema import IndexEntry

__all__ = [
    "DedupAction",
    "DedupRegistry",
    "DedupResult",
    "DedupStats",
    "apply_dedup",
    "cleanup_duplicate_files",
    "scan_tree",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DedupResult:
    """Result of checking an entry against the dedup registry."""

    is_duplicate: bool
    canonical_entry: IndexEntry | None = None
    """The canonical entry if this is a duplicate; ``None`` if this is canonical."""


@dataclass
class DedupStats:
    """Summary statistics for a dedup pass."""

    total_files_scanned: int = 0
    unique_files: int = 0
    duplicates_found: int = 0
    bytes_reclaimed: int = 0
    """Sum of duplicate file sizes (``entry.size.bytes``)."""


@dataclass
class DedupAction:
    """A pending de-duplication action identified by ``scan_tree()``."""

    duplicate_entry: IndexEntry
    canonical_entry: IndexEntry
    duplicate_relative_path: str
    """``file_system.relative`` of the duplicate."""
    canonical_storage_name: str
    """``storage_name`` of the canonical entry."""
    parent_entry: IndexEntry | None = None
    """Parent directory entry that contains the duplicate in its ``items``."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class DedupRegistry:
    """Session-scoped registry for content-addressed de-duplication.

    Tracks which content hashes have been seen and which ``IndexEntry`` is
    the canonical representative for each hash. Designed for single-session
    use within the indexer and for cross-session reuse by ``shruggie-catalog``.

    The registry key is the ``storage_name`` (which encodes both the content
    hash and the file extension). This means two files with identical bytes
    but different extensions (e.g., ``photo.jpg`` and ``photo.jpeg``) are
    treated as distinct — they produce different ``storage_name`` values
    and are not considered duplicates. This is correct: content-addressed
    identity in the ShruggieTech ecosystem includes the extension as part
    of the storage key.
    """

    def __init__(self) -> None:
        self._registry: dict[str, IndexEntry] = {}
        self._stats = DedupStats()

    def check(self, entry: IndexEntry) -> DedupResult:
        """Check whether *entry* is a duplicate.

        If the entry's ``storage_name`` has not been seen, registers it as
        the canonical copy and returns a non-duplicate result. Otherwise,
        returns a duplicate result with a reference to the canonical entry.
        """
        storage_name = entry.attributes.storage_name
        self._stats.total_files_scanned += 1

        if storage_name in self._registry:
            canonical = self._registry[storage_name]
            self._stats.duplicates_found += 1
            self._stats.bytes_reclaimed += entry.size.bytes
            return DedupResult(is_duplicate=True, canonical_entry=canonical)

        # First encounter — register as canonical
        self._registry[storage_name] = entry
        self._stats.unique_files += 1
        return DedupResult(is_duplicate=False, canonical_entry=None)

    def register(self, entry: IndexEntry) -> None:
        """Explicitly register an entry as canonical.

        Used by ``shruggie-catalog`` to pre-populate the registry from
        existing database entries before scanning a new batch.
        """
        storage_name = entry.attributes.storage_name
        if storage_name not in self._registry:
            self._registry[storage_name] = entry

    def merge(self, canonical: IndexEntry, duplicate: IndexEntry) -> None:
        """Merge *duplicate* into *canonical*'s ``duplicates`` list."""
        if canonical.duplicates is None:
            canonical.duplicates = []
        canonical.duplicates.append(duplicate)

    @property
    def stats(self) -> DedupStats:
        """Return a snapshot of the current dedup statistics."""
        return DedupStats(
            total_files_scanned=self._stats.total_files_scanned,
            unique_files=self._stats.unique_files,
            duplicates_found=self._stats.duplicates_found,
            bytes_reclaimed=self._stats.bytes_reclaimed,
        )


# ---------------------------------------------------------------------------
# Tree scanning
# ---------------------------------------------------------------------------


def scan_tree(
    root_entry: IndexEntry,
    registry: DedupRegistry,
) -> list[DedupAction]:
    """Walk an ``IndexEntry`` tree and identify all duplicates.

    Returns a list of ``DedupAction`` objects describing what needs to happen.
    Does NOT mutate entries or touch the filesystem — that is the caller's
    responsibility.

    This function is the primary entry point for both indexer (single-session)
    and catalog (cross-session) use cases. The caller controls the registry
    lifetime: the indexer creates a fresh registry per run; the catalog
    maintains a persistent registry across runs.

    Args:
        root_entry: The root of the IndexEntry tree to scan.
        registry: The dedup registry to populate/query.

    Returns:
        A list of DedupAction objects, one per duplicate found.
    """
    actions: list[DedupAction] = []
    _scan_recursive(root_entry, registry, actions, parent=None)
    return actions


def _scan_recursive(
    entry: IndexEntry,
    registry: DedupRegistry,
    actions: list[DedupAction],
    parent: IndexEntry | None,
) -> None:
    """Recursively scan the entry tree for duplicates."""
    if entry.type == "file":
        result = registry.check(entry)
        if result.is_duplicate and result.canonical_entry is not None:
            actions.append(
                DedupAction(
                    duplicate_entry=entry,
                    canonical_entry=result.canonical_entry,
                    duplicate_relative_path=entry.file_system.relative,
                    canonical_storage_name=result.canonical_entry.attributes.storage_name,
                    parent_entry=parent,
                ),
            )
            logger.info(
                "Duplicate found: %s at %s (identical to %s)",
                entry.name.text,
                entry.file_system.relative,
                result.canonical_entry.attributes.storage_name,
            )
    elif entry.type == "directory" and entry.items:
        for child in entry.items:
            _scan_recursive(child, registry, actions, parent=entry)


# ---------------------------------------------------------------------------
# Apply dedup actions
# ---------------------------------------------------------------------------


def apply_dedup(actions: list[DedupAction]) -> None:
    """Apply de-duplication actions to the entry tree.

    For each action, merges the duplicate's ``IndexEntry`` into the canonical
    entry's ``duplicates`` list and removes the duplicate from its parent's
    ``items`` array.

    Does NOT touch the filesystem. File deletion and sidecar cleanup are
    handled by the caller (the rename phase in the CLI/GUI pipeline).
    """
    for action in actions:
        # Merge duplicate into canonical
        canonical = action.canonical_entry
        duplicate = action.duplicate_entry

        if canonical.duplicates is None:
            canonical.duplicates = []
        canonical.duplicates.append(duplicate)

        # Remove duplicate from parent's items
        if action.parent_entry is not None and action.parent_entry.items is not None:
            try:
                action.parent_entry.items.remove(duplicate)
            except ValueError:
                logger.warning(
                    "Duplicate entry %s not found in parent items during removal",
                    duplicate.name.text,
                )


# ---------------------------------------------------------------------------
# Filesystem cleanup
# ---------------------------------------------------------------------------


def cleanup_duplicate_files(
    actions: list[DedupAction],
    root_path: Path,
    *,
    dry_run: bool = False,
) -> None:
    """Delete duplicate files from disk after dedup merge.

    Called after the rename phase. Each action's ``duplicate_relative_path``
    identifies a file that was merged into a canonical entry's ``duplicates``
    array and should no longer exist on disk.

    Args:
        actions: The list of dedup actions from ``scan_tree()``.
        root_path: The root path of the indexed tree (the target path).
        dry_run: If ``True``, log what would be deleted without deleting.
    """
    for action in actions:
        # Reconstruct the full path to the duplicate file
        file_path = root_path.parent / action.duplicate_relative_path

        if dry_run:
            logger.info(
                "Dry run \u2014 would deduplicate: %s at %s (duplicate of %s)",
                action.duplicate_entry.name.text,
                action.duplicate_relative_path,
                action.canonical_storage_name,
            )
            continue

        # Delete the duplicate file
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(
                    "Duplicate removed: %s at %s (provenance preserved in %s)",
                    action.duplicate_entry.name.text,
                    action.duplicate_relative_path,
                    action.canonical_storage_name,
                )
        except OSError as exc:
            logger.warning(
                "Failed to delete duplicate file: %s: %s",
                file_path,
                exc,
            )

        # Safety net: delete orphaned sidecar if it exists
        sidecar_path = file_path.parent / f"{file_path.name}_meta2.json"
        try:
            if sidecar_path.exists():
                sidecar_path.unlink()
                logger.debug("Orphaned sidecar deleted: %s", sidecar_path)
        except OSError:
            pass


def format_bytes(n: int) -> str:
    """Format a byte count as a human-readable string."""
    if n < 1000:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n_f = n / 1000
        if n_f < 1000 or unit == "TB":
            return f"{n_f:.2f} {unit}"
        n = int(n_f)
    return f"{n} B"  # pragma: no cover

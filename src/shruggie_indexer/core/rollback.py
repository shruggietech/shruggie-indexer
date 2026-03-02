"""Core rollback engine for shruggie-indexer.

Reverses indexer rename and de-duplication operations by reading ``_meta2.json``
sidecar files and restoring files to their original names, directory structure,
and timestamps.  Also reconstructs absorbed sidecar metadata files that were
consumed by MetaMergeDelete, and restores deduplicated files by copying
canonical bytes to each duplicate's original path.

This module is designed for standalone importability by downstream projects
(specifically ``shruggie-vault``).  It operates on :class:`IndexEntry` objects
and filesystem paths, and has no dependencies on CLI, GUI, or presentation
layer code.

Architecture follows the **plan-then-execute** pattern established by
:mod:`~shruggie_indexer.core.dedup`:

1.  :func:`load_meta2` — parse ``_meta2.json`` files into a flat
    ``list[IndexEntry]``.
2.  :func:`plan_rollback` — compute the full operation graph without
    touching the filesystem.
3.  :func:`execute_rollback` — carry out the plan (or dry-run it).

Usage::

    entries = load_meta2(Path("vault/yAAA.jpg_meta2.json"))
    plan = plan_rollback(entries, target_dir=Path("restored/"))
    result = execute_rollback(plan)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol

from shruggie_indexer.exceptions import IndexerConfigError, IndexerTargetError
from shruggie_indexer.models.schema import (
    AttributesObject,
    FileSystemObject,
    HashSet,
    IndexEntry,
    MetadataAttributes,
    MetadataEntry,
    NameObject,
    ParentObject,
    SizeObject,
    TimestampPair,
    TimestampsObject,
)

if TYPE_CHECKING:
    from shruggie_indexer.core.progress import ProgressEvent

__all__ = [
    "LocalSourceResolver",
    "RollbackAction",
    "RollbackPlan",
    "RollbackResult",
    "RollbackStats",
    "SourceResolver",
    "discover_meta2_files",
    "execute_rollback",
    "load_meta2",
    "plan_rollback",
    "verify_file_hash",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RollbackAction:
    """A single file restoration action within a rollback plan."""

    source_path: Path | None
    """Where the content bytes currently live.  ``None`` if unresolvable."""

    target_path: Path
    """Where they should be restored to."""

    entry: IndexEntry
    """The :class:`IndexEntry` driving this action."""

    action_type: str
    """One of: ``'restore'``, ``'duplicate_restore'``, ``'sidecar_restore'``, ``'mkdir'``."""

    skip_reason: str | None = None
    """Non-``None`` if this action will be skipped.  Contains the reason."""

    verified: bool = False
    """Whether the source file's hash was checked against the sidecar."""

    sidecar_data: bytes | str | None = None
    """Pre-decoded sidecar content for ``sidecar_restore`` actions."""

    sidecar_binary: bool = False
    """Whether ``sidecar_data`` is binary (base64-decoded)."""

    metadata_entry: MetadataEntry | None = None
    """The :class:`MetadataEntry` for ``sidecar_restore`` actions."""


@dataclass
class RollbackStats:
    """Summary statistics for a rollback plan or execution result."""

    total_entries: int = 0
    files_to_restore: int = 0
    duplicates_to_restore: int = 0
    sidecars_to_restore: int = 0
    directories_to_create: int = 0
    skipped_unresolvable: int = 0
    skipped_conflict: int = 0
    skipped_already_exists: int = 0


@dataclass
class RollbackPlan:
    """Complete plan for a rollback operation, computed before execution."""

    actions: list[RollbackAction]
    stats: RollbackStats
    warnings: list[str]


@dataclass
class RollbackResult:
    """Outcome of executing a rollback plan."""

    restored: int = 0
    duplicates_restored: int = 0
    sidecars_restored: int = 0
    directories_created: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Duplicate annotation wrapper
# ---------------------------------------------------------------------------


@dataclass
class _DuplicateAnnotation:
    """Transient annotation attached to entries extracted from duplicates[]."""

    is_duplicate: bool = False
    canonical_storage_name: str = ""
    entry_ref: IndexEntry | None = None  # Strong ref prevents id() reuse


# Module-level dict mapping id(entry) → annotation.  This avoids
# monkey-patching the IndexEntry dataclass.  The stored ``entry_ref``
# keeps the object alive so ``id()`` is never recycled while the
# annotation exists, and the ``is`` identity check in ``_is_duplicate``
# prevents false positives if the dict is stale.
_annotations: dict[int, _DuplicateAnnotation] = {}


def _mark_duplicate(entry: IndexEntry, canonical_storage_name: str) -> None:
    """Annotate *entry* as a duplicate of the given canonical."""
    _annotations[id(entry)] = _DuplicateAnnotation(
        is_duplicate=True,
        canonical_storage_name=canonical_storage_name,
        entry_ref=entry,
    )


def _is_duplicate(entry: IndexEntry) -> bool:
    ann = _annotations.get(id(entry))
    return ann is not None and ann.is_duplicate and ann.entry_ref is entry


def _canonical_storage_name(entry: IndexEntry) -> str:
    ann = _annotations.get(id(entry))
    if ann is None or ann.entry_ref is not entry:
        return entry.attributes.storage_name
    return ann.canonical_storage_name


# ---------------------------------------------------------------------------
# Source resolver protocol & default implementation
# ---------------------------------------------------------------------------


class SourceResolver(Protocol):
    """Protocol for locating content files during rollback.

    Implementations provide the bytes for a given :class:`IndexEntry`.  The
    default implementation searches the local filesystem.  Downstream tools
    (vault) provide implementations that retrieve bytes from remote storage.
    """

    def resolve(self, entry: IndexEntry, search_dir: Path | None) -> Path | None:
        """Return the local path to the content file, or ``None`` if not found.

        For remote resolvers, this may involve downloading the file to a
        temporary location and returning that path.
        """
        ...


class LocalSourceResolver:
    """Locate content files on the local filesystem.

    Search strategy (tried in order):

    1. Look for ``storage_name`` in *search_dir* — handles renamed files.
    2. Look for ``name.text`` in *search_dir*, verify hash if found — handles
       non-renamed files.

    Returns ``None`` if neither match succeeds.
    """

    def __init__(self, *, verify_hash: bool = True) -> None:
        self._verify_hash = verify_hash

    def resolve(self, entry: IndexEntry, search_dir: Path | None) -> Path | None:
        if search_dir is None:
            return None

        # Strategy 1: storage_name match (renamed file)
        storage_path = search_dir / entry.attributes.storage_name
        if storage_path.is_file():
            if self._verify_hash and entry.hashes is not None:
                self._check_hash(storage_path, entry)
            return storage_path

        # Strategy 2: original name match (non-renamed file)
        if entry.name.text is not None:
            original_path = search_dir / entry.name.text
            if original_path.is_file():
                if self._verify_hash and entry.hashes is not None:
                    self._check_hash(original_path, entry)
                return original_path

        return None

    @staticmethod
    def _check_hash(path: Path, entry: IndexEntry) -> None:
        """Log a warning if the file hash doesn't match the sidecar."""
        if entry.hashes is None:
            return
        algorithm = entry.id_algorithm
        if not verify_file_hash(path, entry.hashes, algorithm):
            expected = getattr(entry.hashes, algorithm, "?")
            logger.warning(
                "Hash mismatch: %s — expected %s, got different value",
                path,
                expected,
            )


# ---------------------------------------------------------------------------
# meta2 JSON → IndexEntry deserialization
# ---------------------------------------------------------------------------


def _hashset_from_dict(d: dict[str, Any] | None) -> HashSet | None:
    if d is None:
        return None
    return HashSet(
        md5=d["md5"],
        sha256=d["sha256"],
        sha512=d.get("sha512"),
    )


def _name_from_dict(d: dict[str, Any]) -> NameObject:
    return NameObject(
        text=d["text"],
        hashes=_hashset_from_dict(d.get("hashes")),
    )


def _size_from_dict(d: dict[str, Any]) -> SizeObject:
    return SizeObject(text=d["text"], bytes=d["bytes"])


def _timestamp_pair_from_dict(d: dict[str, Any]) -> TimestampPair:
    return TimestampPair(iso=d["iso"], unix=d["unix"])


def _timestamps_from_dict(d: dict[str, Any]) -> TimestampsObject:
    return TimestampsObject(
        created=_timestamp_pair_from_dict(d["created"]),
        modified=_timestamp_pair_from_dict(d["modified"]),
        accessed=_timestamp_pair_from_dict(d["accessed"]),
    )


def _parent_from_dict(d: dict[str, Any] | None) -> ParentObject | None:
    if d is None:
        return None
    return ParentObject(
        id=d["id"],
        name=_name_from_dict(d["name"]),
    )


def _filesystem_from_dict(d: dict[str, Any]) -> FileSystemObject:
    return FileSystemObject(
        relative=d["relative"],
        parent=_parent_from_dict(d.get("parent")),
    )


def _attributes_from_dict(d: dict[str, Any]) -> AttributesObject:
    return AttributesObject(
        is_link=d["is_link"],
        storage_name=d["storage_name"],
    )


def _metadata_attrs_from_dict(d: dict[str, Any]) -> MetadataAttributes:
    return MetadataAttributes(
        type=d["type"],
        format=d["format"],
        transforms=d.get("transforms", []),
        source_media_type=d.get("source_media_type"),
    )


def _metadata_entry_from_dict(d: dict[str, Any]) -> MetadataEntry:
    fs = None
    if d.get("file_system") is not None:
        fs = _filesystem_from_dict(d["file_system"])
    size = None
    if d.get("size") is not None:
        size = _size_from_dict(d["size"])
    ts = None
    if d.get("timestamps") is not None:
        ts = _timestamps_from_dict(d["timestamps"])
    return MetadataEntry(
        id=d["id"],
        origin=d["origin"],
        name=_name_from_dict(d["name"]),
        hashes=_hashset_from_dict(d["hashes"]) or HashSet(md5="", sha256=""),
        attributes=_metadata_attrs_from_dict(d["attributes"]),
        data=d.get("data"),
        file_system=fs,
        size=size,
        timestamps=ts,
    )


def _entry_from_dict(d: dict[str, Any]) -> IndexEntry:
    """Reconstruct an :class:`IndexEntry` from a JSON-parsed dict."""
    items = None
    if d.get("items") is not None:
        items = [_entry_from_dict(item) for item in d["items"]]

    metadata = None
    if d.get("metadata") is not None:
        metadata = [_metadata_entry_from_dict(m) for m in d["metadata"]]

    duplicates = None
    if d.get("duplicates") is not None:
        duplicates = [_entry_from_dict(dup) for dup in d["duplicates"]]

    indexed_at = None
    if d.get("indexed_at") is not None:
        indexed_at = _timestamp_pair_from_dict(d["indexed_at"])

    return IndexEntry(
        schema_version=d["schema_version"],
        id=d["id"],
        id_algorithm=d["id_algorithm"],
        type=d["type"],
        name=_name_from_dict(d["name"]),
        extension=d.get("extension"),
        size=_size_from_dict(d["size"]),
        hashes=_hashset_from_dict(d.get("hashes")),
        file_system=_filesystem_from_dict(d["file_system"]),
        timestamps=_timestamps_from_dict(d["timestamps"]),
        attributes=_attributes_from_dict(d["attributes"]),
        items=items,
        metadata=metadata,
        duplicates=duplicates,
        mime_type=d.get("mime_type"),
        session_id=d.get("session_id"),
        indexed_at=indexed_at,
    )


# ---------------------------------------------------------------------------
# Meta2 loader & discovery
# ---------------------------------------------------------------------------


def discover_meta2_files(
    directory: Path,
    *,
    recursive: bool = False,
) -> list[Path]:
    """Find all ``*_meta2.json`` files in a directory.

    Args:
        directory: The directory to search.
        recursive: When ``True``, search subdirectories as well.
            When ``False`` (default), search only the immediate directory.

    Returns:
        Sorted list of discovered meta2 file paths.
    """
    if recursive:
        return sorted(directory.rglob("*_meta2.json"))
    return sorted(directory.glob("*_meta2.json"))


def _flatten_tree(entry: IndexEntry, out: list[IndexEntry]) -> None:
    """Recursively extract all ``type == "file"`` entries from a tree."""
    if entry.type == "file":
        out.append(entry)
    if entry.items:
        for child in entry.items:
            _flatten_tree(child, out)


def _extract_duplicates(entries: list[IndexEntry]) -> list[IndexEntry]:
    """Extract duplicates from each canonical entry and annotate them."""
    result: list[IndexEntry] = []
    for entry in entries:
        result.append(entry)
        if entry.duplicates:
            for dup in entry.duplicates:
                _mark_duplicate(dup, entry.attributes.storage_name)
                result.append(dup)
    return result


def load_meta2(
    path: Path,
    *,
    recursive: bool = False,
) -> list[IndexEntry]:
    """Load and parse a ``_meta2.json`` file into a flat list of IndexEntry objects.

    Handles three input shapes:

    1. **Per-file sidecar:** single IndexEntry object → returns ``[entry]``.
    2. **Aggregate output** (directory entry with ``items[]``): walks the tree,
       returns all ``type == "file"`` entries flattened.
    3. **Directory path:** discovers all ``*_meta2.json`` files (recursively if
       *recursive* is ``True``), loads each, returns combined flat list.

    Duplicate entries from the ``duplicates`` array of each canonical entry
    are extracted and included in the returned list with a transient
    annotation distinguishing them from canonical entries.

    Args:
        path: Path to a ``_meta2.json`` file, aggregate output file, or
            directory containing ``_meta2.json`` sidecars.
        recursive: When ``True`` and *path* is a directory, search
            subdirectories for sidecars.

    Returns:
        Flat list of :class:`IndexEntry` objects (files only).

    Raises:
        IndexerConfigError: If the file is not valid JSON.
        IndexerConfigError: If ``schema_version`` is not 2.
        IndexerTargetError: If *path* does not exist.
    """
    if not path.exists():
        msg = f"Path does not exist: {path}"
        raise IndexerTargetError(msg)

    # Shape 3: directory → discover and combine
    if path.is_dir():
        files = discover_meta2_files(path, recursive=recursive)
        combined: list[IndexEntry] = []
        for f in files:
            combined.extend(load_meta2(f, recursive=False))
        return combined

    # Shapes 1 & 2: single JSON file
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"Invalid JSON in {path}: {exc}"
        raise IndexerConfigError(msg) from exc

    # Schema version gate
    version = data.get("schema_version")
    if version != 2:
        msg = (
            f"Unsupported schema version in {path}: expected 2, got {version}. "
            "v1 sidecar files must be migrated to v2 format before rollback."
        )
        raise IndexerConfigError(msg)

    entry = _entry_from_dict(data)

    # Shape 2: aggregate directory entry with items[]
    if entry.type == "directory" and entry.items:
        flat: list[IndexEntry] = []
        _flatten_tree(entry, flat)
        return _extract_duplicates(flat)

    # Shape 1: single file entry
    if entry.type == "file":
        return _extract_duplicates([entry])

    # Unexpected type — return empty
    return []


# ---------------------------------------------------------------------------
# Hash verification
# ---------------------------------------------------------------------------


def verify_file_hash(
    path: Path,
    expected: HashSet,
    algorithm: str = "md5",
) -> bool:
    """Verify a file's content hash against expected values.

    Computes the hash of the file at *path* and compares against the
    expected :class:`HashSet`.  Uses only the specified *algorithm* for
    efficiency (avoids computing all hashes).

    Args:
        path: File to hash.
        expected: Expected hash values.
        algorithm: Hash algorithm to use (default ``"md5"``).

    Returns:
        ``True`` if the hash matches, ``False`` otherwise.
    """
    from shruggie_indexer.core.hashing import hash_file

    expected_value = getattr(expected, algorithm, None)
    if expected_value is None:
        return False

    # hash_file requires at minimum md5+sha256 (see _make_hashset).
    # Always use the default algorithms to avoid KeyError.
    computed = hash_file(path)
    actual_value = getattr(computed, algorithm, None)

    return actual_value is not None and actual_value.upper() == expected_value.upper()


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


def _is_path_safe(target_dir: Path, resolved: Path) -> bool:
    """Return ``True`` if *resolved* stays within *target_dir*."""
    try:
        resolved.resolve().relative_to(target_dir.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Rollback planner
# ---------------------------------------------------------------------------


def plan_rollback(
    entries: list[IndexEntry],
    target_dir: Path,
    *,
    source_dir: Path | None = None,
    resolver: SourceResolver | None = None,
    verify: bool = True,
    force: bool = False,
    flat: bool = False,
    skip_duplicates: bool = False,
    restore_sidecars: bool = True,
) -> RollbackPlan:
    """Compute the full rollback plan without executing it.

    This is the primary API entry point for rollback operations.

    Args:
        entries: Flat list of :class:`IndexEntry` objects from
            :func:`load_meta2`.
        target_dir: Root directory for restored files.  Created if absent.
        source_dir: Directory to search for content files.  When ``None``,
            the resolver's default search behaviour applies.
        resolver: Source file locator.  Defaults to
            :class:`LocalSourceResolver`.
        verify: Compute and verify content hashes.  Default ``True``.
        force: Overwrite existing files in target directory.  Default ``False``.
        flat: When ``True``, restore all files directly into *target_dir*
            using only ``name.text`` (no directory structure).
            Default ``False``.
        skip_duplicates: Do not restore files from ``duplicates[]`` arrays.
        restore_sidecars: Restore absorbed sidecar metadata files from
            :class:`MetadataEntry` records.  Default ``True``.

    Returns:
        A :class:`RollbackPlan` describing all actions to be taken.
    """
    # Purge stale annotations from prior load_meta2 calls.  id() values
    # can be reused after objects are garbage-collected, so we remove
    # annotations whose keys don't belong to the current *entries* batch
    # to avoid false-positive duplicate detection.
    live_ids = {id(e) for e in entries}
    _stale = [k for k in _annotations if k not in live_ids]
    for k in _stale:
        del _annotations[k]

    if resolver is None:
        resolver = LocalSourceResolver(verify_hash=verify)

    actions: list[RollbackAction] = []
    stats = RollbackStats(total_entries=len(entries))
    warnings: list[str] = []
    dirs_needed: set[Path] = set()
    flat_targets_seen: set[str] = set()

    for entry in entries:
        is_dup = _is_duplicate(entry)

        # Skip duplicates if requested
        if is_dup and skip_duplicates:
            continue

        # Locate source
        source_path = resolver.resolve(entry, source_dir)
        if source_path is None and is_dup:
            # For duplicates, try resolving via canonical storage_name
            canonical_sn = _canonical_storage_name(entry)
            if source_dir is not None:
                canonical_path = source_dir / canonical_sn
                if canonical_path.is_file():
                    source_path = canonical_path

        action_type = "duplicate_restore" if is_dup else "restore"

        if source_path is None:
            sn = entry.attributes.storage_name
            name_text = entry.name.text or "<unnamed>"
            logger.warning(
                "Source not found for entry: %s / %s in %s",
                sn,
                name_text,
                source_dir,
            )
            actions.append(
                RollbackAction(
                    source_path=None,
                    target_path=_compute_target_path(entry, target_dir, flat),
                    entry=entry,
                    action_type=action_type,
                    skip_reason="Source file not found",
                ),
            )
            stats.skipped_unresolvable += 1
            continue

        # Compute target path
        target_path = _compute_target_path(entry, target_dir, flat)

        # Path safety check
        if not _is_path_safe(target_dir, target_path):
            rel = entry.file_system.relative if not flat else (entry.name.text or "")
            logger.warning("Path traversal rejected: %s", rel)
            actions.append(
                RollbackAction(
                    source_path=source_path,
                    target_path=target_path,
                    entry=entry,
                    action_type=action_type,
                    skip_reason="Path traversal rejected",
                ),
            )
            stats.skipped_conflict += 1
            continue

        # Flat mode collision check
        if flat:
            flat_key = (entry.name.text or "").lower()
            if flat_key in flat_targets_seen:
                name_text = entry.name.text or "<unnamed>"
                logger.warning(
                    "Flat restore collision: %s already exists in target "
                    "(from a different entry). Skipped.",
                    name_text,
                )
                actions.append(
                    RollbackAction(
                        source_path=source_path,
                        target_path=target_path,
                        entry=entry,
                        action_type=action_type,
                        skip_reason="Flat restore collision",
                    ),
                )
                stats.skipped_conflict += 1
                continue
            flat_targets_seen.add(flat_key)

        # Conflict check — target already exists on disk
        skip = _check_conflict(
            target_path, entry, verify, force, stats,
        )
        if skip is not None:
            actions.append(
                RollbackAction(
                    source_path=source_path,
                    target_path=target_path,
                    entry=entry,
                    action_type=action_type,
                    skip_reason=skip,
                ),
            )
            continue

        # Good to restore
        if is_dup:
            stats.duplicates_to_restore += 1
        else:
            stats.files_to_restore += 1

        actions.append(
            RollbackAction(
                source_path=source_path,
                target_path=target_path,
                entry=entry,
                action_type=action_type,
                verified=verify,
            ),
        )

        # Track directories needed (structured mode)
        if not flat:
            parent = target_path.parent
            if parent != target_dir:
                dirs_needed.add(parent)

        # Sidecar restoration
        if restore_sidecars and entry.metadata:
            for meta in entry.metadata:
                if meta.origin != "sidecar":
                    continue
                _plan_sidecar_restore(
                    meta, entry, target_dir, flat, actions, stats,
                    dirs_needed, flat_targets_seen, force, verify,
                )

    # Directory actions (structured mode only)
    if not flat:
        for d in sorted(dirs_needed):
            actions.append(
                RollbackAction(
                    source_path=None,
                    target_path=d,
                    entry=entries[0] if entries else IndexEntry(
                        schema_version=2, id="", id_algorithm="md5",
                        type="directory",
                        name=NameObject(text=None, hashes=None),
                        extension=None,
                        size=SizeObject(text="0 B", bytes=0),
                        hashes=None,
                        file_system=FileSystemObject(relative="", parent=None),
                        timestamps=TimestampsObject(
                            created=TimestampPair(iso="", unix=0),
                            modified=TimestampPair(iso="", unix=0),
                            accessed=TimestampPair(iso="", unix=0),
                        ),
                        attributes=AttributesObject(is_link=False, storage_name=""),
                    ),
                    action_type="mkdir",
                ),
            )
            stats.directories_to_create += 1

    # Mixed-session warning (structured mode only)
    if not flat:
        session_ids = {
            e.session_id for e in entries
            if e.session_id is not None
        }
        if len(session_ids) > 1:
            n = len(entries)
            m = len(session_ids)
            msg = (
                f"{n} entries span {m} distinct indexing sessions. "
                "Relative paths may not share a common root. "
                "Consider using --flat or specifying --target explicitly."
            )
            warnings.append(msg)
            logger.warning("%s", msg)

    return RollbackPlan(actions=actions, stats=stats, warnings=warnings)


def _compute_target_path(entry: IndexEntry, target_dir: Path, flat: bool) -> Path:
    """Compute the restore target path for an entry."""
    if flat:
        return target_dir / (entry.name.text or entry.attributes.storage_name)
    # Structured: use file_system.relative, converting forward slashes
    rel = entry.file_system.relative.replace("/", os.sep)
    return target_dir / rel


def _check_conflict(
    target_path: Path,
    entry: IndexEntry,
    verify: bool,
    force: bool,
    stats: RollbackStats,
) -> str | None:
    """Check if the target already exists.  Returns skip_reason or None."""
    if not target_path.exists():
        return None

    if verify and entry.hashes is not None:
        if verify_file_hash(target_path, entry.hashes, entry.id_algorithm):
            logger.debug("Skipped (already exists, same hash): %s", target_path)
            stats.skipped_already_exists += 1
            return "Already exists (same content)"

    if force:
        return None

    logger.warning("Skipped (exists, different content): %s", target_path)
    stats.skipped_conflict += 1
    return "Already exists (different content)"


def _plan_sidecar_restore(
    meta: MetadataEntry,
    parent_entry: IndexEntry,
    target_dir: Path,
    flat: bool,
    actions: list[RollbackAction],
    stats: RollbackStats,
    dirs_needed: set[Path],
    flat_targets_seen: set[str],
    force: bool,
    verify: bool,
) -> None:
    """Add a sidecar restoration action to the plan."""
    # Compute target path
    if flat:
        target_path = target_dir / (meta.name.text or "unknown_sidecar")
    else:
        if meta.file_system is not None:
            rel = meta.file_system.relative.replace("/", os.sep)
            target_path = target_dir / rel
        elif meta.name.text is not None:
            # Fallback: place alongside the parent entry
            parent_rel = parent_entry.file_system.relative.replace("/", os.sep)
            parent_target = target_dir / parent_rel
            target_path = parent_target.parent / meta.name.text
        else:
            return  # Cannot determine target

    # Path safety
    if not _is_path_safe(target_dir, target_path):
        return

    # Flat collision check
    if flat:
        flat_key = (meta.name.text or "").lower()
        if flat_key in flat_targets_seen:
            return
        flat_targets_seen.add(flat_key)

    # Conflict check
    if target_path.exists() and not force:
        stats.skipped_conflict += 1
        return

    # Decode sidecar data
    sidecar_data, sidecar_binary = _decode_sidecar_data(meta)

    stats.sidecars_to_restore += 1
    actions.append(
        RollbackAction(
            source_path=None,
            target_path=target_path,
            entry=parent_entry,
            action_type="sidecar_restore",
            sidecar_data=sidecar_data,
            sidecar_binary=sidecar_binary,
            metadata_entry=meta,
        ),
    )

    if not flat:
        parent = target_path.parent
        if parent != target_dir:
            dirs_needed.add(parent)


def _decode_sidecar_data(meta: MetadataEntry) -> tuple[bytes | str, bool]:
    """Decode sidecar data based on format.  Returns (data, is_binary)."""
    fmt = meta.attributes.format
    data = meta.data

    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False), False
    if fmt == "text":
        return str(data), False
    if fmt == "base64":
        return base64.b64decode(data), True
    if fmt == "lines":
        if isinstance(data, list):
            return "\n".join(str(line) for line in data), False
        return str(data), False

    # Unknown format — treat as text
    return str(data), False


# ---------------------------------------------------------------------------
# Rollback executor
# ---------------------------------------------------------------------------


def execute_rollback(
    plan: RollbackPlan,
    *,
    dry_run: bool = False,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> RollbackResult:
    """Execute a previously computed rollback plan.

    Processes actions in order: ``mkdir`` → ``restore`` → ``duplicate_restore``
    → ``sidecar_restore``.

    In dry-run mode, logs all actions at ``INFO`` level without performing them.

    Args:
        plan: The plan from :func:`plan_rollback`.
        dry_run: Log actions without executing them.
        progress_callback: Optional callback for progress reporting (GUI).
        cancel_event: Optional :class:`threading.Event` for cancellation (GUI).

    Returns:
        A :class:`RollbackResult` summarizing the outcome.
    """
    result = RollbackResult()

    # Sort actions by execution phase
    mkdir_actions = [a for a in plan.actions if a.action_type == "mkdir" and not a.skip_reason]
    restore_actions = [a for a in plan.actions if a.action_type == "restore" and not a.skip_reason]
    dup_actions = [a for a in plan.actions if a.action_type == "duplicate_restore" and not a.skip_reason]
    sidecar_actions = [a for a in plan.actions if a.action_type == "sidecar_restore" and not a.skip_reason]
    skipped_actions = [a for a in plan.actions if a.skip_reason]

    result.skipped = len(skipped_actions)

    total_actionable = len(mkdir_actions) + len(restore_actions) + len(dup_actions) + len(sidecar_actions)
    completed = 0

    # Phase 1: create directories (deepest-first → sort by depth descending,
    # but we actually need shallowest-first for creation)
    mkdir_actions.sort(key=lambda a: len(a.target_path.parts))
    for action in mkdir_actions:
        if _check_cancelled(cancel_event, result):
            return result
        completed += 1
        _report_progress(progress_callback, "rollback", total_actionable, completed, action.target_path)

        if dry_run:
            logger.info("Dry run — would create directory: %s", action.target_path)
            result.directories_created += 1
            continue
        try:
            action.target_path.mkdir(parents=True, exist_ok=True)
            logger.info("Directory created: %s", action.target_path)
            result.directories_created += 1
        except OSError as exc:
            logger.error("Failed to create directory %s: %s", action.target_path, exc)
            result.failed += 1
            result.errors.append(f"mkdir {action.target_path}: {exc}")

    # Phase 2: restore canonical files
    for action in restore_actions:
        if _check_cancelled(cancel_event, result):
            return result
        completed += 1
        _report_progress(progress_callback, "rollback", total_actionable, completed, action.target_path)
        _execute_file_copy(action, result, dry_run=dry_run)

    # Phase 3: restore duplicates
    for action in dup_actions:
        if _check_cancelled(cancel_event, result):
            return result
        completed += 1
        _report_progress(progress_callback, "rollback", total_actionable, completed, action.target_path)
        _execute_file_copy(action, result, dry_run=dry_run, is_duplicate=True)

    # Phase 4: restore sidecars
    for action in sidecar_actions:
        if _check_cancelled(cancel_event, result):
            return result
        completed += 1
        _report_progress(progress_callback, "rollback", total_actionable, completed, action.target_path)
        _execute_sidecar_write(action, result, dry_run=dry_run)

    # Summary log
    logger.info(
        "Rollback complete: %d restored, %d duplicates, %d sidecars, %d skipped, %d failed",
        result.restored,
        result.duplicates_restored,
        result.sidecars_restored,
        result.skipped,
        result.failed,
    )

    return result


def _check_cancelled(
    cancel_event: threading.Event | None,
    result: RollbackResult,
) -> bool:
    """Return ``True`` and log if cancellation was requested."""
    if cancel_event is not None and cancel_event.is_set():
        logger.info("Rollback cancelled by user")
        return True
    return False


def _report_progress(
    callback: Callable[[ProgressEvent], None] | None,
    phase: str,
    total: int,
    completed: int,
    current_path: Path | None,
) -> None:
    """Fire progress callback if provided."""
    if callback is None:
        return
    from shruggie_indexer.core.progress import ProgressEvent

    callback(
        ProgressEvent(
            phase=phase,
            items_total=total,
            items_completed=completed,
            current_path=current_path,
            message=None,
            level="info",
        ),
    )


def _execute_file_copy(
    action: RollbackAction,
    result: RollbackResult,
    *,
    dry_run: bool = False,
    is_duplicate: bool = False,
) -> None:
    """Copy a source file to the target path and restore timestamps."""
    name_text = action.entry.name.text or action.entry.attributes.storage_name

    if dry_run:
        if is_duplicate:
            logger.info(
                "Dry run — would restore duplicate: %s → %s",
                name_text,
                action.target_path,
            )
        else:
            logger.info(
                "Dry run — would restore: %s → %s",
                name_text,
                action.target_path,
            )
        if is_duplicate:
            result.duplicates_restored += 1
        else:
            result.restored += 1
        return

    try:
        # Ensure parent exists
        action.target_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(str(action.source_path), str(action.target_path))

        # Restore timestamps
        _restore_timestamps(action.target_path, action.entry.timestamps)

        if is_duplicate:
            canonical_name = _canonical_storage_name(action.entry)
            logger.info(
                "Duplicate restored: %s → %s (copy of %s)",
                name_text,
                action.target_path,
                canonical_name,
            )
            result.duplicates_restored += 1
        else:
            logger.info("Restored: %s → %s", name_text, action.target_path)
            result.restored += 1
    except OSError as exc:
        logger.error(
            "Failed to restore %s → %s: %s",
            name_text,
            action.target_path,
            exc,
        )
        result.failed += 1
        result.errors.append(f"restore {name_text} → {action.target_path}: {exc}")


def _execute_sidecar_write(
    action: RollbackAction,
    result: RollbackResult,
    *,
    dry_run: bool = False,
) -> None:
    """Write decoded sidecar data to the target path."""
    sidecar_name = (
        action.metadata_entry.name.text
        if action.metadata_entry and action.metadata_entry.name.text
        else str(action.target_path.name)
    )

    if dry_run:
        logger.info(
            "Dry run — would restore sidecar: %s → %s",
            sidecar_name,
            action.target_path,
        )
        result.sidecars_restored += 1
        return

    try:
        action.target_path.parent.mkdir(parents=True, exist_ok=True)

        if action.sidecar_binary:
            action.target_path.write_bytes(action.sidecar_data)  # type: ignore[arg-type]
        else:
            action.target_path.write_text(
                str(action.sidecar_data),
                encoding="utf-8",
            )

        # Restore timestamps if the metadata entry has them
        if action.metadata_entry and action.metadata_entry.timestamps:
            _restore_timestamps(action.target_path, action.metadata_entry.timestamps)

        logger.info("Sidecar restored: %s → %s", sidecar_name, action.target_path)
        result.sidecars_restored += 1
    except OSError as exc:
        logger.error(
            "Failed to restore sidecar %s → %s: %s",
            sidecar_name,
            action.target_path,
            exc,
        )
        result.failed += 1
        result.errors.append(f"sidecar {sidecar_name} → {action.target_path}: {exc}")


def _restore_timestamps(path: Path, timestamps: TimestampsObject) -> None:
    """Set atime/mtime from sidecar timestamps.  Attempt ctime on Windows."""
    try:
        # Sidecar timestamps are millisecond Unix timestamps; os.utime
        # expects seconds.
        atime = timestamps.accessed.unix / 1000
        mtime = timestamps.modified.unix / 1000
        os.utime(path, (atime, mtime))
    except OSError as exc:
        logger.error("Failed to set timestamps on %s: %s", path, exc)
        return

    # Attempt ctime on Windows via pywin32 (SHOULD, not MUST)
    try:
        import pywintypes
        import win32file

        ctime = timestamps.created.unix / 1000

        handle = win32file.CreateFile(
            str(path),
            win32file.GENERIC_WRITE,
            0,
            None,
            win32file.OPEN_EXISTING,
            0,
            None,
        )
        try:
            creation_time = pywintypes.Time(ctime)
            win32file.SetFileTime(handle, creation_time, None, None)
        finally:
            handle.Close()
    except ImportError:
        logger.debug(
            "pywin32 not available — skipping ctime restoration for %s",
            path,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to set ctime on %s: %s", path, exc)

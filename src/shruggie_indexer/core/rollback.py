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
import ctypes
import json
import logging
import os
import shutil
import sys
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

# Module-level dict mapping id(entry) → Path of the directory containing
# the meta2 file that produced this entry.  Used by LocalSourceResolver
# to locate content files in subdirectories during recursive rollback.
_origin_dirs: dict[int, Path] = {}


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


def _get_origin_dir(entry: IndexEntry) -> Path | None:
    """Return the meta2 origin directory for *entry*, or ``None``."""
    ann = _origin_dirs.get(id(entry))
    return ann


class LocalSourceResolver:
    """Locate content files on the local filesystem.

    Search strategy (tried in order):

    1. Look for ``storage_name`` in *search_dir* — handles renamed files.
    2. Look for ``name.text`` in *search_dir*, verify hash if found — handles
       non-renamed files.
    3. If the entry has a meta2 origin directory that differs from
       *search_dir*, repeat strategies 1 & 2 in the origin directory —
       handles recursive rollback where content files live alongside their
       meta2 sidecars in subdirectories.

    Returns ``None`` if neither match succeeds.
    """

    def __init__(self, *, verify_hash: bool = True) -> None:
        self._verify_hash = verify_hash

    def _try_dir(self, entry: IndexEntry, directory: Path) -> Path | None:
        """Attempt to find the source file for *entry* in *directory*."""
        # Strategy A: storage_name match (renamed file)
        storage_path = directory / entry.attributes.storage_name
        if storage_path.is_file():
            if self._verify_hash and entry.hashes is not None:
                self._check_hash(storage_path, entry)
            return storage_path

        # Strategy B: original name match (non-renamed file)
        if entry.name.text is not None:
            original_path = directory / entry.name.text
            if original_path.is_file():
                if self._verify_hash and entry.hashes is not None:
                    self._check_hash(original_path, entry)
                return original_path

        return None

    def resolve(self, entry: IndexEntry, search_dir: Path | None) -> Path | None:
        if search_dir is None:
            return None

        # Strategies 1 & 2: search in the caller-provided search_dir
        result = self._try_dir(entry, search_dir)
        if result is not None:
            return result

        # Strategy 3: origin directory fallback (recursive rollback)
        origin = _get_origin_dir(entry)
        if origin is not None and origin.resolve() != search_dir.resolve():
            result = self._try_dir(entry, origin)
            if result is not None:
                return result

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
            sub_entries = load_meta2(f, recursive=False)
            # Annotate each entry with the directory its meta2 came from
            # so LocalSourceResolver can find content files alongside the
            # sidecar during recursive rollback.
            for e in sub_entries:
                _origin_dirs[id(e)] = f.parent
            combined.extend(sub_entries)
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
        entries = _extract_duplicates(flat)
        # Annotate all entries with the meta2 file's parent directory
        for e in entries:
            _origin_dirs[id(e)] = path.parent
        return entries

    # Shape 1: single file entry
    if entry.type == "file":
        entries = _extract_duplicates([entry])
        for e in entries:
            _origin_dirs[id(e)] = path.parent
        return entries

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
# Pre-planning entry sanitization
# ---------------------------------------------------------------------------


def _deduplicate_by_content_hash(
    entries: list[IndexEntry],
) -> list[IndexEntry]:
    """Remove entries with duplicate content hashes but conflicting relative paths.

    When multiple entries share the same content hash (``hashes.sha256`` or
    ``hashes.md5``) but differ in ``file_system.relative``, this indicates
    stale metadata from prior indexing sessions.  Tiebreaking rules:

    1. If entries have ``session_id`` values, prefer the one matching the
       majority session (the ``session_id`` that appears most frequently
       across *all* loaded entries).
    2. If only one entry has a ``session_id``, prefer it over entries
       without one.
    3. Otherwise, keep the first encountered.

    Returns a new list with conflicting duplicates removed.
    """
    if not entries:
        return entries

    # Determine majority session across all entries
    session_counts: dict[str, int] = {}
    for entry in entries:
        if entry.session_id is not None:
            session_counts[entry.session_id] = (
                session_counts.get(entry.session_id, 0) + 1
            )

    majority_session: str | None = None
    if session_counts:
        majority_session = max(session_counts, key=lambda k: session_counts[k])

    # Group entries by composite content hash (md5 + sha256).  Two entries
    # represent the same file only when both hashes agree; using a single
    # hash as the key would cause false collisions when test helpers or
    # partial metadata produce entries with a shared default hash value.
    #
    # Entries annotated as duplicates (from the ``duplicates[]`` array of a
    # canonical entry) are excluded from collision detection.  They are
    # *expected* to share the canonical's content hash at a different
    # relative path — that is the normal dedup-restore workflow, not a
    # stale-metadata collision.
    hash_groups: dict[tuple[str, str], list[IndexEntry]] = {}
    for entry in entries:
        if entry.hashes is None:
            continue
        if _is_duplicate(entry):
            continue  # Dedup entries share hash intentionally
        md5 = (entry.hashes.md5 or "").upper()
        sha256 = (entry.hashes.sha256 or "").upper()
        if md5 or sha256:
            hash_groups.setdefault((md5, sha256), []).append(entry)

    discarded_ids: set[int] = set()

    for content_key, group in hash_groups.items():
        if len(group) < 2:
            continue

        # Check for actual relative path conflicts
        relatives = {e.file_system.relative for e in group}
        if len(relatives) < 2:
            continue  # Same hash, same relative — no conflict

        # Collision detected — pick winner
        content_hash = "/".join(k for k in content_key if k)
        winner = _resolve_hash_collision(group, majority_session)
        for entry in group:
            if entry is not winner:
                discarded_ids.add(id(entry))
                logger.warning(
                    "Duplicate content hash %s found in multiple sessions.\n"
                    "  Keeping: %s (session %s)\n"
                    "  Discarding: %s (session %s)",
                    content_hash,
                    winner.file_system.relative,
                    winner.session_id or "<none>",
                    entry.file_system.relative,
                    entry.session_id or "<none>",
                )

    if not discarded_ids:
        return entries

    return [e for e in entries if id(e) not in discarded_ids]


def _resolve_hash_collision(
    group: list[IndexEntry],
    majority_session: str | None,
) -> IndexEntry:
    """Pick the winning entry from a content-hash collision group.

    Rules (applied in order):

    1. If entries have ``session_id`` values, prefer the one matching
       *majority_session*.
    2. If only one entry (or subset) has a ``session_id``, prefer any
       entry with a ``session_id`` over entries without one.
    3. Otherwise, keep the first encountered.
    """
    with_session = [e for e in group if e.session_id is not None]

    # Rule 1: entries with session_ids — prefer majority
    if with_session and majority_session is not None:
        majority_entries = [
            e for e in with_session if e.session_id == majority_session
        ]
        if majority_entries:
            return majority_entries[0]

    # Rule 2: any entry with session_id over entries without
    if with_session:
        return with_session[0]

    # Rule 3: no session_ids — first encountered
    return group[0]


def _strip_legacy_prefix(
    entries: list[IndexEntry],
    source_dir: Path | None = None,
) -> None:
    """Detect and strip legacy ``file_system.relative`` prefix in place.

    Pre-fix indexer versions computed ``file_system.relative`` from the
    *parent* of the target directory, prepending the target's own name
    (e.g., ``"data/images/photo.jpg"`` instead of ``"images/photo.jpg"``).

    Detection heuristic: if every entry's relative path has at least two
    components and all entries share the same first component, that
    component is the legacy prefix.  The candidate prefix is confirmed by
    comparing against *source_dir*'s name — the legacy prefix equals the
    indexed directory name, which is typically the source directory.  When
    *source_dir* is ``None``, the prefix is accepted without confirmation
    (callers that cannot provide a source directory accept the small risk
    of a false positive).

    Upon detection, the prefix is stripped from all entries and an ``INFO``
    message is logged.
    """
    if not entries:
        return

    # If any entry already uses "." as relative, it's the current format
    if any(e.file_system.relative == "." for e in entries):
        return

    first_components: set[str] = set()
    for entry in entries:
        rel = entry.file_system.relative.replace("\\", "/")
        parts = rel.split("/")
        if len(parts) < 2:
            return  # At least one entry is a bare filename — not legacy
        first_components.add(parts[0])

    if len(first_components) != 1:
        return  # No single common prefix

    prefix = next(iter(first_components))
    if not prefix or prefix == ".":
        return

    # Verify that the candidate prefix matches the source directory name.
    # The legacy bug prepended the *indexed directory's own name*; the
    # source directory is typically that same directory.
    if source_dir is not None and prefix != source_dir.name:
        return  # Common prefix is a legitimate subdirectory, not legacy

    logger.info(
        "Detected legacy relative path prefix '%s'. "
        "Stripping prefix for rollback.",
        prefix,
    )

    for entry in entries:
        rel = entry.file_system.relative.replace("\\", "/")
        if rel == prefix:
            entry.file_system = FileSystemObject(
                relative=".", parent=entry.file_system.parent,
            )
        elif rel.startswith(prefix + "/"):
            entry.file_system = FileSystemObject(
                relative=rel[len(prefix) + 1 :],
                parent=entry.file_system.parent,
            )


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
    # Log resolved parameters for diagnostics
    logger.info(
        "Rollback plan: entries=%d, target_dir=%s, source_dir=%s, "
        "verify=%s, force=%s, flat=%s, skip_duplicates=%s, "
        "restore_sidecars=%s",
        len(entries),
        target_dir,
        source_dir,
        verify,
        force,
        flat,
        skip_duplicates,
        restore_sidecars,
    )

    # Purge stale annotations from prior load_meta2 calls.  id() values
    # can be reused after objects are garbage-collected, so we remove
    # annotations whose keys don't belong to the current *entries* batch
    # to avoid false-positive duplicate detection.
    live_ids = {id(e) for e in entries}
    _stale = [k for k in _annotations if k not in live_ids]
    for k in _stale:
        del _annotations[k]
    _stale_origins = [k for k in _origin_dirs if k not in live_ids]
    for k in _stale_origins:
        del _origin_dirs[k]

    # Pre-planning sanitization: legacy prefix stripping, then collision
    # detection.  Order matters — prefix stripping normalises relative
    # paths before collision grouping compares them.
    _strip_legacy_prefix(entries, source_dir=source_dir)
    entries = _deduplicate_by_content_hash(entries)

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


def _set_windows_creation_time(path: Path, ctime_seconds: float) -> bool:
    """Set file creation time on Windows using ctypes/kernel32.

    Uses the Windows API directly via ``ctypes.windll.kernel32`` — no
    external packages required.  Returns ``True`` on success, ``False``
    on failure (logged at DEBUG).

    No-op returning ``False`` on non-Windows platforms.
    """
    if sys.platform != "win32":
        return False

    GENERIC_WRITE = 0x40000000  # noqa: N806
    FILE_WRITE_ATTRIBUTES = 0x100  # noqa: N806
    OPEN_EXISTING = 3  # noqa: N806
    FILE_SHARE_READ = 1  # noqa: N806
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value  # noqa: N806

    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        handle = kernel32.CreateFileW(
            str(path),
            GENERIC_WRITE | FILE_WRITE_ATTRIBUTES,
            FILE_SHARE_READ,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            logger.debug(
                "CreateFileW failed for %s (error %d)",
                path,
                kernel32.GetLastError(),
            )
            return False

        try:
            # Convert Unix seconds → Windows FILETIME (100-ns intervals
            # since 1601-01-01 00:00:00 UTC).
            ft = int((ctime_seconds + 11644473600) * 10_000_000)
            filetime = ctypes.c_ulonglong(ft)
            # SetFileTime(handle, lpCreationTime, lpLastAccessTime,
            #             lpLastWriteTime) — only set creation time.
            ok = kernel32.SetFileTime(
                handle,
                ctypes.byref(filetime),
                None,
                None,
            )
            if not ok:
                logger.debug(
                    "SetFileTime failed for %s (error %d)",
                    path,
                    kernel32.GetLastError(),
                )
                return False
            return True
        finally:
            kernel32.CloseHandle(handle)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to set ctime on %s: %s", path, exc)
        return False


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

    # Restore creation time on Windows via ctypes/kernel32
    ctime = timestamps.created.unix / 1000
    _set_windows_creation_time(path, ctime)

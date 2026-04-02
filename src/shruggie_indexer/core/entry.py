"""Index entry construction for shruggie-indexer.

Hub module that orchestrates the assembly of ``IndexEntry`` objects from
filesystem paths.  This is the hub-and-spoke architecture described in
spec section 4.2 — ``entry.py`` is the sole module that calls into the
component modules (``paths``, ``hashing``, ``timestamps``, ``exif``,
``rules``) and wires their outputs together into the final schema objects.
No component module calls another component module directly; all coordination
flows through ``entry.py``.

Also contains the Stage 7 stale metadata cleanup routine
(``cleanup_stale_metadata``), which runs as the final phase of the
MetaMergeDelete pipeline.

See spec section 6.8 for full behavioral guidance.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from shruggie_indexer.core._formatting import human_readable_size
from shruggie_indexer.core.encoding import detect_file_encoding
from shruggie_indexer.core.exif import extract_exif
from shruggie_indexer.core.hashing import (
    hash_directory_id,
    hash_file,
    hash_string,
    select_id,
)
from shruggie_indexer.core.paths import (
    build_sidecar_path,
    extract_components,
    relative_forward_slash,
    resolve_path,
    validate_extension,
)
from shruggie_indexer.core.rules import classify_relationships, load_rules
from shruggie_indexer.core.timestamps import extract_timestamps
from shruggie_indexer.core.traversal import list_children
from shruggie_indexer.exceptions import (
    IndexerCancellationError,
    IndexerTargetError,
)
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
)

if TYPE_CHECKING:
    import threading
    from collections.abc import Callable
    from pathlib import Path

    from shruggie_indexer.config.types import IndexerConfig
    from shruggie_indexer.core.progress import ProgressEvent

__all__ = [
    "build_directory_entry",
    "build_file_entry",
    "cleanup_stale_metadata",
    "index_path",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_algorithms(config: IndexerConfig) -> tuple[str, ...]:
    """Return the hash algorithm tuple based on configuration."""
    if config.compute_sha512:
        return ("md5", "sha256", "sha512")
    return ("md5", "sha256")


def _build_parent(
    parent_name: str,
    parent_path: Path,
    algorithms: tuple[str, ...],
    config: IndexerConfig,
) -> ParentObject | None:
    """Construct a ``ParentObject`` for the item's parent directory.

    Returns ``None`` when the item is at a filesystem root (empty parent name).
    """
    if not parent_name:
        return None

    grandparent_name = parent_path.parent.name
    dir_hashes = hash_directory_id(parent_name, grandparent_name, algorithms)
    parent_id = select_id(dir_hashes, config.id_algorithm, "x")
    name_hashes = hash_string(parent_name, algorithms)
    name_obj = NameObject(text=parent_name, hashes=name_hashes)
    return ParentObject(id=parent_id, name=name_obj)


def _build_storage_name(entry_id: str, extension: str | None) -> str:
    """Construct the deterministic storage name from identity and extension."""
    if extension:
        return f"{entry_id}.{extension}"
    return entry_id


def _make_exif_metadata_entry(
    exif_data: dict[str, Any],
    algorithms: tuple[str, ...],
    config: IndexerConfig,
) -> MetadataEntry:
    """Wrap exiftool output in a ``MetadataEntry`` with ``origin='generated'``.

    The identity hash is derived from the deterministic JSON serialization
    of the exif data dictionary (sorted keys, ``ensure_ascii=False``).
    """
    data_json = json.dumps(exif_data, sort_keys=True, ensure_ascii=False)
    data_hashes = hash_string(data_json, algorithms)
    entry_id = select_id(data_hashes, config.id_algorithm, "z")

    return MetadataEntry(
        id=entry_id,
        origin="generated",
        name=NameObject(text=None, hashes=None),
        hashes=data_hashes,
        attributes=MetadataAttributes(
            type="exiftool.json_metadata",
            format="json",
            transforms=["key_filter"],
        ),
        data=exif_data,
    )


def _assemble_metadata(
    exif_entry: MetadataEntry | None,
    metadata_active: bool,
) -> list[MetadataEntry] | None:
    """Build the metadata array for a file entry.

    Returns ``None`` when no metadata processing was requested.
    Returns ``[]`` when processing was active but produced no results.
    """
    if not metadata_active:
        return None

    entries: list[MetadataEntry] = []
    if exif_entry is not None:
        entries.append(exif_entry)
    return entries


def _make_indexed_at() -> TimestampPair:
    """Create a ``TimestampPair`` for the current UTC time."""
    now = datetime.now(UTC)
    iso = now.strftime("%Y-%m-%dT%H:%M:%S.%f") + "+00:00"
    unix_ms = int(now.timestamp() * 1000)
    return TimestampPair(iso=iso, unix=unix_ms)


def _enumerate_siblings(path: Path) -> list[Path]:
    """List sibling files in the path's parent directory.

    Used as a fallback when ``siblings`` is not pre-supplied by the caller.
    """
    parent = path.parent
    try:
        return sorted(
            (p for p in parent.iterdir() if p.is_file()),
            key=lambda p: p.name.lower(),
        )
    except OSError:
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_file_entry(
    path: Path,
    config: IndexerConfig,
    siblings: list[Path] | None = None,
    delete_queue: list[Path] | None = None,
    sidecar_type_cache: dict[Path, str | None] | None = None,
    sidecar_entry_cache: dict[Path, MetadataEntry] | None = None,
    *,
    cancel_event: threading.Event | None = None,
    _index_root: Path | None = None,
    session_id: str | None = None,
) -> IndexEntry:
    """Build a complete ``IndexEntry`` for a single file.

    Executes the v4 construction sequence defined in spec section 6.8.

    Args:
        path: Absolute path to the file.
        config: Resolved configuration.
        siblings: Reserved for backward compatibility with legacy callers.
        delete_queue: Reserved for backward compatibility with legacy callers.
        sidecar_type_cache: Reserved for backward compatibility.
        sidecar_entry_cache: Reserved for backward compatibility.
        cancel_event: Optional ``threading.Event`` checked before expensive
            operations (hashing, EXIF extraction).  When set, raises
            ``IndexerCancellationError``.
        _index_root: Internal parameter — root directory for relative path
            computation.  Defaults to ``path.parent`` when not supplied.

    Returns:
        A fully populated ``IndexEntry`` conforming to the v4 schema.

    Raises:
        IndexerCancellationError: ``cancel_event`` was set during processing.
    """
    algorithms = _get_algorithms(config)
    index_root = _index_root if _index_root is not None else path.parent

    # Step 1 — Path components
    components = extract_components(path)
    extension = validate_extension(components.suffix, config)

    # Step 2 — Stat and symlink detection
    is_symlink = path.is_symlink()
    stat_result = path.lstat() if is_symlink else path.stat()

    # Step 3 — Hashing
    name_hashes = hash_string(components.name, algorithms)

    if is_symlink:
        content_hashes: HashSet | None = hash_string(
            components.name,
            algorithms,
        )
    else:
        try:
            content_hashes = hash_file(
                path,
                algorithms,
                cancel_event=cancel_event,
            )
        except IndexerCancellationError:
            raise
        except OSError:
            logger.warning(
                "Content hashing failed for %s — hashes set to null",
                path,
            )
            content_hashes = None

    # Step 4 — Identity selection
    identity_hashes = content_hashes if content_hashes is not None else name_hashes
    entry_id = select_id(identity_hashes, config.id_algorithm, "y")

    # Step 5 — Timestamps
    timestamps_obj = extract_timestamps(stat_result, is_symlink=is_symlink)

    # Step 6 — Size
    size_obj = SizeObject(
        text=human_readable_size(stat_result.st_size),
        bytes=stat_result.st_size,
    )

    # Step 7 — Parent identity
    parent_obj = _build_parent(
        components.parent_name,
        components.parent_path,
        algorithms,
        config,
    )

    # Step 8 — EXIF metadata
    if cancel_event is not None and cancel_event.is_set():
        raise IndexerCancellationError("Indexing cancelled")
    exif_entry: MetadataEntry | None = None
    mime_type: str | None = None
    if config.extract_exif and not is_symlink:
        logger.debug("ExifTool invoked for: %s", path)
        try:
            exif_data = extract_exif(path, config)
            if exif_data is not None:
                exif_entry = _make_exif_metadata_entry(
                    exif_data,
                    algorithms,
                    config,
                )
                mime_type = exif_data.get("File:MIMEType")
        except Exception:
            logger.warning(
                "EXIF extraction failed for %s",
                path,
                exc_info=True,
            )

    # Step 9 — Encoding detection
    encoding_obj = None
    if config.detect_encoding and not is_symlink:
        encoding_obj = detect_file_encoding(
            path,
            detect_charset_enabled=config.detect_charset,
        )

    # Step 10 — Metadata assembly (ExifTool only in v4)
    metadata_active = config.extract_exif
    metadata = _assemble_metadata(exif_entry, metadata_active)

    # Step 11 — Storage name
    storage_name = _build_storage_name(entry_id, extension)

    # Step 12 — Assembly
    return IndexEntry(
        schema_version=4,
        id=entry_id,
        id_algorithm=config.id_algorithm,
        type="file",
        name=NameObject(text=components.name, hashes=name_hashes),
        extension=extension,
        size=size_obj,
        hashes=content_hashes,
        file_system=FileSystemObject(
            relative=relative_forward_slash(path, index_root),
            parent=parent_obj,
        ),
        timestamps=timestamps_obj,
        attributes=AttributesObject(
            is_link=is_symlink,
            storage_name=storage_name,
        ),
        items=None,
        metadata=metadata,
        mime_type=mime_type,
        encoding=encoding_obj,
        session_id=session_id,
        indexed_at=_make_indexed_at(),
    )


def build_directory_entry(
    path: Path,
    config: IndexerConfig,
    recursive: bool = False,
    delete_queue: list[Path] | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: threading.Event | None = None,
    *,
    _index_root: Path | None = None,
    session_id: str | None = None,
) -> IndexEntry:
    """Build a complete ``IndexEntry`` for a directory.

    When ``recursive=True``, descends into subdirectories and populates
    the ``items`` field with a fully nested tree of child ``IndexEntry``
    objects.  When ``recursive=False``, populates ``items`` with only
    immediate children (child directories have ``items=None``).

    Args:
        path: Absolute path to the directory.
        config: Resolved configuration.
        recursive: Whether to descend into subdirectories.
        delete_queue: MetaMergeDelete accumulator.
        progress_callback: Optional callable invoked after each child
            item is processed and once after child discovery.
        cancel_event: Optional ``threading.Event`` checked before each
            child item.  When set, raises ``IndexerCancellationError``.
        _index_root: Internal parameter — root directory for relative path
            computation.  Defaults to ``path.parent`` when not supplied.

    Returns:
        A fully populated ``IndexEntry`` conforming to the v4 schema.

    Raises:
        IndexerCancellationError: ``cancel_event`` was set during the
            child-processing loop.
    """
    from shruggie_indexer.core.progress import ProgressEvent

    algorithms = _get_algorithms(config)
    index_root = _index_root if _index_root is not None else path

    components = extract_components(path)
    stat_result = path.stat()

    # Directory identity (name-based, not content-based)
    dir_identity = hash_directory_id(
        components.name,
        components.parent_name,
        algorithms,
    )
    entry_id = select_id(dir_identity, config.id_algorithm, "x")

    name_hashes = hash_string(components.name, algorithms)
    timestamps_obj = extract_timestamps(stat_result)

    parent_obj = _build_parent(
        components.parent_name,
        components.parent_path,
        algorithms,
        config,
    )

    # --- Child enumeration and construction ---
    # Check cancellation before discovery (Issue 2).
    if cancel_event is not None and cancel_event.is_set():
        raise IndexerCancellationError("Indexing cancelled")
    logger.info("Discovery phase started for: %s", path)
    _discovery_start = time.monotonic()
    files, directories = list_children(path, config)

    total_items = len(files) + len(directories)
    _discovery_elapsed = time.monotonic() - _discovery_start
    logger.info(
        "Discovery complete: %d items found in %.3fs (%d files, %d directories)",
        total_items,
        _discovery_elapsed,
        len(files),
        len(directories),
    )

    # Progress: discovery phase
    if progress_callback is not None:
        progress_callback(
            ProgressEvent(
                phase="discovery",
                items_total=total_items,
                items_completed=0,
                current_path=path,
                message=f"Discovered {total_items} items in {components.name}",
                level="info",
            )
        )

    child_entries: list[IndexEntry] = []
    items_completed = 0

    # Signal transition from discovery to processing so the GUI can
    # switch the progress bar to determinate mode immediately, before
    # the first (potentially slow) build_file_entry call.
    if progress_callback is not None and total_items > 0:
        progress_callback(
            ProgressEvent(
                phase="processing",
                items_total=total_items,
                items_completed=0,
                current_path=path,
                message=None,
                level="info",
            )
        )

    # Process file children first
    logger.info("Processing phase started: %d items", total_items)
    for child_path in files:
        if cancel_event is not None and cancel_event.is_set():
            raise IndexerCancellationError("Indexing cancelled")

        try:
            _item_start = time.monotonic()
            child_entry = build_file_entry(
                child_path,
                config,
                delete_queue=delete_queue,
                cancel_event=cancel_event,
                _index_root=index_root,
                session_id=session_id,
            )
            child_entries.append(child_entry)
            _item_elapsed = time.monotonic() - _item_start
            logger.debug(
                "Completed [%d/%d]: %s in %.3fs",
                items_completed + 1,
                total_items,
                child_path.name,
                _item_elapsed,
            )
        except IndexerCancellationError:
            raise
        except Exception:
            logger.warning(
                "Failed to build entry for %s — skipping",
                child_path,
                exc_info=True,
            )

        items_completed += 1
        if progress_callback is not None:
            progress_callback(
                ProgressEvent(
                    phase="processing",
                    items_total=total_items,
                    items_completed=items_completed,
                    current_path=child_path,
                    message=None,
                    level="info",
                )
            )

    # Process directory children
    for child_path in directories:
        if cancel_event is not None and cancel_event.is_set():
            raise IndexerCancellationError("Indexing cancelled")

        try:
            if recursive:
                child_entry = build_directory_entry(
                    child_path,
                    config,
                    recursive=True,
                    delete_queue=delete_queue,
                    progress_callback=progress_callback,
                    cancel_event=cancel_event,
                    _index_root=index_root,
                    session_id=session_id,
                )
            else:
                child_entry = _build_shallow_directory_entry(
                    child_path,
                    config,
                    index_root,
                    session_id=session_id,
                )
            child_entries.append(child_entry)
        except IndexerCancellationError:
            raise
        except Exception:
            logger.warning(
                "Failed to build entry for %s — skipping",
                child_path,
                exc_info=True,
            )

        items_completed += 1
        if progress_callback is not None:
            progress_callback(
                ProgressEvent(
                    phase="processing",
                    items_total=total_items,
                    items_completed=items_completed,
                    current_path=child_path,
                    message=None,
                    level="info",
                )
            )

    # Size aggregation: sum of all child sizes (recursive totals)
    total_bytes = sum(child.size.bytes for child in child_entries)
    size_obj = SizeObject(
        text=human_readable_size(total_bytes),
        bytes=total_bytes,
    )

    storage_name = _build_storage_name(entry_id, None)

    return IndexEntry(
        schema_version=4,
        id=entry_id,
        id_algorithm=config.id_algorithm,
        type="directory",
        name=NameObject(text=components.name, hashes=name_hashes),
        extension=None,
        size=size_obj,
        hashes=None,
        file_system=FileSystemObject(
            relative=relative_forward_slash(path, index_root),
            parent=parent_obj,
        ),
        timestamps=timestamps_obj,
        attributes=AttributesObject(
            is_link=path.is_symlink(),
            storage_name=storage_name,
        ),
        items=child_entries,
        metadata=None,
        session_id=session_id,
        indexed_at=_make_indexed_at(),
    )


def _build_shallow_directory_entry(
    path: Path,
    config: IndexerConfig,
    index_root: Path,
    *,
    session_id: str | None = None,
) -> IndexEntry:
    """Build a directory entry without enumerating children.

    Used for child directories in flat mode (``recursive=False``).
    The entry has identity, timestamps, and stat-derived size, but
    ``items`` is ``None`` (not populated).
    """
    algorithms = _get_algorithms(config)
    components = extract_components(path)

    stat_result = path.stat()

    dir_identity = hash_directory_id(
        components.name,
        components.parent_name,
        algorithms,
    )
    entry_id = select_id(dir_identity, config.id_algorithm, "x")

    name_hashes = hash_string(components.name, algorithms)
    timestamps_obj = extract_timestamps(stat_result)

    size_obj = SizeObject(
        text=human_readable_size(stat_result.st_size),
        bytes=stat_result.st_size,
    )

    parent_obj = _build_parent(
        components.parent_name,
        components.parent_path,
        algorithms,
        config,
    )

    storage_name = _build_storage_name(entry_id, None)

    return IndexEntry(
        schema_version=4,
        id=entry_id,
        id_algorithm=config.id_algorithm,
        type="directory",
        name=NameObject(text=components.name, hashes=name_hashes),
        extension=None,
        size=size_obj,
        hashes=None,
        file_system=FileSystemObject(
            relative=relative_forward_slash(path, index_root),
            parent=parent_obj,
        ),
        timestamps=timestamps_obj,
        attributes=AttributesObject(
            is_link=path.is_symlink(),
            storage_name=storage_name,
        ),
        items=None,
        metadata=None,
        session_id=session_id,
        indexed_at=_make_indexed_at(),
    )


def index_path(
    target: Path,
    config: IndexerConfig,
    *,
    delete_queue: list[Path] | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: threading.Event | None = None,
    session_id: str | None = None,
) -> IndexEntry:
    """Top-level entry point: classify target and dispatch.

    This is the single function consumed by the CLI, GUI, and public API.
    Resolves the target, determines whether it is a file or directory,
    and delegates to ``build_file_entry()`` or ``build_directory_entry()``.
    Forwards ``progress_callback`` and ``cancel_event`` to
    ``build_directory_entry()`` for directory targets; both parameters
    are ignored for single-file targets.
    """
    resolved = resolve_path(target)
    target_type = "file" if resolved.is_file() else "directory" if resolved.is_dir() else "unknown"
    logger.info("index_path: target=%s, type=%s", resolved, target_type)

    # Generate a session ID if the caller did not supply one.
    if session_id is None:
        session_id = str(uuid.uuid4())

    if resolved.is_file():
        entry = build_file_entry(
            resolved,
            config,
            delete_queue=delete_queue,
            cancel_event=cancel_event,
            session_id=session_id,
        )
        _annotate_relationships(entry, config)
        return entry

    if resolved.is_dir():
        entry = build_directory_entry(
            resolved,
            config,
            recursive=config.recursive,
            delete_queue=delete_queue,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
            session_id=session_id,
        )
        _annotate_relationships(entry, config)
        return entry

    raise IndexerTargetError(f"Target is neither a file nor a directory: {resolved}")


# ---------------------------------------------------------------------------
# Stage 7: Stale metadata cleanup (MetaMergeDelete post-processing)
# ---------------------------------------------------------------------------

_STALE_METADATA_RE = re.compile(
    r"_(meta[23]?|directorymeta[23]?)\.json$",
    re.IGNORECASE,
)
"""Matches indexer metadata output filenames:

``_meta.json``, ``_meta2.json``, ``_meta3.json``, ``_directorymeta.json``,
``_directorymeta2.json``, ``_directorymeta3.json``.  Used to identify stale
artifacts from prior indexer runs during Stage 7 cleanup.
"""


def _collect_protected_sidecars(
    entry: Any,
    root_path: Path,
    config: IndexerConfig,
    protected: set[Path],
) -> None:
    """Compute current-run output sidecar paths from the entry tree.

    Both the original-name and storage-name sidecar paths are added for
    file entries, ensuring no current-run output is accidentally deleted
    regardless of whether rename succeeded, failed, or was skipped.
    """
    if entry.type == "file":
        item_path = root_path / entry.file_system.relative
        # Protect original-name sidecar (pre-rename or rename-inactive).
        protected.add(build_sidecar_path(item_path, "file"))
        # Protect storage-name sidecar (post-rename).
        if entry.attributes and entry.attributes.storage_name:
            parent_dir = item_path.parent
            protected.add(parent_dir / f"{entry.attributes.storage_name}_meta3.json")
    elif entry.type == "directory":
        # The root directory entry (relative == ".") has no sidecar
        # written by _write_inplace_tree (it's skipped as _is_root).
        if entry.file_system.relative != "." and config.write_directory_meta:
            dir_path = root_path / entry.file_system.relative
            protected.add(build_sidecar_path(dir_path, "directory"))
        if entry.items:
            for child in entry.items:
                _collect_protected_sidecars(
                    child,
                    root_path,
                    config,
                    protected,
                )


def _collect_traversed_dirs(
    entry: Any,
    root_path: Path,
    traversed: list[Path],
) -> None:
    """Extract the set of directories traversed during indexing.

    Walks the entry tree and maps each directory entry back to its
    absolute path on disk via ``root_path / relative``.
    """
    if entry.type == "directory":
        if entry.file_system.relative == ".":
            traversed.append(root_path)
        else:
            traversed.append(root_path / entry.file_system.relative)
        if entry.items:
            for child in entry.items:
                _collect_traversed_dirs(child, root_path, traversed)


def cleanup_stale_metadata(
    entry: Any,
    root_path: Path,
    config: IndexerConfig,
) -> int:
    """Stage 7: Remove stale metadata artifacts from prior indexer runs.

    After MetaMergeDelete's Stage 6 (consumed-sidecar deletion), scans all
    directories traversed during the current run for files matching the
    indexer metadata naming convention (``_meta.json``, ``_meta2.json``,
    ``_meta3.json``, ``_directorymeta.json``, ``_directorymeta2.json``,
    ``_directorymeta3.json``).  Files that are
    NOT current-run output sidecars are identified as stale and deleted.

    This addresses the gap where Layer 1 exclusion prevents re-indexing
    of prior output artifacts but provides no cleanup mechanism, causing
    stale files to accumulate across repeated MetaMergeDelete runs.

    Args:
        entry: The root ``IndexEntry`` (or compatible object) from the
            current indexing run.
        root_path: Absolute path to the target directory (for directory
            indexing) or the target file's parent directory (for
            single-file indexing).
        config: Resolved configuration.  Only ``output_inplace``,
            ``write_directory_meta``, and ``rename`` are consulted
            (to determine which current-run sidecars to protect).

    Returns:
        Count of stale files successfully removed.
    """
    # ── Build the protected set (current-run output sidecars) ──────────
    protected: set[Path] = set()
    if config.output_inplace:
        _collect_protected_sidecars(entry, root_path, config, protected)

    # ── Collect directories traversed during this indexing run ──────────
    traversed: list[Path] = []
    if entry.type == "file":
        # Single-file index: scan the containing directory.
        traversed.append(root_path)
    else:
        _collect_traversed_dirs(entry, root_path, traversed)

    # ── Scan and delete stale artifacts ────────────────────────────────
    deleted = 0
    for dir_path in traversed:
        try:
            children = list(dir_path.iterdir())
        except OSError as exc:
            logger.warning(
                "Cannot scan directory for stale metadata: %s: %s",
                dir_path,
                exc,
            )
            continue
        for child in children:
            if not child.is_file():
                continue
            if not _STALE_METADATA_RE.search(child.name):
                continue
            if child in protected:
                continue
            # Stale artifact — delete it.
            try:
                child.unlink()
                logger.info("Stale metadata artifact removed: %s", child)
                deleted += 1
            except OSError as exc:
                logger.warning(
                    "Failed to remove stale metadata artifact: %s: %s",
                    child,
                    exc,
                )
    return deleted


def _walk_entries(root: IndexEntry) -> list[IndexEntry]:
    """Return all entries in a tree for in-place relationship annotation."""
    entries: list[IndexEntry] = []
    stack = [root]
    while stack:
        current = stack.pop()
        entries.append(current)
        if current.duplicates:
            stack.extend(reversed(current.duplicates))
        if current.items:
            stack.extend(reversed(current.items))
    return entries


def _annotate_relationships(root: IndexEntry, config: IndexerConfig) -> None:
    """Populate ``relationships`` fields using the v4 rule engine."""
    if config.no_sidecar_detection:
        return

    rules = load_rules(config)
    relationship_map = classify_relationships([root], rules)
    if not relationship_map:
        return

    for entry in _walk_entries(root):
        relationships = relationship_map.get(entry.id)
        if relationships:
            entry.relationships = relationships

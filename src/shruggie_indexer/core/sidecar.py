"""Sidecar metadata file discovery and parsing for shruggie-indexer.

Discovers sidecar metadata files adjacent to an indexed item (siblings in the
same directory) and parses them into ``MetadataEntry`` objects.  Ten sidecar
types are recognized, each with type-specific reading strategies:

    description, desktop_ini, generic_metadata, hash, json_metadata, link,
    screenshot, subtitles, thumbnail, torrent

Discovery uses compiled regex patterns from the configuration against sibling
filenames.  First matching type wins (pattern order is significant).

Parsing follows a format-appropriate fallback chain:
    JSON → plain text → binary (Base64) → error entry

The ``MetaMergeDelete`` queue accumulates sidecar paths for deferred deletion
in Stage 6 when ``config.meta_merge_delete`` is enabled.

See spec §6.7 for full behavioral guidance.
See ``docs/porting-reference/MetaFileRead_DependencyCatalog.md`` for the
original sidecar parsing logic being replaced.
"""

from __future__ import annotations

import base64
import configparser
import json
import logging
import os
from typing import TYPE_CHECKING, Any

from shruggie_indexer.core._formatting import human_readable_size as _human_readable_size
from shruggie_indexer.core.hashing import hash_file, hash_string, select_id
from shruggie_indexer.core.timestamps import extract_timestamps
from shruggie_indexer.models.schema import (
    FileSystemObject,
    MetadataAttributes,
    MetadataEntry,
    NameObject,
    SizeObject,
    TimestampsObject,
)

if TYPE_CHECKING:
    import re
    from collections.abc import Mapping
    from pathlib import Path

    from shruggie_indexer.config.types import IndexerConfig

__all__ = [
    "discover_and_parse",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Type detection
# ---------------------------------------------------------------------------


def _detect_type(
    filename: str,
    metadata_identify: Mapping[str, tuple[re.Pattern[str], ...]],
) -> str | None:
    """Determine the sidecar type of a filename by regex matching.

    Tests the filename against all patterns in ``metadata_identify`` in
    definition order.  Returns the first matching type name, or ``None``
    if no pattern matches.

    Args:
        filename: The sidecar filename to classify.
        metadata_identify: Ordered mapping of type names to compiled
            regex pattern tuples.

    Returns:
        The detected type name (e.g. ``"description"``), or ``None``.
    """
    for type_name, patterns in metadata_identify.items():
        for pattern in patterns:
            if pattern.search(filename):
                return type_name
    return None


def _is_excluded(
    filename: str,
    exclude_patterns: tuple[re.Pattern[str], ...],
) -> bool:
    """Check whether a filename matches any metadata exclusion pattern."""
    return any(pattern.search(filename) for pattern in exclude_patterns)


# ---------------------------------------------------------------------------
# Format-specific readers
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> Any:
    """Read and parse a JSON file.

    Returns the parsed JSON value, or raises on failure.
    """
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def _read_text(path: Path) -> str:
    """Read a file as UTF-8 text."""
    return path.read_text(encoding="utf-8")


def _read_lines(path: Path) -> list[str]:
    """Read a file and return non-empty lines."""
    text = path.read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip()]


def _read_binary_base64(path: Path) -> str:
    """Read a file as binary and encode to Base64 ASCII string."""
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _read_link(path: Path) -> str | None:
    """Extract URL or path from a link file.

    Supports ``.url`` files (INI format with ``URL=`` key) and falls back
    to Base64 encoding for ``.lnk`` and other binary link formats.

    Returns the extracted URL string, or a Base64-encoded representation.
    """
    suffix = path.suffix.lower()

    if suffix == ".url":
        return _read_url_file(path)

    if suffix == ".lnk":
        return _read_lnk_file(path)

    # Generic link files — try text, then binary.
    try:
        return _read_text(path)
    except (UnicodeDecodeError, ValueError):
        return _read_binary_base64(path)


def _read_url_file(path: Path) -> str | None:
    """Parse a Windows ``.url`` file for its URL value."""
    try:
        config = configparser.ConfigParser(interpolation=None)
        config.read(str(path), encoding="utf-8")
        url = config.get("InternetShortcut", "URL", fallback=None)
        if url:
            return url
    except (configparser.Error, OSError, UnicodeDecodeError):
        pass

    # Fallback: scan lines for URL= pattern.
    try:
        text = _read_text(path)
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("URL="):
                return stripped[4:]
    except (OSError, UnicodeDecodeError):
        pass

    return None


def _read_lnk_file(path: Path) -> str | None:
    """Attempt to extract target from a Windows ``.lnk`` file.

    Tries ``pylnk3`` first, then falls back to Base64 encoding.
    """
    # Try pylnk3 if available.
    try:
        import pylnk3  # type: ignore[import-untyped]

        lnk = pylnk3.parse(str(path))
        if hasattr(lnk, "path") and lnk.path:
            return lnk.path
        if hasattr(lnk, "relative_path") and lnk.relative_path:
            return lnk.relative_path
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("pylnk3 failed for %s: %s", path, exc)

    # Binary fallback.
    return _read_binary_base64(path)


# ---------------------------------------------------------------------------
# Type-specific data reading
# ---------------------------------------------------------------------------

# Types that use the JSON → text → binary fallback chain.
_FALLBACK_CHAIN_TYPES: frozenset[str] = frozenset({
    "description",
    "generic_metadata",
    "subtitles",
})


def _read_with_fallback(
    path: Path,
    sidecar_type: str,
    config: IndexerConfig,
) -> tuple[Any, str, list[str]]:
    """Read a sidecar file using the type-appropriate strategy.

    Returns ``(data, format, transforms)`` where:
    - ``data`` is the parsed content (may be ``None`` on total failure)
    - ``format`` describes the serialization format of ``data``
    - ``transforms`` lists any transformations applied

    Args:
        path: Absolute path to the sidecar file.
        sidecar_type: The detected sidecar type.
        config: Active configuration.

    Returns:
        A 3-tuple of ``(data, format_name, transforms)``.
    """
    type_attrs = config.metadata_attributes.get(sidecar_type)

    # --- Fallback chain types: JSON → text → binary ---
    if sidecar_type in _FALLBACK_CHAIN_TYPES:
        return _read_fallback_chain(path, type_attrs)

    # --- Type-specific readers ---
    if sidecar_type == "json_metadata":
        return _read_type_json_metadata(path)

    if sidecar_type == "hash":
        return _read_type_hash(path)

    if sidecar_type == "link":
        return _read_type_link(path)

    if sidecar_type == "desktop_ini":
        return _read_type_desktop_ini(path)

    if sidecar_type in ("screenshot", "thumbnail", "torrent"):
        return _read_type_binary(path)

    # Unknown type — try fallback chain.
    logger.debug("Unknown sidecar type %r — using fallback chain", sidecar_type)
    return _read_fallback_chain(path, type_attrs)


def _read_fallback_chain(
    path: Path,
    type_attrs: Any | None,
) -> tuple[Any, str, list[str]]:
    """Execute the JSON → text → binary fallback chain.

    Attempts each format in order based on what the type attributes expect.
    Falls back through the chain on failure.
    """
    expect_json = type_attrs.expect_json if type_attrs else True
    expect_text = type_attrs.expect_text if type_attrs else True
    expect_binary = type_attrs.expect_binary if type_attrs else True

    # Step 1: JSON
    if expect_json:
        try:
            data = _read_json(path)
            return data, "json", ["json_compact"]
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass

    # Step 2: Text
    if expect_text:
        try:
            data = _read_text(path)
            return data, "text", []
        except (OSError, UnicodeDecodeError):
            pass

    # Step 3: Binary
    if expect_binary:
        try:
            data = _read_binary_base64(path)
            return data, "base64", ["base64_encode"]
        except OSError:
            pass

    # All failed.
    logger.warning("All read strategies failed for sidecar: %s", path)
    return None, "error", []


def _read_type_json_metadata(path: Path) -> tuple[Any, str, list[str]]:
    """Read a json_metadata sidecar (JSON only, no fallback)."""
    try:
        data = _read_json(path)
        return data, "json", ["json_compact"]
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to parse JSON metadata sidecar %s: %s", path, exc)
        return None, "error", []


def _read_type_hash(path: Path) -> tuple[Any, str, list[str]]:
    """Read a hash sidecar (non-empty lines)."""
    try:
        lines = _read_lines(path)
        return lines, "lines", []
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read hash sidecar %s: %s", path, exc)
        return None, "error", []


def _read_type_link(path: Path) -> tuple[Any, str, list[str]]:
    """Read a link sidecar (URL/path extraction)."""
    try:
        data = _read_link(path)
        if data is None:
            return None, "error", []

        # Check if result is Base64 (from binary fallback) or text.
        # Base64 strings are ASCII-only and typically long; URLs/paths are not.
        # A simple heuristic: if the result looks like Base64, label accordingly.
        try:
            base64.b64decode(data, validate=True)
            if len(data) > 100:
                return data, "base64", ["base64_encode"]
        except Exception:
            pass

        return data, "text", []
    except OSError as exc:
        logger.warning("Failed to read link sidecar %s: %s", path, exc)
        return None, "error", []


def _read_type_desktop_ini(path: Path) -> tuple[Any, str, list[str]]:
    """Read a desktop.ini sidecar (text, binary fallback)."""
    try:
        data = _read_text(path)
        return data, "text", []
    except (OSError, UnicodeDecodeError):
        try:
            data = _read_binary_base64(path)
            return data, "base64", ["base64_encode"]
        except OSError as exc:
            logger.warning("Failed to read desktop.ini sidecar %s: %s", path, exc)
            return None, "error", []


def _read_type_binary(path: Path) -> tuple[Any, str, list[str]]:
    """Read a binary sidecar (screenshot, thumbnail, torrent)."""
    try:
        data = _read_binary_base64(path)
        return data, "base64", ["base64_encode"]
    except OSError as exc:
        logger.warning("Failed to read binary sidecar %s: %s", path, exc)
        return None, "error", []


# ---------------------------------------------------------------------------
# MIME type detection for binary sidecars
# ---------------------------------------------------------------------------

_BINARY_MIME_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".torrent": "application/x-bittorrent",
    ".lnk": "application/x-ms-shortcut",
    ".db": "application/x-thumbs-db",
}


def _detect_source_media_type(path: Path, fmt: str) -> str | None:
    """Determine source media type for a sidecar.

    Returns a MIME type string for binary-format sidecars, ``None`` for
    text/JSON formats.
    """
    if fmt not in ("base64",):
        return None
    return _BINARY_MIME_TYPES.get(path.suffix.lower())


# ---------------------------------------------------------------------------
# MetadataEntry construction
# ---------------------------------------------------------------------------


def _build_metadata_entry(
    sidecar_path: Path,
    sidecar_type: str,
    data: Any,
    fmt: str,
    transforms: list[str],
    index_root: Path,
    config: IndexerConfig,
) -> MetadataEntry:
    """Construct a complete ``MetadataEntry`` from a parsed sidecar.

    Args:
        sidecar_path: Absolute path to the sidecar file.
        sidecar_type: Detected type name.
        data: Parsed sidecar content.
        fmt: Format label (``'json'``, ``'text'``, ``'base64'``, ``'lines'``,
             ``'error'``).
        transforms: List of transform labels applied.
        index_root: Root directory of the indexing operation.
        config: Active configuration.

    Returns:
        A fully populated ``MetadataEntry``.
    """
    from shruggie_indexer.core.paths import relative_forward_slash

    # Hash the sidecar file contents.
    algorithms = ("md5", "sha256")
    if config.compute_sha512:
        algorithms = ("md5", "sha256", "sha512")

    try:
        file_hashes = hash_file(sidecar_path, algorithms=algorithms)
    except OSError:
        # If we can't hash the file, use name hashes.
        file_hashes = hash_string(sidecar_path.name, algorithms=algorithms)

    # Identity: "y" + digest selected by configured algorithm.
    entry_id = select_id(file_hashes, config.id_algorithm, "y")

    # Name hashing.
    name_hashes = hash_string(sidecar_path.name, algorithms=algorithms)
    name_obj = NameObject(text=sidecar_path.name, hashes=name_hashes)

    # Filesystem location.
    rel_path = relative_forward_slash(sidecar_path, index_root)
    file_system = FileSystemObject(relative=rel_path, parent=None)

    # Size and timestamps from stat.
    try:
        stat_result = os.stat(sidecar_path)
        size_obj = SizeObject(
            text=_human_readable_size(stat_result.st_size),
            bytes=stat_result.st_size,
        )
        timestamps_obj: TimestampsObject | None = extract_timestamps(stat_result)
    except OSError:
        size_obj = SizeObject(text="0 B", bytes=0)
        timestamps_obj = None

    # Source media type for binary sidecars.
    source_media_type = _detect_source_media_type(sidecar_path, fmt)

    # Attributes.
    attributes = MetadataAttributes(
        type=sidecar_type,
        format=fmt,
        transforms=list(transforms),
        source_media_type=source_media_type,
    )

    return MetadataEntry(
        id=entry_id,
        origin="sidecar",
        name=name_obj,
        hashes=file_hashes,
        attributes=attributes,
        data=data,
        file_system=file_system,
        size=size_obj,
        timestamps=timestamps_obj,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def discover_and_parse(
    item_path: Path,
    item_name: str,
    siblings: list[Path],
    config: IndexerConfig,
    *,
    index_root: Path | None = None,
    delete_queue: list[Path] | None = None,
) -> list[MetadataEntry]:
    """Discover and parse sidecar metadata files for an item.

    Examines the ``siblings`` list (pre-enumerated by the entry builder from
    ``list_children()``) and identifies sidecar metadata files by matching
    their names against the configured type-detection regex patterns.

    Each discovered sidecar is read using a format-appropriate strategy and
    wrapped in a ``MetadataEntry`` with full provenance (filesystem path,
    size, timestamps, hashes).

    Args:
        item_path: Absolute path to the item being indexed.
        item_name: The item's filename (used to contextualise pattern
            matching for types that reference the parent item name).
        siblings: Pre-enumerated list of all file paths in the same
            directory as ``item_path``.  Avoids re-scanning.
        config: The active :class:`~shruggie_indexer.config.types.IndexerConfig`.
        index_root: Root directory of the indexing operation.  Used to
            compute relative paths for sidecar entries.  Defaults to
            ``item_path.parent``.
        delete_queue: When ``config.meta_merge_delete`` is ``True`` and this
            list is provided, sidecar paths are appended for deferred deletion
            in Stage 6.

    Returns:
        List of ``MetadataEntry`` objects, empty if no sidecars found.
    """
    if index_root is None:
        index_root = item_path.parent

    metadata_identify = config.metadata_identify
    exclude_patterns = config.metadata_exclude_patterns

    entries: list[MetadataEntry] = []
    item_path_resolved = item_path.resolve() if item_path.exists() else item_path

    for sibling_path in siblings:
        # Skip the item itself.
        sibling_resolved = (
            sibling_path.resolve() if sibling_path.exists() else sibling_path
        )
        if sibling_resolved == item_path_resolved:
            continue

        sibling_name = sibling_path.name

        # Check exclusion patterns first.
        if _is_excluded(sibling_name, exclude_patterns):
            continue

        # Detect type by matching against identification patterns.
        sidecar_type = _detect_type(sibling_name, metadata_identify)
        if sidecar_type is None:
            continue

        logger.debug(
            "Sidecar discovered: %s (type=%s) for item %s",
            sibling_name,
            sidecar_type,
            item_name,
        )

        # Read the sidecar content using the type-specific strategy.
        data, fmt, transforms = _read_with_fallback(sibling_path, sidecar_type, config)

        # Build the MetadataEntry.
        entry = _build_metadata_entry(
            sidecar_path=sibling_path,
            sidecar_type=sidecar_type,
            data=data,
            fmt=fmt,
            transforms=transforms,
            index_root=index_root,
            config=config,
        )
        entries.append(entry)

        # MetaMergeDelete queue.
        if config.meta_merge_delete and delete_queue is not None:
            delete_queue.append(sibling_path)

    return entries

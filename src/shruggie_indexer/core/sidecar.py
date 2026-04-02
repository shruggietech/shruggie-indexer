"""Legacy sidecar metadata file discovery and parsing.

Deprecated in v4: the active indexing pipeline now treats all files as
first-class ``IndexEntry`` objects and annotates associations through the
relationship rule engine in ``core.rules``.

Discovers sidecar metadata files adjacent to an indexed item (siblings in the
same directory) and parses them into ``MetadataEntry`` objects.  Eleven sidecar
types are recognized, each with type-specific reading strategies:

    description, desktop_ini, generic_metadata, hash, json_metadata, link,
    screenshot, shortcut, subtitles, thumbnail, torrent

Discovery uses compiled regex patterns from the configuration against sibling
filenames.  First matching type wins (pattern order is significant).

Parsing follows a format-appropriate fallback chain:
    JSON → plain text → binary (Base64) → error entry

The ``MetaMergeDelete`` queue accumulates sidecar paths for deferred deletion
in Stage 6 when ``config.meta_merge_delete`` is enabled.

See spec §6.7 for historical behavioral guidance.
See ``docs/porting-reference/MetaFileRead_DependencyCatalog.md`` for the
original sidecar parsing logic being replaced.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from shruggie_indexer.config.defaults import DEFAULT_METADATA_IDENTIFY_STRINGS
from shruggie_indexer.core.hashing import hash_file, hash_string, select_id
from shruggie_indexer.models.schema import (
    EncodingObject,
    MetadataAttributes,
    MetadataEntry,
    NameObject,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from shruggie_indexer.config.types import IndexerConfig

__all__ = [
    "discover_and_parse",
]

logger = logging.getLogger(__name__)


_LEGACY_METADATA_IDENTIFY: dict[str, tuple[re.Pattern[str], ...]] = {
    type_name: tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
    for type_name, patterns in DEFAULT_METADATA_IDENTIFY_STRINGS.items()
}


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
# Text formats: per-format readers with encoding variants
# ---------------------------------------------------------------------------

# Formats that carry text content which undergoes lossy decode.
_TEXT_FORMATS: frozenset[str] = frozenset({"json", "text", "lines"})


def _read_text_with_encoding(
    path: Path,
    *,
    detect_charset_enabled: bool = True,
) -> tuple[str, EncodingObject | None]:
    """Read a file as UTF-8 text, capturing encoding metadata.

    Reads raw bytes, performs encoding detection, then decodes.
    Returns (decoded_text, encoding_object).
    """
    raw = path.read_bytes()

    from shruggie_indexer.core.encoding import detect_bytes_encoding

    enc = detect_bytes_encoding(raw, detect_charset_enabled=detect_charset_enabled)

    # Decode with BOM handling (utf-8-sig strips BOM automatically).
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")

    return text, enc


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


def _read_url_as_text(path: Path) -> tuple[Any, str, list[str]]:
    """Read a ``.url`` file through the text cascade.

    Stores the full file content verbatim (including the
    ``[InternetShortcut]`` header and ``URL=`` key) as ``format: "text"``.
    This preserves Windows shortcut functionality on rollback.
    """
    try:
        data = _read_text(path)
        return data, "text", []
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read .url sidecar %s: %s", path, exc)
        return None, "error", []


def _read_lnk_with_metadata(path: Path) -> tuple[Any, str, list[str], dict[str, str] | None]:
    """Read a ``.lnk`` file with dual-storage: base64 data + link_metadata.

    Always base64-encodes the raw binary for byte-perfect rollback.
    Additionally attempts to extract structured metadata fields
    (target_path, working_directory, arguments, icon_location,
    description, hotkey) using the ``LnkParse3`` library.

    Returns ``(data, format, transforms, link_metadata)`` where
    ``link_metadata`` is ``None`` when extraction fails or the library
    is unavailable.
    """
    # Always base64-encode for rollback fidelity.
    try:
        b64_data = _read_binary_base64(path)
    except OSError as exc:
        logger.warning("Failed to read .lnk sidecar %s: %s", path, exc)
        return None, "error", [], None

    # Attempt metadata extraction.
    link_metadata = _extract_lnk_metadata(path)

    return b64_data, "base64", ["base64_encode"], link_metadata


def _extract_lnk_metadata(path: Path) -> dict[str, str] | None:
    """Extract structured metadata from a ``.lnk`` binary shortcut.

    Uses ``LnkParse3`` if available.  Returns a dict of non-empty fields,
    or ``None`` if extraction fails or the library is missing.
    """
    try:
        from shruggie_indexer.core.lnk_parser import parse_lnk
    except ImportError:
        logger.debug(".lnk parser unavailable — skipping metadata extraction for %s", path)
        return None

    try:
        return parse_lnk(path)
    except Exception as exc:
        logger.warning(".lnk metadata extraction failed for %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Type-specific data reading
# ---------------------------------------------------------------------------

# Types that use the JSON → text → binary fallback chain.
_FALLBACK_CHAIN_TYPES: frozenset[str] = frozenset(
    {
        "description",
        "generic_metadata",
        "subtitles",
    }
)


def _detect_text_encoding(
    path: Path,
    fmt: str,
    config: IndexerConfig,
) -> EncodingObject | None:
    """Detect encoding metadata for a sidecar with a text-based format.

    Only runs for text formats (json, text, lines) when encoding detection
    is enabled.  Returns ``None`` for binary formats, error, or when
    detection is disabled.
    """
    if fmt not in _TEXT_FORMATS:
        return None
    if not config.detect_encoding:
        return None

    from shruggie_indexer.core.encoding import detect_file_encoding

    return detect_file_encoding(
        path,
        detect_charset_enabled=config.detect_charset,
    )


def _read_with_fallback(
    path: Path,
    sidecar_type: str,
    config: IndexerConfig,
) -> tuple[Any, str, list[str], dict[str, Any] | None, EncodingObject | None]:
    """Read a sidecar file using the type-appropriate strategy.

    Returns ``(data, format, transforms, extra_attrs, encoding)`` where:
    - ``data`` is the parsed content (may be ``None`` on total failure)
    - ``format`` describes the serialization format of ``data``
    - ``transforms`` lists any transformations applied
    - ``extra_attrs`` is an optional dict of additional
      ``MetadataAttributes`` fields (e.g. ``json_style``,
      ``link_metadata``, ``type_override``)
    - ``encoding`` is an :class:`EncodingObject` for text-format sidecars,
      or ``None`` for binary formats and when detection is disabled

    Args:
        path: Absolute path to the sidecar file.
        sidecar_type: The detected sidecar type.
        config: Active configuration.

    Returns:
        A 5-tuple of ``(data, format_name, transforms, extra_attrs, encoding)``.
    """
    metadata_attributes = getattr(config, "metadata_attributes", {})
    type_attrs = metadata_attributes.get(sidecar_type)

    # --- Fallback chain types: JSON → text → binary ---
    if sidecar_type in _FALLBACK_CHAIN_TYPES:
        data, fmt, transforms = _read_fallback_chain(path, type_attrs)
        extra = _detect_json_style_extra(path, fmt)
        enc = _detect_text_encoding(path, fmt, config)
        return data, fmt, transforms, extra, enc

    # --- Type-specific readers ---
    if sidecar_type == "json_metadata":
        data, fmt, transforms = _read_type_json_metadata(path)
        extra = _detect_json_style_extra(path, fmt)
        enc = _detect_text_encoding(path, fmt, config)
        return data, fmt, transforms, extra, enc

    if sidecar_type == "hash":
        data, fmt, transforms = _read_type_hash(path)
        enc = _detect_text_encoding(path, fmt, config)
        return data, fmt, transforms, None, enc

    if sidecar_type == "link":
        data, fmt, transforms, extra = _read_type_link(path)
        enc = _detect_text_encoding(path, fmt, config)
        return data, fmt, transforms, extra, enc

    if sidecar_type == "desktop_ini":
        data, fmt, transforms = _read_type_desktop_ini(path)
        enc = _detect_text_encoding(path, fmt, config)
        return data, fmt, transforms, None, enc

    if sidecar_type in ("screenshot", "thumbnail", "torrent"):
        data, fmt, transforms = _read_type_binary(path)
        return data, fmt, transforms, None, None

    # Unknown type — try fallback chain.
    logger.debug("Unknown sidecar type %r — using fallback chain", sidecar_type)
    data, fmt, transforms = _read_fallback_chain(path, type_attrs)
    extra = _detect_json_style_extra(path, fmt)
    enc = _detect_text_encoding(path, fmt, config)
    return data, fmt, transforms, extra, enc


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


def _detect_json_indent(path: Path) -> tuple[str, str | None]:
    """Detect JSON formatting style and indent string.

    Returns (json_style, json_indent) where:
    - json_style is "compact" or "pretty"
    - json_indent is the literal indent string (e.g., "  ", "    ",
      "\\t") for pretty JSON, or None for compact JSON.

    Detection heuristic: find the first line that starts with whitespace
    after a newline. The leading whitespace of that line (up to the first
    non-whitespace character) is the indent string. If the file contains
    no indented lines, it is compact.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "compact", None

    # Find first indented line.
    for line in raw.split("\n")[1:]:  # Skip first line (opening brace).
        if line and line[0] in (" ", "\t"):
            # Extract the indent: all leading whitespace.
            indent = ""
            for ch in line:
                if ch in (" ", "\t"):
                    indent += ch
                else:
                    break
            if indent:
                return "pretty", indent
    return "compact", None


def _detect_json_style_extra(
    path: Path,
    fmt: str,
) -> dict[str, Any] | None:
    """Return extra attributes dict with ``json_style`` and ``json_indent``.

    Returns ``None`` for non-JSON formats.
    """
    if fmt != "json":
        return None
    style, indent = _detect_json_indent(path)
    result: dict[str, Any] = {"json_style": style}
    if indent is not None:
        result["json_indent"] = indent
    return result


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


def _read_type_link(path: Path) -> tuple[Any, str, list[str], dict[str, Any] | None]:
    """Read a link sidecar.

    ``.url`` files use the text cascade (full content preserved).
    ``.lnk`` files use base64 encoding with optional metadata extraction.
    Other link files use text → binary fallback.

    Returns ``(data, format, transforms, extra_attrs)`` where
    ``extra_attrs`` is a dict of additional ``MetadataAttributes`` fields
    (e.g. ``link_metadata``, overridden ``type``) or ``None``.
    """
    suffix = path.suffix.lower()

    if suffix == ".url":
        data, fmt, transforms = _read_url_as_text(path)
        return data, fmt, transforms, None

    if suffix == ".lnk":
        data, fmt, transforms, link_meta = _read_lnk_with_metadata(path)
        extra: dict[str, Any] = {"type_override": "shortcut"}
        if link_meta is not None:
            extra["link_metadata"] = link_meta
        return data, fmt, transforms, extra

    # Generic link files — try text, then binary.
    try:
        data = _read_text(path)
        return data, "text", [], None
    except (UnicodeDecodeError, ValueError):
        pass
    try:
        data = _read_binary_base64(path)
        return data, "base64", ["base64_encode"], None
    except OSError as exc:
        logger.warning("Failed to read link sidecar %s: %s", path, exc)
        return None, "error", [], None


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
    *,
    extra_attrs: dict[str, Any] | None = None,
    encoding: EncodingObject | None = None,
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
        extra_attrs: Optional dict of additional ``MetadataAttributes``
            fields.  Supported keys: ``json_style``, ``link_metadata``,
            ``type_override`` (overrides the ``type`` field on the
            constructed attributes).

    Returns:
        A fully populated ``MetadataEntry``.
    """
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

    # Source media type for binary sidecars.
    source_media_type = _detect_source_media_type(sidecar_path, fmt)

    # Resolve extra attributes from the reader.
    effective_type = sidecar_type
    link_metadata: dict[str, str] | None = None

    if extra_attrs:
        effective_type = extra_attrs.get("type_override", sidecar_type)
        link_metadata = extra_attrs.get("link_metadata")

    # Attributes.
    attributes = MetadataAttributes(
        type=effective_type,
        format=fmt,
        transforms=list(transforms),
        source_media_type=source_media_type,
        link_metadata=link_metadata,
    )

    return MetadataEntry(
        id=entry_id,
        origin="sidecar",
        name=name_obj,
        hashes=file_hashes,
        attributes=attributes,
        data=data,
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
    sidecar_type_cache: dict[Path, str | None] | None = None,
    sidecar_entry_cache: dict[Path, MetadataEntry] | None = None,
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
        sidecar_type_cache: Optional cache for sidecar type detection results,
            keyed by sibling path.
        sidecar_entry_cache: Optional cache for parsed ``MetadataEntry``
            objects, keyed by sidecar path.

    Returns:
        List of ``MetadataEntry`` objects, empty if no sidecars found.
    """
    if index_root is None:
        index_root = item_path.parent

    metadata_identify = getattr(config, "metadata_identify", _LEGACY_METADATA_IDENTIFY)
    exclude_patterns = config.metadata_exclude_patterns

    entries: list[MetadataEntry] = []
    item_path_resolved = item_path.resolve() if item_path.exists() else item_path

    for sibling_path in siblings:
        # Skip the item itself.
        sibling_resolved = sibling_path.resolve() if sibling_path.exists() else sibling_path
        if sibling_resolved == item_path_resolved:
            continue

        sibling_name = sibling_path.name

        # Check exclusion patterns first.
        if _is_excluded(sibling_name, exclude_patterns):
            continue

        # Detect type by matching against identification patterns.
        if sidecar_type_cache is not None:
            sidecar_type = sidecar_type_cache.get(sibling_path)
            if sibling_path not in sidecar_type_cache:
                sidecar_type = _detect_type(sibling_name, metadata_identify)
                sidecar_type_cache[sibling_path] = sidecar_type
        else:
            sidecar_type = _detect_type(sibling_name, metadata_identify)

        if sidecar_type is None:
            continue

        logger.debug(
            "Sidecar discovered: %s (type=%s) for item %s",
            sibling_name,
            sidecar_type,
            item_name,
        )

        if sidecar_entry_cache is not None and sibling_path in sidecar_entry_cache:
            entry = sidecar_entry_cache[sibling_path]
        else:
            # Read the sidecar content using the type-specific strategy.
            data, fmt, transforms, extra_attrs, enc = _read_with_fallback(
                sibling_path,
                sidecar_type,
                config,
            )

            # Build the MetadataEntry.
            entry = _build_metadata_entry(
                sidecar_path=sibling_path,
                sidecar_type=sidecar_type,
                data=data,
                fmt=fmt,
                transforms=transforms,
                index_root=index_root,
                config=config,
                extra_attrs=extra_attrs,
                encoding=enc,
            )
            if sidecar_entry_cache is not None:
                sidecar_entry_cache[sibling_path] = entry

        entries.append(entry)

        # MetaMergeDelete queue.
        if bool(getattr(config, "meta_merge_delete", False)) and delete_queue is not None:
            delete_queue.append(sibling_path)

    return entries

"""Path resolution and manipulation for shruggie-indexer.

Provides all path-related operations used by the rest of the indexing engine:
resolving paths to canonical absolute form, extracting path components,
validating file extensions, and constructing derived paths for output files.

This is the single source of truth for path handling — no other module
performs its own path manipulation (DEV-04).

See spec §6.2 for full behavioral guidance.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from shruggie_indexer.config.types import IndexerConfig

__all__ = [
    "PathComponents",
    "build_sidecar_path",
    "build_storage_path",
    "extract_components",
    "resolve_path",
    "validate_extension",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class PathComponents(NamedTuple):
    """Decomposed path components returned by :func:`extract_components`.

    All components are derived from ``pathlib.Path`` properties rather than
    string manipulation.
    """

    name: str
    """Full filename including extension (``Path.name``)."""

    stem: str
    """Filename without the final extension (``Path.stem``)."""

    suffix: str | None
    """Extension without leading dot, lowercased.  ``None`` if absent."""

    parent_name: str
    """Leaf name of the parent directory.  Empty string for root-level items."""

    parent_path: Path
    """Absolute path of the parent directory."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_path(path: Path | str) -> Path:
    """Resolve a path to its canonical absolute form.

    Resolves symlinks, normalizes separators, and collapses ``..`` and ``.``
    components.  Falls back to non-strict resolution when the path does not
    exist on disk.

    Args:
        path: The path to resolve (may be relative or absolute).

    Returns:
        An absolute, resolved :class:`~pathlib.Path`.

    Raises:
        IndexerError: If the path cannot be resolved at all.
    """
    from shruggie_indexer.exceptions import IndexerError

    p = Path(path)
    try:
        return p.resolve(strict=True)
    except (OSError, ValueError):
        pass

    try:
        return p.resolve(strict=False)
    except (OSError, ValueError) as exc:
        raise IndexerError(f"Cannot resolve path: {path}") from exc


def extract_components(path: Path) -> PathComponents:
    """Extract all path components needed by the entry builder.

    The suffix is lowercased and has its leading dot stripped.  If the path
    has no extension, ``suffix`` is ``None``.

    Args:
        path: An absolute, resolved path.

    Returns:
        A :class:`PathComponents` named tuple.
    """
    raw_suffix = path.suffix
    if raw_suffix:
        suffix: str | None = raw_suffix.lstrip(".").lower()
    else:
        suffix = None

    return PathComponents(
        name=path.name,
        stem=path.stem,
        suffix=suffix,
        parent_name=path.parent.name,
        parent_path=path.parent,
    )


def validate_extension(suffix: str | None, config: IndexerConfig) -> str | None:
    """Validate a file extension against the configured regex pattern.

    Returns the validated extension string (lowercase, no leading dot) if
    valid; returns ``None`` if the extension is empty or fails validation.

    Args:
        suffix: The extension to validate (lowercase, no leading dot), or
            ``None``.
        config: The active :class:`~shruggie_indexer.config.types.IndexerConfig`.

    Returns:
        The validated extension, or ``None``.
    """
    if not suffix:
        return None

    pattern = config.extension_validation_pattern
    if not pattern:
        return suffix

    if re.fullmatch(pattern, suffix):
        return suffix

    logger.debug("Extension rejected by validation pattern: %r", suffix)
    return None


def build_sidecar_path(item_path: Path, item_type: str) -> Path:
    """Construct the path for an in-place sidecar output file.

    For files: ``<item_path>_meta2.json``
    For directories: ``<item_path>/_directorymeta2.json``

    Args:
        item_path: Absolute path to the indexed item.
        item_type: ``"file"`` or ``"directory"``.

    Returns:
        The sidecar output :class:`~pathlib.Path`.
    """
    if item_type == "directory":
        return item_path / "_directorymeta2.json"
    return item_path.parent / f"{item_path.name}_meta2.json"


def build_storage_path(item_path: Path, storage_name: str) -> Path:
    """Construct the target path for a rename operation.

    Returns ``item_path.parent / storage_name``.

    Args:
        item_path: Absolute path to the original item.
        storage_name: The deterministic storage name.

    Returns:
        The rename-target :class:`~pathlib.Path`.
    """
    return item_path.parent / storage_name


def relative_forward_slash(path: Path, root: Path) -> str:
    """Compute the relative path from *root* to *path* using forward slashes.

    Used to populate the ``file_system.relative`` field in the v2 schema,
    which always uses ``/`` as the separator regardless of platform.

    Args:
        path: The absolute path to express relatively.
        root: The root from which to compute the relative path.

    Returns:
        A forward-slash-separated relative path string.
    """
    try:
        rel = path.relative_to(root)
    except ValueError:
        # If path is not relative to root, fall back to the full path.
        rel = path
    return str(PurePosixPath(rel))

"""Core processing modules for shruggie-indexer.

This sub-package contains the engine modules that perform filesystem traversal,
hashing, timestamp extraction, EXIF metadata collection, sidecar parsing, entry
orchestration, JSON serialization, and rename operations.
"""

import contextlib

from shruggie_indexer.core.hashing import (
    NULL_HASHES,
    hash_directory_id,
    hash_file,
    hash_string,
    select_id,
)
from shruggie_indexer.core.paths import (
    PathComponents,
    build_sidecar_path,
    build_storage_path,
    extract_components,
    relative_forward_slash,
    resolve_path,
    validate_extension,
)
from shruggie_indexer.core.timestamps import extract_timestamps

__all__ = [
    "NULL_HASHES",
    "PathComponents",
    "build_directory_entry",
    "build_file_entry",
    "build_sidecar_path",
    "build_storage_path",
    "extract_components",
    "extract_timestamps",
    "hash_directory_id",
    "hash_file",
    "hash_string",
    "index_path",
    "relative_forward_slash",
    "resolve_path",
    "select_id",
    "validate_extension",
]

with contextlib.suppress(ImportError):
    from shruggie_indexer.core.entry import (
        build_directory_entry,
        build_file_entry,
        index_path,
    )

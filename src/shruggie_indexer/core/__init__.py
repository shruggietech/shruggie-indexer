"""Core processing modules for shruggie-indexer.

This sub-package contains the engine modules that perform filesystem traversal,
hashing, timestamp extraction, EXIF metadata collection, sidecar parsing, entry
orchestration, JSON serialization, and rename operations.
"""

import contextlib

__all__ = [
    "build_directory_entry",
    "build_file_entry",
    "index_path",
]

with contextlib.suppress(ImportError):
    from shruggie_indexer.core.entry import (
        build_directory_entry,
        build_file_entry,
        index_path,
    )

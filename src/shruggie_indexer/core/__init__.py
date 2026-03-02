"""Core processing modules for shruggie-indexer.

This sub-package contains the engine modules that perform filesystem traversal,
hashing, timestamp extraction, EXIF metadata collection, sidecar parsing, entry
orchestration, JSON serialization, and rename operations.
"""

from shruggie_indexer.core.dedup import (
    DedupAction,
    DedupRegistry,
    DedupResult,
    DedupStats,
    apply_dedup,
    cleanup_duplicate_files,
    scan_tree,
)
from shruggie_indexer.core.entry import (
    build_directory_entry,
    build_file_entry,
    index_path,
)
from shruggie_indexer.core.exif import extract_exif
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
from shruggie_indexer.core.progress import ProgressEvent
from shruggie_indexer.core.rename import rename_item
from shruggie_indexer.core.rollback import (
    LocalSourceResolver,
    RollbackAction,
    RollbackPlan,
    RollbackResult,
    RollbackStats,
    discover_meta2_files,
    execute_rollback,
    load_meta2,
    plan_rollback,
    verify_file_hash,
)
from shruggie_indexer.core.serializer import serialize_entry, write_inplace, write_output
from shruggie_indexer.core.sidecar import discover_and_parse
from shruggie_indexer.core.timestamps import extract_timestamps
from shruggie_indexer.core.traversal import list_children

__all__ = [
    "DedupAction",
    "DedupRegistry",
    "DedupResult",
    "DedupStats",
    "LocalSourceResolver",
    "NULL_HASHES",
    "PathComponents",
    "ProgressEvent",
    "RollbackAction",
    "RollbackPlan",
    "RollbackResult",
    "RollbackStats",
    "apply_dedup",
    "build_directory_entry",
    "build_file_entry",
    "build_sidecar_path",
    "build_storage_path",
    "cleanup_duplicate_files",
    "discover_and_parse",
    "discover_meta2_files",
    "execute_rollback",
    "extract_components",
    "extract_exif",
    "extract_timestamps",
    "hash_directory_id",
    "hash_file",
    "hash_string",
    "index_path",
    "list_children",
    "load_meta2",
    "plan_rollback",
    "relative_forward_slash",
    "rename_item",
    "resolve_path",
    "scan_tree",
    "select_id",
    "serialize_entry",
    "validate_extension",
    "verify_file_hash",
    "write_inplace",
    "write_output",
]

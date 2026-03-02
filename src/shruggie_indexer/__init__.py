"""shruggie-indexer: Filesystem indexer with hash-based identity, metadata extraction,
and structured JSON output.

Public API surface (section 9.1 of the spec). The full set of names is available
as the core modules are delivered across sprints.
"""

from shruggie_indexer._version import __version__
from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import IndexerConfig, MetadataTypeAttributes
from shruggie_indexer.core.entry import (
    build_directory_entry,
    build_file_entry,
    index_path,
)
from shruggie_indexer.core.exif import shutdown_exiftool
from shruggie_indexer.core.progress import ProgressEvent
from shruggie_indexer.core.rename import rename_inplace_sidecar, rename_item
from shruggie_indexer.core.rollback import (
    LocalSourceResolver,
    RollbackAction,
    RollbackPlan,
    RollbackResult,
    RollbackStats,
    SourceResolver,
    discover_meta2_files,
    execute_rollback,
    load_meta2,
    plan_rollback,
    verify_file_hash,
)
from shruggie_indexer.core.serializer import serialize_entry, write_inplace
from shruggie_indexer.exceptions import (
    IndexerCancellationError,
    IndexerConfigError,
    IndexerError,
    IndexerRuntimeError,
    IndexerTargetError,
    RollbackError,
    RenameError,
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
    TimestampsObject,
)

__all__ = [
    "AttributesObject",
    "FileSystemObject",
    "HashSet",
    "IndexEntry",
    "IndexerCancellationError",
    "IndexerConfig",
    "IndexerConfigError",
    "IndexerError",
    "IndexerRuntimeError",
    "IndexerTargetError",
    "LocalSourceResolver",
    "MetadataAttributes",
    "MetadataEntry",
    "MetadataTypeAttributes",
    "NameObject",
    "ParentObject",
    "ProgressEvent",
    "RenameError",
    "RollbackAction",
    "RollbackError",
    "RollbackPlan",
    "RollbackResult",
    "RollbackStats",
    "SizeObject",
    "SourceResolver",
    "TimestampPair",
    "TimestampsObject",
    "__version__",
    "build_directory_entry",
    "build_file_entry",
    "discover_meta2_files",
    "execute_rollback",
    "index_path",
    "load_config",
    "load_meta2",
    "plan_rollback",
    "rename_inplace_sidecar",
    "rename_item",
    "serialize_entry",
    "shutdown_exiftool",
    "verify_file_hash",
    "write_inplace",
]

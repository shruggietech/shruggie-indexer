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
from shruggie_indexer.core.progress import ProgressEvent
from shruggie_indexer.core.serializer import serialize_entry
from shruggie_indexer.exceptions import (
    IndexerCancellationError,
    IndexerConfigError,
    IndexerError,
    IndexerRuntimeError,
    IndexerTargetError,
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
    "MetadataAttributes",
    "MetadataEntry",
    "MetadataTypeAttributes",
    "NameObject",
    "ParentObject",
    "ProgressEvent",
    "RenameError",
    "SizeObject",
    "TimestampPair",
    "TimestampsObject",
    "__version__",
    "build_directory_entry",
    "build_file_entry",
    "index_path",
    "load_config",
    "serialize_entry",
]

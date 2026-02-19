"""shruggie-indexer: Filesystem indexer with hash-based identity, metadata extraction,
and structured JSON output.

Public API surface (section 9.1 of the spec). Names are imported lazily — modules that
do not yet exist are silently skipped. The full set becomes available as the package is
built out across sprints.
"""

import contextlib

from shruggie_indexer._version import __version__

# ─── Lazy imports for modules not yet implemented ───────────────────────────
# Guarded by contextlib.suppress so the package remains importable before
# the target modules exist.  Each block will be replaced with a direct
# import once the corresponding sprint delivers the module.
from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import IndexerConfig, MetadataTypeAttributes
from shruggie_indexer.exceptions import (
    IndexerCancellationError,
    IndexerConfigError,
    IndexerError,
    IndexerRuntimeError,
    IndexerTargetError,
    RenameError,
)

with contextlib.suppress(ImportError):
    from shruggie_indexer.core.entry import (  # type: ignore[import-not-found]
        build_directory_entry,
        build_file_entry,
        index_path,
    )

with contextlib.suppress(ImportError):
    from shruggie_indexer.core.progress import ProgressEvent  # type: ignore[import-not-found]

with contextlib.suppress(ImportError):
    from shruggie_indexer.core.serializer import serialize_entry  # type: ignore[import-not-found]

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

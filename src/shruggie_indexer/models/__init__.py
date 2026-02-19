"""Data models for shruggie-indexer v2 schema output."""

import contextlib

__all__ = [
    "HashSet",
    "IndexEntry",
    "MetadataEntry",
    "NameObject",
    "ParentObject",
    "SizeObject",
    "TimestampPair",
    "TimestampsObject",
]

with contextlib.suppress(ImportError):
    from shruggie_indexer.models.schema import (
        HashSet,
        IndexEntry,
        MetadataEntry,
        NameObject,
        ParentObject,
        SizeObject,
        TimestampPair,
        TimestampsObject,
    )

"""Configuration type definitions for shruggie-indexer.

All configuration is represented by a single top-level frozen dataclass,
``IndexerConfig``.  Every ``core/`` module that consumes configuration
receives it as an ``IndexerConfig`` parameter — no module inspects environment
variables, reads files, or accesses global state at runtime.

See spec §7.1 and §9.3 for full behavioral guidance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import re
    from pathlib import Path

__all__ = [
    "ExiftoolConfig",
    "IndexerConfig",
    "MetadataTypeAttributes",
]


@dataclass(frozen=True)
class MetadataTypeAttributes:
    """Behavioral attributes for a single sidecar metadata type.

    Corresponds to the original ``$MetadataFileParser.Attributes.<TypeName>``
    sub-objects.  Field names use snake_case per Python convention.
    """

    about: str
    expect_json: bool
    expect_text: bool
    expect_binary: bool
    parent_can_be_file: bool
    parent_can_be_directory: bool


@dataclass(frozen=True)
class ExiftoolConfig:
    """Exiftool-specific configuration."""

    exclude_extensions: frozenset[str]
    base_args: tuple[str, ...]


@dataclass(frozen=True)
class IndexerConfig:
    """Immutable configuration for a single indexing invocation.

    All fields have defaults — an ``IndexerConfig`` constructed with no
    arguments represents the compiled default configuration.  To create a
    modified copy, use ``dataclasses.replace()``.

    This class is frozen (immutable).  Mutable collection types are replaced
    with their immutable counterparts (``frozenset``, ``tuple``,
    ``MappingProxyType``) to enforce immutability at the field level.
    """

    # ── Target and traversal ────────────────────────────────────────────
    recursive: bool = True
    id_algorithm: str = "md5"
    compute_sha512: bool = False

    # ── Output routing ──────────────────────────────────────────────────
    output_stdout: bool = True
    output_file: Path | None = None
    output_inplace: bool = False

    # ── Metadata processing ─────────────────────────────────────────────
    extract_exif: bool = False
    meta_merge: bool = False
    meta_merge_delete: bool = False

    # ── Encoding detection ──────────────────────────────────────────────
    detect_encoding: bool = True
    """Enable BOM, line-ending, and character encoding detection.

    When True, the indexer reads the first 64 KB of each file in binary
    mode to detect encoding metadata. Default: True. Disabling this
    omits the encoding field from output, which prevents hash-perfect
    reversal by downstream consumers.
    """

    detect_charset: bool = True
    """Enable chardet-based character encoding detection.

    When True, the encoding detection module passes the file sample to
    chardet for encoding identification. When False, only BOM and
    line-ending detection are performed (chardet is skipped). Requires
    the chardet dependency (standard, not optional). Default: True.
    """

    # ── Output suppression ──────────────────────────────────────────────
    write_directory_meta: bool = True

    # ── Rename ──────────────────────────────────────────────────────────
    rename: bool = False
    dry_run: bool = False

    # ── Filesystem exclusion filters ────────────────────────────────────
    filesystem_excludes: frozenset[str] = field(default_factory=frozenset)
    filesystem_exclude_globs: tuple[str, ...] = ()

    # ── Extension validation ────────────────────────────────────────────
    extension_validation_pattern: str = (
        r"^(([a-z0-9]){1,2}|([a-z0-9])([a-z0-9\-]){1,12}([a-z0-9]))$"
    )

    # ── Exiftool ────────────────────────────────────────────────────────
    exiftool_exclude_extensions: frozenset[str] = field(default_factory=frozenset)
    exiftool_exclude_keys: frozenset[str] = field(default_factory=frozenset)
    exiftool_args: tuple[str, ...] = ()

    # ── Metadata file parser ────────────────────────────────────────────
    metadata_identify: MappingProxyType[str, tuple[re.Pattern[str], ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    metadata_attributes: MappingProxyType[str, MetadataTypeAttributes] = field(
        default_factory=lambda: MappingProxyType({})
    )
    metadata_exclude_patterns: tuple[re.Pattern[str], ...] = ()

    # ── Extension groups ────────────────────────────────────────────────
    extension_groups: MappingProxyType[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )

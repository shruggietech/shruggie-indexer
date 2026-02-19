"""Configuration system for shruggie-indexer.

Provides TOML-based configuration loading with a 4-layer merge strategy:
compiled defaults -> user config -> project config -> runtime overrides.
"""

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import (
    ExiftoolConfig,
    IndexerConfig,
    MetadataTypeAttributes,
)

__all__ = [
    "ExiftoolConfig",
    "IndexerConfig",
    "MetadataTypeAttributes",
    "load_config",
]

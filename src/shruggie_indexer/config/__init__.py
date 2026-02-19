"""Configuration system for shruggie-indexer.

Provides TOML-based configuration loading with a 4-layer merge strategy:
compiled defaults -> user config -> project config -> runtime overrides.
"""

import contextlib

__all__ = [
    "IndexerConfig",
    "load_config",
]

with contextlib.suppress(ImportError):
    from shruggie_indexer.config.loader import load_config

with contextlib.suppress(ImportError):
    from shruggie_indexer.config.types import IndexerConfig

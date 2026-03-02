"""Exception hierarchy for shruggie-indexer.

All exceptions inherit from IndexerError to enable catch-all handling.
These exceptions map to CLI exit codes (section 8.10 of the spec):
    IndexerConfigError      -> exit code 2
    IndexerTargetError      -> exit code 3
    IndexerRuntimeError     -> exit code 4
    IndexerCancellationError -> exit code 5
"""

__all__ = [
    "IndexerCancellationError",
    "IndexerConfigError",
    "IndexerError",
    "IndexerRuntimeError",
    "IndexerTargetError",
    "RenameError",
    "RollbackError",
]


class IndexerError(Exception):
    """Base class for all shruggie-indexer exceptions."""


class IndexerConfigError(IndexerError):
    """Configuration is invalid or cannot be loaded."""


class IndexerTargetError(IndexerError):
    """Target path is invalid, inaccessible, or unclassifiable."""


class IndexerRuntimeError(IndexerError):
    """Unrecoverable error during indexing execution."""


class RenameError(IndexerRuntimeError):
    """File rename failed (collision, permission, etc.)."""


class IndexerCancellationError(IndexerError):
    """The indexing operation was cancelled by the caller."""


class RollbackError(IndexerRuntimeError):
    """An error occurred during a rollback operation."""

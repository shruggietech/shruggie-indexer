"""Shared formatting utilities for shruggie-indexer core modules."""

from __future__ import annotations

__all__ = ["human_readable_size"]

_SIZE_UNITS: tuple[str, ...] = ("B", "KB", "MB", "GB", "TB")


def human_readable_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string using decimal SI units.

    Uses thresholds of 1,000 (not 1,024) per spec section 5.2.3.

    Examples::

        >>> human_readable_size(0)
        '0 B'
        >>> human_readable_size(1500)
        '1.50 KB'
        >>> human_readable_size(15_280_000)
        '15.28 MB'
    """
    if size_bytes == 0:
        return "0 B"

    value = float(size_bytes)
    for unit in _SIZE_UNITS[:-1]:
        if abs(value) < 1000.0:
            if value == int(value):
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1000.0

    # TB or larger
    if value == int(value):
        return f"{int(value)} {_SIZE_UNITS[-1]}"
    return f"{value:.2f} {_SIZE_UNITS[-1]}"

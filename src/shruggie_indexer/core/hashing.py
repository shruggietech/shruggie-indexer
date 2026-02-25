"""Hashing and identity generation for shruggie-indexer.

Provides cryptographic hash digests of file contents and name strings, and
from those digests produces the deterministic unique identifiers (``id``
field) that are the foundation of the indexing system.

This is the single hashing module consumed by all callers (DEV-01).  All
active algorithms are computed in a single file read (DEV-02).  String
inputs are unconditionally NFC-normalized before hashing (DEV-15).
Null-hash constants are computed at import time (DEV-09).

See spec §6.3 for full behavioral guidance.
"""

from __future__ import annotations

import hashlib
import unicodedata
from typing import TYPE_CHECKING

from shruggie_indexer.models.schema import HashSet

if TYPE_CHECKING:
    import threading
    from pathlib import Path

__all__ = [
    "CHUNK_SIZE",
    "NULL_HASHES",
    "hash_directory_id",
    "hash_file",
    "hash_string",
    "select_id",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNK_SIZE: int = 65_536
"""Read buffer size in bytes (64 KB) for streaming file hashing."""

# Algorithm names accepted by the public API.
_SUPPORTED_ALGORITHMS: frozenset[str] = frozenset({"md5", "sha256", "sha512"})

# Default algorithm tuple when caller does not specify.
_DEFAULT_ALGORITHMS: tuple[str, ...] = ("md5", "sha256")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_hashset(digests: dict[str, str]) -> HashSet:
    """Build a ``HashSet`` from a digest mapping, uppercasing all values."""
    return HashSet(
        md5=digests["md5"].upper(),
        sha256=digests["sha256"].upper(),
        sha512=digests["sha512"].upper() if "sha512" in digests else None,
    )


# ---------------------------------------------------------------------------
# Null-hash constants (DEV-09)
# ---------------------------------------------------------------------------

NULL_HASHES: HashSet = HashSet(
    md5=hashlib.md5(b"").hexdigest().upper(),
    sha256=hashlib.sha256(b"").hexdigest().upper(),
    sha512=hashlib.sha512(b"").hexdigest().upper(),
)
"""Hash of the empty byte sequence for each algorithm.

Returned by ``hash_string()`` when the input is ``None`` or ``""``.
Computed once at module import time rather than hardcoded (DEV-09).
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def hash_file(
    path: Path,
    algorithms: tuple[str, ...] = _DEFAULT_ALGORITHMS,
    *,
    cancel_event: threading.Event | None = None,
) -> HashSet:
    """Compute content hashes of a file.

    Reads the file in :data:`CHUNK_SIZE` chunks and feeds each chunk to all
    requested hash algorithms simultaneously (DEV-02).

    Args:
        path: Absolute path to the file.
        algorithms: Hash algorithm names to compute.  Defaults to
            ``("md5", "sha256")``.
        cancel_event: Optional ``threading.Event`` checked every chunk.
            When set, raises ``IndexerCancellationError``.

    Returns:
        A :class:`~shruggie_indexer.models.schema.HashSet` with the computed
        digests in uppercase hexadecimal.

    Raises:
        IndexerCancellationError: ``cancel_event`` was set during hashing.
    """
    from shruggie_indexer.exceptions import IndexerCancellationError

    hashers = {alg: hashlib.new(alg) for alg in algorithms}

    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK_SIZE):
            if cancel_event is not None and cancel_event.is_set():
                raise IndexerCancellationError("Hashing cancelled")
            for h in hashers.values():
                h.update(chunk)

    digests = {alg: h.hexdigest() for alg, h in hashers.items()}
    return _make_hashset(digests)


def hash_string(
    value: str | None,
    algorithms: tuple[str, ...] = _DEFAULT_ALGORITHMS,
) -> HashSet:
    """Compute hashes of a NFC-normalized, UTF-8 encoded string.

    Applies ``unicodedata.normalize('NFC', value)`` before encoding to
    UTF-8 bytes (DEV-15).  For ``None`` or empty-string inputs, returns
    :data:`NULL_HASHES` without recomputing.

    Args:
        value: The string to hash.
        algorithms: Hash algorithm names to compute.

    Returns:
        A :class:`~shruggie_indexer.models.schema.HashSet`.
    """
    if not value:
        return NULL_HASHES

    normalized = unicodedata.normalize("NFC", value)
    data = normalized.encode("utf-8")

    hashers = {alg: hashlib.new(alg) for alg in algorithms}
    for h in hashers.values():
        h.update(data)

    digests = {alg: h.hexdigest() for alg, h in hashers.items()}
    return _make_hashset(digests)


def hash_directory_id(
    name: str,
    parent_name: str,
    algorithms: tuple[str, ...] = _DEFAULT_ALGORITHMS,
) -> HashSet:
    """Compute directory identity using the two-layer hashing scheme.

    Algorithm (performed independently for each active hash algorithm):

    1. ``hash(name)``        -> *name_digest*  (uppercase hex string)
    2. ``hash(parent_name)`` -> *parent_digest* (uppercase hex string)
    3. ``hash(name_digest + parent_digest)`` -> *final_digest*

    The concatenation in step 3 uses the uppercase hex representations,
    matching the original ``[BitConverter]::ToString()`` concatenation.

    Args:
        name: Leaf name of the directory.
        parent_name: Leaf name of the parent directory (may be ``""`` for
            root-level directories).
        algorithms: Hash algorithm names to compute.

    Returns:
        A :class:`~shruggie_indexer.models.schema.HashSet` containing the
        final digests.
    """
    name_hashes = hash_string(name, algorithms)
    parent_hashes = hash_string(parent_name, algorithms)

    # Build combined strings per algorithm and hash them.
    digests: dict[str, str] = {}
    for alg in algorithms:
        name_digest = getattr(name_hashes, alg)
        parent_digest = getattr(parent_hashes, alg)
        if name_digest is None or parent_digest is None:
            continue
        combined = name_digest + parent_digest
        digests[alg] = hashlib.new(
            alg, combined.encode("utf-8")
        ).hexdigest()

    return _make_hashset(digests)


def select_id(
    hashes: HashSet,
    algorithm: str,
    prefix: str,
) -> str:
    """Select and prefix an identity value from a HashSet.

    Args:
        hashes: The :class:`~shruggie_indexer.models.schema.HashSet` to
            select from.
        algorithm: Which digest to use (``"md5"`` or ``"sha256"``).
        prefix: Identity prefix — ``"x"`` (directory), ``"y"`` (file),
            or ``"z"`` (generated metadata).

    Returns:
        The prefixed identity string, e.g. ``"yA8A8C089…"``.
    """
    digest = getattr(hashes, algorithm)
    if digest is None:
        msg = f"HashSet does not contain algorithm {algorithm!r}"
        raise ValueError(msg)
    return f"{prefix}{digest}"

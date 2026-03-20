"""File encoding detection for shruggie-indexer.

Detects byte-order marks (BOM), line-ending conventions, and character
encoding of file content. These signals enable downstream consumers to
perform hash-perfect reversal from decoded text back to original file bytes.

Detection has two layers:
- Manual detection: BOM prefix matching and line-ending scanning.
  Deterministic and infallible for the signals it covers.
- Chardet detection: Statistical character encoding inference via the
  chardet library. Probabilistic, with confidence scores.

See spec §6.12 for full behavioral guidance.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from shruggie_indexer.models.schema import EncodingObject

logger = logging.getLogger(__name__)

# BOM byte sequences, ordered longest-first to avoid prefix ambiguity.
# UTF-32 LE starts with FF FE 00 00, which has the same first two bytes
# as UTF-16 LE (FF FE). Checking the longer sequence first prevents
# misidentification.
_BOM_TABLE: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xef\xbb\xbf", "utf-8"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)

# Reverse lookup: BOM identifier -> byte sequence. Used by the rollback
# engine to prepend the correct BOM during file restoration.
BOM_BYTES: dict[str, bytes] = {name: bom for bom, name in _BOM_TABLE}


def detect_bom(data: bytes) -> str | None:
    """Detect a byte-order mark in the leading bytes of file content.

    Args:
        data: The first 4+ bytes of the file content.

    Returns:
        A BOM identifier string ("utf-8", "utf-16-le", etc.) or None.
    """
    for bom_bytes, bom_name in _BOM_TABLE:
        if data.startswith(bom_bytes):
            return bom_name
    return None


def detect_line_endings(data: bytes) -> str | None:
    """Detect the line-ending convention used in file content.

    Scans the provided bytes for CR+LF (\\r\\n) and bare LF (\\n)
    sequences. Returns "crlf", "lf", "mixed", or None.

    The scan strips any detected BOM prefix before analysis to avoid
    false positives from BOM bytes that happen to contain 0x0A or 0x0D.

    Args:
        data: Raw file content bytes (or a representative prefix).

    Returns:
        "lf" if only bare LF found, "crlf" if only CR+LF found,
        "mixed" if both styles present, or None if no line endings
        detected (single-line file or binary).
    """
    # Strip BOM prefix if present.
    for bom_bytes, _ in _BOM_TABLE:
        if data.startswith(bom_bytes):
            data = data[len(bom_bytes):]
            break

    has_crlf = b"\r\n" in data
    # Count bare LF: occurrences of \n that are NOT preceded by \r.
    # Replace all \r\n first, then check for remaining \n.
    bare_lf_data = data.replace(b"\r\n", b"")
    has_bare_lf = b"\n" in bare_lf_data

    if has_crlf and has_bare_lf:
        return "mixed"
    if has_crlf:
        return "crlf"
    if has_bare_lf:
        return "lf"
    return None


def detect_charset(data: bytes) -> tuple[str | None, float | None]:
    """Detect character encoding using chardet.

    Returns (encoding_name, confidence) or (None, None) if chardet
    is not installed or detection is inconclusive.

    The chardet library uses a 12-stage detection pipeline (BOM
    detection, structural probing, byte validity filtering, bigram
    statistical models) to identify the character encoding of
    arbitrary byte sequences. It covers 99 encodings and achieves
    98.2% accuracy on standard test corpora.

    Args:
        data: Raw file content bytes (or a representative prefix;
              chardet works well with 10 KB+ of data).

    Returns:
        Tuple of (encoding_name, confidence) where encoding_name is
        a Python codec name and confidence is 0.0-1.0, or (None, None).
    """
    try:
        import chardet
    except ImportError:
        logger.warning(
            "chardet is not installed; character encoding detection "
            "is unavailable. Install chardet to enable this feature."
        )
        return None, None

    try:
        result = chardet.detect(data)
    except Exception:  # noqa: BLE001
        logger.debug("chardet detection failed", exc_info=True)
        return None, None

    encoding = result.get("encoding")
    confidence = result.get("confidence")

    if encoding is None:
        return None, None

    # Normalize encoding name to Python codec name (lowercase).
    return encoding.lower(), confidence


def detect_file_encoding(
    path: Path,
    *,
    detect_charset_enabled: bool = True,
    charset_sample_size: int = 65_536,
) -> EncodingObject | None:
    """Detect encoding metadata for a file.

    Reads the file in binary mode. Performs BOM detection and
    line-ending detection unconditionally. Performs charset detection
    via chardet unless disabled.

    Args:
        path: Path to the file.
        detect_charset_enabled: Whether to run chardet detection.
            Default: True.
        charset_sample_size: Maximum bytes to read for detection
            (default: 64 KB). BOM and line-ending detection use
            the same read buffer.

    Returns:
        An EncodingObject with populated fields, or None on read failure
        or when no signals are detected.
    """
    try:
        with open(path, "rb") as f:
            sample = f.read(charset_sample_size)
    except OSError as exc:
        logger.debug("Cannot read file for encoding detection: %s: %s", path, exc)
        return None

    if not sample:
        return None

    return _detect_from_bytes(sample, detect_charset_enabled=detect_charset_enabled)


def detect_bytes_encoding(
    data: bytes,
    *,
    detect_charset_enabled: bool = True,
) -> EncodingObject | None:
    """Detect encoding metadata from an in-memory byte buffer.

    Same logic as detect_file_encoding but operates on bytes already
    in memory (avoids redundant file reads for sidecars whose content
    has already been read).

    Args:
        data: Raw file content bytes.
        detect_charset_enabled: Whether to run chardet detection.
            Default: True.

    Returns:
        An EncodingObject with populated fields, or None if nothing detected.
    """
    if not data:
        return None

    return _detect_from_bytes(data, detect_charset_enabled=detect_charset_enabled)


def _detect_from_bytes(
    data: bytes,
    *,
    detect_charset_enabled: bool = True,
) -> EncodingObject | None:
    """Core detection logic shared by file and bytes entry points."""
    bom = detect_bom(data)
    line_endings = detect_line_endings(data)

    detected_encoding: str | None = None
    confidence: float | None = None
    if detect_charset_enabled:
        detected_encoding, confidence = detect_charset(data)

    # Return None if nothing was detected (binary file, no BOM,
    # no line endings, chardet returned nothing).
    if bom is None and line_endings is None and detected_encoding is None:
        return None

    return EncodingObject(
        bom=bom,
        line_endings=line_endings,
        detected_encoding=detected_encoding,
        confidence=confidence,
    )

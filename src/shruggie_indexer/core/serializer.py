"""JSON serialization and output routing for shruggie-indexer.

Converts ``IndexEntry`` model instances to JSON text and routes the result to
one or more output destinations.  This is Stage 5 of the processing pipeline
(spec section 4.1).

The serializer is a pure presentation layer — it does not modify the
``IndexEntry`` data, only formats and delivers it.

Three independent output destinations are supported:
  - ``--stdout``  → ``sys.stdout``
  - ``--outfile`` → specified file path
  - ``--inplace`` → per-item sidecar files alongside each processed item

See spec section 6.9 for full behavioral guidance.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING, Any

from shruggie_indexer.core.paths import build_sidecar_path

if TYPE_CHECKING:
    from pathlib import Path

    from shruggie_indexer.config.types import IndexerConfig
    from shruggie_indexer.models.schema import IndexEntry

__all__ = [
    "serialize_entry",
    "write_inplace",
    "write_output",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# orjson / json fallback
# ---------------------------------------------------------------------------

try:
    import orjson

    _HAS_ORJSON = True
except ImportError:
    orjson = None  # type: ignore[assignment]
    _HAS_ORJSON = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Canonical key order matching IndexEntry.to_dict() output.
_TOP_LEVEL_KEY_ORDER: tuple[str, ...] = (
    "schema_version",
    "id",
    "id_algorithm",
    "type",
    "name",
    "extension",
    "mime_type",
    "size",
    "hashes",
    "file_system",
    "timestamps",
    "attributes",
    "items",
    "metadata",
)


def _clean_none_sha512(obj: Any) -> Any:
    """Recursively remove ``sha512`` keys whose value is ``None``.

    The v2 schema specifies that ``sha512`` is omitted (not emitted as
    ``null``) when not computed.  ``HashSet.to_dict()`` already handles this,
    but this function acts as a safety net for any dict produced outside
    ``to_dict()`` (e.g. via ``dataclasses.asdict()``).
    """
    if isinstance(obj, dict):
        return {
            k: _clean_none_sha512(v)
            for k, v in obj.items()
            if not (k == "sha512" and v is None)
        }
    if isinstance(obj, list):
        return [_clean_none_sha512(item) for item in obj]
    return obj


def _order_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Re-order a top-level entry dict so ``schema_version`` comes first.

    Keys present in :data:`_TOP_LEVEL_KEY_ORDER` are placed first in order;
    any remaining keys follow in their original order.
    """
    ordered: dict[str, Any] = {}
    for key in _TOP_LEVEL_KEY_ORDER:
        if key in d:
            ordered[key] = d[key]
    for key in d:
        if key not in ordered:
            ordered[key] = d[key]
    return ordered


def _prepare_dict(entry: IndexEntry) -> dict[str, Any]:
    """Convert an ``IndexEntry`` to a JSON-ready, cleaned, and ordered dict."""
    raw = entry.to_dict()
    cleaned = _clean_none_sha512(raw)
    return _order_dict(cleaned)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def serialize_entry(
    entry: IndexEntry,
    *,
    compact: bool = False,
) -> str:
    """Serialize an ``IndexEntry`` to a JSON string.

    When ``compact=False``, output is pretty-printed with 2-space indent.
    When ``compact=True``, output is a single line.

    Uses ``orjson`` when available for faster serialization; falls back to
    the standard library ``json`` module otherwise.

    Args:
        entry: The entry to serialize.
        compact: Whether to produce compact single-line output.

    Returns:
        UTF-8 JSON string.
    """
    prepared = _prepare_dict(entry)

    if _HAS_ORJSON and orjson is not None:
        opts = orjson.OPT_NON_STR_KEYS
        if not compact:
            opts |= orjson.OPT_INDENT_2
        return orjson.dumps(prepared, option=opts).decode("utf-8")

    if compact:
        return json.dumps(prepared, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(prepared, ensure_ascii=False, indent=2)


def write_output(
    entry: IndexEntry,
    config: IndexerConfig,
) -> None:
    """Route serialized output to configured destinations.

    Examines ``config.output_stdout``, ``config.output_file``, and
    ``config.output_inplace`` to determine where output goes.  Multiple
    destinations may be active simultaneously.

    Args:
        entry: The completed entry tree.
        config: Resolved configuration with output routing flags.
    """
    json_str = serialize_entry(entry)

    if config.output_stdout:
        sys.stdout.write(json_str)
        sys.stdout.write("\n")
        sys.stdout.flush()

    if config.output_file is not None:
        config.output_file.write_text(json_str + "\n", encoding="utf-8")
        logger.info("Output written to %s", config.output_file)


def write_inplace(
    entry: IndexEntry,
    item_path: Path,
    item_type: str,
) -> None:
    """Write a single in-place sidecar file alongside an item.

    Called during traversal for each item when inplace mode is active.
    The sidecar path is constructed via ``paths.build_sidecar_path()``.

    Args:
        entry: The completed entry for this item.
        item_path: Absolute path to the indexed item.
        item_type: ``"file"`` or ``"directory"``.
    """
    sidecar_path = build_sidecar_path(item_path, item_type)
    json_str = serialize_entry(entry)
    sidecar_path.write_text(json_str + "\n", encoding="utf-8")
    logger.debug("Inplace sidecar written to %s", sidecar_path)

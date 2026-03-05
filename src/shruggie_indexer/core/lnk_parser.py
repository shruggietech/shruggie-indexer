"""Windows ``.lnk`` shortcut parser for shruggie-indexer.

Extracts structured metadata from ``.lnk`` (MS-SHLLINK) binary shortcut
files.  Uses ``LnkParse3`` when available; returns ``None`` gracefully
when the library is missing or parsing fails.

The extracted metadata is stored in ``MetadataAttributes.link_metadata``
alongside a base64-encoded copy of the raw binary in ``MetadataEntry.data``
(dual-storage approach).

See spec §6.7 and §7.5 for sidecar type definitions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

__all__ = [
    "parse_lnk",
]

logger = logging.getLogger(__name__)

try:
    import LnkParse3  # type: ignore[import-untyped]

    _HAS_LNK_PARSER = True
except ImportError:
    _HAS_LNK_PARSER = False
    logger.debug(
        "LnkParse3 not installed — .lnk metadata extraction unavailable. "
        "Install with: pip install LnkParse3"
    )


def parse_lnk(path: Path) -> dict[str, str] | None:
    """Extract structured metadata from a ``.lnk`` binary shortcut.

    Returns a dict containing non-empty fields from the shortcut:

    - ``target_path`` — the file, folder, or resource the shortcut points to.
    - ``working_directory`` — the working directory for the target.
    - ``arguments`` — command-line arguments passed to the target.
    - ``icon_location`` — path to the icon resource.
    - ``description`` — the shortcut's comment/description string.
    - ``hotkey`` — keyboard shortcut assigned to the link.

    Fields that are absent or empty in the ``.lnk`` file are omitted.

    Returns ``None`` if parsing fails or ``LnkParse3`` is unavailable.

    Args:
        path: Absolute path to the ``.lnk`` file.

    Raises:
        Exception: Re-raised only when an unexpected error occurs during
            parsing (callers should catch broadly and fall back).
    """
    if not _HAS_LNK_PARSER:
        return None

    with open(path, "rb") as f:
        lnk = LnkParse3.lnk_file(f)

    metadata: dict[str, str] = {}

    # Extract fields from the parsed .lnk object.
    # LnkParse3 exposes data through get_json() or individual accessors.
    json_data = lnk.get_json()

    # Target path — may be in several locations within the parsed data.
    target = _extract_target_path(lnk, json_data)
    if target:
        metadata["target_path"] = target

    # Working directory
    working_dir = _safe_str(json_data.get("data", {}).get("working_directory"))
    if working_dir:
        metadata["working_directory"] = working_dir

    # Arguments
    arguments = _safe_str(json_data.get("data", {}).get("command_line_arguments"))
    if arguments:
        metadata["arguments"] = arguments

    # Icon location
    icon_loc = _safe_str(json_data.get("data", {}).get("icon_location"))
    if icon_loc:
        metadata["icon_location"] = icon_loc

    # Description
    description = _safe_str(json_data.get("data", {}).get("description"))
    if description:
        metadata["description"] = description

    # Hotkey
    hotkey = _extract_hotkey(json_data)
    if hotkey:
        metadata["hotkey"] = hotkey

    return metadata if metadata else None


def _extract_target_path(lnk: object, json_data: dict) -> str | None:
    """Extract the target path from a parsed .lnk file.

    Tries multiple sources in priority order:
    1. ``link_info.local_base_path`` — most reliable for local files.
    2. ``link_info.local_base_path_unicode`` — Unicode variant.
    3. ``link_info.common_path_suffix`` — network paths.
    4. ``relative_path`` from string data.
    """
    data = json_data.get("data", {})
    link_info = json_data.get("link_info", {})

    # Local base path
    local_path = _safe_str(link_info.get("local_base_path"))
    if local_path:
        return local_path

    local_path_unicode = _safe_str(link_info.get("local_base_path_unicode"))
    if local_path_unicode:
        return local_path_unicode

    # Network path
    common_suffix = _safe_str(link_info.get("common_path_suffix"))
    net_name = _safe_str(
        link_info.get("common_network_relative_link", {}).get("net_name")
    )
    if net_name and common_suffix:
        return f"{net_name}\\{common_suffix}"
    if net_name:
        return net_name

    # Relative path from string data
    relative_path = _safe_str(data.get("relative_path"))
    if relative_path:
        return relative_path

    return None


def _extract_hotkey(json_data: dict) -> str | None:
    """Extract the hotkey string from parsed .lnk data."""
    header = json_data.get("header", {})
    hotkey_raw = header.get("hotkey")
    if not hotkey_raw:
        return None
    s = _safe_str(hotkey_raw)
    # LnkParse3 may return "0" or empty for no hotkey
    if s and s != "0":
        return s
    return None


def _safe_str(value: object) -> str | None:
    """Convert a value to a non-empty string, or return ``None``."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None

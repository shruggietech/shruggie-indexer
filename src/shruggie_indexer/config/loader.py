"""Configuration loader for shruggie-indexer.

Implements the 4-layer configuration resolution pipeline:

    1. Compiled defaults  (``config/defaults.py``)
    2. User config file   (platform-standard location)
    3. Project-local file (``.shruggie-indexer.toml`` in target dir ancestors)
    4. CLI/API overrides

See spec §7.1, §7.6, §7.7, and §9.3 for full behavioral guidance.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

from shruggie_indexer.config.defaults import (
    DEFAULT_EXIFTOOL_ARGS,
    DEFAULT_EXIFTOOL_EXCLUDE_EXTENSIONS,
    DEFAULT_EXIFTOOL_EXCLUDE_KEYS,
    DEFAULT_EXTENSION_GROUPS,
    DEFAULT_EXTENSION_VALIDATION_PATTERN,
    DEFAULT_FILESYSTEM_EXCLUDE_GLOBS,
    DEFAULT_FILESYSTEM_EXCLUDES,
    DEFAULT_METADATA_ATTRIBUTES,
    DEFAULT_METADATA_EXCLUDE_PATTERN_STRINGS,
    DEFAULT_METADATA_IDENTIFY_STRINGS,
    DEFAULT_SCALARS,
)
from shruggie_indexer.config.types import (
    IndexerConfig,
    MetadataTypeAttributes,
)
from shruggie_indexer.exceptions import IndexerConfigError

__all__ = ["load_config"]

logger = logging.getLogger(__name__)

# Config file names
_USER_CONFIG_FILENAME = "config.toml"
_LEGACY_DIR_NAME = "shruggie-indexer"  # v0.1.0 path (without ecosystem parent)
_PROJECT_CONFIG_FILENAME = ".shruggie-indexer.toml"


# ---------------------------------------------------------------------------
# Platform-aware config file discovery (§3.3)
# ---------------------------------------------------------------------------


def _legacy_roaming_base() -> Path | None:
    """Return the v0.1.1 Roaming base directory on Windows, or None."""
    if sys.platform != "win32":
        return None
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))


def _find_user_config() -> Path | None:
    """Resolve the platform-standard user configuration file path.

    Three-tier fallback chain:

    1. Canonical path via :func:`~shruggie_indexer.app_paths.get_app_data_dir`
       (``%LOCALAPPDATA%`` on Windows).
    2. v0.1.1 Roaming path (``%APPDATA%\\shruggie-tech\\shruggie-indexer\\``,
       Windows only).
    3. v0.1.0 flat path (``%APPDATA%\\shruggie-indexer\\`` or
       ``~/.config/shruggie-indexer/``).

    Returns ``None`` if no config file is found at any location.
    """
    from shruggie_indexer.app_paths import get_app_data_dir

    canonical_dir = get_app_data_dir()

    # Tier 1: Canonical path
    canonical_path = canonical_dir / _USER_CONFIG_FILENAME
    if canonical_path.is_file():
        return canonical_path

    # Tier 2: v0.1.1 Roaming (Windows only)
    roaming_base = _legacy_roaming_base()
    if roaming_base is not None:
        roaming_path = (
            roaming_base / "shruggie-tech" / "shruggie-indexer"
            / _USER_CONFIG_FILENAME
        )
        if roaming_path.is_file():
            logger.info(
                "Configuration file found at legacy Roaming path %s — "
                "consider moving it to %s",
                roaming_path,
                canonical_path,
            )
            return roaming_path

    # Tier 3: v0.1.0 flat path
    if roaming_base is not None:
        legacy_flat = roaming_base / _LEGACY_DIR_NAME / _USER_CONFIG_FILENAME
    else:
        # Linux / macOS: same config base minus ecosystem dir
        legacy_flat = (
            canonical_dir.parent.parent / _LEGACY_DIR_NAME / _USER_CONFIG_FILENAME
        )
    if legacy_flat.is_file():
        logger.info(
            "Configuration file found at legacy v0.1.0 path %s — "
            "consider moving it to %s",
            legacy_flat,
            canonical_path,
        )
        return legacy_flat

    return None


def _find_project_config(target_directory: Path) -> Path | None:
    """Search *target_directory* and its ancestors for a project config.

    Returns ``None`` if no project config is found.
    """
    current = target_directory.resolve()
    while True:
        candidate = current / _PROJECT_CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


# ---------------------------------------------------------------------------
# TOML parsing helpers
# ---------------------------------------------------------------------------


def _read_toml(path: Path) -> dict[str, Any]:
    """Read and parse a TOML file, raising ``IndexerConfigError`` on failure."""
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise IndexerConfigError(f"Configuration file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise IndexerConfigError(f"Invalid TOML in {path}: {exc}") from exc
    except OSError as exc:
        raise IndexerConfigError(f"Cannot read configuration file {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Defaults → dict
# ---------------------------------------------------------------------------


def _get_defaults_dict() -> dict[str, Any]:
    """Build the base configuration dict from compiled defaults."""
    d: dict[str, Any] = dict(DEFAULT_SCALARS)
    d["extension_validation_pattern"] = DEFAULT_EXTENSION_VALIDATION_PATTERN
    d["filesystem_excludes"] = set(DEFAULT_FILESYSTEM_EXCLUDES)
    d["filesystem_exclude_globs"] = list(DEFAULT_FILESYSTEM_EXCLUDE_GLOBS)
    d["exiftool_exclude_extensions"] = set(DEFAULT_EXIFTOOL_EXCLUDE_EXTENSIONS)
    d["exiftool_exclude_keys"] = set(DEFAULT_EXIFTOOL_EXCLUDE_KEYS)
    d["exiftool_args"] = list(DEFAULT_EXIFTOOL_ARGS)
    d["metadata_identify"] = {
        k: list(v) for k, v in DEFAULT_METADATA_IDENTIFY_STRINGS.items()
    }
    d["metadata_attributes"] = dict(DEFAULT_METADATA_ATTRIBUTES)
    d["metadata_exclude_patterns"] = list(DEFAULT_METADATA_EXCLUDE_PATTERN_STRINGS)
    d["extension_groups"] = {k: list(v) for k, v in DEFAULT_EXTENSION_GROUPS.items()}
    return d


# ---------------------------------------------------------------------------
# TOML merge logic (§7.7)
# ---------------------------------------------------------------------------

# Fields that are collections and support the ``_append`` merge variant.
_COLLECTION_FIELDS: dict[str, str] = {
    # toml section.key -> config_dict key
    "filesystem_excludes.names": "filesystem_excludes",
    "filesystem_excludes.globs": "filesystem_exclude_globs",
    "exiftool.exclude_extensions": "exiftool_exclude_extensions",
    "exiftool.base_args": "exiftool_args",
    "metadata_exclude.patterns": "metadata_exclude_patterns",
}


def _merge_toml(config_dict: dict[str, Any], toml_data: dict[str, Any]) -> None:
    """Merge parsed TOML data into *config_dict* using replace/append semantics."""
    if not toml_data:
        return

    # Scalar top-level keys
    for key in (
        "recursive", "id_algorithm", "compute_sha512",
        "output_stdout", "output_file", "output_inplace",
        "extract_exif", "meta_merge", "meta_merge_delete",
        "rename", "dry_run", "extension_validation_pattern",
    ):
        if key in toml_data:
            config_dict[key] = toml_data[key]

    # output_file: convert string to Path
    if toml_data.get("output_file"):
        config_dict["output_file"] = Path(toml_data["output_file"])

    # Filesystem excludes section
    fs_section = toml_data.get("filesystem_excludes", {})
    if isinstance(fs_section, dict):
        if "names" in fs_section:
            config_dict["filesystem_excludes"] = set(fs_section["names"])
        if "names_append" in fs_section:
            config_dict["filesystem_excludes"].update(fs_section["names_append"])
        if "globs" in fs_section:
            config_dict["filesystem_exclude_globs"] = list(fs_section["globs"])
        if "globs_append" in fs_section:
            config_dict["filesystem_exclude_globs"].extend(fs_section["globs_append"])

    # Exiftool section
    exif_section = toml_data.get("exiftool", {})
    if isinstance(exif_section, dict):
        if "exclude_extensions" in exif_section:
            config_dict["exiftool_exclude_extensions"] = set(
                exif_section["exclude_extensions"]
            )
        if "exclude_extensions_append" in exif_section:
            config_dict["exiftool_exclude_extensions"].update(
                exif_section["exclude_extensions_append"]
            )
        if "base_args" in exif_section:
            config_dict["exiftool_args"] = list(exif_section["base_args"])
        if "base_args_append" in exif_section:
            config_dict["exiftool_args"].extend(exif_section["base_args_append"])
        if "exclude_keys" in exif_section:
            config_dict["exiftool_exclude_keys"] = set(
                exif_section["exclude_keys"]
            )
        if "exclude_keys_append" in exif_section:
            config_dict["exiftool_exclude_keys"].update(
                exif_section["exclude_keys_append"]
            )

    # Metadata identification patterns section
    identify_section = toml_data.get("metadata_identify", {})
    if isinstance(identify_section, dict):
        for type_name, patterns in identify_section.items():
            if type_name.endswith("_append"):
                base_name = type_name.removesuffix("_append")
                if base_name in config_dict["metadata_identify"]:
                    config_dict["metadata_identify"][base_name].extend(patterns)
                else:
                    config_dict["metadata_identify"][base_name] = list(patterns)
            else:
                config_dict["metadata_identify"][type_name] = list(patterns)

    # Metadata exclude patterns section
    meta_exclude_section = toml_data.get("metadata_exclude", {})
    if isinstance(meta_exclude_section, dict):
        if "patterns" in meta_exclude_section:
            config_dict["metadata_exclude_patterns"] = list(
                meta_exclude_section["patterns"]
            )
        if "patterns_append" in meta_exclude_section:
            config_dict["metadata_exclude_patterns"].extend(
                meta_exclude_section["patterns_append"]
            )

    # Extension groups section
    groups_section = toml_data.get("extension_groups", {})
    if isinstance(groups_section, dict):
        for group_name, extensions in groups_section.items():
            if group_name.endswith("_append"):
                base_name = group_name.removesuffix("_append")
                if base_name in config_dict["extension_groups"]:
                    config_dict["extension_groups"][base_name].extend(extensions)
                else:
                    config_dict["extension_groups"][base_name] = list(extensions)
            else:
                config_dict["extension_groups"][group_name] = list(extensions)

    # Warn about unknown top-level keys
    known_top = {
        "recursive", "id_algorithm", "compute_sha512",
        "output_stdout", "output_file", "output_inplace",
        "extract_exif", "meta_merge", "meta_merge_delete",
        "rename", "dry_run", "extension_validation_pattern",
        "filesystem_excludes", "exiftool", "metadata_identify",
        "metadata_exclude", "extension_groups",
        "logging",  # Handled by CLI/GUI, not by IndexerConfig
    }
    for key in toml_data:
        if key not in known_top:
            logger.warning("Unknown configuration key ignored: %s", key)


def _merge_overrides(config_dict: dict[str, Any], overrides: dict[str, Any]) -> None:
    """Apply CLI/API overrides as the highest-priority layer.

    Overrides use flat ``IndexerConfig`` field names.  Dotted keys are mapped
    to nested structures where appropriate.
    """
    if not overrides:
        return

    # Direct scalar mappings
    scalar_keys = {
        "recursive", "id_algorithm", "compute_sha512",
        "output_stdout", "output_file", "output_inplace",
        "extract_exif", "meta_merge", "meta_merge_delete",
        "rename", "dry_run", "extension_validation_pattern",
    }
    for key in scalar_keys:
        if key in overrides:
            config_dict[key] = overrides[key]

    # Dotted key mappings for nested structures
    dotted_map = {
        "exiftool.exclude_extensions": "exiftool_exclude_extensions",
        "exiftool.exclude_keys": "exiftool_exclude_keys",
        "exiftool.base_args": "exiftool_args",
        "filesystem_excludes": "filesystem_excludes",
        "filesystem_exclude_globs": "filesystem_exclude_globs",
    }
    for dotted_key, dict_key in dotted_map.items():
        if dotted_key in overrides:
            val = overrides[dotted_key]
            if isinstance(val, (set, frozenset)):
                config_dict[dict_key] = set(val)
            elif isinstance(val, (list, tuple)):
                config_dict[dict_key] = list(val)
            else:
                config_dict[dict_key] = val


# ---------------------------------------------------------------------------
# Implication propagation (§7.1)
# ---------------------------------------------------------------------------


def _apply_implications(config_dict: dict[str, Any]) -> None:
    """Propagate parameter implications in reverse dependency order."""
    # meta_merge_delete → meta_merge
    if config_dict.get("meta_merge_delete"):
        config_dict["meta_merge"] = True

    # meta_merge → extract_exif
    if config_dict.get("meta_merge"):
        config_dict["extract_exif"] = True

    # rename → output_inplace
    if config_dict.get("rename"):
        config_dict["output_inplace"] = True

    # Output mode defaulting (§7.1):
    # If neither output_file nor output_inplace is set, default output_stdout
    # to True.  If either is set and output_stdout wasn't explicitly provided,
    # default it to False.
    # Note: since we're working from defaults that already have output_stdout=True,
    # we only need to handle the case where file/inplace output is active.
    if config_dict.get("output_file") or config_dict.get("output_inplace"):
        # output_stdout stays as whatever was explicitly set; the compiled
        # default is True, but if the user didn't explicitly pass it we should
        # default to False.  At this layer we have no way to distinguish
        # "user explicitly set True" from "default True", so we leave it alone
        # and let CLI handle the explicit flag detection.
        pass


# ---------------------------------------------------------------------------
# Validation (§7.1)
# ---------------------------------------------------------------------------


def _validate(config_dict: dict[str, Any]) -> None:
    """Validate the fully-resolved configuration.

    Raises ``IndexerConfigError`` on any invariant violation.
    """
    # 1. MetaMergeDelete safety
    if config_dict.get("meta_merge_delete"):
        has_output = bool(config_dict.get("output_file")) or config_dict.get(
            "output_inplace", False
        )
        if not has_output:
            raise IndexerConfigError(
                "meta_merge_delete requires at least one of output_file or "
                "output_inplace to be set. Without a persistent output "
                "destination, sidecar file content would be lost."
            )

    # 2. id_algorithm validity
    if config_dict.get("id_algorithm") not in ("md5", "sha256"):
        raise IndexerConfigError(
            f"id_algorithm must be 'md5' or 'sha256', "
            f"got {config_dict.get('id_algorithm')!r}"
        )

    # 3. Regex compilation validation
    for type_name, patterns in config_dict.get("metadata_identify", {}).items():
        for i, pattern in enumerate(patterns):
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                raise IndexerConfigError(
                    f"Invalid regex in metadata_identify.{type_name}[{i}]: "
                    f"{pattern!r} — {exc}"
                ) from exc

    for i, pattern in enumerate(config_dict.get("metadata_exclude_patterns", [])):
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise IndexerConfigError(
                f"Invalid regex in metadata_exclude_patterns[{i}]: "
                f"{pattern!r} — {exc}"
            ) from exc

    # Validate extension_validation_pattern compiles
    evp = config_dict.get("extension_validation_pattern", "")
    if evp:
        try:
            re.compile(evp)
        except re.error as exc:
            raise IndexerConfigError(
                f"Invalid extension_validation_pattern: {evp!r} — {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Build final frozen IndexerConfig
# ---------------------------------------------------------------------------


def _build_config(config_dict: dict[str, Any]) -> IndexerConfig:
    """Compile patterns, freeze collections, and construct ``IndexerConfig``."""
    from types import MappingProxyType

    # Compile metadata_identify patterns
    compiled_identify: dict[str, tuple[re.Pattern[str], ...]] = {}
    for type_name, patterns in config_dict.get("metadata_identify", {}).items():
        compiled_identify[type_name] = tuple(
            re.compile(p, re.IGNORECASE) for p in patterns
        )

    # Compile metadata_exclude_patterns
    compiled_exclude = tuple(
        re.compile(p, re.IGNORECASE)
        for p in config_dict.get("metadata_exclude_patterns", [])
    )

    # Freeze extension groups
    frozen_groups: dict[str, tuple[str, ...]] = {
        k: tuple(sorted(set(v)))
        for k, v in config_dict.get("extension_groups", {}).items()
    }

    # Freeze metadata_attributes
    frozen_attrs: dict[str, MetadataTypeAttributes] = dict(
        config_dict.get("metadata_attributes", {})
    )

    # Handle output_file
    output_file = config_dict.get("output_file")
    if isinstance(output_file, str) and output_file:
        output_file = Path(output_file)
    elif not output_file:
        output_file = None

    return IndexerConfig(
        recursive=config_dict.get("recursive", True),
        id_algorithm=config_dict.get("id_algorithm", "md5"),
        compute_sha512=config_dict.get("compute_sha512", False),
        output_stdout=config_dict.get("output_stdout", True),
        output_file=output_file,
        output_inplace=config_dict.get("output_inplace", False),
        extract_exif=config_dict.get("extract_exif", False),
        meta_merge=config_dict.get("meta_merge", False),
        meta_merge_delete=config_dict.get("meta_merge_delete", False),
        rename=config_dict.get("rename", False),
        dry_run=config_dict.get("dry_run", False),
        filesystem_excludes=frozenset(config_dict.get("filesystem_excludes", set())),
        filesystem_exclude_globs=tuple(
            config_dict.get("filesystem_exclude_globs", [])
        ),
        extension_validation_pattern=config_dict.get(
            "extension_validation_pattern", DEFAULT_EXTENSION_VALIDATION_PATTERN
        ),
        exiftool_exclude_extensions=frozenset(
            config_dict.get("exiftool_exclude_extensions", set())
        ),
        exiftool_exclude_keys=frozenset(
            config_dict.get("exiftool_exclude_keys", set())
        ),
        exiftool_args=tuple(config_dict.get("exiftool_args", [])),
        metadata_identify=MappingProxyType(compiled_identify),
        metadata_attributes=MappingProxyType(frozen_attrs),
        metadata_exclude_patterns=compiled_exclude,
        extension_groups=MappingProxyType(frozen_groups),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(
    *,
    config_file: Path | str | None = None,
    target_directory: Path | str | None = None,
    overrides: dict[str, Any] | None = None,
) -> IndexerConfig:
    """Construct a fully resolved, immutable ``IndexerConfig``.

    Resolution layers (lowest to highest priority):

    1. Compiled defaults (§7.2).
    2. User config file at the platform-standard location (§3.3),
       unless *config_file* is specified.
    3. Project-local config file in *target_directory* or its ancestors,
       if *target_directory* is provided.
    4. Explicit overrides from the *overrides* dict.

    After merging, the function applies parameter implications (§7.1),
    validates the result, compiles regex patterns, and returns an immutable
    ``IndexerConfig``.

    Args:
        config_file: Explicit path to a TOML configuration file.  When
            provided, this replaces the user config file resolution (layer 2).
        target_directory: The directory being indexed.  Used to search for a
            project-local config file.
        overrides: Dict of field-name-to-value overrides applied as the
            highest-priority layer.

    Returns:
        A frozen ``IndexerConfig`` instance.

    Raises:
        IndexerConfigError: The config file does not exist, contains invalid
            TOML, contains values of the wrong type, or the resolved
            configuration fails validation.
    """
    # Layer 1: Compiled defaults
    config_dict = _get_defaults_dict()

    # Layer 2: User config file
    if config_file is not None:
        config_file = Path(config_file)
        if config_file.is_file():
            _merge_toml(config_dict, _read_toml(config_file))
        else:
            raise IndexerConfigError(
                f"Specified configuration file does not exist: {config_file}"
            )
    else:
        user_config = _find_user_config()
        if user_config is not None:
            logger.debug("Loading user config: %s", user_config)
            _merge_toml(config_dict, _read_toml(user_config))

    # Layer 3: Project-local config file
    if target_directory is not None:
        target_directory = Path(target_directory)
        project_config = _find_project_config(target_directory)
        if project_config is not None:
            logger.debug("Loading project config: %s", project_config)
            _merge_toml(config_dict, _read_toml(project_config))

    # Layer 4: CLI/API overrides
    if overrides:
        _merge_overrides(config_dict, overrides)

    # Apply parameter implications (§7.1)
    _apply_implications(config_dict)

    # Validate (§7.1)
    _validate(config_dict)

    # Build, compile, freeze, and return
    return _build_config(config_dict)

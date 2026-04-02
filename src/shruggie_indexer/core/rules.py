"""Standalone sidecar relationship rule engine for v4 classification."""

from __future__ import annotations

import fnmatch
import logging
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from shruggie_indexer.app_paths import get_pack_dir
from shruggie_indexer.exceptions import IndexerConfigError
from shruggie_indexer.models.schema import IndexEntry, PredicateResult, RelationshipAnnotation

if TYPE_CHECKING:
    from shruggie_indexer.config.types import IndexerConfig, SidecarRuleConfig

__all__ = [
    "BUILTIN_RULES",
    "SidecarRule",
    "classify_relationships",
    "evaluate_predicates",
    "load_rules",
    "match_rule",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SidecarRule:
    """A single sidecar classification rule."""

    name: str
    match: str
    type: str
    scope: str = "file"
    requires_sibling: str | None = None
    requires_sibling_any: list[str] | None = None
    excludes_sibling: str | None = None
    min_siblings: int | None = None
    enabled: bool = True
    extends: str | None = None
    rule_source: str = "builtin"


BUILTIN_RULES: tuple[SidecarRule, ...] = (
    SidecarRule(name="yt-dlp-description", match="{stem}.description", type="description"),
    SidecarRule(name="yt-dlp-info", match="{stem}.info.json", type="json_metadata"),
    SidecarRule(name="json-meta", match="{stem}.meta.json", type="json_metadata"),
    SidecarRule(name="json-metadata", match="{stem}.metadata.json", type="json_metadata"),
    SidecarRule(name="json-exif", match="{stem}.exif.json", type="json_metadata"),
    SidecarRule(name="json-ai", match="{stem}.AI.json", type="json_metadata"),
    SidecarRule(name="json-subs", match="{stem}_subs.json", type="json_metadata"),
    SidecarRule(name="json-subtitles", match="{stem}_subtitles.json", type="json_metadata"),
    SidecarRule(name="json-language-metadata", match="{stem}.*.json", type="json_metadata"),
    SidecarRule(
        name="yt-dlp-thumbnail",
        match="{stem}_screen*.jpg",
        type="screenshot",
        requires_sibling="{stem}.*",
    ),
    SidecarRule(
        name="yt-dlp-thumbnail-png",
        match="{stem}_screen*.png",
        type="screenshot",
        requires_sibling="{stem}.*",
    ),
    SidecarRule(
        name="yt-dlp-thumbnail-webp",
        match="{stem}_screen*.webp",
        type="screenshot",
        requires_sibling="{stem}.*",
    ),
    SidecarRule(
        name="yt-dlp-subtitles-vtt",
        match="{stem}.*.vtt",
        type="subtitles",
        requires_sibling_any=["{stem}.mp4", "{stem}.mkv", "{stem}.webm"],
    ),
    SidecarRule(name="subtitle-srt", match="{stem}.srt", type="subtitles"),
    SidecarRule(name="subtitle-sub", match="{stem}.sub", type="subtitles"),
    SidecarRule(name="subtitle-sbv", match="{stem}.sbv", type="subtitles"),
    SidecarRule(name="subtitle-vtt", match="{stem}.vtt", type="subtitles"),
    SidecarRule(name="subtitle-lrc", match="{stem}.lrc", type="subtitles"),
    SidecarRule(name="subtitle-text", match="{stem}.*.txt", type="subtitles"),
    SidecarRule(name="any-lnk", match="*.lnk", type="shortcut", scope="directory"),
    SidecarRule(
        name="desktop-ini",
        match="desktop.ini",
        type="desktop_ini",
        scope="directory",
    ),
    SidecarRule(name="dotted-desktop-ini", match="*.desktop.ini", type="desktop_ini"),
    SidecarRule(name="any-url", match="*.url", type="link"),
    SidecarRule(name="any-link", match="*.link", type="link"),
    SidecarRule(name="any-source-link", match="*.source", type="link"),
    SidecarRule(name="any-torrent", match="*.torrent", type="torrent"),
    SidecarRule(name="any-magnet", match="*.magnet", type="torrent"),
    SidecarRule(name="nfo-file", match="{stem}.nfo", type="generic_metadata"),
    SidecarRule(name="meta-exif", match="{stem}.exif", type="generic_metadata"),
    SidecarRule(name="meta-meta", match="{stem}.meta", type="generic_metadata"),
    SidecarRule(name="meta-metadata", match="{stem}.metadata", type="generic_metadata"),
    SidecarRule(name="meta-comments", match="{stem}.comments", type="generic_metadata"),
    SidecarRule(name="meta-cfg", match="{stem}.cfg", type="generic_metadata"),
    SidecarRule(name="meta-conf", match="{stem}.conf", type="generic_metadata"),
    SidecarRule(name="meta-config", match="{stem}.config", type="generic_metadata"),
    SidecarRule(name="meta-yaml", match="{stem}.yaml", type="generic_metadata"),
    SidecarRule(
        name="git-attributes",
        match=".gitattributes",
        type="generic_metadata",
        scope="directory",
    ),
    SidecarRule(name="git-ignore", match=".gitignore", type="generic_metadata", scope="directory"),
    SidecarRule(name="hash-md5", match="{stem}.md5", type="hash"),
    SidecarRule(name="hash-sha1", match="{stem}.sha1", type="hash"),
    SidecarRule(name="hash-sha256", match="{stem}.sha256", type="hash"),
    SidecarRule(name="hash-sha512", match="{stem}.sha512", type="hash"),
    SidecarRule(name="hash-blake2b", match="{stem}.blake2b", type="hash"),
    SidecarRule(name="hash-blake2s", match="{stem}.blake2s", type="hash"),
    SidecarRule(name="hash-crc32", match="{stem}.crc32", type="hash"),
    SidecarRule(name="hash-xxhash", match="{stem}.xxhash", type="hash"),
    SidecarRule(name="hash-checksum", match="{stem}.checksum", type="hash"),
    SidecarRule(name="hash-generic", match="{stem}.hash", type="hash"),
)


@dataclass(frozen=True)
class _DirectoryContext:
    directory_id: str | None
    file_entries: tuple[IndexEntry, ...]


def _final_stem(filename: str) -> str:
    return PurePosixPath(filename).stem


def _matches_pattern(pattern: str, filename: str) -> bool:
    return fnmatch.fnmatchcase(filename.lower(), pattern.lower())


def _resolve_pattern(pattern: str, stem: str | None) -> str:
    resolved = pattern
    if stem is not None:
        resolved = resolved.replace("{stem}", stem)
    return resolved


def _ordered_stems(directory_stems: set[str]) -> list[str]:
    return sorted(directory_stems, key=lambda value: (-len(value), value.lower()))


def match_rule(rule: SidecarRule, filename: str, directory_stems: set[str]) -> str | None:
    """Return the matched target stem if *rule* matches *filename*."""
    if rule.scope == "directory":
        return "" if _matches_pattern(rule.match, filename) else None

    if "{stem}" in rule.match:
        for stem in _ordered_stems(directory_stems):
            if _matches_pattern(_resolve_pattern(rule.match, stem), filename):
                return stem
        return None

    if _matches_pattern(rule.match, filename):
        return _final_stem(filename)
    return None


def evaluate_predicates(
    rule: SidecarRule,
    filename: str,
    sibling_filenames: set[str],
    bound_stem: str | None,
) -> tuple[list[PredicateResult], int]:
    """Evaluate rule predicates against sibling filenames."""
    siblings = {name for name in sibling_filenames if name != filename}
    predicates: list[PredicateResult] = []

    if rule.requires_sibling is not None:
        resolved = _resolve_pattern(rule.requires_sibling, bound_stem)
        predicates.append(
            PredicateResult(
                name="requires_sibling",
                pattern=resolved,
                satisfied=any(_matches_pattern(resolved, sibling) for sibling in siblings),
            )
        )

    if rule.requires_sibling_any is not None:
        resolved_patterns = [
            _resolve_pattern(pattern, bound_stem) for pattern in rule.requires_sibling_any
        ]
        predicates.append(
            PredicateResult(
                name="requires_sibling_any",
                patterns=resolved_patterns,
                satisfied=any(
                    _matches_pattern(pattern, sibling)
                    for pattern in resolved_patterns
                    for sibling in siblings
                ),
            )
        )

    if rule.excludes_sibling is not None:
        resolved = _resolve_pattern(rule.excludes_sibling, bound_stem)
        predicates.append(
            PredicateResult(
                name="excludes_sibling",
                pattern=resolved,
                satisfied=not any(_matches_pattern(resolved, sibling) for sibling in siblings),
            )
        )

    if not predicates:
        return [], 3

    satisfied_count = sum(1 for predicate in predicates if predicate.satisfied)
    if satisfied_count == len(predicates):
        return predicates, 3
    if satisfied_count == 0:
        return predicates, 1
    return predicates, 2


def _validate_rule_fields(name: str, rule_data: dict[str, object], source: str) -> None:
    allowed = {
        "match",
        "type",
        "scope",
        "requires_sibling",
        "requires_sibling_any",
        "excludes_sibling",
        "min_siblings",
        "enabled",
        "extends",
        "name",
    }
    unknown = sorted(set(rule_data) - allowed)
    if unknown:
        raise IndexerConfigError(
            f"Unknown fields in {source} sidecar rule {name!r}: {', '.join(unknown)}"
        )

    enabled = rule_data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise IndexerConfigError(f"sidecar rule {name!r} has non-boolean enabled field")

    if enabled:
        if not isinstance(rule_data.get("match"), str) or not rule_data["match"]:
            raise IndexerConfigError(f"sidecar rule {name!r} is missing a non-empty match")
        if not isinstance(rule_data.get("type"), str) or not rule_data["type"]:
            raise IndexerConfigError(f"sidecar rule {name!r} is missing a non-empty type")
    elif not isinstance(rule_data.get("extends") or name, str):
        raise IndexerConfigError(f"sidecar rule {name!r} must disable a named rule")

    scope = rule_data.get("scope", "file")
    if scope not in {"file", "directory"}:
        raise IndexerConfigError(f"sidecar rule {name!r} has invalid scope {scope!r}")

    requires_sibling_any = rule_data.get("requires_sibling_any")
    if requires_sibling_any is not None and not isinstance(requires_sibling_any, (list, tuple)):
        raise IndexerConfigError(
            f"sidecar rule {name!r} requires_sibling_any must be a list of strings"
        )


def _coerce_rule(rule_data: dict[str, object], rule_source: str) -> SidecarRule:
    name = str(rule_data["name"])
    _validate_rule_fields(name, rule_data, rule_source)
    requires_sibling_any = rule_data.get("requires_sibling_any")
    return SidecarRule(
        name=name,
        match=str(rule_data.get("match", "")),
        type=str(rule_data.get("type", "")),
        scope=str(rule_data.get("scope", "file")),
        requires_sibling=(
            str(rule_data["requires_sibling"])
            if rule_data.get("requires_sibling") is not None
            else None
        ),
        requires_sibling_any=(
            [str(pattern) for pattern in requires_sibling_any]
            if requires_sibling_any is not None
            else None
        ),
        excludes_sibling=(
            str(rule_data["excludes_sibling"])
            if rule_data.get("excludes_sibling") is not None
            else None
        ),
        min_siblings=(
            int(rule_data["min_siblings"]) if rule_data.get("min_siblings") is not None else None
        ),
        enabled=bool(rule_data.get("enabled", True)),
        extends=str(rule_data["extends"]) if rule_data.get("extends") is not None else None,
        rule_source=rule_source,
    )


def _from_rule_config(rule: SidecarRuleConfig, rule_source: str) -> SidecarRule:
    return _coerce_rule(
        {
            "name": rule.name,
            "match": rule.match,
            "type": rule.type,
            "scope": rule.scope,
            "requires_sibling": rule.requires_sibling,
            "requires_sibling_any": (
                list(rule.requires_sibling_any) if rule.requires_sibling_any else None
            ),
            "excludes_sibling": rule.excludes_sibling,
            "min_siblings": rule.min_siblings,
            "enabled": rule.enabled,
            "extends": rule.extends,
        },
        rule_source,
    )


def _load_pack_rules(pack_dir: Path) -> list[SidecarRule]:
    pack_rules: list[SidecarRule] = []
    if not pack_dir.exists():
        return pack_rules

    for pack_file in sorted(pack_dir.glob("*.toml"), key=lambda path: path.name.lower()):
        try:
            toml_data = tomllib.loads(pack_file.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise IndexerConfigError(f"Invalid rule pack {pack_file}: {exc}") from exc

        pack_meta = toml_data.get("pack", {})
        pack_name = (
            pack_meta.get("name", pack_file.stem) if isinstance(pack_meta, dict) else pack_file.stem
        )
        rules_section = toml_data.get("sidecar_rules", {})
        if not isinstance(rules_section, dict):
            raise IndexerConfigError(f"Rule pack {pack_file} is missing a [sidecar_rules] table")

        for rule_name, rule_data in rules_section.items():
            if not isinstance(rule_data, dict):
                raise IndexerConfigError(
                    f"Rule pack {pack_file} has malformed rule {rule_name!r}: expected table"
                )
            merged_rule = dict(rule_data)
            merged_rule["name"] = rule_name
            pack_rules.append(_coerce_rule(merged_rule, f"pack:{pack_name}"))

    return pack_rules


def load_rules(config: IndexerConfig) -> list[SidecarRule]:
    """Load user, pack, and built-in rules in final resolution order."""
    user_rules = [_from_rule_config(rule, "user") for rule in config.sidecar_rules]
    pack_rules = _load_pack_rules(get_pack_dir())

    resolved: list[SidecarRule] = []
    blocked_names: set[str] = set()
    user_names: set[str] = set()
    pack_names: set[str] = set()

    for rule in user_rules:
        if not rule.enabled:
            blocked_names.add(rule.name)
            if rule.extends is not None:
                blocked_names.add(rule.extends)
            continue
        resolved.append(rule)
        user_names.add(rule.name)

    for rule in pack_rules:
        if rule.name in blocked_names or rule.name in user_names or rule.name in pack_names:
            continue
        if not rule.enabled:
            blocked_names.add(rule.name)
            if rule.extends is not None:
                blocked_names.add(rule.extends)
            pack_names.add(rule.name)
            continue
        resolved.append(rule)
        pack_names.add(rule.name)

    overridden_builtin_names = blocked_names | user_names | pack_names
    resolved.extend(rule for rule in BUILTIN_RULES if rule.name not in overridden_builtin_names)
    return resolved


def _flatten_entries(entries: list[IndexEntry]) -> list[IndexEntry]:
    flat: list[IndexEntry] = []
    stack = list(reversed(entries))
    while stack:
        entry = stack.pop()
        flat.append(entry)
        if entry.duplicates:
            stack.extend(reversed(entry.duplicates))
        if entry.items:
            stack.extend(reversed(entry.items))
    return flat


def _file_name(entry: IndexEntry) -> str:
    relative = PurePosixPath(entry.file_system.relative)
    return relative.name


def _parent_relative(entry: IndexEntry) -> str:
    relative = PurePosixPath(entry.file_system.relative)
    return str(relative.parent)


def _resolve_target_id(
    rule: SidecarRule,
    bound_stem: str | None,
    source_entry: IndexEntry,
    stem_to_entries: dict[str, list[IndexEntry]],
    directory_id: str | None,
) -> str | None:
    if rule.scope == "directory":
        return directory_id

    if bound_stem is None:
        return None

    source_name = _file_name(source_entry)
    for candidate in stem_to_entries.get(bound_stem, []):
        if candidate.id == source_entry.id:
            continue
        if _file_name(candidate) == source_name:
            continue
        return candidate.id
    return None


def classify_relationships(
    entries: list[IndexEntry],
    rules: list[SidecarRule],
) -> dict[str, list[RelationshipAnnotation]]:
    """Classify relationships for all entries."""
    flat_entries = _flatten_entries(entries)
    directory_entries: dict[str, IndexEntry] = {}
    grouped_files: dict[str, list[IndexEntry]] = defaultdict(list)

    for entry in flat_entries:
        if entry.type == "directory":
            directory_entries[entry.file_system.relative] = entry
        elif entry.type == "file":
            grouped_files[_parent_relative(entry)].append(entry)

    relationship_map: dict[str, list[RelationshipAnnotation]] = {}

    for directory_relative, file_entries in grouped_files.items():
        file_entries = sorted(file_entries, key=lambda item: _file_name(item).lower())
        filenames = {_file_name(entry) for entry in file_entries}
        directory_stems = {_final_stem(filename) for filename in filenames}
        stem_to_entries: dict[str, list[IndexEntry]] = defaultdict(list)
        for entry in file_entries:
            stem_to_entries[_final_stem(_file_name(entry))].append(entry)

        directory_id = (
            directory_entries.get(directory_relative).id
            if directory_relative in directory_entries
            else None
        )

        for entry in file_entries:
            filename = _file_name(entry)
            for rule in rules:
                bound_stem = match_rule(rule, filename, directory_stems)
                if bound_stem is None:
                    continue

                predicates, confidence = evaluate_predicates(
                    rule,
                    filename,
                    filenames,
                    bound_stem or None,
                )
                target_id = _resolve_target_id(
                    rule,
                    bound_stem or None,
                    entry,
                    stem_to_entries,
                    directory_id,
                )
                if target_id is None:
                    logger.debug(
                        "Skipping relationship for %s via rule %s: target unresolved",
                        entry.file_system.relative,
                        rule.name,
                    )
                    continue

                relationship_map[entry.id] = [
                    RelationshipAnnotation(
                        target_id=target_id,
                        type=rule.type,
                        rule=rule.name,
                        rule_source=rule.rule_source,
                        confidence=confidence,
                        predicates=predicates,
                    )
                ]
                break

    return relationship_map

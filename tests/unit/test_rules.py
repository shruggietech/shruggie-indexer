"""Unit tests for the standalone sidecar rule engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.rules import (
    BUILTIN_RULES,
    SidecarRule,
    classify_relationships,
    evaluate_predicates,
    load_rules,
    match_rule,
)
from shruggie_indexer.exceptions import IndexerConfigError
from shruggie_indexer.models.schema import (
    AttributesObject,
    FileSystemObject,
    HashSet,
    IndexEntry,
    NameObject,
    SizeObject,
    TimestampPair,
    TimestampsObject,
)

RULE_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "rules"


def _timestamp_pair() -> TimestampPair:
    return TimestampPair(iso="2026-04-02T00:00:00.000000+00:00", unix=1)


def _timestamps() -> TimestampsObject:
    pair = _timestamp_pair()
    return TimestampsObject(created=pair, modified=pair, accessed=pair)


def _hashes(value: str) -> HashSet:
    padded = (value * 64)[:64]
    return HashSet(md5=(value * 32)[:32], sha256=padded)


def _file_entry(relative: str, entry_id: str) -> IndexEntry:
    name = Path(relative).name
    suffix = Path(relative).suffix.lstrip(".") or None
    return IndexEntry(
        id=entry_id,
        id_algorithm="md5",
        type="file",
        name=NameObject(text=name, hashes=_hashes(entry_id)),
        extension=suffix,
        size=SizeObject(text="1 B", bytes=1),
        hashes=_hashes(entry_id + "hash"),
        file_system=FileSystemObject(relative=relative, parent=None),
        timestamps=_timestamps(),
        attributes=AttributesObject(is_link=False, storage_name=entry_id),
    )


def _directory_entry(
    relative: str,
    entry_id: str,
    items: list[IndexEntry] | None = None,
) -> IndexEntry:
    name = Path(relative).name if relative != "." else "."
    return IndexEntry(
        id=entry_id,
        id_algorithm="md5",
        type="directory",
        name=NameObject(text=name, hashes=_hashes(entry_id)),
        extension=None,
        size=SizeObject(text="0 B", bytes=0),
        hashes=None,
        file_system=FileSystemObject(relative=relative, parent=None),
        timestamps=_timestamps(),
        attributes=AttributesObject(is_link=False, storage_name=entry_id),
        items=items,
    )


class TestPatternMatching:
    @pytest.mark.parametrize(
        ("rule", "filename", "directory_stems", "expected"),
        [
            (
                SidecarRule(
                    name="desc",
                    match="{stem}.description",
                    type="description",
                ),
                "video.description",
                {"video"},
                "video",
            ),
            (
                SidecarRule(name="wild", match="{stem}.*.vtt", type="subtitles"),
                "video.en.vtt",
                {"video"},
                "video",
            ),
            (
                SidecarRule(
                    name="literal",
                    match="desktop.ini",
                    type="desktop_ini",
                    scope="directory",
                ),
                "desktop.ini",
                {"video"},
                "",
            ),
            (
                SidecarRule(name="nostem", match="*.url", type="link"),
                "video.url",
                {"video"},
                "video",
            ),
            (
                SidecarRule(
                    name="nomatch",
                    match="{stem}.description",
                    type="description",
                ),
                "notes.txt",
                {"video"},
                None,
            ),
        ],
    )
    def test_match_rule(
        self,
        rule: SidecarRule,
        filename: str,
        directory_stems: set[str],
        expected: str | None,
    ) -> None:
        assert match_rule(rule, filename, directory_stems) == expected

    def test_longest_stem_wins(self) -> None:
        rule = SidecarRule(name="subtitle", match="{stem}.*.vtt", type="subtitles")
        matched = match_rule(rule, "movie.trailer.en.vtt", {"movie", "movie.trailer"})
        assert matched == "movie.trailer"


class TestPredicateEvaluation:
    def test_requires_sibling_full_confidence(self) -> None:
        rule = SidecarRule(
            name="thumb",
            match="{stem}_screen.jpg",
            type="screenshot",
            requires_sibling="{stem}.mp4",
        )
        predicates, confidence = evaluate_predicates(
            rule,
            "video_screen.jpg",
            {"video.mp4", "video_screen.jpg"},
            "video",
        )
        assert confidence == 3
        assert predicates[0].satisfied is True

    def test_requires_sibling_any_partial_confidence(self) -> None:
        rule = SidecarRule(
            name="subs",
            match="{stem}.*.vtt",
            type="subtitles",
            requires_sibling="{stem}.mp4",
            requires_sibling_any=["{stem}.mkv", "{stem}.webm"],
        )
        predicates, confidence = evaluate_predicates(
            rule,
            "video.en.vtt",
            {"video.mp4", "video.en.vtt"},
            "video",
        )
        assert confidence == 2
        assert [predicate.satisfied for predicate in predicates] == [True, False]

    def test_requires_sibling_any_no_predicates_satisfied(self) -> None:
        rule = SidecarRule(
            name="subs",
            match="{stem}.*.vtt",
            type="subtitles",
            requires_sibling_any=["{stem}.mkv", "{stem}.webm"],
        )
        predicates, confidence = evaluate_predicates(
            rule,
            "video.en.vtt",
            {"video.en.vtt"},
            "video",
        )
        assert confidence == 1
        assert predicates[0].satisfied is False

    def test_excludes_sibling_reduces_confidence(self) -> None:
        rule = SidecarRule(
            name="desc",
            match="{stem}.description",
            type="description",
            excludes_sibling="{stem}.info.json",
        )
        predicates, confidence = evaluate_predicates(
            rule,
            "video.description",
            {"video.description", "video.info.json"},
            "video",
        )
        assert confidence == 1
        assert predicates[0].satisfied is False

    def test_no_predicates_defaults_to_full_confidence(self) -> None:
        predicates, confidence = evaluate_predicates(
            SidecarRule(name="desc", match="{stem}.description", type="description"),
            "video.description",
            {"video.description"},
            "video",
        )
        assert predicates == []
        assert confidence == 3


class TestRuleLoading:
    @staticmethod
    def _make_valid_pack_dir(tmp_path: Path) -> Path:
        pack_dir = tmp_path / "packs"
        pack_dir.mkdir()
        for pack_name in ("a-first.toml", "b-second.toml"):
            (pack_dir / pack_name).write_text(
                (RULE_FIXTURES / "packs" / pack_name).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        return pack_dir

    def test_user_rules_load_before_builtins(self) -> None:
        config = load_config(config_file=RULE_FIXTURES / "user_rules.toml")
        rules = load_rules(config)
        assert rules[0].name == "custom-note"
        assert any(rule.name == "yt-dlp-info" for rule in rules)

    def test_user_rule_disables_builtin(self) -> None:
        config = load_config(config_file=RULE_FIXTURES / "user_rules.toml")
        rule_names = [rule.name for rule in load_rules(config)]
        assert "yt-dlp-description" not in rule_names

    def test_pack_rules_loaded_between_user_and_builtin(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "shruggie_indexer.core.rules.get_pack_dir",
            lambda: self._make_valid_pack_dir(tmp_path),
        )
        config = load_config(config_file=RULE_FIXTURES / "user_rules.toml")
        rules = load_rules(config)
        names = [rule.name for rule in rules]
        assert names[0] == "custom-note"
        assert names[1] == "pack-description"
        assert names.index("pack-json") < names.index("yt-dlp-info")

    def test_first_pack_definition_wins(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "shruggie_indexer.core.rules.get_pack_dir",
            lambda: self._make_valid_pack_dir(tmp_path),
        )
        rules = load_rules(load_config())
        shared_rule = next(rule for rule in rules if rule.name == "shared-name")
        assert shared_rule.rule_source == "pack:alpha"
        assert shared_rule.type == "description"

    def test_malformed_user_rule_rejected(self) -> None:
        config = load_config(config_file=RULE_FIXTURES / "invalid_user_rule.toml")
        with pytest.raises(IndexerConfigError, match="missing a non-empty type"):
            load_rules(config)

    def test_malformed_pack_rule_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        pack_dir = tmp_path / "packs"
        pack_dir.mkdir()
        (pack_dir / "bad.toml").write_text(
            (RULE_FIXTURES / "packs" / "invalid-pack.toml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "shruggie_indexer.core.rules.get_pack_dir",
            lambda: pack_dir,
        )
        with pytest.raises(IndexerConfigError, match="missing a non-empty type"):
            load_rules(load_config())


class TestClassification:
    def test_file_scoped_relationship_classified(self) -> None:
        entries = [
            _file_entry("video.mp4", "y-video"),
            _file_entry("video.description", "y-desc"),
        ]
        relationships = classify_relationships(entries, [BUILTIN_RULES[0]])
        assert relationships["y-desc"][0].target_id == "y-video"
        assert relationships["y-desc"][0].type == "description"

    def test_directory_scoped_relationship_targets_directory(self) -> None:
        entries = [
            _directory_entry("videos", "x-videos"),
            _file_entry("videos/desktop.ini", "y-desktop"),
            _file_entry("videos/movie.mp4", "y-movie"),
        ]
        rule = SidecarRule(
            name="desktop-ini",
            match="desktop.ini",
            type="desktop_ini",
            scope="directory",
        )
        relationships = classify_relationships(entries, [rule])
        assert relationships["y-desktop"][0].target_id == "x-videos"

    def test_entries_without_match_are_absent(self) -> None:
        entries = [_file_entry("notes.txt", "y-notes")]
        assert classify_relationships(entries, list(BUILTIN_RULES)) == {}

    def test_nested_entries_are_flattened(self) -> None:
        nested_entries = [
            _directory_entry(
                ".",
                "x-root",
                items=[
                    _directory_entry(
                        "videos",
                        "x-videos",
                        items=[
                            _file_entry("videos/movie.mp4", "y-movie"),
                            _file_entry("videos/movie.description", "y-desc"),
                        ],
                    )
                ],
            )
        ]
        relationships = classify_relationships(nested_entries, [BUILTIN_RULES[0]])
        assert relationships["y-desc"][0].target_id == "y-movie"

    def test_predicate_detail_is_preserved(self) -> None:
        entries = [
            _file_entry("video.mp4", "y-video"),
            _file_entry("video.en.vtt", "y-vtt"),
        ]
        rule = SidecarRule(
            name="subs",
            match="{stem}.*.vtt",
            type="subtitles",
            requires_sibling_any=["{stem}.mkv", "{stem}.mp4"],
        )
        relationships = classify_relationships(entries, [rule])
        annotation = relationships["y-vtt"][0]
        assert annotation.confidence == 3
        assert annotation.predicates[0].name == "requires_sibling_any"
        assert annotation.predicates[0].patterns == ["video.mkv", "video.mp4"]

    @pytest.mark.parametrize(
        "expected_type",
        [
            "description",
            "json_metadata",
            "screenshot",
            "subtitles",
            "shortcut",
            "desktop_ini",
            "link",
            "torrent",
            "generic_metadata",
            "hash",
        ],
    )
    def test_builtin_rule_library_covers_sidecar_vocab(self, expected_type: str) -> None:
        assert expected_type in {rule.type for rule in BUILTIN_RULES}

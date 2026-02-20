"""Unit tests for config/loader.py and config/types.py — §7 Configuration.

11 test cases per §14.2.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import IndexerConfig
from shruggie_indexer.exceptions import IndexerConfigError

# Resolved path to the config fixture directory.
_CONFIG_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "config_files"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    """Tests for default configuration construction."""

    def test_default_config(self) -> None:
        """load_config() with no inputs returns a fully populated IndexerConfig."""
        config = load_config()
        assert isinstance(config, IndexerConfig)
        assert config.recursive is True
        assert config.id_algorithm == "md5"
        assert config.compute_sha512 is False
        assert len(config.filesystem_excludes) > 0
        assert len(config.metadata_identify) > 0


class TestTomlLoading:
    """Tests for TOML configuration file loading."""

    def test_toml_loading(self, tmp_path: Path) -> None:
        """Overridden values applied; non-overridden values retain defaults."""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(
            'recursive = false\nid_algorithm = "sha256"\n',
            encoding="utf-8",
        )
        config = load_config(config_file=toml_file)
        assert config.recursive is False
        assert config.id_algorithm == "sha256"
        # Non-overridden default retained
        assert config.compute_sha512 is False

    def test_invalid_toml(self, tmp_path: Path) -> None:
        """Invalid TOML syntax raises IndexerConfigError with clear message."""
        toml_file = tmp_path / "bad.toml"
        toml_file.write_text("[[invalid toml ===", encoding="utf-8")
        with pytest.raises(IndexerConfigError, match="Invalid TOML"):
            load_config(config_file=toml_file)

    def test_invalid_toml_fixture(self) -> None:
        """The invalid.toml fixture file is rejected by the config loader."""
        fixture = _CONFIG_FIXTURES / "invalid.toml.fixture"
        assert fixture.exists(), f"Fixture missing: {fixture}"
        with pytest.raises(IndexerConfigError, match="Invalid TOML"):
            load_config(config_file=fixture)

    def test_unknown_keys_ignored(self, tmp_path: Path) -> None:
        """Unknown keys in TOML do not raise errors."""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(
            'unknown_key = "should_be_ignored"\nrecursive = true\n',
            encoding="utf-8",
        )
        # Should not raise
        config = load_config(config_file=toml_file)
        assert config.recursive is True


class TestCliOverrideMerging:
    """Tests for override merging priority."""

    def test_cli_override_merging(self, tmp_path: Path) -> None:
        """CLI override wins over TOML value."""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text("recursive = false\n", encoding="utf-8")
        config = load_config(
            config_file=toml_file,
            overrides={"recursive": True},
        )
        assert config.recursive is True


class TestFrozenImmutability:
    """Tests for frozen dataclass immutability."""

    def test_frozen_immutability(self) -> None:
        """Attempting to set a field on an IndexerConfig raises FrozenInstanceError."""
        config = load_config()
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.recursive = False  # type: ignore[misc]


class TestSidecarPatternConfig:
    """Tests for sidecar pattern configuration."""

    def test_sidecar_pattern_config(self, tmp_path: Path) -> None:
        """Custom sidecar regex appears in config.metadata_identify."""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(
            '[metadata_identify]\ncustom_type = ["\\\\.custom$"]\n',
            encoding="utf-8",
        )
        config = load_config(config_file=toml_file)
        assert "custom_type" in config.metadata_identify
        patterns = config.metadata_identify["custom_type"]
        assert len(patterns) >= 1


class TestFixtureFiles:
    """Tests that exercise the config fixture files on disk."""

    def test_valid_fixture(self) -> None:
        """valid.toml fixture loads without error and applies overrides."""
        fixture = _CONFIG_FIXTURES / "valid.toml"
        assert fixture.exists(), f"Fixture missing: {fixture}"
        config = load_config(config_file=fixture)
        assert config.recursive is False
        assert config.id_algorithm == "sha256"

    def test_partial_fixture(self) -> None:
        """partial.toml overrides id_algorithm; other fields retain defaults."""
        fixture = _CONFIG_FIXTURES / "partial.toml"
        assert fixture.exists(), f"Fixture missing: {fixture}"
        config = load_config(config_file=fixture)
        assert config.id_algorithm == "sha256"
        # Non-overridden defaults preserved
        assert config.recursive is True


class TestExiftoolExclusionConfig:
    """Tests for exiftool exclusion extension configuration."""

    def test_exiftool_exclusion_config(self, tmp_path: Path) -> None:
        """Custom exclusion extension appears in config."""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(
            "[exiftool]\nexclude_extensions = [\"xyz\", \"abc\"]\n",
            encoding="utf-8",
        )
        config = load_config(config_file=toml_file)
        assert "xyz" in config.exiftool_exclude_extensions
        assert "abc" in config.exiftool_exclude_extensions

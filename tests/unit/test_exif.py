"""Unit tests for core/exif.py — §6.6 EXIF and Embedded Metadata Extraction.

7 test cases per §14.2.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.config.types import IndexerConfig
from shruggie_indexer.core.exif import (
    EXIFTOOL_EXCLUDED_KEYS,
    extract_exif,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(**overrides: object) -> IndexerConfig:
    return load_config(overrides=overrides)  # type: ignore[arg-type]


def _load_fixture(name: str) -> list[dict[str, Any]]:
    fixture = FIXTURES_DIR / "exiftool_responses" / name
    return json.loads(fixture.read_text(encoding="utf-8"))


def _reset_exif_module() -> None:
    """Reset module-level state in exif so probing re-runs."""
    import shruggie_indexer.core.exif as mod

    sentinel = mod._NOT_PROBED
    mod._exiftool_path = sentinel
    mod._pyexiftool_available = sentinel
    mod._backend = sentinel
    mod._batch_helper = None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtractExifSuccess:
    """Test successful metadata extraction with mocked exiftool."""

    def test_successful_extraction_subprocess(
        self, sample_file: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Mocked subprocess backend returns filtered metadata."""
        import shruggie_indexer.core.exif as exif_mod

        fixture_data = _load_fixture("exe_response.json")
        json_out = json.dumps(fixture_data)

        # Set module to subprocess backend.
        monkeypatch.setattr(exif_mod, "_exiftool_path", "exiftool")
        monkeypatch.setattr(exif_mod, "_pyexiftool_available", False)
        monkeypatch.setattr(exif_mod, "_backend", "subprocess")
        monkeypatch.setattr(exif_mod, "_batch_helper", None)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json_out
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            config = _cfg(extract_exif=True)
            result = extract_exif(sample_file, config)

        assert result is not None
        assert isinstance(result, dict)
        # Excluded keys should be removed.
        for key in EXIFTOOL_EXCLUDED_KEYS:
            assert key not in result
        # Real keys should remain.
        assert "EXE:CompanyName" in result or "File:MIMEType" in result


class TestExiftoolAbsent:
    """Test graceful degradation when exiftool is not installed."""

    def test_exiftool_absent_returns_none(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """When exiftool is disabled, extract_exif returns None."""
        config = _cfg(extract_exif=True)
        result = extract_exif(sample_file, config)
        assert result is None


class TestExtensionGate:
    """Test extension exclusion filtering."""

    def test_excluded_extension_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Files with excluded extensions are skipped without calling exiftool."""
        import shruggie_indexer.core.exif as exif_mod

        monkeypatch.setattr(exif_mod, "_exiftool_path", "exiftool")
        monkeypatch.setattr(exif_mod, "_pyexiftool_available", False)
        monkeypatch.setattr(exif_mod, "_backend", "subprocess")

        json_file = tmp_path / "data.json"
        json_file.write_text('{"key": "val"}', encoding="utf-8")

        config = _cfg(extract_exif=True)
        # .json is in the default exclusion list.
        result = extract_exif(json_file, config)
        assert result is None


class TestKeyFiltering:
    """Test that excluded keys are removed from exiftool output."""

    def test_excluded_keys_removed(
        self, sample_file: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """EXIFTOOL_EXCLUDED_KEYS entries are stripped from output."""
        import shruggie_indexer.core.exif as exif_mod

        data = [{
            "ExifToolVersion": 12.76,
            "FileName": "test.txt",
            "Directory": "/tmp",
            "File:MIMEType": "text/plain",
            "Custom:Tag": "value",
        }]

        monkeypatch.setattr(exif_mod, "_exiftool_path", "exiftool")
        monkeypatch.setattr(exif_mod, "_pyexiftool_available", False)
        monkeypatch.setattr(exif_mod, "_backend", "subprocess")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(data)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            config = _cfg(extract_exif=True)
            result = extract_exif(sample_file, config)

        assert result is not None
        assert "ExifToolVersion" not in result
        assert "FileName" not in result
        assert "Directory" not in result
        assert "File:MIMEType" in result
        assert "Custom:Tag" in result


class TestTimeoutHandling:
    """Test subprocess timeout handling."""

    def test_timeout_returns_none(
        self, sample_file: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """subprocess.TimeoutExpired results in None, not an exception."""
        import shruggie_indexer.core.exif as exif_mod

        monkeypatch.setattr(exif_mod, "_exiftool_path", "exiftool")
        monkeypatch.setattr(exif_mod, "_pyexiftool_available", False)
        monkeypatch.setattr(exif_mod, "_backend", "subprocess")

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("exiftool", 30),
        ):
            config = _cfg(extract_exif=True)
            result = extract_exif(sample_file, config)

        assert result is None


class TestMalformedJson:
    """Test malformed JSON handling."""

    def test_malformed_json_returns_none(
        self, sample_file: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Invalid JSON from exiftool results in None."""
        import shruggie_indexer.core.exif as exif_mod

        monkeypatch.setattr(exif_mod, "_exiftool_path", "exiftool")
        monkeypatch.setattr(exif_mod, "_pyexiftool_available", False)
        monkeypatch.setattr(exif_mod, "_backend", "subprocess")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "this is not valid json{{"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            config = _cfg(extract_exif=True)
            result = extract_exif(sample_file, config)

        assert result is None


class TestBackendReset:
    """Test that batch backend failures result in reset."""

    def test_batch_error_resets_helper(
        self, sample_file: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When pyexiftool helper raises, it is set to None for retry."""
        import shruggie_indexer.core.exif as exif_mod

        mock_helper = MagicMock()
        mock_helper.get_metadata.side_effect = RuntimeError("process died")
        mock_helper.__exit__ = MagicMock()

        monkeypatch.setattr(exif_mod, "_exiftool_path", "exiftool")
        monkeypatch.setattr(exif_mod, "_pyexiftool_available", True)
        monkeypatch.setattr(exif_mod, "_backend", "batch")
        monkeypatch.setattr(exif_mod, "_batch_helper", mock_helper)

        # Also mock subprocess fallback to avoid actual subprocess call.
        with patch("subprocess.run", side_effect=OSError("no exiftool")):
            config = _cfg(extract_exif=True)
            result = extract_exif(sample_file, config)

        assert result is None
        # The helper should have been reset to None.
        assert exif_mod._batch_helper is None

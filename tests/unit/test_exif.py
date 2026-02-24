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
    _base_key,
    _filter_keys,
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

    def test_group_prefixed_keys_removed(
        self, sample_file: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Group-prefixed keys (e.g. System:FileName) are matched by base name."""
        import shruggie_indexer.core.exif as exif_mod

        data = [{
            "SourceFile": "C:/Users/test/file.txt",
            "ExifTool:ExifToolVersion": 12.76,
            "ExifTool:Now": "2026:02:23 12:00:00-05:00",
            "ExifTool:ProcessingTime": "0.005 s",
            "System:FileName": "file.txt",
            "System:Directory": "C:/Users/test",
            "System:FileSize": "1234 bytes",
            "System:FileModifyDate": "2026:02:23 12:00:00-05:00",
            "System:FileAccessDate": "2026:02:23 12:00:00-05:00",
            "System:FileCreateDate": "2026:02:23 12:00:00-05:00",
            "System:FilePermissions": "rw-r--r--",
            "System:FileAttributes": "Regular; Archive",
            "File:FileType": "TXT",
            "File:FileTypeExtension": "txt",
            "File:MIMEType": "text/plain",
            "File:Encoding": "utf-8",
            "QuickTime:SomeTag": "preserved",
            "Composite:Duration": 120.5,
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
        # All excluded keys (prefixed and unprefixed) must be absent.
        assert "SourceFile" not in result
        assert "ExifTool:ExifToolVersion" not in result
        assert "ExifTool:Now" not in result
        assert "ExifTool:ProcessingTime" not in result
        assert "System:FileName" not in result
        assert "System:Directory" not in result
        assert "System:FileSize" not in result
        assert "System:FileModifyDate" not in result
        assert "System:FileAccessDate" not in result
        assert "System:FileCreateDate" not in result
        assert "System:FilePermissions" not in result
        assert "System:FileAttributes" not in result
        # Embedded metadata keys must be preserved.
        assert result["File:FileType"] == "TXT"
        assert result["File:FileTypeExtension"] == "txt"
        assert result["File:MIMEType"] == "text/plain"
        assert result["File:Encoding"] == "utf-8"
        assert result["QuickTime:SomeTag"] == "preserved"
        assert result["Composite:Duration"] == 120.5

    def test_expanded_exclusion_set_contains_required_keys(self) -> None:
        """EXIFTOOL_EXCLUDED_KEYS includes all required base key names."""
        required = {
            # Original v1 jq deletion list
            "ExifToolVersion", "FileSequence", "NewGUID", "Directory",
            "FileName", "FilePath", "BaseName", "FilePermissions",
            # Expanded set
            "SourceFile", "FileSize", "FileModifyDate", "FileAccessDate",
            "FileCreateDate", "FileAttributes", "FileDeviceNumber",
            "FileInodeNumber", "FileHardLinks", "FileUserID",
            "FileGroupID", "FileDeviceID", "FileBlockSize",
            "FileBlockCount", "Now", "ProcessingTime",
            # ExifTool informational error field
            "Error",
        }
        assert required.issubset(EXIFTOOL_EXCLUDED_KEYS)


class TestBaseKey:
    """Test the _base_key helper used for prefix-aware key filtering."""

    def test_unprefixed_key(self) -> None:
        assert _base_key("FileName") == "FileName"

    def test_single_prefixed_key(self) -> None:
        assert _base_key("System:FileName") == "FileName"

    def test_double_prefixed_key(self) -> None:
        assert _base_key("Main:System:FileName") == "FileName"

    def test_empty_string(self) -> None:
        assert _base_key("") == ""


class TestFilterKeysDirect:
    """Direct unit tests for _filter_keys without extract_exif."""

    def test_mixed_prefixed_and_unprefixed(self) -> None:
        """Both prefixed and unprefixed excluded keys are removed."""
        data = {
            "ExifToolVersion": 12.76,
            "System:FileName": "test.txt",
            "System:FileSize": "100 bytes",
            "File:MIMEType": "text/plain",
            "SourceFile": "/tmp/test.txt",
            "ExifTool:Now": "2026:01:01",
        }
        result = _filter_keys(data, EXIFTOOL_EXCLUDED_KEYS)
        assert result == {"File:MIMEType": "text/plain"}

    def test_no_excluded_keys(self) -> None:
        """Data with no excluded keys passes through unchanged."""
        data = {
            "File:MIMEType": "text/plain",
            "Composite:Duration": 42,
        }
        result = _filter_keys(data, EXIFTOOL_EXCLUDED_KEYS)
        assert result == data

    def test_all_excluded_returns_empty(self) -> None:
        """Data containing only excluded keys results in empty dict."""
        data = {
            "System:FileName": "test.txt",
            "ExifToolVersion": 12.76,
            "SourceFile": "/tmp/test.txt",
        }
        result = _filter_keys(data, EXIFTOOL_EXCLUDED_KEYS)
        assert result == {}


class TestConfigurableExcludeKeys:
    """Test user-customizable exiftool key exclusions (§4.3)."""

    def test_default_config_matches_hardcoded_set(self) -> None:
        """Default config produces the same exclusion set as EXIFTOOL_EXCLUDED_KEYS."""
        config = _cfg(extract_exif=True)
        assert config.exiftool_exclude_keys == EXIFTOOL_EXCLUDED_KEYS

    def test_replace_mode(self) -> None:
        """exiftool.exclude_keys replaces the entire exclusion set."""
        custom_set = frozenset({"SourceFile"})
        result = _filter_keys(
            {
                "SourceFile": "/tmp/test.txt",
                "ExifToolVersion": 12.76,
                "File:MIMEType": "text/plain",
            },
            custom_set,
        )
        # Only SourceFile should be excluded; ExifToolVersion passes through
        assert "SourceFile" not in result
        assert result == {"ExifToolVersion": 12.76, "File:MIMEType": "text/plain"}

    def test_append_mode(self) -> None:
        """exiftool.exclude_keys_append adds keys to the default set."""
        extended_set = EXIFTOOL_EXCLUDED_KEYS | {"Copyright", "Artist"}
        data = {
            "Copyright": "2026 Test",
            "Artist": "John Doe",
            "File:MIMEType": "text/plain",
            "ExifToolVersion": 12.76,  # in default set
        }
        result = _filter_keys(data, extended_set)
        # Copyright, Artist, and ExifToolVersion should all be excluded
        assert result == {"File:MIMEType": "text/plain"}

    def test_replace_mode_via_config_loader(self) -> None:
        """Config loader correctly resolves a replace-mode exclusion set."""
        from shruggie_indexer.config.loader import load_config

        config = load_config(
            overrides={"exiftool.exclude_keys": frozenset({"SourceFile", "FileName"})},
        )
        assert config.exiftool_exclude_keys == frozenset({"SourceFile", "FileName"})

    def test_append_mode_via_toml(self, tmp_path: Path) -> None:
        """TOML exclude_keys_append extends the default set."""
        from shruggie_indexer.config.loader import load_config

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[exiftool]\nexclude_keys_append = ["Copyright", "Artist"]\n',
            encoding="utf-8",
        )
        config = load_config(config_file=config_file)
        assert "Copyright" in config.exiftool_exclude_keys
        assert "Artist" in config.exiftool_exclude_keys
        # Default keys must still be present
        assert "SourceFile" in config.exiftool_exclude_keys
        assert "ExifToolVersion" in config.exiftool_exclude_keys

    def test_replace_mode_via_toml(self, tmp_path: Path) -> None:
        """TOML exclude_keys replaces the entire set."""
        from shruggie_indexer.config.loader import load_config

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[exiftool]\nexclude_keys = ["SourceFile"]\n',
            encoding="utf-8",
        )
        config = load_config(config_file=config_file)
        assert config.exiftool_exclude_keys == frozenset({"SourceFile"})

    def test_custom_exclusion_applied_in_extract(
        self, sample_file: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Custom exclusion set is applied during extract_exif."""
        import shruggie_indexer.core.exif as exif_mod

        data = [{
            "File:MIMEType": "text/plain",
            "Copyright": "2026 Test",
            "SourceFile": "/tmp/test.txt",
        }]

        monkeypatch.setattr(exif_mod, "_exiftool_path", "exiftool")
        monkeypatch.setattr(exif_mod, "_pyexiftool_available", False)
        monkeypatch.setattr(exif_mod, "_backend", "subprocess")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(data)
        mock_result.stderr = ""

        # Use a custom set that only excludes SourceFile
        config = load_config(
            overrides={
                "extract_exif": True,
                "exiftool.exclude_keys": frozenset({"SourceFile"}),
            },
        )
        with patch("subprocess.run", return_value=mock_result):
            result = extract_exif(sample_file, config)

        assert result is not None
        # SourceFile excluded by custom set
        assert "SourceFile" not in result
        # Copyright NOT excluded (not in custom set)
        assert "Copyright" in result
        assert result["File:MIMEType"] == "text/plain"

    def test_empty_exclusion_set_passes_all(self) -> None:
        """An empty exclusion set passes all keys through."""
        data = {
            "SourceFile": "/tmp/test.txt",
            "ExifToolVersion": 12.76,
            "File:MIMEType": "text/plain",
        }
        result = _filter_keys(data, frozenset())
        assert result == data


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


class TestNonZeroExitMetadataRecovery:
    """Test that valid metadata is recovered from non-zero exit codes.

    ExifTool returns exit code 1 for "Unknown file type" but still produces
    valid system-level metadata.  These tests verify that shruggie-indexer
    captures this metadata instead of discarding it (§3.3).
    """

    _7Z_EXIFTOOL_RESPONSE = [{
        "SourceFile": "FeedsExport.7z",
        "ExifTool:ExifToolVersion": 13.10,
        "ExifTool:Now": "2026:02:23 19:35:11-05:00",
        "ExifTool:Error": "Unknown file type",
        "ExifTool:ProcessingTime": "0.366 s",
        "System:FileSize": "728 MB",
        "System:FileModifyDate": "2026:02:09 16:14:22-05:00",
        "System:FileAccessDate": "2026:02:23 19:35:11-05:00",
        "System:FileCreateDate": "2026:02:23 19:28:39-05:00",
        "System:FileAttributes": "Regular; (none); Archive",
        # MIMEType survives key filtering — validates metadata recovery.
        "File:MIMEType": "application/x-7z-compressed",
    }]

    def test_batch_recovers_metadata_on_nonzero_exit(
        self, sample_file: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Batch backend recovers valid JSON from ExifToolExecuteError."""
        import shruggie_indexer.core.exif as exif_mod

        # Simulate ExifToolExecuteError with valid stdout
        stdout_json = json.dumps(self._7Z_EXIFTOOL_RESPONSE)

        class FakeExifToolExecuteError(Exception):
            def __init__(self_inner) -> None:  # noqa: N805, ANN101
                super().__init__("execute returned a non-zero exit status: 1")
                self_inner.returncode = 1
                self_inner.stdout = stdout_json
                self_inner.stderr = ""
                self_inner.cmd = ["-json"]

        mock_helper = MagicMock()
        mock_helper.get_metadata.side_effect = FakeExifToolExecuteError()

        monkeypatch.setattr(exif_mod, "_exiftool_path", "exiftool")
        monkeypatch.setattr(exif_mod, "_pyexiftool_available", True)
        monkeypatch.setattr(exif_mod, "_backend", "batch")
        monkeypatch.setattr(exif_mod, "_batch_helper", mock_helper)

        config = _cfg(extract_exif=True)
        result = extract_exif(sample_file, config)

        # Must return filtered metadata, NOT None.
        assert result is not None
        assert isinstance(result, dict)
        # Excluded keys must be removed (SourceFile, FileSize, Error, etc.)
        assert "SourceFile" not in result
        assert "ExifTool:ExifToolVersion" not in result
        assert "ExifTool:Now" not in result
        assert "ExifTool:ProcessingTime" not in result
        assert "ExifTool:Error" not in result
        assert "System:FileSize" not in result
        assert "System:FileModifyDate" not in result
        assert "System:FileAttributes" not in result
        # The batch helper must NOT be reset after a recoverable error.
        assert exif_mod._batch_helper is mock_helper

    def test_subprocess_recovers_metadata_on_nonzero_exit(
        self, sample_file: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Subprocess fallback recovers valid JSON on exit code 1."""
        import shruggie_indexer.core.exif as exif_mod

        monkeypatch.setattr(exif_mod, "_exiftool_path", "exiftool")
        monkeypatch.setattr(exif_mod, "_pyexiftool_available", False)
        monkeypatch.setattr(exif_mod, "_backend", "subprocess")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps(self._7Z_EXIFTOOL_RESPONSE)
        mock_result.stderr = "Warning: Unknown file type"

        with patch("subprocess.run", return_value=mock_result):
            config = _cfg(extract_exif=True)
            result = extract_exif(sample_file, config)

        # Must return filtered metadata, NOT None.
        assert result is not None
        assert isinstance(result, dict)
        # Excluded keys removed
        assert "SourceFile" not in result
        assert "ExifTool:Error" not in result

    def test_nonzero_exit_no_stdout_returns_none(
        self, sample_file: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-zero exit with no stdout data returns None (true failure)."""
        import shruggie_indexer.core.exif as exif_mod

        monkeypatch.setattr(exif_mod, "_exiftool_path", "exiftool")
        monkeypatch.setattr(exif_mod, "_pyexiftool_available", False)
        monkeypatch.setattr(exif_mod, "_backend", "subprocess")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Fatal error"

        with patch("subprocess.run", return_value=mock_result):
            config = _cfg(extract_exif=True)
            result = extract_exif(sample_file, config)

        assert result is None

    def test_batch_nonzero_no_stdout_resets_helper(
        self, sample_file: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Batch error with no recoverable stdout resets the helper."""
        import shruggie_indexer.core.exif as exif_mod

        # Error without stdout attribute (true process failure)
        mock_helper = MagicMock()
        mock_helper.get_metadata.side_effect = RuntimeError("broken pipe")
        mock_helper.__exit__ = MagicMock()

        monkeypatch.setattr(exif_mod, "_exiftool_path", "exiftool")
        monkeypatch.setattr(exif_mod, "_pyexiftool_available", True)
        monkeypatch.setattr(exif_mod, "_backend", "batch")
        monkeypatch.setattr(exif_mod, "_batch_helper", mock_helper)

        with patch("subprocess.run", side_effect=OSError("no exiftool")):
            config = _cfg(extract_exif=True)
            result = extract_exif(sample_file, config)

        assert result is None
        assert exif_mod._batch_helper is None

    def test_error_key_excluded_from_output(self) -> None:
        """The 'Error' base key is in EXIFTOOL_EXCLUDED_KEYS."""
        assert "Error" in EXIFTOOL_EXCLUDED_KEYS

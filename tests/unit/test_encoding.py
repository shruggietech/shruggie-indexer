"""Unit tests for core/encoding.py — Encoding Detection Module.

Covers: BOM detection (all five types plus no-BOM), line-ending detection
(LF, CRLF, mixed, none), chardet integration (UTF-8, Windows-1252),
edge cases (empty input, binary data), and BOM_BYTES reverse lookup.
"""

from __future__ import annotations

from shruggie_indexer.core.encoding import (
    BOM_BYTES,
    detect_bom,
    detect_bytes_encoding,
    detect_charset,
    detect_file_encoding,
    detect_line_endings,
)
from shruggie_indexer.models.schema import EncodingObject

# ---------------------------------------------------------------------------
# BOM Detection
# ---------------------------------------------------------------------------


class TestDetectBom:
    """Tests for BOM prefix detection."""

    def test_utf8_bom(self) -> None:
        """UTF-8 BOM (EF BB BF) is detected."""
        data = b"\xef\xbb\xbf" + b"hello"
        assert detect_bom(data) == "utf-8"

    def test_utf16_le_bom(self) -> None:
        """UTF-16 LE BOM (FF FE) is detected."""
        data = b"\xff\xfe" + b"h\x00"
        assert detect_bom(data) == "utf-16-le"

    def test_utf16_be_bom(self) -> None:
        """UTF-16 BE BOM (FE FF) is detected."""
        data = b"\xfe\xff" + b"\x00h"
        assert detect_bom(data) == "utf-16-be"

    def test_utf32_le_bom(self) -> None:
        """UTF-32 LE BOM (FF FE 00 00) is detected, not confused with UTF-16 LE."""
        data = b"\xff\xfe\x00\x00" + b"h\x00\x00\x00"
        assert detect_bom(data) == "utf-32-le"

    def test_utf32_be_bom(self) -> None:
        """UTF-32 BE BOM (00 00 FE FF) is detected."""
        data = b"\x00\x00\xfe\xff" + b"\x00\x00\x00h"
        assert detect_bom(data) == "utf-32-be"

    def test_no_bom(self) -> None:
        """Plain ASCII data has no BOM."""
        data = b"hello world"
        assert detect_bom(data) is None

    def test_empty_data(self) -> None:
        """Empty bytes have no BOM."""
        assert detect_bom(b"") is None


# ---------------------------------------------------------------------------
# Line-Ending Detection
# ---------------------------------------------------------------------------


class TestDetectLineEndings:
    """Tests for line-ending convention detection."""

    def test_lf_only(self) -> None:
        """Files with only LF line endings are detected as 'lf'."""
        data = b"line1\nline2\n"
        assert detect_line_endings(data) == "lf"

    def test_crlf_only(self) -> None:
        """Files with only CRLF line endings are detected as 'crlf'."""
        data = b"line1\r\nline2\r\n"
        assert detect_line_endings(data) == "crlf"

    def test_mixed_line_endings(self) -> None:
        """Files with both CRLF and bare LF are detected as 'mixed'."""
        data = b"line1\r\nline2\nline3\r\n"
        assert detect_line_endings(data) == "mixed"

    def test_no_line_endings(self) -> None:
        """Single-line files with no newlines return None."""
        data = b"single line"
        assert detect_line_endings(data) is None

    def test_empty_data(self) -> None:
        """Empty bytes have no line endings."""
        assert detect_line_endings(b"") is None

    def test_bom_stripped_before_detection(self) -> None:
        """BOM bytes do not interfere with line-ending detection."""
        data = b"\xef\xbb\xbf" + b"line1\r\nline2\r\n"
        assert detect_line_endings(data) == "crlf"

    def test_only_lf_in_middle(self) -> None:
        """A single bare LF is detected."""
        data = b"hello\nworld"
        assert detect_line_endings(data) == "lf"

    def test_only_crlf_in_middle(self) -> None:
        """A single CRLF is detected."""
        data = b"hello\r\nworld"
        assert detect_line_endings(data) == "crlf"


# ---------------------------------------------------------------------------
# Chardet Integration
# ---------------------------------------------------------------------------


class TestDetectCharset:
    """Tests for chardet-based character encoding detection."""

    def test_utf8_detection(self) -> None:
        """UTF-8 encoded text is detected with high confidence."""
        text = "The quick brown fox jumps over the lazy dog. " * 20
        data = text.encode("utf-8")
        encoding, confidence = detect_charset(data)
        assert encoding is not None
        # chardet may report "ascii" for pure ASCII text; both are valid
        assert encoding in ("utf-8", "ascii")
        assert confidence is not None
        assert confidence > 0.9

    def test_utf8_with_non_ascii(self) -> None:
        """UTF-8 text with non-ASCII characters is detected as UTF-8."""
        text = "Ünïcödé téxt with spëcîal charäctêrs. " * 10
        data = text.encode("utf-8")
        encoding, confidence = detect_charset(data)
        assert encoding is not None
        assert encoding == "utf-8"
        assert confidence is not None
        assert confidence > 0.8

    def test_windows_1252_detection(self) -> None:
        """Windows-1252 encoded text is detected correctly."""
        # Use characters that are valid in Windows-1252 but not in UTF-8
        # as raw bytes: curly quotes, em dash, etc.
        data = (
            b"This is a Windows-1252 file with special chars: "
            b"\x93smart quotes\x94 and \x96em dash\x97 "
            b"and \xe9 accent and \xf1 tilde. " * 10
        )
        encoding, _confidence = detect_charset(data)
        assert encoding is not None
        # chardet may report windows-1252 or iso-8859-1
        assert "1252" in encoding or "8859" in encoding

    def test_empty_data(self) -> None:
        """Empty data returns a valid result (chardet returns a default)."""
        encoding, _confidence = detect_charset(b"")
        # chardet may return a default encoding for empty input; accept either
        assert encoding is None or isinstance(encoding, str)


# ---------------------------------------------------------------------------
# Integration: detect_bytes_encoding / detect_file_encoding
# ---------------------------------------------------------------------------


class TestDetectBytesEncoding:
    """Tests for the bytes-level convenience function."""

    def test_empty_returns_none(self) -> None:
        """Empty byte buffer returns None."""
        assert detect_bytes_encoding(b"") is None

    def test_bom_and_crlf_detected(self) -> None:
        """UTF-8 BOM + CRLF line endings are detected together."""
        data = b"\xef\xbb\xbf" + b"line1\r\nline2\r\n"
        result = detect_bytes_encoding(data)
        assert result is not None
        assert result.bom == "utf-8"
        assert result.line_endings == "crlf"

    def test_lf_only_detected(self) -> None:
        """LF-only text without BOM is detected."""
        data = b"line1\nline2\n"
        result = detect_bytes_encoding(data)
        assert result is not None
        assert result.bom is None
        assert result.line_endings == "lf"

    def test_charset_disabled(self) -> None:
        """When charset detection is disabled, only BOM and line endings are returned."""
        data = b"\xef\xbb\xbf" + b"line1\nline2\n"
        result = detect_bytes_encoding(data, detect_charset_enabled=False)
        assert result is not None
        assert result.bom == "utf-8"
        assert result.line_endings == "lf"
        assert result.detected_encoding is None
        assert result.confidence is None

    def test_binary_no_signals_returns_none(self) -> None:
        """Random binary bytes with no line endings and no BOM returns None.

        Note: chardet may still detect an encoding for some byte sequences,
        so we only test with charset detection disabled to ensure determinism.
        """
        # Bytes that have no newlines and no BOM prefix
        data = bytes(range(128, 256))
        result = detect_bytes_encoding(data, detect_charset_enabled=False)
        assert result is None


class TestDetectFileEncoding:
    """Tests for the file-level convenience function."""

    def test_file_with_bom(self, tmp_path) -> None:
        """File with UTF-8 BOM is detected correctly."""
        f = tmp_path / "bom.txt"
        f.write_bytes(b"\xef\xbb\xbf" + b"hello\nworld\n")
        result = detect_file_encoding(f)
        assert result is not None
        assert result.bom == "utf-8"
        assert result.line_endings == "lf"

    def test_file_with_crlf(self, tmp_path) -> None:
        """File with CRLF line endings is detected correctly."""
        f = tmp_path / "crlf.txt"
        f.write_bytes(b"line1\r\nline2\r\n")
        result = detect_file_encoding(f)
        assert result is not None
        assert result.line_endings == "crlf"

    def test_empty_file(self, tmp_path) -> None:
        """Empty file returns None."""
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        result = detect_file_encoding(f)
        assert result is None

    def test_nonexistent_file(self, tmp_path) -> None:
        """Non-existent file returns None (not an exception)."""
        f = tmp_path / "nonexistent.txt"
        result = detect_file_encoding(f)
        assert result is None


# ---------------------------------------------------------------------------
# BOM_BYTES Reverse Lookup
# ---------------------------------------------------------------------------


class TestBomBytesReverseLookup:
    """Tests for the BOM_BYTES reverse lookup dictionary."""

    def test_utf8_bom_bytes(self) -> None:
        assert BOM_BYTES["utf-8"] == b"\xef\xbb\xbf"

    def test_utf16_le_bom_bytes(self) -> None:
        assert BOM_BYTES["utf-16-le"] == b"\xff\xfe"

    def test_utf16_be_bom_bytes(self) -> None:
        assert BOM_BYTES["utf-16-be"] == b"\xfe\xff"

    def test_utf32_le_bom_bytes(self) -> None:
        assert BOM_BYTES["utf-32-le"] == b"\xff\xfe\x00\x00"

    def test_utf32_be_bom_bytes(self) -> None:
        assert BOM_BYTES["utf-32-be"] == b"\x00\x00\xfe\xff"

    def test_all_five_bom_types_present(self) -> None:
        """All five BOM identifiers are in the lookup table."""
        expected = {"utf-8", "utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"}
        assert set(BOM_BYTES.keys()) == expected


# ---------------------------------------------------------------------------
# EncodingObject.to_dict() Edge Cases
# ---------------------------------------------------------------------------


class TestEncodingObjectToDict:
    """Tests for EncodingObject serialization."""

    def test_all_none_returns_empty_dict(self) -> None:
        """All-None EncodingObject produces empty dict."""
        enc = EncodingObject()
        assert enc.to_dict() == {}

    def test_partial_fields(self) -> None:
        """Only populated fields appear in dict."""
        enc = EncodingObject(bom="utf-8", line_endings="lf")
        d = enc.to_dict()
        assert d == {"bom": "utf-8", "line_endings": "lf"}
        assert "detected_encoding" not in d
        assert "confidence" not in d

    def test_full_fields(self) -> None:
        """All populated fields appear in dict."""
        enc = EncodingObject(
            bom="utf-8",
            line_endings="crlf",
            detected_encoding="utf-8",
            confidence=0.99,
        )
        d = enc.to_dict()
        assert d == {
            "bom": "utf-8",
            "line_endings": "crlf",
            "detected_encoding": "utf-8",
            "confidence": 0.99,
        }

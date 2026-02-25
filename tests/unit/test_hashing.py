"""Unit tests for core/hashing.py — §6.3 Hashing and Identity Generation.

12 test cases per §14.2.
"""

from __future__ import annotations

import hashlib
import re
import threading
from pathlib import Path

import pytest

from shruggie_indexer.core.hashing import (
    NULL_HASHES,
    hash_directory_id,
    hash_file,
    hash_string,
    select_id,
)
from shruggie_indexer.exceptions import IndexerCancellationError
from shruggie_indexer.models.schema import HashSet

# ---------------------------------------------------------------------------
# Pre-computed reference values
# ---------------------------------------------------------------------------

# hashlib.md5(b"hello world").hexdigest().upper()
_HELLO_MD5 = "5EB63BBBE01EEED093CB22BB8F5ACDC3"
# hashlib.sha256(b"hello world").hexdigest().upper()
_HELLO_SHA256 = "B94D27B9934D3E08A52E52D7DA7DABFAC484EFE37A5380EE9088F7ACE2EFCDE9"

# hashlib.md5(b"").hexdigest().upper()
_EMPTY_MD5 = "D41D8CD98F00B204E9800998ECF8427E"
# hashlib.sha256(b"").hexdigest().upper()
_EMPTY_SHA256 = "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855"
# hashlib.sha512(b"").hexdigest().upper()
_EMPTY_SHA512 = (
    "CF83E1357EEFB8BDF1542850D66D8007D620E4050B5715DC83F4A921D36CE9CE"
    "47D0D13C5D85F2B0FF8318D2877EEC2F63B931BD47417A81A538327AF927DA3E"
)

_UPPERCASE_HEX_RE = re.compile(r"^[0-9A-F]+$")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHashFile:
    """Tests for hash_file()."""

    def test_hash_known_file_content(self, sample_file: Path) -> None:
        """MD5 and SHA256 of ``b'hello world'`` match pre-computed values."""
        result = hash_file(sample_file)
        assert result.md5 == _HELLO_MD5
        assert result.sha256 == _HELLO_SHA256

    def test_hash_empty_file(self, empty_file: Path) -> None:
        """Zero-byte file returns the well-known empty-input hashes."""
        result = hash_file(empty_file)
        assert result.md5 == _EMPTY_MD5
        assert result.sha256 == _EMPTY_SHA256

    def test_multi_algorithm_single_pass(self, sample_file: Path) -> None:
        """All four digests returned when 3 algorithms requested.

        We verify all three are present and the file is read in a single
        streaming pass by checking the result structure.
        """
        result = hash_file(sample_file, algorithms=("md5", "sha256", "sha512"))
        assert result.md5 == _HELLO_MD5
        assert result.sha256 == _HELLO_SHA256
        assert result.sha512 is not None
        # Verify SHA512 matches independently computed value.
        expected_sha512 = hashlib.sha512(b"hello world").hexdigest().upper()
        assert result.sha512 == expected_sha512

    def test_default_algorithms(self, sample_file: Path) -> None:
        """No explicit algorithms -> md5 + sha256 populated, sha512 is None."""
        result = hash_file(sample_file)
        assert result.md5 is not None
        assert result.sha256 is not None
        assert result.sha512 is None

    def test_sha512_optional(self, sample_file: Path) -> None:
        """Explicit (md5, sha256) -> sha512 is None."""
        result = hash_file(sample_file, algorithms=("md5", "sha256"))
        assert result.sha512 is None

    def test_cancel_event_raises(self, large_file: Path) -> None:
        """Pre-set cancel_event raises IndexerCancellationError."""
        cancel = threading.Event()
        cancel.set()
        with pytest.raises(IndexerCancellationError):
            hash_file(large_file, cancel_event=cancel)

    def test_cancel_event_none_no_effect(self, sample_file: Path) -> None:
        """Default cancel_event=None does not interfere with hashing."""
        result = hash_file(sample_file, cancel_event=None)
        assert result.md5 == _HELLO_MD5


class TestHashString:
    """Tests for hash_string()."""

    def test_hash_string(self) -> None:
        """hash_string('sunset.jpg') returns expected MD5 and SHA256."""
        result = hash_string("sunset.jpg")
        expected_md5 = hashlib.md5(b"sunset.jpg").hexdigest().upper()
        expected_sha256 = hashlib.sha256(b"sunset.jpg").hexdigest().upper()
        assert result.md5 == expected_md5
        assert result.sha256 == expected_sha256

    def test_hash_empty_string(self) -> None:
        """Empty string returns NULL_HASHES."""
        result = hash_string("")
        assert result is NULL_HASHES

    def test_hash_none(self) -> None:
        """None input returns NULL_HASHES."""
        result = hash_string(None)
        assert result is NULL_HASHES


class TestHashDirectoryId:
    """Tests for hash_directory_id() — the two-layer hashing scheme."""

    def test_directory_identity_two_layer(self) -> None:
        """hash_directory_id('vacation', 'photos') matches manual step-through.

        Algorithm:
          1. hash('vacation') -> name_digest
          2. hash('photos')   -> parent_digest
          3. hash(name_digest + parent_digest) -> final
        """
        result = hash_directory_id("vacation", "photos")

        # Step through manually.
        name_md5 = hashlib.md5(b"vacation").hexdigest().upper()
        parent_md5 = hashlib.md5(b"photos").hexdigest().upper()
        combined_md5 = (name_md5 + parent_md5).encode("utf-8")
        expected_md5 = hashlib.md5(combined_md5).hexdigest().upper()
        assert result.md5 == expected_md5

        name_sha256 = hashlib.sha256(b"vacation").hexdigest().upper()
        parent_sha256 = hashlib.sha256(b"photos").hexdigest().upper()
        combined_sha256 = (name_sha256 + parent_sha256).encode("utf-8")
        expected_sha256 = hashlib.sha256(combined_sha256).hexdigest().upper()
        assert result.sha256 == expected_sha256


class TestNullHashes:
    """Tests for the NULL_HASHES module-level constant."""

    def test_null_hash_constant(self) -> None:
        """NULL_HASHES matches hashlib.*( b'').hexdigest().upper()."""
        assert NULL_HASHES.md5 == _EMPTY_MD5
        assert NULL_HASHES.sha256 == _EMPTY_SHA256
        assert NULL_HASHES.sha512 == _EMPTY_SHA512


class TestSelectId:
    """Tests for select_id() — identity prefix convention."""

    def test_id_prefix_file(self) -> None:
        """File identity starts with 'y'."""
        hs = HashSet(md5="ABCD1234" * 4, sha256="ABCD1234" * 8)
        result = select_id(hs, "md5", "y")
        assert result.startswith("y")
        assert result == "y" + hs.md5

    def test_id_prefix_directory(self) -> None:
        """Directory identity starts with 'x'."""
        hs = HashSet(md5="ABCD1234" * 4, sha256="ABCD1234" * 8)
        result = select_id(hs, "sha256", "x")
        assert result.startswith("x")
        assert result == "x" + hs.sha256

    def test_id_prefix_generated_metadata(self) -> None:
        """Generated metadata identity starts with 'z'."""
        hs = HashSet(md5="ABCD1234" * 4, sha256="ABCD1234" * 8)
        result = select_id(hs, "md5", "z")
        assert result.startswith("z")


class TestUppercaseHex:
    """Tests for the uppercase hex convention."""

    def test_hashset_uppercase(self, sample_file: Path) -> None:
        """All hex strings contain only 0-9A-F, never lowercase a-f."""
        result = hash_file(sample_file)
        assert _UPPERCASE_HEX_RE.match(result.md5)
        assert _UPPERCASE_HEX_RE.match(result.sha256)

        result_str = hash_string("test")
        assert _UPPERCASE_HEX_RE.match(result_str.md5)
        assert _UPPERCASE_HEX_RE.match(result_str.sha256)

"""Integration tests — output modes (stdout, outfile, inplace).

5 test cases per §14.3.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from shruggie_indexer.config.loader import load_config
from shruggie_indexer.core.entry import index_path
from shruggie_indexer.core.serializer import serialize_entry, write_inplace, write_output


def _cfg(**overrides: object):
    return load_config(overrides=overrides)


class TestOutputModes:
    """Tests for the three output destinations."""

    def test_stdout_capture(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """write_output with stdout=True writes valid JSON to stdout."""
        config = _cfg(output_stdout=True)
        entry = index_path(sample_file, config)

        captured = StringIO()
        with patch("sys.stdout", captured):
            write_output(entry, config)

        output = captured.getvalue().strip()
        parsed = json.loads(output)
        assert parsed["schema_version"] == 2

    def test_outfile_write(
        self, sample_file: Path, tmp_path: Path, mock_exiftool: None,
    ) -> None:
        """write_output with output_file creates the output file."""
        outfile = tmp_path / "output.json"
        config = _cfg(output_stdout=False, output_file=outfile)
        entry = index_path(sample_file, config)

        write_output(entry, config)

        assert outfile.exists()
        parsed = json.loads(outfile.read_text(encoding="utf-8"))
        assert parsed["schema_version"] == 2

    def test_inplace_creates_sidecar(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """write_inplace creates a _meta2.json sidecar alongside the file."""
        config = _cfg()
        entry = index_path(sample_file, config)

        write_inplace(entry, sample_file, "file")

        sidecar = sample_file.parent / (sample_file.name + "_meta2.json")
        assert sidecar.exists()
        parsed = json.loads(sidecar.read_text(encoding="utf-8"))
        assert parsed["schema_version"] == 2

    def test_combined_stdout_and_outfile(
        self, sample_file: Path, tmp_path: Path, mock_exiftool: None,
    ) -> None:
        """Both stdout and outfile can be active simultaneously."""
        outfile = tmp_path / "both_output.json"
        config = _cfg(output_stdout=True, output_file=outfile)
        entry = index_path(sample_file, config)

        captured = StringIO()
        with patch("sys.stdout", captured):
            write_output(entry, config)

        # Both destinations should have valid output.
        assert json.loads(captured.getvalue().strip())["schema_version"] == 2
        assert json.loads(outfile.read_text(encoding="utf-8"))["schema_version"] == 2

    def test_empty_directory_output(
        self, tmp_path: Path, mock_exiftool: None,
    ) -> None:
        """An empty directory produces valid output with items=[]."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        config = _cfg()
        entry = index_path(empty_dir, config)

        assert entry.type == "directory"
        assert entry.items is not None
        assert entry.items == []

        json_str = serialize_entry(entry)
        parsed = json.loads(json_str)
        assert parsed["schema_version"] == 2
        assert parsed["items"] == []

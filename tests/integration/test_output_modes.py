"""Integration tests — output modes (stdout, outfile, inplace).

5 + 6 test cases per §14.3.
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


class TestWriteDirectoryMetaFlag:
    """Tests for --no-dir-meta suppression of directory sidecars."""

    def test_dir_sidecar_suppressed_inplace(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """--no-dir-meta suppresses in-place _directorymeta2.json files."""
        from shruggie_indexer.cli.main import _write_inplace_tree

        config = _cfg(output_inplace=True, write_directory_meta=False)
        entry = index_path(sample_tree, config)

        _write_inplace_tree(
            entry, sample_tree, write_inplace,
            write_directory_meta=False,
        )

        # No _directorymeta2.json should exist anywhere
        dir_sidecars = list(sample_tree.rglob("*_directorymeta2.json"))
        assert dir_sidecars == [], f"Unexpected dir sidecars: {dir_sidecars}"

        # Per-file sidecars should exist
        file_sidecars = list(sample_tree.rglob("*_meta2.json"))
        assert len(file_sidecars) > 0

    def test_dir_sidecar_written_when_enabled(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """With write_directory_meta=True, dir sidecars are written."""
        from shruggie_indexer.cli.main import _write_inplace_tree

        config = _cfg(output_inplace=True, write_directory_meta=True)
        entry = index_path(sample_tree, config)

        _write_inplace_tree(
            entry, sample_tree, write_inplace,
            write_directory_meta=True,
        )

        # At least one _directorymeta2.json should exist (subdir)
        dir_sidecars = list(sample_tree.rglob("*_directorymeta2.json"))
        assert len(dir_sidecars) > 0

    def test_stdout_unaffected_by_no_dir_meta(
        self, sample_tree: Path, mock_exiftool: None,
    ) -> None:
        """Stdout output is NOT suppressed by --no-dir-meta."""
        config = _cfg(
            output_stdout=True,
            write_directory_meta=False,
        )
        entry = index_path(sample_tree, config)

        captured = StringIO()
        with patch("sys.stdout", captured):
            write_output(entry, config)

        output = captured.getvalue().strip()
        parsed = json.loads(output)
        assert parsed["schema_version"] == 2
        assert parsed["type"] == "directory"
        assert "items" in parsed

    def test_explicit_outfile_unaffected(
        self, sample_tree: Path, tmp_path: Path, mock_exiftool: None,
    ) -> None:
        """An explicit --outfile path is NOT suppressed by --no-dir-meta."""
        outfile = tmp_path / "custom_output.json"
        config = _cfg(
            output_stdout=False,
            output_file=outfile,
            write_directory_meta=False,
        )
        entry = index_path(sample_tree, config)

        write_output(entry, config)

        assert outfile.exists()
        parsed = json.loads(outfile.read_text(encoding="utf-8"))
        assert parsed["schema_version"] == 2

    def test_auto_generated_aggregate_suppressed(
        self, sample_tree: Path, tmp_path: Path, mock_exiftool: None,
    ) -> None:
        """Auto-generated _directorymeta2.json is suppressed by --no-dir-meta."""
        from dataclasses import replace as dc_replace

        auto_path = tmp_path / "sample_tree_directorymeta2.json"
        config = _cfg(
            output_stdout=False,
            output_file=auto_path,
            write_directory_meta=False,
        )
        entry = index_path(sample_tree, config)

        # Simulate the CLI gating logic
        if (
            not config.write_directory_meta
            and entry.type == "directory"
            and config.output_file is not None
            and str(config.output_file).endswith("_directorymeta2.json")
        ):
            config_for_write = dc_replace(config, output_file=None)
        else:
            config_for_write = config

        write_output(entry, config_for_write)

        assert not auto_path.exists()

    def test_single_file_target_unaffected(
        self, sample_file: Path, mock_exiftool: None,
    ) -> None:
        """--no-dir-meta has no effect on single-file targets."""
        config = _cfg(
            output_stdout=True,
            write_directory_meta=False,
        )
        entry = index_path(sample_file, config)

        captured = StringIO()
        with patch("sys.stdout", captured):
            write_output(entry, config)

        output = captured.getvalue().strip()
        parsed = json.loads(output)
        assert parsed["type"] == "file"
        assert parsed["schema_version"] == 2

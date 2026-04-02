from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from shruggie_indexer.core.cleanup import cleanup_legacy_outputs


def _file_entry(relative: str, storage_name: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="file",
        file_system=SimpleNamespace(relative=relative),
        attributes=SimpleNamespace(storage_name=storage_name),
        items=None,
    )


def _dir_entry(relative: str, items: list[SimpleNamespace] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        type="directory",
        file_system=SimpleNamespace(relative=relative),
        attributes=None,
        items=items or [],
    )


def test_cleanup_removes_only_matching_legacy_file_outputs(tmp_path: Path) -> None:
    current = tmp_path / "video.mp4_idx.json"
    current.write_text("{}", encoding="utf-8")

    stale_v1 = tmp_path / "video.mp4_meta.json"
    stale_v1.write_text("{}", encoding="utf-8")
    stale_v2 = tmp_path / "video.mp4_meta2.json"
    stale_v2.write_text("{}", encoding="utf-8")
    stale_v3 = tmp_path / "video.mp4_meta3.json"
    stale_v3.write_text("{}", encoding="utf-8")

    orphan = tmp_path / "other.mp4_meta3.json"
    orphan.write_text("{}", encoding="utf-8")

    removed = cleanup_legacy_outputs(
        _dir_entry(".", [_file_entry("video.mp4", "yVIDEO.mp4")]),
        tmp_path,
        write_directory_meta=True,
    )

    assert removed == 3
    assert current.exists()
    assert not stale_v1.exists()
    assert not stale_v2.exists()
    assert not stale_v3.exists()
    assert orphan.exists()


def test_cleanup_removes_matching_legacy_output_for_renamed_file(tmp_path: Path) -> None:
    current = tmp_path / "yABC123.jpg_idx.json"
    current.write_text("{}", encoding="utf-8")

    stale = tmp_path / "yABC123.jpg_meta3.json"
    stale.write_text("{}", encoding="utf-8")
    untouched = tmp_path / "photo.jpg_meta3.json"
    untouched.write_text("{}", encoding="utf-8")

    removed = cleanup_legacy_outputs(
        _dir_entry(".", [_file_entry("photo.jpg", "yABC123.jpg")]),
        tmp_path,
        write_directory_meta=True,
    )

    assert removed == 1
    assert current.exists()
    assert not stale.exists()
    assert untouched.exists()


def test_cleanup_removes_only_touched_directory_legacy_outputs(tmp_path: Path) -> None:
    current_dir = tmp_path / "album"
    current_dir.mkdir()
    current = current_dir / "album_idxd.json"
    current.write_text("{}", encoding="utf-8")

    stale = current_dir / "album_directorymeta3.json"
    stale.write_text("{}", encoding="utf-8")

    orphan_dir = tmp_path / "untouched"
    orphan_dir.mkdir()
    orphan = orphan_dir / "untouched_directorymeta3.json"
    orphan.write_text("{}", encoding="utf-8")

    removed = cleanup_legacy_outputs(
        _dir_entry(".", [_dir_entry("album")]),
        tmp_path,
        write_directory_meta=True,
    )

    assert removed == 1
    assert current.exists()
    assert not stale.exists()
    assert orphan.exists()
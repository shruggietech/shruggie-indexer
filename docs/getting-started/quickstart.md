# Quick Start

This guide walks through the most common shruggie-indexer operations. For the full CLI reference, see the [CLI Reference](../user-guide/cli-reference.md).

## Index a Single File

Point shruggie-indexer at any file to produce a JSON index entry on stdout:

```bash
shruggie-indexer path/to/file.jpg
```

The tool auto-detects whether the target is a file or directory. To force the interpretation, use `--file` or `--directory`.

## Index a Directory

Index a directory and all its contents recursively (the default):

```bash
shruggie-indexer path/to/directory/
```

Disable recursion to index only the directory's immediate children:

```bash
shruggie-indexer path/to/directory/ --no-recursive
```

## Save Output to a File

Write the combined JSON output to a file instead of stdout:

```bash
shruggie-indexer path/to/target --outfile index.json
```

The short form `-o` also works:

```bash
shruggie-indexer path/to/target -o index.json
```

## Write In-Place Sidecar Files

Write individual `_meta2.json` sidecar files alongside each indexed item:

```bash
shruggie-indexer path/to/directory/ --inplace
```

This creates a `filename_meta2.json` next to each file and a `_directorymeta2.json` inside each directory.

## Enable Metadata Extraction

Extract embedded EXIF/XMP/IPTC metadata via ExifTool:

```bash
shruggie-indexer path/to/file.jpg --meta
```

!!! note "ExifTool required"
    The `--meta` flag requires [ExifTool](exiftool.md) to be installed and on your `PATH`. If ExifTool is not found, a warning is logged and the `metadata` array simply omits the exiftool entry.

Merge sidecar metadata files into the parent entry's metadata array:

```bash
shruggie-indexer path/to/directory/ --meta-merge
```

Merge sidecar metadata and delete the original sidecar files after merging:

```bash
shruggie-indexer path/to/directory/ --meta-merge-delete --outfile index.json
```

!!! warning "Implication chain"
    `--meta-merge-delete` implies `--meta-merge`, which implies `--meta`. You do not need to specify all three. Additionally, `--meta-merge-delete` requires a persistent output destination (`--outfile` or `--inplace`).

## Rename Files to Storage Names

Rename files to their deterministic, hash-based `storage_name` values:

```bash
shruggie-indexer path/to/directory/ --rename --dry-run
```

The `--dry-run` flag previews the rename operations without modifying any files. Remove `--dry-run` to execute the renames:

```bash
shruggie-indexer path/to/directory/ --rename
```

!!! tip "Rename implies in-place"
    `--rename` automatically enables `--inplace` so that sidecar files are written alongside the renamed items, preserving the original filename in the index entry.

## Choose an ID Algorithm

By default, the `id` field uses MD5. To use SHA-256 instead:

```bash
shruggie-indexer path/to/file --id-type sha256
```

To include SHA-512 in the hash output (not used for `id`, but stored in the `hashes` object):

```bash
shruggie-indexer path/to/file --compute-sha512
```

## Example Output

Here is a representative JSON output for a single file (abbreviated):

```json
{
  "schema_version": 2,
  "id": "yA8A8C089A6A8583B24C85F5A4A41F5AC",
  "id_algorithm": "md5",
  "type": "file",
  "name": {
    "text": "flashplayer.exe",
    "hashes": {
      "md5": "3470F718BA9457335A59CE06239A9250",
      "sha256": "4DC834B31A1A5967F7A97AAD3D62EE91CCCC99B2034748135AFC193889B9A0EB"
    }
  },
  "extension": "exe",
  "mime_type": "application/octet-stream",
  "size": { "text": "15.28 MB", "bytes": 16027648 },
  "hashes": {
    "md5": "A8A8C089A6A8583B24C85F5A4A41F5AC",
    "sha256": "B6BA115C2B43D87AADDF0060C44726E7AF1A12C9501FC63DE652A9517D7367DB"
  },
  "file_system": {
    "relative": ".test/flashplayer.exe",
    "parent": {
      "id": "x3B4F479E9F880E438882FC34B67D352C",
      "name": {
        "text": ".test",
        "hashes": { "md5": "5E7576E3CD79114D46850714E998A3B0", "sha256": "..." }
      }
    }
  },
  "timestamps": {
    "created":  { "iso": "2026-02-15T09:28:17.408462-05:00", "unix": 1771165697408 },
    "modified": { "iso": "2023-08-03T19:47:44.000000-04:00", "unix": 1691106464000 },
    "accessed": { "iso": "2026-02-15T09:28:18.109390-05:00", "unix": 1771165698109 }
  },
  "attributes": {
    "is_link": false,
    "storage_name": "yA8A8C089A6A8583B24C85F5A4A41F5AC.exe"
  },
  "items": null,
  "metadata": null
}
```

## Next Steps

- [CLI Reference](../user-guide/cli-reference.md) — Complete flag documentation, output scenarios, and exit codes.
- [Configuration](../user-guide/configuration.md) — TOML config files, default values, and override behavior.
- [Schema Reference](../schema/index.md) — Full v2 schema documentation with field tables.

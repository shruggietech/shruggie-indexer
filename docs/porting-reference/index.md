# Porting Reference

!!! info "Historical Reference"
    This section contains archival reference materials from the original PowerShell implementation. These documents were used during development and are preserved for traceability. They are not part of the runtime codebase and do not affect shruggie-indexer's behavior.

## Operations Catalog

- [MakeIndex Operations Catalog](MakeIndex_OperationsCatalog.md) — Categorized inventory of all logical operations in the original `MakeIndex` and its dependency tree, mapped to recommended Python modules.

## Configuration Reference

- [MetadataFileParser Object](MakeIndex%28MetadataFileParser%29.ps1) — Isolated PowerShell script containing the complete `$global:MetadataFileParser` object definition. Source of truth for sidecar metadata file discovery and classification patterns.

## Dependency Catalogs

Each catalog documents a single function from the original pslib library that `MakeIndex` depends on — its parameters, internal sub-functions, external calls, and behavioral contract.

| Function | Catalog | Status in Port |
|----------|---------|----------------|
| MakeIndex | [MakeIndex_DependencyCatalog.md](MakeIndex_DependencyCatalog.md) | Top-level function being ported. |
| Base64DecodeString | [Base64DecodeString_DependencyCatalog.md](Base64DecodeString_DependencyCatalog.md) | Eliminated — exiftool arguments passed directly. |
| Date2UnixTime | [Date2UnixTime_DependencyCatalog.md](Date2UnixTime_DependencyCatalog.md) | Eliminated — timestamps derived from stat results. |
| DirectoryId | [DirectoryId_DependencyCatalog.md](DirectoryId_DependencyCatalog.md) | Ported to `core/hashing.py`. |
| FileId | [FileId_DependencyCatalog.md](FileId_DependencyCatalog.md) | Ported to `core/hashing.py`. |
| MetaFileRead | [MetaFileRead_DependencyCatalog.md](MetaFileRead_DependencyCatalog.md) | Ported to `core/sidecar.py`. |
| TempOpen | [TempOpen_DependencyCatalog.md](TempOpen_DependencyCatalog.md) | Eliminated — replaced by `tempfile`. |
| TempClose | [TempClose_DependencyCatalog.md](TempClose_DependencyCatalog.md) | Eliminated — replaced by context manager cleanup. |
| Vbs | [Vbs_DependencyCatalog.md](Vbs_DependencyCatalog.md) | Replaced by Python `logging` framework. |

## V1 Output Schema

- [MakeIndex_OutputSchema.json](MakeIndex_OutputSchema.json) — The original v1 output schema definition. Retained as a porting reference only — the port targets the v2 schema.

## V1 Output Examples

The [v1-examples/](v1-examples/) directory contains real-world output files from the original `MakeIndex` function:

- [apktool.jar_meta.json](v1-examples/apktool.jar_meta.json)
- [exiftool.exe_meta.json](v1-examples/exiftool.exe_meta.json)
- [flashplayer.exe_meta.json](v1-examples/flashplayer.exe_meta.json)
- [SearchMyFiles.chm_meta.json](v1-examples/SearchMyFiles.chm_meta.json)

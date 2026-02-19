# shruggie-indexer

A Python reimplementation of the `MakeIndex` function from the original PowerShell-based pslib library. `shruggie-indexer` produces structured JSON index entries for files and directories — capturing identity hashes, timestamps, EXIF metadata, sidecar metadata, and filesystem attributes in the [v2 schema](schema/shruggie-indexer-v2.schema.json) format.

## Documentation Sections

- **[Schema Reference](schema/index.md)** — Canonical v2 JSON Schema definition, type descriptions, and validation examples.
- **[Porting Reference](porting-reference/index.md)** — Reference materials from the original PowerShell implementation: dependency catalogs, operations catalog, v1 schema, and the MetadataFileParser configuration object.
- **[User Guide](user/index.md)** — Installation, quick start, configuration reference, and changelog.

## Quick Links

- [GitHub Repository](https://github.com/shruggietech/shruggie-indexer)
- [Technical Specification](https://github.com/shruggietech/shruggie-indexer/blob/main/shruggie-indexer-spec.md)
- [V2 JSON Schema (canonical)](https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json)

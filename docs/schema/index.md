# Schema Reference

The v2 output schema defines the structure of index entries produced by `shruggie-indexer`. It is a ground-up restructuring of the original MakeIndex v1 output format — consolidating related fields into logical sub-objects, eliminating redundancies, and adding a `schema_version` discriminator for forward compatibility.

## Canonical Schema

The authoritative schema definition is hosted at:

- **Canonical URL:** [schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json](https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json)
- **Local copy:** [shruggie-indexer-v2.schema.json](shruggie-indexer-v2.schema.json)

The local copy is committed to the repository and kept in sync with the canonical hosted version.

## Schema Types

The v2 schema defines the following reusable type definitions:

| Type | Description |
|------|-------------|
| `IndexEntry` | Top-level object representing a single indexed file or directory. |
| `NameObject` | Original and storage name fields for a filesystem item. |
| `HashSet` | MD5, SHA1, SHA256, and SHA512 hashes computed from a single source. |
| `SizeObject` | File size in bytes and human-readable form. |
| `TimestampPair` | Unix timestamp (milliseconds) paired with an ISO 8601 string. |
| `TimestampsObject` | Accessed, created, and modified timestamp pairs. |
| `ParentObject` | Identity and name of the parent directory. |
| `MetadataEntry` | A single sidecar metadata file's parsed content and attributes. |

## Validation Examples

The [examples/](examples/) directory contains real-world v2-compliant output files that demonstrate the schema in practice:

- [flashplayer.exe_meta2.json](examples/flashplayer.exe_meta2.json)

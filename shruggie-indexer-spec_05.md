## 5. Output Schema

This section defines the complete v2 output schema for `shruggie-indexer` — the structure, field definitions, type constraints, nullability rules, and behavioral guidance for every field in an `IndexEntry`. The canonical machine-readable schema is the JSON Schema document at [schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json](https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json). This section interprets and extends that schema with implementation guidance, v1-to-v2 mapping context, and behavioral notes that a JSON Schema cannot express — but does not supersede the canonical schema for structural or type-level definitions. Where a conflict exists between this section and the canonical schema, the canonical schema governs field names, types, and `required` constraints; this section governs behavioral semantics and implementation strategy.

The v2 schema is a ground-up restructuring of the original MakeIndex v1 output format (`MakeIndex_OutputSchema.json`). The port targets v2 exclusively. It does not produce v1 output. A v1-to-v2 migration utility for converting existing v1 index assets is a planned post-MVP deliverable (see §1.2, Out of Scope).

### 5.1. Schema Overview

#### Design principles

The v2 schema is governed by five design principles that drove the restructuring from v1.

**P1 — Logical grouping.** Related fields are consolidated into typed sub-objects rather than scattered across the top level. In v1, a file's name and its name hashes are separate top-level keys (`Name`, `NameHashes`); in v2, they are a single `NameObject` with `text` and `hashes` properties. The same consolidation applies to timestamps (`TimestampPair` pairs an ISO string with a Unix integer), sizes (`SizeObject` pairs a human-readable string with a byte count), and parent relationships (`ParentObject` groups the parent's ID and name). This eliminates the implicit coupling between field pairs that existed in v1 and makes the schema self-documenting: every sub-object is a complete, independently meaningful unit.

**P2 — Single discriminator for item type.** v1 uses a dual-boolean pattern (`IsDirectory: true/false` and an implied file/directory distinction from field presence) that is ambiguous in edge cases and requires consumers to perform boolean logic. v2 replaces this with a single `type` enum (`"file"` or `"directory"`). Combined with the `schema_version` discriminator (absent in v1), consumers can route parsing logic unambiguously from the first two fields of any entry.

**P3 — Provenance tracking for metadata entries.** v1's `Metadata` array entries carry `Source`, `Type`, `Name`, `NameHashes`, and `Data` — enough to describe the metadata content but not enough to reconstruct the original sidecar file that the content came from. v2's `MetadataEntry` adds `origin` (generated vs. sidecar), `file_system` (relative path of the original sidecar file), `size`, `timestamps`, and an `attributes` sub-object (type classification, format, transforms). This makes the `metadata` array a complete manifest for MetaMergeDelete reversal: every sidecar entry carries enough information to reconstruct the original file on disk.

**P4 — Elimination of redundancy and platform coupling.** v1 includes fields that are structurally redundant (`BaseName` duplicates the stem of `Name`, `Ids` and `ContentHashes` carry overlapping hash values for files), platform-specific (`Encoding` is a .NET `System.Text.Encoding` serialization), or algorithmically redundant (`SHA1` is carried alongside MD5 and SHA256 despite serving no unique purpose in the identity scheme). v2 drops these fields and normalizes what remains. See §5.11 for the full inventory.

**P5 — Explicit algorithm selection.** v1's `_id` field is derived from one of the hash algorithms (MD5 or SHA256) but the schema does not record which algorithm was used — consumers must reverse-match the `_id` value against the `Ids` object to determine the algorithm. v2 adds `id_algorithm` as an explicit top-level field, making the identity derivation fully self-describing.

#### Canonical schema location

The canonical v2 JSON Schema is hosted at:

```
https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json
```

This document uses JSON Schema Draft-07 (`https://json-schema.org/draft-07/schema#`). The schema `$id` is set to the canonical URL. The schema `title` is `IndexEntry`.

#### Schema version

Every v2 output document includes a `schema_version` field with the integer value `2`. This field is the first property in the serialized JSON output (by convention, not by requirement — JSON objects are unordered, but the serializer SHOULD place `schema_version` first for readability). The value is a `const` constraint in the JSON Schema: `{ "type": "integer", "const": 2 }`. Consumers SHOULD check this field before attempting to parse the remainder of the document and SHOULD reject documents with an unrecognized schema version.

The v1 schema has no version discriminator. The absence of a `schema_version` field (or the presence of the v1-specific `_id` field with its `y`/`x` prefix) is sufficient to identify a v1 document, but consumers SHOULD NOT rely on field absence for version detection — the eventual v1-to-v2 migration utility will handle schema identification as part of its conversion logic.

### 5.2. Reusable Type Definitions

The v2 schema defines six reusable type definitions in the `definitions` block of the JSON Schema. These are the building blocks from which the top-level `IndexEntry` properties and the nested `MetadataEntry` objects are composed. Each definition is referenced via `$ref` wherever it appears.

The Python implementation SHOULD model these definitions as individual `dataclass` types (or Pydantic models behind an import guard) in `models/schema.py`. This mirrors the schema's compositional structure and gives every sub-object a named type for static analysis, IDE support, and independent testability. See §3.2 for the module location rationale.

#### 5.2.1. HashSet

A `HashSet` is a collection of cryptographic hash digests for a given input. All hash values are uppercase hexadecimal strings (characters `0–9`, `A–F`).

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `md5` | `string` | Yes | MD5 digest. 32 hex characters. Pattern: `^[0-9A-F]{32}$`. |
| `sha256` | `string` | Yes | SHA-256 digest. 64 hex characters. Pattern: `^[0-9A-F]{64}$`. |
| `sha512` | `string` | No | SHA-512 digest. 128 hex characters. Pattern: `^[0-9A-F]{128}$`. Included when configured or when additional verification strength is warranted. |

`additionalProperties` is `false` — no extra keys are permitted.

**v1 comparison:** v1 defines hash fields as separate top-level objects (`Ids`, `NameHashes`, `ContentHashes`, `ParentIds`, `ParentNameHashes`) each with their own `MD5`, `SHA1`, `SHA256`, `SHA512` properties. v2 replaces all of these with `HashSet` references.

**SHA1 removal:** v1 includes `SHA1` as a required field in most hash objects. v2 drops SHA1 entirely. SHA1 served no unique purpose in the identity scheme (it is not used for `_id` derivation) and adds computational overhead for each hashed input. MD5 provides the legacy default identity algorithm; SHA256 provides the cryptographically strong alternative; SHA512 provides an optional high-strength digest. SHA1 occupies an awkward middle ground where it is neither the fastest, the strongest, nor the default. See §5.11 for the full drop rationale.

**Uppercase convention:** All hex strings are uppercase. The original uses uppercase hex throughout (`FileId` and `DirectoryId` both call `.ToUpper()` on their output). The port preserves this convention via `hashlib.hexdigest().upper()`.

> **Implementation note:** The Python `HashSet` dataclass SHOULD have `sha512` as an `Optional[str]` field defaulting to `None`. The serialization helper MUST omit the `sha512` key entirely from the JSON output when its value is `None`, rather than emitting `"sha512": null`. This matches the JSON Schema's `required` constraint (only `md5` and `sha256` are required) and avoids bloating the output with null optional fields.

#### 5.2.2. NameObject

A `NameObject` pairs a text string with its associated hash digests. Used for file names, directory names, parent directory names, and metadata sidecar file names.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `text` | `string` or `null` | Yes | The text value of the name. Includes the extension for files. Null when the named entity has no meaningful name (e.g., generated metadata entries). |
| `hashes` | `HashSet` or `null` | Yes | Hash digests of the UTF-8 byte representation of the `text` string. Null when `text` is null. |

The `text` and `hashes` fields have a co-nullability invariant: when `text` is `null`, `hashes` MUST also be `null`. When `text` is a non-empty string, `hashes` MUST be a populated `HashSet`. The implementation SHOULD enforce this invariant at construction time.

**v1 comparison:** v1 uses separate top-level field pairs — `Name` / `NameHashes`, `ParentName` / `ParentNameHashes` — where the relationship between the text and its hashes is implicit. v2's `NameObject` makes the relationship explicit and eliminates the possibility of a name being present without its hashes or vice versa.

**Hash input encoding:** The hashes in a `NameObject` are computed from the UTF-8 encoded bytes of the `text` string. This matches the original's behavior (PowerShell's `[System.Text.Encoding]::UTF8.GetBytes($Name)` produces UTF-8 bytes) and is the natural encoding for Python's `hashlib` when given `name.encode('utf-8')`.

#### 5.2.3. SizeObject

A `SizeObject` expresses a file size in both human-readable and machine-readable forms.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `text` | `string` | Yes | Human-readable size string with appropriate unit suffix (e.g., `"15.28 MB"`, `"135 B"`, `"2.04 GB"`). Units follow the decimal SI convention: B, KB, MB, GB, TB. |
| `bytes` | `integer` | Yes | Exact size in bytes. Minimum value: `0`. |

`additionalProperties` is `false`.

**v1 comparison:** v1 has a single `Size` field of type `number` (bytes only). v2 adds the human-readable string for consumer convenience. The `bytes` field preserves the exact integer value for programmatic use.

**Human-readable formatting rules:** The `text` string SHOULD use two decimal places for values ≥ 1 KB and no decimal places for values in bytes. The unit thresholds are: < 1,000 B → `"N B"`, < 1,000,000 B → `"N.NN KB"`, < 1,000,000,000 B → `"N.NN MB"`, < 1,000,000,000,000 B → `"N.NN GB"`, otherwise `"N.NN TB"`. These thresholds use decimal SI (powers of 1,000), not binary (powers of 1,024). A 1,048,576-byte file is reported as `"1.05 MB"`, not `"1.00 MiB"`.

> **New in v2.** This type has no v1 equivalent. The original stores only a raw byte count.

#### 5.2.4. TimestampPair

A `TimestampPair` expresses a single timestamp in both ISO 8601 local-time and Unix epoch millisecond formats.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `iso` | `string` | Yes | ISO 8601 timestamp with fractional seconds and timezone offset. Format: `yyyy-MM-ddTHH:mm:ss.fffffffzzz` (up to 7 fractional digits; Python implementations will typically produce 6). |
| `unix` | `integer` | Yes | Unix timestamp in milliseconds since epoch (`1970-01-01T00:00:00Z`). Integer precision. Timezone-independent. |

`additionalProperties` is `false`.

**v1 comparison:** v1 uses separate top-level field pairs — `TimeAccessed` / `UnixTimeAccessed`, `TimeCreated` / `UnixTimeCreated`, `TimeModified` / `UnixTimeModified`. v2's `TimestampPair` consolidates each pair into a single object and nests them inside a `TimestampsObject` (see §5.2.5).

**Fractional seconds precision:** The original's `.ToString($DateFormat)` uses the `fffffff` format specifier, which produces 7 fractional digits (100-nanosecond precision, the resolution of .NET's `DateTime` type). Python's `datetime.isoformat()` produces 6 fractional digits by default (microsecond precision). This is an acceptable deviation — the 7th digit is almost always `0` in practice because filesystem timestamps rarely carry sub-microsecond precision. The ISO string format SHOULD include all available fractional digits without artificial truncation or zero-padding to a specific width. See §6.5 for the timestamp derivation logic and §14.5 for cross-platform precision considerations.

**Millisecond Unix timestamps:** The `unix` value is in milliseconds, not seconds. This matches the original's `[DateTimeOffset]::ToUnixTimeMilliseconds()` and is computed in the port as `int(stat_result.st_mtime * 1000)`. See DEV-07 in §2.6.

#### 5.2.5. TimestampsObject

A `TimestampsObject` groups the three standard filesystem timestamps.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `created` | `TimestampPair` | Yes | When the item was created on the filesystem. |
| `modified` | `TimestampPair` | Yes | When the item's content was last modified. |
| `accessed` | `TimestampPair` | Yes | When the item was last accessed (read). See platform caveat below. |

`additionalProperties` is `false`.

**Access time caveat:** Filesystem access-time tracking varies by OS and mount options. Linux systems mounted with `noatime` or `relatime` (the default on most distributions) may report stale or approximate access times. The indexer reports whatever the filesystem provides via `os.stat()` without attempting to validate accuracy. Consumers SHOULD NOT rely on `accessed` timestamps for precise behavioral analysis.

**Creation time portability:** On Windows, `os.stat().st_birthtime` (Python 3.12+) or `st_ctime` provides the file creation time. On Linux, `st_birthtime` is available on Python 3.12+ for filesystems that support it (ext4 with kernel 4.11+); on older kernels or unsupported filesystems, it is unavailable. On macOS, `st_birthtime` is generally available. When creation time is not available, the implementation MUST fall back to `st_ctime` (which on Linux represents the inode change time, not the creation time) and SHOULD log a diagnostic message on the first occurrence per invocation. See §14.5 for the full cross-platform discussion.

#### 5.2.6. ParentObject

A `ParentObject` provides identity and naming information for the parent directory of an indexed item.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | `string` | Yes | The unique identifier of the parent directory. Uses the `x` prefix (directory ID namespace). Pattern: `^x[0-9A-F]+$`. |
| `name` | `NameObject` | Yes | The name of the parent directory. |

`additionalProperties` is `false`.

The parent `id` is computed using the same two-layer directory hashing scheme as directory entries themselves: `hash(hash(parent_name) + hash(grandparent_name))`, prefixed with `x`. For items at the root of the indexed tree, the parent directory exists on the filesystem (it is the target directory's own parent) but will not have its own `IndexEntry` in the output. The parent ID is still computed and populated.

**v1 comparison:** v1 spreads parent identity across four top-level fields — `ParentId`, `ParentIds`, `ParentName`, `ParentNameHashes`. v2 collapses these into a single `ParentObject` with two properties. The v1 `ParentId` (a single string selected from `ParentIds` by the chosen algorithm) maps to v2's `parent.id`. The v1 `ParentIds` (the full hash set) is not directly carried into `ParentObject` — the parent's `name.hashes` provides the name hashes, and the parent's full identity hash set can be recomputed from those if needed. This is a deliberate simplification: carrying the full `ParentIds` hash set was redundant given that the parent ID's derivation from name hashes is deterministic and documented.

> **Deviation from v1 field cardinality:** v1's `ParentIds` provides the parent's full hash-based ID set (MD5, SHA256, optionally SHA1 and SHA512) as a separate object. v2 provides only the single selected `parent.id` string and the parent's `name` (with its name hashes). If a consumer needs the parent's alternative algorithm ID, they can recompute it from the parent name hashes using the documented directory ID scheme. This reduces per-entry size and eliminates a field whose values were derivable from other present fields.

### 5.3. Top-Level IndexEntry Fields

An `IndexEntry` is a JSON object conforming to the root schema. It describes a single indexed file or directory. The following table lists all top-level properties in the order they appear in the canonical schema. Detailed behavioral guidance for each field follows in §5.4 through §5.10.

| Property | Type | Required | Section |
|----------|------|----------|---------|
| `schema_version` | `integer` (const `2`) | Yes | §5.4 |
| `id` | `string` | Yes | §5.4 |
| `id_algorithm` | `string` (enum) | Yes | §5.4 |
| `type` | `string` (enum) | Yes | §5.4 |
| `name` | `NameObject` | Yes | §5.5 |
| `extension` | `string` or `null` | Yes | §5.5 |
| `mime_type` | `string` or `null` | No | §5.5 |
| `size` | `SizeObject` | Yes | §5.5 |
| `hashes` | `HashSet` or `null` | Yes | §5.5 |
| `file_system` | `object` | Yes | §5.6 |
| `timestamps` | `TimestampsObject` | Yes | §5.7 |
| `attributes` | `object` | Yes | §5.8 |
| `items` | `array` of `IndexEntry` or `null` | No | §5.9 |
| `metadata` | `array` of `MetadataEntry` or `null` | No | §5.10 |

`additionalProperties` is `false` at the root level — no extra keys are permitted. The `required` array in the canonical schema is:

```json
[
  "schema_version", "id", "id_algorithm", "type", "name",
  "extension", "size", "hashes", "file_system", "timestamps", "attributes"
]
```

The `items` and `metadata` fields are not in the `required` array. They MAY be omitted entirely (not just set to `null`) when not applicable. However, the implementation SHOULD include them with explicit `null` values for consistency — an `IndexEntry` for a file emits `"items": null`, `"metadata": null` rather than omitting the keys. This makes every entry structurally uniform, which simplifies consumer parsing. The `mime_type` field is also not required and follows the same convention.

### 5.4. Identity Fields

These fields establish the item's unique identity and schema context.

#### `schema_version`

| Attribute | Value |
|-----------|-------|
| Type | `integer` |
| Constraint | `const: 2` |
| Required | Yes |
| v1 equivalent | None (v1 has no version discriminator) |

Always the integer `2`. The serializer SHOULD place this field first in the serialized JSON output for readability, though JSON objects are unordered and consumers MUST NOT depend on field order.

#### `id`

| Attribute | Value |
|-----------|-------|
| Type | `string` |
| Pattern | `^[xy][0-9A-F]+$` |
| Required | Yes |
| v1 equivalent | `_id` |

The primary unique identifier for the indexed item. The first character is a type prefix that encodes the item's namespace:

- `y` — File. The hash portion is derived from the file's content bytes (or from the file's name string if the file is a symbolic link).
- `x` — Directory. The hash portion is derived from the two-layer name hashing scheme: `hash(hash(directory_name) + hash(parent_directory_name))`.

The remaining characters are the uppercase hexadecimal hash digest selected by `id_algorithm`. For the default `id_algorithm` of `md5`, a file ID is 33 characters total (1 prefix + 32 hex). For `sha256`, it is 65 characters (1 prefix + 64 hex).

**v1 comparison:** Identical semantics. The field name changes from `_id` to `id` (the leading underscore was a legacy convention from the original's MongoDB-influenced naming). The `z` prefix used for generated metadata entry IDs appears in `MetadataEntry.id` (§5.10), not at the `IndexEntry` top level.

**Derivation details:** The hash computation and prefix application logic are defined in §6.3. The `id` value MUST be one of the hash digests present in the `hashes` field (for files) or derivable from the `name.hashes` field (for directories). The `id_algorithm` field identifies which one.

#### `id_algorithm`

| Attribute | Value |
|-----------|-------|
| Type | `string` |
| Enum | `["md5", "sha256"]` |
| Required | Yes |
| v1 equivalent | None (implicit in v1) |

The hash algorithm used to generate the `id` field. The value is always lowercase. The default is `"md5"`, matching the original's default behavior. The `"sha256"` option exists for workflows that require cryptographically stronger identifiers.

This field determines:

- Which digest from the `hashes` `HashSet` is used as the basis for `id`.
- Which digest is used to construct `attributes.storage_name`.
- Which digest is used for `file_system.parent.id` (the parent directory ID is always computed with the same algorithm as the child's ID).

> **New in v2.** v1 provides no mechanism to determine which algorithm produced the `_id` value. Consumers must reverse-match `_id` against the `Ids` object. v2 makes this explicit.

#### `type`

| Attribute | Value |
|-----------|-------|
| Type | `string` |
| Enum | `["file", "directory"]` |
| Required | Yes |
| v1 equivalent | `IsDirectory` (boolean) |

The fundamental filesystem type of the indexed item. This is the primary structural discriminator — it determines which other fields are populated vs. null, whether `items` is meaningful, and how `hashes` should be interpreted.

| `type` value | `hashes` | `extension` | `items` | `metadata` |
|-------------|----------|-------------|---------|------------|
| `"file"` | Content hash `HashSet` (or name hash if symlink) | File extension string | `null` | Array of `MetadataEntry` or `null` |
| `"directory"` | `null` | `null` | Array of child `IndexEntry` or `null` | `null` |

**v1 comparison:** v1 uses `IsDirectory: true/false`. v2 replaces this with a string enum for three reasons. First, it eliminates the implicit "IsFile" concept (v1 has no explicit `IsFile` field — it is inferred from `IsDirectory: false`). Second, it avoids the boolean ambiguity where `false` carries semantic meaning that must be negated to interpret ("not a directory" → "a file"). Third, string enums are extensible if future schema versions need to add item types (e.g., `"symlink"` as a distinct type rather than a flag).

### 5.5. Naming and Content Fields

These fields describe the item's name, extension, content type, size, and content hashes.

#### `name`

| Attribute | Value |
|-----------|-------|
| Type | `NameObject` |
| Required | Yes |
| v1 equivalent | `Name` + `NameHashes` |

The name of the indexed item. For files, `name.text` includes the extension (e.g., `"report.pdf"`). For directories, `name.text` is the directory name (e.g., `"photos"`). Does not include any path components.

The `name.hashes` field contains the hash digests of the UTF-8 encoded bytes of `name.text`. These name hashes are used in directory identity computation (see §6.3) and are included for both files and directories.

**v1 comparison:** v1's `Name` (a plain string) and `NameHashes` (a hash object) are consolidated into a single `NameObject`. v1's `BaseName` (the filename without extension) is dropped — see §5.11.

#### `extension`

| Attribute | Value |
|-----------|-------|
| Type | `string` or `null` |
| Required | Yes |
| v1 equivalent | `Extension` |

The file extension without the leading period (e.g., `"exe"`, `"json"`, `"tar.gz"`). Null for directories. Also null for files that have no extension.

The extension value is derived from the filesystem name. For multi-part extensions like `.tar.gz`, the implementation SHOULD use the full compound extension. Extension validation is governed by the configurable pattern described in §7 (default: the regex from the original, externalized per DEV-14 in §2.6). Extensions that fail validation are still recorded in this field — validation failures affect only whether the extension is considered "recognized" for purposes like exiftool processing, not whether it is stored.

The extension is stored in lowercase. The original's `MakeObject` converts extensions to lowercase before storage; the port preserves this behavior.

#### `mime_type`

| Attribute | Value |
|-----------|-------|
| Type | `string` or `null` |
| Required | No |
| v1 equivalent | None |

The MIME type of the file as detected by the indexer (e.g., `"application/octet-stream"`, `"text/plain"`, `"image/png"`). Null for directories.

Detection is based on the file extension using Python's `mimetypes.guess_type()` from the standard library. If `exiftool` is available and returns a `MIMEType` field, the exiftool-reported MIME type takes precedence over the extension-based guess when the two disagree. If neither method produces a result, the field is set to `null`.

> **New in v2.** This field has no v1 equivalent. The original does not perform MIME type detection. This is a low-cost addition that provides significant utility for downstream consumers who need to filter or route index entries by content type.

#### `size`

| Attribute | Value |
|-----------|-------|
| Type | `SizeObject` |
| Required | Yes |
| v1 equivalent | `Size` (number, bytes only) |

The size of the item. For files, `size.bytes` is the file size as reported by `os.stat().st_size`. For directories, `size.bytes` is the total combined size of all contained files and subdirectories — computed as the sum of all child `size.bytes` values during the traversal loop (see §4.3, step 4j). The `size.text` field provides the human-readable representation per the formatting rules in §5.2.3.

**v1 comparison:** v1's `Size` is a bare `number` (bytes only). v2 wraps it in a `SizeObject` that adds the human-readable `text` field.

#### `hashes`

| Attribute | Value |
|-----------|-------|
| Type | `HashSet` or `null` |
| Required | Yes |
| v1 equivalent | `ContentHashes` (partially; see below) |

Hash digests of the item's content.

For **files**: the `HashSet` contains digests computed over the file's byte content in a single streaming pass (see §6.3 and §16.1). If the file is a symbolic link, the hashes are computed over the UTF-8 encoded bytes of the file's name string instead, ensuring deterministic IDs without requiring the link target to be accessible.

For **directories**: `null`. Directory identity is derived from name hashing (the two-layer scheme), not content hashing. The directory's name hashes are in `name.hashes`.

**v1 comparison:** v1 has two separate hash objects — `Ids` (which for files contains content-derived values and for directories contains name-derived values) and `ContentHashes` (which for files duplicates `Ids` and for directories is `null`). v2 eliminates this redundancy. The `hashes` field corresponds to content hashes only; name hashes live in `name.hashes`. For files, `hashes` is the single source of content hash digests. For directories, `hashes` is `null` and identity derivation uses `name.hashes`.

> **Deviation from v1 `Ids` semantics:** v1's `Ids` object serves double duty — it is both "the hashes used for identity derivation" and "the content/name hashes." v2 separates these concepts. The `id` field is the identity. The `hashes` field is the content hashes (files only). The `name.hashes` field is the name hashes (both files and directories). The `id` value is derived from one of these hash sets depending on the item type, as documented by `id_algorithm`. This separation is clearer and eliminates the confusion of having an `Ids` object that means different things for files vs. directories.

### 5.6. Filesystem Location and Hierarchy Fields

The `file_system` top-level property groups filesystem location and hierarchy information.

#### `file_system`

| Attribute | Value |
|-----------|-------|
| Type | `object` |
| Required | Yes |
| v1 equivalent | Partially: `ParentId` + `ParentIds` + `ParentName` + `ParentNameHashes` |

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `relative` | `string` | Yes | The relative path from the index root to this item. Uses forward-slash separators regardless of the source platform. |
| `parent` | `ParentObject` or `null` | Yes | Identity and naming information for this item's parent directory. |

`additionalProperties` is `false`.

**`file_system.relative`** is the relative path from the root of the index operation to the current item. For the root item itself (the target of the indexing invocation), this is `"."`. For a file `photos/vacation/beach.jpg` within a directory being indexed recursively, the relative path is `"photos/vacation/beach.jpg"`. Path separators are always forward slashes, even when the indexer runs on Windows. This ensures that index output is portable across platforms.

> **New in v2.** v1 has no relative path field. The original's output embeds items in a recursive tree structure but does not record the relative path for any individual entry. The relative path is new in v2 and provides significant utility for consumers who need to locate or reconstruct the filesystem layout from a flat iteration of the entry tree.

**`file_system.parent`** is a `ParentObject` (§5.2.6) containing the parent directory's computed ID and name. Null for the root item of a single-file index operation where the parent directory's identity is not meaningful. For all other items — including the root item of a directory index operation — the parent is populated.

**v1 comparison:** v1's `ParentId`, `ParentIds`, `ParentName`, and `ParentNameHashes` are consolidated into `file_system.parent`. The v1 `ParentId` value of `"x"` (used when the item is at the root of the system) is not preserved — `parent` is `null` in that scenario instead. See §5.2.6 for the `ParentObject` field mapping.

### 5.7. Timestamp Fields

#### `timestamps`

| Attribute | Value |
|-----------|-------|
| Type | `TimestampsObject` |
| Required | Yes |
| v1 equivalent | `TimeAccessed` + `UnixTimeAccessed` + `TimeCreated` + `UnixTimeCreated` + `TimeModified` + `UnixTimeModified` |

The three standard filesystem timestamps, each as a `TimestampPair` (§5.2.4) providing both ISO 8601 and Unix millisecond representations.

**v1 comparison:** v1 uses six separate top-level fields for three timestamps (two formats each). v2 nests them in a single `TimestampsObject` containing three `TimestampPair` values. The semantic content is identical; the structural organization is consolidated.

**Derivation:** All timestamps are derived from `os.stat()` / `os.lstat()` results. The ISO string is produced from a `datetime` object constructed from the stat float, with the local timezone offset attached. The Unix millisecond integer is computed directly from the stat float. See §6.5 for implementation details and §14.5 for cross-platform behavior.

### 5.8. Attribute Fields

#### `attributes`

| Attribute | Value |
|-----------|-------|
| Type | `object` |
| Required | Yes |
| v1 equivalent | `IsLink` + `StorageName` |

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `is_link` | `boolean` | Yes | Whether the item is a symbolic link (symlink). |
| `storage_name` | `string` | Yes | The deterministic name for renamed/storage mode. |

`additionalProperties` is `false`.

**`attributes.is_link`** is `true` when the item is a symbolic link, `false` otherwise. When `true`, the item's `hashes` are computed from the file name string rather than the file content (for files) or the hashing falls back to name-only (for directory symlinks), since the link target may not be accessible. See §6.4 for symlink detection logic.

**v1 comparison:** Direct mapping from v1's `IsLink` boolean. The semantics are identical.

**`attributes.storage_name`** is the deterministic filename used when the indexer's rename operation is active. For files: the `id` followed by a period and the extension (e.g., `"yA8A8C089A6A8583B24C85F5A4A41F5AC.exe"`). For files without an extension: identical to the `id`. For directories: identical to the `id` (e.g., `"x3B4F479E9F880E438882FC34B67D352C"`).

**v1 comparison:** Direct mapping from v1's `StorageName`. The construction logic is identical.

### 5.9. Recursive Items Field

#### `items`

| Attribute | Value |
|-----------|-------|
| Type | `array` of `IndexEntry` or `null` |
| Required | No |
| v1 equivalent | `Items` |

Child items contained within a directory. Each element is a complete `IndexEntry` conforming to the same root schema (a recursive `$ref` to the root). Present only when the indexed item is a directory and the indexer is operating in recursive or flat-directory mode.

| Scenario | `items` value |
|----------|--------------|
| Item is a file | `null` |
| Item is a directory, flat mode | Array of immediate child `IndexEntry` objects |
| Item is a directory, recursive mode | Array of child `IndexEntry` objects, where child directories themselves have populated `items` (recursive nesting) |
| Item is a directory, single-file mode (not applicable) | N/A — a directory in single-file mode is not a valid scenario |

The children in the `items` array SHOULD be ordered files-first, then directories, matching the original's traversal order. Within each group (files, directories), entries SHOULD be ordered by name (lexicographic, case-insensitive). This ordering is a convention for human readability, not a schema constraint — consumers MUST NOT depend on any particular ordering of the `items` array.

**v1 comparison:** v1's `Items` has the same recursive structure. The v1 schema defines `Items` with `anyOf` permitting `null` elements within the array — the v2 schema tightens this to require that every element in the `items` array is a valid `IndexEntry` (no null entries). If an item cannot be processed (permission error, etc.), it is excluded from the array entirely rather than represented as a null placeholder. This is a stricter contract that simplifies consumer code.

### 5.10. Metadata Array and MetadataEntry Fields

#### `metadata`

| Attribute | Value |
|-----------|-------|
| Type | `array` of `MetadataEntry` or `null` |
| Required | No |
| v1 equivalent | `Metadata` |

An array of metadata records associated with the indexed item. For files, this typically includes an exiftool-generated entry (when the `-Meta` flag is active and the file type is not in the exclusion list) and any sidecar metadata files discovered alongside the item (when MetaMerge is active). For directories, this is `null`. Each element is a self-contained `MetadataEntry` object.

The `metadata` array MAY be empty (an empty array `[]`) when metadata processing is active but no metadata sources are found for the item. The distinction between `null` (metadata processing not applicable or not requested) and `[]` (metadata processing was performed but yielded no results) is semantically meaningful and SHOULD be preserved by the implementation.

#### MetadataEntry

A `MetadataEntry` is a self-contained record describing a single metadata source associated with the parent `IndexEntry`. The v2 `MetadataEntry` is significantly richer than its v1 counterpart, carrying enough information to support MetaMergeDelete reversal operations.

**Top-level properties of `MetadataEntry`:**

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | `string` | Yes | Unique identifier. Prefix `z` for generated, `y` for sidecar. Pattern: `^[yz][0-9A-F]+$`. |
| `origin` | `string` (enum) | Yes | `"generated"` or `"sidecar"`. Primary discriminator. |
| `name` | `NameObject` | Yes | Source name. For sidecar: original filename. For generated: `text` and `hashes` are both `null`. |
| `hashes` | `HashSet` | Yes | Content hashes. For sidecar: hashes of the original file bytes. For generated: hashes of the serialized output. |
| `file_system` | `object` or absent | No | Sidecar only. Contains `relative` (relative path to original sidecar file). |
| `size` | `SizeObject` or absent | No | Sidecar only. Size of the original sidecar file. |
| `timestamps` | `TimestampsObject` or absent | No | Sidecar only. Timestamps of the original sidecar file. |
| `attributes` | `object` | Yes | Classification, format, and transform info. See below. |
| `data` | `null`, `string`, `object`, or `array` | Yes | The metadata content. |

The `required` array for `MetadataEntry` is: `["id", "origin", "name", "hashes", "attributes", "data"]`.

#### MetadataEntry.origin

The `origin` field is the primary structural discriminator for a `MetadataEntry`. It determines which optional fields are present and how the entry should be interpreted.

| `origin` | ID prefix | `file_system` | `size` | `timestamps` | Description |
|----------|-----------|---------------|--------|-------------|-------------|
| `"generated"` | `z` | Absent | Absent | Absent | Created by a tool during indexing (e.g., exiftool output). Never existed as a standalone file. |
| `"sidecar"` | `y` | Present | Present | Present | Absorbed from an external metadata file discovered alongside the indexed item. Carries full filesystem provenance for MetaMergeDelete reversal. |

**v1 comparison:** v1's `MetadataEntry` has `Source` and `Type` fields that partially encode provenance, but does not distinguish generated from sidecar metadata structurally. v1 has no filesystem provenance fields for sidecar entries — the original sidecar file's path, size, and timestamps are lost after MetaMerge. v2's explicit `origin` discriminator and the sidecar-only provenance fields are the structural foundation for reversible MetaMergeDelete operations.

#### MetadataEntry.attributes

The `attributes` sub-object classifies the metadata entry's content type, serialization format, and any transformations applied to the source data before storage.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `type` | `string` | Yes | Semantic classification. See type values below. |
| `format` | `string` (enum) | Yes | Serialization format of the `data` field: `"json"`, `"text"`, `"base64"`, or `"lines"`. |
| `source_media_type` | `string` | No | MIME type of the original source data when the stored format differs from the original (e.g., `"image/png"` for a Base64-encoded screenshot). |
| `transforms` | `array` of `string` | Yes | Ordered list of transformations applied. Empty array means no transforms. |

The `required` array for `attributes` is: `["type", "format", "transforms"]`.

**`attributes.type` values** use hierarchical dot-notation where a prefix identifies the generating tool for generated metadata:

For generated metadata (prefix identifies the tool):

- `"exiftool.json_metadata"` — EXIF/XMP/IPTC metadata extracted by exiftool, delivered as a JSON object.

For sidecar metadata (no prefix — `origin` already indicates sidecar provenance):

- `"description"` — Text description file (e.g., youtube-dl output).
- `"desktop_ini"` — Windows `desktop.ini` file.
- `"generic_metadata"` — Generic metadata/config file (`.cfg`, `.conf`, `.yaml`, `.meta`, etc.).
- `"hash"` — File containing hash/checksum values (`.md5`, `.sha256`, `.crc32`, etc.).
- `"json_metadata"` — JSON-format metadata file (`.info.json`, `.meta.json`, etc.).
- `"link"` — URL shortcut (`.url`), filesystem shortcut (`.lnk`), or pointer file.
- `"screenshot"` — Screen capture image associated with the indexed item.
- `"subtitles"` — Subtitle/caption track (`.srt`, `.sub`, `.vtt`, `.lrc`, etc.).
- `"thumbnail"` — Thumbnail/cover image (`.cover`, `.thumb`, `thumbs.db`).
- `"torrent"` — Torrent/magnet link file.
- `"error"` — The entry could not be read or classified. `data` may be `null` or partial.

These type values are derived from the `MetadataFileParser.Identify` key names in the original configuration, lowercased and converted from PascalCase to snake_case (e.g., `JsonMetadata` → `json_metadata`, `DesktopIni` → `desktop_ini`). The generated metadata type uses dot-notation (`exiftool.json_metadata`) to namespace it separately from the sidecar types.

**v1 comparison:** v1's `Source` and `Type` fields map roughly to `origin` and `attributes.type` respectively. v1's `Source` carries free-text values like `"internal"` or `"external"`; v2's `origin` is a strict two-value enum. v1's `Type` carries the PascalCase type name; v2's `attributes.type` uses lowercase snake_case with tool-prefixed dot-notation for generated entries.

**`attributes.format` values:**

| Format | `data` type | Description |
|--------|-------------|-------------|
| `"json"` | `object` or `array` | Parsed JSON. Stored as a native JSON structure, not a string. |
| `"text"` | `string` | UTF-8 text content. |
| `"base64"` | `string` | Base64-encoded binary content. Decode to recover original bytes. |
| `"lines"` | `array` of `string` | Line-oriented content (hash files, subtitle files). |

**`attributes.transforms`** is an ordered list of transformations applied to the source data before storing it in `data`. The list is ordered from first-applied to last-applied. To reverse storage and recover the original data, apply the inverse of each transform in reverse order.

Defined transform identifiers:

- `"base64_encode"` — Source bytes were Base64-encoded for JSON-safe storage. Inverse: Base64-decode.
- `"json_compact"` — Source JSON was compacted (whitespace removed). Inverse: none needed.
- `"line_split"` — Source text was split into an array of lines (empty lines filtered). Inverse: join with newline.
- `"key_filter"` — Specific keys were removed from a JSON object (e.g., exiftool system keys). Inverse: not reversible.

An empty array means the data is stored as-is with no transformations.

#### MetadataEntry.data

The `data` field contains the actual metadata content. Its structure depends on `attributes.format`:

- When `format` is `"json"`: a JSON object or array.
- When `format` is `"text"` or `"base64"`: a string.
- When `format` is `"lines"`: an array of strings.
- May be `null` if the metadata could not be read (when `attributes.type` is `"error"`).

**v1 comparison:** v1's `Data` field has the same polymorphic nature (`"type": ["null", "string", "object", "array"]`). The difference is that v2's `attributes.format` explicitly declares how to interpret the `data` value, whereas v1 consumers must infer the format from context.

### 5.11. Dropped and Restructured Fields

This section documents every v1 field that is absent from v2 and every v1 field whose v2 representation differs structurally. This serves as a complete mapping reference for the eventual v1-to-v2 migration utility and for consumers adapting existing v1 parsing code.

#### Dropped fields

**`Encoding`** — Dropped (DEV-12 in §2.6). The v1 `Encoding` field contains a serialization of the .NET `System.Text.Encoding` object produced by the `GetFileEncoding` sub-function. This includes properties like `IsSingleByte`, `Preamble`, `BodyName`, `EncodingName`, `HeaderName`, `WebName`, `WindowsCodePage`, `IsBrowserDisplay`, `IsBrowserSave`, `IsMailNewsDisplay`, `IsMailNewsSave`, `EncoderFallback`, `DecoderFallback`, `IsReadOnly`, and `CodePage`. The field is deeply coupled to the .NET type system and has limited utility outside .NET consumers. Python has no standard library facility that produces the same output structure. BOM detection can be performed via `chardet` or manual byte inspection, but the full .NET encoding profile is not reproducible. The field is dropped without replacement. If encoding detection becomes a requirement in a future version, a new field with a Python-native structure would be added.

**`BaseName`** — Dropped. The v1 `BaseName` field contains the filename without its extension (the "stem"). This value is trivially derivable from `name.text` by stripping the `extension` — e.g., for `name.text = "report.pdf"` and `extension = "pdf"`, the base name is `"report"`. Storing a derivable value as a separate field adds no information and inflates the output. Consumers who need the base name can compute it: `name.text.rsplit('.', 1)[0]` (or simply `name.text` when `extension` is `null`).

> **Improvement over v1:** The original includes `BaseName` as a top-level required field because PowerShell's `Get-Item` object exposes `.BaseName` as a property and it was inexpensive to include. In a schema designed for clarity and minimalism, derivable fields are omitted.

**`SHA1` (within hash objects)** — Dropped. All v1 hash objects (`Ids`, `NameHashes`, `ContentHashes`, `ParentIds`, `ParentNameHashes`) include a `SHA1` property. v2's `HashSet` drops SHA1 entirely. SHA1 is not used for identity derivation (only MD5 and SHA256 are `id_algorithm` options), it provides no unique value that MD5 or SHA256 does not already provide in the indexer's use case, and computing it adds overhead for every hashed input. SHA1's cryptographic weaknesses (demonstrated collision attacks since 2017) make it unsuitable as a security-relevant digest, and its 160-bit length occupies an awkward middle ground between MD5 (128-bit, fast, legacy default) and SHA256 (256-bit, strong, recommended). The port does not compute SHA1 digests.

#### Restructured fields (v1 → v2 mapping)

| v1 Field | v2 Location | Structural Change |
|----------|-------------|-------------------|
| `_id` | `id` | Renamed. Leading underscore removed. |
| `Ids` | `hashes` (files), `name.hashes` (directories) | Split. For files, `Ids` content → `hashes`. For directories, `Ids` content was derived from name hashes → `name.hashes`. SHA1 dropped. |
| `Name` | `name.text` | Nested into `NameObject`. |
| `NameHashes` | `name.hashes` | Nested into `NameObject`. SHA1 dropped. |
| `ContentHashes` | `hashes` | Renamed and promoted. Null for directories. SHA1 dropped. |
| `Extension` | `extension` | Renamed (lowercase). |
| `BaseName` | Dropped | Derivable from `name.text` and `extension`. |
| `StorageName` | `attributes.storage_name` | Nested into `attributes` object. |
| `Encoding` | Dropped | .NET-specific. No replacement. |
| `Size` | `size.bytes` | Nested into `SizeObject`. `size.text` added. |
| `IsDirectory` | `type` | Replaced by string enum. |
| `IsLink` | `attributes.is_link` | Nested into `attributes` object. |
| `ParentId` | `file_system.parent.id` | Nested into `file_system.parent`. |
| `ParentIds` | Dropped | Derivable from `file_system.parent.name.hashes`. |
| `ParentName` | `file_system.parent.name.text` | Nested into `file_system.parent.name`. |
| `ParentNameHashes` | `file_system.parent.name.hashes` | Nested into `file_system.parent.name`. SHA1 dropped. |
| `UnixTimeAccessed` | `timestamps.accessed.unix` | Nested into `TimestampsObject` → `TimestampPair`. |
| `TimeAccessed` | `timestamps.accessed.iso` | Nested into `TimestampsObject` → `TimestampPair`. |
| `UnixTimeCreated` | `timestamps.created.unix` | Nested. |
| `TimeCreated` | `timestamps.created.iso` | Nested. |
| `UnixTimeModified` | `timestamps.modified.unix` | Nested. |
| `TimeModified` | `timestamps.modified.iso` | Nested. |
| `Items` | `items` | Renamed (lowercase). Null entries disallowed. |
| `Metadata` | `metadata` | Renamed (lowercase). `MetadataEntry` structure significantly enriched. |
| (Metadata) `Source` | `metadata[].origin` | Replaced by strict enum. |
| (Metadata) `Type` | `metadata[].attributes.type` | Nested. Snake_case. Dot-notation for generated entries. |
| (Metadata) `Name` | `metadata[].name.text` | Nested into `NameObject`. |
| (Metadata) `NameHashes` | `metadata[].name.hashes` | Nested into `NameObject`. |
| (Metadata) `Data` | `metadata[].data` | Same polymorphic type. Format now explicit via `attributes.format`. |

#### New v2 fields with no v1 equivalent

| v2 Field | Description |
|----------|-------------|
| `schema_version` | Version discriminator (always `2`). |
| `id_algorithm` | Explicit algorithm identifier for `id` derivation. |
| `type` | String enum replacing `IsDirectory` boolean. |
| `mime_type` | MIME type detection (extension and/or exiftool). |
| `size.text` | Human-readable size string. |
| `file_system.relative` | Relative path from index root. |
| `metadata[].origin` | Generated vs. sidecar discriminator. |
| `metadata[].file_system` | Sidecar file relative path (for MetaMergeDelete reversal). |
| `metadata[].size` | Sidecar file size (for MetaMergeDelete reversal). |
| `metadata[].timestamps` | Sidecar file timestamps (for MetaMergeDelete reversal). |
| `metadata[].hashes` | Content hashes of metadata (integrity verification). |
| `metadata[].attributes.format` | Explicit data format declaration. |
| `metadata[].attributes.transforms` | Applied transformation chain (for data reversal). |
| `metadata[].attributes.source_media_type` | Original MIME type of binary sidecar data. |

### 5.12. Schema Validation and Enforcement

#### Build-time validation

The canonical v2 JSON Schema (`shruggie-indexer-v2.schema.json`) MUST be used as the validation target for output conformance testing (see §13.4). The test suite SHOULD include a schema conformance test that:

1. Generates index entries for a representative set of inputs (files of various types, directories, symlinks, items with sidecar metadata, items without metadata).
2. Validates each generated entry against the canonical JSON Schema using a Draft-07-compliant validator (e.g., `jsonschema` Python package).
3. Fails the test suite if any entry violates the schema.

This ensures that the implementation's serialization logic stays in sync with the schema definition.

#### Runtime validation

The core indexing engine (`core/entry.py`) does NOT perform JSON Schema validation at runtime — this would add unacceptable overhead for large directory trees. Instead, the implementation relies on **structural correctness by construction**: the `IndexEntry`, `HashSet`, `NameObject`, `SizeObject`, `TimestampPair`, `TimestampsObject`, `ParentObject`, and `MetadataEntry` dataclasses enforce type constraints and required fields through their constructors. If a field is required by the schema, the corresponding dataclass field has no default value (forcing the caller to provide it). If a field is nullable, the corresponding dataclass field is typed `Optional[T]` with a default of `None`.

For consumers who want runtime validation (e.g., when ingesting index output from untrusted sources), the port provides optional Pydantic models behind an import guard in `models/schema.py`. These models mirror the dataclass definitions but add Pydantic's runtime type checking, pattern validation, and `model_validate_json()` for schema-validating a JSON string on ingestion. The Pydantic models are not used by the core engine. See §3.2 for the module layout.

#### Serialization invariants

The serializer (`core/serializer.py`) MUST enforce the following invariants when converting an `IndexEntry` to JSON:

1. **No additional properties.** Every JSON object in the output corresponds to a schema type with `additionalProperties: false`. The serializer MUST NOT include keys that are not defined in the schema.

2. **Required fields are always present.** Every field in the schema's `required` array MUST appear in the output, even when its value is `null`.

3. **Optional fields with `null` values.** For top-level `IndexEntry` properties that are not in `required` (`items`, `metadata`, `mime_type`), the serializer SHOULD include them with `null` values for structural uniformity. Consumers SHOULD be prepared for these fields to be absent or `null`.

4. **Optional `HashSet` fields.** `HashSet.sha512` MUST be omitted from the JSON output (not emitted as `null`) when it was not computed. This matches the JSON Schema expectation that `sha512` is simply not present rather than present-but-null.

5. **Sidecar-only MetadataEntry fields.** `MetadataEntry.file_system`, `MetadataEntry.size`, and `MetadataEntry.timestamps` MUST be present for sidecar entries (`origin: "sidecar"`) and MUST be absent (not `null`) for generated entries (`origin: "generated"`). This is a structural invariant enforced by the `origin` discriminator.

### 5.13. Backward Compatibility Considerations

The v2 schema is a breaking change from v1. Consumers of existing v1 index assets cannot parse v2 output without modification, and vice versa.

#### Migration path

The planned v1-to-v2 migration utility (post-MVP, see §1.2) will convert existing `_meta.json` and `_directorymeta.json` v1 files to the v2 format. The migration is lossy in one direction: v1 fields that are dropped in v2 (`Encoding`, `BaseName`, `SHA1` hashes) are discarded. The migration is enriching in the other direction: v2 fields that have no v1 equivalent (`schema_version`, `id_algorithm`, `type`, `mime_type`, `size.text`, `file_system.relative`, and all `MetadataEntry` provenance fields) are populated with computed or default values where possible and `null` where not.

#### Filename convention

v1 index sidecar files use the suffixes `_meta.json` (for files) and `_directorymeta.json` (for directories). v2 index sidecar files use the suffixes `_meta2.json` and `_directorymeta2.json`. The `2` in the v2 suffixes prevents collision with existing v1 files and allows both versions to coexist on disk during a migration period. This convention is enforced by the serializer when writing in-place output files.

#### Consumer guidance

Consumers adapting from v1 to v2 parsing should:

1. Check for the presence of `schema_version`. If present and equal to `2`, parse as v2. If absent, parse as v1.
2. Replace all PascalCase field accessors with snake_case equivalents (e.g., `entry["IsDirectory"]` → `entry["type"] == "directory"`).
3. Navigate nested sub-objects for fields that were previously top-level (e.g., `entry["Size"]` → `entry["size"]["bytes"]`).
4. Handle the absence of `Encoding`, `BaseName`, and `SHA1` fields.
5. For `MetadataEntry` processing, switch from `Source`/`Type` string matching to `origin` enum checking and `attributes.type` matching.

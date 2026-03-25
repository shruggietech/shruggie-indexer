# Sidecar Architecture Pivot: From Embedded Processing to Relationship Annotation

**Document ID:** `20260321-005-sidecar-architecture-pivot.md`
**Status:** Ratified — 2026-03-24
**Scope:** Defines a fundamental architectural change to how `shruggie-indexer` handles sidecar files. Implications cascade into the `metadexer` ecosystem direction, the `shruggie-indexer` technical specification, the v4 output schema, and the `shruggie-catalog` specification (not yet written).

**Audience:** AI coding agents operating in isolated windows. This document is self-contained context for implementing the changes described herein.

---

## 1. Triggering Evidence

During GUI round-trip testing on 2026-03-21, three-stage tree snapshots (source, mmd, rollback) revealed byte-level size mismatches in four sidecar files after a full index-rename-rollback cycle. Direct file comparison of the `FeedsExport.7z_info.json` sidecar confirmed two transformations applied silently by the system:

1. **Line-ending normalization.** The source file used Windows-style CRLF line endings (1,006 `\r\n` pairs). The rollback output used Unix-style LF. This accounted for 1,006 of the 1,007 missing bytes.
2. **Trailing newline removal.** The source file ended with a trailing `\r\n` after the final closing brace. The rollback output ended immediately after `}` with no trailing newline. This accounted for the remaining 1 byte.

The JSON content was semantically identical. The byte-level difference was a pure serialization artifact introduced by the sidecar reconstruction pipeline.

The same class of discrepancy affected all four flagged sidecar files:

| File | Source bytes | Rollback bytes | Delta | Cause |
|------|-------------|----------------|-------|-------|
| `FeedsExport.7z_info.json` | 47,102 | 46,095 | -1,007 | CRLF→LF (1,006) + trailing newline (1) |
| `FeedsExport_info.json` | 47,102 | 46,095 | -1,007 | Same |
| `How_the_DNS_works-[2ZUxoi7YNgs].info.json` | 805,289 | 791,580 | -13,709 | Same class (CRLF + trailing newline at scale) |
| `How_the_DNS_works-[2ZUxoi7YNgs].url` | 69 | 67 | -2 | Line-ending normalization |

---

## 2. Root Cause Analysis

### 2.1. The reconstruction pipeline

The current sidecar system processes JSON sidecar files through a parse-store-reserialize pipeline:

1. **Ingest:** File content is read, parsed via `json.loads()`, and stored as a Python object in the `MetadataEntry.data` field.
2. **Storage:** The parsed object is serialized into the `_meta3.json` sidecar alongside formatting hints (`json_style`, `json_indent`) and encoding metadata (`encoding.line_endings`, `encoding.bom`, `encoding.detected_encoding`).
3. **Rollback:** The `_decode_sidecar_data()` function calls `_restore_json()` to re-serialize the Python object via `json.dumps()`, then calls `_apply_text_encoding()` to reapply line endings, encoding, and BOM.

This pipeline is lossy by design. `json.dumps()` produces its own output conventions (trailing newline behavior, whitespace after separators, Unicode escape handling, key ordering). The system attempts to compensate by recording and replaying formatting metadata, but this is a reconstruction strategy that will always be incomplete.

### 2.2. The broader problem

The CRLF/trailing-newline issue is a symptom, not the disease. The same class of silent modification can occur through:

- Key ordering differences between `json.loads()` round-trip and original file.
- Unicode escape sequence normalization (`\u00e9` vs literal `é`).
- Numeric precision changes (integer vs float representation).
- Trailing commas in non-strict JSON (accepted by some tools, rejected by `json.loads()`).
- Insignificant whitespace variations not captured by `json_style`/`json_indent`.
- Any future `json.dumps()` behavior change in a Python version upgrade.

Every new edge case requires a new compensating field on the schema and new restoration logic. This is, architecturally, a game of whack-a-mole.

### 2.3. Forensic integrity implication

The `shruggie-indexer` project claims to be a trustworthy custodian of files suitable for forensic and evidentiary use cases. A system that silently modifies file content during round-trip processing (even sidecar content) directly contradicts this claim. The files in question could themselves be evidence, and the system has no business altering them.

---

## 3. Considered Alternatives

### 3.1. Patch the reconstruction pipeline

Add trailing-newline detection and fix the CRLF application order in `_apply_text_encoding()`. This was rejected as treating a symptom. The next edge case would require another patch.

### 3.2. Add a raw-bytes backup option

Store a base64-encoded copy of the original sidecar bytes alongside the parsed content. During rollback, if raw bytes are present, write them directly and skip reconstruction. This would be opt-in via a CLI flag (`--sidecar-raw-backup`) and config key, disabled by default.

This was developed as an intermediate proposal. It solves the forensic fidelity problem for users who enable it but leaves two systems in place (reconstruction for default, raw-write for strict mode), increasing overall complexity.

### 3.3. Configurable per-sidecar storage strategies

Extend the raw-bytes option into a full rule-based configuration system where each sidecar type can specify a storage strategy (`semantic`, `raw`, or `dual`). The `.lnk` handler's existing dual-storage approach (base64 raw + structured metadata) served as the template.

This was explored in depth but recognized as adding significant configuration complexity for a system whose fundamental architecture was already under question.

### 3.4. Gut the sidecar processing system entirely (SELECTED)

Remove all special sidecar processing. Every file on disk becomes a first-class IndexEntry with its own identity hash, timestamps, and metadata. The system then runs a relationship classification pass and annotates entries with informational relationship data. No file content is parsed and re-serialized. No file is excluded from the main index. No file is embedded into another entry's metadata array.

This was selected as the correct architectural direction. The rationale follows in Section 4.

---

## 4. Architectural Decision

### 4.1. Core principle

The indexer is a filesystem inventory and relationship annotation tool. Its job is to answer: "What exists on disk, what is each file's identity, and what are the apparent relationships between files?" It does not ingest, transform, embed, or reconstruct file content.

### 4.2. What changes

**Every file is a first-class IndexEntry.** A `.description` file, an `.info.json` file, a `_screen.jpg` file, a `.lnk` shortcut: all receive their own identity hash, their own timestamps, their own ExifTool metadata (if `--meta` is enabled), their own `encoding` detection, and their own `file_system` placement. No file is silently consumed into another entry.

**Relationships are informational annotations.** After the inventory pass, a relationship classifier examines the file list and annotates entries with relationship data. These annotations say "I believe this file is associated with that file, here's the rule that matched, here's the relationship type." The annotation does not change how either file is processed, stored, renamed, or rolled back.

**The sidecar ingest/reconstruct/restore pipeline is removed.** The following components are eliminated or fundamentally simplified:

| Current component | Disposition |
|---|---|
| `core/sidecar.py` discovery and parsing | Replaced by a relationship classifier |
| `MetadataEntry` model (sidecar-origin entries) | Sidecar-origin fields removed; model retained for ExifTool-only metadata |
| `metadata[]` array on `IndexEntry` (sidecar content) | Sidecar-origin entries removed; array retained for ExifTool metadata |
| `relationships[]` array on `IndexEntry` | New: holds relationship annotations (see Section 5) |
| `_decode_sidecar_data()` in rollback engine | Removed entirely |
| `_restore_json()` in rollback engine | Removed entirely |
| `_apply_text_encoding()` in rollback engine (sidecar path) | Removed entirely |
| Sidecar-specific rename tracking | Removed (all files rename uniformly) |
| `--meta-merge` flag | Removed (no sidecar content to merge) |
| `--meta-merge-delete` flag | Removed (no sidecar content to merge or delete) |
| `json_style`, `json_indent` on `MetadataAttributes` | Removed (no JSON re-serialization) |
| `format`, `transforms` on `MetadataEntry` | Removed (no content storage strategy) |
| Sidecar encoding metadata for reconstruction | Removed (no reconstruction) |

**Rename becomes uniform.** Every file gets a storage name based on its content hash. No special handling for sidecar files. No sidecar-rename tracking. No "rename the sidecar alongside its parent" logic.

**Rollback becomes uniform.** Every file has an IndexEntry with `name.text` and `file_system.relative`. Rollback copies the file from its storage-named location to its original relative path. No sidecar reconstruction. No format-aware re-serialization. No encoding-aware text restoration for sidecar content. Byte-perfect by construction.

### 4.3. What does NOT change

**ExifTool metadata extraction.** The `--meta` flag continues to invoke ExifTool on each file and store the results. This is metadata *about* the file (extracted from the file's own content), not metadata *from* a neighboring file. ExifTool results remain in the `metadata[]` array with `origin: "exiftool"`. The array serves as a general-purpose container for external tool output, decoupled from the specific tool that produces it. This design accommodates a future replacement tool (e.g., `rustif`) without schema changes, and preserves the array as an open-ended extension point for third-party consumers and downstream catalog features.

**Encoding detection.** The `encoding` field on IndexEntry continues to capture BOM, line endings, and detected charset for each file. This is intrinsic file metadata, not sidecar reconstruction data. It remains useful for downstream consumers (including the catalog) that need to understand file content characteristics.

**Identity computation.** Hashing, `storage_name` generation, and the `id`/`id_algorithm` system are unchanged.

**Configuration file format.** TOML-based configuration continues. New sidecar rule configuration extends the existing file.

**Existing CLI flags** (except `--meta-merge` and `--meta-merge-delete`, which are removed). All other flags (`--meta`, `--rename`, `--inplace`, `--dry-run`, `--id-type`, encoding flags, logging flags) continue to function as specified.

---

## 5. Relationship Annotation Design

### 5.1. Schema shape

Each IndexEntry gains an optional `relationships` array. Each element describes a believed association with another indexed file:

```json
{
  "name": { "text": "How_the_DNS_works-[2ZUxoi7YNgs].description" },
  "id": "yABC123...",
  "relationships": [
    {
      "target_id": "y89073B5A650BAE44AA3969C4336B050D",
      "type": "description",
      "rule": "yt-dlp-description",
      "rule_source": "builtin",
      "confidence": 3,
      "predicates": []
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `target_id` | string | The `id` of the related IndexEntry. |
| `type` | string | The semantic relationship type (e.g., `description`, `subtitles`, `screenshot`, `json_metadata`, `shortcut`). |
| `rule` | string | The name of the sidecar rule that produced this relationship. Enables auditability and debugging. |
| `rule_source` | string | The origin of the rule: `"builtin"`, `"user"`, or `"pack:<pack-name>"`. Provides provenance without encoding it into the rule name. |
| `confidence` | integer | How confident the classifier is. See Section 5.3. |
| `predicates` | array | Detailed predicate evaluation results. See Section 5.4. |

The `relationships` array is absent (not empty) when no relationships are detected for a file.

Relationships are directional: the sidecar-like file points at its parent-like file. Bidirectional discovery is a catalog concern. The catalog can trivially invert the relationship graph from the flat index data to provide "show me everything related to this file" queries. The indexer does not produce back-references on target entries.

### 5.2. Relationship types

The initial set of relationship types matches the current sidecar type vocabulary:

`description`, `desktop_ini`, `generic_metadata`, `hash`, `json_metadata`, `link`, `screenshot`, `shortcut`, `subtitles`, `thumbnail`, `torrent`

Additional types can be introduced via user-authored rules without code changes.

### 5.3. Confidence levels

The `confidence` field is an integer code. Higher values indicate greater confidence.

| Code | Meaning |
|------|---------|
| `3` | Rule matched and all predicates satisfied (or no predicates defined on the rule). Highest confidence. |
| `2` | Rule matched but only some predicates were satisfied. Partial confidence. |
| `1` | Rule matched but no required predicates were satisfied. Lowest confidence. |

No relationship entry is written when no rule matches a file. Absence of a `relationships` array (or an empty match set) indicates no rules applied. Unmatched files are a concern for the audit report (see Section 6.7), not the index output.

### 5.4. Predicate detail

Each relationship entry includes a `predicates` array documenting the evaluation outcome of each predicate defined on the matching rule. This provides introspection for debugging and downstream filtering without requiring re-evaluation.

```json
{
  "target_id": "y89073...",
  "type": "screenshot",
  "rule": "yt-dlp-thumbnail",
  "rule_source": "builtin",
  "confidence": 2,
  "predicates": [
    { "name": "requires_sibling", "pattern": "{stem}.mp4", "satisfied": true },
    { "name": "requires_sibling_any", "patterns": ["{stem}.mkv", "{stem}.webm"], "satisfied": false }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | The predicate type (`requires_sibling`, `requires_sibling_any`, `excludes_sibling`). |
| `pattern` | string | The pattern evaluated (present when the predicate takes a single pattern). |
| `patterns` | array of strings | The patterns evaluated (present when the predicate takes a list). |
| `satisfied` | boolean | Whether the predicate condition was met. |

The `predicates` array is empty (not absent) when a rule defines no predicates. This distinguishes "no predicates to evaluate" from "predicates evaluated with results."

---

## 6. Sidecar Rule Engine

### 6.1. Rule structure

Rules are defined in TOML configuration. The system ships with a built-in rule library covering common conventions. Users can override, extend, or disable built-in rules via their config file.

```toml
[sidecar_rules.yt-dlp-description]
match = "{stem}.description"
type = "description"

[sidecar_rules.yt-dlp-info]
match = "{stem}.info.json"
type = "json_metadata"

[sidecar_rules.yt-dlp-thumbnail]
match = "{stem}_screen.jpg"
type = "screenshot"
requires_sibling = "{stem}.mp4"

[sidecar_rules.yt-dlp-subtitles]
match = "{stem}.*.vtt"
type = "subtitles"
requires_sibling_any = ["{stem}.mp4", "{stem}.mkv", "{stem}.webm"]

[sidecar_rules.any-lnk]
match = "*.lnk"
type = "shortcut"
scope = "directory"

[sidecar_rules.disable-builtin-example]
extends = "builtin-some-rule"
enabled = false
```

### 6.2. Match syntax

The `match` field uses a constrained pattern language, not raw regex. Tokens:

| Token | Meaning |
|-------|---------|
| `{stem}` | The content file's name without its final extension. |
| `*` | Glob-style wildcard (matches any sequence of non-separator characters). |
| Literal text | Matches exactly. |

This provides a middle ground between rigid literal matching and unconstrained regex. The `{stem}` token is the key innovation: it binds the sidecar's identity to a specific content file's name, which is the relationship the rule is asserting.

If a user needs full regex (advanced use case), a future `match_regex` field can coexist alongside `match` without changing the default experience.

### 6.3. Predicates

Predicates are optional conditions evaluated after a rule's pattern matches. They are engine-defined (not user-authored code) and evaluated as existence checks against the directory's file list.

| Predicate | Type | Meaning |
|-----------|------|---------|
| `requires_sibling` | string (pattern) | The relationship is produced at full confidence only if a file matching this pattern exists in the same directory. |
| `requires_sibling_any` | list of strings (patterns) | At least one of the listed patterns must match a sibling for full confidence. |
| `excludes_sibling` | string (pattern) | The relationship is NOT produced at full confidence if a file matching this pattern exists. |
| `min_siblings` | integer | The relationship is produced at full confidence only if at least N other files in the directory also match rules pointing at the same target. Useful for cluster detection. |

Predicate patterns use the same token syntax as `match` (`{stem}`, `*`, literals).

**Predicate failure behavior:** When a rule's pattern matches but one or more required predicates fail, the relationship is emitted with a reduced `confidence` value (2 for partial satisfaction, 1 for no predicates satisfied). The relationship is never silently suppressed. The `predicates` array on the relationship entry documents which predicates passed and which failed, providing full transparency for downstream consumers that want to filter on confidence level.

### 6.4. Scope

The `scope` field (default: `"file"`) controls what the rule's `{stem}` token binds to:

- `"file"`: The `{stem}` token matches against content file stems in the same directory. This is the standard case: "this sidecar belongs to that specific content file."
- `"directory"`: The rule matches files that are sidecars of the directory context itself (e.g., `desktop.ini`, `folder.jpg`, `.lnk` shortcuts). The `{stem}` token is not available in directory-scoped rules. The `target_id` in the resulting relationship points to the directory's IndexEntry.

### 6.5. Rule resolution order

1. User-defined rules (from config file) are evaluated first, in definition order.
2. Community pack rules (if installed) are evaluated next, in pack-then-definition order.
3. Built-in rules are evaluated last, in definition order.

First matching rule wins. A user rule with the same name as a built-in rule overrides it entirely. A user rule can disable a built-in by name (`extends = "builtin-name"`, `enabled = false`).

### 6.6. Sidecar-blind mode

A `--no-sidecar-detection` CLI flag (and corresponding config key) disables the relationship classifier entirely. Every file is indexed as a standalone content file with no `relationships` array. The rule engine is not invoked.

This mode is the zero-assumption baseline. It is useful for:

- First-time indexing of an unfamiliar file collection.
- Workflows where relationship detection is handled entirely by the catalog.
- Users who want a pure filesystem inventory with no interpretive layer.

### 6.7. Sidecar audit mode

A `--sidecar-audit` CLI flag runs the full index with relationship classification enabled but produces an additional audit report. The report lists:

- Every relationship detected, with the rule that produced it and the confidence level.
- Every file that was *not* matched by any rule (potential unrecognized sidecars or standalone content).
- Files that matched a rule pattern but failed a predicate (near-misses).

The audit report is written to a separate file (not mixed into the index output). Its format is designed to be human-reviewable and to serve as a starting point for authoring custom rules.

This feature does not need to be in the first implementation pass. The architecture supports it without structural changes.

---

## 7. Community Rule Packs

### 7.1. Pack format

A community rule pack is a TOML file containing a set of sidecar rules under a namespaced table:

```toml
[pack]
name = "yt-dlp"
version = "1.0.0"
description = "Sidecar rules for yt-dlp video downloads"
author = "ShruggieTech"

[sidecar_rules.yt-dlp-description]
match = "{stem}.description"
type = "description"

[sidecar_rules.yt-dlp-info-json]
match = "{stem}.info.json"
type = "json_metadata"

# ... additional rules
```

### 7.2. Pack installation

Packs are installed as TOML files in the user's pack directory (`%LOCALAPPDATA%\shruggie-tech\shruggie-indexer\packs\` on Windows, `~/.local/share/shruggie-tech/shruggie-indexer/packs/` on Linux/macOS).

Future CLI commands (not in initial scope):

- `shruggie-indexer packs list-remote` — fetch and display available packs from the official manifest.
- `shruggie-indexer packs install <n>` — download a pack TOML from the official repository.
- `shruggie-indexer packs list` — show installed packs.
- `shruggie-indexer packs remove <n>` — remove an installed pack.

The pack management CLI is a catalog-era feature. For the initial indexer implementation, packs are manually placed in the directory.

### 7.3. Pack resolution

Installed packs are loaded after user rules and before built-in rules (see Section 6.5). If multiple packs define rules with the same name, load order is alphabetical by pack filename, and the first definition wins. User rules always override pack rules.

---

## 8. Impact on Existing Systems

### 8.1. Output schema

This is a **v4 schema change**. Key differences from v3:

| Aspect | v3 (current) | v4 (proposed) |
|--------|-------------|---------------|
| Sidecar files in index output | Excluded from main index; content embedded in parent's `metadata[]` | Included as first-class IndexEntry objects |
| `metadata[]` array purpose | Holds both ExifTool metadata and ingested sidecar content | Holds only ExifTool-extracted metadata |
| `MetadataEntry.origin` | `"exiftool"` or `"sidecar"` | `"exiftool"` only (sidecar-origin entries removed) |
| `MetadataEntry.data` | Contains parsed sidecar file content | Not applicable (no sidecar content stored) |
| `MetadataEntry.encoding` | Sidecar file encoding for reconstruction | Not applicable |
| `MetadataEntry.attributes.format` | `"json"`, `"text"`, `"base64"`, `"lines"` | Not applicable |
| `MetadataEntry.attributes.json_style` | `"pretty"` or `"compact"` | Not applicable |
| `MetadataEntry.attributes.json_indent` | Indent string for JSON reconstruction | Not applicable |
| `MetadataEntry.attributes.transforms` | `["json_compact"]`, `["base64_encode"]`, etc. | Not applicable |
| `relationships[]` on IndexEntry | Does not exist | New: array of relationship annotations |
| `--meta-merge` flag | Merges sidecar content into parent entries | Removed |
| `--meta-merge-delete` flag | Merges and deletes sidecar files | Removed |
| `schema_version` | `3` | `4` |
| In-place file-level sidecar suffix | `_meta3.json` | `_idx.json` (fixed; no longer version-bumped) |
| In-place directory-level sidecar suffix | `_directorymeta3.json` | `_idxd.json` (fixed; no longer version-bumped) |

### 8.2. In-place output suffix convention

Starting with v4, the in-place output files use fixed suffixes that are decoupled from the schema version number:

| Scope | Legacy suffixes (recognized for backward compatibility) | v4+ suffix (permanent) |
|-------|--------------------------------------------------------|----------------------|
| File-level | `_meta.json`, `_meta2.json`, `_meta3.json` | `_idx.json` |
| Directory-level | `_directorymeta.json`, `_directorymeta2.json`, `_directorymeta3.json` | `_idxd.json` |

The `_idx.json` and `_idxd.json` suffixes are final. Future schema version bumps change the `schema_version` field inside the file, not the filename. This eliminates the suffix-churn pattern from prior versions.

The `metadata_exclude_patterns` list MUST include all legacy suffixes and the new suffixes to prevent the indexer from re-indexing its own output.

### 8.3. Legacy output cleanup

A `cleanup_legacy_sidecars` config key (default: `false`) and corresponding CLI flag control automatic removal of obsolete tool output files. When enabled:

1. After a successful index run that writes `_idx.json` and/or `_idxd.json` files, the system scans the same directories for old-format siblings (`_meta.json`, `_meta2.json`, `_meta3.json`, `_directorymeta.json`, `_directorymeta2.json`, `_directorymeta3.json`).
2. An old-format file is deleted only if a new-format file was successfully written in the same run for the same scope. Orphaned legacy files in directories the current run did not touch are never deleted.
3. Each deletion is logged at `INFO` level. No user confirmation is required.

This is cleanup of the indexer's own tool artifacts, not user data. The "no silent data loss" principle does not apply to stale tool output that has been superseded by a freshly generated replacement.

### 8.4. Rollback engine

The rollback engine simplifies dramatically:

**Removed codepaths:**
- `_plan_sidecar_restore()` — no sidecar-specific restore planning.
- `_decode_sidecar_data()` — no sidecar content decoding.
- `_restore_json()` — no JSON re-serialization.
- `_apply_text_encoding()` usage for sidecar restoration — the function may remain for other purposes but is no longer called by the sidecar restore path (which no longer exists).
- Sidecar-specific timestamp restoration.
- Sidecar-specific conflict resolution.
- The `sidecar_data`, `sidecar_binary`, and `metadata_entry` fields on `RollbackAction`.

**Simplified behavior:** Every entry in the rollback plan is a file copy (or a duplicate re-copy). The source file exists on disk in its storage-named form. The rollback engine copies it to the original relative path and restores timestamps. Uniform for all files regardless of whether they were "sidecars" in a previous life.

**Backward compatibility:** The rollback engine MUST continue to support v2 and v3 sidecar files for rollback of existing indexed collections. This means the old `_decode_sidecar_data()` path is retained as a legacy fallback, invoked only when loading v2/v3 sidecar files from `_meta2.json` or `_meta3.json` output. New v4 output written to `_idx.json` never triggers this path.

### 8.5. Rename engine

**Removed complexity:**
- Sidecar-rename tracking (renaming the in-place sidecar file alongside its content file).
- The "inplace sidecar renamed" log messages and associated bookkeeping.
- Special handling for sidecar files during the rename pass.

**Simplified behavior:** Every file in the index gets a storage name. Every file is renamed independently. The in-place sidecar written alongside each renamed file uses the `_idx.json` suffix and records the original name and relationships, enabling rollback.

### 8.6. Discovery and traversal

**Removed complexity:**
- Sidecar exclusion from the main file list during discovery. Currently, files identified as sidecars are excluded from entry building (`Excluded N sidecar file(s) from entry building`). This exclusion logic is removed. All files enter the main entry list.
- The `metadata_identify` regex pattern set used for sidecar type detection during discovery. This is replaced by the rule engine's pattern matching, which runs as a post-discovery classification pass rather than an inline exclusion filter.

**Changed behavior:** The `metadata_exclude_patterns` configuration (which excludes the indexer's own output files) is retained and updated to cover both legacy suffixes and the new `_idx.json`/`_idxd.json` suffixes. These are tool artifacts, not files to be indexed or relationship-classified. The exclusion applies to both the entry list and the relationship classifier: files matching `metadata_exclude_patterns` are invisible to the entire pipeline.

### 8.7. Configuration file

**New sections:**
- `[sidecar_rules.*]` table(s) for user-defined relationship rules.
- `[packs]` section for pack management settings (future).
- `cleanup_legacy_sidecars` key for legacy output cleanup.

**Removed sections/keys:**
- Any configuration related to `metadata_identify` sidecar type patterns (replaced by the rule engine).
- `meta_merge` and `meta_merge_delete` configuration keys.

**Retained sections/keys:**
- `metadata_exclude_patterns` (tool artifact exclusion, updated to include `_idx.json` and `_idxd.json`).
- `exiftool` configuration (exclude extensions, exclude keys).
- All other existing configuration.

### 8.8. GUI

The GUI currently has controls for meta-merge and meta-merge-delete operations. These controls are removed. The GUI gains no new controls for the relationship classifier in the initial implementation (the built-in rules apply automatically; custom rules are configured via the TOML file).

Future GUI enhancements (not in initial scope): a rule editor panel, a relationship visualization in the results view.

### 8.9. Tests

**Tests to be removed or rewritten:**
- All sidecar round-trip fidelity tests (the 12 tests covering `.url` text cascade, `.lnk` dual-storage, JSON style detection, and restoration fidelity). The `.lnk` and `.url` specific handling is no longer needed; they're just files.
- Meta-merge and meta-merge-delete integration tests.
- Sidecar reconstruction tests.

**Tests to be added:**
- Relationship classifier unit tests: rule matching, predicate evaluation, confidence assignment, predicate detail recording.
- Integration tests: full index of a directory containing known sidecar conventions, verifying correct relationship annotations with expected confidence values and predicate outcomes.
- Rollback integration tests: verify that files previously treated as sidecars are now rolled back as ordinary files (byte-perfect).
- Backward compatibility tests: v2 and v3 sidecar files can still be rolled back via the legacy path.
- Sidecar-blind mode tests: verify no relationships are produced when `--no-sidecar-detection` is active.
- Legacy cleanup tests: verify old-format files are removed only when a new-format replacement was written in the same run, and that orphaned legacy files in untouched directories are not deleted.

---

## 9. Impact on Ecosystem

### 9.1. Indexer-Catalog contract

The contract between the indexer and catalog changes fundamentally:

**Previous contract:** The indexer produces consolidated entries where sidecar content is embedded in the parent entry's `metadata[]` array. The catalog stores these entries as point-in-time snapshots.

**New contract:** The indexer produces a flat inventory of all files with directional relationship annotations. The catalog consumes these entries, persists the relationship graph, and provides consolidated asset views on demand. The catalog is responsible for:

- Building and maintaining the relationship graph across sessions, including bidirectional lookups (inverting the indexer's directional annotations to answer "what points at this file?").
- Providing "show me everything related to this file" queries (subgraph extraction).
- Detecting relationship changes between sessions (new sidecars appeared, sidecars disappeared, relationships changed).
- Visualization of the relationship graph.
- Any consolidation or "asset view" presentation that the v3 embedded-sidecar model previously provided at the indexer level.

### 9.2. Ecosystem direction document

The ecosystem direction document (`20260305-002-ecosystem-direction.md`) requires updates to reflect:

- The indexer's reduced scope (inventory + relationships, not content processing).
- The catalog's expanded scope (relationship graph, consolidated views, visualization, bidirectional discovery).
- The removal of meta-merge and meta-merge-delete from the indexer's responsibilities.
- The new indexer-catalog contract described above.
- The sidecar rule engine as a shared architectural concept (the catalog may extend it with cross-session rules).

### 9.3. Technical specification

The `shruggie-indexer-spec.md` requires substantial updates:

- §5 (Schema): New v4 schema with `relationships[]`, removal of sidecar-origin `MetadataEntry` fields. New `_idx.json`/`_idxd.json` suffix convention.
- §6.7 (Sidecar Metadata File Handling): Rewritten to describe the relationship classifier instead of the ingest/embed pipeline.
- §6.10 (File Rename): Simplified to remove sidecar-rename tracking.
- §6.11 (Rollback Operations): Simplified to remove sidecar reconstruction. Legacy support documented.
- §7.5 (Sidecar Suffix Patterns): Replaced by the rule engine specification.
- §7.6/§7.7 (Configuration): Updated with new rule engine configuration, `cleanup_legacy_sidecars` key.
- §8 (CLI): `--meta-merge` and `--meta-merge-delete` removed. `--no-sidecar-detection` added. `--cleanup-legacy-sidecars` added.
- §10 (GUI): Meta-merge controls removed.
- §14 (Tests): Updated per Section 8.9 above.

---

## 10. Implementation Sequencing

The following is a high-level ordering, not a sprint plan. Sprint-level decomposition will be done separately.

### Phase 1: Schema and core model (foundation)

Define the v4 schema. Add `relationships[]` to IndexEntry with the full annotation shape (`target_id`, `type`, `rule`, `rule_source`, `confidence`, `predicates`). Remove sidecar-origin fields from MetadataEntry (retain ExifTool-only usage). Adopt `_idx.json` and `_idxd.json` as the fixed output suffixes. Bump `schema_version` to 4.

### Phase 2: Rule engine (classification infrastructure)

Implement the rule engine: rule loading from config, built-in rule library, pattern matching with `{stem}` and `*` tokens, predicate evaluation with pass/fail recording, confidence code assignment, `rule_source` tracking. No integration with the indexer pipeline yet; this is a standalone module with unit tests.

### Phase 3: Discovery pipeline refactor (integration)

Remove sidecar exclusion from discovery. All files enter the main entry list. After the inventory pass, run the relationship classifier over the entry list and populate `relationships[]`. Remove the `metadata_identify` regex system. Ensure `metadata_exclude_patterns` suppresses both entry creation and relationship classification for tool artifacts.

### Phase 4: Rename simplification

Remove sidecar-rename tracking. Every file renames independently. Update in-place output to use `_idx.json` and `_idxd.json` suffixes with v4 schema content.

### Phase 5: Rollback simplification

Remove sidecar reconstruction codepaths from the rollback engine. All files roll back as ordinary file copies. Retain legacy v2/v3 support as a fallback path triggered by `_meta2.json`/`_meta3.json` input.

### Phase 6: CLI and GUI cleanup

Remove `--meta-merge` and `--meta-merge-delete` flags. Add `--no-sidecar-detection` flag. Add `--cleanup-legacy-sidecars` flag. Remove meta-merge GUI controls. Update help text and documentation.

### Phase 7: Tests and validation

Full test rewrite per Section 8.9. Three-stage tree snapshot validation (source → mmd → rollback) to confirm byte-perfect round-trip for all files including former sidecars. Legacy cleanup tests.

### Phase 8: Specification and documentation update

Update the technical specification, ecosystem direction document, changelog, and README to reflect the v4 architecture, new suffix convention, and legacy cleanup feature.

---

## 11. Future Work (Out of Scope for This Pivot)

The following items are enabled by this architecture but are not part of the initial implementation:

- **Community pack CLI** (`packs list-remote`, `packs install`, etc.).
- **Self-update mechanism** for the indexer binary/package.
- **Sidecar audit mode** (`--sidecar-audit` flag and report generation).
- **Interactive training mode** (guided rule authoring from audit output).
- **Catalog relationship graph** (persistence, querying, visualization, bidirectional discovery).
- **Cross-session relationship analysis** (detecting sidecar additions/removals between indexing sessions).
- **`match_regex` field** on rules for advanced users who need full regex.
- **`min_siblings` predicate** (cluster detection).
- **GUI rule editor** and relationship visualization panel.

---

## 12. Resolved Design Decisions

The following decisions were resolved during ratification review on 2026-03-24.

**1. In-place output suffix:** The version-bumped suffix convention (`_meta.json`, `_meta2.json`, `_meta3.json`) is retired. v4 output uses `_idx.json` for file-level and `_idxd.json` for directory-level in-place output. These suffixes are permanent. Future schema versions change the internal `schema_version` field, not the filename. Legacy suffixes are recognized for backward compatibility in rollback and are cleaned up on demand via `cleanup_legacy_sidecars` (see Section 8.3).

**2. ExifTool metadata placement:** ExifTool results remain in the `metadata[]` array with `origin: "exiftool"`. The array is retained as a general-purpose container for external tool output, decoupled from any specific tool identity. This accommodates future tool replacement (e.g., `rustif`), third-party extension, and potential downstream catalog uses (e.g., tagging) without schema changes.

**3. Predicate failure behavior:** Predicate failures are emitted, not suppressed. The `confidence` field is an integer code: `3` (full match), `2` (partial predicates satisfied), `1` (no predicates satisfied). Each relationship entry includes a `predicates` array documenting individual predicate outcomes. No relationship entry is written when no rule matches. See Sections 5.3 and 5.4.

**4. Bidirectional relationship annotation:** Relationships are directional only. The sidecar-like file's entry points at the parent-like file. The parent receives no back-reference. Bidirectional discovery, graph inversion, and consolidated asset views are catalog responsibilities. See Section 9.1.

**5. Rule naming convention:** Rule names are short and unprefixed. Provenance is tracked via a separate `rule_source` field on the relationship entry (`"builtin"`, `"user"`, or `"pack:<pack-name>"`). This separates the concerns of "what does this rule do" from "where did it come from." See Section 5.1.

**6. `metadata_exclude_patterns` scope:** The exclusion patterns apply to both the entry list and the relationship classifier. Files matching these patterns (the indexer's own output artifacts) are invisible to the entire pipeline. The pattern list covers all legacy suffixes (`_meta.json`, `_meta2.json`, `_meta3.json`, `_directorymeta.json`, `_directorymeta2.json`, `_directorymeta3.json`) and the new suffixes (`_idx.json`, `_idxd.json`). See Section 8.6.

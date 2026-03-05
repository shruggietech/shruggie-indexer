# ShruggieTech Asset Ecosystem — Project Direction

- **Author:** William Thompson (ShruggieTech LLC)
- **Date:** 2026-03-05
- **Supersedes:** `20260223-002-ecosystem-direction.md`
- **Status:** APPROVED

---

## Audience

This document is written **AI-first, Human-second**.

It defines architectural intent, invariant boundaries, system philosophy, and uniform conventions for the ShruggieTech asset ecosystem. It is not a marketing description or a feature specification. It is a directional document intended to constrain future implementation decisions and guide AI-assisted development across all four ecosystem components.

Every section is written with sufficient detail for an AI implementation agent to produce correct design decisions within an isolated context window, without interactive clarification. Human developers and maintainers are the secondary audience — the document is equally valid as a traditional engineering reference.

Assume full familiarity with `shruggie-indexer` and its output contract (`IndexEntry` v2).

---

## Problem Statement

Managing a large, heterogeneous collection of digital assets across local filesystems, cloud storage, and multi-user environments is fragile when done with ad-hoc tooling. The core failure modes are:

- Identity is path-based, so moving or renaming a file breaks relationships.
- Metadata is either absent or stored in proprietary silos.
- Deduplication is best-effort and unreliable.
- Integrity verification is manual and inconsistent.
- Tooling is tightly coupled, making partial automation difficult.

The ShruggieTech asset ecosystem exists to solve these problems through deterministic, content-addressed identity and a clean separation of concerns across a small set of composable utilities.

---

## Core Philosophy

### 1. Identity Is Deterministic and Client-Originated

All content identity — hashes, IDs, `storage_name` — is computed client-side from the content itself.

- Servers do not define identity.
- Servers may verify identity periodically or probabilistically.
- The `IndexEntry` is the authoritative metadata record for a content object.

This system is **content-addressed**, not path-addressed.

### 2. Bytes and Metadata Are Separate but Linked

Each concern has exactly one home:

| Concern | Component |
|---|---|
| Identity generation and metadata extraction | Indexer |
| Raw byte storage | Vault |
| Structured metadata and references | Catalog |
| Orchestration and workflow | Sync |

No component is permitted to silently absorb a neighbor's responsibility.

### 3. Standalone Utility Principle

Each utility must:

- Be useful independently, without the others.
- Have a CLI-first interface with stable, documented contracts.
- Be automatable without human interaction.
- Make minimal external assumptions.
- Avoid hidden coupling to sibling utilities.

Utilities may optionally expose daemon or API modes, but CLI contracts remain canonical. API layers must be thin wrappers over CLI logic, not independent implementations.

### 4. Servers Are Registries and Policy Engines, Not Sources of Truth

**What servers do:**

- Enforce authentication and authorization.
- Record references and ownership.
- Apply and enforce storage policies.
- Optionally verify integrity on a schedule or by policy.

**What servers do not do:**

- Define or recompute content identity.
- Mutate content or rewrite metadata.
- Make autonomous decisions about asset disposition.

---

## System Overview

The ecosystem consists of four utilities. They are listed here in dependency order: each utility depends only on those above it.

```
shruggie-indexer   ← foundational; no dependencies on other ecosystem components
shruggie-vault     ← depends on indexer output (IndexEntry)
shruggie-catalog   ← depends on indexer output (IndexEntry)
shruggie-sync      ← orchestrates indexer, vault, and catalog
```

All downstream components treat `shruggie-indexer` output as a fixed contract. No component below it is permitted to redefine or reinterpret the identity it establishes.

---

## Component Specifications

### shruggie-indexer

**Role within the ecosystem:** Foundation. Defines identity and metadata shape.

**Release status:** v0.1.2 (released 2026-03-05). Stable.

`shruggie-indexer` operates on local files and directories. It produces `IndexEntry` JSON records — structured metadata objects that serve as the authoritative description of a content object throughout the rest of the ecosystem.

**Responsibilities:**

- Compute deterministic content identity (`id`, `storage_name`) via hash of file bytes.
- Extract file metadata (MIME type, size, timestamps, format-specific fields via ExifTool).
- Produce well-formed `IndexEntry` v2 JSON output.
- Manage sidecar metadata files (discovery, parsing, MetaMergeDelete lifecycle).
- Provide session-level provenance (`session_id`, `indexed_at`) for downstream correlation.

**Non-responsibilities:**

- No storage management.
- No reference tracking.
- No orchestration.

**Delivery surfaces:** CLI (`click`), GUI (`customtkinter`), Python library (`index_path()` API).

**Invariants:**

- Given the same bytes, the same `IndexEntry` identity fields are always produced.
- `IndexEntry` output is the only artifact this tool emits. It does not side-effect storage.
- `session_id` links all entries from a single invocation; `indexed_at` records observation time distinct from file timestamps.

---

### shruggie-vault

**Role within the ecosystem:** Byte storage. Preserves truth.

**Release status:** Planned.

A deterministic, content-addressed store for raw bytes. Assets are stored and retrieved strictly by identity-derived keys established by the indexer.

**Responsibilities:**

- Store bytes under a deterministic key (`storage_name`).
- Retrieve bytes by `id` or `storage_name`.
- Check existence without retrieval (`head`).
- Verify stored bytes against a provided `IndexEntry` when explicitly requested.
- Prune unreferenced objects when explicitly invoked.

**Non-responsibilities:**

- No metadata indexing or search.
- No identity computation or verification of its own accord.
- No implicit mutation of stored content.
- No knowledge of catalog references.

**Storage backends:**

- Local filesystem.
- S3-compatible object storage (AWS S3, MinIO, etc.).

**API surface:** The vault may expose an HTTP API layer for remote operation. This API is a thin transport layer; all identity logic remains on the client.

**Invariants:**

- The same `storage_name` always maps to identical bytes. This is a write-once guarantee.
- The vault enforces identity; it does not compute it.
- Verification is always explicit — never triggered automatically during ingest.
- Pruning is always explicit — the vault never autonomously deletes content.

**Standalone usefulness:**

- Functions as a general-purpose content-addressed storage tool independent of any catalog.
- Verifies storage integrity independently.
- Suitable for archival and deduplicated storage workflows on its own.

---

### shruggie-catalog

**Role within the ecosystem:** Metadata registry. Records truth.

**Release status:** Next in development sequence (active pivot target).

A structured database of `IndexEntry` records and the references (collections, projects, users, snapshots) that point to them.

**Responsibilities:**

- Store and retrieve full `IndexEntry` JSON records.
- Project and index searchable fields (MIME type, size, timestamps, format-specific metadata, etc.).
- Track logical references to assets: collections, projects, users/tenants, snapshots.
- Provide search and query capability over indexed fields.
- Reconcile catalog contents against a vault (detect missing or orphaned blobs).
- Correlate `IndexEntry` snapshots across time using `id`, `session_id`, and `indexed_at` to build identity evolution history.

**Non-responsibilities:**

- No raw byte storage.
- No identity computation.
- No autonomous deletion of vault objects.
- No filesystem scanning.

**Storage backends:**

- PostgreSQL (primary mode, multi-user).
- SQLite (single-user mode).

**API surface:** The catalog may expose an HTTP API for remote access. Authentication and authorization are enforced at this layer.

**Invariants:**

- `id` is globally unique per content object. Duplicate ingest is idempotent.
- Multiple references may point to a single asset; assets do not belong to references.
- Reference deletion removes the reference, not the underlying asset.
- Physical deletion from the vault requires a separate, explicit prune operation.

**Catalog–Indexer contract:** The `IndexEntry` is a point-in-time snapshot. Its fields describe a file's identity, metadata, and filesystem state at the moment of indexing. Over time, content hashes change when content is modified, timestamps shift through normal filesystem operations, metadata objects evolve as external tools and source files change, and relative paths change when files are moved or index roots differ between runs. This transient nature is correct by design. The indexer produces accurate snapshots; the catalog receives them, correlates them across time, and maintains a durable record of identity evolution.

**Standalone usefulness:**

- Functions as an asset inventory system independent of where bytes actually live.
- Operates in read-only mode for analysis or auditing.
- Provides a durable metadata record that survives storage backend migration.

---

### shruggie-sync

**Role within the ecosystem:** Orchestration. Propagates truth.

**Release status:** Planned.

`shruggie-sync` connects the other three components into a coherent, reliable workflow. It is the primary operational surface for end users running ingestion pipelines.

**Responsibilities:**

- Accept directory or file targets as input.
- Invoke `shruggie-indexer` to produce `IndexEntry` records for each target.
- Generate Sync Plans (dry-run output of pending operations) before committing any changes.
- Check the catalog and vault for already-present assets to avoid redundant work.
- Upload bytes to the vault.
- Commit `IndexEntry` records to the catalog only after upload is confirmed complete.
- Handle resumable uploads across interrupted runs.
- Support dry-run mode with no side effects.

**Non-responsibilities:**

- No long-term metadata storage of its own.
- No persistent daemon required for core operation.
- No silent mutation of existing assets.
- No identity computation (that belongs to the indexer).

**Operational modes:**

*Local mode:* Indexer → local vault → local catalog. No server required. Suitable for offline archival and single-user workflows.

*Remote mode (client-hashed, server-verify flow):* Client invokes indexer and computes identity locally. Client uploads bytes directly to remote vault. Client commits metadata to remote catalog. Server may verify integrity asynchronously by policy.

**Invariants:**

- Identity always originates from the client. Sync never delegates identity decisions to a server.
- Upload is confirmed complete before catalog commit.
- Catalog commit is idempotent. Resubmitting the same `IndexEntry` is safe.
- Sync is restartable at any point without risk of corruption or data loss.
- No asset is silently overwritten or deleted.

**Standalone usefulness:**

- Functions as a reliable directory-to-vault ingestion pipeline.
- Suitable for backup, archival, and cross-system migration workflows.
- Produces deterministic, auditable deduplication behavior.

---

## The IndexEntry Contract

The `IndexEntry` v2 JSON schema is the stable foundation on which all ecosystem components are built. Downstream components consume it as a fixed contract and MUST NOT redefine its fields or semantics.

### Canonical Schema Location

The authoritative machine-readable schema is hosted at:

```
https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json
```

This document uses JSON Schema Draft-07. A local copy is committed to the indexer repository at `docs/schema/shruggie-indexer-v2.schema.json` and MUST be kept in sync with the canonical hosted version.

### Schema Design Principles

The v2 schema is governed by five design principles:

**P1 — Logical grouping.** Related fields are consolidated into typed sub-objects (`NameObject`, `HashSet`, `SizeObject`, `TimestampPair`, `TimestampsObject`, `ParentObject`, `MetadataEntry`) rather than scattered across the top level.

**P2 — Single discriminator for item type.** A `type` enum (`"file"` or `"directory"`) combined with `schema_version` allows consumers to route parsing unambiguously from the first two fields of any entry.

**P3 — Provenance tracking for metadata entries.** `MetadataEntry` includes `origin`, `file_system`, `size`, `timestamps`, and an `attributes` sub-object — enough to reconstruct the original sidecar file for MetaMergeDelete reversal.

**P4 — Elimination of redundancy.** Dropped fields that were structurally redundant, platform-specific, or algorithmically redundant from the v1 schema.

**P5 — Explicit algorithm selection.** `id_algorithm` records which hash algorithm produced `id`, making identity derivation fully self-describing.

### Top-Level IndexEntry Fields

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `schema_version` | `integer` (const `2`) | Yes | Always `2`. Placed first by convention. |
| `id` | `string` | Yes | Primary identifier. Prefix `y` = file, `x` = directory. Pattern: `^[xy][0-9A-F]+$`. |
| `id_algorithm` | `string` (enum) | Yes | `"md5"` or `"sha256"`. |
| `type` | `string` (enum) | Yes | `"file"` or `"directory"`. |
| `name` | `NameObject` | Yes | Item name with associated hash digests. |
| `extension` | `string` or `null` | Yes | Lowercase, no leading dot. `null` for directories. |
| `mime_type` | `string` or `null` | No | MIME type via `mimetypes.guess_type()`, overridden by ExifTool. |
| `size` | `SizeObject` | Yes | Human-readable and byte-count size. |
| `hashes` | `HashSet` or `null` | Yes | Content hashes (file) or `null` (directory). |
| `file_system` | `object` | Yes | Relative path and parent directory identity. |
| `timestamps` | `TimestampsObject` | Yes | Created, modified, and accessed timestamps (each as `TimestampPair` with ISO 8601 + Unix milliseconds). |
| `attributes` | `object` | Yes | Symlink status and deterministic `storage_name`. |
| `items` | `array[IndexEntry]` or `null` | No | Child entries (directory) or `null` (file). |
| `metadata` | `array[MetadataEntry]` or `null` | No | Sidecar and generated metadata. |
| `session_id` | `string` or `null` | No | UUID4 linking to the invocation that produced this entry. |
| `indexed_at` | `TimestampPair` or `null` | No | When the entry was constructed (distinct from file timestamps). |

`additionalProperties` is `false` at the root level — no extra keys are permitted.

### Reusable Type Definitions

Six types defined in the schema's `definitions` block compose the top-level properties:

| Type | Purpose |
|------|---------|
| `NameObject` | Pairs a `text` string with its `hashes` (`HashSet`). |
| `HashSet` | Contains `md5`, `sha256`, and optionally `sha512` hex digests. |
| `SizeObject` | Pairs a human-readable `display` string with a `bytes` integer. |
| `TimestampPair` | Pairs an `iso` (ISO 8601) string with a `unix` (milliseconds) integer. |
| `TimestampsObject` | Groups `created`, `modified`, and `accessed` as `TimestampPair` objects. |
| `ParentObject` | Groups the parent directory's `id` and `name` (`NameObject`). |
| `MetadataEntry` | A sidecar or generated metadata record with `id`, `origin`, `name`, `hashes`, `attributes`, and `data`. |

### Schema Evolution Rules

- **Additive fields are non-breaking.** New optional fields (like `session_id` and `indexed_at`) MAY be added to v2 without incrementing `schema_version`. Consumers MUST tolerate unknown optional fields.
- **Structural changes require a version bump.** Renaming, retyping, removing a required field, or altering semantic meaning constitutes a breaking change and MUST increment `schema_version`.
- **Deprecation before removal.** A field marked deprecated in version N is emitted but ignored, then removed in version N+1.
- **Consumers dispatch on `schema_version`.** The integer value `2` is checked before parsing. Documents with unrecognized versions SHOULD be rejected.

---

## Verification Philosophy

Integrity is enforced through **explicit verification**, not blind trust during ingest.

Verification modes available to the vault:

- **Strict** — re-hash the entire stored object and compare against the `IndexEntry`.
- **Sampled** — probabilistic audits across a fraction of stored objects.
- **Tiered** — frequency and depth determined by tenant policy or asset risk classification.

Verification is a vault capability invoked by policy or on-demand. It is not part of the ingest critical path. This preserves ingestion performance while maintaining the ability to audit integrity continuously.

---

## Reference and Deletion Model

Assets are **immutable**. References are **mutable**.

Deletion is always two-phase:

1. Remove references in the catalog.
2. Explicitly invoke vault prune for unreferenced objects.

This model prevents accidental data loss. No content is ever removed in a single implicit operation.

---

## Composition Rules

No utility may:

- Recompute identity unless performing an explicit integrity verification.
- Rewrite or amend an `IndexEntry` outside of the indexer's own operation.
- Implicitly delete content from any backend.
- Implicitly migrate content between backends.

All cross-utility interaction must occur through explicit CLI invocation or defined API contracts. There are no hidden side channels.

---

## Design Goals

The following properties must be preserved across all future implementation decisions:

- **Determinism** — the same input always produces the same output.
- **Idempotence** — repeating an operation produces no additional side effects.
- **Composability** — utilities work independently and in combination without modification.
- **Auditability** — all operations are traceable; no silent mutations or deletions.
- **Minimal hidden state** — system state is observable and recoverable from durable records.
- **Clear failure modes** — failures surface explicitly; the system does not paper over errors.
- **Offline-first capability** — local operation is fully functional without network access.

---

## Failure Model

`shruggie-sync` must tolerate and recover from:

- Interrupted or partial uploads.
- Duplicate catalog commits.
- Partial batch failures.
- Network failures at any stage.
- Temporary catalog unavailability.
- Temporary vault unavailability.

The system always favors:

- **Consistency over convenience** — incomplete operations leave the system in a known, recoverable state.
- **Explicit reconciliation over implicit repair** — the system surfaces discrepancies and requires deliberate action to resolve them.

---

## Long-Term Extensibility

The following capabilities should be achievable through future extension without requiring changes to the identity model or core contracts:

- Multiple vault backends operating simultaneously.
- Multiple catalog instances (e.g., per-tenant, per-project).
- Vault-to-vault migration with integrity verification.
- Manifest export and import for portable asset sets.
- Snapshot materialization from catalog state.
- Immutable archival tiers with tiered access policies.

None of these capabilities require redefining content identity. The `IndexEntry` contract is the stable foundation on which all future extension is built.

---

## Uniform Ecosystem Conventions

The following conventions apply to **all** components in the ShruggieTech ecosystem. They are derived from the patterns established and battle-tested during the `shruggie-indexer` implementation. New components MUST adopt these conventions to maintain consistency and interoperability.

### Documentation Philosophy

All technical specifications and sprint planning documents are written **AI-first, Human-second**. The primary consumers are AI implementation agents operating within isolated context windows during sprint-based development. Every section provides sufficient detail for an AI agent to produce correct, complete code without interactive clarification.

- The technical specification for each component is the **single source of truth** for that component's behavioral contract.
- When the specification and the implementation disagree, the specification is presumed correct unless a deliberate amendment has been made.
- Specifications are maintained as living documents alongside the codebase. Updates SHOULD be committed alongside the code changes they describe.

### Requirement Level Keywords

All specifications use the keywords defined in RFC 2119 to indicate requirement levels:

| Keyword | Meaning |
|---------|---------|
| **MUST** / **MUST NOT** | Absolute requirement or prohibition. Non-conformant if violated. |
| **SHALL** / **SHALL NOT** | Synonymous with MUST / MUST NOT. |
| **SHOULD** / **SHOULD NOT** | Strong recommendation. Deviation must be deliberate and understood. |
| **MAY** | Truly optional. |

These keywords are capitalized when used in their RFC 2119 sense. Lowercase usage carries ordinary English meaning.

### Typographic and Cross-Reference Conventions

- `Monospace text` denotes code identifiers, file paths, CLI flags, configuration keys, and literal values.
- **Bold text** denotes emphasis or key terms being defined.
- *Italic text* denotes document titles, variable placeholders, or first use of a defined term.
- `§N.N` denotes a cross-reference to a section within the same specification.

### Specification Status Lifecycle

| Status | Meaning |
|--------|---------|
| `DRAFT` | Under active development. Sections may be incomplete. |
| `REVIEW` | Believed complete; undergoing review for correctness and consistency. |
| `APPROVED` | Reviewed and accepted as the implementation target. |
| `AMENDED` | Modified after initial approval to reflect post-release changes. |

### File Encoding and Line Endings

All source files, configuration files, output files, documentation files, and specification documents produced by any ecosystem tool MUST use:

- **UTF-8 encoding without BOM.**
- **LF (Unix) line endings.**

This is a hard invariant. Mojibake from CP1252/UTF-8 mismatches has been a recurring issue and requires explicit verification. Output functions MUST use `encoding="utf-8"` explicitly — never rely on platform defaults.

### Repository Organization

Each component repository follows a consistent top-level structure:

```
<component>/
├── .archive/                   # Sprint docs, historical planning, prompt templates
├── .github/
│   └── workflows/              # CI and release pipelines
├── docs/                       # MkDocs documentation source
├── scripts/                    # Build scripts, utilities
├── src/<package_name>/         # Source code (src layout)
├── tests/                      # Test suite
├── .gitignore
├── CHANGELOG.md
├── LICENSE
├── mkdocs.yml
├── pyproject.toml
├── README.md
└── <component>-spec.md         # Authoritative technical specification
```

### Archive Directory Naming Convention

All files in `.archive/` follow a strict naming pattern:

```
<YYYYmmdd>-<ZZZ>-<title>.<ext>
```

| Component | Description |
|-----------|-------------|
| `YYYYmmdd` | Date the document was created. |
| `ZZZ` | Three-digit zero-padded increment (`001`, `002`, etc.). **Resets to `001` on each new date.** |
| `title` | Lowercase-hyphenated descriptive title. |
| `ext` | File extension. |

Related clusters of documents (e.g., a sprint doc and its prompt template) MAY share the same increment. Sprint documents use a "Batch N" label in their header corresponding to the date-scoped increment.

### Sprint Document Format

Sprint planning documents follow a consistent five-section structure:

1. **Header block** — project name, repository, author, date, target release, audience, predecessor reference.
2. **Purpose and ecosystem context** — what this sprint accomplishes and why, with a dependency diagram if relevant.
3. **Implementation ordering** — strict dependency-ordered sequencing with rationale for the ordering.
4. **Work item sections** — each section is a self-contained sprint suitable for a single AI coding agent context window, containing: problem statement with evidence, root cause analysis (for bug fixes), required changes with explicit file paths, affected file matrix, spec cross-references (`§X.Y` notation), acceptance criteria, and mandatory verification commands (grep-based evidence collection).
5. **Specification update directive** — always the last section; reflects all changes into the authoritative spec.

Each sprint document is paired with a `_TEMPLATE.txt` prompt file for AI coding agent sessions:

```
<YYYYmmdd>-<ZZZ>-<title>_TEMPLATE.txt
```

### AI Agent Session Discipline

Sprint documents are designed as explicit behavioral contracts for AI coding agents operating in isolated context windows:

- Agents MUST NOT trust prior implementation work without independent verification. Stale bytecode cache has previously masked source changes.
- Agents MUST use grep-based evidence collection to verify the current state of the codebase before making changes.
- Agents MUST verify acceptance criteria against actual runtime behavior, not assumed correctness from code inspection alone.
- Each sprint section is self-contained. An agent working on Section 3 should not need to have executed Sections 1–2, but MUST be told that those sections are complete.

### Python Version and Language Standards

All ecosystem components target **Python 3.12+** as the minimum version. This enables use of `tomllib` (stdlib TOML parser, 3.11+), modern type hint syntax, and other language features.

### Configuration Architecture

All ecosystem components use **TOML** as the configuration file format, parsed by Python's `tomllib` module. TOML is chosen over JSON (no comments, verbose), YAML (whitespace-sensitive, multiple dialects, requires third-party parser), and INI (no nested structures, no typed values).

**Layered override behavior** (lowest to highest priority):

1. Compiled defaults (always present; a Python module, not a TOML file).
2. User config directory (platform-specific; see Application Data Directory below).
3. Project-local config (searched upward from target directory).
4. CLI/API arguments (highest priority).

Configuration objects SHOULD be frozen (immutable) dataclasses. Unknown keys in user-provided TOML MUST be silently ignored (forward compatibility). Invalid values MUST produce clear error messages naming the offending key and value.

### Shared Ecosystem Namespace

All ecosystem components share the `shruggie-tech` namespace for application data. The directory hierarchy uses a two-level structure:

```
<platform_base>/shruggie-tech/
├── shared.toml                         # (future: cross-tool configuration)
├── shruggie-indexer/
│   ├── config.toml
│   ├── gui-session.json
│   └── logs/
├── shruggie-catalog/
│   ├── config.toml
│   └── logs/
├── shruggie-vault/
└── shruggie-sync/
```

A `shared.toml` file at the `shruggie-tech/` level is reserved for future cross-tool settings. Individual component directories live alongside it.

### Application Data Directory

Each component resolves its application data directory through a single canonical module (`app_paths.py` or equivalent). No other module may resolve application data paths independently.

| Platform | Base path | Environment variable |
|----------|-----------|---------------------|
| Windows | `%LOCALAPPDATA%\shruggie-tech\<component>\` | `LOCALAPPDATA` |
| Linux | `~/.config/shruggie-tech/<component>/` | `XDG_CONFIG_HOME` (fallback: `~/.config`) |
| macOS | `~/Library/Application Support/shruggie-tech/<component>/` | _(hardcoded)_ |

**Important:** On Windows, all data goes under `%LOCALAPPDATA%` (Local), not `%APPDATA%` (Roaming). Roaming sync is deprecated on Windows 11, and `platformdirs` defaults to Local.

### CLI Interface Conventions

All CLI interfaces use `click` as the argument parser. CLI contracts are the canonical interface — API and GUI layers are secondary.

**Core principles:**

- Content filtering flags are independent of output destination flags.
- `stdout` stays clean for structured output (JSON). All diagnostics go to `stderr`.
- Destructive operations require explicit opt-in flags. No destructive action is a default.
- `--dry-run` mode is available for any operation with side effects.

### Error Handling and Logging

All components use Python's standard `logging` module with a consistent hierarchy:

- Logger names follow the package structure: `shruggie_indexer.core.entry`, `shruggie_catalog.db.ingest`, etc.
- Log output goes to `stderr` (console) and optionally to persistent log files under `<app_data_dir>/logs/`.
- Log files use the naming pattern `YYYY-MM-DD_HHMMSS.log`.

**Dependency verification pattern:**

| Category | Failure mode |
|----------|-------------|
| Required CLI dependency (e.g., `click`) | Hard error with install instructions. |
| Required external binary (e.g., `exiftool`) | Warning + graceful degradation (null output for affected features). |
| Optional performance dependency (e.g., `orjson`) | Silent fallback to stdlib equivalent. |
| Development/test dependency (e.g., `pytest`) | Import error at test time only. |

### Testing Strategy

Test suites are organized by test type, not by source module:

| Category | Directory | Scope |
|----------|-----------|-------|
| Unit | `tests/unit/` | Individual functions in isolation. |
| Integration | `tests/integration/` | Full pipeline, end-to-end. |
| Conformance | `tests/conformance/` | Output structure against canonical schemas. |
| Platform | `tests/platform/` | OS-specific behavior. |

All tests run with a bare `pytest` invocation. `pyproject.toml` registers custom markers (`slow`, `platform_windows`, `platform_linux`, `platform_macos`, `requires_exiftool`, etc.) with `--strict-markers` to catch typos. Every behavioral contract in the specification SHOULD have a corresponding test.

### Packaging and Distribution

Ecosystem components are **not published to PyPI**. End users download pre-built executables from GitHub Releases.

**Packaging stack:**

- `pyproject.toml` as the single metadata and dependency declaration file.
- PyInstaller for standalone executables (CLI and GUI as separate build targets).
- GitHub Actions release pipeline triggered on `v*` tag pushes, with matrix builds for Windows (x64), Linux (x64), and macOS (arm64).
- Version string lives in a single `_version.py` file. All other references derive from it.
- `pyproject.toml` follows conventions established by `shruggie-feedtools` for scaffolding. Divergences are documented explicitly.

**Release pipeline stages:** Checkout → Test → Build (PyInstaller) → Rename artifacts (version + platform tags) → Upload → Create GitHub Release.

### Documentation Site

All components use **MkDocs** with the **Material for MkDocs** theme. Dark mode (`slate` scheme) is enabled. Required extensions: `admonition`, `pymdownx.details`, `pymdownx.superfences`.

The documentation source lives in `docs/` within each repository. `CHANGELOG.md` at the repository root is auto-copied to the docs site during CI build. The docs site is deployed via GitHub Pages from a `gh-pages` branch managed by GitHub Actions.

### JSON Conventions

- All JSON output uses UTF-8 encoding without BOM.
- Serializers SHOULD use compact formatting for production output.
- `schema_version` is placed first in serialized output by convention (JSON objects are unordered, but consistent key ordering aids human readability).
- `null` is used (not omitted) for explicitly absent values on required fields. Optional fields that are `None` are omitted from output.
- Non-ASCII characters are preserved as literal UTF-8 — not escaped to `\uXXXX` sequences.
- `orjson` is preferred for performance where available, with `json.dumps()` as a silent fallback.

### Version Numbering

All ecosystem components follow semantic versioning (`MAJOR.MINOR.PATCH`). Pre-release versions use suffixes like `-rc1`. The version string is the single source from which all references (pyproject.toml, `__init__.py`, CLI `--version` output, etc.) derive.

---

## Implementation Guidance

When generating code for any component in this ecosystem, the following constraints are invariant:

- Maintain strict separation of responsibilities as defined above. A component must not absorb logic belonging to a neighbor.
- Avoid shared mutable state across utilities.
- Favor explicit JSON contracts over implicit in-process coupling.
- Design CLI interfaces first; API and daemon layers are secondary.
- Keep API layers as thin transports over CLI logic. Do not implement independent behavior at the API layer.
- All destructive operations (delete, prune, overwrite) must require explicit opt-in flags. No destructive action is a default.
- All files produced by tooling must use UTF-8 encoding without BOM.
- Evidence-based debugging: runtime logs and filesystem state are the primary diagnostic tools. Root causes must be traced through evidence, not assumed.
- No silent data loss: all destructive operations require explicit opt-in. Duplicate removal must preserve complete provenance — never silently delete metadata.

---

## Summary

This ecosystem is not a monolith. It is a set of composable primitives built around deterministic, content-addressed identity.

> The **indexer** defines truth.
> The **vault** preserves truth.
> The **catalog** records truth.
> **Sync** propagates truth.

No component is permitted to redefine it.

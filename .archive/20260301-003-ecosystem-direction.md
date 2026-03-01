# ShruggieTech Asset Ecosystem — Project Direction

## Audience

This document is written AI-first and human-second.

It defines architectural intent, invariant boundaries, and system philosophy for the ShruggieTech asset ecosystem. It is not a marketing description or a feature specification. It is a directional document intended to constrain future implementation decisions and guide AI-assisted development.

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

`shruggie-indexer` operates on local files and directories. It produces `IndexEntry` JSON records — structured metadata objects that serve as the authoritative description of a content object throughout the rest of the ecosystem.

**Responsibilities:**
- Compute deterministic content identity (`id`, `storage_name`) via hash of file bytes.
- Extract file metadata (MIME type, size, timestamps, format-specific fields via ExifTool).
- Produce well-formed `IndexEntry` v2 JSON output.
- Perform single-session, content-addressed de-duplication during rename operations. Duplicate files are deleted; their complete identity metadata is preserved in the canonical entry's `duplicates` array. This dedup scope is strictly bounded to a single runtime invocation.

**Non-responsibilities:**
- No storage management.
- No reference tracking.
- No orchestration.
- No cross-session de-duplication. The indexer has no knowledge of entries produced by prior invocations. Cross-session dedup — detecting that a file indexed today is identical to one indexed last month — is the catalog's responsibility.

**Invariants:**
- Given the same bytes, the same `IndexEntry` identity fields are always produced.
- `IndexEntry` output is the primary artifact this tool emits. When Rename mode is active, the tool also performs filesystem mutations: renaming files to their content-addressed `storage_name` and, as a consequence of rename, deleting byte-identical duplicate files whose identity metadata has been preserved in the canonical entry's `duplicates` array. These mutations are gated behind the explicit `--rename` flag — they never occur in the default mode.

---

### shruggie-vault

**Role within the ecosystem:** Byte storage. Preserves truth.

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
- Pruning is always explicit — the vault never autonomously delete content.

**Standalone usefulness:**
- Functions as a general-purpose content-addressed storage tool independent of any catalog.
- Verifies storage integrity independently.
- Suitable for archival and deduplicated storage workflows on its own.

---

### shruggie-catalog

**Role within the ecosystem:** Metadata registry. Records truth.

A structured database of `IndexEntry` records and the references (collections, projects, users, snapshots) that point to them.

**Responsibilities:**
- Store and retrieve full `IndexEntry` JSON records.
- Project and index searchable fields (MIME type, size, timestamps, format-specific metadata, etc.).
- Track logical references to assets:
  - Collections
  - Projects
  - Users / Tenants
  - Snapshots
- Provide search and query capability over indexed fields.
- Reconcile catalog contents against a vault (detect missing or orphaned blobs).
- Perform cross-session de-duplication by maintaining a persistent `DedupRegistry` backed by its database. When new `IndexEntry` records are ingested, the catalog checks them against all previously cataloged entries. The catalog reuses the indexer's `core.dedup` module (`DedupRegistry`, `scan_tree()`, `apply_dedup()`) for this purpose — the detection and merge logic is identical; only the registry lifetime and scope differ.

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

**Standalone usefulness:**
- Functions as an asset inventory system independent of where bytes actually live.
- Operates in read-only mode for analysis or auditing.
- Provides a durable metadata record that survives storage backend migration.

---

### shruggie-sync

**Role within the ecosystem:** Orchestration. Propagates truth.

`shruggie-sync` connects the other three components into a coherent, reliable workflow. It is the primary operational surface for end users running ingestion pipelines.

**Responsibilities:**
- Accept directory or file targets as input.
- Invoke `shruggie-indexer` to produce `IndexEntry` records for each target. (Sync drives the workflow; indexer performs identity computation.)
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

## De-Duplication Scope Boundaries

Content-addressed de-duplication operates at two distinct scopes within the ecosystem:

| Scope | Component | Registry lifetime | Detects |
|-------|-----------|-------------------|---------|
| Single session | Indexer | One CLI/GUI/API invocation | Duplicates within a single directory tree processed in one run |
| Cross-session | Catalog | Persistent (database-backed) | Duplicates across all previously cataloged entries, regardless of when or where they were indexed |

The indexer's dedup module (`shruggie_indexer.core.dedup`) provides the shared implementation for both scopes. The indexer creates a fresh `DedupRegistry` per invocation; the catalog pre-populates the registry from its database before processing new entries.

This separation ensures that:
- The indexer remains standalone and stateless between runs.
- The catalog is the single authority for cross-session identity resolution.
- The dedup logic is implemented once and reused, not reimplemented in each component.

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

## Implementation Guidance

When generating code for any component in this ecosystem, the following constraints are invariant:

- Maintain strict separation of responsibilities as defined above. A component must not absorb logic belonging to a neighbor.
- Avoid shared mutable state across utilities.
- Favor explicit JSON contracts over implicit in-process coupling.
- Design CLI interfaces first; API and daemon layers are secondary.
- Keep API layers as thin transports over CLI logic. Do not implement independent behavior at the API layer.
- All destructive operations (delete, prune, overwrite) must require explicit opt-in flags. No destructive action is a default.
- All files produced by tooling must use UTF-8 encoding without BOM.

---

## Summary

This ecosystem is not a monolith. It is a set of composable primitives built around deterministic, content-addressed identity.

> The **indexer** defines truth.
> The **vault** preserves truth.
> The **catalog** records truth.
> **Sync** propagates truth.

No component is permitted to redefine it.

## 18. Future Considerations

This section catalogs enhancements, extensions, and architectural evolution paths that are explicitly deferred from the v0.1.0 (MVP) release. Every item listed here has been referenced from at least one normative section of this specification — this section consolidates those references into a single planning document, describes each item's scope and preconditions, and identifies the architectural constraints that govern how the item can be added without disrupting the existing system.

This section is informational, not normative. Nothing described here constitutes a commitment to implement. The items are organized by likelihood and dependency order: §18.1 covers concrete feature additions that the MVP architecture already supports structurally; §18.2 covers output schema evolution, which has broader compatibility implications; §18.3 covers a plugin or extension architecture, which would be the most significant structural change and is therefore the most speculative.

### 18.1. Potential Feature Additions

This subsection collects every post-MVP enhancement that has been identified during specification development, organized by the functional area of the codebase that would be affected. Each item includes the originating reference, a description of what the enhancement involves, the preconditions or dependencies that must be satisfied before implementation, and an assessment of the architectural impact — whether the enhancement fits cleanly within the existing module boundaries or requires structural changes.

#### 18.1.1. v1-to-v2 Migration Utility

**Originating references:** §1.2 (Out of Scope), §2.3 (G7, NG2), §5.5, §5.13 (Backward Compatibility).

This is the most clearly defined post-MVP deliverable. The utility converts existing v1 index sidecar files (`_meta.json`, `_directorymeta.json`) to the v2 format (`_meta2.json`, `_directorymeta2.json`). The conversion is lossy in one direction: v1 fields dropped in v2 (`Encoding`, `BaseName`, `SHA1` hashes) are discarded. It is enriching in the other: v2 fields with no v1 equivalent (`schema_version`, `id_algorithm`, `type`, `mime_type`, `size.text`, `file_system.relative`, and all `MetadataEntry` provenance fields) are populated with computed or default values where possible and `null` where not.

The migration utility is a standalone command — likely a new CLI subcommand (`shruggie-indexer migrate`) or a separate script in the `scripts/` directory. It does NOT require modifications to the core indexing engine or the v2 dataclass definitions. The primary implementation challenge is correctly identifying v1 documents (by the absence of `schema_version` or the presence of v1-specific fields like `_id` with its `y`/`x` prefix) and mapping v1's flat PascalCase fields to v2's nested snake_case sub-objects.

**Preconditions:** The v2 schema and output pipeline must be stable. The utility should not ship until the MVP has been validated against the v2 schema in production-like usage, confirming that the v2 field semantics are correct and complete.

**Architectural impact:** Low. The utility consumes the existing `models/schema.py` dataclasses for v2 output construction and the `core/serializer.py` module for JSON output. It adds a new module (e.g., `tools/migrate.py` or `cli/commands/migrate.py`) with no changes to existing modules.

#### 18.1.2. Rename Revert Operation

**Originating references:** §6.10 (File Rename and In-Place Write Operations).

The original's source comments include a "To-Do" note about adding a `Revert` parameter. The v2 schema's enriched `MetadataEntry` provenance fields (§5.10, principle P3) and the in-place sidecar files provide the data foundation for reversal: the sidecar file written alongside each renamed item records the original filename in `name.text`, allowing a revert operation to reconstruct the original path.

A `revert_rename()` function would read the sidecar's `name.text` field and rename the file back to its original name. The implementation is straightforward — iterate sidecar files in a target directory, parse each one, extract `name.text`, and rename the associated storage-named file back to its original name. The primary complexity is conflict detection: if the original filename already exists (because a different file now occupies that name), the revert must fail gracefully for that file.

**Preconditions:** The rename operation (§6.10) and in-place write mode (§6.9) must be stable and producing correct sidecar files with complete `name.text` provenance.

**Architectural impact:** Low. A new function in `core/rename.py` (or a new `core/revert.py` module), a new CLI flag (`--revert`), and corresponding API surface. No changes to existing modules beyond adding the new entry point.

#### 18.1.3. Exiftool Batch Mode via PyExifTool

**Originating references:** §6.6, §12.3, §16.3, §17.5.

The MVP invokes `exiftool` as a separate `subprocess.run()` call for each eligible file. For directories with thousands of media files, process startup overhead dominates runtime. The `pyexiftool` library's `-stay_open` mode keeps a single Perl process alive across multiple file inputs, reducing per-file cost from 200–500 ms (process startup) to 20–50 ms (metadata extraction only).

The batch mode implementation is deferred to post-MVP for three reasons documented in §17.5: it breaks per-file error isolation, it changes the invocation model from synchronous to batched or asynchronous, and the per-file approach is correct and sufficient. The upgrade path is clean because `core/exif.py` already encapsulates all exiftool interaction behind the `extract_exif()` interface — swapping the backend from subprocess-per-file to `pyexiftool` batch mode is an implementation change within a single module.

**Preconditions:** The `perf` extra must be declared in `pyproject.toml` (it already is, §12.3). The batch mode wrapper must implement reconnection logic for process failures and per-file timeout enforcement. The selection between batch and per-file mode should be logged at `DEBUG` level.

**Architectural impact:** Low. Changes are confined to `core/exif.py`. The module already contains the import guard structure (`try: import exiftool as pyexiftool / except ImportError: pyexiftool = None`). The public `extract_exif()` interface does not change.

#### 18.1.4. CLI Graceful Interrupt Handling (SIGINT)

**Originating references:** §10.5 (GUI cancellation), §8.10 (Exit Codes).

The GUI defines a cancellation mechanism (§10.5) that interrupts the indexing loop between items and raises `IndexerCancelled`. The CLI does not currently support mid-operation cancellation — a `SIGINT` (Ctrl+C) terminates the process immediately, potentially leaving partially-written output files.

A graceful interrupt handler would register a `signal.signal(signal.SIGINT, ...)` handler that sets a cancellation flag checked at item boundaries in the traversal loop. When triggered, the handler would complete the current item, write partial output (for `--outfile` or `--inplace` modes), clean up any open file handles, and exit with a distinct exit code indicating interrupted operation.

**Preconditions:** The item-level error boundary (§4.5) already provides the check-point structure — the cancellation flag check is a natural addition to the existing per-item try/except boundary. The `--inplace` mode already writes incrementally, so partial output is inherently safe. The `--outfile` and `--stdout` modes require a decision about whether to write a partial tree or discard everything.

**Architectural impact:** Low to moderate. A signal handler in `cli/main.py`, a cancellation flag threading through the orchestrator, and a new exit code. The GUI's `IndexerCancelled` exception (§10.5) may be reusable for both surfaces.

#### 18.1.5. Depth-Limited Recursion

**Originating references:** §9.2 (Core Functions architectural note).

The `recursive` parameter on `build_directory_entry()` is a boolean. A depth-limited variant (`max_depth=N`) would allow users to index only the top N levels of a directory tree, which is useful for large repository checkouts or deeply nested media libraries where only the top-level structure is of interest.

The implementation is straightforward: replace the boolean `recursive` parameter with an integer depth counter that decrements at each level. When the counter reaches zero, child directories are listed but not entered. The CLI would expose this as `--depth N` (or `--max-depth N`), with the default being unlimited (`None` or `-1`).

**Preconditions:** None beyond a stable recursive traversal implementation.

**Architectural impact:** Low. A parameter type change in `core/entry.py` and `core/traversal.py`, a new CLI flag, and a corresponding API parameter. The recursive call structure does not change — only the recursion guard condition.

#### 18.1.6. Unicode Normalization Flag

**Originating references:** §15.2 (Filesystem Behavior Differences).

macOS's HFS+ and APFS filesystems store filenames in NFD (decomposed) Unicode normalization form, while Windows NTFS and most Linux filesystems store them as-provided (often NFC). This means the same logical filename can produce different hash values on different platforms, because the raw UTF-8 bytes fed to `hash_string()` differ.

A `--normalize-unicode` CLI flag (or `normalize_unicode` config option) would force NFC normalization on all filename strings before hashing. This would ensure cross-platform hash consistency at the cost of breaking the invariant that re-indexing the same file on the same filesystem always produces the same identity (if the filesystem stores NFD and the tool normalizes to NFC, the hashed string differs from the stored filename).

**Preconditions:** None. Python's `unicodedata.normalize('NFC', name)` provides the normalization primitive.

**Architectural impact:** Low. A conditional `unicodedata.normalize()` call in `core/hashing.hash_string()`, gated by a config flag. The config system, CLI parser, and API surface each gain one additional option.

#### 18.1.7. Windows `.lnk` Shortcut Resolution

**Originating references:** §12.4 (Eliminated Original Dependencies — `Lnk2Path`).

The original resolves Windows `.lnk` shortcut files to their target paths via the `Lnk2Path` function, which uses COM interop. The cross-platform port treats `.lnk` files encountered as sidecar content as opaque binary data and Base64-encodes them.

A post-MVP enhancement could add `.lnk` resolution on Windows using the optional `pylnk3` package (or COM interop via `win32com`). The resolution would extract the target path from the shortcut and store it as the sidecar's `data` field instead of the raw binary content. On non-Windows platforms, the fallback to Base64 encoding would remain.

**Preconditions:** A suitable `.lnk` parsing library must be identified. `pylnk3` is the most common pure-Python option. The enhancement should be gated by an import guard, similar to the `pyexiftool` pattern.

**Architectural impact:** Low. Changes confined to `core/sidecar.py` (or the metadata read logic for link-type sidecars). A new optional dependency declared in `pyproject.toml`.

#### 18.1.8. Exiftool Runtime Version Checking

**Originating references:** §12.1 (Required External Binaries).

The port requires exiftool ≥ 12.0 for the `-api requestall=3` and `-api largefilesupport=1` arguments but does not enforce version checking at runtime. An older exiftool will likely work for most files but may produce incomplete metadata.

A version check would invoke `exiftool -ver` once at startup (alongside the existing `shutil.which()` availability probe), parse the version string, and emit a warning if the version is below the minimum. The check cost is negligible — one additional subprocess invocation per process lifetime, completed in under 100 ms.

**Preconditions:** A stable exiftool availability probe (§17.5) must be in place. The version check should run immediately after the availability probe succeeds.

**Architectural impact:** Minimal. A few lines added to the exiftool availability probe in `core/exif.py`.

#### 18.1.9. Configurable Exiftool Timeout

**Originating references:** §6.6, §17.5.

The 30-second exiftool timeout is currently a hardcoded constant. If users encounter legitimate timeout hits on files that exiftool can process (just slowly) — such as very large video files with deeply nested metadata — the timeout could be exposed as a configuration parameter.

**Preconditions:** User reports of legitimate timeout hits. Without evidence of real-world need, adding a configuration surface for this value is premature.

**Architectural impact:** Minimal. A new field in `IndexerConfig`, passed through to `subprocess.run(timeout=...)`.

#### 18.1.10. Structured Performance Tracking

**Originating references:** §14.7 (Performance Benchmarks).

The MVP's benchmarks produce unstructured timing output reviewed manually. A post-MVP enhancement could integrate `pytest-benchmark` for structured performance tracking with statistical analysis, historical trend lines, and automated regression detection.

**Preconditions:** A stable benchmark suite and a CI pipeline that preserves benchmark results across runs.

**Architectural impact:** Minimal. A new dev dependency, benchmark fixture changes in `tests/benchmarks/`, and CI configuration updates. No changes to production code.

#### 18.1.11. Platform-Specific Installers

**Originating references:** §13.5 (Release Artifact Inventory).

The MVP distributes standalone executables. Platform-specific installers (`.msi` for Windows, `.dmg` for macOS, `.deb`/`.rpm` for Linux) would improve user experience with features like Start Menu integration, Applications folder placement, and package manager updates.

**Preconditions:** A stable release pipeline and executable build process. Installer creation tools (`WiX` for `.msi`, `create-dmg` for `.dmg`, `fpm` for Linux packages) must be integrated into the GitHub Actions workflow.

**Architectural impact:** None to production code. Build pipeline additions only.

#### 18.1.12. Formal Accessibility Improvements

**Originating references:** §10.7 (Keyboard Shortcuts and Accessibility).

The MVP makes reasonable accommodations for keyboard-only operation but does not target formal accessibility compliance (WCAG, Section 508). CustomTkinter inherits `tkinter`'s native accessibility support, which varies by platform — Windows provides the best screen reader integration via UI Automation, while Linux/macOS support is limited.

Formal accessibility work would involve audit against WCAG guidelines, addition of ARIA-equivalent labels where CustomTkinter supports them, high-contrast theme variants, and screen reader testing on all three platforms.

**Preconditions:** A stable GUI implementation and user feedback indicating accessibility is a priority.

**Architectural impact:** Moderate within the GUI layer (`gui/`). No impact on the core engine or CLI.

#### 18.1.13. End-User Documentation

**Originating references:** §3.6 (Documentation Artifacts).

The `docs/user/` directory is a post-MVP deliverable. For the v0.1.0 release, user-facing documentation is limited to the `README.md` at the repository root. A complete documentation set would include an installation guide, usage examples, configuration reference, and changelog.

**Preconditions:** A stable CLI interface and configuration system. Documentation written against an unstable interface creates maintenance burden.

**Architectural impact:** None. Documentation artifacts only.

#### 18.1.14. Session ID in JSON Output

**Originating references:** §11.4 (Session Identifiers).

The session ID (a UUID4 generated per invocation) currently appears only in log output. A future schema version could include it in the JSON output metadata to link an index entry back to the invocation that produced it. This would support provenance tracking — given an index file, a user could correlate it with the log output from the run that created it.

This item is deliberately listed as a feature addition rather than a schema evolution item (§18.2) because it is a purely additive field that does not change existing semantics. It could be added as a new top-level field (e.g., `session_id`) in the v2 schema without breaking backward compatibility, or it could be deferred to a v3 schema if it accompanies other breaking changes.

**Preconditions:** Confirmation that the session ID is useful to downstream consumers. The field adds bytes to every output file for a benefit that may be niche.

**Architectural impact:** Minimal. A new field on the `IndexEntry` dataclass, populated by the orchestrator from the session context.

### 18.2. Schema Evolution

The v2 output schema includes a `schema_version` discriminator field (§5.3) whose express purpose is to enable schema evolution. The discriminator allows consumers to detect the schema version before parsing and to dispatch to version-specific parsing logic. This subsection describes the principles governing schema evolution, the known candidates for a future v3 schema, and the compatibility constraints that any schema change must satisfy.

#### 18.2.1. Evolution Principles

**Additive changes are non-breaking.** A new optional field added to an existing object (e.g., a `session_id` field on `IndexEntry`, or a `created_source` field on `TimestampsObject`) does not break existing consumers. Consumers that do not recognize the field ignore it. The `schema_version` value does not need to change for purely additive fields — the v2 schema's `additionalProperties: false` constraint would need to be relaxed or the canonical JSON Schema updated to include the new field, but the discriminator value can remain `2` as long as no existing field's semantics change.

**Structural changes require a version bump.** Any change that renames a field, changes a field's type, removes a required field, or alters the semantic meaning of an existing field constitutes a breaking change and MUST increment `schema_version`. Consumers dispatch on `schema_version` and expect the fields listed for that version.

**Deprecation before removal.** If a v2 field is to be removed in v3, a transition period should be provided: the field is marked as deprecated in v2.x documentation, emitted but ignored by the tool, and finally removed in v3. The migration utility pattern established for v1-to-v2 (§18.1.1) should be replicated for any future version transition.

**Schema-version-specific serialization.** The serializer (§6.9) currently hardcodes `schema_version: 2`. If a future version supports emitting multiple schema versions (e.g., a `--schema-version 3` flag for early adopters), the serializer must dispatch to version-specific field sets and object structures. This is a non-trivial change and should be avoided unless there is a compelling reason to support concurrent version output.

#### 18.2.2. Candidate v3 Additions

The following fields have been identified during specification development as candidates for future schema versions. None of these are committed — they are recorded here so that future development can evaluate them against actual user needs.

**`timestamps.created_source`** (§15.5). A string field on `TimestampsObject` indicating the provenance of the creation timestamp — `"birthtime"` when derived from `st_birthtime` (macOS, Windows) or `"ctime_fallback"` when derived from `st_ctime` (Linux, where `ctime` represents the last inode change, not creation). This field would resolve the ambiguity documented in §15.5 about what `timestamps.created` actually represents on different platforms.

**`session_id`** (§18.1.14). A UUID4 string linking the index entry to the invocation that produced it. See §18.1.14 for the full description. This is additive and could be added to v2 without a version bump.

**`encoding`** (§5.11). If encoding detection becomes a requirement, a new field with a Python-native structure (not the .NET-specific `System.Text.Encoding` serialization from v1) would be added. The structure might include `bom` (detected BOM, if any), `detected_encoding` (best-guess encoding name from `chardet` or similar), and `confidence` (detection confidence score). This would be a new top-level field — not a restoration of the v1 `Encoding` field, which is explicitly dropped without replacement.

**`type` enum extension** (§5.4). The `type` field currently uses a two-value string enum (`"file"`, `"directory"`). The enum was designed as extensible (§5.4) — a future version could add `"symlink"` as a distinct type rather than a boolean flag, allowing consumers to dispatch on item type without checking a separate symlink field. This would be a semantic change to the `type` field (expanding its value set) and should be handled carefully: existing consumers that switch on `type` and assume only two values would need updating.

#### 18.2.3. Compatibility Strategy

The v2 schema's design already accommodates the most likely evolution paths:

The `schema_version` discriminator enables version detection. The `type` field uses a string enum rather than a boolean, enabling value-set expansion. The `MetadataEntry.origin` field uses a string enum (`"sidecar"`, `"generated"`) that can be extended with new origin types. The `HashSet` object's `sha512` field demonstrates the pattern for optional algorithm-specific fields — additional algorithms can be added as new optional properties without breaking consumers that expect only `md5` and `sha256`.

The v2 sidecar filename convention (`_meta2.json`, `_directorymeta2.json`) embeds the schema version in the filename. A v3 schema would use `_meta3.json` and `_directorymeta3.json`, allowing v2 and v3 sidecar files to coexist on disk. This is the same coexistence pattern used for the v1-to-v2 transition (§5.13).

### 18.3. Plugin or Extension Architecture

The MVP does not include a plugin system. All behavior is compiled into the package — sidecar parsers, hash algorithms, metadata extractors, and output formatters are all defined in the core modules and configured through the externalized configuration system (§7). This subsection evaluates whether a plugin architecture is warranted, what it would look like, and under what conditions it should be considered.

#### 18.3.1. Current Extensibility Mechanisms

The MVP already provides meaningful extensibility through configuration rather than code:

The sidecar discovery system (§7.3) uses regex patterns defined in configuration. Adding a new sidecar type requires adding a new regex pattern and type definition to the configuration file — no code changes. The exiftool exclusion list (§7.4) is similarly configurable. The filesystem exclusion filters (§7.2) allow users to add platform-specific or project-specific directory exclusions. The extension validation regex (§7.5, DEV-14) is externalized for the same reason.

These configuration-driven extension points cover the most common customization needs: "I have a new metadata file pattern that the indexer doesn't recognize" and "I have files or directories that should be excluded." For these use cases, the configuration system is the correct mechanism — a plugin architecture would be overengineering.

#### 18.3.2. Where Plugins Would Add Value

A plugin architecture would become valuable if users need to extend the indexer's behavior in ways that configuration cannot express:

**Custom metadata extractors.** The MVP extracts metadata via exiftool (for embedded EXIF/XMP data) and via the sidecar parser (for external metadata files). If users need to extract metadata from domain-specific formats that exiftool does not support — such as proprietary CAD file metadata, scientific data file headers (HDF5, NetCDF), or application-specific config files — a plugin interface for metadata extractors would allow them to register a callable that receives a file path and returns a `MetadataEntry` (or `None`).

**Custom output formatters.** The MVP outputs JSON exclusively. If downstream consumers need CSV, XML, SQLite, or protocol buffer output, a formatter plugin interface would allow custom serializers to be registered alongside the built-in JSON serializer.

**Custom identity schemes.** The MVP computes identity from content hashes (MD5, SHA256, optionally SHA512). Some use cases may require alternative identity schemes — e.g., BLAKE3 for performance, or content-addressable storage identifiers that combine hash with size. A hash algorithm plugin interface would allow new algorithms to be registered and included in `HashSet` output.

#### 18.3.3. Recommended Approach

If a plugin architecture is pursued, the recommended approach is a lightweight entry-point-based system using Python's `importlib.metadata.entry_points()` (available in Python ≥ 3.12, the project's baseline). Plugins would be installed as separate Python packages that declare entry points in their `pyproject.toml`:

```toml
# In a hypothetical shruggie-indexer-hdf5 plugin's pyproject.toml:
[project.entry-points."shruggie_indexer.extractors"]
hdf5 = "shruggie_indexer_hdf5:extract_hdf5_metadata"
```

The indexer would discover installed plugins at startup via `entry_points(group="shruggie_indexer.extractors")` and register them alongside the built-in extractors. This approach requires no changes to the indexer's core architecture — the discovery is additive, the plugin callable conforms to an interface defined by the indexer, and uninstalling the plugin removes the behavior.

This is the standard Python pattern for extensible applications (used by `pytest`, `setuptools`, `tox`, and many others). It does not require a custom plugin loader, a plugin directory, or a plugin configuration file — the Python packaging system handles discovery and installation.

#### 18.3.4. When to Implement

A plugin architecture should NOT be implemented speculatively. The configuration-based extensibility in the MVP covers the known customization needs. The plugin architecture should be pursued only when concrete user requests demonstrate a need that configuration cannot satisfy — specifically, when users need to run custom Python code as part of the indexing pipeline, not just adjust parameters.

The architectural preparation for a future plugin system is minimal: the hub-and-spoke module design (§4.2) already isolates each functional area behind a defined interface (`extract_exif()`, `discover_sidecars()`, `hash_file()`, `serialize_entry()`). Converting any of these interfaces to a plugin dispatch point requires adding an entry-point discovery step at module initialization and iterating over registered plugins alongside the built-in implementation. The structural refactoring cost is low when the need materializes.

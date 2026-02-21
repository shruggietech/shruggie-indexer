# shruggie-indexer Documentation Buildout — Agent Prompt & Planning

This document contains three sections:

1. **The Prompt** — Copy/paste into VS Code chat for the AI coding agent
2. **Navigation Restructure** — Exact mappings for what changes in `mkdocs.yml` and `docs/`
3. **Spec-to-Docs Reference Map** — Source references for populating each docs page

---

## Section 1: Agent Prompt

The prompt below is designed to be self-contained. Copy everything between the `---BEGIN PROMPT---` and `---END PROMPT---` markers.

---BEGIN PROMPT---

## Task: Documentation Site Buildout for shruggie-indexer v0.1.0

You are working on the documentation site for `shruggie-indexer`, a cross-platform Python tool that produces structured JSON index entries for files and directories — capturing hash-based identities, timestamps, EXIF metadata, sidecar metadata, and filesystem attributes in a v2 schema format. The tool ships as a CLI utility, Python library, and standalone GUI application.

The docs site uses MkDocs with Material for MkDocs and is deployed to GitHub Pages. The site infrastructure is already in place but most user-facing pages are stubs. Your job is to populate them with real content and restructure the navigation to lead with user-facing material.

**IMPORTANT FRAMING NOTE:** This is a released, standalone project (v0.1.0 is published). Do NOT describe the project primarily as "a port of" or "a reimplementation of" something else. The project originated as a reimplementation of a PowerShell tool, and that history can be mentioned in context (e.g., in the Porting Reference section or as brief background), but all primary descriptions should present shruggie-indexer on its own terms — what it does, how it works, and why someone would use it. The homepage, user guide, and all user-facing pages should describe the tool's capabilities directly.

### Source Material

Use the following files as authoritative sources for content. Read each one before writing the pages that reference it.

| Source File | What to Extract |
|-------------|-----------------|
| `shruggie-indexer-spec.md` (§2.3) | Design goals G1–G7, Non-goals NG1–NG6 |
| `shruggie-indexer-spec.md` (§4) | Architecture overview, module decomposition, data flow, processing pipeline |
| `shruggie-indexer-spec.md` (§5) | V2 schema: design principles P1–P5, reusable types, all field groups |
| `shruggie-indexer-spec.md` (§6) | Core operations: traversal, hashing, timestamps, exif, sidecar, entry construction, serialization, rename |
| `shruggie-indexer-spec.md` (§7) | Configuration: architecture, defaults, MetadataFileParser, TOML format, override/merge behavior |
| `shruggie-indexer-spec.md` (§8) | CLI: command structure, all options/flags, mutual exclusions, output scenarios, exit codes |
| `shruggie-indexer-spec.md` (§9) | Python API: public surface, core functions, configuration API, data classes, usage examples |
| `shruggie-indexer-spec.md` (§12) | External dependencies: exiftool, stdlib modules, third-party packages, eliminated deps |
| `shruggie-indexer-spec.md` (§15) | Platform portability: Windows/Linux/macOS considerations, creation time, symlinks |
| `src/shruggie_indexer/cli/main.py` | Live CLI option definitions (verify against spec §8) |
| `CHANGELOG.md` | Release history |
| `README.md` | Current project description (for reference — you'll be writing better content) |
| `docs/schema/shruggie-indexer-v2.schema.json` | The canonical v2 JSON Schema file |
| `docs/schema/examples/flashplayer.exe_meta2.json` | Real-world v2 output example |

### Deliverables

Complete ALL of the following file operations. For existing files that are stubs, replace the content entirely. For new files, create them. Verify `mkdocs build` passes with `strict: true` before committing.

#### 1. Update `mkdocs.yml` — New Navigation Structure

Replace the existing `nav:` block with:

```yaml
nav:
  - Home: index.md
  - Getting Started:
      - Installation: getting-started/installation.md
      - Quick Start: getting-started/quickstart.md
      - ExifTool Setup: getting-started/exiftool.md
  - User Guide:
      - Overview: user-guide/index.md
      - CLI Reference: user-guide/cli-reference.md
      - Configuration: user-guide/configuration.md
      - Python API: user-guide/python-api.md
      - Platform Notes: user-guide/platform-notes.md
  - Schema Reference:
      - Overview: schema/index.md
  - Porting Reference:
      - Overview: porting-reference/index.md
      - Operations Catalog: porting-reference/MakeIndex_OperationsCatalog.md
      - Dependency Catalogs:
          - MakeIndex: porting-reference/MakeIndex_DependencyCatalog.md
          - Base64DecodeString: porting-reference/Base64DecodeString_DependencyCatalog.md
          - Date2UnixTime: porting-reference/Date2UnixTime_DependencyCatalog.md
          - DirectoryId: porting-reference/DirectoryId_DependencyCatalog.md
          - FileId: porting-reference/FileId_DependencyCatalog.md
          - MetaFileRead: porting-reference/MetaFileRead_DependencyCatalog.md
          - TempOpen: porting-reference/TempOpen_DependencyCatalog.md
          - TempClose: porting-reference/TempClose_DependencyCatalog.md
          - Vbs: porting-reference/Vbs_DependencyCatalog.md
  - Changelog: changelog.md
```

Also add the `navigation.sections` feature to the theme features list for better section grouping.

#### 2. Rewrite `docs/index.md` — Project Homepage

Write a proper project homepage that presents shruggie-indexer as a standalone tool. Structure:

- **Opening paragraph** — What the tool does in 2-3 sentences. No mention of porting. Focus: "shruggie-indexer produces structured JSON index entries for files and directories, capturing hash-based identities, filesystem timestamps, EXIF metadata, sidecar metadata, and storage attributes." Mention v2 schema, cross-platform, three delivery surfaces (CLI, Python API, GUI).
- **Key Features** — Brief descriptions (not a bullet dump). Cover: deterministic hash-based identity, multi-algorithm hashing (MD5/SHA-256/SHA-512), EXIF metadata extraction via exiftool, sidecar metadata discovery and merging, configurable TOML-based settings, cross-platform (Windows/Linux/macOS), structured v2 JSON output.
- **Quick Example** — A single CLI invocation and a snippet of the JSON output (use the real schema structure from §5.3).
- **Documentation Sections** — Links to Getting Started, User Guide, Schema Reference, with 1-sentence descriptions.
- **Quick Links** — GitHub repo, PyPI (if published), v2 JSON Schema canonical URL, Technical Specification link.

Remove ALL "Work in Progress" admonitions from this page.

#### 3. Create `docs/getting-started/` directory and move/create files

- **Move** `docs/user/installation.md` → `docs/getting-started/installation.md` and rewrite with full content.
- **Move** `docs/user/quickstart.md` → `docs/getting-started/quickstart.md` and rewrite with full content.
- **Create** `docs/getting-started/exiftool.md` (new page).

##### `docs/getting-started/installation.md` content:
Source: spec §2.4 (Platform Requirements), §2.5 (Python Version), §12 (Dependencies), §13 (Packaging)

Cover these topics with real content:
- System requirements: Python 3.12+, supported platforms (Windows, Linux, macOS)
- Install via pip: `pip install shruggie-indexer`
- Install with optional dependencies: `pip install shruggie-indexer[gui]` (for GUI), `pip install shruggie-indexer[dev]` (for development)
- Standalone executables: download from GitHub Releases, platform-specific binaries (Windows .exe, Linux binary, macOS ARM64 binary)
- Verification: `shruggie-indexer --version`
- Optional: exiftool installation (link to the ExifTool Setup page)

##### `docs/getting-started/quickstart.md` content:
Source: spec §8.1–§8.9 (CLI), §6 (Core Operations)

Cover with real examples:
- Index a single file: `shruggie-indexer /path/to/file.jpg`
- Index a directory: `shruggie-indexer /path/to/directory/`
- Recursive vs. non-recursive: `--recursive` / `--no-recursive`
- Save output to file: `--outfile index.json` or `-o index.json`
- Enable metadata extraction: `--meta` (exiftool), `--meta-merge` (sidecar merge), `--meta-merge-delete`
- Write in-place sidecar files: `--inplace`
- Rename files to storage names: `--rename` with `--dry-run` preview
- Choose ID algorithm: `--id-type md5` or `--id-type sha256`
- Output example: Show a representative JSON snippet from the v2 schema
- Link to the full CLI Reference for complete flag documentation

##### `docs/getting-started/exiftool.md` content:
Source: spec §6.6 (EXIF Extraction), §12.1 (Required External Binaries)

Cover:
- What exiftool is and why shruggie-indexer uses it
- How to install exiftool on each platform (Windows, Linux/apt, macOS/brew)
- How to verify installation: `exiftool -ver`
- Behavior when exiftool is not installed (graceful degradation — warning, not fatal)
- The `pyexiftool` batch mode vs. subprocess fallback (brief explanation of the two backends)
- The file extension exclusion list (which file types are skipped by default)

#### 4. Create `docs/user-guide/` directory and populate

- **Create** `docs/user-guide/index.md` (new landing page)
- **Create** `docs/user-guide/cli-reference.md` (new page)
- **Move** `docs/user/configuration.md` → `docs/user-guide/configuration.md` and rewrite
- **Create** `docs/user-guide/python-api.md` (new page)
- **Create** `docs/user-guide/platform-notes.md` (new page)

##### `docs/user-guide/index.md` content:
A landing page with brief descriptions linking to each sub-page. Remove ALL "Work in Progress" admonitions.

##### `docs/user-guide/cli-reference.md` content:
Source: spec §8 (CLI Interface) — this is the most detail-heavy page.

This should be the definitive CLI reference. Cover every option:
- Command structure: `shruggie-indexer [OPTIONS] [TARGET]`
- TARGET argument behavior (auto-detection, explicit `--file` / `--directory`)
- Target options: `--file`/`--directory`, `--recursive`/`--no-recursive`
- Output options: `--stdout`/`--no-stdout`, `--outfile`/`-o`, `--inplace`
- Metadata options: `--meta`/`-m`, `--meta-merge`, `--meta-merge-delete` (document the implication chain)
- Rename options: `--rename`, `--dry-run`
- Identity options: `--id-type`, `--compute-sha512`
- Configuration: `--config`
- Logging: `-v`/`--verbose` (repeatable), `-q`/`--quiet`
- General: `--version`, `--help`
- Mutual exclusion rules (§8.8)
- Output scenarios table (§8.9 — the 7 output mode combinations)
- Exit codes table (§8.10)
- Signal handling (§8.11)

Use admonitions for important notes (e.g., `--meta-merge-delete` implies `--meta-merge` implies `--meta`).

##### `docs/user-guide/configuration.md` content:
Source: spec §7 (Configuration)

Replace the stub with full content:
- Configuration hierarchy: CLI flags > config file > built-in defaults
- Config file format: TOML, loaded via `--config` flag or default location
- Default configuration values (document all defaults from §7.2)
- MetadataFileParser configuration: sidecar suffix patterns, type identification rules (§7.3)
- Exiftool exclusion lists: file extensions skipped, exiftool key exclusions (§7.4)
- Sidecar suffix patterns and type identification (§7.5)
- Configuration file format specification (§7.6)
- Override and merging behavior (§7.7)

Include a sample TOML config file showing all available options with their defaults.

##### `docs/user-guide/python-api.md` content:
Source: spec §9 (Python API)

Cover:
- Public API surface (§9.1): what is importable, stability guarantees
- Core functions: `index_path()`, `index_file()`, `index_directory()` (§9.2)
- Configuration API: `IndexerConfig`, `load_config()` (§9.3)
- Data classes and type definitions: `IndexEntry`, `HashSet`, `NameObject`, etc. (§9.4)
- Programmatic usage examples (§9.5): index a single file, index a directory, customize configuration, access specific fields

##### `docs/user-guide/platform-notes.md` content:
Source: spec §15 (Platform Portability)

Cover:
- Cross-platform design principles (§15.1)
- Windows-specific considerations (§15.2): NTFS, junctions, long paths
- Linux and macOS considerations (§15.3)
- Filesystem behavior differences (§15.4): case sensitivity, path separators
- Creation time portability (§15.5): `st_birthtime` vs `st_ctime` vs fallback
- Symlink and reparse point handling (§15.6)

#### 5. Rewrite `docs/schema/index.md` — Full Schema Reference

Source: spec §5 (Output Schema), `docs/schema/shruggie-indexer-v2.schema.json`, `docs/schema/examples/flashplayer.exe_meta2.json`

Replace the stub with comprehensive schema documentation:
- Schema overview and design principles (P1–P5 from §5.1) — rewrite these in docs-friendly language, not spec language
- Schema version: `"2"` — mention the `schema_version` discriminator field
- Reusable type definitions (§5.2): document each type (`HashSet`, `NameObject`, `SizeObject`, `TimestampPair`, `TimestampsObject`, `ParentObject`) with field tables showing name, type, nullable, and description
- Top-level IndexEntry fields (§5.3): full field inventory table
- Field group sections (§5.4–§5.10): Identity, Naming/Content, Filesystem Location, Timestamps, Attributes, Recursive Items, Metadata Array — each with field tables and behavioral notes
- A complete annotated v2 output example (use/adapt the flashplayer example from `docs/schema/examples/`)
- Link to the canonical JSON Schema: `https://schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json`
- Link to the local copy: `shruggie-indexer-v2.schema.json` (relative link)
- Schema validation: brief note on how to validate output against the schema using standard JSON Schema tooling

#### 6. Create `docs/changelog.md` at the top level

Move the changelog out of the user guide nesting into its own top-level nav entry. Copy the content from `docs/user/changelog.md` to `docs/changelog.md`.

#### 7. Clean up old `docs/user/` directory

After moving files, the old `docs/user/` directory will have orphaned files. Remove the following files that have been moved or replaced:
- `docs/user/index.md`
- `docs/user/installation.md`
- `docs/user/quickstart.md`
- `docs/user/configuration.md`
- `docs/user/changelog.md`
- `docs/user/testing-troubleshooting.md` — Move this to `docs/user-guide/testing-troubleshooting.md` if it has real content, or drop it from nav if it's a stub. Use your judgment.

Delete the `docs/user/` directory after all files are moved.

#### 8. Update Porting Reference landing page

Rewrite `docs/porting-reference/index.md` to add brief context that this section contains reference materials from the original PowerShell implementation that informed the development of shruggie-indexer. Make it clear these are historical/archival references, not active documentation for using the tool.

### Writing Guidelines

1. **No "Work in Progress" admonitions.** Remove every instance. The site should present as complete documentation for a released v0.1.0.
2. **Standalone language.** Describe what shruggie-indexer does, not what it was ported from. The word "port" should appear only in the Porting Reference section and, if needed, in a brief "Background" or "History" note elsewhere.
3. **Concrete examples.** Every page that describes CLI or API usage should include runnable examples with realistic paths and representative output snippets.
4. **Use admonitions** (`!!! note`, `!!! tip`, `!!! warning`) for important callouts — especially for the metadata implication chain, platform-specific behavior, and exiftool dependency.
5. **Use field tables** for the schema reference and CLI reference. MkDocs Material renders these well.
6. **Internal cross-links.** Link between pages (e.g., Quick Start links to CLI Reference for full details, CLI Reference links to Configuration for config file format).
7. **UTF-8 without BOM** for all files.

### Verification

After all files are written:
1. Run `mkdocs build --strict` — must pass with zero warnings.
2. Run `mkdocs serve` and visually verify every page renders and all internal links resolve.
3. Verify the nav structure matches the specification above.

---END PROMPT---

---

## Section 2: Navigation Restructure — Exact Mappings

### Current → Proposed Navigation

```
CURRENT NAV                              PROPOSED NAV
──────────────────────────────────       ──────────────────────────────────
Home: index.md                       →   Home: index.md (REWRITE)
                                         
Schema Reference:                        Getting Started:               (NEW section)
  Overview: schema/index.md          │     Installation                  (MOVED from user/)
                                     │     Quick Start                   (MOVED from user/)
Porting Reference:                   │     ExifTool Setup                (NEW page)
  Overview: porting-reference/       │   
  Operations Catalog                 │   User Guide:                     (NEW section)
  Dependency Catalogs (9 pages)      │     Overview                      (NEW landing page)
                                     │     CLI Reference                 (NEW page)
User Guide:                          │     Configuration                 (MOVED from user/, REWRITE)
  Overview: user/index.md            │     Python API                    (NEW page)
  Installation: user/installation.md │     Platform Notes                (NEW page)
  Quick Start: user/quickstart.md    │   
  Configuration: user/configuration  │   Schema Reference:
  Testing Troubleshooting            │     Overview: schema/index.md     (REWRITE)
  Changelog: user/changelog.md      │   
                                     │   Porting Reference:              (KEPT, demoted in order)
                                     │     (all existing pages unchanged)
                                     │   
                                     │   Changelog: changelog.md         (MOVED to top-level)
```

### File Operations Summary

| Operation | From | To |
|-----------|------|----|
| REWRITE | `docs/index.md` | `docs/index.md` |
| MOVE + REWRITE | `docs/user/installation.md` | `docs/getting-started/installation.md` |
| MOVE + REWRITE | `docs/user/quickstart.md` | `docs/getting-started/quickstart.md` |
| CREATE | — | `docs/getting-started/exiftool.md` |
| CREATE | — | `docs/user-guide/index.md` |
| CREATE | — | `docs/user-guide/cli-reference.md` |
| MOVE + REWRITE | `docs/user/configuration.md` | `docs/user-guide/configuration.md` |
| CREATE | — | `docs/user-guide/python-api.md` |
| CREATE | — | `docs/user-guide/platform-notes.md` |
| REWRITE | `docs/schema/index.md` | `docs/schema/index.md` |
| MOVE | `docs/user/changelog.md` | `docs/changelog.md` |
| MOVE (conditional) | `docs/user/testing-troubleshooting.md` | `docs/user-guide/testing-troubleshooting.md` (if it has real content) |
| REWRITE | `docs/porting-reference/index.md` | `docs/porting-reference/index.md` |
| DELETE | `docs/user/index.md` | — |
| DELETE | `docs/user/` (directory) | — |
| UPDATE | `mkdocs.yml` | `mkdocs.yml` |

### Rationale

1. **Getting Started is now the first section** — first-time users land on installation and quick-start immediately rather than a schema reference stub.
2. **User Guide is the second section** — the detailed reference material (CLI, config, API, platform) lives here, separate from the onboarding flow.
3. **ExifTool gets its own page** — it's the single most common setup question and deserves dedicated coverage rather than being buried in installation notes.
4. **Schema Reference stays but gets real content** — populated with the rich detail from spec §5.
5. **Porting Reference moves to second-to-last** — still accessible for historical context and contributor reference, but no longer a prominent nav destination for end users.
6. **Changelog is top-level** — easily findable without digging into a sub-section.
7. **"User Guide" is renamed conceptually** — old `user/` directory is replaced with `getting-started/` (onboarding) and `user-guide/` (reference), which is a more natural split.

---

## Section 3: Spec-to-Docs Reference Map

This table maps every docs page to the specific technical specification sections (and other source files) that should be consulted when writing that page's content. The spec sections are listed in priority order — the first-listed section is the primary source.

### Homepage (`docs/index.md`)

| Source | Sections | What to Extract |
|--------|----------|-----------------|
| `shruggie-indexer-spec.md` | §1.1, §2.1, §2.3 | Project identity, purpose statement, design goals G1–G7 (rewrite as feature descriptions) |
| `shruggie-indexer-spec.md` | §5.1 | Schema design principles P1–P5 (for the "structured output" messaging) |
| `shruggie-indexer-spec.md` | §8.1 | CLI command structure (for the quick example) |
| `CHANGELOG.md` | v0.1.0 entry | Feature list for the "what's included" summary |
| `README.md` | — | Current description (reference only — rewrite in standalone terms) |

### Installation (`docs/getting-started/installation.md`)

| Source | Sections | What to Extract |
|--------|----------|-----------------|
| `shruggie-indexer-spec.md` | §2.4 | Platform and runtime requirements (Python 3.12+, OS support) |
| `shruggie-indexer-spec.md` | §2.5 | Python version requirements and rationale |
| `shruggie-indexer-spec.md` | §12.1 | Required external binaries (exiftool) |
| `shruggie-indexer-spec.md` | §12.3 | Third-party Python packages |
| `shruggie-indexer-spec.md` | §13.1–§13.3 | Package metadata, pyproject.toml, entry points |
| `shruggie-indexer-spec.md` | §13.4 | Standalone executable builds (PyInstaller) |
| `shruggie-indexer-spec.md` | §13.5 | Release artifact inventory (what's downloadable) |
| `pyproject.toml` | `[project.optional-dependencies]` | Extras groups: `gui`, `dev`, `docs` |

### Quick Start (`docs/getting-started/quickstart.md`)

| Source | Sections | What to Extract |
|--------|----------|-----------------|
| `shruggie-indexer-spec.md` | §8.1–§8.6 | CLI command structure and primary options |
| `shruggie-indexer-spec.md` | §8.9 | Output scenarios (the 7 combinations) |
| `shruggie-indexer-spec.md` | §5.3–§5.4 | Top-level fields and identity fields (for output example) |
| `shruggie-indexer-spec.md` | §6.1 | Traversal behavior (recursive/non-recursive) |
| `shruggie-indexer-spec.md` | §6.3 | Hashing behavior (for explaining ID prefixes x/y/z) |
| `docs/schema/examples/flashplayer.exe_meta2.json` | — | Real output example to include as sample |
| `src/shruggie_indexer/cli/main.py` | Click decorators | Verify exact flag names match implementation |

### ExifTool Setup (`docs/getting-started/exiftool.md`)

| Source | Sections | What to Extract |
|--------|----------|-----------------|
| `shruggie-indexer-spec.md` | §6.6 | EXIF extraction: purpose, backend selection logic, error handling table |
| `shruggie-indexer-spec.md` | §12.1 | Required external binary details (exiftool version, PATH requirement) |
| `shruggie-indexer-spec.md` | §12.5 | Dependency verification at runtime |
| `shruggie-indexer-spec.md` | §17.5 | Exiftool invocation strategy (batch vs subprocess) |
| `shruggie-indexer-spec.md` | §7.4 | Exiftool exclusion lists (extension and key exclusions) |
| `docs/porting-reference/MakeIndex_OperationsCatalog.md` | Category 6 | Improvement notes on exiftool handling (for context on why batch mode) |

### User Guide Landing (`docs/user-guide/index.md`)

| Source | Sections | What to Extract |
|--------|----------|-----------------|
| — | — | This is a navigation/overview page. Brief descriptions linking to sub-pages. No deep spec references needed. |

### CLI Reference (`docs/user-guide/cli-reference.md`)

| Source | Sections | What to Extract |
|--------|----------|-----------------|
| `shruggie-indexer-spec.md` | §8.1 | Command structure |
| `shruggie-indexer-spec.md` | §8.2 | Target input options (TARGET argument, auto-detection, --file/--directory) |
| `shruggie-indexer-spec.md` | §8.3 | Output mode options (--stdout, --outfile, --inplace) |
| `shruggie-indexer-spec.md` | §8.4 | Metadata processing options (--meta, --meta-merge, --meta-merge-delete, implication chain) |
| `shruggie-indexer-spec.md` | §8.5 | Rename option (--rename, --dry-run) |
| `shruggie-indexer-spec.md` | §8.6 | ID type selection (--id-type, --compute-sha512) |
| `shruggie-indexer-spec.md` | §8.7 | Verbosity and logging (-v, -q, log level mapping table) |
| `shruggie-indexer-spec.md` | §8.8 | Mutual exclusion rules and validation |
| `shruggie-indexer-spec.md` | §8.9 | Output scenarios table (the 7 mode combinations) |
| `shruggie-indexer-spec.md` | §8.10 | Exit codes table |
| `shruggie-indexer-spec.md` | §8.11 | Signal handling and graceful interruption |
| `src/shruggie_indexer/cli/main.py` | Click decorators | Verify all flags, defaults, and help text match |

### Configuration (`docs/user-guide/configuration.md`)

| Source | Sections | What to Extract |
|--------|----------|-----------------|
| `shruggie-indexer-spec.md` | §7.1 | Configuration architecture (layered resolution) |
| `shruggie-indexer-spec.md` | §7.2 | Default configuration (all default values) |
| `shruggie-indexer-spec.md` | §7.3 | Metadata file parser configuration (sidecar patterns, type ID) |
| `shruggie-indexer-spec.md` | §7.4 | Exiftool exclusion lists |
| `shruggie-indexer-spec.md` | §7.5 | Sidecar suffix patterns and type identification |
| `shruggie-indexer-spec.md` | §7.6 | Configuration file format (TOML structure) |
| `shruggie-indexer-spec.md` | §7.7 | Configuration override and merging behavior |
| `src/shruggie_indexer/config/defaults.py` | — | Verify actual default values match spec |
| `src/shruggie_indexer/config/types.py` | — | Verify config dataclass field names |

### Python API (`docs/user-guide/python-api.md`)

| Source | Sections | What to Extract |
|--------|----------|-----------------|
| `shruggie-indexer-spec.md` | §9.1 | Public API surface and stability guarantees |
| `shruggie-indexer-spec.md` | §9.2 | Core functions: index_path(), index_file(), index_directory() |
| `shruggie-indexer-spec.md` | §9.3 | Configuration API: IndexerConfig, load_config() |
| `shruggie-indexer-spec.md` | §9.4 | Data classes and type definitions |
| `shruggie-indexer-spec.md` | §9.5 | Programmatic usage examples |
| `src/shruggie_indexer/__init__.py` | — | Verify what is actually exported in `__all__` |
| `src/shruggie_indexer/models/schema.py` | — | Verify dataclass field names and types |
| `src/shruggie_indexer/api.py` (or equivalent) | — | Verify actual function signatures |

### Platform Notes (`docs/user-guide/platform-notes.md`)

| Source | Sections | What to Extract |
|--------|----------|-----------------|
| `shruggie-indexer-spec.md` | §15.1 | Cross-platform design principles |
| `shruggie-indexer-spec.md` | §15.2 | Windows-specific: NTFS, junctions, long paths, UNC |
| `shruggie-indexer-spec.md` | §15.3 | Linux and macOS considerations |
| `shruggie-indexer-spec.md` | §15.4 | Filesystem behavior differences (case sensitivity, separators) |
| `shruggie-indexer-spec.md` | §15.5 | Creation time portability (st_birthtime / st_ctime / fallback) |
| `shruggie-indexer-spec.md` | §15.6 | Symlink and reparse point handling |
| `shruggie-indexer-spec.md` | §6.4 | Symlink detection (behavioral details) |
| `shruggie-indexer-spec.md` | §6.5 | Filesystem timestamps and date conversion |

### Schema Reference (`docs/schema/index.md`)

| Source | Sections | What to Extract |
|--------|----------|-----------------|
| `shruggie-indexer-spec.md` | §5.1 | Schema overview, design principles P1–P5 |
| `shruggie-indexer-spec.md` | §5.2 | Reusable type definitions (HashSet, NameObject, SizeObject, TimestampPair, TimestampsObject, ParentObject) |
| `shruggie-indexer-spec.md` | §5.3 | Top-level IndexEntry fields inventory |
| `shruggie-indexer-spec.md` | §5.4 | Identity fields (schema_version, id, id_algorithm, type) |
| `shruggie-indexer-spec.md` | §5.5 | Naming and content fields (name, extension, mime_type, size, hashes) |
| `shruggie-indexer-spec.md` | §5.6 | Filesystem location and hierarchy fields (file_system object) |
| `shruggie-indexer-spec.md` | §5.7 | Timestamp fields |
| `shruggie-indexer-spec.md` | §5.8 | Attribute fields |
| `shruggie-indexer-spec.md` | §5.9 | Recursive items field |
| `shruggie-indexer-spec.md` | §5.10 | Metadata array and MetadataEntry fields |
| `shruggie-indexer-spec.md` | §5.11 | Dropped and restructured fields (v1→v2 changes, for context) |
| `shruggie-indexer-spec.md` | §5.12 | Schema validation and enforcement |
| `shruggie-indexer-spec.md` | §5.13 | Backward compatibility considerations |
| `docs/schema/shruggie-indexer-v2.schema.json` | — | The canonical schema file (link to it, reference its definitions) |
| `docs/schema/examples/flashplayer.exe_meta2.json` | — | Annotated real-world example |

### Porting Reference Landing (`docs/porting-reference/index.md`)

| Source | Sections | What to Extract |
|--------|----------|-----------------|
| `shruggie-indexer-spec.md` | §2.2 | Relationship to the original implementation |
| `shruggie-indexer-spec.md` | §2.6 | Intentional deviations from the original (DEV-01 through DEV-16) |
| `shruggie-indexer-spec.md` | §12.4 | Eliminated original dependencies |
| Existing `docs/porting-reference/index.md` | — | Current content (supplement, don't lose existing links) |

### Changelog (`docs/changelog.md`)

| Source | Sections | What to Extract |
|--------|----------|-----------------|
| `CHANGELOG.md` (repo root) | — | Mirror or include the full changelog content |
| `docs/user/changelog.md` | — | Current content (move as-is) |

---

## Summary Checklist

For the agent executing the prompt:

- [ ] `mkdocs.yml` updated with new nav
- [ ] `docs/index.md` rewritten (standalone framing)
- [ ] `docs/getting-started/installation.md` created with real content
- [ ] `docs/getting-started/quickstart.md` created with real content
- [ ] `docs/getting-started/exiftool.md` created
- [ ] `docs/user-guide/index.md` created
- [ ] `docs/user-guide/cli-reference.md` created (comprehensive)
- [ ] `docs/user-guide/configuration.md` created with real content
- [ ] `docs/user-guide/python-api.md` created
- [ ] `docs/user-guide/platform-notes.md` created
- [ ] `docs/schema/index.md` rewritten (full schema docs)
- [ ] `docs/changelog.md` created at top level
- [ ] `docs/porting-reference/index.md` updated with archival framing
- [ ] Old `docs/user/` directory cleaned up
- [ ] All "Work in Progress" admonitions removed
- [ ] `mkdocs build --strict` passes
- [ ] All internal links resolve

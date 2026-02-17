## 7. Configuration

This section defines the configuration system that replaces the original's hardcoded `$global:MetadataFileParser` object and the literal values scattered throughout the `MakeIndex` function body. It specifies every configurable field, its type, its default value, the TOML file format used for user overrides, and the layered resolution strategy that merges defaults, user files, and CLI/API arguments into a single immutable configuration object.

The configuration system implements design goal G4 (§2.3): a user SHOULD be able to add a new sidecar metadata pattern, extend the exiftool exclusion list, or modify the filesystem exclusion filters without editing source code. It also implements the no-global-state principle from §4.4: the configuration is constructed once during Stage 1 of the processing pipeline (§4.1), frozen into an immutable object, and threaded through the entire call chain as an explicit function parameter.

§3.2 defines the module layout (`config/types.py`, `config/defaults.py`, `config/loader.py`). §3.3 defines the file resolution paths. §4.2 defines the dependency rules (Rule 4: `config/` is consumed, not called back into). This section defines the content — what fields exist, what values they hold, and how they compose.

### 7.1. Configuration Architecture

#### The `IndexerConfig` dataclass

All configuration is represented by a single top-level frozen dataclass, `IndexerConfig`, defined in `config/types.py`. Every `core/` module that consumes configuration receives it as an `IndexerConfig` parameter. No module inspects environment variables, reads files, or accesses global state to obtain configuration at runtime — the `IndexerConfig` is the sole source of truth.

```python
@dataclass(frozen=True)
class IndexerConfig:
    """Immutable configuration for a single indexing invocation."""

    # Target and traversal
    recursive: bool = True
    id_algorithm: str = "md5"  # "md5" or "sha256"
    compute_sha512: bool = False

    # Output routing
    output_stdout: bool = True
    output_file: Path | None = None
    output_inplace: bool = False

    # Metadata processing
    extract_exif: bool = False
    meta_merge: bool = False
    meta_merge_delete: bool = False

    # Rename
    rename: bool = False
    dry_run: bool = False

    # Filesystem exclusion filters
    filesystem_excludes: frozenset[str] = ...  # see §7.2
    filesystem_exclude_globs: tuple[str, ...] = ...

    # Extension validation
    extension_validation_pattern: str = ...  # compiled regex string

    # Exiftool
    exiftool_exclude_extensions: frozenset[str] = ...
    exiftool_args: tuple[str, ...] = ...

    # Metadata file parser
    metadata_identify: MappingProxyType[str, tuple[re.Pattern, ...]] = ...
    metadata_attributes: MappingProxyType[str, MetadataTypeAttributes] = ...
    metadata_exclude_patterns: tuple[re.Pattern, ...] = ...
    extension_groups: MappingProxyType[str, tuple[str, ...]] = ...
```

The `frozen=True` parameter ensures that the object is immutable after construction. Mutable collection types in the original (`list`, `dict`, `set`) are replaced with their immutable counterparts (`tuple`, `frozenset`, `MappingProxyType`) to enforce this at the field level. If using Pydantic instead of stdlib `dataclasses`, the equivalent is `model_config = ConfigDict(frozen=True)`.

> **Deviation from original:** The original distributes configuration across six global variables (`$global:MetadataFileParser`, `$global:ExiftoolRejectList`, `$global:MetaSuffixInclude`, `$global:MetaSuffixIncludeString`, `$global:MetaSuffixExclude`, `$global:MetaSuffixExcludeString`) plus inline literals in the function body. The port consolidates everything into a single typed, immutable object. See §4.4 for the full rationale.

#### Nested configuration types

Two nested types provide structure within `IndexerConfig`:

```python
@dataclass(frozen=True)
class MetadataTypeAttributes:
    """Behavioral attributes for a single sidecar metadata type."""
    about: str
    expect_json: bool
    expect_text: bool
    expect_binary: bool
    parent_can_be_file: bool
    parent_can_be_directory: bool
```

This is the Python equivalent of the original's `$MetadataFileParser.Attributes.<TypeName>` sub-objects (e.g., `Description`, `GenericMetadata`, `Hash`, etc.). The field names are converted from PascalCase to snake_case per Python convention.

```python
@dataclass(frozen=True)
class ExiftoolConfig:
    """Exiftool-specific configuration."""
    exclude_extensions: frozenset[str]
    base_args: tuple[str, ...]
```

Implementations MAY flatten these nested types into top-level `IndexerConfig` fields if the nesting adds no practical value for their codebase. The specification uses the nested form because it mirrors the logical grouping of the original `MetadataFileParser` and produces cleaner TOML sections (§7.6).

#### Configuration construction flow

The `load_config()` function in `config/loader.py` is the sole factory for `IndexerConfig` objects. It is called once per invocation during Stage 1:

1. Start with compiled defaults from `config/defaults.py` (§7.2).
2. If a user config file exists at a resolved path (§3.3), read and parse it as TOML via `tomllib.loads()`.
3. If a project-local config file exists (`.shruggie-indexer.toml` in the target directory or its ancestors), read and parse it.
4. Apply CLI argument overrides or API keyword argument overrides.
5. Apply parameter implications (e.g., `rename=True` → `output_inplace=True`; `meta_merge_delete=True` → `meta_merge=True` → `extract_exif=True`).
6. Validate the fully-resolved configuration (§7.1, Validation rules).
7. Compile regex patterns from string form into `re.Pattern` objects.
8. Freeze and return the `IndexerConfig`.

Steps 2–4 follow the layered precedence defined in §3.3. Steps 5–6 are described in detail below.

#### Parameter implications

Certain flag combinations carry implicit dependencies. The configuration loader enforces these implications after merging all layers, matching the original's behavior:

| If this is `True`... | ...then force this to `True` | Original equivalent |
|---|---|---|
| `rename` | `output_inplace` | `$Rename` → `$OutFileInPlace = $true` (line ~9360) |
| `meta_merge_delete` | `meta_merge` | `$MetaMergeDelete` → `$MetaMerge = $true` (line ~9447) |
| `meta_merge` | `extract_exif` | `$MetaMerge` → `$Meta = $true` (line ~9450) |

These implications are applied in reverse dependency order — `meta_merge_delete` first, then `meta_merge`, then `rename` — so that transitive chains propagate correctly. For example, `meta_merge_delete=True` with all other flags at their defaults produces `meta_merge=True, extract_exif=True, meta_merge_delete=True`.

#### Output mode defaulting

The original's output mode resolution (lines ~9352–9437) applies complex conditional logic to determine whether stdout is active based on which output flags the user specified. The port simplifies this to a single rule:

- If neither `output_file` nor `output_inplace` is specified, and `output_stdout` was not explicitly set to `False`, then `output_stdout` defaults to `True`.
- If `output_file` or `output_inplace` is specified, `output_stdout` defaults to `False` unless the user explicitly passes `--stdout`.

The original's `NoStandardOutput` / `StandardOutput` dual-flag pattern (a positive and negative flag for the same boolean) is eliminated. The port uses a single `output_stdout` field. The CLI provides only `--stdout` and `--no-stdout`; absence of either flag triggers the defaulting logic above.

> **Improvement over original:** The original's output mode resolution is a 90-line block with nested conditionals, redundant inverse-variable tracking (`$NoStandardOutput = !$StandardOutput`), and commented-out debug logging. The port's rule is two sentences. The behavioral outcome is identical.

#### Validation rules

After implication propagation and output mode defaulting, the configuration loader validates the following invariants. Violations are fatal errors raised before any processing begins:

1. **MetaMergeDelete safety.** If `meta_merge_delete` is `True`, at least one of `output_file` or `output_inplace` MUST also be `True`. This prevents the scenario where sidecar files are deleted without their content being captured in any persistent output. The original enforces this via the `$MMDSafe` variable (lines ~9354–9427); the port enforces it as a declarative validation rule.

2. **IdType validity.** `id_algorithm` MUST be either `"md5"` or `"sha256"`. The original validates this with a `switch` statement that falls through to an error (line ~8776). The port validates during configuration construction.

3. **Path conflicts.** If `output_file` is specified, it MUST NOT point to a path inside the target directory when `output_inplace` is also active. (Writing the aggregate output file into the same directory tree being indexed with in-place writes active would cause the aggregate file to be indexed on subsequent runs.)

4. **Regex compilation.** All regex strings in the metadata identification and exclusion pattern lists MUST compile without error. If a user-provided pattern is invalid, the loader raises a `ConfigurationError` with the offending pattern and the `re.error` message.

---

### 7.2. Default Configuration

The compiled defaults in `config/defaults.py` define the baseline configuration that applies when no user configuration file is present. These defaults reproduce the behavioral intent of the original's hardcoded values while extending them for cross-platform coverage (DEV-10) and correcting known issues.

The tool MUST operate correctly using only compiled defaults — no configuration file is required (§3.3).

#### Scalar defaults

| Field | Default | Rationale |
|-------|---------|-----------|
| `recursive` | `True` | Matches original: recursion is on unless `-NotRecursive` is specified. |
| `id_algorithm` | `"sha256"` | Matches original: `$IdType` defaults to `"SHA256"`. |
| `compute_sha512` | `False` | SHA512 is available but not computed by default for performance. The original does not compute SHA512 at runtime either (despite declaring it in the output schema). |
| `output_stdout` | `True` (conditional) | Applied via the defaulting logic in §7.1 — only `True` when no file-based output is active. |
| `output_file` | `None` | No aggregate output file by default. |
| `output_inplace` | `False` | No in-place sidecar writes by default. |
| `extract_exif` | `False` | Matches original: `-Meta` defaults to `$false`. |
| `meta_merge` | `False` | Matches original: `-MetaMerge` defaults to `$false`. |
| `meta_merge_delete` | `False` | Matches original: `-MetaMergeDelete` defaults to `$false`. |
| `rename` | `False` | Matches original: `-Rename` defaults to `$false`. |
| `dry_run` | `False` | New field (not in original). |

#### Extension validation pattern

```python
EXTENSION_VALIDATION_PATTERN = r"^(([a-z0-9]){1,2}|([a-z0-9])([a-z0-9\-]){1,12}([a-z0-9]))$"
```

This is the original's extension validation regex from `MakeObject` (line ~8710), transcribed exactly. It accepts lowercase alphanumeric extensions of 1–14 characters where hyphens are permitted in interior positions but not at the start or end. The regex is applied to the extension string *without* the leading dot (e.g., `"mp4"`, not `".mp4"`).

This pattern is configurable (DEV-14) — users who encounter legitimate extensions rejected by this pattern can relax it in their config file. The default preserves the original's behavior.

#### Filesystem exclusion defaults

The default filesystem exclusion set extends the original's Windows-only pair to cover all three target platforms:

```python
FILESYSTEM_EXCLUDES = frozenset({
    # Windows
    "$recycle.bin",
    "system volume information",
    "desktop.ini",
    "thumbs.db",
    # macOS
    ".ds_store",
    ".spotlight-v100",
    ".trashes",
    ".fseventsd",
    ".temporaryitems",
    ".documentrevisions-v100",
    # Version control (optional, included by default)
    ".git",
})

FILESYSTEM_EXCLUDE_GLOBS = (
    # Linux
    ".trash-*",
)
```

All exclusion names are stored in lowercase. Matching is performed case-insensitively (§6.1). Glob patterns are stored separately from exact-match names because they require `fnmatch` matching rather than set membership lookup. The original only excludes `$RECYCLE.BIN` and `System Volume Information` (DEV-10).

#### Exiftool exclusion defaults

```python
EXIFTOOL_EXCLUDE_EXTENSIONS = frozenset({
    "csv", "htm", "html", "json", "tsv", "xml",
})
```

This matches the original's `$MetadataFileParser.Exiftool.Exclude` exactly. See §7.4 for the full rationale.

#### Exiftool argument defaults

```python
EXIFTOOL_BASE_ARGS = (
    "-extractEmbedded3",
    "-scanForXMP",
    "-unknown2",
    "-json",
    "-G3:1",
    "-struct",
    "-ignoreMinorErrors",
    "-charset", "filename=utf8",
    "-api", "requestall=3",
    "-api", "largefilesupport=1",
    "--",
)
```

These are the original's exiftool arguments, decoded from the Base64-encoded `$ArgsQ` string (the quiet-mode variant — the port controls verbosity through its own logging system, not through exiftool's `-quiet` flag). The arguments are stored as a plain Python tuple rather than being Base64-encoded (DEV-05).

> **Improvement over original:** The original Base64-encodes the exiftool argument strings (`$ArgsV`, `$ArgsQ`) and decodes them at runtime via `Base64DecodeString`, writing the result to a temporary file that is then passed to exiftool via `-@ "$TempArgsFile"`. This three-step pipeline (encode → decode → write to file → pass as arg file) is entirely unnecessary. The port stores the arguments as a plain tuple and passes them directly to `subprocess.run()` as a list. The `-b` flag (binary output) present in the original's verbose argument set is intentionally omitted from the default — it causes exiftool to emit binary-encoded values in the JSON output, which complicates downstream parsing. If binary output is needed for specific use cases, it can be added via configuration.

#### Metadata identification pattern defaults

The complete default pattern set is specified in §7.5. The defaults in `config/defaults.py` define these patterns as lists of regex strings. The `config/loader.py` compiles them into `re.Pattern` objects during configuration construction.

#### Metadata type attribute defaults

The complete default attribute set is specified in §7.3. The defaults in `config/defaults.py` define these as `MetadataTypeAttributes` instances.

#### Extension group defaults

The extension groups from the original's `$MetadataFileParser.ExtensionGroups` are carried forward verbatim. These groups classify common file extensions into categories (Archive, Audio, Font, Image, Link, Subtitles, Video) and are used during sidecar metadata parsing to infer expected content types. The complete lists are specified in §7.3.

---

### 7.3. Metadata File Parser Configuration

This subsection specifies the complete porting of the original `$global:MetadataFileParser` ordered hashtable into the typed configuration system. The original object contains four top-level sub-objects — `Attributes`, `Identify`, `Exiftool`, and `ExtensionGroups` — plus a derived `Indexer` sub-object. Each is mapped to a corresponding field or group of fields in `IndexerConfig`.

The isolated reference script `MakeIndex(MetadataFileParser).ps1` (§1.5) is the authoritative source for the original patterns. This section reproduces the complete content with porting guidance.

#### Attributes → `metadata_attributes`

The `Attributes` sub-object defines behavioral metadata for each sidecar type — what data formats to expect, whether the sidecar can be associated with a file parent, a directory parent, or both. These attributes guide the parsing strategy in `core/sidecar.py` (§6.7).

| Type Name | `about` | `expect_json` | `expect_text` | `expect_binary` | `parent_can_be_file` | `parent_can_be_directory` |
|-----------|---------|---------------|---------------|-----------------|---------------------|--------------------------|
| `description` | Likely a youtube-dl or yt-dlp information file containing UTF-8 text (with possible problematic characters). | `True` | `True` | `False` | `True` | `False` |
| `desktop_ini` | A Windows desktop.ini file used to customize folder appearance in Windows Explorer. | `False` | `True` | `True` | `False` | `True` |
| `generic_metadata` | Generic metadata file which may contain any type of metadata information related to files or directories. | `True` | `True` | `True` | `True` | `True` |
| `hash` | A file containing a hash value (MD5, SHA1, SHA256, etc.) of another file. | `False` | `True` | `False` | `True` | `False` |
| `json_metadata` | A JSON file containing metadata information related to files or directories. | `True` | `False` | `False` | `True` | `True` |
| `link` | A file containing an Internet URL or a link to another file or directory. | `False` | `True` | `True` | `True` | `True` |
| `screenshot` | A screenshot image file which may contain a screen capture of a computer desktop or application. | `False` | `False` | `True` | `True` | `False` |
| `subtitles` | A subtitle file which contains text-based subtitles for a video or audio file. | `True` | `True` | `True` | `True` | `False` |
| `thumbnail` | A thumbnail image file containing one or more reduced-size icon images related to another file or directory. | `False` | `False` | `True` | `True` | `True` |
| `torrent` | A torrent or magnet link file containing connection and/or identification information for peer-to-peer retrieval. | `False` | `False` | `True` | `True` | `True` |

The type names are converted from PascalCase (`DesktopIni`) to snake_case (`desktop_ini`) per Python convention. The `about` strings are preserved from the original for documentation purposes.

#### Identify → `metadata_identify`

The `Identify` sub-object contains the regex patterns used to classify a filename as a sidecar metadata file and determine its type. Each type maps to an ordered list of regex patterns. A filename matches a type if it matches any pattern in that type's list. Patterns within a list are ordered from most specific to most generic (where applicable — notably the Subtitles patterns).

These patterns are the most critical configuration data to port correctly. The regex syntax used by the original is PowerShell's `-match` operator, which uses .NET regular expressions. The patterns in `MetadataFileParser.Identify` use a subset of .NET regex that is fully compatible with Python's `re` module — specifically: character classes, alternation, anchors (`^`, `$`), quantifiers, and grouping. No .NET-specific regex features (lookbehind with variable length, named balancing groups) are used. The patterns can therefore be transcribed to Python without syntactic modification.

**Porting rule:** Each pattern string is compiled in Python via `re.compile(pattern, re.IGNORECASE)`. The `re.IGNORECASE` flag is applied because the original's `-match` operator performs case-insensitive matching by default in PowerShell. All patterns are applied using `re.search()` against the full filename (not just the extension), matching the original's behavior where patterns may anchor to the start or end of the filename.

The complete pattern inventory, transcribed from `MakeIndex(MetadataFileParser).ps1`:

**Description:**
```python
(r'\.description$',)
```

**DesktopIni:**
```python
(r'\.desktop\.ini$', r'desktop\.ini$')
```

**GenericMetadata:**
```python
(
    r'\.(exif|meta|metadata)$',
    r'\.comments$',
    r'^.(git(attributes|ignore))$',
    r'\.(cfg|conf|config)$',
    r'\.yaml$',
)
```

**Hash:**
```python
(r'\.(md5|sha\d+|blake2[bs]|crc\d+|xxhash|checksum|hash)$',)
```

**JsonMetadata:**
```python
(
    r'_directorymeta\.json$',
    r'_(subs|subtitles)\.json$',
    # BCP 47 language-code subtitles in JSON format
    r'\.(aa|af|sq|gsw-fr|ase|am|ar|arq|abv|arz|acm|ajp|afb-kw|apc|ayl|ary|acx|'
    r'afb-qa|ar-sa|ar-sy|aeb|ar-ae|ar-ye|arp|hy|as|az|az-cyrl|az-latn|ba|be|bn|'
    r'bn-in|bs|bs-cyrl|bzs|br|br-fr|bg|my|ca|tzm|tzm-arab-ma|tzm-dz|tzm-tfng|'
    r'tzm-tfng-ma|ckb|ckb-iq|chr|zh|yue|yue-hk|cmn|cmn-hans|cmn-hans-cn|'
    r'cmn-hans-hk|cmn-hans-mo|cmn-hans-my|cmn-hans-sg|cmn-hans-tw|cmn-tw|'
    r'cmn-hant|cmn-hant-cn|cmn-hant-hk|cmn-hant-mo|cmn-hant-my|cmn-hant-sg|'
    r'cmn-hant-tw|nan|zh-hans|zh-hans-cn|zh-hans-hk|zh-hans-mo|zh-hans-my|'
    r'zh-hans-sg|zh-hans-tw|zh-hant|zh-hant-cn|zh-hant-hk|zh-hant-mo|'
    r'zh-hant-my|zh-hant-sg|zh-hant-tw|com|co|co-fr|hr|hr-ba|quz|cs|da|prs|dv|'
    r'nl|dz|bin|en|en-au|en-bz|en-ca|en-029|en-hk|en-in|en-id|en-ie|en-jm|'
    r'en-my|en-nz|en-ph|en-sg|en-za|en-se|en-tt|en-ae|en-gb|en-us|en-zw|et|eu|'
    r'fo|fil|fi|nl-be|fr|fr-be|fr-cm|fr-ca|fr-029|fr-ci|fr-ht|fr-lu|fr-ml|'
    r'fr-mc|fr-ma|fr-re|fr-sn|fr-ch|fr-cd|ff|ff-latn|ff-latn-ng|ff-latn-sn|'
    r'ff-ng|gl|ka|de|de-at|de-li|de-lu|gsw|de-ch|el|gn|gu|ha|ha-latn|ha-latn-ng|'
    r'haw|he|hi|hu|ibb|is|ig|id|iu|iu-cans|ga|it|it-ch|ja|ja-jp|quc|kl|kn|kr|'
    r'kr-ng|ks|ks-deva-in|kk|km|rw|kok|ko|ky|lad|lo|la|la-va|lv|ln|lt|dsb|lb|'
    r'mk|ms-bn|ms-my|ms|ml|mt|mni|mni-beng-in|mi|arn|mr|fit|moh|mn|mn-cn|'
    r'mn-mong|mn-mong-cn|nv|ne|ne-in|no|nb|nn|oc|or|om|pap|pap-029|ps|fa|pl|'
    r'pt-br|pt|pa|pa-arab|qu|qu-bo|qu-ec|qu-pe|ro|ro-md|rm|ru|ru-md|aec|sah|smi|'
    r'smn|smj|smj-no|se|se-fi|se-no|se-se|sms|sma|sma-no|sm|sa|gd|sr|sr-cyrl|'
    r'sr-ba|sr-cyrl-me|sr-latn|sr-latn-ba|sr-me|sd|sd-arab|sd-in|si|sk|sl|so|st|'
    r'nso|es-ar|es-bo|es|es-cl|es-co|es-cr|es-cu|es-do|es-ec|es-sv|es-gt|es-hn|'
    r'es-419|es-mx|es-ni|es-pa|es-py|es-pe|es-pr|es-us|es-uy|es-ve|sw|sw-ke|sv|'
    r'sv-fi|syr|syr-sy|tl|tg|tg-cyrl|tg-cyrl-tj|ta|tt|te|th|bo|ti|ts|tn|tn-bw|'
    r'tr|tk|uk|und|hsb|ur|ug|uz|ca-es|ve|vi|cy|fy|wo|xh|ii|yi|yo|zu'
    r')(-orig)?\.json$',
    r'_[a-z0-9]{3,19}\.json$',
    r'\.exifjson$',
    r'\.(AI|exif|info|meta)\.json$',
)
```

The BCP 47 language-code alternation is the longest and most carefully crafted pattern in the configuration. It matches subtitle metadata files produced by youtube-dl / yt-dlp, which use the naming convention `<basename>.<language_code>.json`. The alternation covers all language codes recognized by the original author. This pattern MUST be ported exactly — any dropped or modified language code will cause the corresponding subtitle files to be missed during sidecar discovery. The Python string is split across multiple lines for readability using implicit string concatenation; when compiled, it produces a single contiguous pattern identical to the original.

**Link:**
```python
(r'\.(url|lnk|link|source)$',)
```

**Screenshot:**
```python
(r'(-|_)?(screen|screen(s|shot|shots)|thumb|thumb(nail|nails))((-|_)?([0-9]{1,9}))?\.(jpg|jpeg|png|webp)$',)
```

**Subtitles:**
```python
(
    # Pattern 1: Language-tagged subtitle files (most specific)
    r'\.(aa|af|sq|...<same BCP 47 alternation as JsonMetadata>...)(-orig)?\.(srt|sub|sbv|vtt|lrc|txt)$',
    # Pattern 2: Bare subtitle extensions (most generic)
    r'\.(srt|sub|sbv|vtt|lrc)$',
)
```

The Subtitles pattern list reuses the same BCP 47 language-code alternation as the JsonMetadata patterns but with subtitle file extensions (`.srt`, `.sub`, `.sbv`, `.vtt`, `.lrc`, `.txt`) instead of `.json`. Pattern order matters: the more specific language-tagged pattern is listed first so that a file like `video.en.srt` is matched by the specific pattern before the generic `\.srt$` pattern. Both patterns classify the file as `subtitles`, so the ordering affects only the efficiency of matching, not the outcome. Nonetheless, the original's ordering SHOULD be preserved.

**Thumbnail:**
```python
(
    r'\.(cover|thumb|thumb(s|db|index|nail))$',
    r'^(thumb|thumb(s|db|index|nail))\.db$',
)
```

**Torrent:**
```python
(r'\.(torrent|magnet)$',)
```

#### Indexer include/exclude → `metadata_exclude_patterns` (plus computed inclusion)

The original's `$MetadataFileParser.Indexer` sub-object contains two derived arrays:

- `Exclude`: Regex patterns for files that should be excluded from the index entirely (e.g., existing `_meta.json` sidecar files, thumbnail database files). These files are not indexed as standalone items when encountered during traversal.
- `Include`: A union of all patterns from the `Identify` sub-object, computed at load time by iterating `$MetadataFileParser.Identify.Keys` and collecting all per-type patterns into a flat array.
- `ExcludeString` / `IncludeString`: The `Exclude` and `Include` arrays joined with `|` into single alternation strings.

The port preserves the `Exclude` patterns as `metadata_exclude_patterns`:

```python
METADATA_EXCLUDE_PATTERNS = (
    re.compile(r'_(meta|directorymeta)\.json$', re.IGNORECASE),
    re.compile(r'\.(cover|thumb|thumb(s|db|index|nail))$', re.IGNORECASE),
    re.compile(r'^(thumb|thumb(s|db|index|nail))\.db$', re.IGNORECASE),
)
```

> **Improvement over original:** The original pre-joins the `Include` and `Exclude` arrays into single `IncludeString` / `ExcludeString` alternation strings for use with PowerShell's `-match` operator. This is an optimization for PowerShell's regex engine, which compiles the pattern on every `-match` call. In Python, patterns are compiled once via `re.compile()` and reused. The pre-joined alternation strings are unnecessary — the port stores individual compiled patterns and iterates them. This is equally fast for the small number of patterns involved (typically under 30 total) and simpler to maintain, debug, and extend. The `IncludeString` / `ExcludeString` fields are not ported.

The `Include` set (the union of all `Identify` patterns) is not stored as a separate configuration field. Instead, the determination of whether a filename is a sidecar metadata file is performed by iterating `metadata_identify` and checking for any match — which is logically equivalent to checking against the union. If a fast "is this a sidecar at all?" check is needed as a hot-path optimization, the loader MAY compute a combined alternation pattern at construction time and expose it as a read-only property on `IndexerConfig`.

#### ExtensionGroups → `extension_groups`

The `ExtensionGroups` sub-object classifies common file extensions into seven categories. These groups are used by the sidecar parser (§6.7) to infer expected content types and validate parent-child relationships (e.g., a `subtitles` sidecar should be a sibling of a Video or Audio file, not an Image file). The complete lists, carried forward verbatim from the original:

| Group | Extensions |
|-------|-----------|
| `archive` | `7z`, `ace`, `alz`, `arc`, `arj`, `bz`, `bz2`, `cab`, `cbr`, `cbz`, `chm`, `cpio`, `deb`, `dmg`, `egg`, `gz`, `hdd`, `img`, `iso`, `jar`, `lha`, `lz`, `lz4`, `lzh`, `lzma`, `lzo`, `qcow2`, `rar`, `rpm`, `s7z`, `shar`, `sit`, `sitx`, `sqx`, `tar`, `tbz`, `tbz2`, `tgz`, `tlz`, `txz`, `vdi`, `vhd`, `vhdx`, `vmdk`, `war`, `wim`, `xar`, `xz`, `z`, `zip`, `zpaq`, `zst` |
| `audio` | `3gp`, `8svx`, `aa`, `aac`, `aax`, `act`, `aif`, `aiff`, `amr`, `ape`, `au`, `awb`, `cda`, `dct`, `dss`, `dvf`, `flac`, `gsm`, `iklax`, `ivs`, `m4a`, `m4b`, `m4p`, `mka`, `mlp`, `mmf`, `mp2`, `mp3`, `mpc`, `msv`, `ogg`, `oga`, `opus`, `ra`, `rm`, `raw`, `sln`, `tta`, `voc`, `vox`, `wav`, `wma`, `wv`, `webm`, `wv`, `wvp`, `wvpk` |
| `font` | `eot`, `otf`, `svg`, `svgz`, `ttc`, `ttf`, `woff`, `woff2` |
| `image` | `3fr`, `ari`, `arw`, `bay`, `bmp`, `cr2`, `crw`, `dcr`, `dng`, `erf`, `fff`, `gif`, `gpr`, `icns`, `ico`, `iiq`, `jng`, `jp2`, `jpeg`, `jpg`, `k25`, `kdc`, `mef`, `mos`, `mrw`, `nef`, `nrw`, `orf`, `pbm`, `pef`, `pgm`, `png`, `ppm`, `psd`, `ptx`, `raf`, `raw`, `rw2`, `rwl`, `sr2`, `srf`, `svg`, `tga`, `tif`, `tiff`, `webp`, `x3f` |
| `link` | `link`, `lnk`, `shortcut`, `source`, `symlink`, `url` |
| `subtitles` | `srt`, `sub`, `sbv`, `vtt`, `lrc` |
| `video` | `3g2`, `3gp`, `3gp2`, `3gpp`, `amv`, `asf`, `avi`, `divx`, `drc`, `dv`, `f4v`, `flv`, `gvi`, `gxf`, `ismv`, `m1v`, `m2v`, `m2t`, `m2ts`, `m4v`, `mkv`, `mov`, `mp2`, `mp2v`, `mp4`, `mp4v`, `mpe`, `mpeg`, `mpeg1`, `mpeg2`, `mpeg4`, `mpg`, `mpv2`, `mts`, `mtv`, `mxf`, `nsv`, `nuv`, `ogm`, `ogv`, `ogx`, `ps`, `rec`, `rm`, `rmvb`, `tod`, `ts`, `tts`, `vob`, `vro`, `webm`, `wm`, `wmv`, `wtv`, `xesc` |

All extensions are stored in lowercase without a leading dot. Extension groups are stored as a `MappingProxyType[str, tuple[str, ...]]` in `IndexerConfig`.

**Note on duplicates:** The original's `audio` list contains `wv` twice. The port deduplicates this during loading — `frozenset` or `tuple(sorted(set(...)))` naturally eliminates duplicates.

**Note on overlapping extensions:** Some extensions appear in multiple groups (e.g., `3gp` in both Audio and Video, `svg` in both Font and Image, `mp2` in both Audio and Video, `rm` in both Audio and Video, `webm` in both Audio and Video, `raw` in both Audio and Image). This is intentional — a `.3gp` file may contain audio, video, or both. The extension groups describe what a file *could* be, not a mutually exclusive classification. The sidecar parser uses these groups as heuristics, not definitive type assignments.

---

### 7.4. Exiftool Exclusion Lists

The `exiftool_exclude_extensions` configuration field specifies file extensions for which exiftool metadata extraction is skipped entirely. When a file's extension (lowercase, without the leading dot) appears in this set, `core/exif.extract_exif()` returns `None` without invoking the exiftool subprocess (§6.6).

#### Default exclusion set

```python
EXIFTOOL_EXCLUDE_EXTENSIONS = frozenset({
    "csv", "htm", "html", "json", "tsv", "xml",
})
```

#### Rationale

These file types cause exiftool to emit the file's text content as metadata rather than extracting meaningful embedded metadata. The original documents this problem explicitly (line ~7717):

> *"If included, these types of files can result in (essentially) total inclusion of the file content inside the exiftool output (which is rediculous and defeats the purpose of trying to get simple metadata on a file in the first place). The exiftool authors have rejected numerous user requests for more limited metadata outputs from these file types, so we have to manually reject processing them entirely."*

The practical consequence of including these file types is twofold: the metadata output becomes massive (potentially gigabytes for large CSV or XML files), and the serialization layer may fail under the resulting memory pressure (the original's `ConvertTo-Json` has a known memory ceiling; Python's `json.dumps()` is more robust but the output is still uselessly large).

#### Extension mechanism

Users can extend the exclusion list via configuration (§7.6, §7.7). For example, a user working with large `.log` or `.txt` files that produce similarly excessive exiftool output can add those extensions to their config:

```toml
[exiftool]
exclude_extensions_append = ["log", "txt"]
```

The `_append` suffix triggers additive merge behavior (§7.7) rather than replacement.

---

### 7.5. Sidecar Suffix Patterns and Type Identification

This subsection consolidates the porting guidance for the sidecar metadata identification system — the regex patterns in `metadata_identify` that determine whether a given filename is a sidecar metadata file and, if so, what type it is.

#### How sidecar identification works

During sidecar discovery (§6.7), for each item being indexed, the sidecar module examines the item's sibling files. For each sibling, it tests the sibling's filename against every pattern in `metadata_identify`, iterating types in definition order. The first matching type wins — the sibling is classified as that type and no further patterns are tested.

This means type ordering in the configuration is significant when patterns could overlap. The definition order should place more specific types before more generic ones. The default ordering matches the original: Description, DesktopIni, GenericMetadata, Hash, JsonMetadata, Link, Screenshot, Subtitles, Thumbnail, Torrent.

#### Indexer exclusion during traversal

Independently from sidecar identification, the traversal module (§6.1) and entry construction module (§6.8) use `metadata_exclude_patterns` to skip certain files entirely. These are files that are themselves indexer output artifacts (e.g., `_meta.json`, `_directorymeta.json`) or thumbnail databases that are not meaningful to index. When MetaMerge is active, files matching any `metadata_identify` pattern for the current item's basename are also excluded from the regular item list (they are processed as sidecars rather than indexed as standalone items).

The distinction is important: `metadata_identify` determines *type classification* of sidecars. `metadata_exclude_patterns` determines which files to *skip entirely* during traversal. The two systems are complementary but serve different purposes.

#### Pattern compilation and caching

All regex strings from the configuration are compiled into `re.Pattern` objects once during `load_config()` (Stage 1). The compiled patterns are stored in the `IndexerConfig` and reused for every filename test. Pattern compilation is a measurable cost for the BCP 47 language-code alternations (which produce large NFA state machines), but it happens exactly once and the compiled pattern is then O(n) in the input string length for each subsequent match.

The implementation SHOULD pre-compile all patterns using `re.compile(pattern, re.IGNORECASE)`. The `re.IGNORECASE` flag ensures that filename matching is case-insensitive across all platforms, matching the original's behavior.

#### Validation of user-provided patterns

If a user adds custom patterns via configuration (§7.6), the configuration loader MUST validate that each pattern compiles without error. Invalid patterns produce a fatal `ConfigurationError` with the offending pattern and the `re.error` message. The indexing operation does not proceed with invalid patterns — a user typo in a regex MUST NOT cause silent misidentification of sidecar files.

---

### 7.6. Configuration File Format

The configuration file format is TOML, parsed by Python's `tomllib` module (standard library, Python 3.11+). TOML is chosen over JSON (no comments, verbose for nested structures), YAML (whitespace-sensitive, multiple dialects, requires a third-party parser), and INI (no nested structures, no typed values) because it provides a reasonable balance of human readability, type preservation, and stdlib support.

#### File naming and location

The configuration file name is `config.toml`. The resolution paths are defined in §3.3:

| Priority | Location | Description |
|----------|----------|-------------|
| 1 (lowest) | Compiled defaults | `config/defaults.py`. Always present. |
| 2 | User config directory | `~/.config/shruggie-indexer/config.toml` (Linux/macOS) or `%APPDATA%\shruggie-indexer\config.toml` (Windows). |
| 3 | Project-local config | `.shruggie-indexer.toml` in the target directory or its ancestors (searched upward). |
| 4 (highest) | CLI/API arguments | Command-line flags or `index_path()` keyword arguments. |

#### TOML structure

The TOML file mirrors the `IndexerConfig` field structure. Top-level scalar fields are TOML key-value pairs. Nested structures become TOML tables. Collection fields (extension lists, regex patterns) become TOML arrays.

A complete example showing every configurable field:

```toml
# shruggie-indexer configuration

# Traversal and identity
recursive = true
id_algorithm = "sha256"       # "md5" or "sha256"
compute_sha512 = false

# Output routing (typically set via CLI, not config file)
# output_stdout = true
# output_file = ""
# output_inplace = false

# Metadata processing
extract_exif = false
meta_merge = false
meta_merge_delete = false

# Rename
rename = false
dry_run = false

# Extension validation regex (applied without the leading dot)
extension_validation_pattern = '^(([a-z0-9]){1,2}|([a-z0-9])([a-z0-9\-]){1,12}([a-z0-9]))$'

[filesystem_excludes]
# Exact-match names (case-insensitive)
names = [
    "$recycle.bin",
    "system volume information",
    "desktop.ini",
    "thumbs.db",
    ".ds_store",
    ".spotlight-v100",
    ".trashes",
    ".fseventsd",
    ".temporaryitems",
    ".documentrevisions-v100",
    ".git",
]
# Glob patterns (fnmatch syntax)
globs = [".trash-*"]

[exiftool]
exclude_extensions = ["csv", "htm", "html", "json", "tsv", "xml"]

base_args = [
    "-extractEmbedded3",
    "-scanForXMP",
    "-unknown2",
    "-json",
    "-G3:1",
    "-struct",
    "-ignoreMinorErrors",
    "-charset", "filename=utf8",
    "-api", "requestall=3",
    "-api", "largefilesupport=1",
    "--",
]

[metadata_identify]
# Each key is a type name; each value is a list of regex pattern strings.
# Patterns are compiled with re.IGNORECASE at load time.
description = ['\.description$']
desktop_ini = ['\.desktop\.ini$', 'desktop\.ini$']
# ... (remaining types follow the same pattern)

[metadata_exclude]
patterns = [
    '_(meta|directorymeta)\.json$',
    '\.(cover|thumb|thumb(s|db|index|nail))$',
    '^(thumb|thumb(s|db|index|nail))\.db$',
]

[extension_groups]
archive = ["7z", "ace", "alz", "arc", "arj", "bz", "bz2", "..."]
audio = ["3gp", "8svx", "aa", "aac", "aax", "..."]
# ... (remaining groups)
```

Most users will not need a configuration file at all — the defaults cover the common case. Users who do need customization will typically modify only one or two sections (most commonly `filesystem_excludes` to add project-specific directories, or `exiftool.exclude_extensions` to add problematic file types).

#### Type mapping

TOML values map to Python types as follows in the configuration loader:

| TOML type | Python type in `IndexerConfig` |
|-----------|-------------------------------|
| String | `str` |
| Boolean | `bool` |
| Array of strings | `tuple[str, ...]` or `frozenset[str]` (depending on whether order matters) |
| Table | Nested dataclass or `dict` |
| Integer | `int` (not currently used but supported) |

The configuration loader validates types during parsing. A TOML value of the wrong type for its field produces a `ConfigurationError`. For example, `id_algorithm = 42` (integer instead of string) is a validation error.

---

### 7.7. Configuration Override and Merging Behavior

When multiple configuration layers are present (compiled defaults, user config file, project-local config file, CLI arguments), the layers must be merged into a single `IndexerConfig`. The merging strategy differs by field type.

#### Scalar fields: last-writer-wins

For scalar fields (`bool`, `str`, `Path | None`, `int`), the highest-priority layer that specifies a value wins. Lower-priority values are completely replaced.

Example: If the compiled default for `id_algorithm` is `"sha256"` and the user config file specifies `id_algorithm = "md5"`, the resolved value is `"md5"`. If the CLI then passes `--id-type sha256`, the resolved value reverts to `"sha256"`.

#### Collection fields: replace by default, append on request

For collection fields (extension sets, exclusion lists, regex pattern lists), the default merge behavior is **replace** — the highest-priority layer that specifies a value completely replaces the lower-priority value. This matches the principle of least surprise: if a user specifies `exclude_extensions = ["csv", "xml"]`, they get exactly those two extensions, not a union with the compiled defaults.

However, the more common use case is **additive**: the user wants to keep the defaults and add a few extra entries. To support this, the configuration file recognizes `_append` suffixed field names:

| Config file key | Behavior |
|-----------------|----------|
| `exclude_extensions = [...]` | **Replace**: the specified list becomes the complete exclusion set. |
| `exclude_extensions_append = [...]` | **Append**: the specified entries are added to the existing set (from the lower-priority layer). |

Both forms may be present in the same file (though this is unusual). When both appear, `_append` is applied after the replacement.

This pattern applies to all collection fields:

| Base field | Append variant |
|-----------|----------------|
| `filesystem_excludes.names` | `filesystem_excludes.names_append` |
| `filesystem_excludes.globs` | `filesystem_excludes.globs_append` |
| `exiftool.exclude_extensions` | `exiftool.exclude_extensions_append` |
| `exiftool.base_args` | `exiftool.base_args_append` |
| `metadata_exclude.patterns` | `metadata_exclude.patterns_append` |
| `metadata_identify.<type>` | `metadata_identify.<type>_append` |
| `extension_groups.<group>` | `extension_groups.<group>_append` |

> **Improvement over original:** The original provides no mechanism for user customization of configuration — all values are hardcoded in the script source. The port's layered merge system with both replace and append semantics gives users full control without requiring source code modification, fulfilling design goal G4.

#### CLI/API overrides

CLI arguments and API keyword arguments are the highest-priority layer. They override all file-based configuration. Because CLI arguments are typically scalar (flags and options), not collection-valued, the replace-vs-append distinction rarely applies. The one exception is `--exiftool-exclude-ext`, which accepts a repeatable option: each occurrence appends to the set rather than replacing it.

The configuration loader processes layers in priority order (lowest to highest), building up the resolved configuration incrementally:

```python
def load_config(
    *,
    cli_overrides: dict[str, Any] | None = None,
    target_directory: Path | None = None,
) -> IndexerConfig:
    config_dict = get_defaults_dict()                  # Layer 1
    merge_toml(config_dict, find_user_config())        # Layer 2
    if target_directory:
        merge_toml(config_dict, find_project_config(target_directory))  # Layer 3
    if cli_overrides:
        merge_overrides(config_dict, cli_overrides)    # Layer 4
    apply_implications(config_dict)                    # §7.1 implications
    validate(config_dict)                              # §7.1 validation
    return build_config(config_dict)                   # compile regexes, freeze
```

The `merge_toml()` function implements the replace/append semantics described above. The `merge_overrides()` function applies CLI/API values as simple key replacements (no append semantics). The `build_config()` function compiles regex strings, freezes collections, and constructs the final `IndexerConfig` instance.

#### Absent fields in configuration files

If a configuration file omits a field entirely, the value from the lower-priority layer (ultimately the compiled default) is preserved. Configuration files are sparse by design — a file containing only `id_algorithm = "md5"` changes only that one field and leaves all other fields at their defaults.

#### Unknown fields

If a configuration file contains a key that does not correspond to any `IndexerConfig` field, the loader logs a warning and ignores the key. Unknown keys are not fatal errors — this accommodates forward compatibility when new configuration fields are added in future versions.

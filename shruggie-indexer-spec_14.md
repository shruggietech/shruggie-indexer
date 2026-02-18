## 14. Testing

This section defines the testing strategy, test categories, coverage expectations, and execution requirements for `shruggie-indexer`. It is the normative reference for what must be tested, how tests are organized, what constitutes a passing test suite, and how the test infrastructure integrates with the CI pipeline (§13.5.1) and the cross-platform build matrix.

The test directory layout and fixture structure are defined in §3.4. The pytest configuration (markers, testpaths, strict mode) is defined in `pyproject.toml` (§13.2). The test dependencies (`pytest`, `pytest-cov`, `jsonschema`, `pydantic`) are declared in the `dev` extra (§12.3). This section defines the behavioral content of those tests — what each test category verifies, what invariants it enforces, and what the expected inputs and outputs are.

**Testing philosophy:** The original `MakeIndex` has no tests of any kind. No unit tests, no integration tests, no schema conformance checks, no assertion of expected output. Correctness was validated by the author's manual inspection of output files. The port inverts this: every behavioral contract defined in this specification SHOULD have a corresponding test. An AI implementation agent building a module from this specification SHOULD be able to derive the test cases from the module's behavioral contract without additional guidance.

> **Scope clarification:** This section describes what the tests verify and what inputs they use. It does not prescribe the exact `assert` statements or implementation details of each test function — those are derived by the implementer from the behavioral contracts in §5–§11. The section provides enough structure for an implementer to produce a complete test suite without ambiguity about coverage scope.

### 14.1. Testing Strategy

#### Test categories

The test suite is organized into four categories, each targeting a different level of abstraction:

| Category | Directory | Scope | External dependencies | Mocked components |
|----------|-----------|-------|----------------------|-------------------|
| Unit | `tests/unit/` | Individual functions and modules in isolation | None | Filesystem (via `tmp_path`), exiftool (via captured responses), configuration (via fixture configs) |
| Integration | `tests/integration/` | Full indexing pipeline from target path to validated JSON output | Filesystem (real); exiftool (optional, skippable via marker) | None — exercises the real code path end-to-end |
| Conformance | `tests/conformance/` | Output structure against the canonical v2 JSON Schema | `jsonschema` package | None — validates actual serializer output |
| Platform | `tests/platform/` | Behaviors that vary by operating system | Filesystem (real, platform-specific) | None — exercises platform-specific code paths |

Tests are not organized by source module (no `tests/core/test_hashing.py` mirroring `src/shruggie_indexer/core/hashing.py`). Instead, they are organized by test type, with a flat file layout within each category. This grouping is described in §3.4 and is driven by CI utility: the pipeline can run `pytest tests/unit/` on all platforms, `pytest tests/platform/ -m platform_linux` only on Linux, and `pytest tests/conformance/` only after a successful unit pass.

#### Test execution

All tests are runnable with a bare `pytest` invocation from the repository root:

```bash
# Run all tests
pytest

# Run only unit tests
pytest tests/unit/

# Run tests excluding those that need exiftool
pytest -m "not requires_exiftool"

# Run with coverage
pytest --cov=shruggie_indexer --cov-report=term-missing
```

The `pyproject.toml` `[tool.pytest.ini_options]` section (§13.2) registers the following markers:

| Marker | Purpose |
|--------|---------|
| `slow` | Tests that take more than a few seconds (large directory trees, hashing large files). Deselectable with `-m "not slow"` for rapid iteration. |
| `platform_windows` | Tests that only execute on Windows. Skipped on other platforms via `pytest.mark.skipif`. |
| `platform_linux` | Tests that only execute on Linux. |
| `platform_macos` | Tests that only execute on macOS. |
| `requires_exiftool` | Tests that require `exiftool` to be present on `PATH`. Skipped when exiftool is not installed. |

The `--strict-markers` option ensures that any marker typo (e.g., `@pytest.mark.requiers_exiftool`) causes a test collection error rather than silently creating a new marker. This catches a common class of CI bugs where a misspelled marker causes a test to run unconditionally instead of being skipped.

#### Fixture infrastructure

The `tests/conftest.py` file provides shared fixtures consumed across all test categories:

**`tmp_path` (built-in).** pytest's built-in `tmp_path` fixture provides a unique temporary directory per test. Unit and integration tests create their filesystem fixtures inside `tmp_path` to ensure isolation — no test depends on the state left by a previous test, and no test writes to the real filesystem outside its temporary directory.

**`sample_file` fixture.** Creates a temporary file with configurable name, content, size, and extension inside `tmp_path`. Returns the `Path` to the file. This is the primary input fixture for single-file unit tests.

**`sample_tree` fixture.** Creates a temporary directory hierarchy with configurable depth, breadth, and file contents. Used by traversal, recursive indexing, and integration tests. The fixture accepts a dictionary-based tree specification:

```python
# Illustrative — not the exact implementation.
@pytest.fixture
def sample_tree(tmp_path):
    def _make_tree(spec: dict, root: Path | None = None) -> Path:
        base = root or tmp_path
        for name, content in spec.items():
            path = base / name
            if isinstance(content, dict):
                path.mkdir(parents=True, exist_ok=True)
                _make_tree(content, path)
            elif isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(str(content), encoding="utf-8")
        return base
    return _make_tree
```

**`default_config` fixture.** Returns an `IndexerConfig` constructed from compiled defaults (§7.2) with no user overrides. Used by unit tests that need a configuration object but are not testing configuration behavior.

**`mock_exiftool` fixture.** Patches `subprocess.run` in `core/exif.py` to return pre-captured JSON responses from `tests/fixtures/exiftool_responses/`. Each response file is named after the input file type (e.g., `jpeg_response.json`, `png_response.json`). The fixture returns a context manager that sets up and tears down the mock. Unit tests that exercise EXIF-related code paths use this fixture; integration tests that need real exiftool invocation use the `requires_exiftool` marker instead.

**`exiftool_available` fixture.** A session-scoped fixture that checks `shutil.which("exiftool")` once and exposes the result as a boolean. Tests marked with `@pytest.mark.requires_exiftool` skip when this fixture returns `False`.

### 14.2. Unit Test Coverage

Unit tests exercise individual functions and modules in isolation. Each test file in `tests/unit/` corresponds to one source module, and each test function validates a single behavioral expectation defined in §6 (Core Operations), §7 (Configuration), or §5 (Output Schema models).

#### test_traversal.py

Exercises `core/traversal.list_children()` (§6.1).

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Empty directory | `tmp_path` with no children | Returns `([], [])` — two empty lists. |
| Files only | Directory containing three files, no subdirectories | Returns `([file1, file2, file3], [])` sorted lexicographically. |
| Directories only | Directory containing two subdirectories, no files | Returns `([], [dir1, dir2])` sorted lexicographically. |
| Mixed content | Directory with files and subdirectories | Files and directories returned in separate sorted lists. |
| Exclusion filtering | Directory containing a file matching `filesystem_excludes` (e.g., `desktop.ini`, `Thumbs.db`) | Excluded items are absent from both returned lists. |
| Glob exclusion | Directory containing an item matching `filesystem_exclude_globs` (e.g., `.git/`) | Glob-matched items are absent. |
| Symlink classification | Directory containing a symlink to a file and a symlink to a directory | Symlinks appear in the appropriate list based on `follow_symlinks=False` behavior of `os.scandir()`. |
| Sort order stability | Directory with files named `B.txt`, `a.txt`, `C.txt` | Case-insensitive sort: `a.txt`, `B.txt`, `C.txt`. |
| Permission error on child | Directory where one child file is unreadable | Unreadable item is excluded with a logged warning; other items returned normally. |

#### test_paths.py

Exercises `core/paths.py` functions (§6.2).

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Resolve absolute path | An absolute `Path` | Returns the same path (resolved, no symlinks followed). |
| Resolve relative path | A relative `Path` | Returns the absolute form relative to `cwd`. |
| Extract components | A path like `/home/user/photos/sunset.jpg` | `name="sunset.jpg"`, `stem="sunset"`, `suffix="jpg"` (lowercase, no dot), `parent_name="photos"`. |
| Extension lowercasing | `FILE.JPG` | `suffix="jpg"`. |
| No extension | A file named `Makefile` | `suffix=None`. |
| Multi-dot extension | `archive.tar.gz` | `suffix="gz"` (only the final extension). |
| Extension validation pass | `"jpg"` against the default regex | Validation passes. |
| Extension validation fail | `"thisextensionistoolong"` against the default regex | Validation fails; returns `None`. |
| Root-level parent | `/file.txt` on Unix, `C:\file.txt` on Windows | `parent_name` is empty string. |
| Sidecar path construction (file) | `Path("/photos/sunset.jpg")` | Returns `/photos/sunset.jpg_meta2.json`. |
| Sidecar path construction (dir) | `Path("/photos/vacation")` | Returns `/photos/vacation/_directorymeta2.json`. |

#### test_hashing.py

Exercises `core/hashing.py` functions (§6.3).

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Hash known file content | A file with content `b"hello world"` | MD5, SHA1, SHA256, SHA512 match pre-computed reference values. Hashes are uppercase hexadecimal. |
| Hash empty file | A zero-byte file | Returns the well-known empty-input hash for each algorithm. |
| Hash string | The string `"sunset.jpg"` | MD5 and SHA256 match pre-computed values. Input is UTF-8 encoded before hashing. |
| Hash empty string | `""` | Returns the well-known empty-string hash for each algorithm. |
| Multi-algorithm single pass | A 1 MB file with `algorithms=("md5", "sha1", "sha256", "sha512")` | All four digests returned. File is read once (verifiable by mocking `open()` to count reads). |
| Default algorithms | `hash_file(path)` with no explicit `algorithms` argument | Returns a `HashSet` with `md5` and `sha256` populated. |
| SHA-512 optional | `hash_file(path, algorithms=("md5", "sha256"))` | Returned `HashSet` has `sha512=None`. |
| Directory identity (two-layer) | `hash_directory_id("vacation", "photos")` | Result matches `hash_string(hash_string("vacation").md5 + hash_string("photos").md5)`. The two-layer scheme is validated against a manual step-through. |
| Null hash constant | Requesting the null hash for an algorithm | Returns the hash of `b"0"` for the given algorithm — the well-known null-hash sentinel. |
| ID prefix — file | A file entry | Identity string starts with `y`. |
| ID prefix — directory | A directory entry | Identity string starts with `x`. |
| ID prefix — generated metadata | A generated metadata entry | Identity string starts with `z`. |
| HashSet uppercase | Any hash computation | All hex strings contain only `0-9A-F`, never lowercase `a-f`. |

#### test_timestamps.py

Exercises `core/timestamps.py` (§6.5).

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Mtime extraction | `os.stat()` of a known file | `modified.unix` is `int(st_mtime * 1000)`. `modified.iso` is a valid ISO 8601 string matching the same instant. |
| Atime extraction | Same file | `accessed.unix` and `accessed.iso` consistent with `st_atime`. |
| Creation time (Windows/macOS) | File on a platform with `st_birthtime` or `st_ctime` as creation time | `created.unix` and `created.iso` populated. |
| Creation time (Linux fallback) | File on Linux where `st_birthtime` is unavailable | `created` is `None` (not an error). |
| ISO 8601 format | Any timestamp | ISO string matches `YYYY-MM-DDTHH:MM:SS` format (with optional fractional seconds and timezone). |
| Unix milliseconds | A file with `st_mtime = 1700000000.123` | `unix` value is `1700000000123` (integer milliseconds, not seconds). |

#### test_exif.py

Exercises `core/exif.py` (§6.6). Uses `mock_exiftool` fixture for most tests.

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Successful extraction | A JPEG file with mock exiftool returning valid JSON | Returns parsed metadata dict. |
| Exiftool not found | `shutil.which("exiftool")` patched to return `None` | Returns `None`. Warning logged once (not per file). |
| Excluded file type | A `.zip` file when `.zip` is in `exiftool_exclude_extensions` | Returns `None`. Debug-level log emitted. |
| Exiftool error | Mock returning non-zero returncode | Returns `None`. Warning logged with stderr content. |
| Malformed JSON output | Mock returning invalid JSON on stdout | Returns `None`. Warning logged. |
| Key filtering | Mock returning JSON with keys in the exclusion list | Excluded keys absent from returned dict. |
| Timeout | Mock raising `subprocess.TimeoutExpired` | Returns `None`. Warning logged. |

#### test_sidecar.py

Exercises `core/sidecar.py` (§6.7). Uses static fixture files from `tests/fixtures/sidecar_samples/`.

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| JSON sidecar discovery | Parent file with a matching `*_meta.json` sidecar alongside it | Sidecar discovered and classified as `JsonMetadata`. |
| Description sidecar | A `.description` file alongside a parent | Content read as plain text; `MetadataEntry` created with correct type and origin. |
| Hash sidecar | A `.md5` file alongside a parent | Content parsed as hash value. |
| Binary sidecar (thumbnail) | A `.jpg` file matching the thumbnail regex | Content Base64-encoded. `transforms` list includes the encoding operation. |
| No sidecars present | A parent file with no matching sidecar files | Returns empty list. |
| Malformed JSON sidecar | A `_meta.json` file containing invalid JSON | Warning logged. Sidecar skipped or content treated as raw text (field-level error, §4.5). |
| Multiple sidecars per parent | A parent file with three different sidecar types | All three discovered and returned as separate `MetadataEntry` objects. |
| MetaMergeDelete queueing | Config with `meta_merge_delete=True`; valid sidecar found | Sidecar path appended to the delete queue. |
| Sidecar for directory | `_directorymeta.json` inside a directory | Discovered and classified correctly. |

#### test_entry.py

Exercises `core/entry.py` — `build_file_entry()`, `build_directory_entry()`, and `index_path()` (§6.8).

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Single file entry | A text file in `tmp_path` | Returns `IndexEntry` with `type="file"`, populated hashes, timestamps, name, and size. |
| Directory entry (flat) | A directory with three files, `recursive=False` | Returns `IndexEntry` with `type="directory"` and `items` containing three child entries. No subdirectory recursion. |
| Directory entry (recursive) | A directory with nested subdirectories | Returns `IndexEntry` with `items` nested to match the filesystem hierarchy. |
| Symlink file entry | A symlink to a file | `is_link=True`. Hashes computed from name (not content). |
| Empty directory | A directory with no children | Returns `IndexEntry` with `items=[]`. |
| Item-level error handling | A file whose content raises `PermissionError` during hashing | Item skipped; warning logged. Remaining items processed normally. |
| Field-level error handling | A file where exiftool fails but hashing succeeds | `IndexEntry` produced with `null` metadata; hashes and timestamps populated. |
| ID algorithm selection | Config with `id_algorithm="sha256"` | `_id` field is `"y" + sha256_hash`, not MD5. |

#### test_serializer.py

Exercises `core/serializer.py` (§6.9).

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Basic serialization | A fully-populated `IndexEntry` | Valid JSON output. `schema_version` is the first key. All required fields present. |
| Null optional fields | An `IndexEntry` with `metadata=None` | `metadata` key present in JSON with value `null`. |
| SHA-512 omission | An `IndexEntry` where `HashSet.sha512` is `None` | `sha512` key absent from the `hashes` object (not present as `null`). |
| Nested items | A directory `IndexEntry` with child entries | `items` array contains correctly serialized child objects. |
| Orjson fallback | When `orjson` is not importable | Falls back to `json.dumps()`; output is semantically identical. |
| Ensure ASCII false | Filenames with non-ASCII characters (e.g., `日本語.txt`) | Non-ASCII characters preserved in output, not escaped to `\uXXXX`. |
| Indent formatting | Default serialization | Output is indented (2-space) for readability. |

#### test_rename.py

Exercises `core/rename.py` (§6.10).

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Successful rename | A file, its computed `storage_name`, rename enabled | File renamed to `storage_name` on disk. Old path no longer exists. |
| Dry run | Same file, `dry_run=True` | File NOT renamed. Log message indicates what would have been renamed. |
| Name collision | A file whose `storage_name` already exists at the target path | Rename skipped. Warning logged. Original file untouched. |
| Cross-filesystem rename | (Platform-dependent) A file where `os.rename()` would fail across mount points | `shutil.move()` fallback succeeds. |

#### test_schema.py

Exercises `models/schema.py` — the dataclass definitions and optional Pydantic models (§5).

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| IndexEntry construction | All required fields provided | Object created successfully. All fields accessible. |
| IndexEntry missing required field | Required field omitted | `TypeError` raised (frozen dataclass constructor enforcement). |
| HashSet uppercase invariant | A `HashSet` constructed with lowercase hex | Implementer decides: either the constructor normalizes to uppercase, or a validation check rejects lowercase. The test asserts whichever contract the implementation defines. |
| Pydantic model validation (if available) | Valid JSON parsed via `IndexEntry.model_validate_json()` | Pydantic model constructed without errors. |
| Pydantic model rejection (if available) | JSON with wrong types or missing required fields | Pydantic `ValidationError` raised with descriptive message. |

#### test_config.py

Exercises `config/loader.py` and `config/types.py` (§7).

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Default config | `load_config()` with no config file present | Returns `IndexerConfig` with all default values from §7.2. |
| TOML file loading | A valid TOML config file in `tmp_path` | Overridden values applied; non-overridden values retain defaults. |
| Invalid TOML syntax | A TOML file with syntax errors | `ConfigurationError` raised (or equivalent). Clear error message including the file path and parse error. |
| Unknown keys in TOML | A TOML file with keys not defined in `IndexerConfig` | Unknown keys ignored (not an error). Logged at debug level. |
| CLI override merging | A TOML file setting `recursive=False`, CLI override setting `recursive=True` | CLI override wins: `config.recursive == True`. |
| Frozen immutability | Attempting to set a field on a constructed `IndexerConfig` | `FrozenInstanceError` raised. |
| Sidecar pattern configuration | A TOML file adding a new sidecar type regex | New pattern appears in `config.sidecar_include_patterns`. |
| Exiftool exclusion extension | A TOML file adding `.xyz` to the exclusion list | `.xyz` present in `config.exiftool_exclude_extensions`. |

### 14.3. Integration Tests

Integration tests exercise the full indexing pipeline end-to-end — from a filesystem path to validated JSON output — without mocking the core engine. The distinction from unit tests is that integration tests validate the wiring between modules (does `index_path()` correctly thread configuration through traversal, hashing, timestamps, exif, sidecar, serialization?), while unit tests validate individual module behavior in isolation.

Integration tests create real filesystem structures in `tmp_path` and call the public API or the CLI to process them. Output is captured and validated for structural correctness, field presence, and value accuracy.

#### test_single_file.py

Exercises the single-file indexing path: `index_path()` called on a file target.

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Text file | A `.txt` file with known content | Output `IndexEntry` has `type="file"`, correct `name.text`, non-null `hashes.content` with verifiable digests, valid timestamps, `items` absent or `null`. |
| Binary file | A `.bin` file with random bytes | Hashes computed from actual content. Size matches file length. |
| Zero-byte file | An empty file | Hashes are the well-known empty-input values. `size.bytes == 0`. |
| File with sidecar | A `.jpg` file with a `_meta.json` sidecar alongside it, `extract_exif=False`, `meta_merge=True` | `metadata` array includes a sidecar-origin entry with the sidecar's content. |
| File with exiftool | A real JPEG file, `extract_exif=True` | `metadata` array includes a generated-origin `exiftool.json_metadata` entry. (Requires `requires_exiftool` marker.) |
| Symlink to file | A symlink pointing to a real file | `is_link=True`. Name hashes used for identity (not content hashes). |

#### test_directory_flat.py

Exercises flat (non-recursive) directory indexing.

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Directory with files | A directory containing three files | Root entry has `type="directory"`. `items` contains three file entries. No subdirectory entries in `items`. |
| Directory with subdirectories | A directory containing files and one subdirectory, `recursive=False` | `items` includes the subdirectory as a directory entry with its own identity and timestamps, but the subdirectory's `items` is absent (not recursed into). |
| Empty directory | A directory with no children | Root entry has `items=[]`. |

#### test_directory_recursive.py

Exercises recursive directory indexing.

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Two-level tree | A directory with files and one subdirectory containing files | Root `items` includes the subdirectory entry. That subdirectory entry's `items` includes its child files. |
| Deep nesting | A 5-level deep directory tree | All levels present in the nested `items` structure. |
| Large flat directory | A directory with 100 files | All 100 files present in `items`. Marked `@pytest.mark.slow` if execution exceeds a few seconds. |
| Mixed exclusions | A tree containing both included and excluded items (e.g., `desktop.ini`, `.git/`) | Excluded items absent from `items` at all levels. |

#### test_output_modes.py

Exercises the three output routing modes (§8.3, §8.9).

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Stdout output | `index_path()` with `output_stdout=True` | JSON written to the captured stdout stream. Valid JSON parseable by `json.loads()`. |
| File output | Config with `output_file` pointing to a path in `tmp_path` | JSON written to the specified file. File exists after invocation. Content is valid JSON. |
| In-place output | Config with `output_inplace=True` on a directory | `_meta2.json` sidecar files created alongside each indexed file. `_directorymeta2.json` created in each indexed directory. |
| Stdout suppression | `output_stdout=False`, `output_file` set | No output on stdout; output written to file only. |
| Combined modes | `output_stdout=True` and `output_file` set | Output appears on both stdout and in the file. Both are valid JSON. |

#### test_cli.py

Exercises the CLI interface (§8) by invoking `click`'s test runner or via `subprocess.run()`.

| Test case | Input | Expected behavior |
|-----------|-------|-------------------|
| Default invocation | `shruggie-indexer` with no arguments (CWD is `tmp_path`) | Indexes the current directory recursively. Exits with code 0. JSON on stdout. |
| `--help` | `shruggie-indexer --help` | Exits with code 0. Output contains usage text matching §8.1. |
| `--version` | `shruggie-indexer --version` | Exits with code 0. Output contains the version string from `_version.py`. |
| File target | `shruggie-indexer path/to/file.txt` | Indexes the single file. Output is one `IndexEntry`. |
| Directory target | `shruggie-indexer path/to/dir/` | Indexes the directory recursively. |
| `--no-recursive` | `shruggie-indexer --no-recursive path/to/dir/` | Flat traversal. Output contains only immediate children. |
| `--outfile` | `shruggie-indexer -o output.json path/` | Output written to `output.json`. Stdout is empty. |
| `--meta` | `shruggie-indexer --meta path/to/file.jpg` | Metadata extraction attempted. (Skipped if exiftool unavailable.) |
| `--id-type sha256` | `shruggie-indexer --id-type sha256 path/to/file.txt` | `_id` field uses SHA-256, not MD5. `id_algorithm` field is `"sha256"`. |
| Invalid target | `shruggie-indexer /nonexistent/path` | Exits with code 3 (`TARGET_ERROR`). Error message on stderr. |
| Invalid flag combination | `shruggie-indexer --meta-merge-delete` (without `--outfile` or `--inplace`) | Exits with code 2 (`CONFIGURATION_ERROR`). Error message explains the safety requirement. |
| `-v` verbosity | `shruggie-indexer -v path/` | INFO-level log messages appear on stderr. |
| `-q` quiet mode | `shruggie-indexer -q path/` | No log output on stderr (except fatal errors). |
| Exit code 0 | Successful single-file index | `result.returncode == 0`. |
| Exit code 1 | Directory with one unreadable file | `result.returncode == 1` (partial failure). Output still produced for readable files. |

### 14.4. Output Schema Conformance Tests

Conformance tests validate that the JSON output produced by the indexer structurally matches the canonical v2 JSON Schema definition at `schemas.shruggie.tech/data/shruggie-indexer-v2.schema.json`. These tests use the `jsonschema` package (§12.3) to perform Draft-07 validation against actual serializer output.

Conformance tests are architecturally distinct from unit and integration tests: they do not test implementation logic. They test whether the output artifact — the final JSON bytes — conforms to the published contract. A conformance failure means the serializer is producing output that an external consumer would reject as invalid.

#### Schema loading

The `tests/conformance/test_v2_schema.py` module loads the canonical schema once per test session. The schema SHOULD be loaded from a local copy committed to `tests/fixtures/` (for offline reproducibility) and validated periodically against the published URL to detect drift. The test module SHOULD NOT fetch the schema from the network on every test run — this makes the test suite dependent on network availability and introduces latency.

```python
# Illustrative — not the exact implementation.
import json
import jsonschema
import pytest

SCHEMA_PATH = Path(__file__).parent.parent / "fixtures" / "shruggie-indexer-v2.schema.json"

@pytest.fixture(scope="session")
def v2_schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

def validate_entry(entry_json: str, schema: dict) -> None:
    """Validate a JSON string against the v2 schema. Raises on failure."""
    instance = json.loads(entry_json)
    jsonschema.validate(instance=instance, schema=schema)
```

#### Conformance test cases

| Test case | Input | Validation |
|-----------|-------|------------|
| Single file entry | Index a text file, serialize to JSON | `jsonschema.validate()` passes against the v2 schema. |
| Directory entry (flat) | Index a flat directory | Schema validation passes on the root entry and each child in `items`. |
| Directory entry (recursive) | Index a recursive directory tree | Schema validation passes at every level of the nested structure. |
| Entry with metadata | Index a file with sidecar metadata, `meta_merge=True` | Schema validation passes; `metadata` array entries conform to `MetadataEntry` definition. |
| Entry with exiftool metadata | Index a JPEG with `extract_exif=True` (requires exiftool) | Schema validation passes; generated `MetadataEntry` conforms. |
| Symlink entry | Index a symlink | Schema validation passes; `is_link=True` is valid. |
| All field types exercised | A purpose-built fixture that exercises every optional field and every sub-object type | Full schema coverage — every `$ref` in the schema is exercised at least once. |
| Schema version discriminator | Any valid entry | `entry["schema_version"] == 2`. |
| No additional properties | Any valid entry | Validation with `additionalProperties: false` passes — no unexpected keys at any nesting level. |

#### Serialization invariant checks

Beyond schema validation, conformance tests verify the serialization invariants defined in §5.12:

| Invariant | Test |
|-----------|------|
| Required fields always present | Parse the JSON output and verify that every field listed in the schema's `required` array is present as a key (even if the value is `null`). |
| SHA-512 omission when not computed | When `compute_sha512=False`, verify that `sha512` key does NOT appear in any `hashes` object. |
| Sidecar-only fields present for sidecars | For `MetadataEntry` objects with `origin="sidecar"`, verify that `file_system`, `size`, and `timestamps` are present. |
| Generated-only fields absent for generated entries | For `MetadataEntry` objects with `origin="generated"`, verify that `file_system`, `size`, and `timestamps` are absent. |

### 14.5. Cross-Platform Test Matrix

The test suite runs on three platforms in the CI pipeline (§13.5.1). Most tests are platform-agnostic and run identically everywhere. Platform-specific tests are isolated in `tests/platform/` and conditionally executed via markers.

#### CI matrix

| Platform | Runner | Python version | Test scope |
|----------|--------|---------------|------------|
| Windows x64 | `windows-latest` | 3.12 | `tests/unit/`, `tests/integration/`, `tests/conformance/`, `tests/platform/` (with `platform_windows` marker) |
| Linux x64 | `ubuntu-latest` | 3.12 | `tests/unit/`, `tests/integration/`, `tests/conformance/`, `tests/platform/` (with `platform_linux` marker) |
| macOS x64 | `macos-13` | 3.12 | `tests/unit/`, `tests/integration/`, `tests/conformance/`, `tests/platform/` (with `platform_macos` marker) |
| macOS ARM64 | `macos-latest` | 3.12 | Same as macOS x64. Validates ARM64 behavior. |

All runners install the package with `pip install -e ".[dev,cli,gui]"` and run `pytest` with the `requires_exiftool` marker excluded (unless exiftool is pre-installed on the runner). The CI pipeline does not install exiftool — exiftool-dependent integration tests are validated during local development and optionally in a dedicated CI job that installs exiftool.

#### Platform-specific test targets

**`tests/platform/test_timestamps_platform.py`**

| Test case | Platform | Expected behavior |
|-----------|----------|-------------------|
| Creation time via `st_birthtime` | macOS | `created` timestamp populated from `st_birthtime`. |
| Creation time via `st_ctime` | Windows | `created` timestamp populated from `st_ctime` (which is creation time on NTFS). |
| Creation time fallback | Linux (ext4) | `created` is `None` — `st_birthtime` not available, `st_ctime` is change time, not creation time. |
| Timestamp precision | All platforms | Unix millisecond value and ISO string represent the same instant within 1-second tolerance. |

**`tests/platform/test_symlinks_platform.py`**

| Test case | Platform | Expected behavior |
|-----------|----------|-------------------|
| File symlink detection | All | `is_link=True` for symlinks created with `Path.symlink_to()`. |
| Directory symlink detection | All | `is_link=True` for directory symlinks. |
| Dangling symlink handling | All | Item-level error: warning logged, item either skipped or produced with degraded fields. |
| Symlink hashing fallback | All | Symlinked files use name-based hashing (not content hashing). |
| Symlink creation (Windows) | Windows | Test uses `os.symlink()` with appropriate privileges. Skipped if symlink creation fails (non-admin user without Developer Mode). |

#### Platform-conditional skip pattern

Platform-specific tests use `pytest.mark.skipif` with platform detection:

```python
import platform
import pytest

is_windows = platform.system() == "Windows"
is_linux = platform.system() == "Linux"
is_macos = platform.system() == "Darwin"

@pytest.mark.platform_windows
@pytest.mark.skipif(not is_windows, reason="Windows-specific test")
def test_creation_time_windows(sample_file):
    ...
```

The double-marker pattern (`@pytest.mark.platform_windows` plus `@pytest.mark.skipif`) enables both marker-based filtering (`-m platform_windows`) and automatic skipping on non-matching platforms. The `skipif` ensures the test never executes on the wrong platform, while the marker enables positive selection (`pytest -m platform_windows` runs only Windows tests).

### 14.6. Backward Compatibility Validation

Backward compatibility tests validate that the port produces output semantically equivalent to the original `MakeIndex` implementation for the same input paths — accounting for the documented v1-to-v2 schema restructuring (§5) and the fourteen intentional deviations (§2.6). These tests are not schema conformance tests (those validate structure); they are semantic equivalence tests (these validate that the indexer computes the correct values).

#### Reference data approach

The test suite includes a set of pre-computed reference entries — known-good `IndexEntry` values for specific inputs. These reference entries are created by running the original `MakeIndex` on a set of controlled input files, manually converting the v1 output to v2 field structure, and committing the result as fixture data in `tests/fixtures/`.

Reference data files follow a naming convention: `tests/fixtures/reference/{test_name}.v2.json`. Each file contains a complete v2 `IndexEntry` with all fields populated as the indexer should produce them.

#### What backward compatibility validates

| Validation target | How it is tested |
|-------------------|-----------------|
| Hash identity equivalence | For a file with known content, the port's `_id` field matches the reference. This validates that hashing (content encoding, algorithm selection, hex formatting, prefix application) produces the same identity as the original. |
| Name hash equivalence | For a file with a known name, the port's `name.hashes` match the reference. This validates that string hashing (UTF-8 encoding, case handling) matches the original. |
| Directory identity equivalence | For a directory with a known name and parent, the port's `_id` matches the reference. This validates the two-layer `hash(hash(name) + hash(parent))` scheme. |
| Timestamp equivalence | For a file with known timestamps, the port's `timestamps` values match the reference within platform precision limits (±1 second for ISO, ±1000 for Unix milliseconds). |
| Sidecar discovery equivalence | For a file with known sidecar files alongside it, the port discovers and classifies the same sidecars as the original. |
| Sidecar content equivalence | For a JSON sidecar with known content, the port's parsed metadata matches the reference. |

#### Intentional deviation exclusions

The fourteen intentional deviations (DEV-01 through DEV-14, §2.6) produce expected differences from the original's output. Backward compatibility tests explicitly account for these:

| Deviation | Impact on backward compatibility test |
|-----------|--------------------------------------|
| DEV-02 (all four algorithms computed) | Reference data includes SHA-1 and SHA-512 values. The original would have `null` for these; the port populates them. Tests validate the populated values against independently computed hashes, not against the original's `null`. |
| DEV-07 (direct timestamp derivation) | Timestamps derived from `os.stat()` floats rather than formatted strings. Tests allow a ±1 second tolerance window for ISO timestamps and ±1000 for Unix millisecond values. |
| DEV-09 (computed null-hash constants) | The port computes null hashes at module load time. Reference data reflects the computed values (`hash(b"0")`), not the original's hardcoded constants (which should be identical, but the test verifies this). |

Tests that exercise unchanged behavior (hash identity, sidecar discovery, directory two-layer scheme) require exact matches. Tests that exercise deviated behavior use the deviation-specific validation rules above.

#### Fixture creation and maintenance

Reference fixtures are created once during the initial porting effort and committed to the repository. They are NOT regenerated on every test run. Updating reference fixtures requires:

1. Running the original `MakeIndex` on the controlled input files.
2. Converting v1 output to v2 structure using the field mapping from §5.11.
3. Applying the fourteen deviation adjustments.
4. Committing the updated fixtures with a description of what changed.

This is a manual process — automated reference generation would require running the original PowerShell implementation, which is not available in the CI environment and is not included in the repository (§1.2).

### 14.7. Performance Benchmarks

Performance benchmarks validate that the indexer operates within acceptable time and resource bounds for representative workloads. Benchmarks are not pass/fail tests — they produce timing data that is tracked over time to detect performance regressions. They are marked `@pytest.mark.slow` and are excluded from the default test run.

#### Benchmark scenarios

| Scenario | Input | Measured metric | Baseline expectation |
|----------|-------|-----------------|---------------------|
| Single file hashing (small) | A 1 KB file, all four algorithms | Wall-clock time for `hash_file()` | < 10 ms. Hash computation for small files should be dominated by file-open overhead, not computation. |
| Single file hashing (large) | A 100 MB file, all four algorithms | Wall-clock time and throughput (MB/s) | Throughput within 50% of raw `hashlib` speed on the same file. Validates that the multi-algorithm single-pass approach does not introduce unexpected overhead. |
| Directory traversal (wide) | A directory with 10,000 files | Wall-clock time for `list_children()` | < 5 seconds. Single-pass `os.scandir()` enumeration should be I/O-bound. |
| Directory traversal (deep) | A 50-level deep directory chain | Wall-clock time for recursive `index_path()` | Completes without stack overflow. Python's default recursion limit (1000) is not exceeded for reasonable depths. |
| Full pipeline (small tree) | A directory tree with 100 files across 10 subdirectories | Wall-clock time for `index_path()` with `recursive=True` | < 5 seconds (excluding exiftool). Establishes a baseline for per-file overhead. |
| Full pipeline (medium tree) | A directory tree with 1,000 files across 100 subdirectories | Wall-clock time for `index_path()` with `recursive=True` | < 60 seconds (excluding exiftool). Linear scaling from the small-tree baseline. |
| Serialization (large output) | An `IndexEntry` tree with 1,000 entries | Wall-clock time for `serialize_entry()` | < 2 seconds with `json.dumps()`. Faster with `orjson` if available. |
| Exiftool invocation | 10 JPEG files via `subprocess.run()` (per-file mode) | Wall-clock time per file | < 500 ms per file. Dominated by exiftool startup time. |

#### Benchmark implementation

Benchmarks use `time.perf_counter()` for wall-clock measurement. They are implemented as regular pytest test functions with timing logic:

```python
# Illustrative — not the exact implementation.
import time
import pytest

@pytest.mark.slow
def test_benchmark_hash_large_file(tmp_path):
    """Benchmark: hash a 100 MB file with all four algorithms."""
    large_file = tmp_path / "large.bin"
    large_file.write_bytes(b"\x00" * (100 * 1024 * 1024))

    start = time.perf_counter()
    result = hash_file(large_file, algorithms=("md5", "sha1", "sha256", "sha512"))
    elapsed = time.perf_counter() - start

    # Log the result for regression tracking
    throughput = 100 / elapsed  # MB/s
    print(f"\n  hash_file (100 MB, 4 algorithms): {elapsed:.3f}s ({throughput:.1f} MB/s)")

    # Soft assertion — failure logs a warning, does not fail the test
    assert result.md5 is not None  # Sanity check
```

Benchmarks do NOT have hard pass/fail thresholds in CI. Timing is machine-dependent and varies significantly between CI runners and local hardware. Instead, benchmarks produce timing output that is reviewed during development to detect regressions. A future enhancement (post-MVP) may integrate `pytest-benchmark` or a similar tool for structured performance tracking with statistical analysis.

#### Resource bounds

Beyond timing, two resource limits are validated:

**Memory.** The indexer processes files by streaming chunks (§6.3, §17.2) and does not load entire file contents into memory. A benchmark test that hashes a 1 GB file should not cause memory usage to spike to 1 GB. This is validated by monitoring `os.getpid()` memory via `resource.getrusage()` (Unix) or `psutil` (cross-platform, if available in the `dev` extra) before and after the operation.

**Recursion depth.** The recursive directory traversal must not exceed Python's default recursion limit (typically 1000 frames). A benchmark test that indexes a 100-level deep directory tree validates that the implementation does not use call-stack recursion that would fail at depth. If the port uses recursive function calls for tree traversal, the benchmark validates that the maximum practical depth (50–100 levels) is safe. Deeper trees are a pathological case documented in §16.5.

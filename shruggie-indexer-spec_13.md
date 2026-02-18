## 13. Packaging and Distribution

This section defines how `shruggie-indexer` is packaged, built, versioned, and distributed — from the `pyproject.toml` configuration that governs metadata and dependency declarations, through the entry points that connect the installed package to its three delivery surfaces (CLI, GUI, library), to the PyInstaller-based standalone executable builds and the GitHub Releases workflow that produces downloadable artifacts. It is the normative reference for every field in `pyproject.toml`, every entry point registration, and every artifact that a release produces.

The packaging conventions follow those established by `shruggie-feedtools` (§1.5, External References). Where this section does not explicitly define a convention — such as the exact ruff rule set or the pytest marker registration syntax — the `shruggie-feedtools` `pyproject.toml` is the normative reference for project scaffolding. Where the indexer's needs diverge from feedtools (additional extras, a second PyInstaller target for the GUI), the divergence is documented explicitly.

**Key constraint (reiterated from §2.1):** This project is not published to PyPI. End users download pre-built executables from GitHub Releases. The `pip install` workflow — including editable installs, extras, and the `[project]` metadata table — serves contributors setting up a local development environment, the CI pipeline building release artifacts, and hypothetical future library consumers who install directly from the GitHub repository URL. The `pyproject.toml` is therefore structured to support both `pip install -e ".[dev,cli,gui]"` for contributors and `pyinstaller` for release builds, but it does not include PyPI-specific fields (classifiers, project URLs) that would only matter for a published package.

### 13.1. Package Metadata

The `[project]` table in `pyproject.toml` declares the package identity, authorship, licensing, and compatibility metadata. These fields are consumed by the build backend (`hatchling`), by `pip install` for dependency resolution, and by the `--version` flag for version display.

| Field | Value | Notes |
|-------|-------|-------|
| `name` | `"shruggie-indexer"` | The distribution name. Hyphens are normalized to underscores for the import name (`shruggie_indexer`). |
| `description` | `"Filesystem indexer with hash-based identity, metadata extraction, and structured JSON output"` | Single-line summary. |
| `readme` | `"README.md"` | Points to the repository root README. |
| `license` | `"Apache-2.0"` | SPDX license identifier, referencing the `LICENSE` file at the repository root (§3.1). |
| `requires-python` | `">=3.12"` | Matches the Python version floor established in §2.5. The `>=` constraint (not `==`) allows any 3.12+ interpreter. |
| `authors` | `[{name = "William Thompson"}]` | Single author for the MVP. |
| `keywords` | `["indexer", "filesystem", "metadata", "exif", "hashing"]` | Discovery keywords — relevant if the package is ever published, harmless otherwise. |
| `dynamic` | `["version"]` | The version string is read from `src/shruggie_indexer/_version.py` by hatchling's version plugin (§13.6). It is not hardcoded in `pyproject.toml`. |

Fields deliberately omitted:

- `classifiers` — PyPI trove classifiers are not included because the package is not published to PyPI. If the project is ever published, classifiers should be added at that time to reflect the license, supported Python versions, operating systems, and development status.
- `project-urls` — Same rationale. URLs for the repository, documentation, and issue tracker can be added if the project is published.

### 13.2. pyproject.toml Configuration

The complete `pyproject.toml` is the single configuration file for the build system, package metadata, dependency declarations, entry points, and tool settings. The following is the canonical content — an implementer SHOULD produce a file equivalent to this, though field ordering within tables may vary.

```toml
# ─── Build system ───────────────────────────────────────────────────────────

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# ─── Package metadata ──────────────────────────────────────────────────────

[project]
name = "shruggie-indexer"
description = "Filesystem indexer with hash-based identity, metadata extraction, and structured JSON output"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.12"
authors = [{name = "William Thompson"}]
keywords = ["indexer", "filesystem", "metadata", "exif", "hashing"]
dynamic = ["version"]
dependencies = []

[project.optional-dependencies]
cli = ["click>=8.1"]
gui = ["customtkinter>=5.2"]
perf = ["orjson>=3.9", "pyexiftool>=0.5"]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "jsonschema>=4.17",
    "pydantic>=2.0",
    "ruff>=0.3",
    "tqdm>=4.65",
    "rich>=13.0",
]
all = ["shruggie-indexer[cli,gui,perf]"]

# ─── Entry points ──────────────────────────────────────────────────────────

[project.scripts]
shruggie-indexer = "shruggie_indexer.cli.main:main"

[project.gui-scripts]
shruggie-indexer-gui = "shruggie_indexer.gui.app:main"

# ─── Hatchling configuration ───────────────────────────────────────────────

[tool.hatch.version]
path = "src/shruggie_indexer/_version.py"

[tool.hatch.build.targets.wheel]
packages = ["src/shruggie_indexer"]

# ─── Pytest ────────────────────────────────────────────────────────────────

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "platform_windows: marks tests that only run on Windows",
    "platform_linux: marks tests that only run on Linux",
    "platform_macos: marks tests that only run on macOS",
    "requires_exiftool: marks tests that require exiftool on PATH",
]

# ─── Ruff ──────────────────────────────────────────────────────────────────

[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src"]

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "TCH",  # flake8-type-checking
    "RUF",  # ruff-specific rules
]

[tool.ruff.lint.isort]
known-first-party = ["shruggie_indexer"]

# ─── PyInstaller (reference only — actual builds use .spec files) ──────────

[tool.pyinstaller]
# This table is not consumed by pyinstaller directly.
# It is included as a documentation aid; the build scripts
# (scripts/build.ps1, scripts/build.sh) invoke pyinstaller
# with explicit arguments or .spec files. See §13.4.
```

#### Notable design decisions

**Empty `dependencies` list.** The `[project.dependencies]` list is deliberately empty (§12.3). A bare `pip install shruggie-indexer` installs zero third-party packages. All third-party dependencies are optional extras. This is the implementation of design goal G5 (§2.3): the core indexing engine runs on the standard library alone.

**`[project.scripts]` vs. `[project.gui-scripts]`.** The CLI entry point is registered under `[project.scripts]`, which creates a platform-appropriate console script wrapper (`shruggie-indexer` on Linux/macOS, `shruggie-indexer.exe` on Windows). The GUI entry point is registered under `[project.gui-scripts]`, which on Windows creates a wrapper that does not allocate a console window — this prevents the "flash of black console window" that would occur if a GUI application were launched from a `[project.scripts]` entry point. On Linux and macOS, `[project.gui-scripts]` behaves identically to `[project.scripts]`. The distinction matters only for the `pip install` development workflow; the PyInstaller-built standalone executables handle console/no-console via their own `--windowed` flag (§13.4).

**`[tool.hatch.version]` path.** The version string is read from `src/shruggie_indexer/_version.py` by hatchling's version plugin. This is a single-source-of-truth pattern: the version is defined in exactly one place (the `_version.py` file) and read by `pyproject.toml` (via hatchling), by `__init__.py` (via import), and by the CLI `--version` flag (via the same import). See §13.6 for the full version management strategy.

**Ruff configuration scope.** The ruff rule set is deliberately conservative for the MVP — it enables the most universally beneficial lint rules without imposing subjective style preferences (no `D` docstring enforcement, no `ANN` annotation enforcement, no `PT` pytest style rules). The rule set can be expanded incrementally as the codebase matures. The `target-version = "py312"` setting ensures ruff applies pyupgrade transformations appropriate to the Python 3.12 floor.

**`[tool.pyinstaller]` as documentation.** The `pyproject.toml` includes a `[tool.pyinstaller]` comment block as a breadcrumb for implementers. PyInstaller does not natively read configuration from `pyproject.toml` — it uses `.spec` files or command-line arguments. The actual build configuration lives in the build scripts (§3.5) and the `.spec` files described in §13.4.

### 13.3. Entry Points and Console Scripts

The package registers two entry points — one for the CLI and one for the GUI — plus the `python -m` module execution path. All three routes converge on the same core library.

#### CLI entry point: `shruggie-indexer`

| Registration | `[project.scripts]` in `pyproject.toml` |
|---|---|
| Entry point string | `shruggie-indexer = "shruggie_indexer.cli.main:main"` |
| Invocation | `shruggie-indexer [OPTIONS] [TARGET]` |
| Requires | `click` (installed via the `cli` extra) |
| Failure without dependency | `ImportError` caught in `__main__.py`; prints install instructions to stderr; exits with code 1 |

When `pip install -e ".[cli]"` is executed, pip creates a wrapper script named `shruggie-indexer` (or `shruggie-indexer.exe` on Windows) in the virtual environment's `bin/` (or `Scripts/`) directory. This wrapper imports `shruggie_indexer.cli.main` and calls its `main()` function. The wrapper is a platform-native console script — on Linux/macOS it is a small Python script with a shebang line pointing to the venv interpreter; on Windows it is a `.exe` launcher generated by pip.

#### GUI entry point: `shruggie-indexer-gui`

| Registration | `[project.gui-scripts]` in `pyproject.toml` |
|---|---|
| Entry point string | `shruggie-indexer-gui = "shruggie_indexer.gui.app:main"` |
| Invocation | `shruggie-indexer-gui` (no arguments for the MVP) |
| Requires | `customtkinter` (installed via the `gui` extra) |
| Failure without dependency | `ImportError` caught at the GUI entry point; prints install instructions to stderr; exits with code 1 |

The `[project.gui-scripts]` registration is functionally identical to `[project.scripts]` on Linux and macOS. On Windows, it creates a `shruggie-indexer-gui.exe` wrapper that suppresses console window creation — the GUI application launches without a visible terminal window. This is the standard mechanism for Python GUI applications on Windows and requires no special handling in the source code.

#### Module execution: `python -m shruggie_indexer`

| Mechanism | `__main__.py` in the top-level package |
|---|---|
| Invocation | `python -m shruggie_indexer [OPTIONS] [TARGET]` |
| Behavior | Identical to the `shruggie-indexer` console script |
| Implementation | Imports and calls `cli.main.main()` with the same `ImportError` guard |

The `__main__.py` file (§3.2) provides the `python -m` execution path. It contains no logic beyond importing and calling the CLI entry point:

```python
# src/shruggie_indexer/__main__.py

import sys

def main() -> None:
    try:
        from shruggie_indexer.cli.main import main as cli_main
    except ImportError:
        print(
            "The CLI requires the 'click' package.\n"
            "Install it with: pip install shruggie-indexer[cli]",
            file=sys.stderr,
        )
        sys.exit(1)
    cli_main()

if __name__ == "__main__":
    main()
```

This path exists for two reasons: it provides a universal invocation mechanism that works even if the console script wrapper was not installed (e.g., when the package is installed in a non-standard way), and it enables `python -m shruggie_indexer` as a fallback for environments where modifying `PATH` to include the venv's `bin/` directory is inconvenient.

#### Entry point summary

| Invocation | Requires extras | Target function | Console window |
|---|---|---|---|
| `shruggie-indexer` | `cli` | `shruggie_indexer.cli.main:main` | Yes |
| `shruggie-indexer-gui` | `gui` | `shruggie_indexer.gui.app:main` | No (Windows); Yes (Linux/macOS) |
| `python -m shruggie_indexer` | `cli` | `shruggie_indexer.cli.main:main` | Yes |

### 13.4. Standalone Executable Builds

End users do not install `shruggie-indexer` via pip. They download standalone executables from GitHub Releases — pre-built binaries that bundle the Python interpreter, all required dependencies, and the application code into a single distributable artifact. The build tool is [PyInstaller](https://pyinstaller.org/).

#### Build targets

Each release produces two executables per platform: one for the CLI and one for the GUI. The two are built from separate PyInstaller configurations because they have different entry points, dependency sets, and windowing requirements.

| Target | Entry module | PyInstaller mode | Console window | Output filename (Windows) | Output filename (Linux/macOS) |
|---|---|---|---|---|---|
| CLI | `src/shruggie_indexer/cli/main.py` | `--onefile --console` | Yes | `shruggie-indexer.exe` | `shruggie-indexer` |
| GUI | `src/shruggie_indexer/gui/app.py` | `--onefile --windowed` | No | `shruggie-indexer-gui.exe` | `shruggie-indexer-gui` |

**`--onefile` mode.** Both targets use PyInstaller's one-file bundle mode, which produces a single executable that extracts itself to a temporary directory at runtime. This is the simplest distribution format — the user downloads one file and runs it. The alternative `--onedir` mode (which produces a directory of files) is available as a fallback if one-file extraction causes issues on specific platforms, but `--onefile` is the default for releases.

**`--windowed` vs. `--console`.** The GUI target uses `--windowed` (aliased as `--noconsole` and `-w`) to suppress console window creation on Windows. The CLI target uses `--console` (the default) to ensure stdin/stdout/stderr are connected to the terminal. On Linux and macOS, `--windowed` has no behavioral effect — both targets produce standard ELF/Mach-O executables.

#### PyInstaller spec files

The build scripts (§3.5) invoke PyInstaller using `.spec` files rather than raw command-line arguments. Spec files provide reproducible, version-controlled build configurations and allow platform-conditional logic (e.g., including platform-specific hidden imports or data files).

The spec files live at the repository root alongside `pyproject.toml`:

```
shruggie-indexer/
├── shruggie-indexer-cli.spec
├── shruggie-indexer-gui.spec
├── pyproject.toml
└── ...
```

**CLI spec file** (`shruggie-indexer-cli.spec`):

```python
# shruggie-indexer-cli.spec
# PyInstaller spec file for the CLI executable.

import sys
from pathlib import Path

block_cipher = None
src_dir = Path("src")

a = Analysis(
    [str(src_dir / "shruggie_indexer" / "cli" / "main.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[],
    hiddenimports=["shruggie_indexer"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["customtkinter", "tkinter", "_tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="shruggie-indexer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

**GUI spec file** (`shruggie-indexer-gui.spec`):

```python
# shruggie-indexer-gui.spec
# PyInstaller spec file for the GUI executable.

import sys
from pathlib import Path

block_cipher = None
src_dir = Path("src")

a = Analysis(
    [str(src_dir / "shruggie_indexer" / "gui" / "app.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[],
    hiddenimports=["shruggie_indexer", "customtkinter"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["click"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="shruggie-indexer-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # <-- windowed mode for GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

#### Key spec file decisions

**`excludes` lists.** Each spec file excludes packages that the other target requires but the current target does not. The CLI spec excludes `customtkinter`, `tkinter`, and `_tkinter` — the GUI toolkit and its underlying C extension are substantial (several MB) and are never imported by the CLI. The GUI spec excludes `click` — the GUI does not use the CLI's argument parser. These exclusions reduce bundle size and eliminate false-positive hidden-import detection.

**`hiddenimports`.** PyInstaller's static analysis cannot always detect dynamic imports (e.g., the `try: import orjson` pattern in the serializer). The `hiddenimports` list explicitly declares packages that PyInstaller should include even if they are not statically visible. The lists shown above are the minimum set; the implementer SHOULD add entries for any optional packages that the build environment has installed and that should be included in the bundle (e.g., `orjson` if the performance-optimized serializer should be available in the release build). Packages listed in `hiddenimports` that are not installed in the build environment are silently skipped — they do not cause build failures.

**`datas` list.** Both spec files declare an empty `datas` list. The indexer has no bundled data files (no templates, no asset images, no embedded configuration files). If a future enhancement requires bundled data (e.g., a default configuration file or GUI icon), the `datas` list is the correct mechanism for including it.

**UPX compression.** Both spec files enable UPX compression (`upx=True`). UPX reduces executable size by 30–50% with minimal startup time impact. If UPX is not installed in the build environment, PyInstaller silently skips compression — the build succeeds with a larger executable. The build scripts (§3.5) SHOULD log whether UPX was available for the build.

#### Build invocation

The build scripts (`scripts/build.ps1` and `scripts/build.sh`, §3.5) invoke PyInstaller against both spec files:

```bash
# scripts/build.sh (illustrative excerpt)

#!/usr/bin/env bash
set -euo pipefail

echo "Building CLI executable..."
pyinstaller shruggie-indexer-cli.spec --distpath dist/ --workpath build/cli --clean

echo "Building GUI executable..."
pyinstaller shruggie-indexer-gui.spec --distpath dist/ --workpath build/gui --clean

echo "Build complete. Artifacts in dist/"
ls -lh dist/
```

Both executables are output to the `dist/` directory. The `--workpath` argument separates the intermediate build artifacts for each target to avoid collisions. The `--clean` flag ensures a fresh build each time, preventing stale cached analysis from causing silent inclusion/exclusion errors.

The build scripts MUST be runnable from the repository root. They assume the virtual environment is active and that PyInstaller is installed (`pip install pyinstaller`). PyInstaller is not declared as a project dependency — it is a build-time tool installed in the CI pipeline or by the developer running a local build.

#### Exiftool and standalone builds

The standalone executables do NOT bundle `exiftool`. Exiftool is a separate binary with its own installation and licensing requirements (§12.1). Users who want metadata extraction must install exiftool independently and ensure it is on their system `PATH`. The executables degrade gracefully when exiftool is absent (§4.5, §12.5) — all indexing operations except embedded metadata extraction function normally.

This is a deliberate decision, not an oversight. Bundling exiftool would complicate licensing (exiftool is GPL-licensed, while shruggie-indexer is Apache 2.0), increase the bundle size significantly (~25 MB for the Perl distribution), and create a maintenance burden for tracking exiftool version updates. The user's existing exiftool installation is the correct integration point.

### 13.5. Release Artifact Inventory

Each release produces a fixed set of artifacts, uploaded to GitHub Releases. The artifact set is per-platform — each platform's CI runner produces its own set.

| Artifact | Platform | Description |
|---|---|---|
| `shruggie-indexer-{version}-windows-x64.exe` | Windows | CLI standalone executable |
| `shruggie-indexer-gui-{version}-windows-x64.exe` | Windows | GUI standalone executable |
| `shruggie-indexer-{version}-linux-x64` | Linux | CLI standalone executable |
| `shruggie-indexer-gui-{version}-linux-x64` | Linux | GUI standalone executable |
| `shruggie-indexer-{version}-macos-x64` | macOS (Intel) | CLI standalone executable |
| `shruggie-indexer-gui-{version}-macos-x64` | macOS (Intel) | GUI standalone executable |
| `shruggie-indexer-{version}-macos-arm64` | macOS (Apple Silicon) | CLI standalone executable |
| `shruggie-indexer-gui-{version}-macos-arm64` | macOS (Apple Silicon) | GUI standalone executable |

The `{version}` placeholder is the version string from `_version.py` (e.g., `0.1.0`). Filenames use hyphens as separators and include the platform and architecture to disambiguate downloads on the releases page.

#### macOS dual-architecture builds

macOS requires two architecture variants: `x64` (Intel) and `arm64` (Apple Silicon). PyInstaller produces native executables for the architecture of the host Python interpreter — a build on an Intel Mac produces an x64 binary, a build on an Apple Silicon Mac produces an arm64 binary. Cross-compilation (building arm64 on x64 or vice versa) is not reliably supported by PyInstaller.

The CI pipeline (§13.5.1) handles this by running macOS builds on two separate runner types, one for each architecture. If GitHub Actions does not provide both runner types, the alternative is to build a universal binary using `lipo` after producing both single-architecture builds — but this approach is fragile and should only be used if separate runners are unavailable.

> **Note:** ARM64 macOS builds are a release-time consideration, not an MVP blocker. The v0.1.0 release MAY ship with x64-only macOS builds if arm64 CI runners are not available, with arm64 support added in a subsequent release. The tool runs correctly on Apple Silicon via Rosetta 2 in the interim.

#### Artifacts NOT included in releases

The release does NOT include:

- **Source distributions (`.tar.gz`, `.whl`).** The project is not published to PyPI (§2.1). Source installs are done via `pip install -e .` from a git clone, not from a distribution archive.
- **Checksum files.** GitHub Releases provides its own SHA-256 checksums for uploaded artifacts. Separate `.sha256` sidecar files are redundant.
- **Platform-specific installers (`.msi`, `.dmg`, `.deb`).** Standalone executables are the distribution format. Platform-specific installers are a potential post-MVP enhancement for improved user experience (e.g., Start Menu integration on Windows, Applications folder placement on macOS), but they add significant build complexity and are not required for the MVP.

### 13.5.1. GitHub Actions Release Pipeline

The release pipeline is defined in `.github/workflows/release.yml` (§3.1). It triggers on version tag pushes and produces the full artifact inventory described above.

#### Trigger

```yaml
on:
  push:
    tags:
      - "v*"
```

The pipeline triggers when a tag matching `v*` (e.g., `v0.1.0`, `v0.2.0-rc1`) is pushed to the repository. It does not trigger on branch pushes or pull requests — those are handled by a separate CI workflow (not specified in this document, as it is not a packaging concern).

#### Matrix strategy

The pipeline uses a matrix strategy to build across platforms:

```yaml
strategy:
  matrix:
    include:
      - os: windows-latest
        platform_suffix: windows-x64
      - os: ubuntu-latest
        platform_suffix: linux-x64
      - os: macos-13
        platform_suffix: macos-x64
      - os: macos-latest
        platform_suffix: macos-arm64
```

Each matrix entry runs on a GitHub Actions runner for the target platform. The `platform_suffix` value is interpolated into artifact filenames.

#### Pipeline stages

The pipeline executes the following stages on each matrix runner:

**Stage 1 — Checkout and environment setup.** Checks out the repository at the tag commit. Installs Python 3.12 using `actions/setup-python`. Creates a virtual environment and installs the package with all extras: `pip install -e ".[cli,gui,perf]"`. Installs PyInstaller: `pip install pyinstaller`.

**Stage 2 — Test.** Runs the test suite (`pytest tests/ -m "not requires_exiftool"`) to verify that the codebase is healthy before building release artifacts. The `requires_exiftool` marker is excluded because exiftool may not be installed on all CI runners. If tests fail, the pipeline aborts — no artifacts are produced.

**Stage 3 — Build.** Invokes the build scripts (`scripts/build.sh` or `scripts/build.ps1`) to produce both the CLI and GUI executables via PyInstaller. The build scripts output to `dist/`.

**Stage 4 — Rename artifacts.** Renames the executables from their generic names (`shruggie-indexer`, `shruggie-indexer-gui`) to the versioned, platform-tagged names defined in the artifact inventory (e.g., `shruggie-indexer-0.1.0-linux-x64`). The version string is extracted from the git tag.

**Stage 5 — Upload.** Uploads the renamed artifacts using `actions/upload-artifact` for cross-job sharing.

**Stage 6 — Release (runs once, after all matrix jobs complete).** A separate job that runs after all matrix builds succeed. It downloads all uploaded artifacts and creates a GitHub Release associated with the triggering tag. The release body includes a changelog summary (manually authored or extracted from a `CHANGELOG.md` file if present) and the list of downloadable artifacts.

#### Pipeline design principles

**Build and test on the target platform.** Each platform's artifacts are built on a runner matching that platform. Cross-compilation is not used. This ensures that PyInstaller's dependency detection, binary bundling, and executable format are all native to the target.

**Fail fast.** If any matrix job fails (test failure, build failure, upload failure), the release job does not execute. A partial release — with artifacts for some platforms but not others — is never created.

**Reproducibility.** The pipeline pins the Python version (`3.12`), uses `pip install` with the version constraints from `pyproject.toml`, and builds from the exact commit referenced by the tag. Two runs of the pipeline on the same tag SHOULD produce functionally identical artifacts (byte-identical output is not guaranteed due to PyInstaller's use of timestamps and random identifiers in the bootloader).

### 13.6. Version Management

The version string is defined in a single location and consumed by all components that need it.

#### Single source of truth

The version is defined in `src/shruggie_indexer/_version.py`:

```python
# src/shruggie_indexer/_version.py
__version__ = "0.1.0"
```

This is the only place the version string is written. All other version consumers read from this file:

| Consumer | Mechanism |
|---|---|
| `pyproject.toml` | `[tool.hatch.version]` reads `__version__` from the file path `src/shruggie_indexer/_version.py`. Hatchling parses the file and extracts the version string at build time. |
| `__init__.py` | `from shruggie_indexer._version import __version__` makes the version available as `shruggie_indexer.__version__` for library consumers. |
| CLI `--version` flag | `@click.version_option(version=__version__)` reads the imported `__version__` attribute. |
| GUI window title | The GUI's `__init__` method formats the window title as `f"Shruggie Indexer v{__version__}"` using the imported attribute. |
| PyInstaller artifacts | The build scripts extract the version from `_version.py` (via a shell `grep`/`sed` or Python one-liner) to construct versioned artifact filenames. |

#### Versioning scheme

The project uses semantic versioning (`MAJOR.MINOR.PATCH`):

- **MAJOR** — Incremented for breaking changes to the public API (§9.1) or the output schema (§5). The output schema and the public API are the two stability boundaries.
- **MINOR** — Incremented for backward-compatible feature additions (new CLI flags, new configuration options, new metadata types, schema additions that do not break existing consumers).
- **PATCH** — Incremented for bug fixes, documentation corrections, and internal refactoring that does not change observable behavior.

Pre-release versions use the format `MAJOR.MINOR.PATCH-rcN` (e.g., `0.1.0-rc1`) for release candidates. Pre-release versions are valid PEP 440 versions when expressed as `0.1.0rc1` (no hyphen) — the `_version.py` file uses PEP 440 format, and the git tag uses the hyphenated form for readability.

For the MVP release cycle: the project starts at `0.1.0`. During the `0.x.y` series, minor version bumps MAY include breaking changes to the public API (§9.1). Once the project reaches `1.0.0`, semantic versioning guarantees apply in full.

#### Version bump procedure

Version changes are a manual, deliberate action — not automated by CI. The procedure for releasing a new version is:

1. Update `__version__` in `src/shruggie_indexer/_version.py` to the new version string.
2. Commit the change with a message following the pattern: `release: v{version}`.
3. Create a git tag: `git tag v{version}`.
4. Push the commit and tag: `git push && git push --tags`.
5. The GitHub Actions release pipeline (§13.5.1) triggers on the tag push and produces the release artifacts.

The version bump is a single-file change. There is no need to update `pyproject.toml`, `__init__.py`, or any other file — they all derive the version from `_version.py`. This eliminates the class of bugs where version strings fall out of sync across multiple files.

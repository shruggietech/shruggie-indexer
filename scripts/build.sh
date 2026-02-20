#!/usr/bin/env bash
# -------------------------------------------------------------------
# build.sh — PyInstaller build script for shruggie-indexer
# -------------------------------------------------------------------
#
# SYNOPSIS
#   ./scripts/build.sh [OPTIONS] [TARGET]
#
# DESCRIPTION
#   Invokes PyInstaller against both the CLI and GUI spec files to produce
#   standalone executables in the dist/ directory. Each target is built
#   with a separate workpath to avoid collisions.
#
#   The script checks for UPX availability and logs the result. If UPX is
#   not installed, PyInstaller silently skips compression — the build
#   succeeds with larger executables.
#
#   This script MUST be invoked from the repository root directory.
#   The virtual environment MUST be active and PyInstaller MUST be installed.
#
# POSITIONAL ARGUMENTS
#   TARGET                Build target: cli, gui, or all (default: all).
#
# OPTIONS
#   -h, --help            Display this help text and exit.
#   -c, --clean           Remove existing dist/ and build/ before building.
#
# EXAMPLES
#   ./scripts/build.sh
#       Builds both CLI and GUI executables.
#
#   ./scripts/build.sh cli
#       Builds only the CLI executable.
#
#   ./scripts/build.sh --clean
#       Cleans build artifacts and builds both executables.
#
# REQUIRES
#   Python >= 3.12, PyInstaller, virtual environment active
#
# PROJECT
#   shruggie-indexer
#
# LICENSE
#   Apache 2.0
# -------------------------------------------------------------------

set -euo pipefail

# -------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------

readonly CLI_SPEC_FILE="shruggie-indexer-cli.spec"
readonly GUI_SPEC_FILE="shruggie-indexer-gui.spec"
readonly DIST_DIR="dist"
readonly BUILD_DIR="build"

# -------------------------------------------------------------------
# Defaults
# -------------------------------------------------------------------

TARGET="all"
CLEAN=false

# -------------------------------------------------------------------
# Functions
# -------------------------------------------------------------------

usage() {
    sed -n '/^# SYNOPSIS/,/^# ---/{ /^# ---/d; s/^# \{0,3\}//; p }' "$0"
    exit 0
}

log_info() {
    printf "\033[36m[build]\033[0m %s\n" "$1"
}

log_success() {
    printf "\033[32m[build]\033[0m %s\n" "$1"
}

log_warn() {
    printf "\033[33m[build]\033[0m %s\n" "$1"
}

log_error() {
    printf "\033[31m[build]\033[0m ERROR: %s\n" "$1" >&2
    exit 1
}

check_prerequisites() {
    # Check that we're in the repository root
    if [[ ! -f "pyproject.toml" ]]; then
        log_error "This script must be invoked from the repository root (pyproject.toml not found)."
    fi

    # Check that the virtual environment is active
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        log_error "Virtual environment is not active. Run: source .venv/bin/activate"
    fi

    # Check that PyInstaller is available
    if ! command -v pyinstaller &>/dev/null; then
        log_error "PyInstaller is not installed. Run: pip install pyinstaller"
    fi
    log_info "PyInstaller found: $(command -v pyinstaller)"

    # Check that spec files exist
    if [[ ! -f "$CLI_SPEC_FILE" ]]; then
        log_error "CLI spec file not found: $CLI_SPEC_FILE"
    fi
    if [[ ! -f "$GUI_SPEC_FILE" ]]; then
        log_error "GUI spec file not found: $GUI_SPEC_FILE"
    fi
}

check_upx() {
    if command -v upx &>/dev/null; then
        local upx_version
        upx_version=$(upx --version 2>&1 | head -n1)
        log_success "UPX found: $upx_version"
        log_success "Executables will be UPX-compressed."
    else
        log_warn "UPX not found — executables will not be compressed."
        log_warn "Install UPX for 30-50% smaller executables: https://upx.github.io/"
    fi
}

build_target() {
    local spec_file="$1"
    local label="$2"
    local work_path="$3"

    echo ""
    log_info "Building $label executable..."
    pyinstaller "$spec_file" --distpath "$DIST_DIR" --workpath "$work_path" --clean --noconfirm
    log_success "$label build completed."
}

verify_output() {
    local label="$1"
    local exe_name="$2"

    local output_path="$DIST_DIR/$exe_name"
    if [[ -f "$output_path" ]]; then
        local size_human
        size_human=$(du -h "$output_path" | cut -f1)
        log_success "$label executable verified: $output_path ($size_human)"
    else
        log_error "$label executable not found at expected path: $output_path"
    fi
}

# -------------------------------------------------------------------
# Argument parsing
# -------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            ;;
        -c|--clean)
            CLEAN=true
            shift
            ;;
        cli|gui|all)
            TARGET="$1"
            shift
            ;;
        *)
            log_error "Unknown argument: $1. Use --help for usage."
            ;;
    esac
done

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

echo ""
echo "========================================"
echo "  shruggie-indexer  —  build.sh"
echo "========================================"
echo ""

# 1. Validate prerequisites
check_prerequisites

# 2. Check UPX availability
check_upx

# 3. Clean if requested
if [[ "$CLEAN" == true ]]; then
    log_info "Cleaning previous build artifacts..."
    rm -rf "$DIST_DIR" "$BUILD_DIR"
    log_success "Clean complete."
fi

# 4. Build targets
if [[ "$TARGET" == "all" || "$TARGET" == "cli" ]]; then
    build_target "$CLI_SPEC_FILE" "CLI" "$BUILD_DIR/cli"
    verify_output "CLI" "shruggie-indexer"
fi

if [[ "$TARGET" == "all" || "$TARGET" == "gui" ]]; then
    build_target "$GUI_SPEC_FILE" "GUI" "$BUILD_DIR/gui"
    verify_output "GUI" "shruggie-indexer-gui"
fi

# 5. Summary
echo ""
log_success "Build complete. Artifacts in $DIST_DIR/:"
ls -lh "$DIST_DIR/" 2>/dev/null || log_warn "No artifacts found in $DIST_DIR/"
echo ""

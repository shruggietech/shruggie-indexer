#!/usr/bin/env bash
# -------------------------------------------------------------------
# venv-setup.sh — Virtual environment setup for shruggie-indexer
# -------------------------------------------------------------------
#
# SYNOPSIS
#   ./scripts/venv-setup.sh [OPTIONS]
#
# DESCRIPTION
#   Creates a Python virtual environment in the repository root (.venv/),
#   installs the shruggie-indexer package in editable mode with all
#   development and GUI dependencies, and verifies that the installation
#   succeeded.
#
#   The script is idempotent — it is safe to re-run at any time. If the
#   virtual environment already exists, it will be reused (not recreated)
#   unless the --force flag is specified.
#
#   This script MUST be invoked from the repository root directory.
#
# OPTIONS
#   -h, --help          Display this help text and exit.
#   -f, --force         Remove existing .venv/ and recreate from scratch.
#   -p, --python PATH   Use a specific Python interpreter.
#   -e, --extras LIST   Comma-separated pip extras (default: "dev,gui").
#
# EXAMPLES
#   ./scripts/venv-setup.sh
#       Creates or reuses .venv/ with [dev,gui] extras.
#
#   ./scripts/venv-setup.sh --force
#       Removes any existing .venv/ and rebuilds.
#
#   ./scripts/venv-setup.sh --extras "dev"
#       Installs with only the [dev] extra (no GUI dependencies).
#
#   ./scripts/venv-setup.sh --python /usr/bin/python3.12
#       Uses a specific Python interpreter.
#
# REQUIRES
#   Python >= 3.12
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

readonly MIN_PYTHON_MAJOR=3
readonly MIN_PYTHON_MINOR=12
readonly VENV_DIR=".venv"

# -------------------------------------------------------------------
# Defaults
# -------------------------------------------------------------------

PYTHON_PATH=""
FORCE=false
EXTRAS="dev,gui"

# -------------------------------------------------------------------
# Functions
# -------------------------------------------------------------------

usage() {
    sed -n '/^# SYNOPSIS/,/^# ---/{ /^# ---/d; s/^# \{0,3\}//; p }' "$0"
    exit 0
}

log_info() {
    printf "\033[36m[venv-setup]\033[0m %s\n" "$1"
}

log_success() {
    printf "\033[32m[venv-setup]\033[0m %s\n" "$1"
}

log_warn() {
    printf "\033[33m[venv-setup]\033[0m %s\n" "$1"
}

log_error() {
    printf "\033[31m[venv-setup]\033[0m ERROR: %s\n" "$1" >&2
    exit 1
}

find_python() {
    if [[ -n "$PYTHON_PATH" ]]; then
        if [[ ! -x "$PYTHON_PATH" ]]; then
            log_error "Specified Python path does not exist or is not executable: $PYTHON_PATH"
        fi
        echo "$PYTHON_PATH"
        return
    fi

    for candidate in python3 python; do
        if command -v "$candidate" &>/dev/null; then
            echo "$candidate"
            return
        fi
    done

    log_error "No Python interpreter found on PATH. Install Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} and ensure it is on PATH."
}

check_python_version() {
    local interpreter="$1"
    local version_output
    version_output=$("$interpreter" --version 2>&1)

    if [[ "$version_output" =~ ([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
        local major="${BASH_REMATCH[1]}"
        local minor="${BASH_REMATCH[2]}"
        local patch="${BASH_REMATCH[3]}"

        if (( major < MIN_PYTHON_MAJOR || (major == MIN_PYTHON_MAJOR && minor < MIN_PYTHON_MINOR) )); then
            log_error "Python ${major}.${minor}.${patch} found, but >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} is required."
        fi

        log_info "Using Python ${major}.${minor}.${patch} at: $(command -v "$interpreter")"
    else
        log_error "Could not determine Python version from: $version_output"
    fi
}

create_venv() {
    local interpreter="$1"

    if [[ "$FORCE" == true ]] && [[ -d "$VENV_DIR" ]]; then
        log_warn "Removing existing virtual environment..."
        rm -rf "$VENV_DIR"
    fi

    if [[ -d "$VENV_DIR" ]]; then
        log_info "Virtual environment already exists at ./${VENV_DIR} — reusing."
    else
        log_info "Creating virtual environment at ./${VENV_DIR} ..."
        "$interpreter" -m venv "$VENV_DIR"
    fi
}

get_venv_python() {
    local candidate="${VENV_DIR}/bin/python"
    if [[ -x "$candidate" ]]; then
        echo "$candidate"
        return
    fi

    # Fallback for Windows Git Bash or similar
    candidate="${VENV_DIR}/Scripts/python.exe"
    if [[ -x "$candidate" ]]; then
        echo "$candidate"
        return
    fi

    log_error "Could not locate Python interpreter inside ${VENV_DIR}."
}

install_package() {
    local venv_python="$1"

    log_info "Upgrading pip..."
    "$venv_python" -m pip install --upgrade pip --quiet || log_warn "pip upgrade failed (non-fatal). Continuing."

    log_info "Installing shruggie-indexer in editable mode with [${EXTRAS}] extras..."
    "$venv_python" -m pip install -e ".[${EXTRAS}]"
}

verify_installation() {
    local venv_python="$1"

    log_info "Verifying installation..."
    "$venv_python" -c "from shruggie_indexer._version import __version__; print(f'shruggie-indexer v{__version__}')"

    log_success "Installation verified successfully."
}

# -------------------------------------------------------------------
# Argument parsing
# -------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -p|--python)
            if [[ -z "${2:-}" ]]; then
                log_error "--python requires a path argument."
            fi
            PYTHON_PATH="$2"
            shift 2
            ;;
        -e|--extras)
            if [[ -z "${2:-}" ]]; then
                log_error "--extras requires an argument."
            fi
            EXTRAS="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1. Use --help for usage."
            ;;
    esac
done

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

echo ""
echo "========================================"
echo "  shruggie-indexer  —  venv-setup.sh    "
echo "========================================"
echo ""

# 1. Find and validate the Python interpreter
python_bin=$(find_python)
check_python_version "$python_bin"

# 2. Create or reuse the virtual environment
create_venv "$python_bin"

# 3. Locate the venv Python
venv_python=$(get_venv_python)

# 4. Install the package
install_package "$venv_python"

# 5. Verify
verify_installation "$venv_python"

echo ""
log_success "Done. Activate the environment with:"
echo "    source .venv/bin/activate"
echo ""

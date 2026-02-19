#!/usr/bin/env bash
# -------------------------------------------------------------------
# test.sh — Test runner for shruggie-indexer
# -------------------------------------------------------------------
#
# SYNOPSIS
#   ./scripts/test.sh [OPTIONS] [CATEGORY]
#
# DESCRIPTION
#   Activates the project virtual environment and runs pytest with
#   configurable scope, markers, and coverage options. Supports both
#   named test categories (unit, integration, conformance, platform)
#   and automatic discovery of available test directories.
#
#   When invoked without arguments, the script runs the full test suite.
#   When a category name is provided, only that category's tests are
#   executed.
#
#   This script MUST be invoked from the repository root directory.
#
# POSITIONAL ARGUMENTS
#   CATEGORY              Test category to run: unit, integration,
#                         conformance, platform, all (default: all).
#                         Multiple categories can be comma-separated
#                         (e.g., "unit,conformance").
#
# OPTIONS
#   -h, --help            Display this help text and exit.
#   -d, --discover        List available test categories and exit.
#   -c, --coverage        Enable pytest-cov coverage reporting.
#   -m, --marker EXPR     Pytest marker expression for -m flag
#                         (e.g., "not slow", "not requires_exiftool").
#   -v, --verbose         Enable verbose pytest output.
#   -a, --args "ARGS"     Additional arguments passed to pytest verbatim.
#                         Quote the entire string if it contains spaces.
#
# EXAMPLES
#   ./scripts/test.sh
#       Runs the full test suite.
#
#   ./scripts/test.sh unit
#       Runs only unit tests.
#
#   ./scripts/test.sh "unit,conformance"
#       Runs unit and conformance tests.
#
#   ./scripts/test.sh --discover
#       Lists available test categories and their test counts.
#
#   ./scripts/test.sh integration --marker "not requires_exiftool"
#       Runs integration tests excluding those that require exiftool.
#
#   ./scripts/test.sh --coverage
#       Runs all tests with coverage reporting.
#
#   ./scripts/test.sh unit --verbose --args "--tb=short -x"
#       Runs unit tests verbosely, with short tracebacks and fail-fast.
#
# REQUIRES
#   Virtual environment created by venv-setup.sh.
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

readonly VENV_DIR=".venv"
readonly TESTS_DIR="tests"
readonly VALID_CATEGORIES=("unit" "integration" "conformance" "platform")

# -------------------------------------------------------------------
# Defaults
# -------------------------------------------------------------------

CATEGORY="all"
DISCOVER=false
COVERAGE=false
MARKER=""
VERBOSE=false
EXTRA_ARGS=""

# -------------------------------------------------------------------
# Functions
# -------------------------------------------------------------------

usage() {
    sed -n '/^# SYNOPSIS/,/^# ---/{ /^# ---/d; s/^# \{0,3\}//; p }' "$0"
    exit 0
}

log_info() {
    printf "\033[36m[test]\033[0m %s\n" "$1"
}

log_success() {
    printf "\033[32m[test]\033[0m %s\n" "$1"
}

log_warn() {
    printf "\033[33m[test]\033[0m %s\n" "$1"
}

log_error() {
    printf "\033[31m[test]\033[0m ERROR: %s\n" "$1" >&2
    exit 1
}

get_venv_python() {
    local candidate="${VENV_DIR}/bin/python"
    if [[ -x "$candidate" ]]; then
        echo "$candidate"
        return
    fi

    # Fallback for Windows Git Bash
    candidate="${VENV_DIR}/Scripts/python.exe"
    if [[ -x "$candidate" ]]; then
        echo "$candidate"
        return
    fi

    log_error "Virtual environment not found at ./${VENV_DIR}. Run './scripts/venv-setup.sh' first."
}

discover_categories() {
    echo ""
    log_info "Available test categories:"
    echo ""

    local found=false

    for dir in "${TESTS_DIR}"/*/; do
        [[ -d "$dir" ]] || continue
        local dir_name
        dir_name=$(basename "$dir")
        local count
        count=$(find "$dir" -maxdepth 1 -name "test_*.py" -type f 2>/dev/null | wc -l | tr -d ' ')

        if (( count > 0 )); then
            found=true
            local file_label="files"
            (( count == 1 )) && file_label="file"
            printf "  %-15s %d test %s\n" "$dir_name" "$count" "$file_label"
        fi
    done

    if [[ "$found" == false ]]; then
        echo "  (none found — no test_*.py files in ${TESTS_DIR}/*/)"
        echo ""
        echo "  Expected category directories:"
        for cat in "${VALID_CATEGORIES[@]}"; do
            echo "    tests/${cat}/"
        done
    fi

    echo ""

    # Show categories with no tests yet
    local missing=()
    for cat in "${VALID_CATEGORIES[@]}"; do
        local cat_dir="${TESTS_DIR}/${cat}"
        if [[ ! -d "$cat_dir" ]] || (( $(find "$cat_dir" -maxdepth 1 -name "test_*.py" -type f 2>/dev/null | wc -l) == 0 )); then
            missing+=("$cat")
        fi
    done

    if (( ${#missing[@]} > 0 )); then
        echo "  Categories with no tests yet:"
        for cat in "${missing[@]}"; do
            echo "    ${cat}"
        done
        echo ""
    fi
}

is_valid_category() {
    local needle="$1"
    for cat in "${VALID_CATEGORIES[@]}"; do
        [[ "$cat" == "$needle" ]] && return 0
    done
    return 1
}

resolve_categories() {
    local input="$1"

    if [[ "$input" == "all" ]]; then
        echo "$TESTS_DIR"
        return
    fi

    local IFS=","
    local paths=()

    for cat in $input; do
        cat=$(echo "$cat" | tr -d ' ' | tr '[:upper:]' '[:lower:]')

        if ! is_valid_category "$cat"; then
            log_error "Unknown test category: '${cat}'. Valid categories: ${VALID_CATEGORIES[*]}, all"
        fi

        local cat_path="${TESTS_DIR}/${cat}"
        if [[ ! -d "$cat_path" ]]; then
            log_warn "Test category directory does not exist: ${cat_path} (skipping)"
            continue
        fi

        paths+=("$cat_path")
    done

    if (( ${#paths[@]} == 0 )); then
        log_error "No valid test directories found for category: '${input}'"
    fi

    echo "${paths[*]}"
}

# -------------------------------------------------------------------
# Argument parsing
# -------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            ;;
        -d|--discover)
            DISCOVER=true
            shift
            ;;
        -c|--coverage)
            COVERAGE=true
            shift
            ;;
        -m|--marker)
            if [[ -z "${2:-}" ]]; then
                log_error "--marker requires an expression argument."
            fi
            MARKER="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -a|--args)
            if [[ -z "${2:-}" ]]; then
                log_error "--args requires an argument string."
            fi
            EXTRA_ARGS="$2"
            shift 2
            ;;
        -*)
            log_error "Unknown option: $1. Use --help for usage."
            ;;
        *)
            CATEGORY="$1"
            shift
            ;;
    esac
done

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

echo ""
echo "========================================"
echo "  shruggie-indexer  —  test.sh          "
echo "========================================"
echo ""

# Handle discovery mode
if [[ "$DISCOVER" == true ]]; then
    discover_categories
    exit 0
fi

# 1. Locate virtual environment Python
venv_python=$(get_venv_python)

# 2. Resolve test category to directories
test_paths=$(resolve_categories "$CATEGORY")

# 3. Build pytest arguments
pytest_args=()

# shellcheck disable=SC2206
pytest_args+=($test_paths)

if [[ "$VERBOSE" == true ]]; then
    pytest_args+=("-v")
fi

if [[ "$COVERAGE" == true ]]; then
    pytest_args+=("--cov=shruggie_indexer" "--cov-report=term-missing")
fi

if [[ -n "$MARKER" ]]; then
    pytest_args+=("-m" "$MARKER")
fi

if [[ -n "$EXTRA_ARGS" ]]; then
    # shellcheck disable=SC2206
    pytest_args+=($EXTRA_ARGS)
fi

# 4. Display what we're running
if [[ "$CATEGORY" == "all" ]]; then
    category_label="all categories"
else
    category_label="$CATEGORY"
fi

log_info "Running tests: ${category_label}"

if [[ -n "$MARKER" ]]; then
    log_info "Marker filter: ${MARKER}"
fi

if [[ "$COVERAGE" == true ]]; then
    log_info "Coverage reporting: enabled"
fi

echo -e "\033[90m[test] Command: ${venv_python} -m pytest ${pytest_args[*]}\033[0m"
echo ""

# 5. Execute pytest
set +e
"$venv_python" -m pytest "${pytest_args[@]}"
exit_code=$?
set -e

# 6. Report result
echo ""
if (( exit_code == 0 )); then
    log_success "All tests passed."
elif (( exit_code == 5 )); then
    log_warn "No tests were collected."
else
    log_error "Tests failed with exit code: ${exit_code}"
fi

exit "$exit_code"

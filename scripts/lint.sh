#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-src}"

case "$TARGET" in
  src|tests|all) ;;
  *)
    echo "Usage: ./scripts/lint.sh [src|tests|all]" >&2
    exit 1
    ;;
esac

VENV_PY=".venv/bin/python"
if [[ ! -x "$VENV_PY" && -x ".venv/Scripts/python.exe" ]]; then
  VENV_PY=".venv/Scripts/python.exe"
fi

if [[ ! -x "$VENV_PY" ]]; then
  echo "Virtual environment not found. Run scripts/venv-setup first." >&2
  exit 1
fi

run_ruff() {
  local path="$1"
  echo "[lint] ruff check ${path}/"
  "$VENV_PY" -m ruff check "${path}/"
}

if [[ "$TARGET" == "all" ]]; then
  run_ruff src
  run_ruff tests
else
  run_ruff "$TARGET"
fi

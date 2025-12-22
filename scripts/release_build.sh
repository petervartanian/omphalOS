#!/usr/bin/env bash
set -euo pipefail

# Allow running from a fresh clone without requiring an editable install.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$REPO_ROOT/src:${PYTHONPATH:-}"

RUN_DIR="$1"; OUT="$2"; python -m omphalos release build --run-dir "$RUN_DIR" --out "$OUT"

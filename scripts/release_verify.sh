#!/usr/bin/env bash
set -euo pipefail

# Allow running from a fresh clone without requiring an editable install.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$REPO_ROOT/src:${PYTHONPATH:-}"

python -m omphalos release verify --bundle "$1"

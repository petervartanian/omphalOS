#!/usr/bin/env bash
set -euo pipefail

# Allow running from a fresh clone without requiring an editable install.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$REPO_ROOT/src:${PYTHONPATH:-}"

# Runs the maximal rule pack demo (synthetic) and prints the run dir.

python -m omphalos run --config config/runs/maximal_demo.yaml

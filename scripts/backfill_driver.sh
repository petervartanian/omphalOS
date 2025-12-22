#!/usr/bin/env bash
set -euo pipefail

# Allow running from a fresh clone without requiring an editable install.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$REPO_ROOT/src:${PYTHONPATH:-}"

for i in {1..3}; do python -m omphalos run --config config/runs/backfill_demo.yaml; done

#!/usr/bin/env bash
set -euo pipefail

python -m omphalos contracts validate --schema run_manifest.schema.json --json "$1"

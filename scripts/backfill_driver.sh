#!/usr/bin/env bash
set -euo pipefail

for i in {1..3}; do python -m omphalos run --config config/runs/backfill_demo.yaml; done

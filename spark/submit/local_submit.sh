#!/usr/bin/env bash
set -euo pipefail

# Convenience wrapper for local Spark testing.
#
# Example:
#   bash spark/submit/local_submit.sh artifacts/runs/run-demo

RUN_DIR="${1:-artifacts/runs/run-demo}"

spark-submit spark/jobs/ingest_synthetic.py \
  --trade-feed examples/synthetic/trade_feed.csv \
  --registry examples/synthetic/registry.csv \
  --out-run-dir "$RUN_DIR"

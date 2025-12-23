#!/usr/bin/env bash
set -euo pipefail

RUN_DIR="$1"; OUT="$2"; python -m omphalos release build --run-dir "$RUN_DIR" --out "$OUT"

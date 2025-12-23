#!/usr/bin/env bash
set -euo pipefail

python -m omphalos publishability scan --path . --out artifacts/reports/publishability.json

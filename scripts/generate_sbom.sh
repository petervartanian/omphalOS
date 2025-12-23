#!/usr/bin/env bash
set -euo pipefail

python -m omphalos sbom --out artifacts/reports/sbom.json

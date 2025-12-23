#!/usr/bin/env bash
set -euo pipefail

python -m omphalos release verify --bundle "$1"

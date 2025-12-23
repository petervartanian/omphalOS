#!/usr/bin/env bash
set -euo pipefail

python -m omphalos certify --run-a "$1" --run-b "$2"

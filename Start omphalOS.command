#!/bin/zsh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo 'Install omphalOS first with: poetry install'
  read '?Press Enter to close.'
  exit 1
fi
exec .venv/bin/python -m omphalos --workspace ./workspace serve --open

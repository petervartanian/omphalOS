#!/bin/zsh
set -eu
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m omphalos --workspace ./workspace serve --open
fi
if command -v poetry >/dev/null 2>&1; then
  exec poetry run python -m omphalos --workspace ./workspace serve --open
fi
echo 'Install omphalOS first with: poetry install'
read '?Press Enter to close.'
exit 1

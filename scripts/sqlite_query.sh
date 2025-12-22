#!/usr/bin/env bash
set -euo pipefail

# Run a SQL file against a run's SQLite warehouse.
#
# Usage:
#   bash scripts/sqlite_query.sh artifacts/runs/<run_id> sql/audit/match_rate.sql

RUN_DIR="${1:?run_dir required}"
SQL_FILE="${2:?sql_file required}"

DB="$RUN_DIR/warehouse/warehouse.sqlite"
if [[ ! -f "$DB" ]]; then
  echo "Missing warehouse: $DB" >&2
  exit 2
fi

sqlite3 -header -column "$DB" < "$SQL_FILE"

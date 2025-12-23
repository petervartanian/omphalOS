# Operator runbook

## Local run

python -m omphalos run --config configs/demo.yaml

The run writes:
artifacts/runs/<run_id>/

## Verification

python -m omphalos verify --run-dir artifacts/runs/<run_id>

Verification recomputes hashes and checks that the manifest declares the observed artifact set.

## Release bundle

python -m omphalos release build --run-dir artifacts/runs/<run_id>
python -m omphalos release verify --bundle artifacts/releases/<bundle_id>.tar.zst

## Failure modes

Ingest failures
- invalid CSV, missing columns, encoding errors
- connector misconfiguration

Normalization failures
- schema violations
- unparseable dates or numeric fields

Warehouse failures
- missing tables or drifted schema
- transform compilation errors

Export failures
- query library references missing objects
- parameter sets not satisfiable

## Standard checks

- row_counts.sql
- missing_required_fields.sql
- duplicate_shipments.sql
- match_rate_overall.sql

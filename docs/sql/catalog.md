# SQL catalog

The sql/ directory is a curated query library. Queries are organized by use:

briefing/
  stable outputs intended for recurring briefing products

review/
  drill-down queries used during adjudication

audit/
  integrity, drift, and quality checks

investigations/
  exploratory queries for anomaly hunting and pattern discovery

playbooks/
  multi-step scripts that can be executed as a single casework bundle

## Manifests

sql/manifests/*.yaml define query sets and default parameters.

A catalog runner should record, per query execution:
- query text fingerprint
- parameter values
- output table fingerprint
- execution metadata (engine, runtime, row counts)

These records are written into the run directory to preserve reproducibility.

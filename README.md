# omphalOS

omphalOS is a deterministic analysis workbench for trade and technology-transfer oversight. It builds a run directory that contains: inputs, normalized datasets, a warehouse, scored entities, review tables, exports, and a machine-checkable integrity index.

The repository ships a reference implementation with synthetic data. It is structured to support the same workflow across workstation runs, scheduled runs, and deployed runs, while preserving a stable artifact contract.

## Scope

omphalOS covers four tasks:

1. Ingest: load a trade feed and a registry (lists, watchlists, or reference entities).
2. Normalize: canonicalize fields, enforce schemas, and derive deterministic features.
3. Score and assemble: match trade records to registry entities, compute entity exposure summaries, and write review-ready tables.
4. Package: fingerprint all outputs, emit a run manifest, and (optionally) assemble a release bundle for distribution.

## Run directory contract

A run is an immutable directory rooted at:

artifacts/runs/<run_id>/

The directory is treated as write-once: outputs are written under stable paths, then indexed and fingerprinted. The manifest contains:

- metadata: tool version, run_id, timestamps, environment identifiers
- declared artifacts: relative paths, sizes, sha256
- merkle root of the artifact set
- structured reports: dataset validation, matching statistics, scoring summaries
- release metadata when a bundle is assembled

This contract is the unit of comparison and verification.

## Data model

The reference warehouse is a SQLite database written to:

artifacts/runs/<run_id>/warehouse/warehouse.sqlite

Base tables:

- trade_feed: one row per shipment
- registry: one row per entity
- entity_matches: one row per shipment-entity candidate match
- entity_scores: one row per entity summary

The maximal pipeline extends trade_feed with exporter_country and importer_country while preserving the legacy country field.

## Warehouse and SQL surfaces

The repository contains two SQL surfaces:

1. Warehouse transforms: a dbt project under warehouse/ that defines staging, intermediate, and mart models. It is written to run against SQLite, DuckDB, or Postgres using profiles shipped under warehouse/profiles/.
2. Analyst catalog: a curated query library under sql/ organized by briefing, review, audit, and investigations. Catalog execution records the query text, parameters, and output fingerprints into the run directory.

Both surfaces are designed to be executable and to emit artifacts that the manifest can index.

## Orchestration and deployment

The repository includes:

- scripts/ as the canonical operator interface (run, verify, certify, backfill, release-build, release-verify)
- orchestration/airflow/ with DAGs that call the same runner interfaces
- infra/k8s with base manifests and overlays for scheduled jobs
- infra/terraform with modules and cloud examples for storage, identity, and logging
- spark/scala as an optional scaling path for ingestion and coarse aggregations

## Policy

policies/opa contains Rego policies that can evaluate:

- run manifests and release bundles
- publishability constraints
- infrastructure constraints for Terraform plans and Kubernetes manifests

Policy evaluation produces structured reports under the run directory.

## User interface

ui/ provides a local run browser that renders:

- run manifests
- reports and diffs between runs
- review tables and export artifacts

The UI reads from a small API server under src/omphalos/api.

## Independent verifiers

agents/ contains small verifiers that can validate a run directory without importing the Python package:

- agents/go/omphalos-verify
- agents/rust/omphalos-verify

## Command line

The CLI exposes:

- omphalos run: reference pipeline on synthetic data
- omphalos verify: recompute fingerprints and validate the manifest
- omphalos compare: compare declared artifacts between runs
- omphalos release: build and verify release bundles

Maximal pipelines and additional surfaces are available under src/omphalos/maximal and are invoked through explicit commands and job specs.

## Files kept for provenance

Original repository files are preserved. Where a file is materially upgraded, the prior content is copied into .legacy_snapshots/ with the same relative path before modification.

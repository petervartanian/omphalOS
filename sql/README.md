# SQL library

This folder contains analyst-facing SQL intended to be executed *against a run warehouse*.

- For the reference pipeline, that warehouse is SQLite at: `<run_dir>/warehouse/warehouse.sqlite`
- In workstation/deployment modes, the same schema can be materialized into DuckDB/Postgres.

These queries are deliberately plain SQL (no dbt refs) so they can be used by:

- reviewers who want to reproduce numbers directly
- operators building exports outside the Python pipeline
- notebook users

Conventions:

- parameters are written as `:param_name` placeholders (common across many drivers)
- each query includes a short header describing expected inputs/outputs


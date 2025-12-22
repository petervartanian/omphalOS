# omphalOS

omphalOS exists for a simple reason: _Analytic conclusions outlive the circumstances that produced them._

In U.S.-governmental environments vis-à-vis trade, technology, export controls, and enforcement — the setting(s) for which this system was first built in May 2024, then modernized for open release in December 2025 — an output that may inform action is expected to remain (i) legible under review, (ii) traceable to its provenance, and (iii) transmissible only under deliberate restraint.

The purpose, here, is practical: **to make that posture routine.**

This public release is a sanitized reference implementation, and all example data is synthetic.

## What the system asserts

A run is treated as an evidentiary package: it yields deliverables for a reader and, inseparably, a record adequate to explain what was done, reproduce it when feasible, and detect post-hoc alteration without argument.

The claims, then, are intentionally narrow:

1. Integrity: a completed run directory can be checked against its manifest. (To wit, if the fingerprints do not match, the package has changed.)
2. Comparability: two runs can be compared at the level of declared outputs, so disagreement can be located rather than narrated.
3. Controlled distribution: a publishability scan surfaces common disclosure hazards before a package leaves its originating context.

No stronger guarantee is implied. Correctness remains a matter of method, inputs, and judgment.

## What a reader can expect from the record

A run produces a directory intended to travel as a unit. The directory is structured so a reviewer can answer, from the artifacts alone, the questions that reliably matter once work leaves its originating workspace:

- What inputs were admitted, and what boundaries were enforced?
- What rules governed transformations, and where are those rules stated?
- Which outputs are intended for consumption, which are intermediate, and which require human review?
- What may be shared, with whom, and with what risk of inadvertent disclosure?
- When two executions disagree, is the disagreement substantive or procedural?

If a package cannot answer these questions, it is incomplete work.

## Minimal use

From a fresh clone, either install the package:

```bash
python -m pip install -e .
```

or run directly from source by setting:

```bash
export PYTHONPATH="$(pwd)/src"
```



One may verify the included sample run:

```bash
python -m omphalos verify --run-dir examples/sample_run
```

Execute the synthetic reference pipeline:

```bash
python -m omphalos run --config config/runs/example_run.yaml
```

Verify a generated run directory:

```bash
python -m omphalos verify --run-dir artifacts/runs/<run_id>
```

Compare two runs for payload-level equivalence:

```bash
python -m omphalos certify --run-a artifacts/runs/<runA> --run-b artifacts/runs/<runB>
```

## Optional extras (SQL/dbt, Airflow, Spark)

The core runtime stays lightweight. Extra surfaces are available as optional dependencies:

```bash
# Development tools
python -m pip install -e ".[dev]"

# SQL/dbt surface (DuckDB + Postgres connectivity)
python -m pip install -e ".[warehouse]"

# Orchestration surface
python -m pip install -e ".[orchestration]"

# Spark surface
python -m pip install -e ".[spark]"
```

## Distribution

When a run must be transmitted as a single object:

```bash
python -m omphalos release build --run-dir artifacts/runs/<run_id> --out artifacts/releases/<run_id>.tar.gz
python -m omphalos release verify --bundle artifacts/releases/<run_id>.tar.gz
```

Before distributing outputs outside the environment in which they were generated:

```bash
python -m omphalos publishability scan --path . --out artifacts/reports/publishability.json
```

The scan ought to be treated as a pre-flight gate, whereupon a clean report reduces common failure modes; it does not constitute a blanket safety determination.

## Configuration and declared rules

Runs are configured in `config/runs/`. Schemas and rule packs live in `contracts/`.

The governing posture is explicitness. Shapes worth consuming should be declared. Rules worth relying on should be written down. Failures should be inspectable.

## Appendix A: run directory layout

A typical run directory includes:

- `run_manifest.json`  
  Inventory of outputs with integrity fingerprints.

- `exports/`  
  Reader-facing products (tables, narrative, packet-style records).

- `reports/`  
  Structured checks and summaries (quality, determinism comparison, publishability scan, dependency inventory).

- `lineage/`  
  Append-only event record of execution.

- `warehouse/`  
  Local SQLite artifact used by the reference pipeline.

## Appendix B: operating expectations

omphalOS assumed two expectations throughout itself:

Firstly, the run directory is treated as an immutable package once the run completes. Editing outputs “for presentation” after completion is a change in evidence. If edits are required, the disciplined move is to rerun under a revised configuration and allow the record to reflect the revision.

Secondly, comparisons are only as meaningful as the boundaries you enforce. If the run’s inputs depend on ambient state—untracked files, implicit credentials, external services whose responses are not recorded—then replay will converge on approximation rather than identity. The system will still produce a record; it cannot supply missing constraints.

## Documentation

I recommend that you start with:

- `docs/overview.md`
- `docs/architecture.md`
- `docs/artifacts.md`
- `docs/cli.md`
- `docs/open_source_readiness.md`
- `docs/threat_model.md`

## License

Apache-2.0; see `LICENSE` and `NOTICE`; citation metadata is in `CITATION.cff`.

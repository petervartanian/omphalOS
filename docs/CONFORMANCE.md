# Conformance

Schemas live in `core/schemas/`:

- `case.json` — Case definition with investigative question and scope
- `packet.json` — Analytical product with mandatory epistemic scaffolding
- `run.json` — Portable run manifest with checksummed artifacts

## Running Conformance

From the repository root:

```bash
PYTHONPATH=core/src python -m omphalos.tests.conformance
```

This performs, in order:

(i) Pack checksum verification against `packs/INDEX.json`

(ii) Case execution using `hydrate/cases/case_chemicals.json`

(iii) Manifest verification where `run.json` hashes match artifacts

(iv) Export gate evaluation where `packet.json` must be admissible for export per STANDARDS_OF_REVIEW.md

(v) Best-effort independent verifiers (Go and Rust) if toolchains exist

The Python path is mandatory. The Go and Rust checks are opportunistic unless their toolchains are provisioned offline.

## Release Rule

No release without conformance passing offline.

## What This Ensures

The conformance contract ensures that epistemic humility is not aspirational—it is architecturally mandatory.

Verisimilar world generation produces realistic synthetic data using Zipf distributions, trade corridors, seasonal patterns. Functional polycentric verifiers (Rust, Go) perform checksum validation. Canonical SQL patterns implement investigation families. Documentation maintains scholarly standards. Export gate programmatically enforces unknowns, alternatives, falsifiers.

# omphalOS

**A polycentric, offline-capable casework suite for export control and sanctions analysis.**

omphalOS is built as computational infrastructure for *institutionalized doubt*: it surfaces patterns for review, then forces the record to carry uncertainty, rival explanations, and falsifiers as first-class structure.

## What v1.0 means

Version 1.0 is a contract:

- case, packet, and run-manifest schemas are frozen under `core/schemas/`
- every run is portable: it snapshots the case and the packs it used
- every artifact is checksummed; the manifest is computed last
- the export gate refuses packets that lack mandatory epistemic scaffolding

See `docs/CONFORMANCE.md` and `docs/STANDARDS_OF_REVIEW.md`.

## Quick start

```bash
# Verify offline packs
PYTHONPATH=core/src python -m omphalos.cli pack verify packs/INDEX.json

# Run a case (portable run directory under hydrate/runs)
PYTHONPATH=core/src python -m omphalos.cli case run hydrate/cases/case_chemicals.json --out hydrate/runs

# Verify integrity and apply the export gate
PYTHONPATH=core/src python -m omphalos.cli case verify hydrate/runs/case_chemicals/<run_id>/
PYTHONPATH=core/src python -m omphalos.cli export hydrate/runs/case_chemicals/<run_id>/packet.json

# Run the release constitution
PYTHONPATH=core/src python -m omphalos.cli conformance
```

The workbench UI is a single offline HTML file at `core/ui/analyst-workbench.html`.

## Architecture (high level)

omphalOS operates through three object types:

- **Cases**: investigative questions, scope, and selected investigations
- **Runs**: portable materializations of a case against a world slice, producing checksummed artifacts
- **Packets**: claims plus provenance, and mandatory doubt structure (unknowns, alternatives, falsifiers)

The system’s posture is intentionally non-classificatory: it does not assign risk scores, predict behavior, or operate as real-time monitoring.

## Investigation catalog

The shipped SQL catalog contains **20,000** reviewable investigations. Each is a single query, CTE-based, and bounded by a terminal `LIMIT`. Each includes Canon and Margin reminders designed to make interpretive restraint procedurally non-optional.

See `docs/INVESTIGATIONS.md` and `docs/CANON.md`.

## Polycentric verification

The reference runtime is Python. Independent verifiers in Go and Rust perform integrity checks and packet admissibility checks. Where toolchains are provisioned offline, conformance attempts to execute them as independent witnesses.

See `docs/CONFORMANCE.md`.

## License

CC0 1.0 Universal (Public Domain). See `LICENSE`.

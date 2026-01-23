# Conformance (v1.0)

“Final” is a property of contracts, not of fatigue.

omphalOS v1.0 is final only insofar as the schemas and the conformance suite remain stable.

## The contract

Schemas live in `core/schemas/`:

- `case-1.0.json`
- `packet-1.0.json`
- `run-1.0.json`

No breaking change is permitted without a major version increment.

## Running conformance

From the repository root:

```bash
python -m omphalos.cli conformance
```

This performs, in order:

1. pack checksum verification against `packs/INDEX.json`
2. a case run using `hydrate/cases/case_chemicals.json`
3. manifest verification (`run.json` hashes)
4. export gate evaluation (`packet.json` must be admissible for export)
5. best-effort independent verifiers (Go and Rust) if toolchains exist

The Python path is mandatory. The Go and Rust checks are opportunistic unless their toolchains are provisioned offline.

## Release rule

A v1.0 release must be built from a repository state where conformance passes without network access.


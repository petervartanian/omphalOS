# System overview

omphalOS is organized around a single invariant: every run is a verifiable artifact set. Every component exists to produce, validate, transport, or render that artifact set.

## Layers

1. Ingest
   - connectors read source feeds and emit raw inputs into the run directory
   - inputs are never modified in place; normalization writes to separate paths

2. Normalize
   - schema enforcement and canonicalization
   - deterministic derived fields, feature materialization, and quality reports

3. Warehouse
   - database instantiation from a stable DDL
   - transforms in dbt for staging, intermediate, and mart models
   - dbt artifacts are written into the run directory

4. Scoring and review products
   - match expansion tables, entity scores, and review queues
   - exports built from SQL catalog manifests

5. Packaging
   - run fingerprinting and manifest emission
   - bundle assembly for distribution to other environments

## Determinism and provenance

Determinism is enforced by:
- explicit sorting and stable serialization formats
- stable run identifiers
- stable artifact paths
- explicit hashing of every emitted file

Provenance is preserved by:
- retaining raw inputs
- retaining compiled transforms
- retaining query texts and parameters for every export

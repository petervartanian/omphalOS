# Run directory contract

A run directory is a self-contained unit. Consumers must be able to validate its integrity and interpret its contents without out-of-band metadata.

## Required files

manifest.json
  machine-readable declaration of all artifacts and report blocks

reports/
  structured validation and quality reports

warehouse/
  the analytical database and transform artifacts

exports/
  exported tables, extracts, and briefing products

## Fingerprinting

Each artifact is hashed with sha256. The manifest includes an artifacts_root_hash which is a deterministic merkle root of (path, sha256) pairs.

Verification requires:
- recomputing every sha256
- recomputing the merkle root
- verifying that manifest paths refer to files within the run directory

## Compatibility

Consumers should treat unknown files as allowed. Backwards compatibility is preserved by:
- keeping existing artifact paths stable
- adding new artifacts under new paths
- never reusing a path for a semantically different object

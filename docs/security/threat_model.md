# Threat model

## Assets

- run directories and release bundles
- manifest integrity and attestation keys
- ingestion credentials and connector secrets

## Adversaries

- data source manipulation: altered feeds and partial substitution
- artifact tampering: post-run modification of outputs
- exfiltration: unauthorized access to run directories
- replay: resubmission of old runs as new

## Controls

- manifest hashing and merkle roots
- deterministic paths and immutable writes
- signature and attestation for release bundles
- least privilege identities for runtime jobs
- policy checks on infrastructure and publication workflows

## Residual risk

- upstream feed trust remains external
- probabilistic matching systems require calibration governance
- downstream consumers must verify artifacts before use

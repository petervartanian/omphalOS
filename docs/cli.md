# Command-line interface

This document is the reference for the `omphalos` CLI.

## Conventions

- Commands return exit code `0` on success.
- Commands return non-zero exit codes on failure and print a machine-readable summary to stdout when possible.

## Commands

### `omphalos run --config <config.yaml>`

Executes a run declared by a config file and writes a run directory under `run.output_root` (default: `artifacts/runs/`).

Common flags:

- `--output-root <path>`: override where artifacts are written

### `omphalos verify <run_dir>`

Verifies that a run directory matches its manifest.

### `omphalos certify <run_dir_A> <run_dir_B>`

Compares two runs for payload equivalence and writes a determinism certification report.

### `omphalos publishability scan <path>`

Scans a tree for disallowed patterns and disallowed artifact classes using the rule files from the selected pack.

### `omphalos contracts validate <path>`

Validates JSON artifacts against schemas in `contracts/schemas/`.

### `omphalos release build <run_dir> -o <bundle.tar.gz>`

Builds a portable release bundle and a release manifest.

### `omphalos release verify <bundle.tar.gz>`

Verifies an extracted bundle or archive against its release manifest.

## Examples

Run, verify, and bundle:

```bash
omphalos run --config config/runs/example_run.yaml
omphalos verify artifacts/runs/<run_id>
omphalos release build artifacts/runs/<run_id> -o artifacts/releases/<run_id>.tar.gz
omphalos release verify artifacts/releases/<run_id>.tar.gz
```

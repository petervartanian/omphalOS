# omphalOS 2

**Investigate a transaction. Trace each observation. Record the review.**

omphalOS is a local workbench for export-compliance analysts reviewing counterparty records, shipments, and payments. Import your records, select a dated screening snapshot and investigation scope, examine the actual evidence, then record a named review and export a verifiable case packet.

The successor replaces the old generated-query/demo system with a small implemented investigation library and one shared workflow for the browser and command line. The original code and its audit remain recoverable in Git history. See [what changed](docs/RECONSTRUCTION.md), the [research basis](docs/RESEARCH.md), and [validation results](docs/VALIDATION.md).

## Start

Requires Python 3.11 or newer. Dependencies are pinned in `poetry.lock`.

```sh
poetry install
poetry run omphalos --workspace ./workspace serve --open
```

With a prepared local `.venv`, double-click **Start omphalOS.command** on macOS or **Start omphalOS.cmd** on Windows. Or run:

```sh
.venv/bin/python -m omphalos --workspace ./workspace serve --open
```

Open the address printed by the server. The server binds only to your computer. It loads no external scripts, fonts, or analytics. All analysis, review, verification, and replay work offline once dependencies and inputs are present. Only **Fetch snapshot** contacts the listed official publisher; it sends no case records or search names.

Use **Create synthetic demo** for a clearly labeled demonstration. It contains planted patterns, same-name entities that must remain distinct, different currencies/units, and benign installment payments. It does not stand in for private transaction data.

## The complete workflow

1. **Import evidence.** Upload `entities.csv` plus optional `shipments.csv`, `payments.csv`, `ownership.csv`, and `diligence.csv`, or a single `dataset.json`. Invalid rows, duplicates, unknown fields, and broken references reject the import with explanations. Original files and row locations are retained.
2. **Choose a reference snapshot.** Fetch or manually import an official ITA Consolidated Screening List, OFAC SDN, or OFAC non-SDN snapshot. Import date, publisher metadata, raw bytes, and source category remain visible. A source refresh creates a new snapshot.
3. **Define the question.** Select the actual investigations, date/domain/entity scope, parameters, assessment date, and optional screening snapshot. Missing information produces an explicit coverage limitation.
4. **Investigate.** Read neutral observations and exact contributing records. A name candidate remains an unresolved candidate. Amounts remain in their original currency; HS codes and ECCNs remain separate.
5. **Review.** A named analyst assesses every finding, explaining the disposition, uncertainties, alternative explanations, and evidence that would disconfirm it. Zero findings still require a review of coverage. Review revisions preserve earlier versions.
6. **Export and reproduce.** Completed review unlocks a ZIP containing a readable report, original and normalized inputs, code snapshot, settings, output, review, and complete checksums. Verify it independently, and replay a run using its retained inputs and matching installed code/dependencies.

See the [workbench guide](docs/WORKBENCH.md) and [evidence format](docs/EVIDENCE.md).

## Command-line example

```sh
poetry run omphalos --workspace ./workspace demo --id demo --case-id demo-case
poetry run omphalos --workspace ./workspace run demo-case
poetry run omphalos --workspace ./workspace status
# Use the run_id returned above:
poetry run omphalos --workspace ./workspace show RUN_ID
poetry run omphalos --workspace ./workspace verify RUN_ID
poetry run omphalos --workspace ./workspace replay RUN_ID
poetry run omphalos --workspace ./workspace review-template RUN_ID --output review.json
# Read the evidence, then complete review.json yourself.
poetry run omphalos --workspace ./workspace review review.json
poetry run omphalos --workspace ./workspace export RUN_ID
poetry run omphalos verify /path/to/export.zip
```

The template intentionally fails validation until completed. Its acknowledgment starts false. No command silently completes a human review.

Import your own data and save a case:

```sh
poetry run omphalos --workspace ./workspace import ./my-records --id my-records --label 'October review'
poetry run omphalos schema data
poetry run omphalos schema case
poetry run omphalos catalog
poetry run omphalos --workspace ./workspace case ./my-case.json
poetry run omphalos --workspace ./workspace sources fetch csl --id csl-october
```

All commands return JSON. Verification failure exits 1; invalid input exits 2. `--debug` includes diagnostic tracebacks. Put the global `--workspace` option before the subcommand.

## What verification means

- **Integrity:** the complete file inventory and hashes match; required content is present and structurally valid.
- **Replay:** the same installed engine and dependencies recompute the normalized findings and coverage from archived inputs. Execution timestamps and ZIP bytes need not match.
- **Review:** the required named assessment is recorded against the exact run manifest. Names are self-asserted; this is a single-user application.
- **Authenticity:** ordinary hashes do not establish who supplied evidence. Optional detached Ed25519 verification requires a separately trusted public key. A key bundled by an unknown sender is not independently trusted.

A passed check does not establish the truth of source records, the quality of a human explanation, legal clearance, or admissibility. The application never automatically merges identities, blocks funds, submits reports to authorities, or calculates a probability of wrongdoing.

## Scope and operating limits

This release serves one analyst on a local computer. It is not a multi-user case-management service. It does not provide a complete beneficial-ownership graph, automatic jurisdiction/license decisions, document OCR, international rule coverage, institution-specific retention enforcement, or legal conclusions. Ownership and diligence rows preserve supplied evidence; they do not establish completeness or an automatic 50 Percent Rule decision.

Do not interpret an expired listing retained by a publisher as an active restriction, or a later snapshot as a complete historical list. Review source dates and the underlying agency guidance. Public aggregate trade statistics cannot supply the company-level shipment and payment evidence this application needs.

Synthetic regression tests demonstrate implementation behavior; they do not establish operational detection accuracy. Domain-expert review and an authorized, representative held-out case set are still needed to measure useful findings and false-positive burden. Current validation results distinguish checks actually executed from configured future CI.

## Development

```sh
poetry install
poetry run pytest
poetry run ruff check src tests
poetry run black --check src tests tools
poetry build
```

[Security boundaries](SECURITY.md), [contribution guide](CONTRIBUTING.md), [data schema](docs/DATA.md), and [independent verifiers](native/README.md).

Code retains the original **CC0-1.0** license. Imported data and publisher snapshots retain their own terms and provenance.

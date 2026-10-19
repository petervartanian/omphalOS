<img src="src/omphalos/ui/logo.svg" width="72" height="72" alt="omphalOS ribbon mark" />

# omphalOS: the center of the investigation

**Start with a name or records. Follow the evidence. Record the decision.**

omphalOS is an investigation system for export-compliance analysts reviewing counterparties, shipments, and payments. Enter a company or person's name to discover public identity records, choose the relevant profile, and screen it against the official U.S. Consolidated Screening List. Import records for transaction analysis. A shallow evidence box folds as six stages of the same case are completed: Records, Sources, Plan, Findings, Assessment, and Package.

The successor replaces the old generated-query system with an implemented investigation library shared by the browser and command line. The original code and its audit remain recoverable in Git history. See [what changed](docs/RECONSTRUCTION.md), the [research basis](docs/RESEARCH.md), and [validation results](docs/VALIDATION.md).

## Website edition

The website runs the actual Python investigation engine in a dedicated browser worker, using a pinned Pyodide runtime. Static files can be published on GitHub Pages without a paid server or subscription. Case records stay in that browser; the entered name goes to GLEIF and Wikidata, and the official Consolidated Screening List is downloaded separately.

Build with `python tools/build_browser.py --output dist/browser` and publish that directory. See [browser operation and limits](docs/BROWSER.md). The normal desktop installation remains available below.

## Start locally

Requires Python 3.11 or newer. Dependencies are pinned in `poetry.lock`.

```sh
poetry install
poetry run omphalos --workspace ./workspace serve --open
```

With a prepared local `.venv`, double-click **Start omphalOS.command** on macOS or **Start omphalOS.cmd** on Windows. Or run:

```sh
PYTHONPATH=src .venv/bin/python -m omphalos --workspace ./workspace serve --open
```

Open the address printed by the server. The server binds only to your computer and loads no external scripts, fonts, or analytics. Identity discovery sends the entered name to GLEIF and Wikidata. Screening downloads the official public list separately when needed; that download sends no case records or search names. Analysis, review, verification, and replay work locally once dependencies and inputs are present.

Enter a company or person's name and choose **Find records**. omphalOS looks up public identity records. Choose a sourced profile, or continue with the name alone. It obtains the screening list and drafts a plan, then stops for your review. **Use these sources** accepts the selected inputs; **Run reviewed plan** authorizes the checks. **Import** accepts counterparty or transaction records. **Open** resumes saved investigations or prepares retained record sets. Open an available panel or its matching named control to inspect that stage; **Back to the box** returns to the overview. Earlier retained stages remain accessible, and future stages unlock when their prerequisites are present.

Records is the base. Sources, Plan, Findings, and Assessment form the walls, folding one at a time as each stage completes. Package is the lid; it closes only after the matching evidence package is created. Unfinished panels retain a muted version of their own color. Completion strengthens that color and adds a checkmark to the matching control. Editing a saved decision reopens Assessment and Package. Color and folding indicate completed work, not clearance or risk.

## Shared team workspaces

An optional [team server](docs/TEAM_SERVER.md) adds authenticated accounts, separate workspace membership, analyst/reviewer/viewer roles, live change notifications, and versioned saves that reject conflicting edits. Supervisor decisions bind the authenticated reviewer to the exact submitted package; the author and submitter cannot approve their own work. Imported assessments need a new authenticated team assessment before team approval.

This mode can run on an existing computer or institution's server without an application subscription. It requires a running host and HTTPS for access beyond that computer. The public GitHub Pages application continues to run entirely in the browser; it is not a centrally hosted team service. Both modes use the same investigation engine. See the [setup and operating boundaries](docs/TEAM_SERVER.md).

## The complete workflow

1. **Records.** Start with a name, import files, or select retained records. A counterparty CSV opens a mapping preview; **Investigate these records** confirms it and prepares the sources. Linked transaction files preserve their explicit relationships. Original inputs and row provenance are retained. Selected public profiles produce a new dataset with attributed fields; selecting a profile does not verify its identity.
2. **Sources.** Screening obtains or reuses an eligible official-list snapshot automatically. Review its dates and limitations, then choose **Use these sources**. Shipment and payment checks use the actual records supplied for the case. Acquisition alone does not complete this stage.
3. **Plan.** Inspect the proposed question, assessment date, checks, and missing prerequisites. **Run reviewed plan** records the approval and executes the checks. Changing the dataset, source, purpose, or date invalidates the previous acceptance and requires review again.
4. **Findings.** Inspect the results and coverage. Select an observation for its computed values, cited-record tables, and analytical limits. Evidence pages contain up to 40 references; each record opens with its provenance. Choose **Mark results reviewed** to proceed to Assessment. Identity candidates remain candidates, and zero findings do not establish clearance.
5. **Assessment.** Review the findings and coverage, then choose **Keep open**, **Escalate**, or **Conclude**. Enter one concise **Reason and next step** note, record your name, and acknowledge the coverage. Every new decision requires a substantive note of at least 12 characters. The decision covers the case; it does not require a questionnaire for each observation or invent individual judgments.
6. **Package.** A valid recorded decision and verified run enable an evidence ZIP containing the readable report, original and normalized inputs, code snapshot, settings, results, decision, and checksums. The report separates the analyst's decision from generated analytical context, names checks from the archived catalog, and states that separate supervisory approval is not recorded. Package creation remains separate from the recorded decision; an exported investigation can still be open or escalated.

The box and its working surface form the main application. **Open** lists saved investigations and records. Supporting record and case screens provide inventory and editing controls within the same application. See the [investigation guide](docs/WORKBENCH.md) and [evidence format](docs/EVIDENCE.md).

New guided runs retain the source acceptance and plan approval in a case schema 2.1 workflow record tied to the exact inputs. Earlier case schema 2.0 runs remain readable and exportable with valid reviews; missing approval history is shown as not recorded. It is never inferred from a successful analysis.

## Command line

Import records, inspect the schemas, and save a case definition referring to the imported dataset and any required source snapshot:

```sh
poetry run omphalos --workspace ./workspace import ./my-records --id my-records --label 'October review'
poetry run omphalos schema data
poetry run omphalos schema case
poetry run omphalos schema review
poetry run omphalos catalog
poetry run omphalos --workspace ./workspace sources fetch csl --id csl-october
poetry run omphalos --workspace ./workspace case ./my-case.json
poetry run omphalos --workspace ./workspace run CASE_ID
poetry run omphalos --workspace ./workspace show RUN_ID
poetry run omphalos --workspace ./workspace review ./case-decision.json
poetry run omphalos --workspace ./workspace export RUN_ID
poetry run omphalos --workspace ./workspace verify RUN_ID
poetry run omphalos --workspace ./workspace replay RUN_ID
poetry run omphalos verify /path/to/export.zip
```

Use the case and run IDs returned by the commands. New interface decisions use review schema 2.2: the explicit decision, reviewer, required reason and next-step note, complete observation scope, and coverage acknowledgment. Earlier schema 2.1 decisions remain readable and exportable under their original rules, including optional notes for open or escalated cases. Opening one in the interface leaves it unchanged; saving an interface revision uses 2.2. Schema 2.0 individual reviews also remain supported. No command silently completes a human decision.

All commands return JSON. Verification failure exits 1; invalid input exits 2. `--debug` includes diagnostic tracebacks. Put the global `--workspace` option before the subcommand.

## What verification means

- **Integrity:** the complete file inventory and hashes match; required content is present and structurally valid.
- **Replay:** the same installed engine and dependencies recompute the normalized findings and coverage from archived inputs. Execution timestamps and ZIP bytes need not match.
- **Review:** the required named assessment is recorded against the exact run manifest. In local and public browser modes, reviewer names are self-asserted. Team mode binds new assessments to authenticated server accounts. Review timestamps preserve revision order but are not trusted time.
- **Authenticity:** ordinary hashes do not establish who supplied evidence. Optional detached Ed25519 verification requires a separately trusted public key. A key bundled by an unknown sender is not independently trusted.

A passed check does not establish the truth of source records, the quality of a human explanation, legal clearance, or admissibility. The application never automatically merges identities, blocks funds, submits reports to authorities, or calculates a probability of wrongdoing.

## Scope and operating limits

Local mode serves one analyst on their computer. The website edition saves one workspace in each browser. It supports verified case-package import, separate continuation, and signed reviewer receipts through [case handoffs and independent review](docs/TEAM_REVIEW.md). Those modes do not synchronize participants. The optional team server adds centrally enforced membership and shared state, with conflicts requiring explicit review rather than simultaneous text merging. Download evidence packages and back up the complete team directory as appropriate. It does not provide a complete beneficial-ownership graph, automatic jurisdiction/license decisions, document OCR, international rule coverage, institution-specific retention enforcement, or legal conclusions. Ownership and diligence rows preserve supplied evidence; they do not establish completeness or an automatic 50 Percent Rule decision.

Do not interpret an expired listing retained by a publisher as an active restriction, or a later snapshot as a complete historical list. Review source dates and the underlying agency guidance. Public aggregate trade statistics cannot supply the company-level shipment and payment evidence this application needs.

Synthetic regression tests and [frozen public-source cases](docs/PUBLIC_CASE_VALIDATION.md) demonstrate behavior on their stated examples; they do not establish operational detection accuracy. Domain-expert review and an authorized, representative held-out case set are still needed to measure useful findings and false-positive burden. Current validation results distinguish checks actually executed from configured future CI.

## Development

```sh
poetry install
poetry run pytest
poetry run ruff check src tests
poetry run black --check src tests tools
poetry build
```

For interface development, use Node.js 24 or newer and run `npm ci --ignore-scripts`, then `npm run check`. ESLint checks browser code and Prettier checks the HTML, JavaScript, and CSS. `npm run format` applies the shared formatting rules. These are development tools only; running the application requires no Node.js or frontend build. The Python suite also runs the browser-state regression harness when Node.js is available, and CI explicitly installs it.

[Security boundaries](SECURITY.md), [contribution guide](CONTRIBUTING.md), [data schema](docs/DATA.md), and [independent verifiers](native/README.md).

Application code retains the original **CC0-1.0** license. Packaged Geist and Geist Mono fonts come from `geist@1.7.2` and retain the **SIL Open Font License 1.1**, copied in [font-license.txt](src/omphalos/ui/font-license.txt). Fonts load from the local application, with no third-party font request. Imported data and publisher snapshots retain their own terms and provenance.

The [detection benchmark](docs/DETECTION_BENCHMARK.md) measures labeled synthetic targets, misses, extra observations, and unavailable coverage across all checks, and accepts separately authorized labeled corpora. The [practitioner evaluation protocol](docs/PRACTITIONER_EVALUATION.md) specifies the human study that remains to be conducted.

The [investigator simulations](docs/SIMULATION_RESULTS.md) document the defects found, fixes, executed scenarios, and remaining limits. Their [research basis](docs/SIMULATION_RESEARCH.md) links the public guidance and operational manuals.

The [usability review](docs/USABILITY.md) records the design research, workflow decisions, and boundaries behind the current interface.

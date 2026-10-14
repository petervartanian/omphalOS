# Validation of omphalOS 2.0.0

Executed October 13, 2026 (America/New_York), on an Apple Silicon Mac. These results describe actual checks, not a claim that the system is perfect, legally certified, or operationally calibrated.

## Executed checks

| Check | Result |
|---|---|
| Python 3.11.14, source installation | 146 tests passed; 37 subtests passed |
| Python 3.13.7, source installation | 146 tests passed; 37 subtests passed |
| Python 3.14.3, source installation | 146 tests passed; 37 subtests passed |
| Fresh wheel installation, Python 3.13.7 | 146 tests passed; 37 subtests passed |
| Wheel UI resources | HTML, JavaScript, and CSS present and byte-identical to the validated source |
| Source distribution | Includes lockfiles, frontend check configuration, docs, examples, tests, native verifiers, launchers, and CI |
| Black and Ruff | Formatting and lint checks passed |
| ESLint and Prettier | Browser lint and shared HTML/JavaScript/CSS formatting checks passed |
| Frontend regression | Draft retention across 42 observations and three pages, plus 13 navigation, delayed-response, pending-save, cancellation, and numeric-input guards passed |
| Dependency vulnerability scan | No known vulnerabilities reported by pip-audit after dependency updates; this is a point-in-time database check |
| Frontend development dependency scan | npm audit reported zero known vulnerabilities; no npm package is a product runtime dependency |
| Go and Rust verifier builds | Both built and executed on macOS ARM64 |
| Independent verifier agreement | Both accepted the actual final 22-file run; shared fixtures reject changed, missing, extra, empty, omitted, malformed, duplicate-key, and wrong-digest cases |
| Browser acceptance | Synthetic import, official CSL fetch, case load/run, original-record drilldown, coverage inspection, explicit synthetic review, export, and replay exercised |
| Official reference data | CSL 26,128, OFAC SDN 19,431, and non-SDN 481 records parsed with retained raw snapshots; fresh verified-HTTPS downloads exercised |

One expected warning is emitted when a negative test deliberately constructs a ZIP with a duplicate member. The verifier rejects that ZIP; the warning is not a runtime failure.

The redesigned interface was inspected in the actual in-app browser at its normal 1280px desktop width and at a temporary 390px narrow breakpoint. The data page had no document-width overflow; tables scroll within their containers. Browser checks confirmed the import action opens and focuses its form, incomplete case edits survive navigation and Refresh, saving retains the case, the skip link focuses content without changing routes, run tabs work from the keyboard, and a cited record exposes its retained provenance. These checks complement the automated state harness; they are not a claim of comprehensive accessibility certification.

The redesigned export control created a real ZIP from the retained synthetic review. Its replay control reproduced analysis digest `aa3a439e7651cd5533b199545416c0c8b74a603b2b145ede56e1ddda3c55ff40` with matching engine code and no reported issues. The browser reported no console warnings or errors during this acceptance pass. Test-only case edits and exports were made in a separate copy of the workspace.

The Python suite covers actual CSV/JSON imports, row provenance, duplicate/broken records, finite exact amounts, date and entity/domain scope, true medians, distinct currency/unit cohorts, rolling baselines, invoice identifiers, expired listings, Unicode names, typed identity conflicts, and source parsing/download failures. It also covers incomplete reviews, zero-findings review, modified review anchors, retained revisions, concurrent run isolation, replay mismatches, source changes in a long-running process, host/origin/token checks, path containment, symlinks, and archive limits.

## Retained demonstration

The final browser demonstration used case `demonstration` and run `run-9c53223b1621433497d55a83907aaa0c`, with five fictional entities, 25 shipments, and 29 payments. Four selected investigations produced four observations. Screening compared five fictional entities with 24,978 CSL records after excluding 1,150 records outside their explicit effective dates; it produced zero candidates, which does not constitute clearance.

The example review identifies **Codex software validation — synthetic fixture** and explicitly states that it is a software acceptance test, not an operational compliance review. All four observations remain follow-up items. The browser export contains the source snapshot, original records, analysis, and that clearly labeled test review.

The final retained analysis was re-executed from its archived inputs and its normalized analysis digest matched. The reviewed ZIP passed a separate Python bundle-verification call. Go and Rust independently verified the run directory. These native checks do not claim full Python schema/review validation or ZIP support.

Full machine-readable evidence is kept in the separate local audit directory, including JUnit files for each environment, the final dependency scan, official-source probes, adapter timings, and `evidence/final-workflow.json`. A measured five-entity screening pass against the complete CSL took approximately 0.76 seconds on this host; this is a small-fixture measurement, not a scale guarantee.

## Configured but not yet executed remotely

The checked-in CI matrix targets Python 3.11–3.14 on Linux, macOS, and Windows. A separate native job builds both verifiers and runs their shared conformance fixtures on those operating systems. Those remote jobs have not been run for this local branch; Linux/Windows runtime compatibility remains unconfirmed by this work.

## Remaining external validation

The implementation is tested on synthetic cases and real public reference-list formats. Detection usefulness, false-positive burden, realistic dataset scale, reviewer workflow fit, and regulatory interpretations require qualified review using an authorized, representative case set. The application does not implement a complete ownership-rule engine, automatic legal clearance, multi-user identity/permissions, or organization-specific record-retention policy. Its exact supported behavior and exclusions are documented in `DATA.md`, `EVIDENCE.md`, and `SECURITY.md`.

# Investigator workflow simulation

October 18, 2026. These are synthetic software and task-sequence exercises, not a study with working investigators. The [research and scenario design](SIMULATION_RESEARCH.md) distinguishes BIS exporter guidance, public operational manuals, and investigative-quality frameworks.

## Defects found and corrected

1. **An earlier conclusion could reappear after a later escalation.** Review selection used textual timestamps and random IDs. Equal timestamps, different timestamp precision, or a clock correction could make an older decision and package current again. New revisions use logical, increasing timestamps; existing timestamps are compared as instants. Damaged stored history blocks a new revision rather than disappearing behind it.
2. **Saved investigations concealed their disposition.** Open, escalated, and concluded cases all appeared assessed. The saved-work list, case overview, assessment, and package now retain the recorded decision separately from package completion.
3. **Open or escalated handoffs could have no explanation.** New interface decisions use review 2.2 and require one reason and next-step note. This replaces no other human decision and introduces no per-observation questionnaire. Text validation checks presence and obvious placeholders, not the quality of reasoning. Existing 2.0 and 2.1 reviews remain supported without rewriting them.
4. **Coverage was difficult to read in exported reports.** HTML and Markdown reports now show check names from the retained catalog, evaluated-record counts, observations, unavailable-check reasons, and limitations in tables. Separate supervisory approval is explicitly not recorded.
5. **Supplied explanations could disappear from the reader's view.** A synthetic installment schedule and inspection note were retained in the dataset but absent from the readable report and inaccessible from assessment. Supporting records are now available during review and included in the report, with attribution and provenance. They remain supplied claims; displaying them does not establish corroboration or relevance.

## Executed coverage and limits

| Scenario | Executed exercise | What it establishes |
|---|---|---|
| S1: conflicting identity | Exact synthetic name match with a different country; retain candidate, analytical context, open decision, and unchanged analysis through export. | Conflicting country information does not silently discard a name candidate or turn it into an identity determination. No human identity-resolution accuracy was measured. |
| S2: unresolved transaction | Browser import of two fictional businesses, one shipment, three payments, and two supporting records; inspect the payment observation and cited original record; keep the case open with missing end-user evidence recorded. | The supplied installment explanation and unresolved questions can coexist with the computed observation. This transaction exercise did not perform official name or address screening. |
| S3: benign explanation, incomplete evidence | Supplier schedule attributes payments to deposit, inspection, and delivery; a second supplied record supports inspection while delivery remains unverified. Report and supporting-record tests include benign evidence, out-of-scope records, zero observations, and hostile markup. | Supplied explanations are preserved and accessible independently of findings. The software does not determine whether the explanation is true, complete, or sufficient. |
| S4: source and coverage failures | Existing regressions exercise failed downloads, historical/freshness limits, entities-only prerequisites, retry recovery, and evidence-integrity failures. New simulation exports an explicit open decision with zero observations and an unavailable screening check. | No observations, an unavailable check, and a failed request remain distinguishable. This does not reconstruct historical restrictions. |
| S5: later evidence or revised decision | Change run inputs; reopen and revise an existing decision; collide timestamps, reverse the clock, restore a backup, and revise again. | Earlier runs and exports survive. A new decision cannot inherit the previous package's completion. Changed inputs require a new run and review. Cross-run case chronology is still manual. |
| S6: handoff | Exercise name/CSV intake and all three dispositions through approval, evidence inspection, decision, export, reopening, and revision. Inspect the browser-generated package's question, decision, scope, coverage, references, supporting records, and next action. | A reader can obtain these fields from the artifact. No independent human recipient, delivery acknowledgment, authenticated supervisor approval, or organizational assignment was simulated. |

The regression files are `test_investigator_simulations.py`, `test_investigator_ux_simulation.py`, `test_investigator_reports.py`, and `test_supporting_records.py`, supplemented by the existing approval, source, recovery, review, and evidence tests. `check_browser_runtime.mjs` executes the actual pinned Python/WebAssembly runtime with network access disabled and checks review 2.2 through export, replay, reopening, and backup/restore.

The browser exercise uses an isolated headless Playwright MCP profile and static application files. Its fictional records are not included in the published application or any user's workspace. The task-sequence regression harness simulates interface state; it is distinct from the real-browser exercise.

## Subsequent work

The subsequent release adds [case handoff and signed review](TEAM_REVIEW.md), a [labeled detection benchmark](DETECTION_BENCHMARK.md), and a [prepared practitioner study](PRACTITIONER_EVALUATION.md). The executed observations above describe the earlier simulation release; they are not retrospectively evidence of the later features.

## Remaining boundaries at this checkpoint

This exercise does not establish detection accuracy, false-positive burden, legal adequacy, or usability for working investigators. It does not add shared cases, authenticated roles, independent supervisor approval, complete official address screening, or automatic interpretation of diligence text. A later practitioner study should use an authorized representative case set, include a recipient who sees only the package, and measure errors and assistance needed without assuming a benchmark.

Verification establishes consistency with the supplied file inventory. It does not authenticate the publisher, certify that supplied evidence is true, or prove that a report's assertions are correct. An attacker who rewrites an unsigned package and its manifest can create internally consistent replacement bytes. Existing packages remain readable; the verifier does not execute archived code or compare old reports against a newer renderer.

Executed release checks are recorded in [VALIDATION.md](VALIDATION.md).

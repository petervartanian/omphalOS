# Public-source case validation

This is an offline desk evaluation against historical official records. It adds
evidence beyond invented names and transactions. It is **not a study with working
investigators**, an independent human adjudication, a current sanctions list, or an
estimate of operational accuracy.

The October 18, 2026 corpus was frozen before its first engine run. Its canonical
SHA-256 is
`6267e4d2edd57813f25a999679e8d805d5e4b18df4437b9ec97e7f4bb3532d97`.
The runner rejects changes to those labels; a new evaluation corpus needs its own
version and fingerprint. Input hashes, engine inventory, emitted record IDs,
misses, unexpected candidates, and denominators remain in the JSON report.

## What was selected and why

Six organization entries were transcribed from two dated OFAC announcements:
SUEX OTC, S.R.O.; Chatex; Chatextech SIA; Hightrade Finance Ltd; Izibits OU; and
Southfront. They provide published legal names, alternate spellings, an explicit
alias relationship, and several organization identifier labels. The small
convenience sample was selected for those formats, not to represent the
population of screened counterparties. No personal addresses, passport numbers,
birth dates, or cryptocurrency wallets are retained.

The 21 scenarios include:

- Ten official name or alias inputs against the six extracted records.
- Five official identifiers with a deliberately uninformative display name, so
  the name matcher cannot conceal a broken identifier matcher.
- Two constructed punctuation/token-order variants, one deliberately conflicting
  country, and two constructed identifier-namespace negative controls.
- One missing-source control, whose comparisons must remain unavailable.

For each ordinary scenario, the named record is the positive candidate target;
the other extracted records are pairwise negative candidates. This does **not**
label any organization as unrestricted or establish that two real-world parties
have different legal identities. The country-conflict and namespace controls are
explicitly invented transformations, not additional facts about those companies.

The corpus uses November 8, 2021 as its historical comparison date. The extracted
snapshot is incomplete and must never be used for current operational screening.
The `source_documents` section records the source URLs, publication/update dates
where shown, retrieval date, and SHA-256 of each HTML response retrieved over
verified HTTPS. Those hashes describe retained retrieval bytes, not a promise that
the government page will remain byte-for-byte unchanged.

## Defects found without changing labels

The first evaluation returned 16 of 18 expected available candidates. It missed
the SUEX identifier-only scenarios because the published labels **Company Number**
and **Legal Entity Number** were not recognized by the engine. The matching module
was corrected to recognize these exact organization identifier labels while
retaining the separation from passport and tax identifiers. The source-derived
inputs and expected labels were left unchanged.

After the correction, the frozen corpus returns:

| Comparison outcome | Count |
| --- | ---: |
| Expected candidates returned | 18 |
| Expected candidates missed | 0 |
| Pairwise negative candidates correctly absent | 102 |
| Unexpected candidates | 0 |
| Unavailable positive targets | 1 |
| Unavailable negative targets | 5 |

These repeated comparisons concern only six records. They do not support a claim
of 100% real-world recall or specificity. Unavailable comparisons are excluded
from the returned-candidate and negative-comparison denominators. The report also
separates literal source extracts from the constructed controls.

## Public case coverage boundary

The BIS Seagate release supplies named parties and an enforcement narrative, but
not individual shipment/payment rows in this corpus. A separate fixture provides
only the three named organizations. All eight selected transaction checks must
report `not_evaluable`, with zero transaction observations. The public enforcement
outcome is **not** converted into invented shipments, a positive heuristic label,
or a legal prediction target. This checks that absent evidence remains absent.

## Workflow checks

The browser bridge is also exercised offline with a manually constructed test
projection of the historical extracts. The import is labeled manual; it is not
presented as an official CSL response or a complete list. The tests verify that:

1. Typing an official name and preparing a plan do not approve the source or run
   the plan. Source acceptance and plan execution require separate actions.
2. A returned candidate retains the cited source record and supplied entity row;
   a deliberately conflicting country remains visible.
3. Analysis does not create a case decision. Export is blocked until an explicit
   review is saved. A current case review requires a substantive note, the full
   finding scope, and acknowledgment of limitations.
4. Saving a decision does not rewrite the original observations. The decision,
   original evidence, export verification, and replay survive reopening.

These are product contracts informed by public guidance. They are not a claim
that BIS prescribes this six-stage interface or that software recreates an
investigator's judgment. OFAC's current match-assessment guidance calls for
reviewing the full entry, comparing additional identifying evidence, following
organizational procedures, and preserving the investigation record. Its September
9, 2026 update is included in the source inventory. [OFAC FAQ 5](https://ofac.treasury.gov/faqs/5)

BIS guidance requires inquiry and reevaluation when red flags are present. A
name candidate is therefore a prompt to examine the relevant evidence, not an
automatic conclusion or a clearance. [BIS Know Your Customer guidance](https://www.bis.gov/node/1533)

## Reproduce

Run from the repository with its Python dependencies installed:

```sh
PYTHONPATH=src python tools/public_case_validation.py --check --output public-case-validation.json
PYTHONPATH=src python -m pytest -q tests/test_public_case_validation.py
```

Both commands use frozen repository data and make no network requests. The
fixtures and evaluator are developer tools and are not included in the browser
build or a user's workspace.

The next distinct evidence requirement remains the human study described in
[Practitioner evaluation](PRACTITIONER_EVALUATION.md): recruit actual intended
users, independently label representative cases, and measure their task outcomes.
Neither a passing automated test nor simulated analyst behavior supplies those
participants or those observations.

## Primary records

- [OFAC SUEX designation announcement, September 21, 2021](https://ofac.treasury.gov/recent-actions/20210921)
- [OFAC designations and updates, November 8, 2021](https://ofac.treasury.gov/recent-actions/20211108)
- [BIS Seagate enforcement release, April 19, 2023](https://www.bis.gov/node/20250)

Only the necessary factual organization fields are transcribed. Announcements
describe actions at their publication dates; this evaluation makes no claim about
the parties' present status.

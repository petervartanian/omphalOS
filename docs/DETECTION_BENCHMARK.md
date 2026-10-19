# Detection benchmark

The offline benchmark evaluates which **observations** the current engine produces for a predeclared set of labeled subjects. It measures missed observations, unexpected observations, unavailable comparisons, and review burden. It does not classify legal violations, confirm identities, or establish clearance.

The checked-in corpus contains 104 invented cases covering all 12 current checks. It is authored by the software developers, not independently adjudicated by investigators. Its positive/negative balance and repeated boundary cases are deliberate test design, not representative prevalence. No operational accuracy claim follows from its rates.

## Run and reproduce

From a source checkout with omphalOS and its dependencies installed:

```sh
python tools/detection_benchmark.py --check --output evaluation.json
```

`--check` fails on contract misses, unexpected observations, duplicate observations, or unexpected coverage. It also verifies that every check has at least one positive, negative, and unavailable scenario through the accompanying regression test. Challenge cases remain scored but do not turn a documented capability limit into a failed implementation contract.

To require every positive target, including challenges and unavailable inputs, to be evaluated and emitted:

```sh
python tools/detection_benchmark.py --require-complete --output evaluation.json
```

That command currently exits **1**, deliberately. Several fixtures intentionally lack necessary inputs. The three previously measured executed-check misses now produce candidates; unavailable inputs remain unavailable. A successful contract check must not be presented as complete investigative coverage.

For an authorized, locally held evaluation corpus:

```sh
python tools/detection_benchmark.py --suite labeled-corpus.json --check --output evaluation.json
```

The harness makes no network requests, submits no records, and does not modify an application workspace. It reads JSON for external suites; it never executes code supplied by that JSON. Reports contain case rationales, subject keys, and coverage details, which may themselves be sensitive in a real corpus. Keep those reports under the corpus's access controls.

The JSON report records the complete corpus digest, per-case input and analysis digests, harness digest, and engine source inventory. There are no generated timestamps, random seeds, wall-clock timings, or machine-specific paths in the report. Identical corpus and source bytes produce identical report content. The regression suite also reverses record and list-entry order and checks that observation results do not change.

The synthetic fixtures live in `tests/detection_benchmark_fixtures.py`; the evaluator lives in `tools/detection_benchmark.py`. Neither is included in the browser's application runtime or user workspace. The ordinary test suite exercises the evaluator, so it runs in the existing cross-platform CI matrix.

## What gets counted

Each case selects one check and supplies an exhaustive set of intended positive and negative observation subjects. A target key refers to the relevant shipment, exporter, broker, invoice, normalized full address, exporter/month, entity/list-record pair, or missing-field category. The evaluator derives emitted keys from the actual findings, not their opaque finding IDs.

| Outcome | Meaning |
| --- | --- |
| TP | A declared positive target produced an observation. |
| FP | A declared negative target, or a subject outside the declared target universe, produced an observation. |
| FN | A declared positive target did not produce an observation in an executed check. |
| TN | A declared negative target did not produce an observation in an executed check. |
| Unavailable positive/negative | The check could not be evaluated. These targets enter neither the confusion matrix nor its rate denominators. |

A finding on the wrong shipment produces both a miss and an unexpected observation even when the total finding count happens to be correct. Repeated findings for the same target cannot inflate TP; they are a separate duplicate-observation failure and increase review burden.

Precision is TP/(TP+FP), recall is TP/(TP+FN), and false-positive rate is FP/(FP+TN). The report retains numerators and denominators; undefined rates are `null`. Per-check values are the useful comparisons. Pooled totals mix different target units and the deliberately unequal fixture distribution; they are diagnostic accounting, not an overall product accuracy score. A change in unavailable coverage must be examined alongside the rates.

An ordinary explanation does not make a correctly reported pattern a false positive. For example, three scheduled installments genuinely satisfy a three-payment rule. The benchmark separately counts observations whose synthetic facts supply an ordinary explanation, exposing the work imposed on a reviewer without asking the detector to adjudicate the explanation.

## Executed synthetic evaluation — October 18, 2026

| Check | Cases | TP | FP | FN | TN | Unavailable targets | Ordinary-explanation observations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `broker_concentration` | 6 | 3 | 0 | 0 | 2 | 1 | 1 |
| `data_quality` | 7 | 4 | 0 | 0 | 62 | 1 | 0 |
| `invoice_overlap` | 6 | 3 | 0 | 0 | 2 | 1 | 1 |
| `mixed_payment_methods` | 6 | 2 | 0 | 0 | 3 | 1 | 1 |
| `multi_domain` | 6 | 2 | 0 | 0 | 3 | 1 | 1 |
| `payment_fragmentation` | 6 | 3 | 0 | 0 | 3 | 1 | 1 |
| `screening_candidates` | 28 | 33 | 0 | 0 | 12 | 2 | 2 |
| `shared_address` | 7 | 3 | 0 | 0 | 3 | 1 | 1 |
| `threshold_cluster` | 8 | 3 | 0 | 0 | 4 | 1 | 1 |
| `unit_price_outlier` | 9 | 4 | 0 | 0 | 27 | 15 | 1 |
| `volume_spike` | 8 | 4 | 0 | 0 | 2 | 2 | 1 |
| `weekend_shipments` | 7 | 3 | 0 | 0 | 2 | 2 | 1 |
| **Total** | **104** | **67** | **0** | **0** | **125** | **29** | **12** |

The 29 unavailable targets comprise 17 positive and 12 negative targets. The 67 emitted observations cite 203 record occurrences and 185 distinct records summed within cases; they do not contain duplicate observations. These are workload proxies, not measured review times.

Boundary variations include exact decimal limits, inclusive/exclusive comparison bands, currency separation, case-sensitive units, true even-cohort medians, insufficient cohorts, different suites and countries, repeated counterparties, shared invoice prefixes, unavailable methods/domains, valid `NA` and `nA` values, future and undated records, partial months, zero-count months, explicit source dates, contradictory dates, conflicting identity context, aliases, and typed identifiers.

### Corrections found by the benchmark

The old per-entity candidate cap could hide qualifying source records behind earlier matches. Different entries can carry distinct list categories, dates, and programs. The engine now retains **every qualifying candidate**, whether based on an exact name, approximate name, supported romanization, or typed identifier. The archived `max_candidates` parameter remains accepted for compatibility but no longer truncates output. Legacy omission metrics remain present with zero values. Coverage separately counts exact/ID, approximate, and romanization candidates. Sorting does not affect which records are retained.

The original 91-case labels have not changed. On that unchanged subset, the previous 60 TP / 3 FN / 116 TN / 0 FP result becomes **63 TP / 0 FN / 116 TN / 0 FP**. Thirteen additional cases add four positive targets and nine negative controls. The original two challenge IDs remain in the corpus to expose regressions; they are not relabeled as negatives or removed. The expanded corpus is versioned `synthetic-detection-v2`.

A separate exact-match path retrieves the original `NPO Astra` / `НПО Астра` candidate using a normalized modern Russian ALA-LC romanization. It compares complete token multisets, preserves repeated tokens and organizational wording, and requires at least three distinctive letters on each side. It never applies approximate matching to the romanized form. Supplied exact names or aliases take precedence. The original strings, transformed comparison forms, transformation method, original-script similarity, alias quality, and conflicting context remain visible. The candidate is not an identity conclusion.

The added controls cover dissimilar distinctive names, near misses that would match under loose fuzzy transliteration, generic organization forms, short lookalikes, mixed scripts, unsupported letters, visual confusables, translation rather than transliteration, repeated tokens, reordered names, multigraphs, and conflicting identity context. Targeted tests additionally cover diacritics, hard/soft signs, source aliases, typed-ID precedence, dates, compatibility parameter values, and the total output bound. A separate regression fixes each candidate's source-country list being taken from the last compared record instead of its own retained entry.

A total output bound of 10,000 candidates protects browser memory. If exceeded, the engine discards prior partial findings and returns **not evaluable**, an observed candidate-count lower bound, and a scope-narrowing instruction. It does not label the result clean. Tests lower the bound to exercise its inclusive boundary, accumulation across entities, and approximate/romanized output without creating huge fixtures. The existing 20-million entity/list-record comparison bound also remains. Romanization is prepared once per name and adds at most one exact token comparison per name/alias pair; it does not generate combinatorial spellings. Replaying an archived run under the new engine may produce more candidates; archived inputs and outputs are not rewritten.

### Remaining boundaries

Zero measured misses on this developer-authored corpus is not evidence of complete detection or operational accuracy. Romanization is deliberately narrow: modern Russian letters only, exact normalized token equality only, and no mixed alphabet or unsupported combining-mark conversion. Other Cyrillic languages, historical characters, alternative spelling conventions, transliteration ambiguity, translations, and other scripts require authoritative supplied aliases or a separate validated matching capability. A lossy search form cannot establish the language or identity of the original record.

The engine still does not comprehensively resolve identity across scripts, screen ownership-based restrictions or unlisted parties, perform complete official-address screening, determine licensing, or establish transaction clearance. Seventeen positive and twelve negative targets lack evaluable inputs by design and are never counted as completed negative comparisons. Practitioner judgments and independently adjudicated operational outcomes are not replaced by these fixtures.

## External corpus contract

An external suite follows the same versioned JSON structure:

- `schema_version`: `"1.0"`.
- `suite_id`: a stable corpus/version label.
- `synthetic`: a Boolean describing the corpus.
- `provenance.corpus_id`: a local accession or source reference.
- `provenance.label_provenance`: who or what established labels and how disagreements were resolved. State when labels are not independent.
- `provenance.scope`: population, period, jurisdiction/context where relevant, sampling limits, and what the labels mean.
- `cases`: records described below.

Each case contains `id`, `check`, `kind` (`contract` or `challenge`), a substantive `rationale`, `expected_coverage` (`executed` or `not_evaluable`), ordinary omphalOS `tables`, and `targets`. Each target contains a stable `unit` and Boolean `positive`; an optional Boolean `ordinary_explanation` identifies positive observations that impose review despite a supplied ordinary explanation. Optional `case` values select scope, parameters, and as-of date. Screening cases also supply the normalized `watchlist` and matching `case.watchlist_snapshot_id`.

Use the fixture module as the executable schema example and its target strings as the observation-key reference. Export its returned dictionary as JSON if a starter schema is needed. Do not label an absent output as negative merely because the current engine missed it. Include controls, difficult cases, withheld test cases, and unavailable records; preserve the labels before evaluating the release. A corpus about wrongdoing needs a separately specified and validated legal/adjudication task, not a reinterpretation of these pattern labels.

For external corpora the report retains the supplied provenance and explicitly states that the harness has not verified authorization, label independence, representativeness, or correctness. The included tests exercise this contract using invented records; no independently labeled operational corpus has been supplied or evaluated in this release.

## Official-source basis

The International Trade Administration describes CSL results as screening aids, calls for additional due diligence on apparent matches, and directs users to the applicable official publications and agency lists. Keeping distinct exact candidate entries visible is an engineering inference from those distinctions; it is not a government-prescribed matching algorithm. [ITA, Consolidated Screening List](https://www.trade.gov/consolidated-screening-list)

OFAC describes its scores as name similarity, leaves threshold selection to the user's risk assessment and compliance practices, and recommends repeating baseline checks after search changes. Its own search uses algorithms different from omphalOS; this benchmark does not claim equivalence to that service. Historical membership also cannot be established from a current list alone. These points support explicit thresholds, retained source dates, disclosed omissions, and regression evaluation. [OFAC, How to Search OFAC's Sanctions Lists, FAQs 247, 250, 467, and 892](https://ofac.treasury.gov/faqs/topic/1636)


The supplementary character mapping follows the modern Russian letters in the Library of Congress's 2012 table. Removing its diacritics and hard/soft signs creates a lossy search form; exact-only comparison, minimum distinctive length, unsupported-script rejection, and candidate qualification are omphalOS engineering safeguards, not a government screening algorithm. [Library of Congress, Russian Romanization Table](https://www.loc.gov/catdir/cpso/romanization/russian.pdf)

OFAC's September 21, 2021 announcement uses the explicit organization identifier labels “Company Number” and “Legal Entity Number.” The matcher maps these to registration ID and LEI respectively, with a small explicit allowlist of equivalent labels. It does not infer an organization identifier from arbitrary substrings such as tax, alien, aircraft, or vehicle registration. The separately authored public-source corpus exposed these previously missed label forms. [OFAC, September 21, 2021 designation announcement](https://ofac.treasury.gov/recent-actions/20210921)

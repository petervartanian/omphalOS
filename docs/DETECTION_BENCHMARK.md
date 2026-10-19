# Detection benchmark

The offline benchmark evaluates which **observations** the current engine produces for a predeclared set of labeled subjects. It measures missed observations, unexpected observations, unavailable comparisons, and review burden. It does not classify legal violations, confirm identities, or establish clearance.

The checked-in corpus contains 91 invented cases covering all 12 current checks. It is authored by the software developers, not independently adjudicated by investigators. Its positive/negative balance and repeated boundary cases are deliberate test design, not representative prevalence. No operational accuracy claim follows from its rates.

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

That command currently exits **1**, deliberately. Two approximate candidates exceed the selected candidate limit, one cross-script candidate lacks a supplied alias, and several fixtures intentionally lack necessary inputs. A successful contract check must not be presented as complete investigative coverage.

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

## Executed synthetic baseline — October 18, 2026

| Check | Cases | TP | FP | FN | TN | Unavailable targets | Ordinary-explanation observations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `broker_concentration` | 6 | 3 | 0 | 0 | 2 | 1 | 1 |
| `data_quality` | 7 | 4 | 0 | 0 | 62 | 1 | 0 |
| `invoice_overlap` | 6 | 3 | 0 | 0 | 2 | 1 | 1 |
| `mixed_payment_methods` | 6 | 2 | 0 | 0 | 3 | 1 | 1 |
| `multi_domain` | 6 | 2 | 0 | 0 | 3 | 1 | 1 |
| `payment_fragmentation` | 6 | 3 | 0 | 0 | 3 | 1 | 1 |
| `screening_candidates` | 15 | 26 | 0 | 3 | 3 | 2 | 1 |
| `shared_address` | 7 | 3 | 0 | 0 | 3 | 1 | 1 |
| `threshold_cluster` | 8 | 3 | 0 | 0 | 4 | 1 | 1 |
| `unit_price_outlier` | 9 | 4 | 0 | 0 | 27 | 15 | 1 |
| `volume_spike` | 8 | 4 | 0 | 0 | 2 | 2 | 1 |
| `weekend_shipments` | 7 | 3 | 0 | 0 | 2 | 2 | 1 |
| **Total** | **91** | **60** | **0** | **3** | **116** | **29** | **11** |

The 29 unavailable targets comprise 17 positive and 12 negative targets. The 60 emitted observations cite 196 record occurrences and 180 distinct records summed within cases; they do not contain duplicate observations. These are workload proxies, not measured review times.

Boundary variations include exact decimal limits, inclusive/exclusive comparison bands, currency separation, case-sensitive units, true even-cohort medians, insufficient cohorts, different suites and countries, repeated counterparties, shared invoice prefixes, unavailable methods/domains, valid `NA` and `nA` values, future and undated records, partial months, zero-count months, explicit source dates, contradictory dates, conflicting identity context, aliases, and typed identifiers.

### Correction found by the benchmark

The old per-entity candidate cap could hide exact names and typed-identifier candidates behind earlier source records. Different entries can carry distinct list categories, dates, and programs. The engine now retains all exact normalized-name and typed-ID candidates. `max_candidates` limits only **additional approximate-name** candidates. Finding metrics show the total candidate count and omitted approximate candidates for that entity; coverage shows aggregate retained exact/ID and omitted approximate counts.

Seven exact entries now produce seven observations even with a smaller approximate-match limit. Separate tests exercise seven typed-ID matches with unrelated names, mixed exact/approximate candidates, and weak aliases that remain explicitly qualified. All still require identity review. A total output bound of 10,000 retained candidates protects browser memory. The engine checks it before building findings for an entity; if exceeded, it discards prior partial findings and returns **not evaluable**, an observed candidate-count lower bound, and a scope-narrowing instruction. It does not label the result clean. Targeted tests lower the bound to exercise both its inclusive boundary and accumulation across entities without creating a huge fixture. Replaying an archived run under the new engine may produce more candidates; archived inputs and outputs are not rewritten.

### Remaining measured boundaries

Two of seven approximate-name candidates exceed the default five-candidate limit. They remain FNs in the challenge case, with omission counts available in coverage and finding metrics. Increasing the approximate limit restores eligible candidates; the built-in parameter maximum remains 100. This is a bounded presentation/observation policy, not evidence that omitted candidates are unimportant.

One fixture stipulates that `NPO Astra` and `НПО Астра` identify the same invented organization. Without an explicit alias, the engine does not perform transliteration and misses the candidate. The corresponding supplied-alias case succeeds. Arbitrary cross-script identity resolution, ownership-based restrictions, unlisted parties, complete official-address screening, licensing, and transaction clearance are not measured capabilities of this engine.

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

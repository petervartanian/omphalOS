# Data and analytical behavior

omphalOS analyzes records supplied by an analyst. It does not obtain private bank payments, named customs transactions, beneficial ownership, or export licenses from public trade statistics. The included demonstration is synthetic. Public screening lists provide identity candidates and source-specific listing context; they do not establish that a transaction violates a rule.

## Import formats

Provide a directory with one file per table, named `entities.csv`, `shipments.csv`, `payments.csv`, `ownership.csv`, or `diligence.csv`. Any table can instead use a same-named JSON file containing an array of objects. A table cannot appear twice. Alternatively, provide one `dataset.json` containing `{"schema_version":"2.0","tables":{"entities":[...]}}`. Do not mix that file with per-table files.

UTF-8 and UTF-8 with BOM are supported. CSV uses a header and standard quoting. Unknown fields, duplicate headers/IDs/JSON keys, malformed rows, invalid values, and broken references reject the entire import. Errors identify the input file and row where possible. For multiline CSV records, provenance records the ending physical line; JSON provenance uses the one-based row within its table. Optional blank CSV cells become missing values. All dates use `YYYY-MM-DD`.

Each recognized file is limited to 80 MiB; each table to 250,000 rows. Non-CSV/JSON files are not imported. HTTP uploads have an additional, smaller request limit imposed by the workbench. Importing or running analysis makes no network request. Existing nonempty datasets and snapshots cannot be overwritten through these APIs.

The machine-readable field schemas are available from `omphalos.data.data_schema()` and in `examples/data-schema.json`.

| Table | Required fields | Additional supported fields |
|---|---|---|
| `entities` | `entity_id`, `name` | `entity_type` (defaults to `organization`), `aliases`, `country`, `address`, `city`, `postal_code`, `registration_id`, `lei`, `notes` |
| `shipments` | `shipment_id`, `exporter_id` | `importer_id`, `domain`, `date`, `qty`, `unit`, `commodity_code`, `hs_code`, `eccn`, `invoice_id`, `declared_value`, `ccy`, `mode`, `incoterm`, `description` |
| `payments` | `payment_id`, `shipment_id`, `amount`, `ccy` | `method`, `date`, `bank`, `broker` |
| `ownership` | `relationship_id`, `child_id`, `parent_id` | `ownership_percent`, `valid_from`, `valid_to`, `source_url`, `notes` |
| `diligence` | `evidence_id`, `entity_id`, `title`, `text` | `source_url`, `date` |

At least one entity is required. Stable record and entity-reference IDs contain 1–80 ASCII letters, digits, underscores, or hyphens and start with a letter or digit. Invoice and registration identifiers are text and may contain punctuation. Country codes use two uppercase letters; currency codes use three. These syntax checks do not validate an external code registry. LEIs require 20 uppercase alphanumeric characters; checksum/registry status is not verified. HS codes are digit strings, preserving leading zeros, and are separate from ECCNs. Neither field establishes control status.

Aliases accept a JSON string array or, in CSV, `|` separators. Entity aliases are limited to 100 entries. Names and aliases are limited to 1,000 characters. Other string fields are bounded; NUL characters are rejected. Source-document links must be HTTP(S) URLs without embedded credentials; the application does not fetch them automatically.

Payments, quantities, and declared values must be positive finite decimals with at most 28 digits and eight decimal places. Use decimal strings in JSON to preserve your intended values. Currency is mandatory with a payment amount, and shipment `declared_value` and `ccy` must appear together. No currency conversion occurs. Refunds and negative adjustments require a different data model; do not disguise them as positive payments. Ownership percentages, when supplied, are between 0 and 100. Ownership self-edges, missing parents/children, and inverted date intervals are rejected; import does not prove that the graph is complete or historically correct.

Ownership and diligence records are retained with their provenance. The current detector catalog does not propagate ownership-based restrictions or synthesize conclusions from diligence text. No beneficial-ownership completeness or legal percentage-rule implementation is claimed.

## Originals and integrity

An import stores exact original bytes under `originals/`, normalized records in `dataset.json`, and hashes/counts/field coverage in `dataset-manifest.json`. Metadata maps each normalized record ID to its source file and source row. Loading a dataset verifies the normalized hash, original hashes and sizes, record counts, full provenance inventory, and each normalized record against a fresh parse of its cited original row.

This detects inconsistency and modification relative to an inventory. It does not establish who supplied the original records or whether they describe real events. An actor able to replace the entire dataset and inventory can create another self-consistent package. Evidence export and optional signatures have separate documented trust boundaries.

## Scope and dates

Every case names its dataset, as-of date, selected investigations, and optional scope. Unknown entity IDs and investigation IDs are rejected. Parameters are nested under investigation IDs. Unknown parameters, invalid types, and out-of-range values are rejected. Integer parameters must be JSON integers; decimal parameters are strings.

Shipment scope combines the date interval, selected domain labels, and selected entity IDs (matching exporter or importer). Linked payments must also satisfy the date interval independently. Future-dated shipments and payments are excluded by `as_of` even when no explicit interval is supplied. A `date_to` later than `as_of` is capped at `as_of`.

Undated shipments/payments remain eligible when neither `date_from` nor `date_to` is selected. An explicit date bound excludes undated records. Date-based detectors always require dates. Counts show total, in-scope, excluded, and undated records. Entity screening applies entity scope and, if domain scope is selected, restricts to entities involved in in-scope shipments. Calendar date filters do not manufacture dates for entity records.

No findings is distinct from no usable data. Coverage is `executed` when prerequisites yielded evaluable records, even with zero findings; it is `not_evaluable` when tables, required parameters, a snapshot, or usable records are missing. Monetary and ratio metrics serialize as decimal strings under a fixed 60-digit arithmetic context. Findings have deterministic IDs and cite the records that support their calculations.

## Detector definitions

The catalog exposed in the application is the authoritative list of parameter names, defaults, and numeric bounds. Each selected definition actually executes; there are no generated duplicate definitions.

| Investigation | Actual calculation and default |
|---|---|
| `payment_fragmentation` | At least three payment records linked to one shipment. Totals are separated by currency. |
| `mixed_payment_methods` | At least three distinct normalized, known method labels for a shipment. Unknown methods do not count. |
| `threshold_cluster` | At least two payments in the chosen currency in `[0.90 × threshold, threshold)`. The user must supply threshold and currency; no legal threshold is inferred. |
| `shared_address` | At least three entity IDs sharing normalized street address, city, postal code, and country. Street address and country are required. |
| `volume_spike` | A complete month with at least five shipment records and at least three times the mean of six prior months, requiring at least three records in the baseline. Includes zero months inside the observed period; assumes no baseline before its first observed month. The month containing the as-of/end date is excluded conservatively. A partially scoped first month is excluded from the baseline. |
| `multi_domain` | An exporter appears in at least three distinct supplied domain labels. Labels do not classify controlled products. |
| `unit_price_outlier` | Total linked payments divided by quantity, compared to the true median in cohorts with identical currency, normalized unit, and commodity code (explicit `commodity_code`, otherwise `hs_code`). Minimum cohort five; ratios at least five or at most 0.20 trigger. Mixed-currency shipments and incomplete/small cohorts are excluded and counted. |
| `broker_concentration` | A normalized broker label occurs across at least three distinct exporter/importer pairs. This does not calculate graph betweenness. |
| `invoice_overlap` | Identical normalized full invoice identifiers across at least two exporters. Requires at least four alphanumeric characters and two digits. Punctuation/case differences are normalized; a shared `INV` prefix is insufficient. |
| `weekend_shipments` | Saturday/Sunday supplied dates. No holiday, operating-calendar, time-zone, or prohibition assumption. |
| `screening_candidates` | Name/alias or typed-identifier candidates against one selected snapshot. Details below. |
| `data_quality` | Missing country/address on entities; date/importer/quantity/unit/HS/invoice on shipments; date/method on payments. Missing values are context gaps, not conclusions that records are false. |

Paid value per quantity is a proxy, not a verified invoice price. The full comparison cohort is cited for each median finding. Volume counts reflect imported coverage, not verified business totals; finding references cannot prove that no other shipments occurred. Invoice overlap, shared addresses, mixed methods, and threshold proximity have commonplace benign explanations. Every finding includes specific unknowns, alternative explanations, and checks that could explain or overturn it.

## Official-source snapshots

Supported adapters are `csl`, `ofac_sdn`, and `ofac_non_sdn`:

- [Consolidated Screening List](https://www.trade.gov/consolidated-screening-list): [bulk JSON](https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json), containing source-specific categories and available effective dates.
- [OFAC Sanctions List Service](https://ofac.treasury.gov/sanctions-list-service): [standard SDN XML](https://sanctionslistservice.ofac.treas.gov/api/download/sdn.xml) and [standard consolidated non-SDN XML](https://sanctionslistservice.ofac.treas.gov/api/download/consolidated.xml). These are distinct lists with different legal implications.

A download is an explicit action and transmits no dataset, case question, entity name, or screening query. Bulk access currently requires no API key. Requests use verified TLS with the operating system trust store, a 30-second socket timeout, and a 100 MiB response cap. Redirects are restricted to the documented application hosts and the exact GovCloud publication bucket observed from OFAC's official endpoint, under its `/Published/` prefix. Transient signed redirect URLs are not saved as provenance. An upstream hosting change may require an adapter update; arbitrary URLs are not accepted.

Manual import supports the same formats for offline work. Manual content is not independently authenticated merely because it parses. Both methods retain exact raw bytes, the normalized source records, SHA-256, retrieval/import time, source publication or aggregation time, update metadata, and parser version. A failure creates no partial snapshot. Loads verify and reparse originals. Refresh is never automatic.

Parsers accept at most 150,000 entries. CSL must have a complete, unpaginated `results` array whose length matches `total`; each record needs name, ID, and list source. OFAC standard UTF-8 XML must have publication metadata and a matching record count. DTDs, custom entities, alternate-encoding evasion, missing identities, and duplicate source IDs are rejected. Nested OFAC alias/address/identifier UIDs do not replace the top-level listing UID. OFAC weak/strong alias labels, program tags, and available identifiers are retained. Standard XML lacks individual effective dates for many entries; the parser leaves those dates unknown.

## Candidate matching

Matching preserves record IDs and never merges entities automatically. Name normalization uses Unicode compatibility decomposition, removes combining accents, case-folds, and normalizes punctuation/space. It preserves non-Latin scripts; it does not transliterate Cyrillic or treat Latin/Cyrillic lookalikes as identical. Similarity is the greater of character-sequence similarity in supplied word order and sorted word order. The default cutoff is 0.90. This score is not a probability or measured accuracy claim.

Aliases are evaluated separately. An integer character-count upper bound prunes only pairs that cannot reach the cutoff, preserving the defined matching behavior while avoiding unnecessary sequence comparisons. Names, prepared token order, and character counts are computed once per snapshot name. Identifier candidates compare LEIs to explicitly labeled LEIs, and registration identifiers to explicitly labeled registration IDs; arbitrary passports or tax identifiers are not cross-matched. Registration jurisdiction remains an unresolved identity question.

Candidate output includes actual name similarity, compared strings, exact identifier matches and disagreements, entity-type comparison, like-for-like ISO country comparison, source alias quality, list category, dates, program labels, and structured source-record references. OFAC country names are not silently converted into ISO-code disagreements. Conflicting country, type, or identifier context remains visible; it does not automatically establish or dismiss identity.

Default display is five candidates per entity, maximum 100; omissions are counted in coverage. Exact typed identifier matches sort ahead of name-only candidates. A case with more than 20 million entity/list-record comparisons is `not_evaluable` and asks for narrower entity scope. Known future-started or expired records are excluded for the case as-of date; an inclusive end date remains eligible on that date. Missing effective dates remain unknown. Source dates more than seven days before the as-of date receive an explicit staleness limitation; snapshots dated after the as-of date receive a historical-coverage limitation. The seven-day rule is a display heuristic, not an official freshness guarantee.

A name match cannot establish a legal restriction. Listing absence cannot establish permissibility. This implementation does not comprehensively screen ownership-based restrictions, embargoes, product controls, licenses, end use, or all jurisdictions. A current list cannot reconstruct historical membership without appropriate effective-date evidence.

## Verified examples and validation

`examples/import/` contains a small synthetic CSV import. `examples/case.json` targets dataset ID `example_data`. `examples/data-schema.json` exports the current row schema. The application can also create a deterministic planted demo with outliers, fragmented payments, shared invoice/address patterns, a count spike, several currencies, undated records, distinct entities sharing a name, and benign installments.

Local adapter validation on October 13, 2026 parsed full official responses: 26,128 CSL records, 19,431 SDN records, and 481 non-SDN records. A fresh non-SDN HTTPS download and validation succeeded. On this host, the optimized matcher screened five synthetic names against the archived full CSL in approximately 0.76 seconds; timing is illustrative, not a service guarantee. Counts are observations of those snapshots, not permanent source sizes. Tests exercise invalid imports, exact decimals, logical provenance, true versus arithmetic mean behavior, cohort separation, dates/scopes, prefix collisions, expired/future listings, identity conflicts, Unicode, unsafe XML/redirects, failed-fetch atomicity, and synthetic benign cases. These tests do not estimate real-world detection accuracy.

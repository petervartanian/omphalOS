"""Invented, labeled cases for the offline benchmark; never shipped in the app.

Labels describe subjects expected to produce observations, not illegal conduct.
Challenge labels intentionally include useful capabilities the engine does not have.
"""

from copy import deepcopy


def entity(number=1, **changes):
    return {
        "entity_id": f"E{number}",
        "name": f"Fictional Entity {number}",
        "country": "US",
        "address": f"{number} Invented Lane",
        "city": "Exampleville",
        "postal_code": "00000",
        **changes,
    }


def shipment(number=1, **changes):
    return {
        "shipment_id": f"S{number}",
        "exporter_id": "E1",
        "importer_id": "E2",
        "date": "2026-09-15",
        "qty": "1",
        "unit": "pcs",
        "hs_code": "845610",
        "invoice_id": f"INV-{number:04}",
        "domain": "instruments",
        **changes,
    }


def payment(number=1, **changes):
    return {
        "payment_id": f"P{number}",
        "shipment_id": "S1",
        "date": "2026-09-15",
        "amount": "100",
        "ccy": "USD",
        "method": "wire",
        "broker": "Fictional Agency",
        **changes,
    }


def tables(*, entities=None, shipments=None, payments=None):
    result = {"entities": entities if entities is not None else [entity(), entity(2)]}
    if shipments is not None:
        result["shipments"] = shipments
    if payments is not None:
        result["payments"] = payments
    return result


def benchmark_suite():
    cases = []

    def add(check, label, records, positives=(), negatives=(), **changes):
        ordinary = changes.pop("ordinary", False)
        cases.append(
            deepcopy(
                {
                    "id": f"{check}-{label}",
                    "check": check,
                    "kind": "contract",
                    "rationale": changes.pop("rationale"),
                    "expected_coverage": "executed",
                    "tables": records,
                    "targets": [
                        {
                            "unit": unit,
                            "positive": True,
                            "ordinary_explanation": ordinary,
                        }
                        for unit in positives
                    ]
                    + [{"unit": unit, "positive": False} for unit in negatives],
                    **changes,
                }
            )
        )

    def paid(values, **options):
        return tables(
            shipments=[shipment()],
            payments=[
                payment(i + 1, amount=str(value), **options)
                for i, value in enumerate(values)
            ],
        )

    check = "payment_fragmentation"
    for count in (2, 3, 4):
        add(
            check,
            f"count-{count}",
            paid([100] * count),
            positives=["S1"] if count >= 3 else [],
            negatives=["S1"] if count < 3 else [],
            rationale="Three linked payments is the inclusive default count boundary.",
        )
    add(
        check,
        "ordinary-installments",
        paid([100, 200, 300]),
        ["S1"],
        ordinary=True,
        rationale="The fictional contract explicitly permits three installments. The count is real but does not imply evasion.",
    )
    split = paid([100, 100, 100])
    split["shipments"].append(shipment(2))
    split["payments"][-1]["shipment_id"] = "S2"
    add(
        check,
        "separate-shipments",
        split,
        negatives=["S1", "S2"],
        rationale="Payments on different shipments cannot be pooled to reach three.",
    )
    add(
        check,
        "missing-payments",
        tables(shipments=[shipment()]),
        ["S1"],
        expected_coverage="not_evaluable",
        rationale="The intended payment pattern cannot be tested without the payments table.",
    )

    check = "mixed_payment_methods"
    for label, methods, positive in (
        ("three-distinct", ["wire", "card", "cash"], True),
        ("two-distinct", ["wire", "card", "wire"], False),
        ("case-spacing", ["Wire transfer", "WIRE  TRANSFER", "wire-transfer"], False),
        ("placeholder-does-not-count", ["wire", "card", "N/A"], False),
        ("ordinary-mixed-settlement", ["wire", "card", "cash"], True),
    ):
        records = paid([100] * len(methods))
        for row, method in zip(records["payments"], methods):
            row["method"] = method
        add(
            check,
            label,
            records,
            positives=["S1"] if positive else [],
            negatives=[] if positive else ["S1"],
            ordinary=label.startswith("ordinary"),
            rationale="Count distinct usable normalized method labels; ordinary mixed settlement still produces a review observation.",
        )
    add(
        check,
        "unknown-methods",
        paid([100, 100, 100], method="unknown"),
        ["S1"],
        expected_coverage="not_evaluable",
        rationale="No usable method labels means no evaluated method comparison.",
    )

    check = "threshold_cluster"
    threshold_case = {"parameters": {check: {"threshold": "10000", "currency": "USD"}}}
    for label, amounts, positive in (
        ("lower-inclusive", [9000, 9000], True),
        ("upper-exclusive", [10000, 10000], False),
        ("just-below-lower", ["8999.99999999", "8999.99999999"], False),
        ("just-below-upper", ["9999.99999999", "9999.99999999"], True),
        ("one-in-band", [9500, 10000], False),
        ("ordinary-contract-schedule", [9500, 9800], True),
    ):
        add(
            check,
            label,
            paid(amounts),
            positives=["S1"] if positive else [],
            negatives=[] if positive else ["S1"],
            case=threshold_case,
            ordinary=label.startswith("ordinary"),
            rationale="The analyst-chosen band is [9000, 10000) USD and requires two payments; it is not a legal threshold.",
        )
    split = paid([9500, 9500])
    split["payments"][1]["ccy"] = "EUR"
    add(
        check,
        "currency-separation",
        split,
        negatives=["S1"],
        case=threshold_case,
        rationale="A EUR payment does not count toward a USD comparison band.",
    )
    add(
        check,
        "threshold-not-selected",
        paid([9500, 9500]),
        ["S1"],
        expected_coverage="not_evaluable",
        rationale="No analyst threshold or currency was selected; no legal threshold may be guessed.",
    )

    check = "shared_address"
    shared = [entity(i, address="20 Fictional Street") for i in range(1, 4)]
    key = "20 fictional street|exampleville|00000|us"
    add(
        check,
        "three-entities",
        tables(entities=shared),
        [key],
        rationale="Three distinct IDs share a fully normalized supplied address.",
    )
    add(
        check,
        "two-entities",
        tables(entities=shared[:2]),
        negatives=[key],
        rationale="Two entities remain below the default group boundary.",
    )
    variants = deepcopy(shared)
    variants[1]["address"] = "20 FICTIONAL Street"
    variants[2]["address"] = "20 Fictional  Street"
    add(
        check,
        "case-spacing",
        tables(entities=variants),
        [key],
        rationale="Harmless case and spacing variations preserve the shared address.",
    )
    suites = deepcopy(shared)
    for index, row in enumerate(suites):
        row["address"] += f" Suite {index + 1}"
    add(
        check,
        "distinct-suites",
        tables(entities=suites),
        negatives=[key],
        rationale="Different supplied suites must not be collapsed into one full-address group.",
    )
    countries = deepcopy(shared)
    countries[-1]["country"] = "CA"
    add(
        check,
        "different-country",
        tables(entities=countries),
        negatives=[key],
        rationale="Identical street text in different countries does not satisfy the group boundary.",
    )
    add(
        check,
        "ordinary-registered-agent",
        tables(entities=shared),
        [key],
        ordinary=True,
        rationale="The invented address is a registered agent office. Shared address remains an observation, not ownership evidence.",
    )
    add(
        check,
        "missing-country",
        tables(entities=[entity(i, country=None) for i in range(1, 4)]),
        [key],
        expected_coverage="not_evaluable",
        rationale="Country is required to make full addresses comparable.",
    )

    check = "multi_domain"
    for label, domains, positive in (
        ("three-domains", ["optics", "aviation", "electronics"], True),
        ("two-domains", ["optics", "aviation", "optics"], False),
        ("case-spacing", ["Optics", "OPTICS", "optics"], False),
        ("placeholder", ["optics", "aviation", "unknown"], False),
        ("ordinary-distributor", ["optics", "aviation", "electronics"], True),
    ):
        add(
            check,
            label,
            tables(
                shipments=[
                    shipment(i + 1, domain=value) for i, value in enumerate(domains)
                ]
            ),
            positives=["E1"] if positive else [],
            negatives=[] if positive else ["E1"],
            ordinary=label.startswith("ordinary"),
            rationale="Three distinct usable declared labels satisfy the rule; a diversified distributor is an ordinary explanation.",
        )
    add(
        check,
        "missing-domains",
        tables(shipments=[shipment(domain=None)]),
        ["E1"],
        expected_coverage="not_evaluable",
        rationale="Undeclared domains cannot be invented from product descriptions.",
    )

    check = "invoice_overlap"
    for label, invoices, exporters, positive in (
        ("full-identifier", ["INV-2026-0042", "INV-2026-0042"], ["E1", "E2"], True),
        (
            "format-variation",
            ["INV-2026-0042", "inv / 2026 / 0042"],
            ["E1", "E2"],
            True,
        ),
        ("shared-prefix", ["INV-2026-0042", "INV-2026-0043"], ["E1", "E2"], False),
        ("same-exporter", ["INV-2026-0042", "INV-2026-0042"], ["E1", "E1"], False),
        (
            "ordinary-numbering-collision",
            ["INV-2026-0042", "INV-2026-0042"],
            ["E1", "E2"],
            True,
        ),
    ):
        add(
            check,
            label,
            tables(
                shipments=[
                    shipment(i + 1, invoice_id=value, exporter_id=exporters[i])
                    for i, value in enumerate(invoices)
                ]
            ),
            positives=["inv20260042"] if positive else [],
            negatives=[] if positive else ["inv20260042"],
            ordinary=label.startswith("ordinary"),
            rationale="Only a full normalized identifier reused across distinct exporters qualifies; unrelated numbering can coincide.",
        )
    add(
        check,
        "short-generic-identifiers",
        tables(
            shipments=[
                shipment(1, invoice_id="A1"),
                shipment(2, exporter_id="E2", invoice_id="A1"),
            ]
        ),
        ["a1"],
        expected_coverage="not_evaluable",
        rationale="The weak identifier lacks two digits and four alphanumeric characters.",
    )

    check = "weekend_shipments"
    for label, day, positive in (
        ("friday", "2026-09-18", False),
        ("saturday", "2026-09-19", True),
        ("sunday", "2026-09-20", True),
        ("monday", "2026-09-21", False),
        ("ordinary-port-operations", "2026-09-19", True),
    ):
        add(
            check,
            label,
            tables(shipments=[shipment(date=day)]),
            positives=["S1"] if positive else [],
            negatives=[] if positive else ["S1"],
            ordinary=label.startswith("ordinary"),
            rationale="Calendar Saturday/Sunday is the supported signal; ports may operate normally on those days.",
        )
    add(
        check,
        "undated",
        tables(shipments=[shipment(date=None)]),
        ["S1"],
        expected_coverage="not_evaluable",
        rationale="A missing date cannot establish a weekday.",
    )
    add(
        check,
        "future-outside-scope",
        tables(shipments=[shipment(date="2026-10-03")]),
        ["S1"],
        expected_coverage="not_evaluable",
        rationale="An otherwise weekend-dated shipment after the as-of date is outside scope.",
    )

    check = "broker_concentration"
    for count in (2, 3, 4):
        records = tables(
            entities=[entity(i) for i in range(1, count + 2)],
            shipments=[
                shipment(i, importer_id=f"E{i + 1}") for i in range(1, count + 1)
            ],
            payments=[payment(i, shipment_id=f"S{i}") for i in range(1, count + 1)],
        )
        add(
            check,
            f"pairs-{count}",
            records,
            positives=["fictional agency"] if count >= 3 else [],
            negatives=[] if count >= 3 else ["fictional agency"],
            rationale="Count distinct exporter/importer pairs, not the number of payments or shipments.",
        )
    add(
        check,
        "duplicate-pair",
        paid([100, 100, 100, 100]),
        negatives=["fictional agency"],
        rationale="Many payments for one exporter/importer pair cannot become multiple pairs.",
    )
    ordinary = tables(
        entities=[entity(i) for i in range(1, 5)],
        shipments=[shipment(i, importer_id=f"E{i + 1}") for i in range(1, 4)],
        payments=[payment(i, shipment_id=f"S{i}") for i in range(1, 4)],
    )
    add(
        check,
        "ordinary-large-intermediary",
        ordinary,
        ["fictional agency"],
        ordinary=True,
        rationale="An invented legitimate intermediary serves three unrelated pairs. Concentration alone is not suspicious conduct.",
    )
    add(
        check,
        "unknown-broker",
        paid([100, 100, 100], broker="unknown"),
        ["fictional agency"],
        expected_coverage="not_evaluable",
        rationale="A shared placeholder is not a supplied broker identity.",
    )

    def price_records(values):
        return tables(
            shipments=[shipment(i + 1) for i in range(len(values))],
            payments=[
                payment(i + 1, shipment_id=f"S{i + 1}", amount=str(value))
                for i, value in enumerate(values)
            ],
        )

    check = "unit_price_outlier"
    for label, values, positives in (
        ("high-inclusive", [100, 100, 100, 100, 500], ["S5"]),
        ("below-high", [100, 100, 100, 100, "499.99999999"], []),
        ("low-inclusive", [100, 100, 100, 100, 20], ["S5"]),
        ("above-low", [100, 100, 100, 100, "20.00000001"], []),
        ("even-cohort-median", [100, 100, 200, 200, 300, 1000], ["S6"]),
        ("ordinary-different-specification", [100, 100, 100, 100, 500], ["S5"]),
    ):
        units = [f"S{i + 1}" for i in range(len(values))]
        add(
            check,
            label,
            price_records(values),
            positives=positives,
            negatives=[unit for unit in units if unit not in positives],
            ordinary=label.startswith("ordinary"),
            rationale="Use the true median of an identical currency/unit/commodity cohort; boundary ratios are inclusive and product quality is not known.",
        )
    for label, field, value in (
        ("currency", "ccy", "EUR"),
        ("unit-case", "unit", "PCS"),
        ("commodity", "hs_code", "902780"),
    ):
        records = price_records([100, 100, 100, 100, 500])
        records["payments" if field == "ccy" else "shipments"][-1][field] = value
        add(
            check,
            f"separate-{label}",
            records,
            ["S5"],
            negatives=["S1", "S2", "S3", "S4"],
            expected_coverage="not_evaluable",
            rationale="Splitting one record into a different comparison cohort leaves every cohort below minimum size; absence is not a negative result.",
        )

    def month_records(counts):
        rows = []
        for month, count in enumerate(counts, 3):
            start = len(rows)
            rows.extend(
                shipment(start + i + 1, date=f"2026-{month:02}-15")
                for i in range(count)
            )
        return tables(shipments=rows)

    check = "volume_spike"
    for label, counts, positive in (
        ("increase", [1, 1, 1, 1, 1, 1, 5], True),
        ("below-current-minimum", [1, 1, 1, 1, 1, 1, 4], False),
        ("ratio-inclusive", [2, 2, 2, 2, 2, 2, 6], True),
        ("below-ratio", [2, 2, 2, 2, 2, 2, 5], False),
        ("zero-months-included", [3, 0, 0, 0, 0, 0, 5], True),
        ("ordinary-new-contract", [1, 1, 1, 1, 1, 1, 5], True),
    ):
        add(
            check,
            label,
            month_records(counts),
            positives=["E1|2026-09"] if positive else [],
            negatives=[] if positive else ["E1|2026-09"],
            ordinary=label.startswith("ordinary"),
            rationale="Six prior calendar months, including observed zero months, define the baseline; threefold ratio and five current shipments are inclusive.",
        )
    add(
        check,
        "insufficient-history",
        tables(
            shipments=[shipment(i + 1, date=f"2026-{i + 7:02}-15") for i in range(3)]
        ),
        ["E1|2026-09"],
        expected_coverage="not_evaluable",
        rationale="Three observed months do not establish a six-month baseline.",
    )
    add(
        check,
        "partial-current-month",
        month_records([1, 1, 1, 1, 1, 1, 5]),
        ["E1|2026-09"],
        case={"as_of": "2026-09-20"},
        expected_coverage="not_evaluable",
        rationale="The current partial month is excluded rather than extrapolated.",
    )

    check = "data_quality"
    complete = tables(shipments=[shipment()], payments=[payment()])
    fields = [
        "entities.name",
        "entities.country",
        "entities.address",
        "shipments.date",
        "shipments.importer_id",
        "shipments.qty",
        "shipments.unit",
        "shipments.hs_code",
        "shipments.invoice_id",
        "payments.date",
        "payments.method",
    ]
    add(
        check,
        "complete-context",
        complete,
        negatives=fields,
        rationale="All fields checked by this detector are present; completeness does not establish truth.",
    )
    for label, table, field, value in (
        ("missing-address", "entities", "address", None),
        ("placeholder-address", "entities", "address", "N/A"),
        ("missing-method", "payments", "method", None),
        ("punctuation-method", "payments", "method", "---"),
    ):
        records = deepcopy(complete)
        records[table][0][field] = value
        unit = f"{table}.{field}"
        add(
            check,
            label,
            records,
            [unit],
            negatives=[name for name in fields if name != unit],
            rationale="The named absent/unusable field is the sole missing-context observation; valid other fields are negative controls.",
        )
    namibia = deepcopy(complete)
    namibia["entities"][0]["country"] = "NA"
    namibia["shipments"][0]["unit"] = "nA"
    add(
        check,
        "meaningful-na-labels",
        namibia,
        negatives=fields,
        rationale="NA is Namibia's country code and nA is a valid SI unit; neither is a generic missing-value sentinel.",
    )
    add(
        check,
        "empty-scope",
        complete,
        ["entities.address"],
        case={"scope": {"entity_ids": ["E2"], "domains": ["aviation"]}},
        expected_coverage="not_evaluable",
        rationale="A valid scope with no retained matching records yields unavailable coverage, not completed clean data.",
    )

    check = "screening_candidates"

    def screening(label, subject, entries, positive_ids, negative_ids=(), **changes):
        snapshot = {
            "snapshot_id": "synthetic-list",
            "source_id": "csl",
            "metadata": {"source_updated_at": "2026-10-01"},
            "entries": [
                {
                    "record_id": f"L{i + 1}",
                    "source_row": i + 1,
                    "list_name": "Synthetic test list",
                    **entry,
                }
                for i, entry in enumerate(entries)
            ],
        }
        add(
            check,
            label,
            tables(entities=[entity(**subject)]),
            [f"E1|{value}" for value in positive_ids],
            [f"E1|{value}" for value in negative_ids],
            watchlist=snapshot,
            case={"watchlist_snapshot_id": "synthetic-list", **changes.pop("case", {})},
            **changes,
        )

    screening(
        "exact",
        {"name": "Fictional Aster Instruments"},
        [{"name": "Fictional Aster Instruments"}],
        ["L1"],
        rationale="Exact full names are candidates, not confirmed identities.",
    )
    screening(
        "unicode-token-order",
        {"name": "Société Ágora Maritime Ltd"},
        [{"name": "Maritime Societe Agora Ltd"}],
        ["L1"],
        rationale="Accent normalization and token order do not remove this candidate.",
    )
    screening(
        "listed-alias",
        {"name": "Fictional Aster Instruments"},
        [{"name": "Distinct Legal Name", "aliases": ["Fictional Aster Instruments"]}],
        ["L1"],
        rationale="The retained explicit alias supports a name candidate.",
    )
    screening(
        "distinctive-word-mismatch",
        {"name": "Aster Research and Production Association"},
        [{"name": "Orion Research and Production Association"}],
        [],
        ["L1"],
        rationale="Shared organization wording cannot conceal different distinctive names.",
    )
    screening(
        "same-name-conflicting-country",
        {"name": "Fictional Aster Instruments", "country": "US"},
        [{"name": "Fictional Aster Instruments", "countries": ["DE"]}],
        ["L1"],
        ordinary=True,
        rationale="The invented same-name firms differ in country; the candidate remains visible for identity resolution, not automatic clearance.",
    )
    screening(
        "typed-lei",
        {"name": "Fictional Aster Instruments", "lei": "12345678901234567890"},
        [
            {
                "name": "Distinct Legal Name",
                "identifiers": [{"idType": "LEI", "idNumber": "12345678901234567890"}],
            }
        ],
        ["L1"],
        rationale="A typed exact LEI candidate survives dissimilar names; generic untyped IDs cannot substitute.",
    )
    screening(
        "expired-and-current",
        {"name": "Fictional Aster Instruments"},
        [
            {"name": "Fictional Aster Instruments", "end_date": "2026-09-30"},
            {"name": "Unrelated Entity", "start_date": "2026-01-01"},
        ],
        [],
        ["L1", "L2"],
        rationale="An explicitly expired entry is excluded while the current unrelated entry permits a genuine executed negative.",
    )
    screening(
        "inconsistent-dates",
        {"name": "Fictional Aster Instruments"},
        [
            {
                "name": "Fictional Aster Instruments",
                "start_date": "2026-09-01",
                "end_date": "2025-09-01",
            }
        ],
        ["L1"],
        rationale="Contradictory source dates cannot silently suppress a matching name; applicability remains unresolved.",
    )
    screening(
        "all-expired",
        {"name": "Fictional Aster Instruments"},
        [{"name": "Fictional Aster Instruments", "end_date": "2026-09-30"}],
        ["L1"],
        expected_coverage="not_evaluable",
        rationale="No in-date source entries means no performed comparison; this is not a no-match result.",
    )
    add(
        check,
        "missing-source",
        tables(entities=[entity(name="Fictional Aster Instruments")]),
        ["E1|L1"],
        expected_coverage="not_evaluable",
        rationale="Screening cannot proceed without an explicitly selected snapshot.",
    )
    screening(
        "exact-matches-beyond-limit",
        {"name": "Fictional Aster Instruments"},
        [{"name": "Fictional Aster Instruments"} for _ in range(7)],
        [f"L{i}" for i in range(1, 8)],
        rationale="All seven entries are exact candidate matches. The approximate-name display cap must not suppress any exact candidate or its distinct list context.",
    )
    screening(
        "approximate-display-limit-challenge",
        {"name": "Fictional Aster Instruments"},
        [{"name": "Fictional Aster Instrument"} for _ in range(7)],
        [f"L{i}" for i in range(1, 8)],
        kind="challenge",
        rationale="All seven approximate candidates qualify. The original positive labels stay fixed; a presentation limit must not remove any candidate from the analysis.",
    )
    screening(
        "display-limit-expanded",
        {"name": "Fictional Aster Instruments"},
        [{"name": "Fictional Aster Instruments"} for _ in range(7)],
        [f"L{i}" for i in range(1, 8)],
        case={"parameters": {check: {"max_candidates": 7}}},
        rationale="An archived explicit cap remains accepted for compatibility but cannot suppress otherwise qualifying candidate targets.",
    )
    screening(
        "cross-script-challenge",
        {"name": "NPO Astra"},
        [{"name": "НПО Астра"}],
        ["L1"],
        kind="challenge",
        rationale="The fixture author stipulates the names refer to the same invented organization. The original positive label stays fixed; exact romanization can retrieve a candidate without adjudicating identity.",
    )
    screening(
        "cross-script-supplied-alias",
        {"name": "NPO Astra", "aliases": ["НПО Астра"]},
        [{"name": "НПО Астра"}],
        ["L1"],
        rationale="An authoritative supplied alias takes precedence over a derived romanization search form.",
    )

    for label, left, right, positive in (
        ("romanization-reversed", "НПО Астра", "NPO Astra", True),
        ("romanization-multigraphs", "Shchukin Zhirnov", "Щукин Жирнов", True),
        ("romanization-distinctive-mismatch", "NPO Astra", "НПО Орион", False),
        ("romanization-no-fuzzy-expansion", "NPO Astra", "НПО Астр", False),
        ("romanization-generic-only", "NPO", "НПО", False),
        ("romanization-single-letter", "A", "А", False),
        ("romanization-mixed-script", "Astra", "Аstра", False),
        ("romanization-unsupported-letter", "Galina", "Ґалина", False),
        ("romanization-confusable-not-sound", "Poccia", "Россия", False),
        (
            "romanization-no-translation",
            "Scientific Production Association Astra",
            "НПО Астра",
            False,
        ),
        ("romanization-repeated-token", "Astra Astra", "Астра", False),
        ("romanization-reordered-tokens", "Zhigulin Fedor", "Фёдор Жигулин", True),
    ):
        screening(
            label,
            {"name": left},
            [{"name": right}],
            ["L1"] if positive else [],
            [] if positive else ["L1"],
            rationale=(
                "Exact modern Russian romanization supports a review candidate; it does not establish that the names identify the same subject."
                if positive
                else "No candidate relationship is stipulated. Dissimilar, generic, ambiguous, unsupported, translated, or mixed-script strings must not acquire a candidate through loose romanization."
            ),
        )
    screening(
        "romanization-conflicting-context",
        {"name": "NPO Astra", "entity_type": "organization", "country": "US"},
        [{"name": "НПО Астра", "entity_type": "individual", "countries": ["RU"]}],
        ["L1"],
        ordinary=True,
        rationale="An exact romanization candidate retains explicit type and country conflicts for review; context differences do not erase the candidate or confirm identity.",
    )

    return {
        "schema_version": "1.0",
        "suite_id": "synthetic-detection-v2",
        "synthetic": True,
        "provenance": {
            "corpus_id": "omphalos-authored-synthetic-v2",
            "label_provenance": "Software-author labels from explicit fixture facts and published detector contracts; no independent human adjudication.",
            "scope": "Twelve observation checks on invented records, boundary conditions, unavailable inputs, ordinary explanations, and declared capability challenges. Not a legal or wrongdoing classification task.",
        },
        "cases": cases,
    }

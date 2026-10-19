"""Small, substantive analytical definitions with explicit coverage and uncertainty."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
from statistics import median
from typing import Any

from .data import TABLES
from .models import Analysis, Case
from .screening import candidate_findings, normalized_name
from .util import canonical_json, sha256_bytes


def integer(default: int, minimum: int, description: str, maximum: int = 10000) -> dict:
    return {
        "type": "integer",
        "default": default,
        "minimum": minimum,
        "maximum": maximum,
        "description": description,
    }


def number(
    default: str | None, minimum: str, description: str, maximum: str | None = None
) -> dict:
    result = {"type": "number", "minimum": minimum, "description": description}
    if default is not None:
        result["default"] = default
    else:
        result["required"] = True
    if maximum is not None:
        result["maximum"] = maximum
    return result


DEFINITIONS = [
    (
        "payment_fragmentation",
        "Multiple payments per shipment",
        "Count linked payment records for each shipment; installments are observations, not evidence of structuring.",
        ["shipments", "payments"],
        {"minimum_payments": integer(3, 2, "Minimum linked payments")},
        [
            "Payment records may represent ordinary installments, fees, or duplicate source entries."
        ],
    ),
    (
        "mixed_payment_methods",
        "Mixed payment methods",
        "Count distinct known methods on payments linked to a shipment.",
        ["shipments", "payments"],
        {"minimum_methods": integer(3, 2, "Minimum distinct known payment methods")},
        ["Unknown methods do not count; method categories are analyst-provided."],
    ),
    (
        "threshold_cluster",
        "Payments below a chosen threshold",
        "Find shipments with repeated payments in [threshold × lower_ratio, threshold), in the explicitly chosen currency.",
        ["shipments", "payments"],
        {
            "threshold": number(
                None,
                "0.00000001",
                "Analyst's comparison threshold; no legal threshold is inferred",
            ),
            "currency": {
                "type": "string",
                "required": True,
                "description": "Three-letter currency code",
            },
            "lower_ratio": number(
                "0.90",
                "0",
                "Inclusive lower band as a proportion of threshold",
                "0.99999999",
            ),
            "minimum_payments": integer(
                2, 2, "Minimum payments in the comparison band"
            ),
        },
        [
            "Threshold proximity does not establish evasion or intent.",
            "Different currencies are never combined.",
        ],
    ),
    (
        "shared_address",
        "Shared full address",
        "Group distinct entity IDs by normalized full address, city, postal code, and country.",
        ["entities"],
        {"minimum_entities": integer(3, 2, "Minimum distinct entities")},
        [
            "Shared offices, registered agents, and industrial parks are common benign explanations.",
            "Missing country or street address makes an entity ineligible.",
        ],
    ),
    (
        "volume_spike",
        "Shipment count increases",
        "Compare each complete observed month with the mean of a rolling prior window; zero-count months within the observed period are included.",
        ["shipments"],
        {
            "window_months": integer(6, 2, "Prior calendar months", 60),
            "minimum_prior_shipments": integer(
                3, 1, "Minimum total prior-window shipments"
            ),
            "minimum_current_shipments": integer(
                5, 1, "Minimum current-month shipments"
            ),
            "minimum_ratio": number(
                "3", "1.00000001", "Minimum increase over prior-window mean"
            ),
        },
        [
            "Counts reflect imported records, not verified total business volume.",
            "No baseline is assumed before the earliest in-scope dated record; partial last months are excluded.",
        ],
    ),
    (
        "multi_domain",
        "Activity across declared domains",
        "Count distinct supplied shipment domains per exporter.",
        ["shipments"],
        {"minimum_domains": integer(3, 2, "Minimum distinct domains")},
        [
            "Domains are analyst labels, not verified product classifications or control status."
        ],
    ),
    (
        "unit_price_outlier",
        "Comparable paid-value outliers",
        "Compare total linked payments per quantity to the true median within identical currency, unit, and commodity-code cohorts.",
        ["shipments", "payments"],
        {
            "minimum_cohort": integer(5, 3, "Minimum comparable shipments"),
            "high_ratio": number(
                "5", "1.00000001", "Minimum multiple of cohort median"
            ),
            "low_ratio": number(
                "0.20", "0.00000001", "Maximum fraction of cohort median", "0.99999999"
            ),
        },
        [
            "Payments per quantity are a proxy, not verified invoice unit prices; freight, taxes, and partial payments can differ.",
            "No FX conversion, unit conversion, broad-domain cohorting, or quality adjustment occurs.",
            "Unit labels are case-sensitive; label variants are not automatically combined.",
            "Full cohort records are cited so the median and comparison are inspectable.",
        ],
    ),
    (
        "broker_concentration",
        "Broker involvement across counterparties",
        "Count distinct exporter/importer pairs in payments handled by each supplied broker label.",
        ["shipments", "payments"],
        {"minimum_pairs": integer(3, 2, "Minimum distinct counterparty pairs")},
        [
            "This is broker concentration, not graph betweenness or an assessment of illicit activity.",
            "Broker identity depends on consistent analyst labels.",
        ],
    ),
    (
        "invoice_overlap",
        "Full invoice identifier overlap",
        "Find identical full invoice identifiers used by multiple exporters; compare full normalized values, not prefixes.",
        ["shipments"],
        {"minimum_exporters": integer(2, 2, "Minimum distinct exporters")},
        [
            "A shared accounting service or unrelated invoice numbering can produce overlap.",
            "Only identifiers with at least two digits and four alphanumeric characters are considered.",
        ],
    ),
    (
        "weekend_shipments",
        "Weekend-dated shipment records",
        "Identify records dated Saturday or Sunday using supplied calendar dates.",
        ["shipments"],
        {},
        [
            "Weekend activity is common; no business calendar, holiday, time zone, or prohibited period is inferred."
        ],
    ),
    (
        "screening_candidates",
        "Official-list identity candidates",
        "Compare supplied entity names and typed identifiers with an explicitly selected official snapshot, preserving individual list categories and dates.",
        ["entities"],
        {
            "minimum_score": number(
                "0.90",
                "0.50",
                "Minimum character/token-order name similarity; not a probability",
                "1",
            ),
            "max_candidates": {
                **integer(
                    5,
                    1,
                    "Deprecated compatibility value; all qualifying candidates are retained regardless of this value",
                    100,
                ),
                "deprecated": True,
            },
        },
        [
            "Candidate scores are string similarities, not calibrated confidence or legal conclusions.",
            "Current snapshots cannot establish historical list membership when effective dates are absent.",
            "Ownership-based restrictions and unlisted entities are not comprehensively covered.",
        ],
    ),
    (
        "data_quality",
        "Missing analytical context",
        "Report missing fields that reduce interpretation or comparability of supplied records.",
        ["entities"],
        {},
        [
            "Completeness measures cannot establish the accuracy or exhaustiveness of imported records."
        ],
    ),
]


def catalog() -> list[dict]:
    return [
        {
            "id": item[0],
            "title": item[1],
            "description": item[2],
            "required_tables": item[3],
            "parameters": item[4],
            "limitations": item[5],
            "source_urls": [],
        }
        for item in DEFINITIONS
    ]


def _parameters(case: Case, definition: dict) -> tuple[dict, list[str]]:
    supplied = case.parameters.get(definition["id"], {})
    specs = definition["parameters"]
    unknown = set(supplied) - set(specs)
    if unknown:
        raise ValueError(
            f"Unknown {definition['id']} parameters: {', '.join(sorted(unknown))}"
        )
    result, missing = {}, []
    for key, spec in specs.items():
        value = supplied.get(key, spec.get("default"))
        if value is None:
            missing.append(key)
            continue
        if spec["type"] == "integer":
            if type(value) is not int:
                raise ValueError(f"{definition['id']}.{key} must be an integer")
        elif spec["type"] == "number":
            if isinstance(value, (bool, float)) or not isinstance(
                value, (str, int, Decimal)
            ):
                raise ValueError(f"{definition['id']}.{key} must be a decimal string")
            try:
                value = Decimal(value)
            except InvalidOperation as exc:
                raise ValueError(f"Invalid decimal parameter {key}") from exc
            if not value.is_finite():
                raise ValueError(f"Non-finite decimal parameter {key}")
        elif (
            not isinstance(value, str)
            or len(value) != 3
            or not value.isascii()
            or not value.isupper()
            or not value.isalpha()
        ):
            raise ValueError(
                f"{definition['id']}.{key} must be an uppercase three-letter currency code"
            )
        if "minimum" in spec and value < Decimal(str(spec["minimum"])):
            raise ValueError(f"{definition['id']}.{key} below minimum")
        if "maximum" in spec and value > Decimal(str(spec["maximum"])):
            raise ValueError(f"{definition['id']}.{key} above maximum")
        result[key] = value
    return result, missing


def _scope(dataset: dict, case: Case) -> tuple[dict, dict]:
    tables = dataset["tables"]
    scope = case.scope
    known = {e["entity_id"] for e in tables["entities"]}
    if set(scope.entity_ids) - known:
        raise ValueError("Scope refers to unknown entity IDs")
    date_to = min(scope.date_to, case.as_of) if scope.date_to else case.as_of

    def dated(row: dict) -> bool:
        value = row.get("date")
        if not value:
            return not (scope.date_from or scope.date_to)
        return (
            not scope.date_from or value >= scope.date_from.isoformat()
        ) and value <= date_to.isoformat()

    shipments = [
        s
        for s in tables.get("shipments", [])
        if dated(s)
        and (not scope.domains or s.get("domain") in scope.domains)
        and (
            not scope.entity_ids
            or s["exporter_id"] in scope.entity_ids
            or s.get("importer_id") in scope.entity_ids
        )
    ]
    shipment_ids = {s["shipment_id"] for s in shipments}
    payments = [
        p
        for p in tables.get("payments", [])
        if p["shipment_id"] in shipment_ids and dated(p)
    ]
    involved = {s["exporter_id"] for s in shipments} | {
        s["importer_id"] for s in shipments if s.get("importer_id")
    }
    entities = [
        e
        for e in tables["entities"]
        if (not scope.entity_ids or e["entity_id"] in scope.entity_ids)
        and (not scope.domains or e["entity_id"] in involved)
    ]
    result = {"entities": entities}
    if "shipments" in tables:
        result["shipments"] = shipments
    if "payments" in tables:
        result["payments"] = payments
    for table in ("ownership", "diligence"):
        if table in tables:
            result[table] = tables[table]
    counts = {}
    for table in ("entities", "shipments", "payments"):
        counts[f"{table}_total"] = len(tables.get(table, []))
        counts[f"{table}_in_scope"] = len(result.get(table, []))
        counts[f"{table}_excluded"] = (
            counts[f"{table}_total"] - counts[f"{table}_in_scope"]
        )
    counts["shipments_missing_date_total"] = sum(
        not s.get("date") for s in tables.get("shipments", [])
    )
    counts["payments_missing_date_total"] = sum(
        not p.get("date") for p in tables.get("payments", [])
    )
    return result, counts


def _refs(table: str, rows: list[dict]) -> list[dict]:
    return [{"table": table, "record_id": row[TABLES[table][1]]} for row in rows]


def _finding(
    iid: str,
    key: Any,
    title: str,
    observation: str,
    entities: list[str],
    refs: list[dict],
    metrics: dict,
    unknown: str,
    alternative: str,
    falsifier: str,
) -> dict:
    return {
        "finding_id": iid + "-" + sha256_bytes(canonical_json(key))[:24],
        "investigation_id": iid,
        "title": title,
        "observation": observation,
        "entity_ids": sorted(set(entities)),
        "record_refs": sorted(
            {(r["table"], r["record_id"]): r for r in refs}.values(),
            key=lambda r: (r["table"], r["record_id"]),
        ),
        "metrics": metrics,
        "unknowns": [unknown],
        "alternatives": [alternative],
        "falsifiers": [falsifier],
        "source_refs": [],
    }


def _month(day: str) -> int:
    parsed = date.fromisoformat(day)
    return parsed.year * 12 + parsed.month - 1


def _month_text(month: int) -> str:
    return f"{month // 12:04}-{month % 12 + 1:02}"


_CONTEXT_LABEL_FIELDS = frozenset({"address", "method", "unit", "broker", "domain"})
_CONTEXT_PLACEHOLDERS = frozenset(
    {
        "na",
        "n a",
        "unknown",
        "not provided",
        "not available",
        "not applicable",
        "none",
        "null",
        "tbd",
        "unspecified",
    }
)


def _usable_context(value: Any, field: str) -> bool:
    if not value:
        return False
    if not isinstance(value, str):
        return True
    normalized = normalized_name(value)
    if not normalized:
        return False
    # Sentinel handling is deliberately field-specific. NA is a valid country
    # code; invoice/commodity identifiers and entity names retain their meaning.
    # The case-sensitive SI unit nA (nanoampere) is also meaningful.
    return (
        field not in _CONTEXT_LABEL_FIELDS
        or (field == "unit" and value.strip() == "nA")
        or normalized not in _CONTEXT_PLACEHOLDERS
    )


def _execute(
    iid: str, tables: dict, params: dict, case: Case, watchlist: dict | None
) -> tuple[list[dict], int, list[str], str]:
    entities, shipments, payments = (
        tables.get(k, []) for k in ("entities", "shipments", "payments")
    )
    by_shipment = defaultdict(list)
    for payment in payments:
        by_shipment[payment["shipment_id"]].append(payment)
    shipment_map = {s["shipment_id"]: s for s in shipments}
    findings, limitations = [], []
    eligible = 0
    if iid in ("payment_fragmentation", "mixed_payment_methods", "threshold_cluster"):
        for shipment in shipments:
            linked = by_shipment[shipment["shipment_id"]]
            if iid == "mixed_payment_methods":
                linked = [
                    p for p in linked if _usable_context(p.get("method"), "method")
                ]
                methods = sorted({normalized_name(p["method"]) for p in linked})
                count, threshold = len(methods), params["minimum_methods"]
                metrics = {"known_methods": methods, "method_count": count}
            elif iid == "threshold_cluster":
                linked = [p for p in linked if p["ccy"] == params["currency"]]
                eligible += len(linked)
                low, high = (
                    params["threshold"] * params["lower_ratio"],
                    params["threshold"],
                )
                linked = [p for p in linked if low <= Decimal(p["amount"]) < high]
                count, threshold = len(linked), params["minimum_payments"]
                metrics = {
                    "payment_count": count,
                    "currency": params["currency"],
                    "lower_inclusive": str(low),
                    "upper_exclusive": str(high),
                }
            else:
                count, threshold = len(linked), params["minimum_payments"]
                metrics = {
                    "payment_count": count,
                    "totals_by_currency": {
                        ccy: str(
                            sum(
                                (
                                    Decimal(p["amount"])
                                    for p in linked
                                    if p["ccy"] == ccy
                                ),
                                Decimal(0),
                            )
                        )
                        for ccy in sorted({p["ccy"] for p in linked})
                    },
                }
            if iid != "threshold_cluster":
                eligible += len(linked)
            if count >= threshold:
                findings.append(
                    _finding(
                        iid,
                        shipment["shipment_id"],
                        "Linked payment pattern",
                        f"Shipment {shipment['shipment_id']} meets the chosen {iid.replace('_', ' ')} criterion with {count} qualifying records or methods.",
                        [shipment["exporter_id"]],
                        _refs("shipments", [shipment]) + _refs("payments", linked),
                        metrics,
                        "Contract terms, payment purpose, and whether entries are duplicate ledger records remain unverified.",
                        "Ordinary installments, fees, payment service constraints, or corrections may explain this pattern.",
                        "Reconcile each payment to the contract and ledger; documented schedules or duplicates can explain the observation.",
                    )
                )
    elif iid == "shared_address":
        groups = defaultdict(list)
        for entity in entities:
            if _usable_context(entity.get("address"), "address") and entity.get(
                "country"
            ):
                eligible += 1
                key = tuple(
                    normalized_name(entity.get(k) or "")
                    for k in ("address", "city", "postal_code", "country")
                )
                groups[key].append(entity)
        for key, rows in groups.items():
            if len(rows) >= params["minimum_entities"]:
                findings.append(
                    _finding(
                        iid,
                        key,
                        "Shared supplied address",
                        f"{len(rows)} distinct entity IDs share the same normalized supplied full address.",
                        [r["entity_id"] for r in rows],
                        _refs("entities", rows),
                        {"entity_count": len(rows), "normalized_address": list(key)},
                        "Occupancy dates and any actual relationship between the entities are unknown.",
                        "Registered agents, multi-tenant buildings, and shared service offices can explain the address.",
                        "Confirm suite numbers, occupancy dates, and registries to distinguish a shared location from a substantive relationship.",
                    )
                )
    elif iid == "multi_domain":
        groups = defaultdict(list)
        for s in shipments:
            if _usable_context(s.get("domain"), "domain"):
                eligible += 1
                groups[s["exporter_id"]].append(s)
        for eid, rows in groups.items():
            domains = sorted({normalized_name(s["domain"]) for s in rows})
            if len(domains) >= params["minimum_domains"]:
                findings.append(
                    _finding(
                        iid,
                        eid,
                        "Activity across declared domains",
                        f"Exporter {eid} appears in {len(domains)} supplied shipment domains.",
                        [eid],
                        _refs("shipments", rows),
                        {"domains": domains, "domain_count": len(domains)},
                        "Product classification accuracy and business purpose remain unverified.",
                        "A diversified distributor may routinely supply multiple industries.",
                        "Compare actual product specifications and business records with the supplied domain labels.",
                    )
                )
    elif iid == "invoice_overlap":
        groups = defaultdict(list)
        for s in shipments:
            token = normalized_name(s.get("invoice_id") or "").replace(" ", "")
            if len(token) >= 4 and sum(c.isdigit() for c in token) >= 2:
                eligible += 1
                groups[token].append(s)
        for key, rows in groups.items():
            ids = sorted({s["exporter_id"] for s in rows})
            if len(ids) >= params["minimum_exporters"]:
                findings.append(
                    _finding(
                        iid,
                        key,
                        "Full invoice identifier reused across exporters",
                        f"The normalized full invoice identifier {key} occurs for {len(ids)} exporter IDs.",
                        ids,
                        _refs("shipments", rows),
                        {
                            "normalized_invoice": key,
                            "exporter_count": len(ids),
                            "shipment_count": len(rows),
                        },
                        "Invoice issuers, numbering systems, and original document authenticity are unverified.",
                        "Unrelated exporters or a shared accounting service may use overlapping invoice numbers.",
                        "Inspect complete original invoices, issuers, dates, and numbering policies to establish whether documents are related.",
                    )
                )
    elif iid == "weekend_shipments":
        for s in shipments:
            if s.get("date"):
                eligible += 1
                if date.fromisoformat(s["date"]).weekday() >= 5:
                    findings.append(
                        _finding(
                            iid,
                            s["shipment_id"],
                            "Weekend-dated shipment record",
                            f"Shipment {s['shipment_id']} is dated {s['date']}, a weekend calendar day.",
                            [s["exporter_id"]],
                            _refs("shipments", [s]),
                            {
                                "date": s["date"],
                                "weekday": date.fromisoformat(s["date"]).strftime("%A"),
                            },
                            "The meaning of the supplied date and local operating calendar are unknown.",
                            "Ports and logistics providers commonly operate on weekends.",
                            "Confirm whether the date represents a physical movement, document creation, or an administrative posting.",
                        )
                    )
    elif iid == "broker_concentration":
        groups = defaultdict(list)
        for p in payments:
            if _usable_context(p.get("broker"), "broker") and shipment_map[
                p["shipment_id"]
            ].get("importer_id"):
                eligible += 1
                groups[normalized_name(p["broker"])].append(p)
        for broker, rows in groups.items():
            linked = [shipment_map[p["shipment_id"]] for p in rows]
            pairs = sorted({(s["exporter_id"], s["importer_id"]) for s in linked})
            if len(pairs) >= params["minimum_pairs"]:
                findings.append(
                    _finding(
                        iid,
                        broker,
                        "Broker label links multiple counterparties",
                        f"Broker label {broker} occurs across {len(pairs)} distinct exporter/importer pairs.",
                        [eid for pair in pairs for eid in pair],
                        _refs("payments", rows) + _refs("shipments", linked),
                        {
                            "broker_label": broker,
                            "counterparty_pairs": [list(pair) for pair in pairs],
                            "pair_count": len(pairs),
                        },
                        "The broker's legal identity, contracts, and wider customer base are unverified.",
                        "A large legitimate intermediary may serve many independent counterparties.",
                        "Verify broker identities and mandates, then compare against its normal customer and transaction profile.",
                    )
                )
    elif iid == "unit_price_outlier":
        cohorts = defaultdict(list)
        missing, mixed = 0, 0
        for s in shipments:
            linked = by_shipment[s["shipment_id"]]
            currencies = {p["ccy"] for p in linked}
            commodity = (
                ("commodity", s["commodity_code"])
                if normalized_name(s.get("commodity_code") or "")
                else ("hs", s.get("hs_code"))
            )
            if len(currencies) > 1:
                mixed += 1
                continue
            if (
                not linked
                or not s.get("qty")
                or not _usable_context(s.get("unit"), "unit")
                or not commodity[1]
            ):
                missing += 1
                continue
            # SI unit case changes magnitude (for example, mg and Mg). Avoid
            # conflating units unless a future explicit conversion maps them.
            key = (next(iter(currencies)), s["unit"].strip(), *commodity)
            price = sum((Decimal(p["amount"]) for p in linked), Decimal(0)) / Decimal(
                s["qty"]
            )
            cohorts[key].append((s, linked, price))
        limitations += [
            f"Excluded {missing} shipments without payment, quantity, unit, or commodity context; excluded {mixed} with mixed payment currencies."
        ]
        small = 0
        for key, rows in cohorts.items():
            if len(rows) < params["minimum_cohort"]:
                small += len(rows)
                continue
            eligible += len(rows)
            center = median([r[2] for r in rows])
            all_refs = _refs("shipments", [r[0] for r in rows]) + _refs(
                "payments", [p for r in rows for p in r[1]]
            )
            for shipment, linked, price in rows:
                ratio = price / center
                if ratio >= params["high_ratio"] or ratio <= params["low_ratio"]:
                    findings.append(
                        _finding(
                            iid,
                            shipment["shipment_id"],
                            "Comparable paid-value outlier",
                            f"Shipment {shipment['shipment_id']} has paid value per unit {price}, compared with the true cohort median {center} across {len(rows)} comparable records.",
                            [shipment["exporter_id"]],
                            all_refs,
                            {
                                "shipment_id": shipment["shipment_id"],
                                "paid_value_per_unit": str(price),
                                "cohort_median": str(center),
                                "ratio_to_median": str(ratio),
                                "cohort_size": len(rows),
                                "currency": key[0],
                                "unit": key[1],
                                "commodity_kind": key[2],
                                "commodity_code": key[3],
                            },
                            "Product quality, contract terms, payment completeness, freight, and tax treatment remain unknown.",
                            "Different specifications, prepayments, partial settlements, or data errors may explain the value.",
                            "Reconcile original contracts, quantities, currency, full payment schedules, and comparable product specifications.",
                        )
                    )
        limitations.append(
            f"Excluded {small} shipments in cohorts smaller than minimum_cohort."
        )
    elif iid == "volume_spike":
        evaluated_ids = set()
        evaluated_windows = 0
        dated = [s for s in shipments if s.get("date")]
        if dated:
            first = min(_month(s["date"]) for s in dated)
            last = (
                _month(
                    min(case.scope.date_to, case.as_of).isoformat()
                    if case.scope.date_to
                    else case.as_of.isoformat()
                )
                - 1
            )
            if case.scope.date_from:
                # A partially observed first month cannot serve as a complete baseline month.
                first = max(
                    first,
                    _month(case.scope.date_from.isoformat())
                    + (case.scope.date_from.day != 1),
                )
            groups = defaultdict(list)
            for s in dated:
                groups[s["exporter_id"]].append(s)
            for eid, rows in groups.items():
                counts = Counter(_month(s["date"]) for s in rows)
                for month in range(first + params["window_months"], last + 1):
                    history = list(range(month - params["window_months"], month))
                    prior = sum(counts[m] for m in history)
                    if prior < params["minimum_prior_shipments"]:
                        continue
                    evaluated_windows += 1
                    evaluated_ids.update(
                        s["shipment_id"]
                        for s in rows
                        if history[0] <= _month(s["date"]) <= month
                    )
                    current = counts[month]
                    mean = Decimal(prior) / params["window_months"]
                    ratio = Decimal(current) / mean
                    if (
                        current >= params["minimum_current_shipments"]
                        and ratio >= params["minimum_ratio"]
                    ):
                        cited = [
                            s for s in rows if history[0] <= _month(s["date"]) <= month
                        ]
                        findings.append(
                            _finding(
                                iid,
                                [eid, month],
                                "Monthly shipment count increase",
                                f"Exporter {eid} has {current} records in {_month_text(month)}, compared with a mean of {mean} over the prior {len(history)} months.",
                                [eid],
                                _refs("shipments", cited),
                                {
                                    "month": _month_text(month),
                                    "current_count": current,
                                    "prior_month_counts": {
                                        _month_text(m): counts[m] for m in history
                                    },
                                    "prior_mean": str(mean),
                                    "ratio": str(ratio),
                                },
                                "Whether the imported history is complete and what caused the volume change are unknown.",
                                "Seasonality, a new contract, business growth, or a change in data coverage may explain the increase.",
                                "Compare with complete transaction records, seasonal baselines, new contracts, and changes in source coverage.",
                            )
                        )
        eligible = len(evaluated_ids)
        limitations.append(
            f"Evaluated {evaluated_windows} exporter/month windows with sufficient baseline history."
        )
    elif iid == "screening_candidates":
        if watchlist is None:
            return (
                [],
                0,
                [],
                "An explicitly selected official-list snapshot is required.",
            )
        if case.watchlist_snapshot_id != watchlist.get("snapshot_id"):
            raise ValueError("Case snapshot ID differs from supplied watchlist")
        if len(entities) * len(watchlist["entries"]) > 20_000_000:
            return (
                [],
                0,
                [],
                "Screening exceeds 20 million entity/list comparisons; narrow entity scope and run additional cases.",
            )
        findings, counts = candidate_findings(entities, watchlist, case.as_of, **params)
        if counts["candidate_output_limit_exceeded"]:
            return (
                [],
                0,
                [
                    "Screening stopped before completing all entity comparisons; no partial candidate findings are returned."
                ],
                f"At least {counts['candidate_count_at_least']} candidates exceed the supported screening output limit of {counts['candidate_output_limit']}. Narrow entity scope and run additional cases; if one entity exceeds the limit, review the selected official source directly.",
            )
        eligible = (
            counts["entities_considered"] if counts["source_records_considered"] else 0
        )
        limitations += [
            f"Compared against {counts['source_records_considered']} source records; excluded {counts['source_records_excluded_by_dates']} outside explicit effective dates.",
            f"Retained {counts['candidates_retained_exact_or_identifier']} exact normalized-name or typed-identifier candidates, {counts['candidates_retained_approximate']} approximate-name candidates, and {counts['candidates_retained_transliterated']} romanization candidates; no qualifying candidates were omitted.",
            "Supplementary cross-script matching uses exact normalized modern Russian ALA-LC romanization only. It does not translate names, infer language, cover all Cyrillic alphabets or transliteration variants, or resolve identity. Supply authoritative aliases for other forms.",
        ]
        if counts["source_records_with_inconsistent_dates"]:
            limitations.append(
                f"{counts['source_records_with_inconsistent_dates']} source records have an end date before their start date. "
                "Their names and identifiers were compared, but applicability on the case's as-of date cannot be evaluated. "
                "Matching candidates retain both supplied dates and an explicit inconsistency flag."
            )
        if counts["entities_without_usable_identity"]:
            limitations.append(
                f"Excluded {counts['entities_without_usable_identity']} entity records without a usable name, alias, or supported identifier."
            )
        if not counts["source_records_considered"]:
            return (
                findings,
                0,
                limitations,
                "No source records remain within the case's effective-date scope; no identity comparisons were performed.",
            )
        updated = str(watchlist.get("metadata", {}).get("source_updated_at") or "")[:10]
        try:
            age = (case.as_of - date.fromisoformat(updated)).days
            if age > 7:
                limitations.append(
                    f"Source publication/aggregation date precedes case as-of date by {age} days; list changes may be missing."
                )
            elif age < 0:
                limitations.append(
                    "Snapshot publication/aggregation date follows case as-of date; historical membership is unestablished where effective dates are absent."
                )
        except ValueError:
            limitations.append(
                "Source publication/aggregation date is unavailable or unparseable."
            )
    elif iid == "data_quality":
        fields = {
            "entities": ["name", "country", "address"],
            "shipments": [
                "date",
                "importer_id",
                "qty",
                "unit",
                "hs_code",
                "invoice_id",
            ],
            "payments": ["date", "method"],
        }
        for table, names in fields.items():
            rows = tables.get(table, [])
            eligible += len(rows)
            for field in names:
                missing = [
                    row for row in rows if not _usable_context(row.get(field), field)
                ]
                unusable = sum(bool(row.get(field)) for row in missing)
                if missing:
                    findings.append(
                        _finding(
                            iid,
                            [table, field],
                            "Missing analytical context",
                            (
                                f"{len(missing)} of {len(rows)} in-scope {table} records lack {field}."
                                if not unusable
                                else f"{len(missing)} of {len(rows)} in-scope {table} records have missing or unusable {field} values."
                            ),
                            [],
                            _refs(table, rows),
                            {
                                "table": table,
                                "field": field,
                                "missing_count": len(missing),
                                "record_count": len(rows),
                                **({"unusable_count": unusable} if unusable else {}),
                            },
                            "Missing values may reflect unavailable information, incomplete extraction, or a field that does not apply.",
                            "Source systems may store the same context in documents or separate records.",
                            "Inspect the original source and document whether the missing field can be recovered or is legitimately inapplicable.",
                        )
                    )
    label_fields = {
        "shared_address": (entities, "address"),
        "mixed_payment_methods": (payments, "method"),
        "broker_concentration": (payments, "broker"),
        "multi_domain": (shipments, "domain"),
        "unit_price_outlier": (shipments, "unit"),
    }
    if iid in label_fields:
        rows, field = label_fields[iid]
        unusable = sum(
            bool(row.get(field)) and not _usable_context(row[field], field)
            for row in rows
        )
        if unusable:
            limitations.append(
                f"Excluded {unusable} records with unusable {field} labels: placeholder values or no letters or digits."
            )
    return (
        findings,
        eligible,
        limitations,
        (
            ""
            if eligible
            else "No records satisfy this investigation's data prerequisites within scope."
        ),
    )


def _analyze(dataset: dict, case: dict, watchlist: dict | None = None) -> dict:
    parsed = Case.model_validate(case)
    if dataset.get("metadata", {}).get("dataset_id") != parsed.dataset_id:
        raise ValueError("Case dataset ID differs from supplied dataset")
    definitions = {d["id"]: d for d in catalog()}
    unknown = set(parsed.investigations) - set(definitions)
    if unknown:
        raise ValueError("Unknown investigations: " + ", ".join(sorted(unknown)))
    scoped, counts = _scope(dataset, parsed)
    findings, coverage = [], []
    warnings = [
        "Observations identify records for review; they do not establish wrongdoing, identity equivalence, or legal obligations."
    ]
    if dataset["metadata"].get("synthetic"):
        warnings.append("All transaction data in this dataset is explicitly synthetic.")
    if counts["shipments_missing_date_total"] or counts["payments_missing_date_total"]:
        warnings.append(
            "Undated records remain eligible only when no explicit date range is selected; date-based investigations still exclude them. Future-dated records are always excluded by as_of."
        )
    for iid in parsed.investigations:
        definition = definitions[iid]
        params, missing_params = _parameters(parsed, definition)
        missing_tables = [
            table for table in definition["required_tables"] if table not in scoped
        ]
        if missing_tables or missing_params:
            rows, count, extra, reason = (
                [],
                0,
                [],
                "Missing "
                + "; ".join(
                    filter(
                        None,
                        [
                            (
                                "tables: " + ", ".join(missing_tables)
                                if missing_tables
                                else ""
                            ),
                            (
                                "parameters: " + ", ".join(missing_params)
                                if missing_params
                                else ""
                            ),
                        ],
                    )
                ),
            )
        else:
            rows, count, extra, reason = _execute(
                iid, scoped, params, parsed, watchlist
            )
        findings.extend(rows)
        coverage.append(
            {
                "investigation_id": iid,
                "status": "not_evaluable" if reason else "executed",
                "records_evaluated": count,
                "findings_count": len(rows),
                "reason": reason,
                "limitations": definition["limitations"] + extra,
            }
        )
    findings.sort(key=lambda f: (f["investigation_id"], f["finding_id"]))
    return Analysis.model_validate(
        {
            "findings": findings,
            "coverage": coverage,
            "scope_counts": counts,
            "warnings": warnings,
        }
    ).model_dump(mode="json")


def analyze(dataset: dict, case: dict, watchlist: dict | None = None) -> dict:
    """Use a fixed decimal context, independent of the caller's thread settings."""
    with localcontext(Context(prec=60, rounding=ROUND_HALF_EVEN)):
        return _analyze(dataset, case, watchlist)

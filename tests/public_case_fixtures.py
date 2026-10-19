"""Frozen public-record extracts and predeclared labels; never browser content.

These are historical candidate-generation tests, not current screening lists or
findings about a transaction. Controls explicitly identify invented changes.
The labels were fixed before evaluating the engine against this corpus.
"""

from copy import deepcopy

RETRIEVED_DATE = "2026-10-18"
SOURCES = {
    "ofac-suex-20210921": {
        "url": "https://ofac.treasury.gov/recent-actions/20210921",
        "published_date": "2021-09-21",
        "retrieved_date": RETRIEVED_DATE,
        "html_sha256": "d7ee65d3f596e623dfbbd17010813819658614284d8e0886dd654493cb0dc547",
    },
    "ofac-chatex-20211108": {
        "url": "https://ofac.treasury.gov/recent-actions/20211108",
        "published_date": "2021-11-08",
        "retrieved_date": RETRIEVED_DATE,
        "html_sha256": "e96db63df07d37684286d58eaa7fbd1b31cf7f1b01ef85773c445ad5b3ca1968",
    },
    "bis-seagate-20230419": {
        "url": "https://www.bis.gov/node/20250",
        "published_date": "2023-04-19",
        "retrieved_date": RETRIEVED_DATE,
        "html_sha256": "827a585b05e906968863741d9bac99491de2eb417d3e0a472e934644b5264431",
    },
    "ofac-faq-5": {
        "url": "https://ofac.treasury.gov/faqs/5",
        "published_date": "2015-01-30",
        "updated_date": "2026-09-09",
        "retrieved_date": RETRIEVED_DATE,
        "html_sha256": "f9101c03eb7d8790093e1c66edb2924ee8503463a7e7cfd6f9e6226b527e199f",
    },
    "bis-kyc": {
        "url": "https://www.bis.gov/node/1533",
        "published_date": None,
        "retrieved_date": RETRIEVED_DATE,
        "html_sha256": "caff78e36efbfab6de176fb79077106bac17cba4be8df3200dd6526fa5d774d1",
    },
}

# IDs below are corpus-local locators, not invented OFAC unique identifiers.
# Only factual fields needed by these tests are copied; this is not a full list.
RECORDS = [
    {
        "record_id": "suex",
        "name": "SUEX OTC, S.R.O.",
        "aliases": ["SUCCESSFUL EXCHANGE"],
        "countries": ["CZ", "RU"],
        "identifiers": [
            {"idType": "Company Number", "idNumber": "07486049"},
            {"idType": "Legal Entity Number", "idNumber": "5299007NTWCC3U23WM81"},
        ],
        "source_document": "ofac-suex-20210921",
    },
    {
        "record_id": "chatex",
        "name": "CHATEX",
        "countries": ["EE", "LV", "VC"],
        "source_document": "ofac-chatex-20211108",
    },
    {
        "record_id": "chatextech",
        "name": "CHATEXTECH SIA",
        "countries": ["LV"],
        "identifiers": [
            {"idType": "V.A.T. Number", "idNumber": "LV40203285832"},
            {"idType": "Registration Number", "idNumber": "40203285832"},
        ],
        "source_document": "ofac-chatex-20211108",
    },
    {
        "record_id": "hightrade",
        "name": "HIGHTRADE FINANCE LTD",
        "countries": ["VC"],
        "identifiers": [
            {"idType": "Registration Number", "idNumber": "23905 IBC 2017"}
        ],
        "source_document": "ofac-chatex-20211108",
    },
    {
        "record_id": "izibits",
        "name": "IZIBITS OU",
        "aliases": ["IZIBITS OÜ"],
        "countries": ["EE"],
        "identifiers": [{"idType": "Registration Number", "idNumber": "14407679"}],
        "source_document": "ofac-chatex-20211108",
    },
    {
        "record_id": "southfront",
        "name": "SOUTHFRONT",
        "aliases": ["SOUTH FRONT", "SOUTHFRONT: ANALYSIS & INTELLIGENCE"],
        "countries": ["RU"],
        "source_document": "ofac-chatex-20211108",
    },
]


def snapshot():
    return {
        "snapshot_id": "public-ofac-extract-2021",
        "source_id": "ofac_sdn",
        "metadata": {
            "source_updated_at": "2021-11-08",
            "ingestion_method": "manual_public_extract",
            "warnings": [
                "Historical, partial test extract; not a current screening list."
            ],
        },
        "entries": [
            {
                "source_row": index + 1,
                "list_name": "OFAC historical public-action extract",
                "entity_type": "Entity",
                **deepcopy(record),
            }
            for index, record in enumerate(RECORDS)
        ],
    }


def public_case_suite():
    cases = []

    def add(
        case_id,
        subject,
        record_id,
        rationale,
        *,
        input_kind="source_extract",
        source=None,
    ):
        cases.append(
            {
                "id": case_id,
                "check": "screening_candidates",
                "kind": "contract",
                "rationale": rationale,
                "expected_coverage": "executed",
                "provenance": {"input_kind": input_kind},
                "tables": {"entities": [{"entity_id": "E1", **subject}]},
                "watchlist": deepcopy(source if source is not None else snapshot()),
                "case": {
                    "as_of": "2021-11-08",
                    "watchlist_snapshot_id": "public-ofac-extract-2021",
                    "question": "Which retained historical list record is a candidate for this supplied name or typed identifier?",
                },
                "targets": [
                    {
                        "unit": "E1|" + record["record_id"],
                        "positive": record["record_id"] == record_id,
                    }
                    for record in RECORDS
                ],
            }
        )

    for record in RECORDS:
        subject = {"name": record["name"], "country": record["countries"][0]}
        add(
            "canonical-" + record["record_id"],
            subject,
            record["record_id"],
            "The exact published organization name must retrieve its own extracted record. Other extracted organizations are pairwise negative candidates, not cleared parties.",
        )
        for index, alias in enumerate(record.get("aliases", [])):
            add(
                f"published-alias-{record['record_id']}-{index + 1}",
                {"name": alias},
                record["record_id"],
                "The official announcement explicitly associates this alternate name or Latin spelling with this record; the relationship is not inferred from engine output.",
            )

    for record_id, field, value in (
        ("suex", "registration_id", "07486049"),
        ("suex", "lei", "5299007NTWCC3U23WM81"),
        ("chatextech", "registration_id", "40203285832"),
        ("hightrade", "registration_id", "23905 IBC 2017"),
        ("izibits", "registration_id", "14407679"),
    ):
        add(
            f"published-identifier-{record_id}-{field}",
            {"name": "Account requiring identification", field: value},
            record_id,
            "The typed identifier is copied from the official organization record. The display name is an explicit test placeholder, withholding name similarity so this measures identifier retrieval alone.",
            input_kind="source_identifier_with_placeholder_name",
        )

    for case_id, name, target in (
        ("normalized-punctuation", "suex otc s r o", "suex"),
        ("normalized-token-order", "FINANCE HIGHTRADE LTD", "hightrade"),
    ):
        add(
            case_id,
            {"name": name},
            target,
            "A constructed formatting variation of a published name must retain the same candidate; the variation is not represented as a separately published alias.",
            input_kind="constructed_formatting_control",
        )
    add(
        "conflicting-country",
        {"name": "SUEX OTC, S.R.O.", "country": "US"},
        "suex",
        "An intentionally conflicting country must be shown as a conflict, not suppress the exact-name candidate. This does not assert that a U.S. entity with this identity exists.",
        input_kind="constructed_conflict_control",
    )
    for kind in ("Passport", "Tax ID No."):
        changed = snapshot()
        changed["entries"][0]["identifiers"] = [
            {"idType": kind, "idNumber": "07486049"}
        ]
        add(
            "unrelated-identifier-type-"
            + ("passport" if kind == "Passport" else "tax"),
            {"name": "Account requiring identification", "registration_id": "07486049"},
            None,
            "The source identifier type is deliberately replaced for this negative control. Identical digits in an unrelated identifier namespace cannot establish a registration-ID candidate.",
            input_kind="constructed_identifier_namespace_control",
            source=changed,
        )
    unavailable = deepcopy(cases[0])
    unavailable.update(
        id="missing-required-source",
        rationale="The published exact name remains a positive retrieval target, but screening without a selected source must be unavailable, never a completed negative.",
        expected_coverage="not_evaluable",
        provenance={"input_kind": "constructed_unavailable_control"},
    )
    unavailable.pop("watchlist")
    unavailable["case"].pop("watchlist_snapshot_id")
    cases.append(unavailable)
    return {
        "schema_version": "1.0",
        "suite_id": "public-record-candidate-validation-v1",
        "synthetic": False,
        "provenance": {
            "corpus_id": "official-public-record-extracts-2026-10-18-v1",
            "label_provenance": "Labels were fixed before engine evaluation by a software review agent from the retained official record relationships. Includes explicitly identified constructed controls. No independent practitioner adjudication.",
            "scope": "Historical organization-name, alias and typed-identifier candidate retrieval against six extracted OFAC records. No sanctions-status, identity, wrongdoing, clearance or population-accuracy labels.",
        },
        "source_documents": deepcopy(SOURCES),
        "cases": cases,
    }


def seagate_coverage_case():
    """A public case summary supplies no individual transaction rows to analyze."""
    return {
        "source_document": "bis-seagate-20230419",
        "tables": {
            "entities": [
                {
                    "entity_id": "seagate-us",
                    "name": "Seagate Technology LLC",
                    "country": "US",
                },
                {
                    "entity_id": "seagate-sg",
                    "name": "Seagate Singapore International Headquarters Pte. Ltd.",
                    "country": "SG",
                },
                {
                    "entity_id": "huawei",
                    "name": "Huawei Technologies Co. Ltd.",
                    "country": "CN",
                },
            ]
        },
        "case": {
            "case_id": "public-seagate-coverage",
            "dataset_id": "public-coverage",
            "question": "Which transaction checks can be evaluated from the named organizations alone?",
            "as_of": "2023-04-19",
            "investigations": [
                "payment_fragmentation",
                "mixed_payment_methods",
                "threshold_cluster",
                "unit_price_outlier",
                "invoice_overlap",
                "broker_concentration",
                "volume_spike",
                "weekend_shipments",
            ],
        },
        "expected": "All eight transaction checks are unavailable. A published enforcement outcome does not supply transaction rows or make these heuristics a legal classifier.",
    }

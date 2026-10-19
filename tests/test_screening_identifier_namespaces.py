"""Explicit official organization ID types cannot spill into unrelated namespaces."""

from datetime import date

import pytest

from omphalos.screening import candidate_findings


def evaluate(kind, *, field="registration_id", number="07486049"):
    return candidate_findings(
        [{"entity_id": "E1", "name": "Unidentified customer", field: number}],
        {
            "snapshot_id": "synthetic",
            "source_id": "ofac_sdn",
            "entries": [
                {
                    "record_id": "L1",
                    "name": "Different Official Name",
                    "list_name": "Synthetic list",
                    "identifiers": [{"idType": kind, "idNumber": number}],
                }
            ],
        },
        date(2026, 10, 1),
    )[0]


@pytest.mark.parametrize(
    "kind",
    [
        "registration",
        "Registration ID",
        "Registration Number",
        "Company Number",
        "Company Registration Number",
        "Business Registration Number",
        "Commercial Registry Number",
        "  COMPANY  NUMBER ",
    ],
)
def test_explicit_company_registration_types_are_candidates(kind):
    findings = evaluate(kind)
    assert len(findings) == 1
    metrics = findings[0]["metrics"]
    assert metrics["candidate_selection"] == "typed_identifier"
    assert metrics["identifier_matches"] == [
        {"field": "registration_id", "source_type": kind, "value": "07486049"}
    ]


@pytest.mark.parametrize(
    "kind",
    [
        "LEI",
        "Legal Entity Identifier",
        "Legal Entity Identifier (LEI)",
        "Legal Entity Number",
    ],
)
def test_explicit_lei_types_are_candidates(kind):
    findings = evaluate(kind, field="lei", number="5299007NTWCC3U23WM81")
    assert len(findings) == 1
    assert findings[0]["metrics"]["identifier_matches"][0]["field"] == "lei"
    assert findings[0]["metrics"]["identifier_matches"][0]["source_type"] == kind


@pytest.mark.parametrize(
    "kind",
    [
        "Passport",
        "Tax ID",
        "Tax Registration Number",
        "Alien Registration Number",
        "Aircraft Registration",
        "Vehicle Registration Number",
        "Registration Plate",
        "National ID",
        "V.A.T. Number",
        "Digital Currency Address - XBT",
        "Unknown Legal Entity Identifier Format",
        "LEI or Company Number",
        "Registration Number or Passport",
        "",
    ],
)
def test_unknown_or_ambiguous_types_cannot_match_equal_corporate_digits(kind):
    assert evaluate(kind) == []
    assert evaluate(kind, field="lei", number="5299007NTWCC3U23WM81") == []


def test_supported_namespaces_do_not_cross_match_one_another():
    assert evaluate("Company Number", field="lei", number="5299007NTWCC3U23WM81") == []
    assert (
        evaluate(
            "Legal Entity Number",
            field="registration_id",
            number="5299007NTWCC3U23WM81",
        )
        == []
    )

"""Unusable identity input is not an exact match or a completed comparison."""

from copy import deepcopy
from datetime import date

import pytest
from test_investigations import case, dataset

from omphalos.investigations import analyze
from omphalos.screening import candidate_findings
from omphalos.workflow import plan_case


def snapshot(*entries):
    return {
        "source_id": "csl",
        "snapshot_id": "fixture",
        "metadata": {
            "source_updated_at": "2026-10-13",
            "ingestion_method": "manual_import",
        },
        "entries": [
            {
                "record_id": f"source-{index}",
                "source_row": index + 1,
                "list_name": "Synthetic test list",
                **entry,
            }
            for index, entry in enumerate(entries)
        ],
    }


@pytest.mark.parametrize(
    "source_id,subject_id", [("---", "???"), ("", "---"), ("…", "—")]
)
def test_empty_normalized_identifiers_cannot_create_matches(source_id, subject_id):
    source = snapshot(
        {
            "name": "Harbor Instruments",
            "identifiers": [{"type": "Registration Number", "number": source_id}],
        }
    )
    subject = {
        "entity_id": "E1",
        "name": "Unrelated Orchard",
        "registration_id": subject_id,
    }
    retained = deepcopy((source, subject))
    findings, _ = candidate_findings([subject], source, date(2026, 10, 13))
    assert findings == []
    assert (source, subject) == retained


def test_name_match_does_not_claim_punctuation_identifiers_corroborate_it():
    source = snapshot(
        {
            "name": "Harbor Instruments",
            "identifiers": [{"type": "Registration Number", "number": "---"}],
        }
    )
    findings, _ = candidate_findings(
        [{"entity_id": "E1", "name": "Harbor Instruments", "registration_id": "???"}],
        source,
        date(2026, 10, 13),
    )
    assert len(findings) == 1
    assert findings[0]["metrics"]["identifier_matches"] == []
    assert findings[0]["metrics"]["identifier_comparisons"] == []


@pytest.mark.parametrize("source_id,subject_id", [("A-123", "A123"), ("NA", "NA")])
def test_real_identifiers_still_match_without_name_similarity(source_id, subject_id):
    source = snapshot(
        {
            "name": "Harbor Instruments",
            "identifiers": [{"type": "Registration Number", "number": source_id}],
        }
    )
    findings, counts = candidate_findings(
        [{"entity_id": "E1", "name": "!!!", "registration_id": subject_id}],
        source,
        date(2026, 10, 13),
    )
    assert counts["entities_considered"] == 1
    assert len(findings) == 1 and findings[0]["metrics"]["identifier_matches"]


def test_no_usable_identity_is_not_reported_as_screened_or_runnable():
    records = dataset(
        {"entities": [{"entity_id": "E1", "name": "???", "registration_id": "---"}]}
    )
    source = snapshot({"name": "Harbor Instruments"})
    result = analyze(
        records,
        case("screening_candidates", "data_quality", watchlist_snapshot_id="fixture"),
        source,
    )
    coverage = result["coverage"][0]
    assert coverage["status"] == "not_evaluable" and coverage["records_evaluated"] == 0
    assert any(
        "1 entity records without a usable name" in item
        for item in coverage["limitations"]
    )
    assert any(
        f["metrics"].get("field") == "name" and f["metrics"]["unusable_count"] == 1
        for f in result["findings"]
    )
    plan = plan_case(
        records, "counterparty_screening", as_of="2026-10-13", snapshot=source
    )
    assert plan["can_run"] is False
    screening = next(
        check
        for check in plan["unavailable_checks"]
        if check["id"] == "screening_candidates"
    )
    assert "usable name" in screening["reason"]


def test_usable_alias_and_identifier_keep_subjects_eligible_with_precise_coverage():
    records = dataset(
        {
            "entities": [
                {"entity_id": "E1", "name": "???", "registration_id": "---"},
                {"entity_id": "E2", "name": "???", "aliases": ["Harbor Instruments"]},
                {"entity_id": "E3", "name": "!!!", "registration_id": "A-123"},
            ]
        }
    )
    source = snapshot(
        {
            "name": "Harbor Instruments",
            "identifiers": [{"type": "Registration Number", "number": "A123"}],
        }
    )
    result = analyze(
        records, case("screening_candidates", watchlist_snapshot_id="fixture"), source
    )
    assert result["coverage"][0]["records_evaluated"] == 2
    assert {tuple(f["entity_ids"]) for f in result["findings"]} == {("E2",), ("E3",)}
    plan = plan_case(
        records, "counterparty_screening", as_of="2026-10-13", snapshot=source
    )
    assert plan["can_run"] is True
    assert plan["selected_checks"][0]["records_evaluated"] == 2


def test_all_source_rows_outside_date_scope_does_not_complete_screening():
    records = dataset({"entities": [{"entity_id": "E1", "name": "Harbor Instruments"}]})
    source = snapshot(
        {"name": "Harbor Instruments", "start_date": "2030-01-01"},
        {"name": "Harbor Instruments", "end_date": "2020-01-01"},
    )
    result = analyze(
        records, case("screening_candidates", watchlist_snapshot_id="fixture"), source
    )
    assert result["findings"] == []
    assert result["coverage"][0]["status"] == "not_evaluable"
    assert result["coverage"][0]["records_evaluated"] == 0
    assert "no identity comparisons" in result["coverage"][0]["reason"]
    plan = plan_case(
        records, "counterparty_screening", as_of="2026-10-13", snapshot=source
    )
    assert plan["can_run"] is False
    screening = next(
        check
        for check in plan["unavailable_checks"]
        if check["id"] == "screening_candidates"
    )
    assert "effective-date scope" in screening["reason"]

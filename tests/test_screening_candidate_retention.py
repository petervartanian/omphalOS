"""Presentation limits cannot conceal qualifying identity candidates."""

from datetime import date

from omphalos.screening import candidate_findings


def evaluate(entries, *, limit=1, subject=None):
    return candidate_findings(
        [{"entity_id": "E1", "name": "Fictional Aster Instruments", **(subject or {})}],
        {
            "snapshot_id": "synthetic",
            "source_id": "csl",
            "entries": [
                {"record_id": f"L{i}", "list_name": f"Synthetic list {i}", **entry}
                for i, entry in enumerate(entries)
            ],
        },
        date(2026, 10, 1),
        max_candidates=limit,
    )


def test_all_exact_names_survive_even_when_list_categories_differ():
    findings, counts = evaluate([{"name": "Fictional Aster Instruments"}] * 7)
    assert len(findings) == 7
    assert len({row["metrics"]["list_name"] for row in findings}) == 7
    assert counts["candidates_omitted_by_display_limit"] == 0
    assert counts["candidates_retained_exact_or_identifier"] == 7
    assert all(
        row["metrics"]["candidate_selection"] == "exact_normalized_name"
        for row in findings
    )
    assert all(row["metrics"]["candidates_for_entity"] == 7 for row in findings)


def test_all_typed_identifiers_survive_regardless_of_the_name_limit():
    findings, counts = evaluate(
        [
            {
                "name": "Different Name",
                "identifiers": [{"idType": "LEI", "idNumber": "12345678901234567890"}],
            }
        ]
        * 7,
        subject={"lei": "12345678901234567890"},
    )
    assert len(findings) == 7
    assert counts["candidates_retained_exact_or_identifier"] == 7
    assert all(
        row["metrics"]["candidate_selection"] == "typed_identifier" for row in findings
    )
    assert all(row["metrics"]["name_similarity"] != "1.0000" for row in findings)


def test_all_approximate_names_survive_legacy_limit_without_omissions():
    findings, counts = evaluate(
        [{"name": "Fictional Aster Instruments"}] * 2
        + [{"name": "Fictional Aster Instrument"}] * 4,
        limit=2,
    )
    assert len(findings) == 6
    assert counts["candidates_retained_exact_or_identifier"] == 2
    assert counts["candidates_omitted_by_display_limit"] == 0
    assert counts["candidates_retained_approximate"] == 4
    assert {row["source_refs"][0]["record_id"] for row in findings} == {
        "L0",
        "L1",
        "L2",
        "L3",
        "L4",
        "L5",
    }
    assert all(
        row["metrics"]["approximate_candidates_omitted_for_entity"] == 0
        for row in findings
    )
    assert all(row["metrics"]["candidates_for_entity"] == 6 for row in findings)


def test_exact_weak_alias_remains_a_candidate_with_its_qualification():
    findings, counts = evaluate(
        [
            {
                "name": "Different Name",
                "aliases": ["Fictional Aster Instruments"],
                "alias_details": [
                    {"name": "Fictional Aster Instruments", "quality": "weak"}
                ],
            }
        ]
        * 6
    )
    assert len(findings) == 6 and counts["candidates_omitted_by_display_limit"] == 0
    assert all(row["metrics"]["alias_quality"] == ["weak"] for row in findings)
    assert all("requires identity review" in row["observation"] for row in findings)


def test_output_bound_discards_partial_findings_before_allocating_oversized_entity(
    monkeypatch,
):
    import omphalos.screening as screening

    monkeypatch.setattr(screening, "MAX_RETAINED_CANDIDATES", 5)
    calls = []
    original_digest = screening.sha256_bytes

    def track_finding_allocation(raw):
        calls.append(raw)
        return original_digest(raw)

    monkeypatch.setattr(screening, "sha256_bytes", track_finding_allocation)
    findings, counts = evaluate([{"name": "Fictional Aster Instruments"}] * 6)
    assert findings == [] and calls == []
    assert counts["candidate_output_limit_exceeded"] is True
    assert counts["candidate_count_at_least"] == 6
    assert counts["candidate_output_limit"] == 5
    assert counts["candidates_retained_exact_or_identifier"] == 0


def test_output_bound_is_inclusive_and_across_entities(monkeypatch):
    import omphalos.screening as screening

    monkeypatch.setattr(screening, "MAX_RETAINED_CANDIDATES", 5)
    findings, counts = evaluate([{"name": "Fictional Aster Instruments"}] * 5)
    assert len(findings) == 5 and not counts["candidate_output_limit_exceeded"]
    snapshot = {
        "snapshot_id": "synthetic",
        "source_id": "csl",
        "entries": [
            {
                "record_id": f"L{i}",
                "list_name": "Synthetic list",
                "name": "Fictional Aster Instruments",
            }
            for i in range(3)
        ],
    }
    findings, counts = screening.candidate_findings(
        [
            {"entity_id": f"E{i}", "name": "Fictional Aster Instruments"}
            for i in range(4)
        ],
        snapshot,
        date(2026, 10, 1),
    )
    assert findings == []
    assert counts["candidate_output_limit_exceeded"]
    assert counts["candidate_count_at_least"] == 6
    assert counts["entities_considered"] == 2


def test_output_limit_becomes_unavailable_coverage_not_a_completed_negative(
    monkeypatch,
):
    import omphalos.screening as screening
    from omphalos.investigations import analyze

    monkeypatch.setattr(screening, "MAX_RETAINED_CANDIDATES", 5)
    snapshot = {
        "snapshot_id": "synthetic",
        "source_id": "csl",
        "entries": [
            {
                "record_id": f"L{i}",
                "list_name": "Synthetic list",
                "name": "Fictional Aster Instruments",
            }
            for i in range(6)
        ],
    }
    result = analyze(
        {
            "metadata": {"dataset_id": "synthetic"},
            "tables": {
                "entities": [{"entity_id": "E1", "name": "Fictional Aster Instruments"}]
            },
        },
        {
            "case_id": "synthetic",
            "question": "Which synthetic identity candidates need review?",
            "dataset_id": "synthetic",
            "as_of": "2026-10-01",
            "investigations": ["screening_candidates"],
            "watchlist_snapshot_id": "synthetic",
        },
        snapshot,
    )
    assert result["findings"] == []
    coverage = result["coverage"][0]
    assert coverage["status"] == "not_evaluable"
    assert coverage["records_evaluated"] == coverage["findings_count"] == 0
    assert "At least 6 candidates" in coverage["reason"]
    assert "limit of 5" in coverage["reason"]
    assert "Narrow entity scope" in coverage["reason"]
    assert any("no partial candidate" in value for value in coverage["limitations"])


def test_approximate_overflow_is_unavailable_instead_of_truncated(monkeypatch):
    import omphalos.screening as screening

    monkeypatch.setattr(screening, "MAX_RETAINED_CANDIDATES", 5)
    findings, counts = evaluate([{"name": "Fictional Aster Instrument"}] * 6, limit=1)
    assert findings == []
    assert counts["candidate_output_limit_exceeded"]
    assert counts["candidate_count_at_least"] == 6
    assert counts["candidates_retained_approximate"] == 0
    assert counts["candidates_omitted_by_display_limit"] == 0


def test_source_country_context_is_from_each_retained_record():
    findings, _ = evaluate(
        [
            {"name": "Fictional Aster Instruments", "countries": ["US"]},
            {"name": "Fictional Aster Instruments", "countries": ["GB"]},
        ],
        subject={"country": "US"},
    )
    assert [row["metrics"]["source_countries"] for row in findings] == [["US"], ["GB"]]
    assert [row["metrics"]["country_context"] for row in findings] == [
        "corroborates",
        "differs",
    ]


def test_legacy_candidate_parameter_is_explicitly_deprecated_for_clients():
    from omphalos.investigations import catalog

    spec = next(row for row in catalog() if row["id"] == "screening_candidates")
    assert spec["parameters"]["max_candidates"]["deprecated"] is True
    for limit in (1, 5, 100):
        findings, counts = evaluate(
            [{"name": "Fictional Aster Instrument"}] * 7, limit=limit
        )
        assert len(findings) == 7
        assert counts["candidates_omitted_by_display_limit"] == 0

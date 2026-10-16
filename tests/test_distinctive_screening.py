"""Corporate wording cannot conceal a different distinctive organization name."""

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from omphalos.screening import candidate_findings, name_score


def screen(subject, entries, *, minimum=Decimal("0.90")):
    snapshot = {
        "snapshot_id": "synthetic-list",
        "source_id": "csl",
        "entries": [
            {
                "record_id": f"record-{index}",
                "list_name": "Synthetic list fixture",
                **entry,
            }
            for index, entry in enumerate(entries)
        ],
    }
    return candidate_findings(
        [{"entity_id": "synthetic-subject", **subject}],
        snapshot,
        date(2026, 10, 15),
        minimum_score=minimum,
    )


@pytest.mark.parametrize(
    "left,right",
    [
        (
            "Aster Research and Production Association",
            "Orion Research and Production Association",
        ),
        (
            "Aster Scientific and Production Association",
            "Orion Scientific and Production Association",
        ),
        (
            "Вега Научно-производственное объединение",
            "Заря Научно-производственное объединение",
        ),
        (
            "AB Public Joint Stock Company",
            "XY Public Joint Stock Company",
        ),
    ],
)
def test_high_character_similarity_from_shared_organizational_wording_is_not_enough(
    left, right
):
    assert name_score(left, right) >= Decimal("0.90")
    # The protection also works when the imported/list record lacks a type.
    findings, counts = screen({"name": left}, [{"name": right}])
    assert findings == []
    assert counts["candidates_omitted_by_display_limit"] == 0


def test_distinctive_alias_matches_remain_and_raw_aliases_are_unchanged():
    subject = {
        "name": "Aster NPO",
        "entity_type": "organization",
        "aliases": [
            "Aster Research and Production Association",
            "AST-301",
            "НПО Астра",
        ],
    }
    entries = [
        {"name": "Orion Research and Production Association"},
        {"name": "Unrelated Primary Name", "aliases": ["AST-301"]},
        {"name": "НПО Астра"},
        {"name": "Aster NPO"},
    ]
    before_subject, before_entries = deepcopy(subject), deepcopy(entries)
    findings, _ = screen(subject, entries)
    assert {f["source_refs"][0]["record_id"] for f in findings} == {
        "record-1",
        "record-2",
        "record-3",
    }
    assert all(f["metrics"]["name_similarity"] == "1.0000" for f in findings)
    assert subject == before_subject and entries == before_entries
    assert any(f["metrics"]["entity_name_compared"] == "AST-301" for f in findings)


def test_similar_distinctive_spelling_and_reordered_tokens_still_compare():
    findings, _ = screen(
        {
            "name": "Northbridge Scientific and Production Association",
            "entity_type": "organization",
        },
        [{"name": "Northbridg Scientific and Production Association"}],
    )
    assert len(findings) == 1
    metrics = findings[0]["metrics"]
    assert metrics["entity_distinctive_name"] == "northbridge"
    assert metrics["source_distinctive_name"] == "northbridg"
    assert Decimal(metrics["name_similarity"]) >= Decimal("0.90")
    assert Decimal(metrics["full_name_similarity"]) > Decimal(
        metrics["name_similarity"]
    )
    assert "distinctive-name similarities" in metrics["name_comparison_method"]
    reordered, _ = screen(
        {"name": "Société Ágora Maritime Ltd", "entity_type": "organization"},
        [{"name": "Maritime Societe Agora Ltd"}],
    )
    assert reordered[0]["metrics"]["name_similarity"] == "1.0000"


def test_identifier_match_is_independent_and_reports_actual_name_scores():
    findings, _ = screen(
        {
            "name": "Aster Research and Production Association",
            "entity_type": "organization",
            "lei": "12345678901234567890",
        },
        [
            {
                "name": "Orion Research and Production Association",
                "identifiers": [{"idType": "LEI", "idNumber": "12345678901234567890"}],
            }
        ],
    )
    assert len(findings) == 1
    metrics = findings[0]["metrics"]
    assert metrics["identifier_matches"][0]["field"] == "lei"
    assert Decimal(metrics["name_similarity"]) < Decimal("0.90")
    assert Decimal(metrics["full_name_similarity"]) >= Decimal("0.90")
    assert (
        metrics["entity_name_compared"] == "Aster Research and Production Association"
    )
    assert (
        metrics["source_name_compared"] == "Orion Research and Production Association"
    )


def test_exact_primary_legal_name_is_retained_but_generic_alias_cannot_establish_match():
    exact, _ = screen(
        {"name": "Limited Liability Company", "entity_type": "organization"},
        [{"name": "LIMITED LIABILITY COMPANY"}],
    )
    assert len(exact) == 1 and exact[0]["metrics"]["name_similarity"] == "1.0000"
    alias, _ = screen(
        {"name": "Aster", "entity_type": "organization", "aliases": ["JSC"]},
        [{"name": "Orion", "aliases": ["JSC"]}],
    )
    assert alias == []


@pytest.mark.parametrize(
    "name",
    ["General Electric", "Bank of Example", "Research In Motion", "3M Company", "Co"],
)
def test_meaningful_names_and_known_person_comparison_are_not_blanket_stopwords(name):
    findings, _ = screen(
        {"name": name, "entity_type": "person" if name == "Co" else "organization"},
        [{"name": name, "entity_type": "Individual" if name == "Co" else "Entity"}],
    )
    assert len(findings) == 1
    assert findings[0]["metrics"]["name_similarity"] == "1.0000"


def test_no_transliteration_or_cross_script_identity_is_inferred():
    findings, _ = screen(
        {"name": "Москва НПО", "entity_type": "organization"}, [{"name": "Moskva NPO"}]
    )
    assert findings == []


@pytest.mark.parametrize("category", ["Individual", "Vessel", "Aircraft"])
def test_nonorganization_names_do_not_receive_inferred_corporate_stripping(category):
    findings, _ = screen(
        {"name": "Maya Co"}, [{"name": "May Co", "entity_type": category}]
    )
    assert len(findings) == 1
    assert findings[0]["metrics"]["name_similarity"] == "0.9231"
    assert (
        findings[0]["metrics"]["name_comparison_method"]
        == "Full normalized name comparison."
    )


def test_plausible_short_typo_survives_dampening_without_inflating_original_score():
    left, right = "Joint Stock Company Radiant", "Joint Stock Company Radient"
    findings, _ = screen(
        {"name": left, "entity_type": "organization"}, [{"name": right}]
    )
    assert len(findings) == 1
    metrics = findings[0]["metrics"]
    assert (
        Decimal("0.90")
        <= Decimal(metrics["name_similarity"])
        < Decimal(metrics["full_name_similarity"])
    )
    assert Decimal(metrics["distinctive_name_similarity"]) < Decimal("0.90")


def test_exact_token_order_match_is_preserved_with_asymmetric_phrase_stripping():
    findings, _ = screen(
        {
            "name": "Research and Production Association Orion",
            "entity_type": "organization",
        },
        [{"name": "Orion Association Production and Research"}],
    )
    assert len(findings) == 1
    assert findings[0]["metrics"]["name_similarity"] == "1.0000"


def test_adjusted_upper_bound_pruning_preserves_all_qualifying_pairs():
    from itertools import product

    from omphalos.screening import (
        _candidate_name_score,
        _organization_comparison,
        _prepare_candidate_name,
    )

    names = [
        "Aster Research and Production Association",
        "Orion Research and Production Association",
        "Joint Stock Company Radiant",
        "Joint Stock Company Radient",
        "Limited Liability Company",
        "Research and Production Association Orion",
        "Orion Association Production and Research",
        "AB Public Joint Stock Company",
        "XY Public Joint Stock Company",
        "НПО Астра",
        "НПО Вега",
    ]
    for left, right in product(names, names):
        a, b = (_prepare_candidate_name(value, primary=True) for value in (left, right))
        score = _candidate_name_score(
            a, b, _organization_comparison(a, b, True, False)
        )[0]
        assert score <= name_score(left, right)
        for threshold in map(Decimal, ("0.50", "0.70", "0.90", "1")):
            findings, _ = screen(
                {"name": left, "entity_type": "organization"},
                [{"name": right}],
                minimum=threshold,
            )
            assert bool(findings) == (score >= threshold), (
                left,
                right,
                score,
                threshold,
            )

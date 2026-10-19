"""Limited romanization retrieves candidates without altering identity records."""

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from omphalos.screening import candidate_findings, name_score


def evaluate(left, right, *, subject=None, listing=None, score="0.90"):
    entities = [{"entity_id": "E1", "name": left, **(subject or {})}]
    snapshot = {
        "snapshot_id": "synthetic",
        "source_id": "csl",
        "entries": [
            {
                "record_id": "L1",
                "name": right,
                "list_name": "Synthetic list",
                **(listing or {}),
            }
        ],
    }
    original = deepcopy((entities, snapshot))
    result = candidate_findings(
        entities, snapshot, date(2026, 10, 1), minimum_score=Decimal(score)
    )
    assert (entities, snapshot) == original
    return result


@pytest.mark.parametrize(
    "latin,cyrillic,form",
    [
        ("NPO Astra", "НПО Астра", "npo astra"),
        ("Shchukin Zhirnov", "Щукин Жирнов", "shchukin zhirnov"),
        ("Fëdor Zhigulin", "Фёдор Жигулин", "fedor zhigulin"),
        ("Iurii Iakovlev", "Юрий Яковлев", "iurii iakovlev"),
        ("Ilina", "Ильина", "ilina"),
        ("Semka", "Съемка", "semka"),
        ("Khariton Tsarev", "Харитон Царев", "khariton tsarev"),
        ("Elektron 123", "Электрон 123", "elektron 123"),
        ("NPO Astra", "НПО-АСТРА", "npo astra"),
        ("OOO Astra", "ООО Астра", "ooo astra"),
    ],
)
def test_exact_romanization_is_symmetric_explicit_and_not_identity(
    latin, cyrillic, form
):
    for left, right in ((latin, cyrillic), (cyrillic, latin)):
        findings, counts = evaluate(left, right, score="1")
        assert len(findings) == 1
        metrics = findings[0]["metrics"]
        assert metrics["candidate_selection"] == "transliterated_name"
        assert metrics["name_transformation"] == "russian_ala_lc_2012_normalized"
        assert metrics["entity_name_compared"] == left
        assert metrics["source_name_compared"] == right
        assert metrics["entity_comparison_form"] == form
        assert metrics["source_comparison_form"] == form
        assert metrics["name_similarity"] == "1.0000"
        assert Decimal(metrics["full_name_similarity"]) < 1
        assert counts["candidates_retained_transliterated"] == 1
        assert counts["candidates_retained_exact_or_identifier"] == 0
        assert "lossy" in metrics["name_comparison_method"]
        assert "requires identity review" in findings[0]["observation"]
        assert any("original-script" in value for value in findings[0]["unknowns"])


def test_exact_token_order_can_differ_but_duplicate_tokens_are_not_dropped():
    findings, _ = evaluate("Zhigulin Fedor", "Фёдор Жигулин")
    assert findings[0]["metrics"]["entity_comparison_form"] == "zhigulin fedor"
    assert findings[0]["metrics"]["source_comparison_form"] == "fedor zhigulin"
    assert evaluate("Fedor Fedor Zhigulin", "Фёдор Жигулин")[0] == []


@pytest.mark.parametrize(
    "left,right",
    [
        ("A", "А"),
        ("AB", "АБ"),
        ("NPO", "НПО"),
        ("OOO", "ООО"),
        ("PAO", "ПАО"),
        ("Aktsionernoe Obshchestvo", "Акционерное Общество"),
        ("NPO Astra", "НПО Орион"),
        ("NPO Astra", "НПО Астр"),
        ("NPO Astra", "НПО Астрак"),
        ("Astra", "Аstра"),
        ("Astra", "Aстra"),
        ("Galina", "Ґалина"),
        ("Petro", "Петроі"),
        ("Moskva", "Мосκва"),  # Greek kappa is not Cyrillic к.
        ("Fedor", "Фёдор\u0301"),  # Unsupported additional combining mark.
        ("Poccia", "Россия"),  # Appearance is not a transliteration mapping.
        ("NPO Astra", "Scientific Production Association Astra"),
        ("Iakovlev", "Яковлеѣ"),  # Historical letters require supplied aliases.
        ("Hua Wei", "华为"),
    ],
)
def test_ambiguous_or_unsupported_forms_do_not_gain_loose_romanization(left, right):
    findings, counts = evaluate(left, right)
    assert findings == []
    assert counts["candidates_retained_transliterated"] == 0


def test_name_normalization_and_general_similarity_do_not_merge_scripts():
    assert name_score("Астра", "Astra") < 1
    assert name_score("A", "А") == 0
    assert name_score("Торговая Компания", "Компания Торговая") == 1


def test_supplied_alias_takes_precedence_and_retains_source_quality():
    findings, counts = evaluate(
        "NPO Astra",
        "НПО Астра",
        listing={
            "aliases": ["NPO Astra"],
            "alias_details": [{"name": "NPO Astra", "quality": "weak"}],
        },
    )
    metrics = findings[0]["metrics"]
    assert metrics["candidate_selection"] == "exact_normalized_name"
    assert metrics["name_transformation"] == "normalized"
    assert metrics["source_name_compared"] == "NPO Astra"
    assert metrics["alias_quality"] == ["weak"]
    assert counts["candidates_retained_transliterated"] == 0
    assert counts["candidates_retained_exact_or_identifier"] == 1


def test_romanized_source_alias_keeps_its_original_quality():
    findings, _ = evaluate(
        "NPO Astra",
        "Different Official Name",
        listing={
            "aliases": ["НПО Астра"],
            "alias_details": [{"name": "НПО Астра", "quality": "weak"}],
        },
    )
    assert findings[0]["metrics"]["source_name_compared"] == "НПО Астра"
    assert findings[0]["metrics"]["alias_quality"] == ["weak"]


def test_conflicting_context_and_identifier_type_stay_visible():
    findings, _ = evaluate(
        "NPO Astra",
        "НПО Астра",
        subject={
            "entity_type": "organization",
            "country": "US",
            "registration_id": "123",
        },
        listing={
            "entity_type": "individual",
            "countries": ["RU"],
            "identifiers": [
                {"idType": "registration", "idNumber": "456"},
                {"idType": "passport", "idNumber": "123"},
            ],
        },
    )
    metrics = findings[0]["metrics"]
    assert metrics["entity_type_context"] == metrics["country_context"] == "differs"
    assert metrics["identifier_matches"] == []
    assert len(metrics["identifier_comparisons"]) == 1
    assert metrics["identifier_comparisons"][0]["comparison"] == "different"


def test_typed_identifier_remains_primary_selection_with_romanization_explained():
    findings, counts = evaluate(
        "NPO Astra",
        "НПО Астра",
        subject={"registration_id": "123"},
        listing={"identifiers": [{"idType": "registration", "idNumber": "123"}]},
    )
    metrics = findings[0]["metrics"]
    assert metrics["candidate_selection"] == "typed_identifier"
    assert metrics["name_transformation"] == "russian_ala_lc_2012_normalized"
    assert counts["candidates_retained_exact_or_identifier"] == 1
    assert counts["candidates_retained_transliterated"] == 0


def test_source_dates_still_bound_romanization():
    assert (
        evaluate("NPO Astra", "НПО Астра", listing={"end_date": "2026-09-30"})[0] == []
    )
    findings, _ = evaluate("NPO Astra", "НПО Астра", listing={"end_date": "2026-10-01"})
    assert len(findings) == 1


def test_romanized_outputs_share_the_total_fail_closed_bound(monkeypatch):
    import omphalos.screening as screening

    monkeypatch.setattr(screening, "MAX_RETAINED_CANDIDATES", 0)
    findings, counts = evaluate("NPO Astra", "НПО Астра")
    assert findings == []
    assert counts["candidate_output_limit_exceeded"]
    assert counts["candidates_retained_transliterated"] == 0


def test_transformed_candidates_and_all_approximate_records_survive_export_replay(
    tmp_path, monkeypatch
):
    import json
    import shutil
    import urllib.request
    import zipfile

    from test_case_review import case_review
    from test_investigations import case
    from test_sources_screening import csl_payload, import_csl

    from omphalos.evidence import verify_bundle
    from omphalos.runner import Workspace
    from omphalos.workflow import import_subject

    workspace = Workspace(tmp_path / "workspace")
    import_subject("NPO Astra", workspace.root / "datasets/subject")
    payload = csl_payload()
    payload["total"] = 8
    payload["results"] = [
        {"id": f"entry-{i}", "source": "Entity List (EL)", "name": name}
        for i, name in enumerate(["НПО Астра"] + ["NPO Astrak"] * 7)
    ]
    import_csl(tmp_path, payload)
    shutil.copytree(tmp_path / "snapshot", workspace.root / "sources/snapshot")
    intent = case(
        "screening_candidates",
        dataset_id="subject",
        watchlist_snapshot_id="snapshot",
        parameters={"screening_candidates": {"max_candidates": 1}},
    )
    workspace.save_case(intent)
    run_id = workspace.run_case(intent["case_id"])["run_id"]
    run = workspace.get_run(run_id)
    findings = run["analysis"]["findings"]
    assert len(findings) == 8
    transformed = [
        row
        for row in findings
        if row["metrics"]["candidate_selection"] == "transliterated_name"
    ]
    assert len(transformed) == 1
    assert transformed[0]["metrics"]["source_name_compared"] == "НПО Астра"
    assert transformed[0]["metrics"]["source_comparison_form"] == "npo astra"
    shutil.rmtree(workspace.root / "sources/snapshot")
    shutil.rmtree(workspace.root / "datasets/subject")
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail(
            "Offline replay fetched a network resource"
        ),
    )
    workspace.save_review(run_id, case_review(run))
    package = workspace.export_run(run_id)
    assert package["verification"]["ok"]
    assert verify_bundle(package["path"])["ok"]
    assert Workspace(workspace.root).replay_run(run_id)["ok"]
    with zipfile.ZipFile(package["path"]) as archive:
        retained = json.loads(archive.read("run/analysis.json"))
        assert retained["findings"] == findings
        source = json.loads(archive.read("run/sources/source.json"))
        assert any(row["name"] == "НПО Астра" for row in source["entries"])
        assert "russian_ala_lc_2012_normalized" in archive.read("report.md").decode()


def test_entity_record_comparison_bound_precedes_any_romanization(monkeypatch):
    from test_investigations import case, dataset

    import omphalos.investigations as investigations

    records = dataset(
        {"entities": [{"entity_id": f"E{i}", "name": "NPO Astra"} for i in range(1001)]}
    )
    source = {
        "snapshot_id": "synthetic",
        "source_id": "csl",
        "entries": [{"record_id": "L1", "name": "НПО Астра"}] * 20_000,
    }
    monkeypatch.setattr(
        investigations,
        "candidate_findings",
        lambda *args, **kwargs: pytest.fail("Over-budget comparison ran"),
    )
    result = investigations.analyze(
        records, case("screening_candidates", watchlist_snapshot_id="synthetic"), source
    )
    assert result["findings"] == []
    assert result["coverage"][0]["status"] == "not_evaluable"
    assert "20 million" in result["coverage"][0]["reason"]

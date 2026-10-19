"""Public-source expectations stay frozen; workflow decisions remain human actions."""

from __future__ import annotations

import base64
import runpy
from copy import deepcopy
from pathlib import Path

from public_case_fixtures import RECORDS, SOURCES, public_case_suite

from omphalos.browser import BrowserApp
from omphalos.data import validate_tables
from omphalos.investigations import analyze
from omphalos.util import canonical_json

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = runpy.run_path(str(ROOT / "tools" / "public_case_validation.py"))


def good(app, path, body=None):
    result = app.dispatch(path, body)
    assert result["status"] == 200, result
    return result["body_json"]


def test_public_labels_are_the_original_frozen_corpus():
    assert (
        VALIDATION["corpus_sha256"](VALIDATION["corpus"]())
        == VALIDATION["FROZEN_CORPUS_SHA256"]
    )
    assert len(RECORDS) == 6
    assert all(row["source_document"] in SOURCES for row in RECORDS)
    assert all(source["url"].startswith("https://") for source in SOURCES.values())


def test_official_aliases_and_identifiers_have_no_measured_misses_or_unexpected_candidates():
    before = deepcopy(public_case_suite())
    report = VALIDATION["evaluate_public_cases"]()
    assert public_case_suite() == before
    assert report["passed"]
    assert report["screening"]["summary"]["counts"] == {
        "tp": 18,
        "fp": 0,
        "fn": 0,
        "tn": 102,
        "unavailable_positive": 1,
        "unavailable_negative": 5,
    }
    assert report["independent_practitioner_validation"] is False
    assert report["transaction_coverage"]["findings_count"] == 0
    assert len(report["transaction_coverage"]["coverage"]) == 8
    assert report["by_input_kind"]["source_extract"]["cases"] == 10


def test_conflicting_country_is_visible_without_an_automatic_identity_decision():
    fixture = next(
        case
        for case in public_case_suite()["cases"]
        if case["id"] == "conflicting-country"
    )
    tables, _ = validate_tables(fixture["tables"])
    result = analyze(
        {"metadata": {"dataset_id": "benchmark", "synthetic": False}, "tables": tables},
        {
            "case_id": "public-conflict",
            "dataset_id": "benchmark",
            "investigations": ["screening_candidates"],
            **fixture["case"],
        },
        fixture["watchlist"],
    )
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["metrics"]["country_context"] == "differs"
    assert finding["unknowns"] and finding["alternatives"] and finding["falsifiers"]
    assert finding["source_refs"][0]["record_id"] == "suex"
    assert finding["record_refs"][0]["record_id"] == "E1"


def test_official_name_intake_cannot_approve_sources_plan_or_case(tmp_path):
    def forbidden(*args):
        raise AssertionError("The frozen validation must not contact a live source")

    app = BrowserApp(tmp_path / "public-case-workspace", transport=forbidden)
    subject = good(app, "/api/workflow/subject", {"name": "SUEX OTC, S.R.O."})
    # This is a manual test projection, not an official CSL response or full list.
    source = {
        "total": len(RECORDS),
        "offset": 0,
        "search_performed_at": "2021-11-08T00:00:00Z",
        "sources_used": [],
        "results": [
            {
                "id": record["record_id"],
                "source": "Historical public-source test extract",
                "name": record["name"],
                "alt_names": record.get("aliases", []),
                "addresses": [{"country": country} for country in record["countries"]],
            }
            for record in RECORDS
        ],
    }
    source_bytes = canonical_json(source)
    imported = good(
        app,
        "/api/sources/import",
        {
            "source_id": "csl",
            "files": [
                {
                    "name": "historical-public-test-extract.json",
                    "content_base64": base64.b64encode(source_bytes).decode(),
                }
            ],
        },
    )
    assert imported["ingestion_method"] == "manual_import"
    values = {
        "dataset_id": subject["dataset_id"],
        "goal_id": "counterparty_screening",
        "as_of": "2021-11-08",
        "watchlist_snapshot_id": imported["snapshot_id"],
    }
    proposal = good(app, "/api/workflow/plan", values)
    assert proposal["can_run"]
    execution = {
        **values,
        "case_id": proposal["case"]["case_id"],
        "plan_id": proposal["plan_id"],
    }
    assert (
        app.dispatch("/api/workflow/run", {**execution, "acknowledge_plan": True})[
            "status"
        ]
        == 400
    )
    assert good(app, "/api/state")["runs"] == []
    approved = good(
        app,
        "/api/workflow/approve",
        {**execution, "acknowledge_records": True, "acknowledge_source": True},
    )
    assert app.dispatch("/api/workflow/run", {**execution, **approved})["status"] == 400
    assert good(app, "/api/state")["runs"] == []
    result = good(
        app, "/api/workflow/run", {**execution, **approved, "acknowledge_plan": True}
    )
    run_id = result["run_id"]
    run = good(app, f"/api/runs/{run_id}")
    screening = [
        row
        for row in run["analysis"]["findings"]
        if row["investigation_id"] == "screening_candidates"
    ]
    assert len(screening) == 1
    assert run["latest_review"] is None
    before = canonical_json(run["analysis"])
    rejected = app.dispatch(f"/api/runs/{run_id}/export", {})
    assert (
        rejected["status"] != 200 and "review" in rejected["body_json"]["error"].lower()
    )
    payload = {
        "schema_version": "2.2",
        "run_id": run_id,
        "reviewer": "Public-case software validation",
        "decision": "keep_open",
        "summary": "Historical desk test: obtain independent registration records before resolving the candidate identity.",
        "scope_finding_ids": [row["finding_id"] for row in run["analysis"]["findings"]],
        "acknowledge_limitations": True,
    }
    for changes in (
        {"summary": ""},
        {"scope_finding_ids": []},
        {"acknowledge_limitations": False},
    ):
        assert (
            app.dispatch(f"/api/runs/{run_id}/review", {**payload, **changes})["status"]
            == 400
        )
    good(app, f"/api/runs/{run_id}/review", payload)
    retained = good(app, f"/api/runs/{run_id}")
    assert canonical_json(retained["analysis"]) == before
    assert retained["latest_review"]["review"] == payload
    package = good(app, f"/api/runs/{run_id}/export", {})
    assert package["verification"]["ok"]
    reopened = BrowserApp(app.root, transport=forbidden)
    assert good(reopened, f"/api/runs/{run_id}")["latest_review"]["review"] == payload
    assert good(reopened, f"/api/runs/{run_id}/replay", {})["ok"]

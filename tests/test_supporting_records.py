"""Retained diligence stays reachable even when no observation cites it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_web import browser as browser
from test_web import case

from omphalos.browser import BrowserApp
from omphalos.data import import_dataset
from omphalos.runner import Workspace
from omphalos.util import read_json, write_json


@pytest.fixture(params=["native", "browser"])
def supporting_app(request: pytest.FixtureRequest, tmp_path: Path):
    if request.param == "native":
        server, fetch = request.getfixturevalue("browser")
        return server.workspace, fetch
    app = BrowserApp(tmp_path / "browser-workspace")

    def fetch(path: str, body: dict | None = None):
        response = json.loads(
            app.dispatch_json(path, json.dumps(body) if body is not None else None)
        )
        return response["status"], response["body_json"], {}

    return app.context.workspace, fetch


def supporting_run(
    workspace: Workspace, tmp_path: Path, *, count: int = 43
) -> tuple[str, list[dict[str, Any]]]:
    source = tmp_path / "synthetic-supporting-inputs"
    source.mkdir()
    write_json(
        source / "entities.json",
        [
            {
                "entity_id": entity_id,
                "name": "Synthetic Supporting Records " + entity_id,
                "country": "US",
                "address": "100 Fictional Test Road",
            }
            for entity_id in ("E1", "E2")
        ],
    )
    # The second entity is outside the analytical scope. Supporting records are
    # explicitly all retained diligence, with no inferred relevance or verdict.
    rows = [
        {
            "evidence_id": f"D{count - index:03}",
            "entity_id": "E1" if index % 2 else "E2",
            "title": f"Synthetic supplier schedule {index}",
            "text": (
                "The supplier attributes the payments to deposit, inspection, and delivery. "
                "The final delivery record remains unavailable."
            ),
            "date": "2026-09-01",
            "source_url": "https://example.invalid/synthetic-schedule",
        }
        for index in range(count)
    ]
    if rows:
        write_json(source / "diligence.json", rows)
    import_dataset(
        source,
        workspace.root / "datasets" / "supporting",
        label="Synthetic supporting-record exercise",
        synthetic=True,
    )
    workspace.save_case(
        {
            **case("supporting", investigations=["data_quality"]),
            "scope": {"entity_ids": ["E1"]},
        }
    )
    run_id = workspace.run_case("http-case")["run_id"]
    run = workspace.get_run(run_id)
    assert run["analysis"]["findings"] == []
    data = read_json(workspace.root / "runs" / run_id / "data/dataset.json")
    return run_id, data["tables"].get("diligence", [])


def test_supporting_records_page_all_retained_diligence_with_provenance(
    supporting_app, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, fetch = supporting_app
    run_id, retained = supporting_run(workspace, tmp_path)
    checked: list[str] = []
    verify = workspace.verify_run

    def checked_verify(value: str) -> dict:
        checked.append(value)
        return verify(value)

    def unrelated_run_detail(_run_id: str):
        pytest.fail("Supporting records must not load unrelated reviews or exports.")

    monkeypatch.setattr(workspace, "verify_run", checked_verify)
    monkeypatch.setattr(workspace, "get_run", unrelated_run_detail)
    route = f"/api/runs/{run_id}/supporting-records"
    status, first, _ = fetch(route)
    assert status == 200, first
    assert checked == [run_id]
    assert first["run_id"] == run_id
    assert first["table"] == "diligence"
    assert first["scope"] == "all_retained_diligence"
    assert first["offset"] == 0 and first["limit"] == 40
    assert first["total"] == 43 and len(first["rows"]) == 40
    status, second, _ = fetch(route + "?offset=40&limit=40")
    assert status == 200, second
    assert second["total"] == 43 and len(second["rows"]) == 3
    combined = first["rows"] + second["rows"]
    assert [row["record"] for row in combined] == retained
    assert {row["record"]["entity_id"] for row in combined} == {"E1", "E2"}
    for row in combined:
        assert row["kind"] == "record"
        assert row["table"] == "diligence"
        assert row["ref"] == {"table": "diligence", "record_id": row["id"]}
        assert row["id"] == row["record"]["evidence_id"]
        assert row["synthetic"] is True
        assert row["identity_research"] is None
        assert row["origin"]["source_file"] == "diligence.json"
        assert row["origin"]["source_row"] >= 1
        assert row["source_files"][0]["path"] == "originals/diligence.json"
        assert len(row["source_files"][0]["sha256"]) == 64
    assert fetch(route + "?offset=43")[1]["rows"] == []
    assert fetch(route + "?offset=44")[0] == 400
    assert fetch(route + "?offset=2&limit=1")[1]["rows"] == combined[2:3]


def test_supporting_records_and_individual_evidence_use_same_frozen_inputs(
    supporting_app, tmp_path: Path
) -> None:
    workspace, fetch = supporting_app
    run_id, _ = supporting_run(workspace, tmp_path, count=1)
    route = f"/api/runs/{run_id}/supporting-records"
    before = fetch(route)[1]
    (workspace.root / "datasets" / "supporting").rename(tmp_path / "removed-inputs")
    (workspace.root / "cases" / "http-case.json").write_text("{}")
    status, after, _ = fetch(route)
    assert status == 200 and after == before
    listed = after["rows"][0]
    status, detail, _ = fetch(
        f"/api/runs/{run_id}/evidence?table=diligence&id={listed['id']}"
    )
    assert status == 200, detail
    for key in ("record", "origin", "source_files", "synthetic", "identity_research"):
        assert detail[key] == listed[key]


def test_zero_observation_run_without_diligence_has_explicit_empty_page(
    supporting_app, tmp_path: Path
) -> None:
    workspace, fetch = supporting_app
    run_id, _ = supporting_run(workspace, tmp_path, count=0)
    status, page, _ = fetch(f"/api/runs/{run_id}/supporting-records")
    assert status == 200, page
    assert page == {
        "run_id": run_id,
        "table": "diligence",
        "scope": "all_retained_diligence",
        "total": 0,
        "offset": 0,
        "limit": 40,
        "rows": [],
    }


def test_supporting_records_reject_ambiguous_or_unbounded_pagination(supporting_app):
    _, fetch = supporting_app
    for query in (
        "offset=",
        "offset=-1",
        "offset=1.5",
        "offset=0&offset=1",
        "offset=100000000000",
        "offset=%D9%A1",
        "limit=",
        "limit=0",
        "limit=41",
        "limit=1&limit=2",
        "limit=true",
        "table=entities",
        "dataset_id=mutable",
        "finding_id=F1",
    ):
        status, result, _ = fetch("/api/runs/absent/supporting-records?" + query)
        assert status == 400, (query, result)
    assert fetch("/api/runs/absent/supporting-records")[0] == 404
    assert fetch("/api/runs/..%2Foutside/supporting-records")[0] in {400, 404}


@pytest.mark.parametrize("damaged", ["analysis.json", "data/originals/diligence.json"])
def test_supporting_records_never_expose_damaged_retained_evidence(
    supporting_app, tmp_path: Path, damaged: str
) -> None:
    workspace, fetch = supporting_app
    run_id, _ = supporting_run(workspace, tmp_path, count=1)
    file = workspace.root / "runs" / run_id / damaged
    file.write_bytes(file.read_bytes() + b" ")
    status, result, _ = fetch(f"/api/runs/{run_id}/supporting-records")
    assert status == 409
    assert "integrity failed" in result["error"]
    assert "rows" not in result


def test_supporting_records_respect_local_origin_boundary(browser, tmp_path: Path):
    server, fetch = browser
    run_id, _ = supporting_run(server.workspace, tmp_path, count=1)
    route = f"/api/runs/{run_id}/supporting-records"
    assert fetch(route, headers={"Origin": "https://unrelated.example"})[0] == 403
    assert fetch(route, headers={"Host": "unrelated.example"})[0] == 403

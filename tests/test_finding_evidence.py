"""Bounded citation pages retain provenance and cannot expose unrelated records."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_evidence import make_run
from test_web import browser as browser
from test_web import case, upload

from omphalos import evidence
from omphalos.data import create_demo
from omphalos.util import canonical_json, read_json, sha256_bytes, write_json


def retained_fixture_run(server, request) -> dict:
    create_demo(server.root / "datasets" / "fixture-batch")
    assert request("/api/cases", case("fixture-batch"))[0] == 200
    status, created, _ = request("/api/cases/http-case/run", {})
    assert status == 200, created
    return request(f"/api/runs/{created['run_id']}")[1]


def test_finding_evidence_is_one_verified_page_with_original_provenance(
    browser, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, request = browser
    run = retained_fixture_run(server, request)
    run_id = run["manifest"]["run_id"]
    finding = run["analysis"]["findings"][0]
    verify = server.workspace.verify_run
    checked: list[str] = []

    def counted_verify(value: str) -> dict:
        checked.append(value)
        return verify(value)

    monkeypatch.setattr(server.workspace, "verify_run", counted_verify)
    status, page, _ = request(
        f"/api/runs/{run_id}/finding-evidence?finding_id={finding['finding_id']}"
    )
    assert status == 200, page
    assert checked == [run_id]
    assert page["total"] == len(finding["record_refs"])
    assert page["offset"] == 0 and page["limit"] == 40
    assert [row["ref"] for row in page["rows"]] == finding["record_refs"][:40]
    for row in page["rows"]:
        assert row["kind"] == "record"
        assert row["synthetic"] is True
        assert row["origin"]["source_file"] == "dataset.json"
        assert row["source_files"][0]["sha256"]
        assert row["id"] == row["ref"]["record_id"]


def test_individual_record_checks_run_without_loading_unrelated_detail(
    browser, monkeypatch
) -> None:
    server, request = browser
    run = retained_fixture_run(server, request)
    run_id = run["manifest"]["run_id"]
    ref = run["analysis"]["findings"][0]["record_refs"][0]
    checks = []
    verify = server.workspace.verify_run

    def checked_verify(value):
        checks.append(value)
        return verify(value)

    def unrelated_run_detail(_run_id):
        raise AssertionError(
            "Evidence must not revalidate unrelated reviews or exports"
        )

    monkeypatch.setattr(server.workspace, "verify_run", checked_verify)
    monkeypatch.setattr(server.workspace, "get_run", unrelated_run_detail)
    route = f"/api/runs/{run_id}/evidence?table={ref['table']}&id={ref['record_id']}"
    status, detail, _ = request(route)
    assert status == 200, detail
    assert checks == [run_id]
    assert detail["origin"]["source_file"] == "dataset.json"
    (server.root / "runs" / run_id / "analysis.json").write_text("{}")
    assert request(route)[0] == 409
    assert request("/api/runs/absent/evidence?table=entities&id=E1")[0] == 404


def test_finding_evidence_includes_retained_source_rows(browser) -> None:
    server, request = browser
    original = {
        "id": "official-fixture-1",
        "name": "Synthetic Harbor Instruments",
        "source": "Entity List (EL) - Bureau of Industry and Security",
        "addresses": [{"country": "US", "address": "100 Example Industrial Road"}],
        "start_date": "2020-01-01",
    }
    status, saved, _ = request(
        "/api/sources/import",
        {
            "source_id": "csl",
            "snapshot_id": "source-fixture",
            "files": [
                upload(
                    "consolidated.json",
                    {"total": 1, "offset": 0, "results": [original]},
                )
            ],
        },
    )
    assert status == 200, saved
    create_demo(server.root / "datasets" / "screening-batch")
    definition = {
        **case("screening-batch", investigations=["screening_candidates"]),
        "watchlist_snapshot_id": "source-fixture",
    }
    assert request("/api/cases", definition)[0] == 200
    status, created, _ = request("/api/cases/http-case/run", {})
    assert status == 200, created
    run_id = created["run_id"]
    finding = request(f"/api/runs/{run_id}")[1]["analysis"]["findings"][0]
    status, page, _ = request(
        f"/api/runs/{run_id}/finding-evidence?finding_id={finding['finding_id']}&offset=0"
    )
    assert status == 200, page
    assert page["total"] == len(finding["record_refs"]) + len(finding["source_refs"])
    assert [row["ref"] for row in page["rows"]] == (
        finding["record_refs"] + finding["source_refs"]
    )
    row = next(row for row in page["rows"] if row["kind"] == "source")
    assert row["record"]["raw_record"] == original
    assert row["metadata"]["sha256"]
    assert row["source_id"] == "csl" and row["snapshot_id"] == "source-fixture"
    # Mutable source imports cannot affect the retained record shown above.
    (server.root / "sources/source-fixture/source.json").write_text("{}")
    assert (
        request(
            f"/api/runs/{run_id}/finding-evidence?finding_id={finding['finding_id']}"
        )[1]["rows"]
        == page["rows"]
    )


def make_large_cited_run(root: Path) -> None:
    manifest, _ = make_run(root)
    data = read_json(root / "data/dataset.json")
    data["tables"]["entities"] = [
        {"entity_id": f"E{index}", "name": f"Synthetic entity {index}"}
        for index in range(1, 49)
    ]
    write_json(root / "data/dataset.json", data)
    analysis = read_json(root / "analysis.json")
    analysis["findings"][0]["record_refs"] = [
        {"table": "entities", "record_id": f"E{index}"} for index in range(1, 48)
    ]
    analysis["scope_counts"]["entities"] = 48
    analysis["coverage"][0]["records_evaluated"] = 48
    write_json(root / "analysis.json", analysis)
    (root / "manifest.json").unlink()
    evidence.build_manifest(
        root,
        run_id=manifest["run_id"],
        case_id=manifest["case_id"],
        analysis_digest=sha256_bytes(canonical_json(analysis)),
    )


def test_finding_evidence_pages_only_its_citations(browser) -> None:
    server, request = browser
    make_large_cited_run(server.root / "runs/run_demo")
    path = "/api/runs/run_demo/finding-evidence?finding_id=F1"
    first = request(path)[1]
    second = request(path + "&offset=40")[1]
    assert first["total"] == second["total"] == 47
    assert len(first["rows"]) == 40 and len(second["rows"]) == 7
    assert first["rows"][0]["id"] == "E1"
    assert second["rows"][0]["id"] == "E41"
    assert second["rows"][-1]["id"] == "E47"
    assert not any(row["id"] == "E48" for row in first["rows"] + second["rows"])
    assert request(path + "&offset=47")[1]["rows"] == []
    assert request(path + "&offset=48")[0] == 400
    assert request(path + "&id=E48")[0] == 400
    assert request(path + "&table=entities")[0] == 400


@pytest.mark.parametrize(
    "query",
    [
        "",
        "finding_id=",
        "finding_id=F1&finding_id=F2",
        "finding_id=F1&offset=0&offset=40",
        "finding_id=F1&offset=",
        "finding_id=F1&offset=-1",
        "finding_id=F1&offset=1.5",
        "finding_id=F1&offset=true",
        "finding_id=F1&offset=100000000000",
        "finding_id=F1&dataset_id=other",
        "finding_id=..%2Foutside",
    ],
)
def test_finding_evidence_rejects_invalid_query(browser, query: str) -> None:
    _, request = browser
    assert request(f"/api/runs/run_demo/finding-evidence?{query}")[0] == 400


def test_finding_evidence_rejects_unknown_and_damaged_runs(browser) -> None:
    server, request = browser
    run = retained_fixture_run(server, request)
    run_id = run["manifest"]["run_id"]
    finding_id = run["analysis"]["findings"][0]["finding_id"]
    path = f"/api/runs/{run_id}/finding-evidence?finding_id={finding_id}"
    assert request(f"/api/runs/{run_id}/finding-evidence?finding_id=absent")[0] == 404
    assert request("/api/runs/absent/finding-evidence?finding_id=absent")[0] == 404
    assert request(path, headers={"Origin": "https://unrelated.example"})[0] == 403
    assert request(path, headers={"Host": "unrelated.example"})[0] == 403
    (server.root / "runs" / run_id / "analysis.json").write_text("{}")
    assert request(path)[0] == 409

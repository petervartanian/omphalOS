"""Exercise guided decisions through the real local HTTP service.

These tests focus on user-visible boundaries: previewed bytes and mappings,
approved plans, preserved evidence, and the separate human review. They do not
replace the browser interaction tests or assert visual layout details.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest
from test_web import browser as browser
from test_web import upload

from omphalos.data import load_dataset
from omphalos.sources import import_source, load_source
from omphalos.util import canonical_json, sha256_bytes
from omphalos.workflow import import_vendor_csv, preview_vendor_csv

VENDOR_CSV = (
    b"\xef\xbb\xbfVendor name,Country,Notes,Account code\r\n"
    b'"Example, Ltd.",US,"First line\r\nSecond line",private-001\r\n'
    b'"Example, Ltd.",US,Separate row,private-002\r\n'
)
MAPPING = {
    "Vendor name": "name",
    "Country": "country",
    "Notes": "notes",
    "Account code": None,
}


def preview(request, *, raw: bytes = VENDOR_CSV, mapping: dict | None = None) -> dict:
    status, result, _ = request(
        "/api/workflow/preview",
        {
            "files": [upload("vendor-export.csv", raw)],
            "mapping": MAPPING if mapping is None else mapping,
        },
    )
    assert status == 200, result
    assert result["can_import"], result
    return result


def import_preview(request, result: dict, *, raw: bytes = VENDOR_CSV):
    return request(
        "/api/workflow/import",
        {
            "files": [upload("vendor-export.csv", raw)],
            "mapping": result["mapping"],
            "preview_id": result["preview_id"],
            "label": "Uploaded vendor records",
        },
    )


def plan(
    request,
    dataset_id: str,
    *,
    goal_id: str = "data_readiness",
    snapshot_id: str | None = None,
) -> tuple[dict, dict]:
    payload = {
        "dataset_id": dataset_id,
        "goal_id": goal_id,
        "as_of": "2026-10-13",
        "watchlist_snapshot_id": snapshot_id,
    }
    status, result, _ = request("/api/workflow/plan", payload)
    assert status == 200 and result["can_run"], result
    return payload, result


def run_payload(request, payload: dict, proposed: dict) -> dict:
    execution = {
        **payload,
        "plan_id": proposed["plan_id"],
        "case_id": proposed["case"]["case_id"],
    }
    if not proposed["can_run"]:
        return {**execution, "approval": {}, "acknowledge_plan": True}
    status, result, _ = request(
        "/api/workflow/approve",
        {**execution, "acknowledge_records": True, "acknowledge_source": True},
    )
    assert status == 200, result
    return {**execution, "approval": result["approval"], "acknowledge_plan": True}


def test_guided_import_preserves_original_bytes_and_separate_same_name_rows(browser):
    server, request = browser
    proposed = preview(request)
    assert proposed["row_count"] == 2
    assert proposed["sha256"] == sha256_bytes(VENDOR_CSV)
    assert proposed["mapping"] == MAPPING
    assert {column["name"] for column in proposed["columns"]} == set(MAPPING)
    retained = next(
        column for column in proposed["columns"] if column["name"] == "Account code"
    )
    assert retained["target_field"] is None
    assert retained["status"] == "retained_only"
    assert not list((server.root / "datasets").iterdir())

    status, imported, _ = import_preview(request, proposed)
    assert status == 200, imported
    assert imported["synthetic"] is False
    directory = server.root / "datasets" / imported["dataset_id"]
    assert (directory / "originals/vendor-export.csv").read_bytes() == VENDOR_CSV
    dataset = load_dataset(directory)
    entities = dataset["tables"]["entities"]
    assert len(entities) == 2
    assert len({row["entity_id"] for row in entities}) == 2
    assert {row["name"] for row in entities} == {"Example, Ltd."}
    assert {row["notes"] for row in entities} == {
        "First line\r\nSecond line",
        "Separate row",
    }
    assert {
        origin["source_row"]
        for origin in dataset["metadata"]["provenance"]["entities"].values()
    } == {3, 4}
    # A repeated import is a new dataset, while row identities remain traceable
    # to the same original file and physical CSV rows.
    status, repeated, _ = import_preview(request, proposed)
    assert status == 200, repeated
    assert repeated["dataset_id"] != imported["dataset_id"]
    assert (
        load_dataset(server.root / "datasets" / repeated["dataset_id"])["tables"]
        == dataset["tables"]
    )


@pytest.mark.parametrize("change", ["file", "mapping"])
def test_unconfirmed_file_or_mapping_change_cannot_be_imported(browser, change):
    server, request = browser
    proposed = preview(request)
    body = {
        "files": [upload("vendor-export.csv", VENDOR_CSV)],
        "mapping": dict(proposed["mapping"]),
        "preview_id": proposed["preview_id"],
    }
    if change == "file":
        body["files"] = [
            upload("vendor-export.csv", VENDOR_CSV.replace(b"US", b"GB", 1))
        ]
    else:
        body["mapping"]["Notes"] = None
    status, result, _ = request("/api/workflow/import", body)
    assert status in {400, 409}, result
    assert not list((server.root / "datasets").iterdir())


@pytest.mark.parametrize(
    "mapping",
    [
        {key: value for key, value in MAPPING.items() if key != "Account code"},
        {**MAPPING, "Not an uploaded column": None},
        {**MAPPING, "Notes": "name"},
    ],
    ids=["missing-column", "unknown-column", "duplicate-target"],
)
def test_mapping_is_complete_and_cannot_silently_overwrite_a_field(browser, mapping):
    server, request = browser
    status, result, _ = request(
        "/api/workflow/preview",
        {"files": [upload("vendor-export.csv", VENDOR_CSV)], "mapping": mapping},
    )
    assert status == 400 or status == 200 and result["can_import"] is False, result
    assert not list((server.root / "datasets").iterdir())


def test_import_requires_an_explicit_mapping_object(browser):
    server, request = browser
    proposed = preview(request)
    status, result, _ = request(
        "/api/workflow/import",
        {
            "files": [upload("vendor-export.csv", VENDOR_CSV)],
            "mapping": None,
            "preview_id": proposed["preview_id"],
        },
    )
    assert status == 400, result
    assert not list((server.root / "datasets").iterdir())


def test_guided_run_preserves_plan_and_evidence_without_fabricating_review(browser):
    server, request = browser
    status, imported, _ = import_preview(request, preview(request))
    assert status == 200, imported
    payload, proposed = plan(request, imported["dataset_id"])
    assert proposed["case"]["dataset_id"] == imported["dataset_id"]
    assert proposed["case"]["as_of"] == payload["as_of"]
    assert proposed["case"]["watchlist_snapshot_id"] is None
    assert "threshold_cluster" not in proposed["case"]["investigations"]
    assert not list((server.root / "cases").glob("*.json"))

    status, summary, _ = request(
        "/api/workflow/run", run_payload(request, payload, proposed)
    )
    assert status == 200, summary
    run_id = summary["run_id"]
    status, run, _ = request(f"/api/runs/{run_id}")
    assert status == 200 and run["verification"]["ok"], run
    assert run["case"]["schema_version"] == "2.1"
    restored = {key: value for key, value in run["case"].items() if key != "workflow"}
    restored["schema_version"] = "2.0"
    assert restored == proposed["case"]
    assert run["workflow"]["status"] == "recorded"
    assert run["latest_review"] is None
    assert run["review_validation"]["ok"] is False
    assert request(f"/api/runs/{run_id}/export", {})[0] == 400
    assert request(f"/api/runs/{run_id}/replay", {})[1]["ok"]
    archived = server.root / "runs" / run_id / "data"
    assert (archived / "originals/vendor-export.csv").read_bytes() == VENDOR_CSV
    assert load_dataset(archived)["metadata"]["import_transform"]["mapping"] == MAPPING


def test_changed_plan_inputs_and_repeated_case_cannot_replace_approved_work(browser):
    server, request = browser
    status, imported, _ = import_preview(request, preview(request))
    assert status == 200, imported
    payload, proposed = plan(request, imported["dataset_id"])
    approved = run_payload(request, payload, proposed)
    for changed in [
        {**approved, "as_of": "2025-01-01"},
        {**approved, "case_id": "different-case"},
        {**approved, "plan_id": "unapproved-plan"},
        {**approved, "reviewer": "Invented reviewer"},
    ]:
        status, result, _ = request("/api/workflow/run", changed)
        assert status in {400, 409}, result
        assert not list((server.root / "runs").iterdir())
        assert not list((server.root / "cases").glob("*.json"))

    status, summary, _ = request("/api/workflow/run", approved)
    assert status == 200, summary
    case_path = server.root / "cases" / f"{approved['case_id']}.json"
    original_case = case_path.read_bytes()
    status, result, _ = request("/api/workflow/run", approved)
    assert status == 200 and result["run_id"] == summary["run_id"], result
    assert result["reused"] is True
    assert case_path.read_bytes() == original_case
    assert [path.name for path in (server.root / "runs").iterdir()] == [
        summary["run_id"]
    ]


def test_guided_local_import_plan_and_run_make_no_external_connections(
    browser, monkeypatch
):
    server, request = browser
    original_connect = socket.socket.connect
    attempted: list[Any] = []

    def local_only(sock: socket.socket, address: Any) -> None:
        attempted.append(address)
        assert isinstance(address, tuple) and address[:2] == (
            "127.0.0.1",
            server.port,
        ), f"Guided local processing attempted an external connection: {address}"
        original_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", local_only)
    status, imported, _ = import_preview(request, preview(request))
    assert status == 200, imported
    payload, proposed = plan(request, imported["dataset_id"])
    status, summary, _ = request(
        "/api/workflow/run", run_payload(request, payload, proposed)
    )
    assert status == 200, summary
    assert attempted
    assert all(address[:2] == ("127.0.0.1", server.port) for address in attempted)


@pytest.mark.parametrize("replacement", ["dataset", "source"])
def test_valid_replacement_under_same_identifier_invalidates_prior_plan(
    browser, tmp_path: Path, replacement: str
):
    server, request = browser
    status, imported, _ = import_preview(request, preview(request))
    assert status == 200, imported
    dataset_id = imported["dataset_id"]
    original_source = {
        "search_performed_at": "2026-10-13T09:00:00Z",
        "total": 1,
        "offset": 0,
        "results": [
            {
                "id": "fixture-source-1",
                "name": "Example, Ltd.",
                "source": "Entity List (EL) - Bureau of Industry and Security",
                "addresses": [{"country": "US"}],
                "source_record_note": "First retained source note",
            }
        ],
    }
    if replacement == "source":
        status, saved, _ = request(
            "/api/sources/import",
            {
                "source_id": "csl",
                "snapshot_id": "official-fixture",
                "files": [upload("official.json", original_source)],
            },
        )
        assert status == 200, saved
    payload, proposed = plan(
        request,
        dataset_id,
        goal_id=(
            "counterparty_screening" if replacement == "source" else "data_readiness"
        ),
        snapshot_id="official-fixture" if replacement == "source" else None,
    )
    approved = run_payload(request, payload, proposed)
    if replacement == "dataset":
        # Keep the dataset ID, label, number of records, and analytical eligibility.
        # Replace it with another fully valid import, rather than corrupting hashes.
        raw = VENDOR_CSV.replace(b"First line", b"Updated note")
        upload_path = tmp_path / "vendor-export.csv"
        upload_path.write_bytes(raw)
        revised_preview = preview_vendor_csv(upload_path, MAPPING)
        destination = server.root / "datasets" / dataset_id
        destination.rename(tmp_path / "previous-dataset")
        import_vendor_csv(
            upload_path,
            destination,
            mapping=MAPPING,
            preview_id=revised_preview["preview_id"],
            label=imported["label"],
        )
        assert load_dataset(destination)["metadata"]["dataset_id"] == dataset_id
    else:
        original_source["results"][0][
            "source_record_note"
        ] = "Revised retained source note"
        upload_path = tmp_path / "official.json"
        upload_path.write_bytes(canonical_json(original_source))
        destination = server.root / "sources/official-fixture"
        destination.rename(tmp_path / "previous-source")
        import_source("csl", upload_path, destination)
        assert load_source(destination)["snapshot_id"] == "official-fixture"

    status, result, _ = request("/api/workflow/run", approved)
    assert status == 409, result
    assert not list((server.root / "runs").iterdir())
    assert not list((server.root / "cases").glob("*.json"))


def test_screening_plan_exposes_missing_source_and_cannot_run_anyway(browser):
    server, request = browser
    status, imported, _ = import_preview(request, preview(request))
    assert status == 200, imported
    payload = {
        "dataset_id": imported["dataset_id"],
        "goal_id": "counterparty_screening",
        "as_of": "2000-01-01",
        "watchlist_snapshot_id": None,
    }
    status, proposed, _ = request("/api/workflow/plan", payload)
    assert status == 200, proposed
    assert proposed["can_run"] is False
    assert proposed["case"]["as_of"] == "2000-01-01"
    assert proposed["source_status"]["required"] is True
    assert proposed["source_status"]["selected"] is False
    assert any(
        check["id"] == "screening_candidates" and check["status"] == "not_evaluable"
        for check in proposed["unavailable_checks"]
    )
    status, result, _ = request(
        "/api/workflow/run", run_payload(request, payload, proposed)
    )
    assert status == 400, result
    assert not list((server.root / "runs").iterdir())

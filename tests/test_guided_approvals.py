"""Explicit stage actions remain bound to retained inputs in both runtimes."""

from __future__ import annotations

import copy
import io
import json
import zipfile
from pathlib import Path

import pytest
from test_browser import good, plan, review_and_export
from test_workflow import workspace as workspace

from omphalos.browser import BrowserApp
from omphalos.models import Case
from omphalos.util import canonical_json, read_json, sha256_file, write_json


def prepared(app: BrowserApp) -> tuple[dict, dict]:
    subject = good(
        app, "/api/workflow/subject", {"name": "Fictional Approval Test Company"}
    )
    inputs = {
        "dataset_id": subject["dataset_id"],
        "goal_id": "data_readiness",
        "as_of": "2026-10-16",
        "watchlist_snapshot_id": None,
    }
    proposed = good(app, "/api/workflow/plan", inputs)
    execution = {
        **inputs,
        "plan_id": proposed["plan_id"],
        "case_id": proposed["case"]["case_id"],
    }
    return inputs, execution


@pytest.mark.parametrize("field", ["acknowledge_records", "acknowledge_source"])
@pytest.mark.parametrize("value", [None, False, "true", 1])
def test_source_acceptance_requires_explicit_true_actions(
    tmp_path: Path, field: str, value: object
) -> None:
    app = BrowserApp(tmp_path / "browser")
    _, execution = prepared(app)
    body = {**execution, "acknowledge_records": True, "acknowledge_source": True}
    if value is None:
        body.pop(field)
    else:
        body[field] = value
    assert app.dispatch("/api/workflow/approve", body)["status"] == 400
    assert good(app, "/api/state")["cases"] == []
    assert good(app, "/api/state")["runs"] == []


@pytest.mark.parametrize("value", [None, False, "true", 1])
def test_signed_source_receipt_does_not_authorize_plan_execution(
    tmp_path: Path, value: object
) -> None:
    app = BrowserApp(tmp_path / "browser")
    _, execution = prepared(app)
    approved = good(
        app,
        "/api/workflow/approve",
        {**execution, "acknowledge_records": True, "acknowledge_source": True},
    )
    body = {**execution, **approved}
    if value is not None:
        body["acknowledge_plan"] = value
    assert app.dispatch("/api/workflow/run", body)["status"] == 400
    assert good(app, "/api/state")["cases"] == []
    assert good(app, "/api/state")["runs"] == []


def test_running_a_prepared_plan_without_source_receipt_is_rejected(
    tmp_path: Path,
) -> None:
    app = BrowserApp(tmp_path / "browser")
    _, execution = prepared(app)
    assert (
        app.dispatch("/api/workflow/run", {**execution, "acknowledge_plan": True})[
            "status"
        ]
        == 400
    )
    assert good(app, "/api/state")["cases"] == []


def test_source_acceptance_allows_inspection_of_a_data_limited_plan(
    tmp_path: Path,
) -> None:
    app = BrowserApp(tmp_path / "browser")
    inputs, _ = prepared(app)
    inputs["goal_id"] = "transaction_review"
    proposed = good(app, "/api/workflow/plan", inputs)
    assert proposed["can_run"] is False
    assert proposed["unavailable_checks"]
    execution = {
        **inputs,
        "plan_id": proposed["plan_id"],
        "case_id": proposed["case"]["case_id"],
    }
    approved = good(
        app,
        "/api/workflow/approve",
        {**execution, "acknowledge_records": True, "acknowledge_source": True},
    )
    assert approved["approval"]["source_accepted"] is True
    result = app.dispatch(
        "/api/workflow/run", {**execution, **approved, "acknowledge_plan": True}
    )
    assert result["status"] == 400
    assert "missing plan requirements" in result["body_json"]["error"]
    assert good(app, "/api/state")["runs"] == []


def test_missing_required_list_cannot_be_accepted(tmp_path: Path) -> None:
    app = BrowserApp(tmp_path / "browser")
    inputs, _ = prepared(app)
    inputs["goal_id"] = "counterparty_screening"
    proposed = good(app, "/api/workflow/plan", inputs)
    result = app.dispatch(
        "/api/workflow/approve",
        {
            **inputs,
            "plan_id": proposed["plan_id"],
            "case_id": proposed["case"]["case_id"],
            "acknowledge_records": True,
            "acknowledge_source": True,
        },
    )
    assert result["status"] == 400
    assert "required screening source" in result["body_json"]["error"]


@pytest.mark.parametrize("field", ["dataset_sha256", "source_accepted_at", "signature"])
def test_source_receipt_cannot_be_altered(tmp_path: Path, field: str) -> None:
    app = BrowserApp(tmp_path / "browser")
    inputs, _ = prepared(app)
    execution = plan(app, inputs["dataset_id"])
    changed = copy.deepcopy(execution)
    changed["approval"][field] = (
        "2026-01-01T00:00:00Z" if field.endswith("_at") else "f" * 64
    )
    assert app.dispatch("/api/workflow/run", changed)["status"] == 409
    assert good(app, "/api/state")["cases"] == []


def test_source_receipt_is_bound_to_the_exact_proposed_plan(tmp_path: Path) -> None:
    app = BrowserApp(tmp_path / "browser")
    inputs, _ = prepared(app)
    first = plan(app, inputs["dataset_id"])
    second = plan(app, inputs["dataset_id"])
    assert first["case_id"] != second["case_id"]
    second["approval"] = first["approval"]
    assert app.dispatch("/api/workflow/run", second)["status"] == 409
    assert good(app, "/api/state")["runs"] == []


def test_recorded_actions_survive_retry_export_and_browser_restore(
    tmp_path: Path,
) -> None:
    app = BrowserApp(tmp_path / "browser")
    inputs, _ = prepared(app)
    execution = plan(app, inputs["dataset_id"])
    assert good(app, "/api/state")["cases"] == []
    result = good(app, "/api/workflow/run", execution)
    run_id = result["run_id"]
    run = good(app, f"/api/runs/{run_id}")
    workflow = run["case"]["workflow"]
    assert run["case"]["schema_version"] == "2.1"
    assert run["workflow"] == {"status": "recorded", **workflow}
    assert workflow["records_selected"] is True
    assert workflow["source_accepted"] is True
    assert workflow["plan_approved"] is True
    assert workflow["source_snapshot_id"] is None
    assert workflow["source_sha256"] is None
    assert "signature" not in workflow
    retained_case = (app.root / "runs" / run_id / "case.json").read_bytes()
    assert good(app, "/api/workflow/run", execution)["run_id"] == run_id
    assert (app.root / "runs" / run_id / "case.json").read_bytes() == retained_case
    package = review_and_export(app, run_id)
    with zipfile.ZipFile(
        io.BytesIO(app.export_bytes(package["download_url"]))
    ) as bundle:
        assert bundle.read("run/case.json") == retained_case
        assert b"Workflow record" in bundle.read("report.html")
        assert b"Plan approved for execution" in bundle.read("report.md")
    restored = BrowserApp(tmp_path / "restored")
    assert restored.restore_bytes(app.backup_bytes())["status"] == 200
    assert good(restored, f"/api/runs/{run_id}")["workflow"] == run["workflow"]
    assert good(restored, "/api/workflow/run", execution)["reused"]
    assert good(restored, f"/api/runs/{run_id}/replay", {})["ok"]


def test_legacy_cases_keep_their_original_shape_and_have_no_implied_approvals(
    workspace,
) -> None:
    case = workspace.get_case("case-1")
    assert "workflow" not in case
    assert canonical_json(
        Case.model_validate(case).model_dump(mode="json")
    ) == canonical_json(case)
    assert "workflow" not in json.loads(Case.model_validate(case).model_dump_json())
    result = workspace.run_case("case-1")
    run = workspace.get_run(result["run_id"])
    assert run["workflow"] == {
        "status": "not_recorded",
        "records_selected": False,
        "source_accepted": False,
        "plan_approved": False,
    }
    assert run["case"] == case
    assert workspace.replay_run(result["run_id"])["ok"]


@pytest.mark.parametrize("field", ["dataset_sha256", "source_sha256"])
def test_integrity_verification_binds_approval_to_actual_retained_inputs(
    tmp_path: Path, field: str
) -> None:
    app = BrowserApp(tmp_path / "browser")
    inputs, _ = prepared(app)
    execution = plan(app, inputs["dataset_id"])
    result = good(app, "/api/workflow/run", execution)
    run_id = result["run_id"]
    directory = app.root / "runs" / run_id
    case_path = directory / "case.json"
    case = read_json(case_path)
    case["workflow"][field] = "f" * 64
    if field == "source_sha256":
        # A source digest without a selected source is also a malformed receipt.
        expected = "Source identity and digest"
    else:
        expected = "differs from retained dataset"
    write_json(case_path, case)
    manifest_path = directory / "manifest.json"
    manifest = read_json(manifest_path)
    for item in manifest["files"]:
        if item["path"] == "case.json":
            item["sha256"] = sha256_file(case_path)
            item["size_bytes"] = case_path.stat().st_size
    write_json(manifest_path, manifest)
    run = good(app, f"/api/runs/{run_id}")
    assert run["verification"]["ok"] is False
    assert any(expected in issue for issue in run["verification"]["issues"])
    assert run["workflow"]["status"] == "invalid"
    assert not any(
        run["workflow"][key]
        for key in ("records_selected", "source_accepted", "plan_approved")
    )

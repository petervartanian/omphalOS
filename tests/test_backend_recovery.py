"""Failures and lost responses must not strand an otherwise valid investigation."""

from test_guided_web import import_preview, plan, preview, run_payload
from test_web import browser as browser
from test_workflow import workspace as workspace

from omphalos.workflow import import_subject


def approved_run(request):
    status, imported, _ = import_preview(request, preview(request))
    assert status == 200
    inputs, prepared = plan(request, imported["dataset_id"])
    return run_payload(request, inputs, prepared), prepared


def test_same_approved_plan_can_retry_after_execution_fails(browser, monkeypatch):
    server, request = browser
    payload, _ = approved_run(request)
    execute = server.workspace.run_case
    attempts = 0

    def fail_once(case_id):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("Injected temporary failure")
        return execute(case_id)

    monkeypatch.setattr(server.workspace, "run_case", fail_once)
    assert request("/api/workflow/run", payload)[0] == 500
    case_path = server.root / "cases" / f"{payload['case_id']}.json"
    preserved = case_path.read_bytes()
    assert not list((server.root / "runs").iterdir())
    status, result, _ = request("/api/workflow/run", payload)
    assert status == 200 and result["verification"]["ok"], result
    assert attempts == 2 and case_path.read_bytes() == preserved
    assert len(list((server.root / "runs").iterdir())) == 1


def test_retry_recovers_run_committed_before_response_failure(browser, monkeypatch):
    server, request = browser
    payload, _ = approved_run(request)
    execute = server.workspace.run_case
    saved = {}

    def commit_then_fail(case_id):
        saved.update(execute(case_id))
        raise OSError("Injected failure after result was retained")

    monkeypatch.setattr(server.workspace, "run_case", commit_then_fail)
    assert request("/api/workflow/run", payload)[0] == 500
    status, recovered, _ = request("/api/workflow/run", payload)
    assert status == 200 and recovered["reused"] is True, recovered
    assert recovered["run_id"] == saved["run_id"]
    assert recovered["analysis_digest"] == saved["analysis_digest"]
    assert recovered["verification"]["ok"]
    assert len(list((server.root / "runs").iterdir())) == 1


def test_retry_never_overwrites_a_case_edited_after_failure(browser, monkeypatch):
    server, request = browser
    payload, prepared = approved_run(request)

    def unavailable(_case_id):
        raise OSError("Injected temporary failure")

    monkeypatch.setattr(server.workspace, "run_case", unavailable)
    assert request("/api/workflow/run", payload)[0] == 500
    modified = {
        **prepared["case"],
        "question": "A separately edited investigation purpose.",
    }
    server.workspace.save_case(modified)
    status, result, _ = request("/api/workflow/run", payload)
    assert status == 409 and "changed" in result["error"]
    assert server.workspace.get_case(payload["case_id"]) == modified
    assert not list((server.root / "runs").iterdir())


def test_preexisting_case_is_not_adopted_as_a_guided_retry(browser):
    server, request = browser
    payload, prepared = approved_run(request)
    server.workspace.save_case(prepared["case"])
    status, result, _ = request("/api/workflow/run", payload)
    assert status == 409 and "already exists" in result["error"]
    assert not list((server.root / "runs").iterdir())


def test_completed_but_damaged_result_is_not_replaced_by_retry(browser):
    server, request = browser
    payload, _ = approved_run(request)
    status, saved, _ = request("/api/workflow/run", payload)
    assert status == 200
    analysis = server.root / "runs" / saved["run_id"] / "analysis.json"
    analysis.write_bytes(analysis.read_bytes() + b" ")
    status, result, _ = request("/api/workflow/run", payload)
    assert status == 409 and "integrity verification" in result["error"]
    assert len(list((server.root / "runs").iterdir())) == 1


def test_run_summary_uses_archived_dataset_after_current_case_changes(workspace):
    result = workspace.run_case("case-1")
    original = workspace.get_case("case-1")
    import_subject("A different retained subject", workspace.root / "datasets/other")
    workspace.save_case({**original, "dataset_id": "other"})
    summary = workspace.list_runs(verify_reviews=False)[0]
    assert summary["run_id"] == result["run_id"]
    assert summary["dataset_id"] == original["dataset_id"]
    assert summary["verification_status"] == "not_checked"

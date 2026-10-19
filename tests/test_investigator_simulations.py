"""Synthetic investigator exercises across review, reopening, and handoff."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_case_review import case_review
from test_sources_screening import csl_payload
from test_workflow import workspace as workspace

from omphalos import evidence, runner
from omphalos.runner import Workspace
from omphalos.sources import import_source
from omphalos.util import OmphalOSError, canonical_json, write_json


def test_zero_observations_with_no_screening_coverage_remain_explicit(
    workspace: Workspace,
) -> None:
    case = workspace.get_case("case-1")
    workspace.save_case(
        {**case, "investigations": ["screening_candidates"], "parameters": {}}
    )
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    assert run["analysis"]["findings"] == []
    coverage = run["analysis"]["coverage"][0]
    assert coverage["status"] == "not_evaluable"
    assert coverage["records_evaluated"] == 0
    assert "snapshot is required" in coverage["reason"]
    with pytest.raises(OmphalOSError, match="review"):
        workspace.export_run(run_id)

    decision = case_review(
        run,
        "keep_open",
        "Obtain a current official list before assessing this synthetic subject.",
    )
    workspace.save_review(run_id, decision)
    result = workspace.export_run(run_id)
    with zipfile.ZipFile(result["path"]) as bundle:
        for name in ("report.html", "report.md"):
            report = bundle.read(name).decode()
            assert "Keep investigation open" in report
            assert "Not evaluated" in report
            assert coverage["reason"] in report
    reopened = Workspace(workspace.root).get_run(run_id)
    assert reopened["latest_review"]["review"] == decision
    assert reopened["latest_export"]["name"] == result["name"]


def test_same_name_different_country_is_retained_as_candidate_not_nonmatch(
    workspace: Workspace,
    tmp_path: Path,
) -> None:
    raw = tmp_path / "synthetic-csl.json"
    write_json(raw, csl_payload())
    import_source("csl", raw, workspace.root / "sources" / "synthetic-csl")
    case = workspace.get_case("case-1")
    workspace.save_case(
        {
            **case,
            "investigations": ["screening_candidates"],
            "parameters": {},
            "watchlist_snapshot_id": "synthetic-csl",
            "as_of": "2026-10-13",
        }
    )
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    findings = run["analysis"]["findings"]
    counterpart = next(row for row in findings if row["entity_ids"] == ["E2"])
    assert counterpart["metrics"]["name_similarity"] == "1.0000"
    assert counterpart["metrics"]["country_context"] == "differs"
    assert "requires identity review" in counterpart["observation"]
    original_analysis = canonical_json(run["analysis"])
    workspace.save_review(
        run_id,
        case_review(
            run,
            "keep_open",
            "Country differs, but obtain authoritative identifiers before deciding identity.",
        ),
    )
    result = workspace.export_run(run_id)
    with zipfile.ZipFile(result["path"]) as bundle:
        assert (
            canonical_json(json.loads(bundle.read("run/analysis.json")))
            == original_analysis
        )
        report = bundle.read("report.md").decode()
        assert "Keep investigation open" in report
        assert "no individual dispositions are recorded" in report
        assert "requires identity review" in report
    assert evidence.verify_bundle(Path(result["path"]))["ok"]


def test_reopened_case_can_record_new_decision_without_reusing_old_package(
    workspace: Workspace,
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    closed = workspace.save_review(
        run_id,
        case_review(
            run,
            "conclude",
            "This synthetic exercise ends with the stated evidence limitations retained.",
        ),
    )
    old_export = workspace.export_run(run_id)
    reopened = Workspace(workspace.root)
    revised = reopened.save_review(
        run_id,
        case_review(
            reopened.get_run(run_id),
            "keep_open",
            "New correspondence requires further investigation of the retained observations.",
        ),
    )
    shown = reopened.get_run(run_id)
    assert shown["latest_review"]["review_id"] == revised["review_id"]
    assert shown["latest_export"] is None
    assert Path(closed["path"]).is_file()
    assert evidence.verify_bundle(Path(old_export["path"]))["ok"]
    replacement = reopened.export_run(run_id)
    assert replacement["review_id"] == revised["review_id"]
    assert replacement["name"] != old_export["name"]


def test_changed_case_inputs_require_a_new_run_decision(
    workspace: Workspace,
) -> None:
    original_id = workspace.run_case("case-1")["run_id"]
    original = workspace.get_run(original_id)
    workspace.save_review(original_id, case_review(original, "escalate"))
    prior_export = workspace.export_run(original_id)

    current_case = workspace.get_case("case-1")
    workspace.save_case({**current_case, "scope": {"entity_ids": ["E4"]}})
    replacement_id = workspace.run_case("case-1")["run_id"]
    replacement = workspace.get_run(replacement_id)
    assert replacement["latest_review"] is None
    assert replacement["latest_export"] is None
    with pytest.raises(OmphalOSError, match="review"):
        workspace.export_run(replacement_id)
    with pytest.raises(OmphalOSError, match="different run"):
        workspace.save_review(replacement_id, case_review(original))
    retained = workspace.get_run(original_id)
    assert retained["case"] == original["case"]
    assert retained["latest_export"]["name"] == prior_export["name"]
    assert workspace.replay_run(original_id)["ok"]


@pytest.mark.parametrize(
    "revised_at",
    ["2026-10-18T14:00:00.000000Z", "2026-10-18T13:59:00.000000Z"],
    ids=["same-clock-tick", "clock-corrected-backward"],
)
def test_latest_saved_decision_survives_clock_collision_or_correction(
    workspace: Workspace,
    monkeypatch: pytest.MonkeyPatch,
    revised_at: str,
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)

    def save_at(when: str, ids: list[str], payload: dict) -> dict:
        generated = iter(ids)
        with monkeypatch.context() as patch:
            patch.setattr(runner, "utc_now", lambda: when)
            patch.setattr(
                runner.uuid, "uuid4", lambda: SimpleNamespace(hex=next(generated))
            )
            return workspace.save_review(run_id, payload)

    first = save_at(
        "2026-10-18T14:00:00.000000Z",
        ["f" * 32, "e" * 32],
        case_review(
            run, "conclude", "Synthetic review is concluded with limitations retained."
        ),
    )
    prior_export = workspace.export_run(run_id)
    revised = save_at(
        revised_at,
        ["a" * 32, "b" * 32],
        case_review(
            run, "escalate", "New evidence requires escalation and further review."
        ),
    )
    assert Path(first["path"]).is_file()
    assert evidence.verify_bundle(Path(prior_export["path"]))["ok"]
    reopened = Workspace(workspace.root).get_run(run_id)
    assert reopened["latest_review"]["review_id"] == revised["review_id"]
    assert reopened["latest_review"]["review"]["decision"] == "escalate"
    assert reopened["latest_export"] is None
    result = workspace.export_run(run_id)
    assert result["review_id"] == revised["review_id"]


@pytest.mark.parametrize("schema_version", ["2.1", "2.2"])
def test_inventory_exposes_recorded_decision_without_claiming_verification(
    workspace: Workspace,
    monkeypatch: pytest.MonkeyPatch,
    schema_version: str,
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    payload = case_review(
        workspace.get_run(run_id),
        "escalate",
        "Send the synthetic observations for additional identity research.",
    )
    payload["schema_version"] = schema_version
    saved = workspace.save_review(run_id, payload)

    def cannot_validate(*_args, **_kwargs):
        pytest.fail("A lightweight inventory must defer evidence validation.")

    with monkeypatch.context() as patch:
        patch.setattr(evidence, "validate_review", cannot_validate)
        summary = workspace.list_runs(verify_reviews=False)[0]
    assert summary["case_decision"] == "escalate"
    assert summary["reviewed_by"] == payload["reviewer"]
    assert summary["reviewed_at"] == saved["created_at"]
    assert summary["status"] == "review_recorded"
    assert summary["review_validation"]["status"] == "not_checked"
    assert summary["verification_status"] == "not_checked"
    assert summary["review_validation"]["ok"] is False


def test_inventory_does_not_invent_a_decision_for_legacy_or_unreviewed_runs(
    workspace: Workspace,
) -> None:
    from test_workflow import fixture_review

    run_id = workspace.run_case("case-1")["run_id"]
    pending = workspace.list_runs(verify_reviews=False)[0]
    assert pending["case_decision"] is None
    assert pending["reviewed_by"] is None
    assert pending["reviewed_at"] is None
    saved = workspace.save_review(run_id, fixture_review(workspace.get_run(run_id)))
    reviewed = workspace.list_runs(verify_reviews=False)[0]
    assert reviewed["case_decision"] is None
    assert reviewed["reviewed_by"] == saved["review"]["reviewer"]
    assert reviewed["reviewed_at"] == saved["created_at"]


@pytest.mark.parametrize("damaged_revision", ["latest", "earlier"])
def test_new_decision_cannot_hide_invalid_review_history(
    workspace: Workspace,
    damaged_revision: str,
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    first = workspace.save_review(run_id, case_review(run, "keep_open"))
    last = workspace.save_review(run_id, case_review(run, "escalate"))
    damaged = first if damaged_revision == "earlier" else last
    path = Path(damaged["path"])
    wrapper = json.loads(path.read_bytes())
    wrapper["review"]["reviewer"] = ""
    write_json(path, wrapper)
    before = set(path.parent.glob("*.json"))
    with pytest.raises(OmphalOSError, match="review history"):
        workspace.save_review(run_id, case_review(run, "keep_open"))
    assert set(path.parent.glob("*.json")) == before
    summary = workspace.list_runs(verify_reviews=False)[0]
    assert summary["case_decision"] is None
    assert summary["reviewed_by"] is None
    assert summary["reviewed_at"] is None
    assert summary["review_validation"]["status"] == "invalid"


def test_legacy_whole_second_timestamp_cannot_sort_after_a_later_instant(
    workspace: Workspace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    first = workspace.save_review(run_id, case_review(run))
    wrapper = json.loads(Path(first["path"]).read_bytes())
    wrapper["created_at"] = "2026-10-18T14:00:00Z"
    write_json(Path(first["path"]), wrapper)
    retained_bytes = Path(first["path"]).read_bytes()
    monkeypatch.setattr(runner, "utc_now", lambda: "2026-10-18T14:00:00.500000Z")
    revised = workspace.save_review(run_id, case_review(run, "escalate"))
    assert Path(first["path"]).read_bytes() == retained_bytes
    assert revised["created_at"] == "2026-10-18T14:00:00.500000Z"
    assert (
        workspace.get_run(run_id)["latest_review"]["review_id"] == revised["review_id"]
    )
    assert workspace.export_run(run_id)["review_id"] == revised["review_id"]


def test_revision_order_survives_browser_backup_and_restore(
    workspace: Workspace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omphalos.browser import BrowserApp
    from omphalos.data import create_demo

    original = BrowserApp(tmp_path / "original-browser")
    create_demo(original.root / "datasets" / "demo")
    original.context.workspace.save_case(workspace.get_case("case-1"))
    workspace = original.context.workspace
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    monkeypatch.setattr(runner, "utc_now", lambda: "2026-10-18T14:00:00.000000Z")
    first = workspace.save_review(run_id, case_review(run, "keep_open"))
    second = workspace.save_review(run_id, case_review(run, "escalate"))
    package = workspace.export_run(run_id)
    restored = BrowserApp(tmp_path / "restored-browser")
    assert restored.restore_bytes(original.backup_bytes())["status"] == 200
    reopened = Workspace(restored.root)
    shown = reopened.get_run(run_id)
    assert shown["latest_review"]["review_id"] == second["review_id"]
    assert shown["latest_export"]["name"] == package["name"]
    third = reopened.save_review(run_id, case_review(shown, "keep_open"))
    assert first["created_at"] < second["created_at"] < third["created_at"]
    assert reopened.get_run(run_id)["latest_review"]["review_id"] == third["review_id"]
    assert reopened.get_run(run_id)["latest_export"] is None
    assert reopened.export_run(run_id)["review_id"] == third["review_id"]

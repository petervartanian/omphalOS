"""Case decisions preserve analysis without inventing individual assessments."""

from __future__ import annotations

import argparse
import html
import json
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_evidence import make_run
from test_workflow import fixture_review
from test_workflow import workspace as workspace

from omphalos import evidence
from omphalos.cli import dispatch
from omphalos.models import CaseReview, Review, parse_review
from omphalos.runner import Workspace
from omphalos.util import (
    OmphalOSError,
    canonical_json,
    read_json,
    sha256_bytes,
    write_json,
)


def case_review(run: dict, decision: str = "keep_open", note: str = "") -> dict:
    return {
        "schema_version": "2.1",
        "run_id": run["manifest"]["run_id"],
        "reviewer": "Synthetic case reviewer",
        "decision": decision,
        "summary": note,
        "scope_finding_ids": [
            finding["finding_id"] for finding in run["analysis"]["findings"]
        ],
        "acknowledge_limitations": True,
    }


@pytest.mark.parametrize(
    ("decision", "note"),
    [
        ("keep_open", ""),
        ("escalate", ""),
        (
            "conclude",
            "End this synthetic exercise; no operational clearance is being issued.",
        ),
    ],
)
def test_case_decision_save_reopen_export_without_individual_judgments(
    workspace: Workspace, decision: str, note: str
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    original_analysis = canonical_json(run["analysis"])
    payload = case_review(run, decision, note)
    saved = workspace.save_review(run_id, payload)
    assert saved["review"] == payload
    assert "findings" not in saved["review"]

    reopened = Workspace(workspace.root)
    retained = reopened.get_run(run_id)
    assert retained["review_validation"]["ok"]
    assert retained["latest_review"]["review"] == payload
    assert canonical_json(retained["analysis"]) == original_analysis
    assert reopened.list_runs()[0]["status"] == "reviewed"
    assert reopened._review_state(run_id, verify_reviews=False)[0]["review"] == payload

    result = reopened.export_run(run_id)
    assert result["verification"]["ok"]
    assert evidence.verify_bundle(Path(result["path"]))["ok"]
    with zipfile.ZipFile(result["path"]) as archive:
        archived_review = json.loads(archive.read("review.json"))["review"]
        assert archived_review == payload
        assert (
            canonical_json(json.loads(archive.read("run/analysis.json")))
            == original_analysis
        )
        for report_name in ("report.html", "report.md"):
            report = archive.read(report_name).decode()
            assert "Case decision" in report
            assert "no individual dispositions are recorded" in report
            assert "not statements authored or individually adopted" in report
            assert "Reasoning" not in report
            if note:
                assert "Case note" in report
                assert html.escape(note, quote=True) in report
            else:
                assert "Case note" not in report
            for finding in run["analysis"]["findings"]:
                assert html.escape(finding["observation"], quote=True) in report
                for field in ("unknowns", "alternatives", "falsifiers"):
                    assert html.escape(finding[field][0], quote=True) in report


def test_case_scope_is_exact_without_claiming_individual_assessments(
    workspace: Workspace,
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    payload = case_review(run)
    assert payload["scope_finding_ids"]
    for ids, message in (
        (payload["scope_finding_ids"][1:], "omitted from assessment scope"),
        (payload["scope_finding_ids"] + ["absent"], "Unknown findings"),
        (
            payload["scope_finding_ids"] + payload["scope_finding_ids"][:1],
            "must not repeat",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            workspace.save_review(run_id, {**payload, "scope_finding_ids": ids})
    assert workspace.get_run(run_id)["latest_review"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"reviewer": ""},
        {"reviewer": " "},
        {"reviewer": False},
        {"acknowledge_limitations": False},
        {"acknowledge_limitations": 1},
        {"acknowledge_limitations": "true"},
        {"decision": "explained"},
        {"decision": "conclude"},
        {"summary": "Too short"},
        {"summary": "TODO TODO TODO"},
        {"summary": ".............."},
        {"summary": None},
        {"findings": []},
        {"schema_version": "2.2"},
    ],
)
def test_case_contract_rejects_implicit_or_invalid_decisions(change: dict) -> None:
    payload = {
        "schema_version": "2.1",
        "run_id": "run-one",
        "reviewer": "Synthetic case reviewer",
        "decision": "keep_open",
        "scope_finding_ids": [],
        "acknowledge_limitations": True,
    }
    with pytest.raises(ValidationError):
        parse_review({**payload, **change})


@pytest.mark.parametrize(
    "missing", ["reviewer", "decision", "scope_finding_ids", "acknowledge_limitations"]
)
def test_case_contract_requires_explicit_fields(missing: str) -> None:
    payload = {
        "schema_version": "2.1",
        "run_id": "run-one",
        "reviewer": "Synthetic case reviewer",
        "decision": "keep_open",
        "scope_finding_ids": [],
        "acknowledge_limitations": True,
    }
    del payload[missing]
    with pytest.raises(ValidationError):
        parse_review(payload)


def test_case_note_is_optional_and_escaped_in_reports(workspace: Workspace) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    payload = case_review(run)
    del payload["summary"]
    assert parse_review(payload).summary == ""
    payload["summary"] = '<img src=x onerror="alert(1)"> is literal test text.'
    workspace.save_review(run_id, payload)
    result = workspace.export_run(run_id)
    with zipfile.ZipFile(result["path"]) as archive:
        for name in ("report.html", "report.md"):
            report = archive.read(name).decode()
            assert '<img src=x onerror="alert(1)">' not in report
            assert html.escape(payload["summary"], quote=True) in report


def test_legacy_review_and_case_revision_remain_independently_exportable(
    workspace: Workspace,
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    legacy = fixture_review(run)
    assert isinstance(parse_review(legacy), Review)
    old = workspace.save_review(run_id, legacy)
    prior_bytes = Path(old["path"]).read_bytes()
    current = workspace.save_review(run_id, case_review(run))
    assert isinstance(parse_review(current["review"]), CaseReview)
    assert Path(old["path"]).read_bytes() == prior_bytes
    for revision in (old, current):
        exported = workspace.export_run(run_id, review_id=revision["review_id"])
        assert exported["verification"]["ok"]
    del legacy["schema_version"]
    assert parse_review(legacy).schema_version == "2.0"


def test_case_decision_requires_run_binding_and_integrity(workspace: Workspace) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    payload = case_review(run)
    with pytest.raises(OmphalOSError, match="different run"):
        workspace.save_review(run_id, {**payload, "run_id": "wrong-run"})
    workspace.save_review(run_id, payload)
    path = workspace.root / "runs" / run_id / "analysis.json"
    path.write_bytes(path.read_bytes() + b" ")
    assert not workspace.get_run(run_id)["verification"]["ok"]
    with pytest.raises(OmphalOSError, match="damaged or incomplete"):
        workspace.save_review(run_id, payload)
    with pytest.raises(OmphalOSError):
        workspace.export_run(run_id)


def test_case_scope_tampering_does_not_reopen_as_recorded(workspace: Workspace) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    saved = workspace.save_review(run_id, case_review(workspace.get_run(run_id)))
    path = Path(saved["path"])
    wrapper = read_json(path)
    wrapper["review"]["scope_finding_ids"] = []
    write_json(path, wrapper)
    retained = Workspace(workspace.root).get_run(run_id)
    assert retained["latest_review"] is None
    assert not retained["review_validation"]["ok"]
    assert workspace.list_runs()[0]["status"] == "awaiting_review"
    with pytest.raises(OmphalOSError):
        workspace.export_run(run_id)


def test_case_review_still_resolves_each_original_evidence_reference(
    tmp_path: Path,
) -> None:
    root = tmp_path / "run"
    manifest, _ = make_run(root)
    analysis = read_json(root / "analysis.json")
    payload = case_review({"manifest": manifest, "analysis": analysis})
    analysis["findings"][0]["record_refs"][0]["record_id"] = "ABSENT"
    write_json(root / "analysis.json", analysis)
    (root / "manifest.json").unlink()
    evidence.build_manifest(
        root,
        run_id=manifest["run_id"],
        case_id=manifest["case_id"],
        analysis_digest=sha256_bytes(canonical_json(analysis)),
    )
    result = evidence.validate_review(root, payload)
    assert not result["ok"]
    assert "Unresolved evidence" in " ".join(result["issues"])


def test_zero_findings_case_still_requires_an_explicit_decision(tmp_path: Path) -> None:
    root = tmp_path / "run"
    manifest, _ = make_run(root, finding=False)
    payload = case_review({"manifest": manifest, "analysis": {"findings": []}})
    assert evidence.validate_review(root, payload)["ok"]
    del payload["decision"]
    assert not evidence.validate_review(root, payload)["ok"]


def test_review_schema_advertises_both_contracts(tmp_path: Path) -> None:
    schema = dispatch(
        argparse.Namespace(command="schema", kind="review", workspace=tmp_path)
    )
    assert schema["discriminator"]["propertyName"] == "schema_version"
    assert set(schema["discriminator"]["mapping"]) == {"2.0", "2.1", "2.2"}


@pytest.mark.parametrize("decision", ["keep_open", "escalate", "conclude"])
@pytest.mark.parametrize("note", [None, "", "Too short", "TODO TODO TODO"])
def test_current_case_decision_requires_an_explained_next_step(
    workspace: Workspace, decision: str, note: str | None
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    payload = case_review(workspace.get_run(run_id), decision)
    payload["schema_version"] = "2.2"
    if note is None:
        del payload["summary"]
    else:
        payload["summary"] = note
    with pytest.raises(ValueError):
        workspace.save_review(run_id, payload)
    assert workspace.get_run(run_id)["latest_review"] is None


@pytest.mark.parametrize(
    ("decision", "note"),
    [
        ("keep_open", "Obtain the full ledger before evaluating the volume change."),
        (
            "escalate",
            "Ask the identity specialist to reconcile the conflicting registry IDs.",
        ),
        (
            "conclude",
            "The retained invoices reconcile; this concludes only the sampled review.",
        ),
    ],
)
def test_current_decision_retains_reason_through_reopen_and_handoff(
    workspace: Workspace, decision: str, note: str
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    payload = {
        **case_review(workspace.get_run(run_id), decision, note),
        "schema_version": "2.2",
    }
    saved = workspace.save_review(run_id, payload)
    reopened = Workspace(workspace.root)
    assert reopened.get_run(run_id)["latest_review"]["review"] == payload
    exported = reopened.export_run(run_id)
    assert exported["verification"]["ok"]
    with zipfile.ZipFile(exported["path"]) as archive:
        assert json.loads(archive.read("review.json"))["review"] == payload
        assert saved["review_id"] in archive.read("report.html").decode()
        assert note in archive.read("report.md").decode()


def test_new_decision_keeps_legacy_empty_note_review_exportable(
    workspace: Workspace,
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    old = workspace.save_review(run_id, case_review(run))
    old_bytes = Path(old["path"]).read_bytes()
    payload = {
        **case_review(
            run,
            "escalate",
            "Reconcile the unresolved identifier before any further action.",
        ),
        "schema_version": "2.2",
    }
    current = workspace.save_review(run_id, payload)
    assert Path(old["path"]).read_bytes() == old_bytes
    assert (
        workspace.get_run(run_id)["latest_review"]["review_id"] == current["review_id"]
    )
    for revision in (old, current):
        assert workspace.export_run(run_id, review_id=revision["review_id"])[
            "verification"
        ]["ok"]

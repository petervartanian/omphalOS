"""Workspace listings defer retained-evidence reads without claiming verification."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_evidence import make_run
from test_web import browser as browser

from omphalos import evidence
from omphalos.runner import Workspace
from omphalos.util import OmphalOSError, read_json, write_json


def retained_run(workspace: Workspace, *, reviewed: bool = True) -> dict | None:
    _, review = make_run(workspace.root / "runs" / "run_demo")
    return workspace.save_review("run_demo", review) if reviewed else None


def reject_evidence_reads(monkeypatch: pytest.MonkeyPatch, workspace: Workspace):
    """Model an unavailable archive without reading any of its large files."""
    original_open = Path.open
    run_directory = workspace.root / "runs" / "run_demo"

    def metadata_only(path: Path, *args, **kwargs):
        if path.is_relative_to(run_directory):
            relative = path.relative_to(run_directory).as_posix()
            assert relative in {
                "manifest.json",
                "analysis.json",
                "case.json",
            }, f"Workspace listing opened retained evidence: {relative}"
        return original_open(path, *args, **kwargs)

    def cannot_verify(*_args, **_kwargs):
        pytest.fail("Workspace listing attempted full evidence or review validation")

    monkeypatch.setattr(Path, "open", metadata_only)
    monkeypatch.setattr(evidence, "verify_run", cannot_verify)
    monkeypatch.setattr(evidence, "validate_review", cannot_verify)


def test_lightweight_summary_never_reads_archived_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = Workspace(tmp_path / "workspace")
    retained_run(workspace)
    reject_evidence_reads(monkeypatch, workspace)

    summary = workspace.list_runs(verify_reviews=False)[0]

    assert summary["run_id"] == "run_demo"
    assert summary["case_id"] == "case_demo"
    assert summary["findings_count"] == 1
    assert summary["status"] == "review_recorded"
    assert summary["verification_status"] == "not_checked"
    assert summary["review_validation"] == {
        "ok": False,
        "status": "not_checked",
        "issues": [],
    }


def test_workspace_state_remains_available_without_archive_reads(
    browser, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, request = browser
    retained_run(server.workspace)
    reject_evidence_reads(monkeypatch, server.workspace)

    status, state, _ = request("/api/state")

    assert status == 200
    assert state["runs"][0]["status"] == "review_recorded"
    assert state["runs"][0]["review_validation"]["status"] == "not_checked"
    assert state["runs"][0]["verification_status"] == "not_checked"


def test_listing_without_review_does_not_suggest_an_assessment_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = Workspace(tmp_path / "workspace")
    retained_run(workspace, reviewed=False)
    reject_evidence_reads(monkeypatch, workspace)

    summary = workspace.list_runs(verify_reviews=False)[0]

    assert summary["status"] == "awaiting_review"
    assert summary["review_validation"] == {
        "ok": False,
        "status": "awaiting_review",
        "issues": [],
    }


@pytest.mark.parametrize(
    "damage", ["anchor", "filename", "timestamp", "run_id", "structure", "json"]
)
def test_lightweight_summary_rejects_invalid_review_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    workspace = Workspace(tmp_path / "workspace")
    saved = retained_run(workspace)
    assert saved is not None
    path = Path(saved["path"])
    wrapper = read_json(path)
    if damage == "anchor":
        wrapper["run_manifest_sha256"] = "0" * 64
    elif damage == "filename":
        wrapper["review_id"] = "different-review"
    elif damage == "timestamp":
        wrapper["created_at"] = "not-a-timestampZ"
    elif damage == "run_id":
        wrapper["review"]["run_id"] = "another-run"
    elif damage == "structure":
        wrapper["review"]["reviewer"] = ""
    if damage == "json":
        path.write_text("{incomplete", encoding="utf-8")
    else:
        write_json(path, wrapper)
    reject_evidence_reads(monkeypatch, workspace)

    summary = workspace.list_runs(verify_reviews=False)[0]

    assert summary["status"] == "awaiting_review"
    assert summary["review_validation"]["ok"] is False
    assert summary["review_validation"]["status"] == "invalid"
    assert summary["review_validation"]["issues"]
    assert summary["verification_status"] == "not_checked"


def test_deferred_summary_does_not_weaken_full_validation_or_export(
    tmp_path: Path,
) -> None:
    workspace = Workspace(tmp_path / "workspace")
    retained_run(workspace)
    assert workspace.list_runs()[0]["status"] == "reviewed"

    # Metadata still records the review after evidence is damaged, but it must
    # never present the unchecked record as verified or allow an evidence export.
    dataset_path = workspace.root / "runs" / "run_demo" / "data" / "dataset.json"
    dataset_path.write_bytes(dataset_path.read_bytes() + b"\n")

    summary = workspace.list_runs(verify_reviews=False)[0]
    assert summary["status"] == "review_recorded"
    assert summary["review_validation"]["ok"] is False
    checked = workspace.list_runs()[0]
    assert checked["status"] == "awaiting_review"
    assert checked["review_validation"]["issues"]
    opened = workspace.get_run("run_demo")
    assert opened["verification"]["ok"] is False
    assert opened["latest_review"] is None
    with pytest.raises(OmphalOSError):
        workspace.export_run("run_demo")

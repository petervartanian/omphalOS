"""Regression tests for provenance, review state, and exact input contracts."""

from __future__ import annotations

import copy
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_evidence import make_run
from test_workflow import fixture_review
from test_workflow import workspace as workspace

from omphalos import runner
from omphalos.models import Analysis, Case, Review
from omphalos.runner import Workspace
from omphalos.util import OmphalOSError, read_json, safe_child, write_json


@pytest.mark.parametrize("damage", ["incomplete", "anchor", "timestamp", "json"])
def test_invalid_latest_review_never_appears_completed(
    workspace: Workspace, damage: str
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    first = workspace.save_review(run_id, fixture_review(run))
    second = workspace.save_review(run_id, fixture_review(run))
    path = Path(second["path"])
    wrapper = read_json(path)
    if damage == "incomplete":
        wrapper["review"]["findings"] = []
    elif damage == "anchor":
        wrapper["run_manifest_sha256"] = "0" * 64
    elif damage == "timestamp":
        wrapper["created_at"] = "not-a-dateZ"
    if damage == "json":
        path.write_text("{incomplete", encoding="utf-8")
    else:
        write_json(path, wrapper)
    shown = workspace.get_run(run_id)
    assert shown["latest_review"] is None
    assert not shown["review_validation"]["ok"]
    assert shown["review_validation"]["issues"]
    assert workspace.list_runs()[0]["status"] == "awaiting_review"
    with pytest.raises(OmphalOSError, match="review"):
        workspace.export_run(run_id)
    # A named, earlier intact revision remains independently exportable.
    assert workspace.export_run(run_id, review_id=first["review_id"])["verification"][
        "ok"
    ]


def test_replay_mismatch_does_not_claim_reproduction(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    result = copy.deepcopy(workspace.get_run(run_id)["analysis"])
    result["warnings"].append(
        "Synthetic regression: different recomputed coverage warning."
    )
    monkeypatch.setattr("omphalos.investigations.analyze", lambda *_: result)
    replay = workspace.replay_run(run_id)
    assert not replay["ok"]
    assert "did not reproduce" in replay["meaning"]


def test_changed_files_require_process_restart(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    inventory = {**runner.PROCESS_ENGINE_INVENTORY, "synthetic_change.py": "0" * 64}
    monkeypatch.setattr(runner, "engine_inventory", lambda: inventory)
    with pytest.raises(OmphalOSError, match="Restart"):
        workspace.run_case("case-1")
    replay = workspace.replay_run(run_id)
    assert not replay["ok"]
    assert "Restart" in " ".join(replay["issues"])
    assert len(workspace.list_runs()) == 1


def test_archived_code_must_match_process_snapshot(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_copy = runner.shutil.copyfile

    def changed_copy(source: Path, target: Path) -> str:
        result = original_copy(source, target)
        if Path(target).parent.name == "engine":
            Path(target).write_bytes(
                Path(target).read_bytes() + b"\n# synthetic copy error\n"
            )
        return result

    monkeypatch.setattr(runner.shutil, "copyfile", changed_copy)
    with pytest.raises(OmphalOSError, match="Archived engine bytes differ"):
        workspace.run_case("case-1")
    assert workspace.list_runs() == []


@pytest.mark.parametrize(
    "value",
    [
        0,
        True,
        1791849600,
        "2026-10-13T00:00:00Z",
        "20261013",
        datetime(2026, 10, 13, tzinfo=timezone.utc),
    ],
)
def test_dates_do_not_silently_coerce_to_scope(value: object) -> None:
    case = {
        "case_id": "case-1",
        "dataset_id": "dataset-1",
        "as_of": "2026-10-13",
        "question": "Which records require a documented follow-up?",
        "investigations": ["data_quality"],
    }
    with pytest.raises(ValidationError, match="YYYY-MM-DD"):
        Case.model_validate({**case, "as_of": value})
    with pytest.raises(ValidationError, match="YYYY-MM-DD"):
        Case.model_validate({**case, "scope": {"date_from": value}})
    assert Case.model_validate({**case, "as_of": date(2026, 10, 13)}).as_of == date(
        2026, 10, 13
    )


def test_analysis_numeric_domain_matches_independent_verifiers(tmp_path: Path) -> None:
    make_run(tmp_path / "run")
    original = read_json(tmp_path / "run/analysis.json")
    for value in (2**63, -(2**63) - 1, 1.25, float("inf")):
        analysis = copy.deepcopy(original)
        analysis["findings"][0]["metrics"]["exact_amount"] = value
        with pytest.raises(ValidationError):
            Analysis.model_validate(analysis)
    analysis = copy.deepcopy(original)
    analysis["scope_counts"]["entities"] = 2**63
    with pytest.raises(ValidationError):
        Analysis.model_validate(analysis)
    analysis = copy.deepcopy(original)
    analysis["findings"][0]["metrics"]["exact_amount"] = str(2**63)
    analysis["findings"][0]["metrics"]["max_int"] = 2**63 - 1
    analysis["findings"][0]["metrics"]["min_int"] = -(2**63)
    Analysis.model_validate(analysis)


@pytest.mark.parametrize(
    "summary", ["............", "TODO TODO TODO", "placeholder placeholder"]
)
def test_review_summary_rejects_obvious_placeholders(summary: str) -> None:
    with pytest.raises(ValidationError, match="case-specific reasoning"):
        Review.model_validate(
            {
                "run_id": "run-1",
                "reviewer": "Fixture reviewer",
                "summary": summary,
                "findings": [],
                "acknowledge_limitations": True,
            }
        )


def test_base_directory_links_do_not_redirect_workspace_writes(
    workspace: Workspace, tmp_path: Path
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    directory = workspace.root / "events"
    directory.rename(workspace.root / "events-original")
    try:
        directory.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("This host cannot create symbolic links")
    with pytest.raises(OmphalOSError, match="Symbolic links"):
        safe_child(directory, "test.json")
    with pytest.raises(OmphalOSError, match="Symbolic links"):
        workspace._event("synthetic_test", "case-1")
    assert list(external.iterdir()) == []


def test_json_number_overflow_rejected(tmp_path: Path) -> None:
    path = tmp_path / "overflow.json"
    path.write_text('{"value":1e99999}', encoding="utf-8")
    with pytest.raises(OmphalOSError, match="finite"):
        read_json(path)


def test_explicit_verification_does_not_create_workspace(tmp_path: Path) -> None:
    target = tmp_path / "run"
    make_run(target)
    unused = tmp_path / "unused-workspace"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "omphalos",
            "--workspace",
            str(unused),
            "verify",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not unused.exists()

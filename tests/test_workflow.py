"""End-to-end semantic checks through the public workspace and CLI boundaries."""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from omphalos.data import create_demo, import_dataset
from omphalos.evidence import verify_bundle
from omphalos.models import Case, Review
from omphalos.runner import Workspace
from omphalos.util import (
    OmphalOSError,
    canonical_json,
    read_json,
    safe_child,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    store = Workspace(tmp_path / "workspace")
    create_demo(store.root / "datasets" / "demo")
    store.save_case(
        {
            "case_id": "case-1",
            "dataset_id": "demo",
            "as_of": "2026-09-30",
            "question": "Which payment records need follow-up against contract terms?",
            "investigations": [
                "payment_fragmentation",
                "threshold_cluster",
                "unit_price_outlier",
                "screening_candidates",
            ],
            "parameters": {
                "threshold_cluster": {"threshold": "10000", "currency": "USD"}
            },
        }
    )
    return store


def fixture_review(run: dict) -> dict:
    return {
        "schema_version": "2.0",
        "run_id": run["manifest"]["run_id"],
        "reviewer": "Synthetic test reviewer",
        "summary": "Software fixture only: the planted records exercise review mechanics and are not an operational assessment.",
        "findings": [
            {
                "finding_id": f["finding_id"],
                "disposition": "follow_up",
                "rationale": "Synthetic fixture: request the contract and reconcile the cited payment references before resolving this observation.",
                "unknowns": [
                    "The synthetic fixture does not provide the actual contract terms."
                ],
                "alternatives": [
                    "Ordinary commercial installments could explain these payment records."
                ],
                "falsifiers": [
                    "A signed contract and reconciled invoices could disconfirm the concern."
                ],
            }
            for f in run["analysis"]["findings"]
        ],
        "acknowledge_limitations": True,
    }


def test_run_review_export_replay_from_retained_inputs(workspace: Workspace) -> None:
    result = workspace.run_case("case-1")
    run_id = result["run_id"]
    run = workspace.get_run(run_id)
    assert result["verification"]["ok"]
    assert result["findings_count"] > 0
    assert {r["investigation_id"] for r in run["analysis"]["coverage"]} == set(
        run["case"]["investigations"]
    )
    screening = next(
        r
        for r in run["analysis"]["coverage"]
        if r["investigation_id"] == "screening_candidates"
    )
    assert screening["status"] == "not_evaluable"
    assert screening["reason"]
    with pytest.raises(OmphalOSError, match="review"):
        workspace.export_run(run_id)
    workspace.save_review(run_id, fixture_review(run))
    exported = workspace.export_run(run_id)
    assert exported["verification"]["ok"]
    assert verify_bundle(Path(exported["path"]))["ok"]
    # Replay relies on the retained snapshot, not the original working dataset.
    source = workspace.root / "datasets" / "demo" / "dataset.json"
    source.rename(source.with_suffix(".unavailable"))
    assert workspace.replay_run(run_id)["ok"]


def test_concurrent_runs_unique_but_same_analysis(workspace: Workspace) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: workspace.run_case("case-1"), range(2)))
    assert results[0]["run_id"] != results[1]["run_id"]
    assert results[0]["analysis_digest"] == results[1]["analysis_digest"]
    assert all(workspace.verify_run(r["run_id"])["ok"] for r in results)


def test_scope_changes_actual_analysis_and_case_history(workspace: Workspace) -> None:
    first = workspace.run_case("case-1")
    case = workspace.get_case("case-1")
    case["scope"] = {
        "entity_ids": ["E4"],
        "domains": [],
        "date_from": None,
        "date_to": None,
    }
    workspace.save_case(case)
    second = workspace.run_case("case-1")
    assert first["analysis_digest"] != second["analysis_digest"]
    assert list((workspace.root / "cases" / "history" / "case-1").glob("*.json"))
    assert workspace.get_run(first["run_id"])["case"]["scope"]["entity_ids"] == []


def test_review_incomplete_rejected_and_revisions_preserved(
    workspace: Workspace,
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    review = fixture_review(run)
    review["findings"] = review["findings"][:-1]
    with pytest.raises(OmphalOSError, match="Unreviewed"):
        workspace.save_review(run_id, review)
    review = fixture_review(run)
    first = workspace.save_review(run_id, review)
    original_bytes = Path(first["path"]).read_bytes()
    review["summary"] += " Additional fixture review revision."
    second = workspace.save_review(run_id, review)
    assert first["review_id"] != second["review_id"]
    assert Path(first["path"]).read_bytes() == original_bytes
    assert workspace.export_run(run_id, review_id=first["review_id"])["verification"][
        "ok"
    ]


def test_tampered_run_blocks_review_export_and_replay(workspace: Workspace) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    review = fixture_review(run)
    workspace.save_review(run_id, review)
    path = workspace.root / "runs" / run_id / "analysis.json"
    path.write_bytes(path.read_bytes() + b" ")
    assert not workspace.verify_run(run_id)["ok"]
    assert not workspace.replay_run(run_id)["ok"]
    with pytest.raises(OmphalOSError):
        workspace.save_review(run_id, review)
    with pytest.raises(OmphalOSError):
        workspace.export_run(run_id)


def test_replay_reports_environment_mismatch(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = workspace.run_case("case-1")["run_id"]
    monkeypatch.setattr(
        "omphalos.runner.runtime_versions", lambda: {"pydantic": "different"}
    )
    result = workspace.replay_run(run_id)
    assert not result["ok"]
    assert any("dependency" in issue for issue in result["issues"])


def test_actual_csv_import_and_no_fabricated_finding(tmp_path: Path) -> None:
    source = tmp_path / "input"
    source.mkdir()
    (source / "entities.csv").write_text(
        "entity_id,name,country\nA,Independent Example,US\n", encoding="utf-8"
    )
    (source / "shipments.csv").write_text(
        "shipment_id,exporter_id,date\nS,A,2026-10-01\n", encoding="utf-8"
    )
    (source / "payments.csv").write_text(
        "payment_id,shipment_id,amount,ccy\nP,S,10.25,USD\n", encoding="utf-8"
    )
    store = Workspace(tmp_path / "workspace")
    metadata = import_dataset(source, store.root / "datasets" / "csv")
    assert not metadata["synthetic"]
    assert metadata["counts"]["payments"] == 1
    store.save_case(
        {
            "case_id": "one",
            "dataset_id": "csv",
            "as_of": "2026-10-13",
            "question": "Are several payments linked to the same shipment?",
            "investigations": ["payment_fragmentation"],
        }
    )
    result = store.run_case("one")
    run = store.get_run(result["run_id"])
    assert run["analysis"]["findings"] == []
    assert run["analysis"]["coverage"][0]["status"] == "executed"
    store.save_review(result["run_id"], fixture_review(run))
    assert store.export_run(result["run_id"])["verification"]["ok"]


@pytest.mark.parametrize(
    "bad", ["../escape", "/absolute", "x/../../y", "x\\y", "C:escape", "a/./b", "a//b"]
)
def test_contained_paths(tmp_path: Path, bad: str) -> None:
    with pytest.raises((ValueError, OSError)):
        safe_child(tmp_path, bad)


def test_case_contract_rejects_misleading_input() -> None:
    valid = {
        "case_id": "one",
        "dataset_id": "data",
        "as_of": "2026-10-13",
        "question": "Does the data contain an unusual payment pattern?",
        "investigations": ["payment_fragmentation"],
    }
    with pytest.raises(ValidationError):
        Case.model_validate({**valid, "investigations": ["payment_fragmentation"] * 2})
    with pytest.raises(ValidationError):
        Case.model_validate(
            {**valid, "scope": {"date_from": "2026-10-13", "date_to": "2025-01-01"}}
        )
    with pytest.raises(ValidationError):
        Case.model_validate({**valid, "parameters": {"unselected": {}}})
    with pytest.raises(ValidationError):
        Case.model_validate({**valid, "hidden_flag": True})


def test_review_acknowledgment_is_explicit() -> None:
    review = {
        "run_id": "run-1",
        "reviewer": "Synthetic reviewer",
        "summary": "The synthetic empty run was assessed for coverage limits.",
        "findings": [],
    }
    for value in (False, "true", 1):
        with pytest.raises(ValidationError):
            Review.model_validate({**review, "acknowledge_limitations": value})


@given(
    st.dictionaries(
        st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=20),
        st.integers(min_value=-(2**63), max_value=2**63 - 1),
        max_size=30,
    )
)
def test_canonical_json_roundtrip_and_order(value: dict) -> None:
    encoded = canonical_json(value)
    assert json.loads(encoded) == value
    assert canonical_json(dict(reversed(list(value.items())))) == encoded


def test_duplicate_keys_and_nonfinite_json_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(ValueError):
            read_json(path)


def test_cli_returns_machine_readable_error_and_schema(tmp_path: Path) -> None:
    base = [
        sys.executable,
        "-m",
        "omphalos",
        "--workspace",
        str(tmp_path / "workspace"),
    ]
    result = subprocess.run(
        base + ["schema", "case"], capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout)["title"] == "Case"
    result = subprocess.run(base + ["run", "missing"], capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stderr)["ok"] is False

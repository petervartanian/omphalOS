"""Receiving evidence must preserve bytes, local decisions, and usable continuation."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path

import pytest
from test_browser import good, plan, review_and_export
from test_case_review import case_review
from test_identity_workflow import provider as provider
from test_sources_screening import csl_payload
from test_workflow import workspace as workspace

from omphalos import collaboration
from omphalos.browser import BrowserApp
from omphalos.collaboration import HandoffConflict, import_package, inspect_package
from omphalos.data import load_dataset
from omphalos.identity_workflow import research_identity, select_identity
from omphalos.runner import Workspace
from omphalos.sources import import_source, load_source
from omphalos.util import OmphalOSError, sha256_bytes, write_json
from omphalos.workflow import import_subject


@pytest.fixture
def package(workspace: Workspace) -> tuple[Workspace, dict, bytes]:
    run_id = workspace.run_case("case-1")["run_id"]
    run = workspace.get_run(run_id)
    workspace.save_review(
        run_id,
        case_review(
            run,
            "keep_open",
            "Obtain contract terms and reconcile the retained payment records.",
        ),
    )
    exported = workspace.export_run(run_id)
    return workspace, workspace.get_run(run_id), Path(exported["path"]).read_bytes()


def test_inspect_does_not_change_workspace(package: tuple, tmp_path: Path) -> None:
    _, run, raw = package
    recipient = Workspace(tmp_path / "recipient")
    before = sorted(str(path) for path in recipient.root.rglob("*"))
    preview = inspect_package(raw)
    assert preview["package_sha256"] == sha256_bytes(raw)
    assert preview["run_id"] == run["manifest"]["run_id"]
    assert preview["analysis_digest"] == run["manifest"]["analysis_digest"]
    assert preview["review_id"] == run["latest_review"]["review_id"]
    assert preview["decision"] == "keep_open"
    assert preview["counts"] == run["dataset_metadata"]["counts"]
    assert preview["verification"]["ok"]
    assert preview["verification"]["authenticity"] == "not_assessed"
    assert sorted(str(path) for path in recipient.root.rglob("*")) == before


def test_handoff_preserves_run_sources_and_original_package_and_can_continue(
    package: tuple, tmp_path: Path
) -> None:
    sender, original, raw = package
    recipient = Workspace(tmp_path / "recipient")
    result = import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    assert result["imported"]
    run_id = result["run_id"]
    assert (
        recipient.get_run(run_id)["latest_review"]["review"]
        == original["latest_review"]["review"]
    )
    assert collaboration._tree_bytes(
        recipient.root / "runs" / run_id
    ) == collaboration._tree_bytes(sender.root / "runs" / run_id)
    assert (
        recipient.root / result["download_url"].removeprefix("/api/")
    ).read_bytes() == raw
    assert (
        recipient.list_runs()[0]["dataset_label"]
        == original["dataset_metadata"]["label"]
    )
    current = recipient.get_run(run_id)["latest_export"]
    assert current["download_url"] == result["download_url"]
    dataset = load_dataset(
        recipient.root / "datasets" / result["continuation_dataset_id"]
    )
    original_data = load_dataset(sender.root / "runs" / run_id / "data")
    assert dataset["tables"] == original_data["tables"]
    for field in ("provenance", "source_files", "counts", "intake_method"):
        assert dataset["metadata"][field] == original_data["metadata"][field]
    case = recipient.get_case(result["continuation_case_id"])
    assert "workflow" not in case
    continued = recipient.run_case(result["continuation_case_id"])
    assert continued["run_id"] != run_id
    assert recipient.get_run(continued["run_id"])["latest_review"] is None
    assert recipient.get_run(continued["run_id"])["latest_export"] is None
    assert (
        recipient.get_run(run_id)["latest_review"]["review"]
        == original["latest_review"]["review"]
    )


def test_handoff_copies_screening_snapshot_without_changing_original_bytes(
    workspace: Workspace, tmp_path: Path
) -> None:
    path = tmp_path / "list.json"
    write_json(path, csl_payload())
    import_source("csl", path, workspace.root / "sources" / "screen")
    workspace.save_case(
        {**workspace.get_case("case-1"), "watchlist_snapshot_id": "screen"}
    )
    run_id = workspace.run_case("case-1")["run_id"]
    workspace.save_review(run_id, case_review(workspace.get_run(run_id)))
    raw = Path(workspace.export_run(run_id)["path"]).read_bytes()
    recipient = Workspace(tmp_path / "recipient")
    imported = import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    copied = recipient.root / "sources" / imported["continuation_source_id"]
    original = workspace.root / "runs" / run_id / "sources"
    assert load_source(copied)["entries"] == load_source(original)["entries"]
    assert (copied / "raw.json").read_bytes() == (original / "raw.json").read_bytes()
    assert load_source(copied)["metadata"]["ingestion_method"] == "manual_import"


def test_exact_reimport_is_idempotent_and_never_reverts_newer_local_review(
    package: tuple, tmp_path: Path
) -> None:
    _, _, raw = package
    recipient = Workspace(tmp_path / "recipient")
    first = import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    run_id = first["run_id"]
    revision = recipient.save_review(
        run_id,
        case_review(
            recipient.get_run(run_id),
            "escalate",
            "Refer unresolved evidence to the designated reviewer for additional inquiry.",
        ),
    )
    before = collaboration._tree_bytes(recipient.root)
    second = import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    assert not second["imported"]
    assert (
        recipient.get_run(run_id)["latest_review"]["review_id"] == revision["review_id"]
    )
    assert recipient.get_run(run_id)["latest_export"] is None
    assert collaboration._tree_bytes(recipient.root) == before


def test_divergent_assessment_is_rejected_without_replacing_local_work(
    package: tuple, tmp_path: Path
) -> None:
    sender, run, raw = package
    recipient = Workspace(tmp_path / "recipient")
    import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    sender.save_review(
        run["manifest"]["run_id"],
        case_review(
            run,
            "escalate",
            "The sender revised this assessment after new correspondence.",
        ),
    )
    changed = Path(sender.export_run(run["manifest"]["run_id"])["path"]).read_bytes()
    before = collaboration._tree_bytes(recipient.root)
    with pytest.raises(HandoffConflict, match="different local assessment"):
        import_package(recipient, changed, expected_sha256=sha256_bytes(changed))
    assert collaboration._tree_bytes(recipient.root) == before


def test_same_run_id_with_changed_retained_run_rejects(
    package: tuple, tmp_path: Path
) -> None:
    _, run, raw = package
    recipient = Workspace(tmp_path / "recipient")
    run_path = recipient.root / "runs" / run["manifest"]["run_id"]
    run_path.mkdir()
    (run_path / "local.txt").write_text("Local data must survive.")
    before = collaboration._tree_bytes(recipient.root)
    with pytest.raises(HandoffConflict, match="conflicts"):
        import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    assert collaboration._tree_bytes(recipient.root) == before


def test_changed_file_after_preview_rejects(package: tuple, tmp_path: Path) -> None:
    _, _, raw = package
    recipient = Workspace(tmp_path / "recipient")
    with pytest.raises(HandoffConflict, match="changed"):
        import_package(recipient, raw, expected_sha256="0" * 64)
    assert not list((recipient.root / "runs").iterdir())


def test_failed_publication_rolls_back_only_new_files(
    package: tuple, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, raw = package
    recipient = Workspace(tmp_path / "recipient")
    retained = recipient.root / "events" / "existing.json"
    retained.write_text('{"retain": true}')
    before = collaboration._tree_bytes(recipient.root)
    real = collaboration._publish
    calls = 0

    def fail_third(path: Path, payload: bytes | dict) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("Synthetic interrupted disk write")
        real(path, payload)

    monkeypatch.setattr(collaboration, "_publish", fail_third)
    with pytest.raises(OSError, match="interrupted"):
        import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    assert collaboration._tree_bytes(recipient.root) == before


def test_symlink_destination_rejects_without_writing_target(
    package: tuple, tmp_path: Path
) -> None:
    _, run, raw = package
    recipient = Workspace(tmp_path / "recipient")
    outside = tmp_path / "outside"
    outside.mkdir()
    (recipient.root / "runs" / run["manifest"]["run_id"]).symlink_to(
        outside, target_is_directory=True
    )
    with pytest.raises(OmphalOSError):
        import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    assert not list(outside.iterdir())


@pytest.mark.parametrize("mutation", ["altered", "duplicate", "traversal"])
def test_malformed_or_changed_zip_rejected(package: tuple, mutation: str) -> None:
    _, _, raw = package
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(raw)) as source,
        zipfile.ZipFile(output, "w") as dest,
    ):
        for info in source.infolist():
            content = source.read(info)
            if mutation == "altered" and info.filename == "review.json":
                content = content.replace(b"keep_open", b"conclude")
            dest.writestr(info.filename, content)
        if mutation == "duplicate":
            dest.writestr("review.json", source.read("review.json"))
        if mutation == "traversal":
            dest.writestr("../escape", b"malicious")
    with pytest.raises(OmphalOSError):
        inspect_package(output.getvalue())


def test_browser_endpoints_and_backup_roundtrip_preserve_imported_case(
    package: tuple, tmp_path: Path
) -> None:
    _, _, raw = package
    app = BrowserApp(tmp_path / "browser")
    upload = {
        "file": {"name": "case.zip", "content_base64": base64.b64encode(raw).decode()}
    }

    def request(path: str, body: dict) -> dict:
        return json.loads(app.dispatch_json(path, json.dumps(body)))

    preview = request("/api/handoffs/inspect", upload)
    assert preview["status"] == 200
    opened = request(
        "/api/handoffs/import",
        {**upload, "expected_sha256": preview["body_json"]["package_sha256"]},
    )
    assert opened["status"] == 200, opened
    result = opened["body_json"]
    restored = BrowserApp(tmp_path / "restored")
    restored_result = restored.restore_bytes(app.backup_bytes())
    assert restored_result["status"] == 200, restored_result
    assert restored_result["body_json"]["restored"]
    assert restored.context.workspace.get_run(result["run_id"])["verification"]["ok"]
    assert restored.context.workspace.get_case(result["continuation_case_id"])
    assert (
        request("/api/handoffs/import", {**upload, "expected_sha256": "0" * 64})[
            "status"
        ]
        == 409
    )
    assert (
        request(
            "/api/handoffs/inspect",
            {
                "file": {
                    "name": "case.zip",
                    "content_base64": base64.b64encode(b"not a zip").decode(),
                }
            },
        )["status"]
        == 400
    )
    assert (
        request("/api/handoffs/inspect", {**upload, "trusted": True})["status"] == 400
    )


def test_reexported_same_review_different_zip_cannot_silently_replace_current(
    package: tuple, tmp_path: Path
) -> None:
    sender, run, raw = package
    recipient = Workspace(tmp_path / "recipient")
    import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    different_zip = Path(
        sender.export_run(run["manifest"]["run_id"])["path"]
    ).read_bytes()
    assert different_zip != raw
    before = collaboration._tree_bytes(recipient.root)
    with pytest.raises(HandoffConflict, match="different package"):
        import_package(
            recipient, different_zip, expected_sha256=sha256_bytes(different_zip)
        )
    assert collaboration._tree_bytes(recipient.root) == before


def test_guided_approvals_stay_in_original_and_are_not_adopted_for_continuation(
    tmp_path: Path,
) -> None:
    sender = BrowserApp(tmp_path / "sender")
    subject = good(
        sender, "/api/workflow/subject", {"name": "Synthetic Handoff Subject"}
    )
    run_id = good(sender, "/api/workflow/run", plan(sender, subject["dataset_id"]))[
        "run_id"
    ]
    exported = review_and_export(sender, run_id)
    raw = (sender.root / "exports" / exported["name"]).read_bytes()
    recipient = Workspace(tmp_path / "recipient")
    opened = import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    received = recipient.get_run(run_id)
    assert received["workflow"]["plan_approved"]
    assert received["handoff"]["package_sha256"] == sha256_bytes(raw)
    assert received["latest_export"]["sha256"] == sha256_bytes(raw)
    fresh_case = recipient.get_case(opened["continuation_case_id"])
    assert fresh_case["schema_version"] == "2.0"
    assert "workflow" not in fresh_case
    new_run = recipient.run_case(opened["continuation_case_id"])
    new_state = recipient.get_run(new_run["run_id"])
    assert not new_state["workflow"]["plan_approved"]
    assert new_state["latest_review"] is None
    assert new_state["latest_export"] is None


def test_identity_research_handoff_preserves_replayable_derivation(
    tmp_path: Path, provider: dict
) -> None:
    sender = Workspace(tmp_path / "sender")
    base = sender.root / "datasets" / "entered"
    derived = sender.root / "datasets" / "enriched"
    research = sender.root / "research" / "identity"
    import_subject("Synthetic Harbor Instruments", base)
    report = research_identity(base, research)
    selected = select_identity(
        base, research, derived, report["candidates"][0]["candidate_id"]
    )
    sender.save_case(
        {
            "case_id": "identity-case",
            "dataset_id": "enriched",
            "as_of": "2026-10-18",
            "question": "Which identity details require corroboration against supplied records?",
            "investigations": ["data_quality"],
        }
    )
    run_id = sender.run_case("identity-case")["run_id"]
    sender.save_review(run_id, case_review(sender.get_run(run_id)))
    raw = Path(sender.export_run(run_id)["path"]).read_bytes()
    recipient = Workspace(tmp_path / "recipient")
    opened = import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    retained = load_dataset(
        recipient.root / "datasets" / opened["continuation_dataset_id"]
    )
    assert retained["metadata"]["identity_research"] == selected["identity_research"]
    assert retained["tables"] == load_dataset(derived)["tables"]
    assert (
        recipient.get_run(run_id)["identity_research"] == selected["identity_research"]
    )


def test_corrupted_handoff_marker_never_redirects_continuation(
    package: tuple, tmp_path: Path
) -> None:
    _, _, raw = package
    recipient = Workspace(tmp_path / "recipient")
    opened = import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    marker = recipient.root / "events" / ("handoff-" + sha256_bytes(raw) + ".json")
    event = json.loads(marker.read_bytes())
    event["continuation"]["continuation_dataset_id"] = "other-local-case"
    write_json(marker, event)
    assert recipient.get_run(opened["run_id"])["handoff"] is None
    with pytest.raises(HandoffConflict, match="continuation"):
        import_package(recipient, raw, expected_sha256=sha256_bytes(raw))


def test_reimport_does_not_report_success_for_damaged_continuation(
    package: tuple, tmp_path: Path
) -> None:
    _, _, raw = package
    recipient = Workspace(tmp_path / "recipient")
    opened = import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    copied = (
        recipient.root / "datasets" / opened["continuation_dataset_id"] / "dataset.json"
    )
    copied.write_text("{}")
    assert recipient.get_run(opened["run_id"])["handoff"] is None
    with pytest.raises(HandoffConflict, match="could not be verified"):
        import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    assert copied.read_text() == "{}"


def test_imported_summary_label_needs_no_archived_evidence_reads(
    package: tuple, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, original, raw = package
    recipient = Workspace(tmp_path / "recipient")
    opened = import_package(recipient, raw, expected_sha256=sha256_bytes(raw))
    run_directory = recipient.root / "runs" / opened["run_id"]
    original_open = Path.open

    def metadata_only(path: Path, *args, **kwargs):
        if path.is_relative_to(run_directory):
            assert path.relative_to(run_directory).as_posix() in {
                "manifest.json",
                "analysis.json",
                "case.json",
            }
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", metadata_only)
    summary = recipient.list_runs(verify_reviews=False)[0]
    assert summary["dataset_label"] == original["dataset_metadata"]["label"]
    assert summary["verification_status"] == "not_checked"
    assert summary["review_validation"]["status"] == "not_checked"

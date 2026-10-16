"""The browser bridge uses the same real workflow, evidence, and review engine."""

from __future__ import annotations

import base64
import io
import json
import stat
import sys
import types
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from test_identity_research import gleif_record
from test_sources_screening import OFAC, csl_payload

from omphalos import identity_research, runner, sources
from omphalos.browser import BACKUP_MANIFEST, BrowserApp
from omphalos.data import load_dataset
from omphalos.evidence import _publish_export, verify_bundle
from omphalos.runner import Workspace
from omphalos.util import canonical_json, sha256_bytes


def good(app: BrowserApp, path: str, body: dict | None = None) -> Any:
    result = json.loads(
        app.dispatch_json(path, json.dumps(body) if body is not None else None)
    )
    assert result["status"] == 200, result
    return result["body_json"]


def plan(app: BrowserApp, dataset_id: str, snapshot_id: str | None = None) -> dict:
    values = {
        "dataset_id": dataset_id,
        "goal_id": "counterparty_screening" if snapshot_id else "data_readiness",
        "as_of": "2026-10-16",
        "watchlist_snapshot_id": snapshot_id,
    }
    prepared = good(app, "/api/workflow/plan", values)
    assert prepared["can_run"]
    execution = {
        **values,
        "case_id": prepared["case"]["case_id"],
        "plan_id": prepared["plan_id"],
    }
    approved = good(
        app,
        "/api/workflow/approve",
        {**execution, "acknowledge_records": True, "acknowledge_source": True},
    )
    return {**execution, "approval": approved["approval"], "acknowledge_plan": True}


def review_and_export(app: BrowserApp, run_id: str) -> dict:
    run = good(app, f"/api/runs/{run_id}")
    good(
        app,
        f"/api/runs/{run_id}/review",
        {
            "schema_version": "2.1",
            "run_id": run_id,
            "reviewer": "Browser QA",
            "decision": "keep_open",
            "summary": "Software test with fictional records.",
            "scope_finding_ids": [
                row["finding_id"] for row in run["analysis"]["findings"]
            ],
            "acknowledge_limitations": True,
        },
    )
    package = good(app, f"/api/runs/{run_id}/export", {})
    assert package["verification"]["ok"]
    return package


def test_complete_browser_workflow_reopens_and_replays_without_network(
    tmp_path: Path,
) -> None:
    app = BrowserApp(tmp_path / "browser")
    state = good(app, "/api/state")
    assert state["storage"]["mode"] == "browser"
    assert state["capabilities"]["source_fetch"] == ["csl"]
    dataset = good(app, "/api/workflow/subject", {"name": "Fictional Browser Company"})
    payload = plan(app, dataset["dataset_id"])
    result = good(app, "/api/workflow/run", payload)
    run_id = result["run_id"]
    package = review_and_export(app, run_id)
    assert "path" not in package
    saved = tmp_path / "export.zip"
    saved.write_bytes(app.export_bytes(package["download_url"]))
    assert verify_bundle(saved)["ok"]
    reopened = BrowserApp(app.root)
    assert good(reopened, "/api/state")["token"] == state["token"]
    assert good(reopened, "/api/workflow/run", payload)["reused"]
    assert len(good(reopened, "/api/state")["runs"]) == 1
    assert good(reopened, f"/api/runs/{run_id}/replay", {})["ok"]
    assert reopened.export_bytes(package["download_url"]) == saved.read_bytes()
    assert (
        good(reopened, f"/api/runs/{run_id}")["latest_export"]["name"]
        == package["name"]
    )


def test_browser_identity_sources_and_raw_provenance_survive_offline_replay(
    tmp_path: Path,
) -> None:
    requested = []
    source_raw = canonical_json(csl_payload())

    def transport(url: str, maximum: int, provider: str) -> dict:
        requested.append((url, maximum, provider))
        if provider == "csl":
            raw, final = source_raw, url
        elif provider == "gleif":
            raw, final = canonical_json({"data": [gleif_record()]}), url
        else:
            assert parse_qs(urlsplit(url).query)["action"] == ["wbsearchentities"]
            raw, final = canonical_json({"search": []}), url + "&origin=*"
        return {
            "status": 200,
            "url": final,
            "headers": {"etag": "fixture"},
            "body": memoryview(raw),
        }

    native_download = identity_research._download
    app = BrowserApp(tmp_path / "browser", transport=transport)
    subject = good(app, "/api/workflow/subject", {"name": "Aster Research"})
    research = good(
        app, "/api/workflow/identity-research", {"dataset_id": subject["dataset_id"]}
    )
    selected = good(
        app,
        "/api/workflow/identity-select",
        {
            "dataset_id": subject["dataset_id"],
            "research_id": research["research_id"],
            "candidate_id": research["candidates"][0]["candidate_id"],
        },
    )
    dataset = load_dataset(app.root / "datasets" / selected["dataset_id"])
    assert dataset["tables"]["entities"][0]["name"] == "Aster Research"
    assert dataset["tables"]["entities"][0]["country"] == "GB"
    summaries = {row["dataset_id"]: row for row in good(app, "/api/state")["datasets"]}
    assert "identity_profile" not in summaries[subject["dataset_id"]]
    assert summaries[selected["dataset_id"]]["identity_profile"] == {
        "name": research["candidates"][0]["name"],
        "sources": sorted(
            {claim["source_label"] for claim in research["candidates"][0]["claims"]}
        ),
    }
    assert (
        summaries[selected["dataset_id"]]["parent_dataset_id"] == subject["dataset_id"]
    )
    assert (
        summaries[selected["dataset_id"]]["identity_association"]
        == "user_selected_public_record"
    )
    assert identity_research._download is native_download
    snapshot = good(app, "/api/sources/fetch", {"source_id": "csl"})
    assert (
        app.root / "sources" / snapshot["snapshot_id"] / "raw.json"
    ).read_bytes() == source_raw
    assert snapshot["ingestion_method"] == "official_https"
    assert snapshot["http_headers"]["ETag"] == "fixture"
    assert {row[2] for row in requested} == {"csl", "gleif", "wikidata"}
    payload = plan(app, selected["dataset_id"], snapshot["snapshot_id"])
    run = good(app, "/api/workflow/run", payload)
    package = review_and_export(app, run["run_id"])
    before = len(requested)
    app.transport = None
    assert good(app, f"/api/runs/{run['run_id']}/replay", {})["ok"]
    assert len(requested) == before
    assert app.export_bytes(package["download_url"]).startswith(b"PK")


def test_browser_provider_failure_is_retained_and_can_continue_name_only(
    tmp_path: Path,
) -> None:
    app = BrowserApp(tmp_path / "browser")
    subject = good(app, "/api/workflow/subject", {"name": "徐"})
    research = good(
        app, "/api/workflow/identity-research", {"dataset_id": subject["dataset_id"]}
    )
    assert research["status"] == "unavailable"
    assert all(row["status"] == "unavailable" for row in research["providers"])
    selected = good(
        app,
        "/api/workflow/identity-select",
        {
            "dataset_id": subject["dataset_id"],
            "research_id": research["research_id"],
            "candidate_id": None,
        },
    )
    context = load_dataset(app.root / "datasets" / selected["dataset_id"])["metadata"][
        "identity_research"
    ]
    assert context["status"] == "unavailable"
    assert context["selected_candidate"] is None
    summary = next(
        row
        for row in good(app, "/api/state")["datasets"]
        if row["dataset_id"] == selected["dataset_id"]
    )
    assert summary["identity_profile"] is None
    assert summary["identity_association"] == "no_profile_selected"


def test_browser_ofac_download_is_explicitly_unavailable_but_import_works(
    tmp_path: Path,
) -> None:
    def forbidden(*args: Any) -> None:
        raise AssertionError("Unsupported direct fetch must not be attempted")

    app = BrowserApp(tmp_path / "browser", transport=forbidden)
    result = app.dispatch("/api/sources/fetch", {"source_id": "ofac_sdn"})
    assert result["status"] == 422 and "import" in result["body_json"]["error"]
    imported = good(
        app,
        "/api/sources/import",
        {
            "source_id": "ofac_sdn",
            "files": [
                {"name": "sdn.xml", "content_base64": base64.b64encode(OFAC).decode()}
            ],
        },
    )
    assert imported["ingestion_method"] == "manual_import"
    assert (
        sources.load_source(app.root / "sources" / imported["snapshot_id"])["entries"][
            0
        ]["record_id"]
        == "123"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"url": "https://attacker.example/data"},
        {"status": 302},
        {"body": "normalized text is not original bytes"},
        {"body": b""},
    ],
)
def test_browser_transport_rejects_unverified_response_shape(
    tmp_path: Path, change: dict
) -> None:
    def transport(url: str, maximum: int, provider: str) -> dict:
        return {
            "status": 200,
            "url": url,
            "headers": {},
            "body": canonical_json(csl_payload()),
            **change,
        }

    app = BrowserApp(tmp_path / "browser", transport=transport)
    assert app.dispatch("/api/sources/fetch", {"source_id": "csl"})["status"] == 400
    assert good(app, "/api/state")["sources"] == []


def test_browser_error_after_committed_run_preserves_approved_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = BrowserApp(tmp_path / "browser")
    subject = good(app, "/api/workflow/subject", {"name": "Fictional Retry Company"})
    payload = plan(app, subject["dataset_id"])
    execute = Workspace.run_case

    def fail_response(self: Workspace, case_id: str) -> dict:
        execute(self, case_id)
        raise OSError("Simulated lost response")

    monkeypatch.setattr(Workspace, "run_case", fail_response)
    assert app.dispatch("/api/workflow/run", payload)["status"] == 500
    monkeypatch.setattr(Workspace, "run_case", execute)
    reopened = BrowserApp(app.root)
    assert good(reopened, "/api/workflow/run", payload)["reused"]
    assert len(good(reopened, "/api/state")["runs"]) == 1


def test_browser_workspace_corruption_is_not_reset_or_silently_recreated(
    tmp_path: Path,
) -> None:
    app = BrowserApp(tmp_path / "browser")
    good(app, "/api/workflow/subject", {"name": "Retained subject"})
    app.state_path.unlink()
    with pytest.raises(ValueError, match="left unchanged"):
        BrowserApp(app.root)
    assert len(list((app.root / "datasets").iterdir())) == 1


def test_browser_unsafe_paths_and_bad_json_are_rejected(tmp_path: Path) -> None:
    app = BrowserApp(tmp_path / "browser")
    for path in ("/", "/../browser-state.json", "https://other.example/api/state"):
        assert app.dispatch(path)["status"] in {400, 404}
    for value in ('{"name":"A","name":"B"}', "[]"):
        assert (
            json.loads(app.dispatch_json("/api/workflow/subject", value))["status"]
            == 400
        )
    with pytest.raises(ValueError):
        app.export_bytes("/api/exports/../../browser-state.json")
    assert good(app, "/api/state")["datasets"] == []


def test_browser_runtime_records_real_available_versions_without_native_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = runner.importlib.metadata.version

    def installed(name: str) -> str:
        if name in {"cryptography", "truststore"}:
            raise runner.importlib.metadata.PackageNotFoundError(name)
        return version(name)

    monkeypatch.setattr(runner.importlib.metadata, "version", installed)
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.setitem(
        sys.modules, "pyodide", types.SimpleNamespace(__version__="314.0.7")
    )
    observed = runner.runtime_versions()
    assert observed["pyodide"] == "314.0.7"
    assert observed["pydantic"] == version("pydantic")
    assert "cryptography" not in observed and "truststore" not in observed
    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(runner.importlib.metadata.PackageNotFoundError):
        runner.runtime_versions()


def test_browser_atomic_export_publication_preserves_existing_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = tmp_path / "ready.zip", tmp_path / "published.zip"
    source.write_bytes(b"complete package bytes")
    monkeypatch.setattr(sys, "platform", "emscripten")
    _publish_export(source, target)
    assert not source.exists() and target.read_bytes() == b"complete package bytes"
    source.write_bytes(b"other package")
    with pytest.raises(FileExistsError):
        _publish_export(source, target)
    assert source.read_bytes() == b"other package"
    assert target.read_bytes() == b"complete package bytes"


def test_full_browser_backup_restore_preserves_unassessed_work_and_completed_evidence(
    tmp_path: Path,
) -> None:
    source = BrowserApp(tmp_path / "source")
    entered = good(
        source, "/api/workflow/subject", {"name": "Fictional backup subject"}
    )
    payload = plan(source, entered["dataset_id"])
    initial_backup = source.backup_bytes()
    restored = BrowserApp(tmp_path / "restored")
    assert restored.restore_bytes(memoryview(initial_backup))["status"] == 200
    assert good(restored, "/api/state")["token"] == good(source, "/api/state")["token"]
    assert (
        good(restored, "/api/state")["datasets"][0]["label"]
        == "Fictional backup subject"
    )
    run = good(restored, "/api/workflow/run", payload)
    package = review_and_export(restored, run["run_id"])
    complete = restored.backup_bytes()
    good(source, "/api/workflow/subject", {"name": "Replaced only after validation"})
    result = source.restore_bytes(complete)
    assert result["status"] == 200 and result["body_json"] == {
        "restored": True,
        "datasets": 1,
        "runs": 1,
    }
    reopened = BrowserApp(source.root)
    assert good(reopened, "/api/workflow/run", payload)["reused"]
    assert good(reopened, f"/api/runs/{run['run_id']}/replay", {})["ok"]
    assert reopened.export_bytes(package["download_url"]) == restored.export_bytes(
        package["download_url"]
    )
    assert not list(source.root.glob(".restore-*"))


def rewrite_backup(raw: bytes, change: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        content = {row.filename: archive.read(row) for row in archive.infolist()}
    manifest = json.loads(content[BACKUP_MANIFEST])
    if change == "tamper":
        content["workspace/browser-state.json"] = b"{}"
    elif change == "semantics":
        name = next(name for name in content if name.endswith("/dataset.json"))
        data = json.loads(content[name])
        data["tables"]["entities"][0]["name"] = "Altered without retained original"
        content[name] = canonical_json(data)
        entry = next(
            row for row in manifest["files"] if "workspace/" + row["path"] == name
        )
        entry.update(size_bytes=len(content[name]), sha256=sha256_bytes(content[name]))
        content[BACKUP_MANIFEST] = canonical_json(manifest)
    elif change == "traversal":
        content["workspace/../outside.json"] = b"{}"
    elif change == "oversize":
        manifest["files"][0]["size_bytes"] = 513 * 1024 * 1024
        content[BACKUP_MANIFEST] = canonical_json(manifest)
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in content.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (
                (
                    stat.S_IFLNK
                    if change == "symlink" and name != BACKUP_MANIFEST
                    else stat.S_IFREG
                )
                | 0o600
            ) << 16
            info.compress_type = (
                zipfile.ZIP_BZIP2 if change == "compression" else zipfile.ZIP_DEFLATED
            )
            archive.writestr(info, value)
    return target.getvalue()


@pytest.mark.parametrize(
    "change", ["tamper", "semantics", "traversal", "oversize", "symlink", "compression"]
)
def test_invalid_backup_never_changes_existing_workspace(
    tmp_path: Path, change: str
) -> None:
    app = BrowserApp(tmp_path / "browser")
    good(app, "/api/workflow/subject", {"name": "Retained original"})
    backup = app.backup_bytes()
    before = {
        path.relative_to(app.root): path.read_bytes()
        for path in app.root.rglob("*")
        if path.is_file()
    }
    rejected = app.restore_bytes(rewrite_backup(backup, change))
    assert rejected["status"] == 400, rejected
    assert before == {
        path.relative_to(app.root): path.read_bytes()
        for path in app.root.rglob("*")
        if path.is_file()
    }
    assert good(app, "/api/state")["datasets"][0]["label"] == "Retained original"
    assert not list(app.root.glob(".restore-*"))


def test_interrupted_backup_restore_rolls_back_then_reopens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original, incoming = BrowserApp(tmp_path / "original"), BrowserApp(
        tmp_path / "incoming"
    )
    good(original, "/api/workflow/subject", {"name": "Original retained work"})
    good(incoming, "/api/workflow/subject", {"name": "Incoming replacement"})
    raw = incoming.backup_bytes()
    rename = Path.rename
    moved = []

    def interrupt(path: Path, target: Path) -> Path:
        if path.parent.name.startswith(".restore-stage-"):
            if moved:
                raise OSError("Simulated interrupted child publication")
            moved.append(path.name)
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", interrupt)
    assert original.restore_bytes(raw)["status"] == 400
    monkeypatch.setattr(Path, "rename", rename)
    assert (
        good(original, "/api/state")["datasets"][0]["label"] == "Original retained work"
    )
    reopened = BrowserApp(original.root)
    assert (
        good(reopened, "/api/state")["datasets"][0]["label"] == "Original retained work"
    )
    assert original.restore_bytes(raw)["status"] == 200
    assert (
        good(original, "/api/state")["datasets"][0]["label"] == "Incoming replacement"
    )


def test_failed_restore_rollback_is_quarantined_until_recovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, incoming = BrowserApp(tmp_path / "original"), BrowserApp(tmp_path / "incoming")
    good(app, "/api/workflow/subject", {"name": "Original protected work"})
    good(incoming, "/api/workflow/subject", {"name": "Incoming work"})
    raw = incoming.backup_bytes()
    rename = Path.rename

    def fail_restore(path: Path, target: Path) -> Path:
        if path.parent.name.startswith((".restore-stage-", ".restore-old-")):
            raise OSError("Temporarily unavailable publication")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_restore)
    assert app.restore_bytes(raw)["status"] == 400
    assert app.dispatch("/api/state")["status"] == 503
    assert (
        not app.state_path.exists()
    ), "Quarantined reads must not recreate active state"
    monkeypatch.setattr(Path, "rename", rename)
    assert good(app, "/api/state")["datasets"][0]["label"] == "Original protected work"
    assert BrowserApp(app.root).context.token == app.context.token


def test_zip_directory_limits_are_checked_before_zipfile_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = BrowserApp(tmp_path / "browser")
    raw = bytearray(app.backup_bytes())
    position = raw.rfind(b"PK\x05\x06")
    raw[position + 10 : position + 12] = (65535).to_bytes(2, "little")

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("ZIP directory must be rejected before allocating members")

    monkeypatch.setattr(zipfile, "ZipFile", forbidden)
    assert app.restore_bytes(raw)["status"] == 400

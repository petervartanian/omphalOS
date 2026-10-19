"""Exercise the real HTTP workflow and local-service security boundaries."""

from __future__ import annotations

import base64
import http.client
import json
import mimetypes
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest

from omphalos.data import create_demo
from omphalos.evidence import verify_bundle
from omphalos.web import MAX_BODY_BYTES, create_server


@pytest.fixture
def browser(tmp_path: Path):
    server = create_server(tmp_path / "workspace", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(
        path: str,
        body: Any = None,
        *,
        headers: dict | None = None,
        method: str | None = None,
    ):
        connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=15)
        raw = json.dumps(body).encode() if body is not None else None
        request_headers = {}
        if raw is not None:
            request_headers = {
                "Content-Type": "application/json",
                "Origin": server.url,
                "X-Omphalos-Token": server.token,
            }
        request_headers.update(headers or {})
        connection.request(
            method or ("POST" if raw is not None else "GET"),
            path,
            body=raw,
            headers=request_headers,
        )
        response = connection.getresponse()
        payload = response.read()
        status, returned_headers = response.status, dict(response.getheaders())
        connection.close()
        value = (
            json.loads(payload)
            if "application/json" in returned_headers.get("Content-Type", "")
            else payload
        )
        return status, value, returned_headers

    yield server, request
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def upload(name: str, content: Any) -> dict:
    raw = content if isinstance(content, bytes) else json.dumps(content).encode()
    return {"name": name, "content_base64": base64.b64encode(raw).decode()}


def case(dataset: str, *, investigations: list[str] | None = None) -> dict:
    return {
        "schema_version": "2.0",
        "case_id": "http-case",
        "question": "Which imported transactions require further evidence and analyst follow-up?",
        "dataset_id": dataset,
        "as_of": "2026-10-13",
        "investigations": investigations or ["payment_fragmentation", "data_quality"],
        "scope": {},
        "parameters": {},
        "watchlist_snapshot_id": None,
    }


def test_removed_example_endpoint_cannot_create_workspace_records(browser):
    server, request = browser
    status, _, _ = request("/api/datasets/demo", {"dataset_id": "unwanted-example"})
    assert status == 404
    assert server.workspace.list_datasets() == []
    assert server.workspace.list_cases() == []
    assert server.workspace.list_runs() == []


def test_complete_real_workflow_and_download(browser):
    server, request = browser
    status, state, headers = request("/api/state")
    assert status == 200 and state["datasets"] == [] and state["token"]
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    create_demo(server.root / "datasets" / "fixture-http")
    assert request("/api/cases", case("fixture-http"))[0] == 200
    status, summary, _ = request("/api/cases/http-case/run", {})
    assert status == 200, summary
    run_id = summary["run_id"]
    status, run, _ = request(f"/api/runs/{run_id}")
    assert status == 200 and run["verification"]["ok"]
    assert run["analysis"]["findings"]
    finding = run["analysis"]["findings"][0]
    ref = finding["record_refs"][0]
    status, evidence, _ = request(
        f"/api/runs/{run_id}/evidence?table={ref['table']}&id={ref['record_id']}"
    )
    assert status == 200 and evidence["synthetic"] is True
    assert evidence["origin"]["source_file"] == "dataset.json"
    assert evidence["source_files"][0]["sha256"]
    assert request(f"/api/runs/{run_id}/export", {})[0] == 400
    review = {
        "schema_version": "2.0",
        "run_id": run_id,
        "reviewer": "Synthetic QA analyst",
        "summary": "The synthetic observations require follow-up on the specific invoices and missing transaction context.",
        "acknowledge_limitations": True,
        "findings": [
            {
                "finding_id": item["finding_id"],
                "disposition": "follow_up",
                "rationale": f"The cited records for {item['finding_id']} show a pattern, but the underlying contract is not in the dataset.",
                "unknowns": [
                    "The contract payment schedule has not been supplied for these cited records."
                ],
                "alternatives": [
                    "Ordinary documented installments could explain the observed transaction pattern."
                ],
                "falsifiers": [
                    "An invoice and contract linking each installment to agreed milestones would change this assessment."
                ],
            }
            for item in run["analysis"]["findings"]
        ],
    }
    incomplete = {**review, "findings": review["findings"][:-1]}
    assert request(f"/api/runs/{run_id}/review", incomplete)[0] == 400
    status, saved, _ = request(f"/api/runs/{run_id}/review", review)
    assert status == 200 and saved["review_id"], saved
    assert request(f"/api/runs/{run_id}/verify", {})[1]["ok"]
    replay = request(f"/api/runs/{run_id}/replay", {})
    assert replay[0] == 200 and replay[1]["ok"], replay
    status, exported, _ = request(f"/api/runs/{run_id}/export", {})
    assert status == 200, exported
    status, raw, headers = request(exported["download_url"])
    assert status == 200 and raw.startswith(b"PK")
    assert headers["Content-Disposition"].startswith("attachment;")
    assert raw == Path(exported["path"]).read_bytes()
    assert verify_bundle(Path(exported["path"]))["ok"]
    (server.root / "runs" / run_id / "analysis.json").write_text("{}")
    assert (
        request(
            f"/api/runs/{run_id}/evidence?table={ref['table']}&id={ref['record_id']}"
        )[0]
        == 409
    )
    assert request(f"/api/runs/{run_id}/export", {})[0] == 400


def test_actual_upload_provenance_and_rejected_imports(browser):
    server, request = browser
    csv = b'entity_id,name,country,address\r\nE1,"Example, Ltd.",US,12 Example Road\r\n'
    status, imported, _ = request(
        "/api/datasets/import",
        {
            "dataset_id": "uploaded",
            "label": "Case material",
            "files": [upload("entities.csv", csv)],
        },
    )
    assert status == 200 and imported["synthetic"] is False
    assert (
        server.root / "datasets/uploaded/originals/entities.csv"
    ).read_bytes() == csv
    invalid = [
        upload(
            "entities.json",
            [{"entity_id": "E1", "name": "Alpha"}, {"entity_id": "E1", "name": "Beta"}],
        )
    ]
    status, error, _ = request(
        "/api/datasets/import", {"dataset_id": "invalid", "files": invalid}
    )
    assert status == 400 and "duplicate" in error["error"].lower()
    assert not (server.root / "datasets/invalid").exists()
    assert (
        request(
            "/api/datasets/import",
            {"dataset_id": "escape", "files": [upload("../entities.json", [])]},
        )[0]
        == 400
    )
    assert (
        request(
            "/api/datasets/import",
            {"files": [{"name": "entities.json", "content_base64": "invalid!"}]},
        )[0]
        == 400
    )
    assert (
        request(
            "/api/datasets/import",
            {"files": [upload("entities.json", []), upload("entities.json", [])]},
        )[0]
        == 400
    )
    assert (
        request(
            "/api/datasets/import",
            {"dataset_id": "uploaded", "files": [upload("entities.csv", csv)]},
        )[0]
        == 409
    )
    assert (
        request(
            "/api/datasets/import",
            {"dataset_id": "../../outside", "files": [upload("entities.csv", csv)]},
        )[0]
        == 400
    )


def test_manual_official_source_and_archived_source_drilldown(browser, monkeypatch):
    server, request = browser
    original = {
        "id": "official-fixture-1",
        "name": "Synthetic Harbor Instruments",
        "source": "Entity List (EL) - Bureau of Industry and Security",
        "addresses": [{"country": "US", "address": "100 Example Industrial Road"}],
        "start_date": "2020-01-01",
    }
    snapshot = {"total": 1, "offset": 0, "results": [original]}
    status, saved, _ = request(
        "/api/sources/import",
        {
            "source_id": "csl",
            "snapshot_id": "source-fixture",
            "files": [upload("consolidated.json", snapshot)],
        },
    )
    assert status == 200 and saved["record_count"] == 1, saved
    create_demo(server.root / "datasets" / "screening-fixture")
    definition = {
        **case("screening-fixture", investigations=["screening_candidates"]),
        "watchlist_snapshot_id": "source-fixture",
    }
    assert request("/api/cases", definition)[0] == 200
    status, summary, _ = request("/api/cases/http-case/run", {})
    assert status == 200, summary
    run_id = summary["run_id"]
    run = request(f"/api/runs/{run_id}")[1]
    ref = run["analysis"]["findings"][0]["source_refs"][0]
    checks = []
    verify = server.workspace.verify_run

    def checked_verify(value):
        checks.append(value)
        return verify(value)

    def unrelated_run_detail(_run_id):
        raise AssertionError(
            "Evidence must not revalidate unrelated reviews or exports"
        )

    monkeypatch.setattr(server.workspace, "verify_run", checked_verify)
    monkeypatch.setattr(server.workspace, "get_run", unrelated_run_detail)
    status, evidence, _ = request(
        f"/api/runs/{run_id}/source-evidence?id={ref['record_id']}"
    )
    assert status == 200 and evidence["record"]["raw_record"] == original
    assert checks == [run_id]
    assert (
        evidence["metadata"]["sha256"] and evidence["snapshot_id"] == "source-fixture"
    )
    assert (server.root / "runs" / run_id / "sources" / "raw.json").is_file()
    assert request(f"/api/runs/{run_id}/source-evidence?id=nonexistent")[0] == 404
    (server.root / "runs" / run_id / "sources" / "raw.json").write_text("{}")
    assert (
        request(f"/api/runs/{run_id}/source-evidence?id={ref['record_id']}")[0] == 409
    )


def test_zero_findings_still_requires_review(browser):
    _, request = browser
    assert (
        request(
            "/api/datasets/import",
            {
                "dataset_id": "minimal",
                "files": [
                    upload(
                        "entities.json",
                        [
                            {
                                "entity_id": "E1",
                                "name": "Example",
                                "country": "US",
                                "address": "12 Sample Road",
                            }
                        ],
                    )
                ],
            },
        )[0]
        == 200
    )
    assert (
        request("/api/cases", case("minimal", investigations=["shared_address"]))[0]
        == 200
    )
    status, summary, _ = request("/api/cases/http-case/run", {})
    assert status == 200 and summary["findings_count"] == 0
    run_id = summary["run_id"]
    assert request(f"/api/runs/{run_id}/export", {})[0] == 400
    review = {
        "schema_version": "2.0",
        "run_id": run_id,
        "reviewer": "Example Analyst",
        "summary": "Only one supplied entity was compared. No shared address observation can establish completeness or clearance.",
        "findings": [],
        "acknowledge_limitations": True,
    }
    assert request(f"/api/runs/{run_id}/review", review)[0] == 200


def test_local_host_origin_token_and_path_boundaries(browser, tmp_path):
    server, request = browser
    for host in (
        "attacker.example",
        "127.0.0.1",
        f"127.0.0.1:{server.port}@attacker.example",
    ):
        assert request("/api/state", headers={"Host": host})[0] == 403
    assert (
        request("/api/state", headers={"Origin": "https://attacker.example"})[0] == 403
    )
    assert request("/api/state", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert (
        request("/api/datasets/import", {}, headers={"X-Omphalos-Token": "bad"})[0]
        == 403
    )
    assert request("/api/datasets/import", {}, headers={"Origin": "null"})[0] == 403
    assert (
        request("/api/datasets/import", {}, headers={"Content-Type": "text/plain"})[0]
        == 415
    )
    assert (
        request(
            "/api/datasets/import",
            {},
            headers={"Content-Length": str(MAX_BODY_BYTES + 1)},
        )[0]
        == 413
    )
    assert (
        request("/api/datasets/import", {}, headers={"Transfer-Encoding": "chunked"})[0]
        == 400
    )
    assert request("/api/exports/%2e%2e%2fsecret.zip")[0] == 400
    assert request("/api/exports/secret.txt")[0] == 400
    assert request("/etc/passwd")[0] == 404
    assert (
        request(
            "/api/sources/fetch",
            {"source_id": "csl", "url": "https://attacker.example"},
        )[0]
        == 400
    )
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"secret")
    (server.root / "exports" / "linked.zip").symlink_to(outside)
    assert request("/api/exports/linked.zip")[0] in (400, 404)
    for host in ("0.0.0.0", "192.168.1.2", "attacker.example"):
        with pytest.raises(ValueError, match="only"):
            create_server(tmp_path / "other", host=host, port=0)


def test_no_cdn_and_assets_served_with_security_headers(browser, monkeypatch):
    _, request = browser
    # Windows may not register web font types. Packaged assets must not depend
    # on the host MIME registry, especially with nosniff enabled.
    monkeypatch.setattr(mimetypes, "guess_type", lambda *_args, **_kwargs: (None, None))
    for asset, mime in {
        "/": "text/html; charset=utf-8",
        "/styles.css": "text/css; charset=utf-8",
        "/app.js": "application/javascript; charset=utf-8",
        "/box.js": "application/javascript; charset=utf-8",
        "/geist.woff2": "font/woff2",
        "/geist-mono.woff2": "font/woff2",
        "/font-license.txt": "text/plain; charset=utf-8",
    }.items():
        status, contents, headers = request(asset)
        assert status == 200 and contents
        assert headers["Content-Type"] == mime
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Cache-Control"] == "no-store"
        assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
        assert "script-src 'self'" in headers["Content-Security-Policy"]
        assert "Access-Control-Allow-Origin" not in headers
    assert request("/geist.woff2")[1][:4] == b"wOF2"
    html = request("/")[1].decode()
    assert 'src="https:' not in html and 'href="https:' not in html
    assert 'src="/app.js"' in html
    assert 'src="/box.js"' in html


def test_duplicate_json_keys_missing_origin_and_duplicate_host(browser):
    server, _ = browser
    connection = http.client.HTTPConnection("127.0.0.1", server.port)
    raw = b'{"dataset_id":"one","dataset_id":"two"}'
    connection.request(
        "POST",
        "/api/datasets/import",
        body=raw,
        headers={
            "Content-Type": "application/json",
            "Origin": server.url,
            "X-Omphalos-Token": server.token,
        },
    )
    response = connection.getresponse()
    assert response.status == 400 and b"Duplicate JSON key" in response.read()
    connection.close()
    connection = http.client.HTTPConnection("127.0.0.1", server.port)
    connection.request(
        "POST",
        "/api/datasets/import",
        body=b"{}",
        headers={"Content-Type": "application/json", "X-Omphalos-Token": server.token},
    )
    response = connection.getresponse()
    assert response.status == 403
    response.read()
    connection.close()

    connection = http.client.HTTPConnection("127.0.0.1", server.port)
    connection.putrequest("GET", "/api/state")
    connection.putheader("Host", f"localhost:{server.port}")
    connection.endheaders()
    response = connection.getresponse()
    assert response.status == 403
    response.read()
    connection.close()


def test_review_pagination_preserves_unsaved_assessments_and_escapes_text():
    """Run the actual frontend functions against a minimal DOM in Node, offline."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed for the frontend state regression test")
    script = Path(__file__).parents[1] / "src/omphalos/ui/app.js"
    harness = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const elements = new Map();
let activeForm = null;
function element(selector) {
  if (selector === '#review-form') return activeForm;
  if (!elements.has(selector)) elements.set(selector, {
    textContent: '', innerHTML: '', hidden: false, dataset: {},
    addEventListener() {}, setAttribute() {}, removeAttribute() {},
    classList: { toggle() {} },
  });
  return elements.get(selector);
}
class FormDataStub {
  constructor(form) { this.fields = form.fields; }
  get(name) { return this.fields[name] ?? ''; }
  has(name) { return Object.hasOwn(this.fields, name); }
}
const context = vm.createContext({
  document: { querySelector: element, querySelectorAll: () => [], body: element('body'), addEventListener() {} },
  window: { addEventListener() {} }, location: { hash: '#overview' },
  fetch: () => new Promise(() => {}), FormData: FormDataStub, console,
});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const run = (code) => vm.runInContext(code, context);
run(`model.selectedRun = 'runA'; model.run = {
  analysis: { findings: Array.from({length: 42}, (_, i) => ({finding_id: 'F'+i, title: 'Observation '+i, observation: 'An actual observed pattern for testing', unknowns: [], alternatives: [], falsifiers: []})) },
  latest_review: null, verification: {ok: true}
};`);
function form(start, end) {
  const groups = Array.from({length: end-start}, (_, offset) => {
    const i = start + offset;
    const values = { disposition: 'follow_up', rationale: `Specific evidence-based rationale for F${i}`, unknowns: `The contract for F${i} has not been supplied.`, alternatives: 'Ordinary agreed installments are a plausible explanation.', falsifiers: 'The underlying invoice and signed contract would resolve this issue.' };
    return { dataset: {finding: 'F'+i}, values, querySelector(selector) { return { value: values[selector.match(/name="([^"]+)"/)[1]] }; } };
  });
  return { dataset: {dirty: 'false'}, fields: {reviewer: 'Test Analyst', summary: 'Specific overall assessment retained across pages.', acknowledge_limitations: 'on'}, groups, querySelectorAll: () => groups };
}
activeForm = form(0, 20);
run('saveReviewDraft()');
assert.equal(run('Object.keys(model.reviewDrafts).length'), 0, 'untouched review is not dirty');
activeForm.dataset.dirty = 'true';
run('saveReviewDraft()');
assert.equal(run('model.reviewDrafts.runA.findings.length'), 42);
assert.equal(run('model.reviewDrafts.runA.findings.filter(reviewRowComplete).length'), 20);
activeForm = form(20, 40);
run('model.reviewPage = 1; saveReviewDraft()');
assert.equal(run('model.reviewDrafts.runA.findings[0].rationale'), 'Specific evidence-based rationale for F0');
assert.equal(run('model.reviewDrafts.runA.findings.filter(reviewRowComplete).length'), 40);
activeForm.groups[2].values.rationale = '';
run('saveReviewDraft()');
assert.equal(run('model.reviewDrafts.runA.findings[22].rationale'), '', 'clearing a value must not restore an old assessment');
assert.equal(run('model.reviewDrafts.runA.findings.filter(reviewRowComplete).length'), 39);
activeForm = form(40, 42);
run('model.reviewPage = 2; saveReviewDraft()');
assert.equal(run('model.reviewDrafts.runA.findings.filter(reviewRowComplete).length'), 41);
assert.equal(run('model.reviewDrafts.runA.reviewer'), 'Test Analyst');
const page = run('renderReview()');
assert.ok(page.includes('Showing 41–42 of 42 observations'));
assert.ok(page.includes('Specific evidence-based rationale for F41'));
assert.ok(!page.includes('Specific evidence-based rationale for F0'));
run(`model.run.analysis.findings[40].title = '<img src=x onerror=alert(1)>';`);
assert.ok(run('renderReview()').includes('&lt;img src=x onerror=alert(1)&gt;'));
assert.ok(!run('renderReview()').includes('<img src=x'));
context.fetch = async () => ({ok: true, json: async () => ({token: 'refreshed'})});
(async () => {
  await run('refresh(false)');
  assert.equal(run('model.reviewDrafts.runA.findings[41].rationale'), 'Specific evidence-based rationale for F41', 'refresh must preserve unsaved review');
  assert.equal(run('model.state.token'), 'refreshed');
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node, "-e", harness, str(script)], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stdout + result.stderr

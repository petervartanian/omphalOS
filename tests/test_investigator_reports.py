"""Readable handoffs retain coverage, contrary context, and review boundaries."""

from __future__ import annotations

import html
import json
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import pytest
from test_evidence import make_run

from omphalos import evidence
from omphalos.data import import_dataset
from omphalos.runner import Workspace
from omphalos.util import read_json, sha256_file, write_json


class CoverageTable(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.tags: list[str] = []
        self.in_table = False
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        if tag == "table":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.rows.append([])
        elif self.in_table and tag in {"td", "th"}:
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append("\n")

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.cell is not None:
            self.rows[-1].append("".join(self.cell))
            self.cell = None
        elif tag == "table":
            self.in_table = False


def report_inputs(tmp_path: Path, schema: str = "2.2") -> tuple[dict, dict, dict]:
    run_dir = tmp_path / "run"
    _, legacy_review = make_run(run_dir)
    case = read_json(run_dir / "case.json")
    analysis = read_json(run_dir / "analysis.json")
    review = legacy_review
    if schema != "2.0":
        review = {
            "schema_version": schema,
            "run_id": "run_demo",
            "reviewer": "Synthetic case reviewer",
            "decision": "escalate",
            "summary": "Ask the supplier for the original form before deciding.",
            "scope_finding_ids": [
                finding["finding_id"] for finding in analysis["findings"]
            ],
            "acknowledge_limitations": True,
        }
    return case, analysis, {"review_id": "review_demo", "review": review}


@pytest.mark.parametrize("schema", ["2.1", "2.2"])
def test_handoff_distinguishes_coverage_and_preserves_analytical_context(
    tmp_path: Path, schema: str
) -> None:
    case, analysis, wrapper = report_inputs(tmp_path, schema)
    analysis["coverage"].append(
        {
            "investigation_id": "screening_candidates",
            "status": "not_evaluable",
            "records_evaluated": 0,
            "findings_count": 0,
            "reason": "No screening snapshot was supplied.",
            "limitations": [
                "Identity remains unassessed.",
                "No historical list available.",
            ],
        }
    )
    catalog = [
        {"id": "data_quality", "title": "Missing analytical context"},
        {"id": "screening_candidates", "title": "Official-list identity candidates"},
    ]
    report_html, report_md = evidence._reports(
        case, analysis, wrapper, {"files_checked": 8}, catalog
    )
    parsed = CoverageTable()
    parsed.feed(report_html.decode())
    assert parsed.rows[1] == [
        "Missing analytical context (data_quality)",
        "Completed",
        "1",
        "1",
        "—",
        "Synthetic test data only.",
    ]
    assert parsed.rows[2] == [
        "Official-list identity candidates (screening_candidates)",
        "Not evaluated",
        "0",
        "0",
        "No screening snapshot was supplied.",
        "Identity remains unassessed.\nNo historical list available.",
    ]
    markdown_rows = [
        line for line in report_md.decode().splitlines() if line.startswith("|")
    ]
    assert len(markdown_rows) == 4
    assert all(line.count("|") == 7 for line in markdown_rows)
    for content in (report_html.decode(), report_md.decode()):
        assert "Separate supervisory approval: not recorded." in content
        assert "self-asserted identity" in content
        assert "Zero observations do not establish clearance." in content
        assert "not statements authored or individually adopted" in content
        assert wrapper["review"]["summary"] in content
        for field in ("unknowns", "alternatives", "falsifiers"):
            assert html.escape(analysis["findings"][0][field][0], quote=True) in content


def test_coverage_cells_cannot_inject_html_or_split_markdown_rows(
    tmp_path: Path,
) -> None:
    case, analysis, wrapper = report_inputs(tmp_path)
    title = "A | [link](https://example.invalid) `code` <script>alert(1)</script>"
    reason = "First | reason\r\nSecond <img src=x onerror=alert(1)> \\| end"
    limits = ["A *claim*\nwith | detail", "Another & limitation"]
    analysis["coverage"][0].update(reason=reason, limitations=limits)
    report_html, report_md = evidence._reports(
        case,
        analysis,
        wrapper,
        {"files_checked": 8},
        [{"id": "data_quality", "title": title}],
    )
    parsed = CoverageTable()
    parsed.feed(report_html.decode())
    assert "script" not in parsed.tags
    assert "img" not in parsed.tags
    assert len(parsed.rows) == 2
    assert len(parsed.rows[1]) == 6
    assert parsed.rows[1][0] == f"{title} (data_quality)"
    assert parsed.rows[1][4] == reason.replace("\r\n", "\n")
    assert parsed.rows[1][5] == "\n".join(limits)
    markdown_rows = [
        line for line in report_md.decode().splitlines() if line.startswith("|")
    ]
    assert len(markdown_rows) == 3
    assert all(line.count("|") == 7 for line in markdown_rows)
    assert "&#124;" in markdown_rows[-1]
    assert "&#91;link&#93;" in markdown_rows[-1]
    assert "&#92;&#124;" in markdown_rows[-1]
    assert "First &#124; reason<br>Second &lt;img" in markdown_rows[-1]


@pytest.mark.parametrize(
    "catalog",
    [
        None,
        [{"id": "data_quality"}],
        [
            {"id": "data_quality", "title": "First title"},
            {"id": "data_quality", "title": "Conflicting title"},
        ],
    ],
)
def test_unavailable_or_ambiguous_catalog_falls_back_to_retained_id(
    tmp_path: Path, catalog: list[dict] | None
) -> None:
    case, analysis, wrapper = report_inputs(tmp_path)
    report_html, _ = evidence._reports(
        case, analysis, wrapper, {"files_checked": 8}, catalog
    )
    parsed = CoverageTable()
    parsed.feed(report_html.decode())
    assert parsed.rows[1][0] == "data_quality"


@pytest.mark.parametrize("schema", ["2.0", "2.1", "2.2"])
def test_export_uses_frozen_catalog_and_preserves_legacy_reviews(
    tmp_path: Path, schema: str
) -> None:
    case, analysis, wrapper = report_inputs(tmp_path, schema)
    run_dir = tmp_path / "run"
    manifest = read_json(run_dir / "manifest.json")
    title = "The title retained when this investigation ran"
    write_json(run_dir / "catalog.json", [{"id": "data_quality", "title": title}])
    (run_dir / "manifest.json").unlink()
    evidence.build_manifest(
        run_dir,
        run_id=manifest["run_id"],
        case_id=case["case_id"],
        analysis_digest=manifest["analysis_digest"],
    )
    wrapper.update(
        created_at="2026-10-18T12:00:00Z",
        run_manifest_sha256=sha256_file(run_dir / "manifest.json"),
    )
    review_path = tmp_path / "review.json"
    write_json(review_path, wrapper)
    bundle_path = tmp_path / "bundle.zip"
    evidence.export_bundle(run_dir, review_path, bundle_path)
    assert evidence.verify_bundle(bundle_path)["ok"]
    with zipfile.ZipFile(bundle_path) as archive:
        assert json.loads(archive.read("run/analysis.json")) == analysis
        assert json.loads(archive.read("review.json"))["review"] == wrapper["review"]
        for name in ("report.html", "report.md"):
            report = archive.read(name).decode()
            assert title in report
            assert "Separate supervisory approval: not recorded." in report
            if schema == "2.0":
                assert "Review summary" in report
                assert "Reasoning" in report
                assert wrapper["review"]["findings"][0]["rationale"] in report
            else:
                assert "Case decision" in report
                assert "no individual dispositions are recorded" in report
                assert "Reasoning" not in report


@pytest.mark.parametrize("with_findings", [True, False])
def test_supporting_records_survive_import_run_and_handoff(
    tmp_path: Path, with_findings: bool
) -> None:
    store = Workspace(tmp_path / "workspace")
    source = tmp_path / "input"
    source.mkdir()
    supplied = {
        "schema_version": "2.0",
        "tables": {
            "entities": [
                {"entity_id": "E1", "name": "Synthetic supplier"},
                {"entity_id": "E2", "name": "Synthetic buyer"},
                {"entity_id": "E3", "name": "Separate synthetic subject"},
            ],
            "shipments": [
                {"shipment_id": "S1", "exporter_id": "E1", "importer_id": "E2"}
            ],
            "payments": [
                {
                    "payment_id": f"P{number}",
                    "shipment_id": "S1",
                    "amount": "100",
                    "ccy": "USD",
                }
                for number in range(1, 4 if with_findings else 3)
            ],
            "diligence": [
                {
                    "evidence_id": "D1",
                    "entity_id": "E1",
                    "title": "Supplier payment schedule",
                    "text": "The supplier attributes the payments to deposit, inspection, and delivery installments.",
                    "date": "2026-09-01",
                    "source_url": "https://example.test/schedule",
                },
                {
                    "evidence_id": "D2",
                    "entity_id": "E1",
                    "title": "Routine inspection record",
                    "text": "The supplied inspection record supports the second scheduled milestone; delivery is unverified.",
                    "date": "2026-09-15",
                },
                {
                    "evidence_id": "D3",
                    "entity_id": "E3",
                    "title": "Separate subject's later statement",
                    "text": "This statement concerns a different subject and date from the selected scope.",
                    "date": "2026-10-01",
                },
            ],
        },
    }
    write_json(source / "support.json", supplied)
    original_bytes = (source / "support.json").read_bytes()
    import_dataset(source, store.root / "datasets" / "support", synthetic=True)
    store.save_case(
        {
            "case_id": "supporting-records",
            "dataset_id": "support",
            "as_of": "2026-09-30",
            "question": "Do the supplied milestones explain the payment pattern?",
            "investigations": ["payment_fragmentation"],
            "scope": {"entity_ids": ["E1"]},
        }
    )
    run_id = store.run_case("supporting-records")["run_id"]
    run = store.get_run(run_id)
    assert bool(run["analysis"]["findings"]) is with_findings
    store.save_review(
        run_id,
        {
            "schema_version": "2.2",
            "run_id": run_id,
            "reviewer": "Synthetic analyst",
            "decision": "keep_open",
            "summary": "The schedule offers a benign explanation; request the delivery confirmation.",
            "scope_finding_ids": [
                row["finding_id"] for row in run["analysis"]["findings"]
            ],
            "acknowledge_limitations": True,
        },
    )
    exported = store.export_run(run_id)
    assert exported["verification"]["ok"]
    with zipfile.ZipFile(exported["path"]) as archive:
        assert archive.read("run/data/originals/support.json") == original_bytes
        assert json.loads(archive.read("run/analysis.json")) == run["analysis"]
        for name in ("report.html", "report.md"):
            report = archive.read(name).decode()
            assert "Supplied supporting records" in report
            assert "not automatically corroborated or adopted" in report
            assert "outside the selected entity or date scope" in report
            assert "Original source file: support.json" in report
            assert "Source row: 1" in report
            assert sha256_file(source / "support.json") in report
            for row in supplied["tables"]["diligence"]:
                assert html.escape(row["title"], quote=True) in report
                assert html.escape(row["text"], quote=True) in report
                assert f"Diligence ID: {row['evidence_id']}" in report
                assert f"Associated entity ID: {row['entity_id']}" in report
                assert row["date"] in report
            if with_findings:
                assert "not statements authored or individually adopted" in report
                for finding in run["analysis"]["findings"]:
                    assert html.escape(finding["observation"], quote=True) in report


def test_supplied_claims_and_source_urls_are_escaped_without_invented_provenance(
    tmp_path: Path,
) -> None:
    case, analysis, wrapper = report_inputs(tmp_path)
    title = "Supplier <script>alert(1)</script> | [claim]"
    claim = "Ordinary installments.\n</pre><img src=x onerror=alert(1)>"
    url = 'https://example.test/?note="unsafe"&value=<svg/onload=alert(1)>'
    dataset = {
        "tables": {
            "diligence": [
                {
                    "evidence_id": "D1",
                    "entity_id": "E1",
                    "title": title,
                    "text": claim,
                    "source_url": url,
                }
            ]
        }
    }
    report_html, report_md = evidence._reports(
        case, analysis, wrapper, {"files_checked": 8}, dataset=dataset
    )
    parsed = CoverageTable()
    parsed.feed(report_html.decode())
    assert not ({"script", "img", "svg", "a"} & set(parsed.tags))
    assert html.escape(title, quote=True) in report_html.decode()
    assert html.escape(url, quote=True) in report_html.decode()
    assert "https&#58;//example.test/" in report_md.decode()
    assert "&#91;claim&#93;" in report_md.decode()
    for report in (report_html.decode(), report_md.decode()):
        assert "&lt;/pre&gt;&lt;img" in report
        assert "Date: Not supplied" in report
        assert "Row provenance: Not recorded" in report
        assert "Original file SHA-256" not in report

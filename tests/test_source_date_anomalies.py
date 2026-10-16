"""Contradictory source dates remain visible evidence, not a source outage."""

import json
import shutil
import zipfile
from datetime import date

import pytest
from test_case_review import case_review
from test_investigations import case, dataset
from test_sources_screening import csl_payload, import_csl

from omphalos.evidence import verify_bundle
from omphalos.investigations import analyze
from omphalos.runner import Workspace
from omphalos.screening import candidate_findings
from omphalos.sources import load_source
from omphalos.util import read_json, sha256_file, write_json
from omphalos.workflow import import_subject


def anomalous_payload():
    payload = csl_payload()
    payload["results"][0].update(start_date="2025-11-21", end_date="2024-03-28")
    return payload


def test_inconsistent_interval_is_retained_with_raw_dates_and_bound_diagnostics(
    tmp_path,
):
    payload = anomalous_payload()
    snapshot = import_csl(tmp_path, payload)
    row = next(row for row in snapshot["entries"] if row["upstream_id"] == "one")
    assert row["start_date"] == "2025-11-21"
    assert row["end_date"] == "2024-03-28"
    assert row["raw_record"] == payload["results"][0]
    assert json.loads((tmp_path / "snapshot/raw.json").read_text()) == payload
    assert snapshot["metadata"]["record_count"] == 3
    assert snapshot["metadata"]["parser_version"] == "2.1"
    assert snapshot["metadata"]["effective_date_issue_count"] == 1
    issue = snapshot["metadata"]["effective_date_issues"][0]
    assert issue["record_id"] == row["record_id"]
    assert issue["source_row"] == 1
    assert issue["start_date"] == row["start_date"]
    assert issue["end_date"] == row["end_date"]
    assert "cannot be evaluated" in issue["reason"]
    assert any(
        "contradictory" in warning for warning in snapshot["metadata"]["warnings"]
    )


@pytest.mark.parametrize(
    "as_of", [date(2023, 1, 1), date(2025, 1, 1), date(2026, 10, 15)]
)
def test_inconsistent_dates_neither_imply_expiry_nor_hide_a_matching_identity(
    tmp_path, as_of
):
    snapshot = import_csl(tmp_path, anomalous_payload())
    findings, counts = candidate_findings(
        [{"entity_id": "E1", "name": "Synthetic Harbor Instruments"}], snapshot, as_of
    )
    assert counts["source_records_considered"] == 2
    assert counts["source_records_excluded_by_dates"] == 1  # The consistent future row.
    assert counts["source_records_with_inconsistent_dates"] == 1
    assert len(findings) == 2  # The consistent active row and the unresolved interval.
    flagged = [f for f in findings if f["metrics"].get("listing_date_status")]
    assert len(flagged) == 1
    assert (
        flagged[0]["metrics"]["listing_date_status"] == "inconsistent_source_interval"
    )
    assert flagged[0]["metrics"]["listing_start_date"] == "2025-11-21"
    assert flagged[0]["metrics"]["listing_end_date"] == "2024-03-28"
    assert any("cannot be evaluated" in unknown for unknown in flagged[0]["unknowns"])
    assert flagged[0]["source_refs"]


def test_coverage_explains_date_applicability_gap_without_claiming_source_failure(
    tmp_path,
):
    snapshot = import_csl(tmp_path, anomalous_payload())
    records = dataset(
        {"entities": [{"entity_id": "E1", "name": "Synthetic Harbor Instruments"}]}
    )
    result = analyze(
        records,
        case("screening_candidates", watchlist_snapshot_id="snapshot"),
        snapshot,
    )
    coverage = result["coverage"][0]
    assert coverage["status"] == "executed"
    assert coverage["records_evaluated"] == 1
    assert coverage["findings_count"] == 2
    assert any(
        "1 source records have an end date before their start date" in item
        for item in coverage["limitations"]
    )
    assert any("cannot be evaluated" in item for item in coverage["limitations"])


def test_forged_date_diagnostics_fail_even_when_manifest_hashes_are_replaced(tmp_path):
    import_csl(tmp_path, anomalous_payload())
    path = tmp_path / "snapshot"
    source = read_json(path / "source.json")
    manifest = read_json(path / "source-manifest.json")
    for value in (source["metadata"], manifest):
        value["effective_date_issues"] = []
        value["effective_date_issue_count"] = 0
    write_json(path / "source.json", source)
    manifest["normalized_sha256"] = sha256_file(path / "source.json")
    write_json(path / "source-manifest.json", manifest)
    with pytest.raises(ValueError, match="date diagnostics differ"):
        load_source(path)


def test_older_snapshot_without_date_diagnostics_still_loads(tmp_path):
    snapshot = import_csl(tmp_path, anomalous_payload())
    path = tmp_path / "snapshot"
    source = read_json(path / "source.json")
    manifest = read_json(path / "source-manifest.json")
    for value in (source["metadata"], manifest):
        value["parser_version"] = "2.0"
        value.pop("effective_date_issues")
        value.pop("effective_date_issue_count")
        value["warnings"] = [w for w in value["warnings"] if "contradictory" not in w]
    write_json(path / "source.json", source)
    manifest["normalized_sha256"] = sha256_file(path / "source.json")
    write_json(path / "source-manifest.json", manifest)
    legacy = load_source(path)
    assert legacy["entries"] == snapshot["entries"]
    # Screening derives interval consistency from records even without new metadata.
    _, counts = candidate_findings([], legacy, date(2026, 10, 15))
    assert counts["source_records_with_inconsistent_dates"] == 1


def test_inconsistent_dates_survive_review_export_and_offline_replay(tmp_path):
    workspace = Workspace(tmp_path / "workspace")
    import_subject("Synthetic Harbor Instruments", workspace.root / "datasets/subject")
    import_csl(tmp_path, anomalous_payload())
    shutil.copytree(tmp_path / "snapshot", workspace.root / "sources/snapshot")
    intent = case(
        "screening_candidates", dataset_id="subject", watchlist_snapshot_id="snapshot"
    )
    workspace.save_case(intent)
    run_id = workspace.run_case(intent["case_id"])["run_id"]
    run = workspace.get_run(run_id)
    assert run["verification"]["ok"]
    assert run["screening_source"]["effective_date_issue_count"] == 1
    assert len(run["analysis"]["findings"]) == 2
    shutil.rmtree(workspace.root / "sources/snapshot")
    shutil.rmtree(workspace.root / "datasets/subject")
    workspace.save_review(run_id, case_review(run))
    package = workspace.export_run(run_id)
    assert package["verification"]["ok"]
    assert verify_bundle(package["path"])["ok"]
    assert workspace.replay_run(run_id)["ok"]
    with zipfile.ZipFile(package["path"]) as archive:
        source = json.loads(archive.read("run/sources/source.json"))
        assert source["metadata"]["effective_date_issue_count"] == 1
        report = archive.read("report.md").decode()
        assert "end date precedes its start date" in report
        assert "2025-11-21" in report and "2024-03-28" in report

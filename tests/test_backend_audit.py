"""Regression cases for import, source, analysis, and retained-run audit findings."""

import shutil
from copy import deepcopy

import pytest
from test_case_review import case_review
from test_investigations import case, dataset, sample_prices
from test_sources_screening import csl_payload, import_csl
from test_web import browser as browser

from omphalos.data import create_demo, load_dataset
from omphalos.investigations import analyze, catalog
from omphalos.runner import Workspace
from omphalos.sources import import_source, load_source
from omphalos.util import read_json, sha256_file, write_json
from omphalos.workflow import import_subject, import_vendor_csv, preview_vendor_csv


def test_punctuation_only_addresses_are_not_shared_locations():
    data = dataset(
        {
            "entities": [
                {
                    "entity_id": f"E{i}",
                    "name": f"Synthetic entity {i}",
                    "address": value,
                    "country": "US",
                }
                for i, value in enumerate(("---", "...", "???"))
            ]
        }
    )
    result = analyze(data, case("shared_address", "data_quality"))
    coverage = result["coverage"][0]
    assert coverage["status"] == "not_evaluable"
    assert coverage["records_evaluated"] == 0
    assert any(
        "3 records with unusable address labels" in text
        for text in coverage["limitations"]
    )
    quality = next(f for f in result["findings"] if f["metrics"]["field"] == "address")
    assert quality["metrics"]["unusable_count"] == 3
    assert "missing or unusable" in quality["observation"]
    assert data["tables"]["entities"][0]["address"] == "---"


def test_unknown_payment_punctuation_is_not_a_third_known_method():
    data = sample_prices([1, 1, 1])
    for payment, method in zip(data["tables"]["payments"], ("wire", "cash", "---")):
        payment.update(shipment_id="S0", method=method)
    result = analyze(data, case("mixed_payment_methods", "data_quality"))
    assert result["coverage"][0]["records_evaluated"] == 2
    assert result["coverage"][0]["findings_count"] == 0
    assert any(
        f["metrics"].get("field") == "method" and f["metrics"]["unusable_count"] == 1
        for f in result["findings"]
    )
    data["tables"]["payments"][-1]["method"] = "card"
    assert len(analyze(data, case("mixed_payment_methods"))["findings"]) == 1


def test_punctuation_only_units_do_not_form_comparable_price_cohorts():
    data = sample_prices([1, 1, 1, 1, 100], units=["---"] * 5)
    result = analyze(data, case("unit_price_outlier", "data_quality"))
    assert result["coverage"][0]["status"] == "not_evaluable"
    assert result["coverage"][0]["findings_count"] == 0
    assert any(
        f["metrics"].get("field") == "unit" and f["metrics"]["unusable_count"] == 5
        for f in result["findings"]
    )


def test_unusable_commodity_code_can_use_an_independently_supplied_valid_hs_code():
    data = sample_prices([1, 1, 1, 1, 100])
    for shipment in data["tables"]["shipments"]:
        shipment["commodity_code"] = "---"
    finding = analyze(data, case("unit_price_outlier"))["findings"][0]
    assert finding["metrics"]["commodity_kind"] == "hs"
    assert finding["metrics"]["commodity_code"] == "845610"
    for shipment in data["tables"]["shipments"]:
        shipment["hs_code"] = None
    assert (
        analyze(data, case("unit_price_outlier"))["coverage"][0]["status"]
        == "not_evaluable"
    )


@pytest.mark.parametrize("check", ["broker_concentration", "multi_domain"])
def test_punctuation_labels_do_not_create_network_or_domain_findings(check):
    data = dataset(
        {
            "entities": [
                {"entity_id": f"E{i}", "name": f"Synthetic entity {i}"}
                for i in range(4)
            ],
            "shipments": [
                {
                    "shipment_id": f"S{i}",
                    "exporter_id": "E0",
                    "importer_id": f"E{i+1}",
                    "domain": punctuation,
                }
                for i, punctuation in enumerate(("---", "...", "???"))
            ],
            "payments": [
                {
                    "payment_id": f"P{i}",
                    "shipment_id": f"S{i}",
                    "amount": "1",
                    "ccy": "USD",
                    "broker": "---",
                }
                for i in range(3)
            ],
        }
    )
    result = analyze(data, case(check))
    assert result["findings"] == []
    assert result["coverage"][0]["status"] == "not_evaluable"


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_updated_at", "2099-01-01"),
        ("sources_used", [{"source": "Fabricated"}]),
        ("date_note", "Fabricated freshness interpretation"),
    ],
)
def test_source_derived_metadata_must_reproduce_from_retained_raw_bytes(
    tmp_path, field, value
):
    import_csl(tmp_path)
    path = tmp_path / "snapshot"
    snapshot = read_json(path / "source.json")
    snapshot["metadata"][field] = value
    write_json(path / "source.json", snapshot)
    manifest = read_json(path / "source-manifest.json")
    manifest[field] = value
    manifest["normalized_sha256"] = sha256_file(path / "source.json")
    write_json(path / "source-manifest.json", manifest)
    with pytest.raises(ValueError, match="metadata differs from original"):
        load_source(path)


@pytest.mark.parametrize(
    "patch",
    [
        {"name": "   "},
        {"type": {"unusable": "shape"}},
        {"type": 1},
        {"ids": {}},
        {"ids": ""},
        {"ids": [{"type": "LEI", "number": 123}]},
        {"addresses": {}},
    ],
)
def test_unusable_source_fields_fail_at_import_instead_of_crashing_or_silently_skipping(
    tmp_path, patch
):
    payload = csl_payload()
    payload["results"][0].update(patch)
    raw = tmp_path / "source.json"
    write_json(raw, payload)
    with pytest.raises(ValueError):
        import_source("csl", raw, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_intake_method_survives_import_and_appears_in_saved_dataset_summary(tmp_path):
    workspace = Workspace(tmp_path / "workspace")
    import_subject("Synthetic subject", workspace.root / "datasets/subject")
    csv = tmp_path / "vendors.csv"
    csv.write_text("Company,Country\nSynthetic Vendor,US\n")
    preview = preview_vendor_csv(csv)
    import_vendor_csv(
        csv,
        workspace.root / "datasets/vendors",
        mapping=preview["mapping"],
        preview_id=preview["preview_id"],
    )
    create_demo(workspace.root / "datasets/linked")
    summaries = {row["dataset_id"]: row for row in workspace.list_datasets()}
    assert summaries["subject"]["intake_method"] == "subject_name"
    assert summaries["subject"]["identity_research_retained"] is False
    assert summaries["vendors"]["intake_method"] == "vendor_csv"
    assert summaries["linked"]["intake_method"] == "linked_records"
    assert (
        load_dataset(workspace.root / "datasets/subject")["metadata"]["intake_method"]
        == "subject_name"
    )


def test_all_checks_review_export_and_replay_use_retained_data_after_originals_are_removed(
    tmp_path,
):
    workspace = Workspace(tmp_path / "workspace")
    create_demo(workspace.root / "datasets/linked")
    snapshot = import_csl(tmp_path)
    shutil.copytree(tmp_path / "snapshot", workspace.root / "sources/snapshot")
    payload = case(
        *[row["id"] for row in catalog()],
        dataset_id="linked",
        watchlist_snapshot_id="snapshot",
        parameters={"threshold_cluster": {"threshold": "10000", "currency": "USD"}},
    )
    workspace.save_case(payload)
    run_id = workspace.run_case(payload["case_id"])["run_id"]
    run = workspace.get_run(run_id)
    assert len(run["analysis"]["coverage"]) == len(catalog())
    assert all(
        row["status"] in {"executed", "not_evaluable"}
        for row in run["analysis"]["coverage"]
    )
    names, source = deepcopy(run["entity_names"]), deepcopy(run["screening_source"])
    assert names and source["snapshot_id"] == "snapshot"
    assert source["source_updated_at"] == snapshot["metadata"]["source_updated_at"]
    shutil.rmtree(workspace.root / "datasets/linked")
    shutil.rmtree(workspace.root / "sources/snapshot")
    reopened = Workspace(workspace.root).get_run(run_id)
    assert reopened["verification"]["ok"]
    assert reopened["entity_names"] == names and reopened["screening_source"] == source
    assert workspace.replay_run(run_id)["ok"]
    workspace.save_review(run_id, case_review(reopened))
    assert workspace.export_run(run_id)["verification"]["ok"]
    original = workspace.root / "runs" / run_id / "data/originals/dataset.json"
    original.write_bytes(b"{}")
    failed = workspace.get_run(run_id)
    assert not failed["verification"]["ok"]
    assert failed["entity_names"] == {} and failed["screening_source"] is None


def test_subject_marker_is_available_to_browser_resume(browser):
    server, request = browser
    status, subject, _ = request("/api/workflow/subject", {"name": "Synthetic subject"})
    assert status == 200
    row = next(
        row
        for row in request("/api/state")[1]["datasets"]
        if row["dataset_id"] == subject["dataset_id"]
    )
    assert row["intake_method"] == "subject_name"
    assert row["identity_research_retained"] is False


@pytest.mark.parametrize(
    "placeholder", ["N/A", "NA", "Unknown", "not provided", "null", "TBD"]
)
def test_common_placeholders_do_not_create_label_based_observations(placeholder):
    data = dataset(
        {
            "entities": [
                {
                    "entity_id": f"E{i}",
                    "name": f"Synthetic entity {i}",
                    "address": placeholder,
                    "country": "NA",
                }
                for i in range(4)
            ],
            "shipments": [
                {
                    "shipment_id": f"S{i}",
                    "exporter_id": "E0",
                    "importer_id": f"E{i+1}",
                    "domain": placeholder,
                    "qty": "1",
                    "unit": placeholder,
                    "hs_code": "845610",
                }
                for i in range(3)
            ],
            "payments": [
                {
                    "payment_id": f"P{i}",
                    "shipment_id": f"S{i}",
                    "amount": "100" if i == 2 else "1",
                    "ccy": "USD",
                    "broker": placeholder,
                    "method": placeholder,
                }
                for i in range(3)
            ],
        }
    )
    checks = [
        "shared_address",
        "mixed_payment_methods",
        "broker_concentration",
        "multi_domain",
        "unit_price_outlier",
    ]
    result = analyze(
        data,
        case(
            *checks,
            "data_quality",
            parameters={"unit_price_outlier": {"minimum_cohort": 3}},
        ),
    )
    assert all(
        row["status"] == "not_evaluable"
        for row in result["coverage"]
        if row["investigation_id"] in checks
    )
    assert all(f["investigation_id"] == "data_quality" for f in result["findings"])
    fields = {f["metrics"]["field"] for f in result["findings"]}
    assert {"address", "method", "unit"} <= fields
    assert "country" not in fields
    assert all(e["country"] == "NA" for e in data["tables"]["entities"])


def test_placeholder_detection_preserves_real_names_country_codes_identifiers_and_si_units():
    from omphalos.investigations import _usable_context

    assert _usable_context("NA", "country")
    assert _usable_context("NA-123", "invoice_id")
    assert _usable_context("NA", "commodity_code")
    assert _usable_context("Unknown", "name")
    assert _usable_context("nA", "unit")
    assert _usable_context("123 Unknown Road", "address")
    assert _usable_context("Unknown Brokerage Ltd", "broker")


def test_domain_spelling_variants_do_not_count_as_different_business_domains():
    data = dataset(
        {
            "entities": [{"entity_id": "E1", "name": "Synthetic entity"}],
            "shipments": [
                {"shipment_id": f"S{i}", "exporter_id": "E1", "domain": domain}
                for i, domain in enumerate(
                    ("Machine_tools", "machine-tools", "MACHINE TOOLS")
                )
            ],
        }
    )
    result = analyze(data, case("multi_domain"))
    assert result["coverage"][0]["status"] == "executed"
    assert result["coverage"][0]["records_evaluated"] == 3
    assert result["findings"] == []


def test_si_unit_case_does_not_combine_different_quantity_scales():
    data = sample_prices([1, 1, 1, 1000, 1000, 1000], units=["mg"] * 3 + ["Mg"] * 3)
    result = analyze(
        data,
        case(
            "unit_price_outlier",
            parameters={"unit_price_outlier": {"minimum_cohort": 3}},
        ),
    )
    assert result["coverage"][0]["status"] == "executed"
    assert result["coverage"][0]["records_evaluated"] == 6
    assert result["findings"] == []
    # An outlier inside a comparable cohort is still found, with exact units.
    data["tables"]["payments"][-1]["amount"] = "10000"
    finding = analyze(
        data,
        case(
            "unit_price_outlier",
            parameters={"unit_price_outlier": {"minimum_cohort": 3}},
        ),
    )["findings"][0]
    assert finding["metrics"]["unit"] == "Mg"
    assert finding["metrics"]["cohort_size"] == 3

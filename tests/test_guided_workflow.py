"""Guided intake must be reversible, reviewable, and reproducible."""

from copy import deepcopy
from pathlib import Path

import pytest

from omphalos import investigations
from omphalos.data import (
    DatasetError,
    create_demo,
    import_dataset,
    load_dataset,
    validate_tables,
)
from omphalos.models import Case
from omphalos.runner import Workspace
from omphalos.util import (
    canonical_json,
    read_json,
    sha256_bytes,
    sha256_file,
    write_json,
)
from omphalos.workflow import (
    goal_catalog,
    import_vendor_csv,
    plan_case,
    preview_vendor_csv,
)


def vendor_file(tmp_path: Path, text: str | bytes) -> Path:
    path = tmp_path / "vendors.csv"
    path.write_bytes(text.encode() if isinstance(text, str) else text)
    return path


def imported(tmp_path: Path) -> Path:
    path = vendor_file(
        tmp_path, "Vendor name,Country,Account code\nSame,US,1\nSame,GB,2\n"
    )
    preview = preview_vendor_csv(path)
    dest = tmp_path / "data"
    import_vendor_csv(
        path, dest, mapping=preview["mapping"], preview_id=preview["preview_id"]
    )
    return dest


def rehash_dataset(dest: Path, data: dict) -> None:
    """A rewritten outer checksum must not bypass original-row reproducibility."""
    write_json(dest / "dataset.json", data)
    write_json(
        dest / "dataset-manifest.json",
        {
            "schema_version": "2.0",
            **data["metadata"],
            "dataset_sha256": sha256_file(dest / "dataset.json"),
        },
    )


def dataset(tables: dict | None = None) -> dict:
    tables, _ = validate_tables(
        tables or {"entities": [{"entity_id": "E1", "name": "Example"}]}
    )
    return {"tables": tables, "metadata": {"dataset_id": "data", "synthetic": False}}


def snapshot(updated: str | None = "2026-10-13T01:00:00Z") -> dict:
    # Planning must not inspect list records. Imported-source validation is an
    # upstream boundary; these minimal rows detect any accidental matching call.
    return {
        "snapshot_id": "list1",
        "source_id": "csl",
        "entries": [{}],
        "metadata": {
            "source_updated_at": updated,
            "ingestion_method": "manual_import",
            "warnings": ["Manual import; origin is not verified."],
        },
    }


def propose(data: dict, goal: str, **kwargs) -> dict:
    return plan_case(data, goal, as_of="2026-10-13", case_id="guided1", **kwargs)


def test_preview_retains_rows_bytes_and_physical_multiline_locations(tmp_path):
    raw = (
        b"\xef\xbb\xbfSupplier,Country,Notes,Internal vendor ID\r\n"
        b'"Same, Inc.",United States,"One\r\nTwo",account-1\r\n'
        b'"Same, Inc.",uk,Other,account-2\r\n'
    )
    path = vendor_file(tmp_path, raw)
    preview = preview_vendor_csv(path)
    assert preview["can_import"] and preview["row_count"] == 2
    assert preview["retained_only_columns"] == ["Internal vendor ID"]
    assert [row["country"] for row in preview["preview_rows"]] == ["US", "GB"]
    assert preview["generated_id_count"] == 2
    assert preview["sha256"] == sha256_bytes(raw)
    assert preview == preview_vendor_csv(path)
    dest = tmp_path / "data"
    import_vendor_csv(
        path, dest, mapping=preview["mapping"], preview_id=preview["preview_id"]
    )
    loaded = load_dataset(dest)
    assert (dest / "originals/vendors.csv").read_bytes() == raw
    assert len({row["entity_id"] for row in loaded["tables"]["entities"]}) == 2
    assert {
        origin["source_row"]
        for origin in loaded["metadata"]["provenance"]["entities"].values()
    } == {3, 4}
    assert set(loaded["tables"]) == {"entities"}
    assert any("repeated-name" in warning for warning in preview["warnings"])


def test_existing_ids_are_trimmed_and_preview_retains_file_order(tmp_path):
    path = vendor_file(
        tmp_path,
        "Entity ID,Legal name,LEI,Other names\n Z2 ,Zulu,5493001kjtigc8y1r12,Alias|Other\nA1,Alpha,,\n",
    )
    preview = preview_vendor_csv(path)
    # A malformed identifier is rejected rather than repaired by inventing data.
    assert not preview["can_import"]
    path.write_text(
        path.read_text().replace("5493001kjtigc8y1r12", "5493001kjtigc8y1r12x")
    )
    preview = preview_vendor_csv(path)
    assert preview["can_import"]
    assert [row["entity_id"] for row in preview["preview_rows"]] == ["Z2", "A1"]
    assert preview["generated_id_count"] == 0
    assert preview["preview_rows"][0]["lei"] == "5493001KJTIGC8Y1R12X"


@pytest.mark.parametrize("delimiter", [";", "\t"])
def test_delimiters_are_explicit_and_replayed(tmp_path, delimiter):
    path = vendor_file(
        tmp_path, f"Company name{delimiter}Country\nExample{delimiter}CA\n"
    )
    preview = preview_vendor_csv(path)
    assert preview["delimiter"] == ("tab" if delimiter == "\t" else delimiter)
    dest = tmp_path / "data"
    import_vendor_csv(
        path, dest, mapping=preview["mapping"], preview_id=preview["preview_id"]
    )
    assert load_dataset(dest)["tables"]["entities"][0]["country"] == "CA"


def test_alias_ambiguity_requires_complete_explicit_mapping(tmp_path):
    path = vendor_file(
        tmp_path, "Company,Vendor name,Country,Notes\nOne,Two,US,Context\n"
    )
    assert not preview_vendor_csv(path)["can_import"]
    explicit = {
        "Company": "name",
        "Vendor name": None,
        "Country": "country",
        "Notes": "notes",
    }
    assert preview_vendor_csv(path, explicit)["can_import"]
    for invalid in (
        {"Company": "name"},
        {**explicit, "extra": None},
        {**explicit, "Vendor name": "name"},
        {**explicit, "Notes": "invented_field"},
        {**explicit, "Notes": []},
    ):
        assert not preview_vendor_csv(path, invalid)["can_import"]


@pytest.mark.parametrize(
    "text",
    [
        "name,name\nOne,Two\n",
        "name,country\nOne,US,extra\n",
        "name,country\nOne\n",
        "name\n",
        "name\n\x00bad\n",
    ],
)
def test_invalid_csv_is_rejected_without_row_loss(tmp_path, text):
    with pytest.raises(DatasetError):
        preview_vendor_csv(vendor_file(tmp_path, text))


@pytest.mark.parametrize(
    "text",
    [
        "Company,Country\nExample,Korea\n",
        "Company,Country\n,US\n",
        "Entity ID,Company\nE1,First\nE1,Second\n",
        "Company,LEI\nExample,not-an-lei\n",
    ],
)
def test_invalid_entities_block_whole_import(tmp_path, text):
    path = vendor_file(tmp_path, text)
    preview = preview_vendor_csv(path)
    assert not preview["can_import"] and preview["errors"]
    with pytest.raises(DatasetError):
        import_vendor_csv(
            path,
            tmp_path / "data",
            mapping=preview["mapping"],
            preview_id=preview["preview_id"],
        )
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("change", ["raw_after_sample", "filename", "mapping"])
def test_reviewed_preview_anchors_full_input_and_recipe(tmp_path, change):
    path = vendor_file(tmp_path, "Company,Country\n" + "Example,US\n" * 20)
    preview = preview_vendor_csv(path)
    mapping = dict(preview["mapping"])
    if change == "raw_after_sample":
        path.write_text(path.read_text() + "Unseen row,GB\n")
    elif change == "filename":
        path = path.rename(tmp_path / "renamed.csv")
    else:
        mapping["Country"] = None
    with pytest.raises(DatasetError, match="changed since preview"):
        import_vendor_csv(
            path, tmp_path / "data", mapping=mapping, preview_id=preview["preview_id"]
        )
    assert not (tmp_path / "data").exists()


def test_import_requires_explicit_mapping_and_does_not_overwrite(tmp_path):
    path = vendor_file(tmp_path, "Company\nExample\n")
    preview = preview_vendor_csv(path)
    with pytest.raises(DatasetError, match="explicit column mapping"):
        import_vendor_csv(
            path, tmp_path / "data", mapping=None, preview_id=preview["preview_id"]
        )
    dest = tmp_path / "data"
    dest.mkdir()
    (dest / "keep.txt").write_text("untouched")
    with pytest.raises(DatasetError, match="empty"):
        import_vendor_csv(
            path, dest, mapping=preview["mapping"], preview_id=preview["preview_id"]
        )
    assert (dest / "keep.txt").read_text() == "untouched"


@pytest.mark.parametrize(
    "change",
    ["mapping", "strategy", "preview", "unknown_recipe_key", "drop_row", "row_value"],
)
def test_coherently_rehashed_transform_tampering_is_rejected(tmp_path, change):
    dest = imported(tmp_path)
    data = read_json(dest / "dataset.json")
    recipe = data["metadata"]["import_transform"]
    if change == "mapping":
        recipe["mapping"]["Country"] = None
    elif change == "strategy":
        recipe["id_strategy"] = "guess_same_names"
    elif change == "preview":
        recipe["preview_id"] = "0" * 64
    elif change == "unknown_recipe_key":
        recipe["drop_rows"] = [2]
    elif change == "drop_row":
        removed = data["tables"]["entities"].pop()
        data["metadata"]["counts"]["entities"] -= 1
        del data["metadata"]["provenance"]["entities"][removed["entity_id"]]
    else:
        data["tables"]["entities"][0]["country"] = "DE"
    rehash_dataset(dest, data)
    with pytest.raises(DatasetError):
        load_dataset(dest)


def test_changed_original_bytes_fail_checksum_and_strict_import_remains_strict(
    tmp_path,
):
    dest = imported(tmp_path)
    (dest / "originals/vendors.csv").write_text("Company\nReplacement\n")
    with pytest.raises(DatasetError, match="checksum/size"):
        load_dataset(dest)
    strict = tmp_path / "strict"
    strict.mkdir()
    (strict / "entities.csv").write_text("Vendor name,Country\nExample,US\n")
    with pytest.raises(DatasetError):
        import_dataset(strict, tmp_path / "invalid")


def test_goal_catalog_is_independent_and_uses_real_checks():
    goals = goal_catalog()
    assert {goal["id"] for goal in goals} == {
        "counterparty_screening",
        "transaction_review",
        "data_readiness",
    }
    known = {entry["id"] for entry in investigations.catalog()}
    assert all(set(goal["checks"]) <= known for goal in goals)
    goals[0]["checks"].clear()
    assert goal_catalog()[0]["checks"]


def test_entity_only_plans_separate_missing_source_and_missing_transactions():
    data = dataset()
    screening = propose(data, "counterparty_screening")
    assert not screening["can_run"] and screening["next_action"] == "add_source"
    assert "screening_candidates" in {
        row["id"] for row in screening["unavailable_checks"]
    }
    transaction = propose(data, "transaction_review")
    assert (
        not transaction["can_run"] and transaction["next_action"] == "add_transactions"
    )
    readiness = propose(data, "data_readiness")
    assert readiness["can_run"] and readiness["next_action"] == "run"
    assert readiness["case"]["investigations"] == ["data_quality"]
    assert "missing" in readiness["case"]["question"]


def test_screening_plan_does_not_match_names_and_is_deterministic(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Planning must not run list matching")

    monkeypatch.setattr(investigations, "candidate_findings", unexpected)
    data = dataset()
    source = snapshot()
    plan = propose(data, "counterparty_screening", snapshot=source)
    assert plan["can_run"] and plan["source_status"]["freshness"] == "recent_as_of"
    assert plan["case"]["watchlist_snapshot_id"] == "list1"
    assert "heuristic" in plan["source_status"]["freshness_note"]
    assert plan == propose(data, "counterparty_screening", snapshot=source)
    Case.model_validate(plan["case"])
    assert b"NaN" not in canonical_json(plan)


@pytest.mark.parametrize(
    "updated,expected",
    [
        (None, "unknown"),
        ("bad", "unknown"),
        ("2026-10-01", "stale"),
        ("2026-10-14", "historical_mismatch"),
    ],
)
def test_source_freshness_is_explicit_with_uncertain_dates(updated, expected):
    status = propose(dataset(), "counterparty_screening", snapshot=snapshot(updated))[
        "source_status"
    ]
    assert status["freshness"] == expected
    assert len(status["warnings"]) >= 2
    assert status["ingestion_method"] == "manual_import"


def test_screening_comparison_limit_is_preflighted_without_scanning():
    data = dataset(
        {"entities": [{"entity_id": f"E{i}", "name": "Example"} for i in range(1001)]}
    )
    source = snapshot()
    source["entries"] = [{}] * 20_000
    plan = propose(data, "counterparty_screening", snapshot=source)
    assert not plan["can_run"] and plan["next_action"] == "change_scope"
    assert "20 million" in plan["unavailable_checks"][0]["reason"]


def test_transaction_plan_uses_real_eligibility_and_preserves_as_of(tmp_path):
    create_demo(tmp_path / "demo")
    data = load_dataset(tmp_path / "demo")
    before = deepcopy(data)
    plan = propose(data, "transaction_review")
    assert plan["can_run"]
    assert "payment_fragmentation" in plan["case"]["investigations"]
    assert "threshold_cluster" not in plan["case"]["investigations"]
    assert "weekend" not in plan["case"]["investigations"]
    assert plan["case"]["as_of"] == "2026-10-13"
    actual = investigations.analyze(data, plan["case"])
    assert {
        r["investigation_id"] for r in actual["coverage"] if r["status"] == "executed"
    } == {r["id"] for r in plan["selected_checks"]}
    assert data == before
    assert any("synthetic" in note for note in plan["notes"])


def test_payment_checks_can_run_without_dates_or_shipping_quantity():
    data = dataset(
        {
            "entities": [{"entity_id": "E1", "name": "Example"}],
            "shipments": [{"shipment_id": "S1", "exporter_id": "E1"}],
            "payments": [
                {"payment_id": "P1", "shipment_id": "S1", "amount": "10", "ccy": "USD"}
            ],
        }
    )
    plan = propose(data, "transaction_review")
    assert plan["can_run"] and "payment_fragmentation" in plan["case"]["investigations"]
    assert "unit_price_outlier" in {row["id"] for row in plan["unavailable_checks"]}
    assert any("Undated" in note for note in plan["notes"])
    actual = investigations.analyze(data, plan["case"])
    assert {row["investigation_id"] for row in actual["coverage"]} == {
        row["id"] for row in plan["selected_checks"] + plan["unavailable_checks"]
    }
    assert {
        row["investigation_id"]
        for row in actual["coverage"]
        if row["status"] == "not_evaluable"
    } == {row["id"] for row in plan["unavailable_checks"]}
    data["tables"]["shipments"][0]["date"] = "2027-01-01"
    plan = propose(data, "transaction_review")
    assert not plan["can_run"]
    assert plan["dataset_summary"]["scope_counts"]["shipments_in_scope"] == 0
    assert any("after the assessment" in note for note in plan["notes"])


def test_saved_guided_run_retains_unavailable_checks(tmp_path):
    workspace = Workspace(tmp_path / "workspace")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    write_json(
        inputs / "dataset.json",
        {
            "tables": {
                "entities": [{"entity_id": "E1", "name": "Example"}],
                "shipments": [{"shipment_id": "S1", "exporter_id": "E1"}],
                "payments": [
                    {
                        "payment_id": "P1",
                        "shipment_id": "S1",
                        "amount": "10",
                        "ccy": "USD",
                    }
                ],
            }
        },
    )
    destination = workspace.root / "datasets" / "data"
    import_dataset(inputs, destination)
    plan = propose(load_dataset(destination), "transaction_review")
    assert plan["can_run"] and plan["unavailable_checks"]
    workspace.save_case(plan["case"])
    run = workspace.run_case(plan["case"]["case_id"])
    analysis = read_json(workspace.root / "runs" / run["run_id"] / "analysis.json")
    expected = {row["id"] for row in plan["unavailable_checks"]}
    retained = {
        row["investigation_id"]
        for row in analysis["coverage"]
        if row["status"] == "not_evaluable"
    }
    assert retained == expected
    assert all(
        row["reason"]
        for row in analysis["coverage"]
        if row["status"] == "not_evaluable"
    )


@pytest.mark.parametrize(
    "goal,day,case_id",
    [
        ("unknown", "2026-10-13", "one"),
        ("data_readiness", "10/13/2026", "one"),
        ("data_readiness", "2026-10-13", "../escape"),
    ],
)
def test_plan_rejects_unsupported_or_ambiguous_inputs(goal, day, case_id):
    with pytest.raises(ValueError):
        plan_case(dataset(), goal, as_of=day, case_id=case_id)

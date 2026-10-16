"""Complete linked datasets retain their supplied filenames through replay."""

import shutil
import zipfile

import pytest
from test_case_review import case_review
from test_web import browser as browser
from test_web import case, upload

from omphalos.data import DatasetError, load_dataset
from omphalos.evidence import verify_bundle
from omphalos.util import canonical_json, read_json, sha256_file, write_json


def linked_records():
    return {
        "schema_version": "2.0",
        "tables": {
            "entities": [{"entity_id": "E1", "name": "Synthetic import QA"}],
            "shipments": [{"shipment_id": "S1", "exporter_id": "E1"}],
        },
    }


def test_renamed_dataset_keeps_provenance_through_export_and_offline_replay(browser):
    server, request = browser
    name = "linked-records.JSON"
    original = canonical_json(linked_records())
    status, metadata, _ = request(
        "/api/datasets/import",
        {"dataset_id": "renamed", "files": [upload(name, original)]},
    )
    assert status == 200, metadata
    imported = server.root / "datasets/renamed"
    assert (imported / "originals" / name).read_bytes() == original
    assert load_dataset(imported)["metadata"]["provenance"]["entities"]["E1"] == {
        "source_file": name,
        "source_row": 1,
    }
    assert metadata["source_files"][0]["path"] == f"originals/{name}"
    assert (
        request("/api/cases", case("renamed", investigations=["data_quality"]))[0]
        == 200
    )
    status, created, _ = request("/api/cases/http-case/run", {})
    assert status == 200, created
    run_id = created["run_id"]
    run = request(f"/api/runs/{run_id}")[1]
    assert run["verification"]["ok"]
    assert request(f"/api/runs/{run_id}/review", case_review(run))[0] == 200
    status, exported, _ = request(f"/api/runs/{run_id}/export", {})
    assert status == 200, exported
    assert verify_bundle(exported["path"])["ok"]
    with zipfile.ZipFile(exported["path"]) as archive:
        assert archive.read(f"run/data/originals/{name}") == original
    shutil.rmtree(imported)
    status, replayed, _ = request(f"/api/runs/{run_id}/replay", {})
    assert status == 200 and replayed["ok"], replayed


@pytest.mark.parametrize(
    "value",
    [
        [],
        [{"entity_id": "E1", "name": "Synthetic ambiguous table"}],
        {"entities": [{"entity_id": "E1", "name": "Synthetic missing envelope"}]},
        {"tables": []},
        {"tables": {"entities": []}},
        {**linked_records(), "schema_version": "unknown"},
        {**linked_records(), "metadata": {"synthetic": False}},
        b'{"tables": {}, "tables": {}}',
        b'{"tables":',
    ],
)
def test_renamed_json_rejects_malformed_or_ambiguous_content(browser, value):
    server, request = browser
    status, _, _ = request(
        "/api/datasets/import",
        {"dataset_id": "rejected", "files": [upload("linked-records.json", value)]},
    )
    assert status == 400
    assert not (server.root / "datasets/rejected").exists()


@pytest.mark.parametrize(
    "second",
    [
        upload("entities.json", [{"entity_id": "E2", "name": "Synthetic other"}]),
        upload("second.json", linked_records()),
    ],
)
def test_complete_dataset_cannot_be_mixed_with_other_inputs(browser, second):
    server, request = browser
    status, result, _ = request(
        "/api/datasets/import",
        {
            "dataset_id": "rejected",
            "files": [upload("linked-records.json", linked_records()), second],
        },
    )
    assert status == 400 and "cannot be combined" in result["error"]
    assert not (server.root / "datasets/rejected").exists()


def test_renamed_original_remains_bound_to_normalized_records(browser):
    server, request = browser
    assert (
        request(
            "/api/datasets/import",
            {
                "dataset_id": "renamed",
                "files": [upload("linked.json", linked_records())],
            },
        )[0]
        == 200
    )
    path = server.root / "datasets/renamed"
    data = read_json(path / "dataset.json")
    data["tables"]["entities"][0]["name"] = "Substituted normalized name"
    write_json(path / "dataset.json", data)
    manifest = read_json(path / "dataset-manifest.json")
    manifest["dataset_sha256"] = sha256_file(path / "dataset.json")
    write_json(path / "dataset-manifest.json", manifest)
    with pytest.raises(DatasetError, match="differs from original"):
        load_dataset(path)

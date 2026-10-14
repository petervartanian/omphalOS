from pathlib import Path

import pytest

from omphalos.data import DatasetError, create_demo, import_dataset, load_dataset
from omphalos.util import read_json, sha256_file, write_json


def source(tmp_path: Path, tables: dict) -> Path:
    folder = tmp_path / "input"
    folder.mkdir()
    write_json(folder / "dataset.json", {"tables": tables})
    return folder


def test_csv_precision_provenance_multiline_and_invoice(tmp_path):
    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "entities.csv").write_text(
        'entity_id,name,aliases\n E1 ,"A company\nsecond line",Alias|Other\n'
    )
    (folder / "shipments.csv").write_text(
        "shipment_id,exporter_id,date,invoice_id,hs_code\nS1,E1,2026-01-01,ABC/2026-001,010121\n"
    )
    (folder / "payments.csv").write_text(
        "payment_id,shipment_id,amount,ccy\nP1,S1,9007199254740993.12345678,USD\n"
    )
    dest = tmp_path / "data"
    meta = import_dataset(folder, dest)
    data = load_dataset(dest)
    assert data["tables"]["payments"][0]["amount"] == "9007199254740993.12345678"
    assert data["tables"]["shipments"][0]["hs_code"] == "010121"
    assert meta["provenance"]["entities"]["E1"] == {
        "source_file": "entities.csv",
        "source_row": 3,
    }
    assert (dest / "originals" / "entities.csv").read_bytes() == (
        folder / "entities.csv"
    ).read_bytes()


@pytest.mark.parametrize(
    "patch",
    [
        {"amount": "NaN"},
        {"amount": "Infinity"},
        {"amount": "-1"},
        {"amount": "0"},
        {"amount": "1.000000001"},
        {"amount": True},
        {"ccy": "usd"},
        {"shipment_id": "missing"},
        {"date": 1700000000},
        {"date": "2026-02-30"},
        {"unrecognized": "bad"},
    ],
)
def test_invalid_rows_atomic_rejection(tmp_path, patch):
    payment = {
        "payment_id": "P1",
        "shipment_id": "S1",
        "amount": "1",
        "ccy": "USD",
        **patch,
    }
    folder = source(
        tmp_path,
        {
            "entities": [{"entity_id": "E1", "name": "Entity"}],
            "shipments": [{"shipment_id": "S1", "exporter_id": "E1"}],
            "payments": [payment],
        },
    )
    with pytest.raises(DatasetError):
        import_dataset(folder, tmp_path / "data")
    assert not (tmp_path / "data").exists()


def test_duplicate_ids_and_broken_refs_are_reported(tmp_path):
    folder = source(
        tmp_path,
        {
            "entities": [
                {"entity_id": "E1", "name": "One"},
                {"entity_id": "E1", "name": "Two"},
            ],
            "shipments": [{"shipment_id": "S1", "exporter_id": "missing"}],
        },
    )
    with pytest.raises(DatasetError) as exc:
        import_dataset(folder, tmp_path / "data")
    assert "duplicate" in str(exc.value) and "missing record" in str(exc.value)


def test_duplicate_json_keys_rejected(tmp_path):
    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "entities.json").write_text('[{"entity_id":"E1","name":"A","name":"B"}]')
    with pytest.raises(DatasetError, match="duplicate JSON key"):
        import_dataset(folder, tmp_path / "data")


def test_demo_deterministic_tables_distinct_entities(tmp_path):
    create_demo(tmp_path / "one")
    create_demo(tmp_path / "two")
    one, two = load_dataset(tmp_path / "one"), load_dataset(tmp_path / "two")
    assert one["tables"] == two["tables"]
    assert one["metadata"]["synthetic"] is True
    assert (
        len(
            [
                e
                for e in one["tables"]["entities"]
                if e["name"] == "Synthetic Harbor Instruments"
            ]
        )
        == 2
    )


def test_original_tamper_rejected(tmp_path):
    create_demo(tmp_path / "demo")
    original = tmp_path / "demo" / "originals" / "dataset.json"
    original.write_bytes(original.read_bytes() + b" ")
    with pytest.raises(DatasetError, match="checksum/size"):
        load_dataset(tmp_path / "demo")


def test_rehashed_normalized_data_still_bound_to_original(tmp_path):
    dest = tmp_path / "demo"
    create_demo(dest)
    data = read_json(dest / "dataset.json")
    data["tables"]["entities"][0]["name"] = "Fabricated replacement"
    write_json(dest / "dataset.json", data)
    manifest = read_json(dest / "dataset-manifest.json")
    manifest["dataset_sha256"] = sha256_file(dest / "dataset.json")
    write_json(dest / "dataset-manifest.json", manifest)
    with pytest.raises(DatasetError, match="differs from original"):
        load_dataset(dest)


@pytest.mark.parametrize(
    "patch",
    [
        {"parent_id": "missing"},
        {"parent_id": "E1"},
        {"ownership_percent": "100.01"},
        {"valid_from": "2026-10-01", "valid_to": "2025-01-01"},
        {"source_url": "javascript:alert(1)"},
    ],
)
def test_ownership_rejects_invalid_relationships(tmp_path, patch):
    row = {"relationship_id": "R1", "child_id": "E1", "parent_id": "E2", **patch}
    folder = source(
        tmp_path,
        {
            "entities": [
                {"entity_id": "E1", "name": "One"},
                {"entity_id": "E2", "name": "Two"},
            ],
            "ownership": [row],
        },
    )
    with pytest.raises(DatasetError):
        import_dataset(folder, tmp_path / "data")


def test_ownership_and_diligence_retained_without_inferred_relationships(tmp_path):
    folder = source(
        tmp_path,
        {
            "entities": [
                {"entity_id": "E1", "name": "One"},
                {"entity_id": "E2", "name": "Two"},
            ],
            "ownership": [
                {
                    "relationship_id": "R1",
                    "child_id": "E1",
                    "parent_id": "E2",
                    "ownership_percent": "49.5",
                    "source_url": "https://example.test/filing",
                }
            ],
            "diligence": [
                {
                    "evidence_id": "D1",
                    "entity_id": "E1",
                    "title": "Example filed document",
                    "text": "A supplied observation retained for review.",
                }
            ],
        },
    )
    import_dataset(folder, tmp_path / "data")
    result = load_dataset(tmp_path / "data")
    assert result["tables"]["ownership"][0]["ownership_percent"] == "49.5"
    assert result["metadata"]["provenance"]["diligence"]["D1"]["source_row"] == 1


def test_whitespace_optional_date_is_missing(tmp_path):
    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "entities.csv").write_text("entity_id,name\nE1,Example\n")
    (folder / "shipments.csv").write_text("shipment_id,exporter_id,date\nS1,E1,   \n")
    import_dataset(folder, tmp_path / "data")
    assert load_dataset(tmp_path / "data")["tables"]["shipments"][0]["date"] is None

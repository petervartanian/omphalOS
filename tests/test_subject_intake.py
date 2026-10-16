"""Direct subject intake retains its origin and uses the real screening path."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest
from test_guided_web import run_payload
from test_web import browser as browser
from test_web import upload

from omphalos.data import DatasetError, load_dataset
from omphalos.util import read_json, sha256_bytes
from omphalos.workflow import import_subject


@pytest.mark.parametrize(
    "name",
    [
        None,
        True,
        12,
        [],
        {},
        "",
        "   ",
        "A" * 201,
        "First\nSecond",
        "Subject\tName",
        "Name\x00",
        "\rName",
        "Name\x7f",
        "Name\u0085",
        "Name\u202e",
        "Name\u2028Second",
        "Name\u2029Second",
        "Name\ud800",
    ],
)
def test_subject_rejects_invalid_names_without_creating_dataset(
    tmp_path: Path, name: Any
) -> None:
    destination = tmp_path / "subject"
    with pytest.raises(ValueError):
        import_subject(name, destination)
    assert not destination.exists()


def test_subject_preserves_input_provenance_without_network_or_invented_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def prohibit_network(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Direct subject intake must not make an external connection")

    monkeypatch.setattr(socket.socket, "connect", prohibit_network)
    original_name = "  Société Ágora 华为技术  "
    destination = tmp_path / "direct-subject"
    metadata = import_subject(original_name, destination)
    assert metadata["label"] == original_name.strip()
    assert metadata["synthetic"] is False
    assert metadata["counts"] == {"entities": 1}
    original = destination / "originals/entities.json"
    original_record = read_json(original)[0]
    assert original_record["name"] == original_name
    assert metadata["source_files"] == [
        {
            "path": "originals/entities.json",
            "sha256": sha256_bytes(original.read_bytes()),
            "size_bytes": original.stat().st_size,
        }
    ]
    dataset = load_dataset(destination)
    record = dataset["tables"]["entities"][0]
    assert record["name"] == original_name.strip()
    assert record["entity_type"] == "unknown"
    assert record["country"] is None
    assert record["registration_id"] is None
    assert record["lei"] is None
    assert record["aliases"] == []
    assert "User-provided subject name entered directly" in record["notes"]
    assert "not been verified" in record["notes"]
    assert "not from an uploaded file or an external source" in record["notes"]
    assert dataset["metadata"]["provenance"]["entities"] == {
        record["entity_id"]: {"source_file": "entities.json", "source_row": 1}
    }
    original.write_bytes(original.read_bytes().replace(b"unknown", b"organization"))
    with pytest.raises(DatasetError, match="checksum/size"):
        load_dataset(destination)


def test_subject_accepts_200_characters_and_preserves_punctuation(
    tmp_path: Path,
) -> None:
    name = 'A&B "Subject", ' + "é" * 185
    assert len(name) == 200
    import_subject(name, tmp_path / "boundary")
    assert load_dataset(tmp_path / "boundary")["tables"]["entities"][0]["name"] == name


@pytest.mark.parametrize(
    "body",
    [{}, {"name": "Name", "country": "US"}, {"name": None}, {"name": "\nName"}],
)
def test_subject_api_rejects_invalid_contract(
    browser: tuple[Any, Any], body: dict
) -> None:
    server, request = browser
    status, result, _ = request("/api/workflow/subject", body)
    assert status == 400, result
    assert not list((server.root / "datasets").iterdir())


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://example.com"},
        {"Origin": ""},
        {"X-Omphalos-Token": "wrong"},
        {"Host": "example.com"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_subject_api_requires_same_origin_session(
    browser: tuple[Any, Any], headers: dict
) -> None:
    server, request = browser
    status, result, _ = request(
        "/api/workflow/subject", {"name": "Submitted Subject"}, headers=headers
    )
    assert status == 403, result
    assert not list((server.root / "datasets").iterdir())


def test_repeated_subject_submissions_remain_separate(browser: tuple[Any, Any]) -> None:
    server, request = browser
    datasets, entities = set(), set()
    for _ in range(2):
        status, imported, _ = request(
            "/api/workflow/subject", {"name": "  Submitted Subject  "}
        )
        assert status == 200, imported
        assert imported["label"] == "Submitted Subject"
        assert imported["dataset_id"].startswith("subject_")
        datasets.add(imported["dataset_id"])
        dataset = load_dataset(server.root / "datasets" / imported["dataset_id"])
        entities.add(dataset["tables"]["entities"][0]["entity_id"])
    assert len(datasets) == len(entities) == 2


def test_subject_screening_runs_and_replays_without_fabricating_review(
    browser: tuple[Any, Any],
) -> None:
    server, request = browser
    name = "Synthetic Harbor Instruments"
    status, imported, _ = request("/api/workflow/subject", {"name": name})
    assert status == 200, imported
    snapshot = {
        "total": 1,
        "offset": 0,
        "search_performed_at": "2026-10-14T12:00:00Z",
        "sources_used": [],
        "results": [
            {
                "id": "fixture-entry",
                "source": "Entity List (EL)",
                "name": name,
                "type": "Entity",
                "addresses": [{"country": "US"}],
            }
        ],
    }
    status, source, _ = request(
        "/api/sources/import",
        {"source_id": "csl", "files": [upload("fixture.json", snapshot)]},
    )
    assert status == 200, source
    inputs = {
        "dataset_id": imported["dataset_id"],
        "goal_id": "counterparty_screening",
        "as_of": "2026-10-14",
        "watchlist_snapshot_id": source["snapshot_id"],
    }
    status, proposed, _ = request("/api/workflow/plan", inputs)
    assert status == 200 and proposed["can_run"], proposed
    status, executed, _ = request(
        "/api/workflow/run",
        run_payload(request, inputs, proposed),
    )
    assert status == 200, executed
    run_id = executed["run_id"]
    status, run, _ = request(f"/api/runs/{run_id}")
    assert status == 200 and run["verification"]["ok"], run
    candidates = [
        row
        for row in run["analysis"]["findings"]
        if row["investigation_id"] == "screening_candidates"
    ]
    assert len(candidates) == 1
    assert candidates[0]["metrics"]["country_context"] == "unknown"
    assert candidates[0]["metrics"]["entity_type_context"] == "unknown"
    assert candidates[0]["source_refs"][0]["snapshot_id"] == source["snapshot_id"]
    archived = load_dataset(server.root / "runs" / run_id / "data")
    assert archived["tables"]["entities"][0]["name"] == name
    assert "entered directly" in archived["tables"]["entities"][0]["notes"]
    assert request(f"/api/runs/{run_id}/replay", {})[1]["ok"]
    assert run["latest_review"] is None
    assert run["review_validation"]["ok"] is False
    assert request(f"/api/runs/{run_id}/export", {})[0] == 400

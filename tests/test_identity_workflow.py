"""Public identity context remains attributable, optional, and reproducible offline."""

from __future__ import annotations

import json
import socket
import zipfile
from urllib.parse import parse_qs, urlsplit

import pytest
from test_case_review import case_review
from test_web import browser as browser
from test_web import case

from omphalos import identity_research
from omphalos.data import import_dataset, load_dataset
from omphalos.identity_workflow import (
    load_bound_research,
    research_identity,
    select_identity,
)
from omphalos.runner import Workspace
from omphalos.util import canonical_json, read_json, sha256_file, write_json
from omphalos.workflow import import_subject

LEI = "549300SYNTHETIC00001"


@pytest.fixture
def provider(monkeypatch):
    """Exercise the real provider transcript/replay with synthetic HTTP bytes."""
    configuration = {"status": "candidate", "calls": []}

    def download(url):
        configuration["calls"].append(url)
        if configuration["status"] == "unavailable":
            raise OSError("Synthetic provider outage")
        if urlsplit(url).hostname == "api.gleif.org":
            rows = []
            if configuration["status"] == "candidate":
                rows.append(
                    {
                        "id": LEI,
                        "attributes": {
                            "entity": {
                                "legalName": {
                                    "name": "Synthetic Harbor Instruments Ltd"
                                },
                                "otherNames": [{"name": "Synthetic Harbor"}],
                                "registeredAs": "SYNTHETIC-12345",
                                "legalAddress": {
                                    "addressLines": ["1 Synthetic Street"],
                                    "city": "Example City",
                                    "country": "GB",
                                    "postalCode": "EX1 1AA",
                                },
                            },
                            "registration": {"status": "ISSUED"},
                        },
                    }
                )
            return canonical_json({"data": rows})
        assert parse_qs(urlsplit(url).query)["action"] == ["wbsearchentities"]
        return canonical_json({"search": []})

    monkeypatch.setattr(identity_research, "_download", download)
    return configuration


def prepare(tmp_path, provider):
    base, research, derived = (
        tmp_path / name for name in ("entered", "research", "enriched")
    )
    import_subject("  Synthetic Harbor Instruments  ", base)
    report = research_identity(base, research)
    return base, research, derived, report


def test_selected_profile_preserves_entered_name_original_bytes_and_attribution(
    tmp_path, provider
):
    base, research, derived, report = prepare(tmp_path, provider)
    original_bytes = (base / "originals/entities.json").read_bytes()
    candidate = report["candidates"][0]
    metadata = select_identity(base, research, derived, candidate["candidate_id"])
    data = load_dataset(derived)
    entity = data["tables"]["entities"][0]
    assert entity["name"] == "Synthetic Harbor Instruments"
    assert entity["country"] == "GB"
    assert entity["lei"] == LEI
    assert entity["registration_id"] == "SYNTHETIC-12345"
    assert entity["aliases"] == ["Synthetic Harbor", "Synthetic Harbor Instruments Ltd"]
    assert entity["entity_type"] == "organization"
    assert (derived / "originals/entities.json").read_bytes() == original_bytes
    assert (derived / "base/originals/entities.json").read_bytes() == original_bytes
    assert load_dataset(base)["tables"]["entities"][0]["country"] is None
    context = metadata["identity_research"]
    assert context["selected_candidate"] == candidate
    assert context["association"] == "user_selected_public_record"
    assert (
        context["applied_fields"]["country"]["claims"][0]["kind"] == "gleif_reference"
    )
    assert context["applied_fields"]["country"]["claims"][0]["value"] == "GB"
    assert "does not confirm" in context["notice"]
    assert context["conflicts"] == []
    assert read_json(derived / "research/binding.json")[
        "dataset_sha256"
    ] == sha256_file(base / "dataset.json")
    assert report["providers"][1]["status"] == "no_match"


def test_existing_identity_and_other_entities_are_not_overwritten(tmp_path, provider):
    source, base, research, derived = (
        tmp_path / name for name in ("source", "base", "research", "derived")
    )
    write_json(
        source / "entities.json",
        [
            {
                "entity_id": "one",
                "name": "Entered Name",
                "country": "US",
                "address": "Entered address",
                "entity_type": "organization",
                "aliases": ["Entered alias"],
            },
            {"entity_id": "two", "name": "Other Entity"},
        ],
    )
    import_dataset(source, base, synthetic=True)
    before = load_dataset(base)
    with pytest.raises(ValueError, match="Choose an entity"):
        research_identity(base, tmp_path / "ambiguous")
    with pytest.raises(ValueError, match="absent"):
        research_identity(base, tmp_path / "absent", "absent")
    report = research_identity(base, research, "one")
    select_identity(base, research, derived, report["candidates"][0]["candidate_id"])
    after = load_dataset(derived)
    first, second = after["tables"]["entities"]
    assert second == before["tables"]["entities"][1]
    assert first["name"] == "Entered Name"
    assert first["country"] == "US" and first["address"] == "Entered address"
    assert first["entity_type"] == "organization"
    assert "Entered alias" in first["aliases"]
    assert {
        row["field"] for row in after["metadata"]["identity_research"]["conflicts"]
    } == {"country", "address"}
    assert after["metadata"]["synthetic"] is True


@pytest.mark.parametrize("status", ["no_match", "unavailable", "candidate"])
def test_name_only_continuation_retains_attempt_without_inventing_fields(
    tmp_path, provider, status
):
    provider["status"] = status
    base, research, derived, report = prepare(tmp_path, provider)
    expected = "candidates" if status == "candidate" else status
    assert report["status"] == expected
    metadata = select_identity(base, research, derived, None)
    assert load_dataset(derived)["tables"] == load_dataset(base)["tables"]
    context = metadata["identity_research"]
    assert context["status"] == expected
    assert context["association"] == "no_profile_selected"
    assert context["selected_candidate"] is None
    assert context["applied_fields"] == {}
    assert context["claims"] == []
    if status == "unavailable":
        assert all(p["status"] == "unavailable" for p in context["providers"])
        assert all(
            "Synthetic provider outage" in p["error"] for p in context["providers"]
        )
    assert (
        load_bound_research(derived / "research")[1] == load_bound_research(research)[1]
    )


def test_selection_rejects_wrong_candidate_and_wrong_dataset_binding(
    tmp_path, provider
):
    base, research, derived, report = prepare(tmp_path, provider)
    with pytest.raises(ValueError, match="Choose a candidate"):
        select_identity(base, research, derived, "unretained-candidate")
    import_subject("Synthetic Harbor Instruments", tmp_path / "other")
    with pytest.raises(ValueError, match="dataset or subject changed"):
        select_identity(
            tmp_path / "other",
            research,
            derived,
            report["candidates"][0]["candidate_id"],
        )
    for invalid in (False, 42, {}, ""):
        with pytest.raises(ValueError, match="retained identity candidate"):
            select_identity(base, research, derived, invalid)
    assert not derived.exists()


def rewrite_outer_manifest(path, data):
    write_json(path / "dataset.json", data)
    write_json(
        path / "dataset-manifest.json",
        {
            "schema_version": "2.0",
            **data["metadata"],
            "dataset_sha256": sha256_file(path / "dataset.json"),
        },
    )


def test_rederived_fields_reject_forged_normalized_data_even_with_rehashed_manifest(
    tmp_path, provider
):
    base, research, derived, report = prepare(tmp_path, provider)
    select_identity(base, research, derived, report["candidates"][0]["candidate_id"])
    data = load_dataset(derived)
    data["tables"]["entities"][0]["country"] = "US"
    rewrite_outer_manifest(derived, data)
    with pytest.raises(ValueError, match="retained research transformation"):
        load_dataset(derived)


def test_raw_research_damage_is_rejected_and_not_misreported_as_outage(
    tmp_path, provider
):
    base, research, derived, report = prepare(tmp_path, provider)
    select_identity(base, research, derived, report["candidates"][0]["candidate_id"])
    raw = derived / "research/provider/raw-001.json"
    raw.write_bytes(raw.read_bytes().replace(b"GB", b"US"))
    with pytest.raises(ValueError, match="research bytes changed"):
        load_dataset(derived)


def test_offline_run_replay_export_and_resume_retain_original_and_research(
    tmp_path, provider, monkeypatch
):
    workspace = Workspace(tmp_path / "workspace")
    base = workspace.root / "datasets/entered"
    research = workspace.root / "research/public-records"
    derived = workspace.root / "datasets/enriched"
    import_subject("Synthetic Harbor Instruments", base)
    report = research_identity(base, research)
    selected = select_identity(
        base, research, derived, report["candidates"][0]["candidate_id"]
    )
    payload = case("enriched", investigations=["data_quality"])
    workspace.save_case(payload)
    run_id = workspace.run_case(payload["case_id"])["run_id"]

    def offline(*args, **kwargs):
        pytest.fail("Retained research must replay without any network")

    monkeypatch.setattr(socket.socket, "connect", offline)
    monkeypatch.setattr(identity_research, "_download", offline)
    reopened = Workspace(workspace.root)
    run = reopened.get_run(run_id)
    assert run["verification"]["ok"]
    assert run["identity_research"] == selected["identity_research"]
    assert run["latest_export"] is None
    assert reopened.replay_run(run_id)["ok"]
    reopened.save_review(run_id, case_review(run))
    exported = reopened.export_run(run_id)
    assert exported["verification"]["ok"]
    with zipfile.ZipFile(exported["path"]) as archive:
        entered = json.loads(archive.read("run/data/base/originals/entities.json"))[0]
        assert entered["name"] == "Synthetic Harbor Instruments"
        retained = json.loads(archive.read("run/data/research/provider/report.json"))
        assert retained["candidates"] == report["candidates"]
        assert archive.read("run/data/research/provider/raw-001.json")
    assert reopened.get_run(run_id)["latest_export"]["name"] == exported["name"]
    # Continuing from a retained prior run produces a separate dataset and keeps
    # that original run, its selected association, and its evidence unchanged.
    before = sha256_file(workspace.root / "runs" / run_id / "manifest.json")
    select_identity(base, research, workspace.root / "datasets/name-only", None)
    assert sha256_file(workspace.root / "runs" / run_id / "manifest.json") == before
    assert (
        reopened.get_run(run_id)["identity_research"] == selected["identity_research"]
    )
    raw = workspace.root / "runs" / run_id / "data/research/provider/raw-001.json"
    raw.write_bytes(b"{}")
    damaged = reopened.get_run(run_id)
    assert not damaged["verification"]["ok"]
    assert damaged["identity_research"] is None
    assert damaged["latest_export"] is None


@pytest.mark.parametrize("candidate", ["selected", None])
def test_identity_http_workflow_uses_bound_server_side_selection(
    browser, provider, candidate
):
    server, request = browser
    status, subject, _ = request(
        "/api/workflow/subject", {"name": "Synthetic Harbor Instruments"}
    )
    assert status == 200
    status, report, _ = request(
        "/api/workflow/identity-research", {"dataset_id": subject["dataset_id"]}
    )
    assert status == 200, report
    candidate_id = report["candidates"][0]["candidate_id"] if candidate else None
    status, selected, _ = request(
        "/api/workflow/identity-select",
        {
            "dataset_id": subject["dataset_id"],
            "research_id": report["research_id"],
            "candidate_id": candidate_id,
        },
    )
    assert status == 200, selected
    data = load_dataset(server.root / "datasets" / selected["dataset_id"])
    assert data["tables"]["entities"][0]["name"] == "Synthetic Harbor Instruments"
    assert data["tables"]["entities"][0]["country"] == ("GB" if candidate else None)
    assert selected["dataset_id"] != subject["dataset_id"]
    status, invalid, _ = request(
        "/api/workflow/identity-select",
        {
            "dataset_id": subject["dataset_id"],
            "research_id": report["research_id"],
            "candidate_id": candidate_id,
            "country": "US",
        },
    )
    assert status == 400, invalid
    status, invalid, _ = request(
        "/api/workflow/identity-research",
        {"dataset_id": subject["dataset_id"]},
        headers={"Origin": "https://unrelated.example"},
    )
    assert status == 403, invalid


def test_directory_claims_keep_directory_attribution_through_derivation(
    tmp_path, monkeypatch
):
    from test_identity_research import install_provider, wikidata_records

    install_provider(monkeypatch, entities=wikidata_records())
    base, research, derived = (
        tmp_path / name for name in ("entered", "research", "derived")
    )
    import_subject("Aster Research", base)
    report = research_identity(base, research)
    metadata = select_identity(
        base, research, derived, report["candidates"][0]["candidate_id"]
    )
    context = metadata["identity_research"]
    assert load_dataset(derived)["tables"]["entities"][0]["country"] == "GB"
    assert (
        context["applied_fields"]["country"]["claims"][0]["kind"] == "directory_claim"
    )
    address = context["applied_fields"]["address"]["claims"][0]
    assert address["kind"] == "directory_claim"
    assert address["reference_urls"] == ["https://aster.example/contact"]
    assert all(c["kind"] == "directory_claim" for c in context["claims"])


@pytest.mark.parametrize("provider_status", ["no_match", "unavailable"])
def test_single_character_name_can_continue_after_public_lookup(
    browser, provider, provider_status
):
    server, request = browser
    provider["status"] = provider_status
    status, entered, _ = request("/api/workflow/subject", {"name": "李"})
    assert status == 200, entered
    status, report, _ = request(
        "/api/workflow/identity-research", {"dataset_id": entered["dataset_id"]}
    )
    assert status == 200 and report["status"] == provider_status, report
    status, retained, _ = request(
        "/api/workflow/identity-select",
        {
            "dataset_id": entered["dataset_id"],
            "research_id": report["research_id"],
            "candidate_id": None,
        },
    )
    assert status == 200, retained
    data = load_dataset(server.root / "datasets" / retained["dataset_id"])
    assert data["tables"]["entities"][0]["name"] == "李"
    assert data["metadata"]["identity_research"]["status"] == provider_status
    assert data["metadata"]["identity_research"]["selected_candidate"] is None
    assert data["metadata"]["identity_research"]["applied_fields"] == {}


def test_resumed_research_preserves_prior_attribution_and_unrelated_tables(
    tmp_path, provider
):
    from omphalos.data import create_demo

    base, research, derived = (
        tmp_path / name for name in ("entered", "research", "derived")
    )
    create_demo(base)
    original = load_dataset(base)
    entity_id = original["tables"]["entities"][0]["entity_id"]
    report = research_identity(base, research, entity_id)
    first = select_identity(
        base, research, derived, report["candidates"][0]["candidate_id"]
    )
    data = load_dataset(derived)
    assert {k: v for k, v in data["tables"].items() if k != "entities"} == {
        k: v for k, v in original["tables"].items() if k != "entities"
    }
    provider["status"] = "unavailable"
    research_identity(derived, tmp_path / "retry", entity_id)
    metadata = select_identity(derived, tmp_path / "retry", tmp_path / "resumed", None)
    resumed = load_dataset(tmp_path / "resumed")
    assert resumed["tables"] == data["tables"]
    context = metadata["identity_research"]
    assert context["selected_candidate"] is None
    assert context["status"] == "unavailable"
    assert context["history"] == [
        {k: v for k, v in first["identity_research"].items() if k != "history"}
    ]
    assert (
        load_bound_research(tmp_path / "resumed/base/research")[1]["candidates"]
        == report["candidates"]
    )


@pytest.mark.parametrize("entity_type", ["person", "Individual", "vessel", "aircraft"])
def test_incompatible_profile_cannot_inject_corporate_attributes(
    tmp_path, provider, entity_type
):
    source, base, research, derived = (
        tmp_path / name for name in ("source", "base", "research", "derived")
    )
    write_json(
        source / "entities.json",
        [
            {
                "entity_id": "subject",
                "name": "Synthetic Harbor",
                "entity_type": entity_type,
            }
        ],
    )
    import_dataset(source, base, synthetic=True)
    report = research_identity(base, research)
    before = load_dataset(base)
    with pytest.raises(ValueError, match="different entity type"):
        select_identity(
            base, research, derived, report["candidates"][0]["candidate_id"]
        )
    assert not derived.exists()
    assert load_dataset(base) == before
    select_identity(base, research, derived, None)
    assert load_dataset(derived)["tables"] == before["tables"]


def test_person_profile_selection_supplies_type_without_corporate_or_contact_fields(
    tmp_path, monkeypatch
):
    from test_identity_research import install_provider, item, statement

    install_provider(
        monkeypatch,
        entities={
            "Q100": {
                "labels": {"en": {"value": "Example Person"}},
                "descriptions": {"en": {"value": "public scientist"}},
                "claims": {"P31": [statement(item("Q5"))]},
            }
        },
    )
    base, research, derived = (
        tmp_path / name for name in ("entered", "research", "derived")
    )
    import_subject("Example Person", base)
    report = research_identity(base, research)
    select_identity(base, research, derived, report["candidates"][0]["candidate_id"])
    entity = load_dataset(derived)["tables"]["entities"][0]
    assert entity["entity_type"] == "person"
    assert all(
        entity[field] is None
        for field in (
            "country",
            "address",
            "city",
            "postal_code",
            "registration_id",
            "lei",
        )
    )


def test_separate_entity_selections_keep_both_attributions_and_parent_binding(
    tmp_path, provider
):
    source, base = tmp_path / "source", tmp_path / "base"
    write_json(
        source / "entities.json",
        [
            {
                "entity_id": "one",
                "name": "First entered name",
                "entity_type": "unknown",
            },
            {
                "entity_id": "two",
                "name": "Second entered name",
                "entity_type": "unknown",
            },
        ],
    )
    import_dataset(source, base, synthetic=True)
    first_report = research_identity(base, tmp_path / "first-research", "one")
    first = select_identity(
        base,
        tmp_path / "first-research",
        tmp_path / "first",
        first_report["candidates"][0]["candidate_id"],
    )
    first_entity = load_dataset(tmp_path / "first")["tables"]["entities"][0]
    second_report = research_identity(
        tmp_path / "first", tmp_path / "second-research", "two"
    )
    second = select_identity(
        tmp_path / "first",
        tmp_path / "second-research",
        tmp_path / "second",
        second_report["candidates"][0]["candidate_id"],
    )
    data = load_dataset(tmp_path / "second")
    assert data["tables"]["entities"][0] == first_entity
    assert data["tables"]["entities"][1]["name"] == "Second entered name"
    assert second["identity_research"]["entity_id"] == "two"
    assert second["identity_research"]["history"] == [
        {k: v for k, v in first["identity_research"].items() if k != "history"}
    ]
    with pytest.raises(ValueError, match="dataset or subject changed"):
        select_identity(
            tmp_path / "first", tmp_path / "first-research", tmp_path / "stale", None
        )

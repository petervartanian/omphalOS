"""Identity discovery preserves provenance and never decides identity by rank."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from omphalos import identity_research as research
from omphalos.util import canonical_json, sha256_bytes


def snak(value):
    return {"snaktype": "value", "datavalue": {"value": value}}


def statement(value, **extra):
    return {"mainsnak": snak(value), "rank": "normal", **extra}


def item(qid):
    return {"id": qid, "entity-type": "item"}


def gleif_record():
    return {
        "id": "12345678901234567890",
        "attributes": {
            "entity": {
                "legalName": {"name": "Aster Research Limited"},
                "otherNames": [{"name": "Aster Research"}],
                "registeredAs": "12345678",
                "legalAddress": {
                    "addressLines": ["12 Observatory Road"],
                    "city": "Oxford",
                    "postalCode": "OX1 1AA",
                    "country": "GB",
                },
            },
            "registration": {"status": "LAPSED"},
        },
    }


def wikidata_records():
    return {
        "Q100": {
            "labels": {"en": {"value": "Aster Research"}},
            "descriptions": {"en": {"value": "aerospace company"}},
            "aliases": {"en": [{"value": "Aster Research Limited"}]},
            "claims": {
                "P31": [statement(item("Q783794"))],
                # Historical country on the organization must not propagate.
                "P17": [statement(item("Q400"))],
                "P159": [
                    statement(
                        item("Q200"),
                        qualifiers={
                            "P6375": [
                                snak(
                                    {
                                        "text": "12 Observatory Road, Oxford, OX1 1AA",
                                        "language": "en",
                                    }
                                )
                            ]
                        },
                        references=[
                            {"snaks": {"P854": [snak("https://aster.example/contact")]}}
                        ],
                    )
                ],
                "P856": [statement("https://aster.example/")],
            },
        },
        "Q200": {
            "labels": {"en": {"value": "Oxford"}},
            "claims": {
                "P31": [statement(item("Q515"))],
                "P17": [
                    statement(item("Q300"), rank="preferred"),
                    statement(item("Q400")),
                ],
            },
        },
        "Q300": {
            "labels": {"en": {"value": "United Kingdom"}},
            "claims": {"P297": [statement("GB")]},
        },
    }


def install_provider(monkeypatch, *, gleif=None, entities=None, error=None):
    entities = entities or {}
    calls = []

    def download(url):
        calls.append(url)
        parsed = urlsplit(url)
        params = parse_qs(parsed.query)
        if parsed.hostname == "api.gleif.org":
            if error:
                raise OSError(error)
            return canonical_json({"data": gleif or []})
        if params["action"] == ["wbsearchentities"]:
            return canonical_json({"search": [{"id": "Q100"}] if entities else []})
        ids = params["ids"][0].split("|")
        return canonical_json(
            {"entities": {qid: entities[qid] for qid in ids if qid in entities}}
        )

    monkeypatch.setattr(research, "_download", download)
    return calls


def test_gleif_records_keep_identifiers_status_and_direct_claims(tmp_path, monkeypatch):
    install_provider(monkeypatch, gleif=[gleif_record()])
    report = research.research_subject("Aster Research", tmp_path / "provider")
    candidate = report["candidates"][0]
    assert report["status"] == "candidates"
    assert "LAPSED" in candidate["description"]
    assert candidate["fields"] == {
        "lei": "12345678901234567890",
        "registration_id": "12345678",
        "country": "GB",
        "city": "Oxford",
        "postal_code": "OX1 1AA",
        "address": "12 Observatory Road, Oxford, OX1 1AA, GB",
    }
    for field, value in candidate["fields"].items():
        assert any(
            c["field"] == field and c["value"] == value for c in candidate["claims"]
        )
    assert all(c["kind"] == "gleif_reference" for c in candidate["claims"])
    assert "selected_candidate_id" not in report
    assert research.load_research(tmp_path / "provider") == report


def test_directory_address_is_literal_and_country_follows_current_headquarters(
    tmp_path, monkeypatch
):
    calls = install_provider(monkeypatch, entities=wikidata_records())
    report = research.research_subject("Aster Research", tmp_path / "provider")
    c = report["candidates"][0]
    assert c["fields"] == {
        "address": "12 Observatory Road, Oxford, OX1 1AA",
        "city": "Oxford",
        "country": "GB",
    }
    address = next(c for c in c["claims"] if c["field"] == "address")
    assert address["kind"] == "directory_claim"
    assert address["reference_urls"] == ["https://aster.example/contact"]
    assert all("aster.example" not in url for url in calls)
    country = next(c for c in c["claims"] if c["field"] == "country")
    assert country["record_id"] == "Q300"
    assert country["via"][0]["record_id"] == "Q100"
    assert country["via"][1]["record_id"] == "Q200"
    assert "registration_id" not in c["fields"]
    assert "postal_code" not in c["fields"]  # No heuristic extraction from prose.


@pytest.mark.parametrize(
    "change", ["multiple_countries", "historical_headquarters", "dissolved_country"]
)
def test_ambiguous_or_historical_geography_is_not_asserted(
    tmp_path, monkeypatch, change
):
    entities = wikidata_records()
    if change == "multiple_countries":
        entities["Q200"]["claims"]["P17"][0]["rank"] = "normal"
    elif change == "historical_headquarters":
        entities["Q100"]["claims"]["P159"][0]["qualifiers"]["P582"] = [
            snak({"time": "+1991-01-01T00:00:00Z"})
        ]
    else:
        entities["Q300"]["claims"]["P576"] = [
            statement({"time": "+1991-01-01T00:00:00Z"})
        ]
    install_provider(monkeypatch, entities=entities)
    report = research.research_subject("Aster Research", tmp_path / "provider")
    assert "country" not in report["candidates"][0]["fields"]


def test_successful_directory_survives_gleif_outage(tmp_path, monkeypatch):
    install_provider(monkeypatch, entities=wikidata_records(), error="timeout")
    report = research.research_subject("Aster Research", tmp_path / "provider")
    assert report["status"] == "candidates"
    assert report["providers"][0] == {
        "id": "gleif",
        "label": research.LABELS["gleif"],
        "status": "unavailable",
        "error": "timeout",
    }
    assert report["providers"][1]["status"] == "available"
    assert research.load_research(tmp_path / "provider") == report


def test_no_match_and_unavailable_remain_distinct(tmp_path, monkeypatch):
    install_provider(monkeypatch)
    assert (
        research.research_subject("Missing Corporation", tmp_path / "empty")["status"]
        == "no_match"
    )
    install_provider(monkeypatch, error="network unavailable")
    assert (
        research.research_subject("Missing Corporation", tmp_path / "failed")["status"]
        == "unavailable"
    )


@pytest.mark.parametrize("name", ["李", "A", "3"])
def test_single_character_names_are_queried_and_replay(tmp_path, monkeypatch, name):
    calls = install_provider(monkeypatch)
    path = tmp_path / "provider"
    report = research.research_subject(name, path)
    assert report["query"] == name and report["status"] == "no_match"
    assert len(calls) == 2
    assert parse_qs(urlsplit(calls[0]).query)["filter[entity.legalName]"] == [name]
    assert parse_qs(urlsplit(calls[1]).query)["search"] == [name]
    assert research.load_research(path) == report
    with pytest.raises(ValueError, match="between 2 and 300"):
        research._query(name, schema_version=1)


def test_generic_corporate_name_fallback_is_bounded(tmp_path, monkeypatch):
    calls = install_provider(monkeypatch)
    name = "Joint Stock Company Research and Production Association Named After A. B. Aster"
    report = research.research_subject(name, tmp_path / "provider")
    terms = [
        parse_qs(urlsplit(url).query)["search"][0]
        for url in calls
        if "wbsearchentities" in url
    ]
    assert terms == [name, "Aster"]
    assert len(calls) <= research.MAX_REQUESTS
    assert report["query"] == name


def test_person_discovery_does_not_copy_contact_or_location_information(
    tmp_path, monkeypatch
):
    entities = wikidata_records()
    entities["Q100"]["claims"]["P31"] = [statement(item("Q5"))]
    calls = install_provider(monkeypatch, entities=entities)
    report = research.research_subject("Aster Research", tmp_path / "provider")
    assert report["candidates"][0]["entity_type"] == "person"
    assert report["candidates"][0]["fields"] == {}
    assert not any("Q200" in url or "Q300" in url for url in calls)
    assert not any(
        c["field"] in {"address", "city", "country", "website"}
        for c in report["candidates"][0]["claims"]
    )


def rehash_report(path):
    manifest = json.loads((path / "manifest.json").read_text())
    raw = (path / "report.json").read_bytes()
    manifest["files"]["report.json"] = {"sha256": sha256_bytes(raw), "bytes": len(raw)}
    (path / "manifest.json").write_bytes(canonical_json(manifest))


def test_rehashed_field_tampering_is_rejected_by_reconstruction(tmp_path, monkeypatch):
    install_provider(monkeypatch, gleif=[gleif_record()])
    path = tmp_path / "provider"
    report = research.research_subject("Aster Research", path)
    report["candidates"][0]["fields"]["country"] = "US"
    (path / "report.json").write_bytes(canonical_json(report))
    rehash_report(path)
    with pytest.raises(ValueError, match="differs from"):
        research.load_research(path)


def test_raw_mutation_and_untracked_file_are_rejected(tmp_path, monkeypatch):
    install_provider(monkeypatch, gleif=[gleif_record()])
    path = tmp_path / "provider"
    research.research_subject("Aster Research", path)
    (path / "unexpected.json").write_text("{}")
    with pytest.raises(ValueError, match="inventory"):
        research.load_research(path)
    (path / "unexpected.json").unlink()
    (path / "raw-001.json").write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        research.load_research(path)


def test_changed_request_transcript_cannot_be_reinterpreted_as_outage(
    tmp_path, monkeypatch
):
    install_provider(monkeypatch, gleif=[gleif_record()])
    path = tmp_path / "provider"
    research.research_subject("Aster Research", path)
    manifest = json.loads((path / "manifest.json").read_text())
    manifest["requests"][0]["url"] = "https://example.com/"
    (path / "manifest.json").write_bytes(canonical_json(manifest))
    with pytest.raises(ValueError, match="does not reproduce"):
        research.load_research(path)


def test_existing_snapshot_and_symlink_cannot_be_overwritten(tmp_path, monkeypatch):
    install_provider(monkeypatch)
    path = tmp_path / "provider"
    report = research.research_subject("Aster Research", path)
    with pytest.raises(FileExistsError):
        research.research_subject("Another Company", path)
    assert research.load_research(path) == report
    link = tmp_path / "link"
    link.symlink_to(path, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic"):
        research.research_subject("Another Company", link)
    with pytest.raises(ValueError, match="unsafe"):
        research.load_research(link)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.gleif.org/api/v1/lei-records",
        "https://api.gleif.org.evil.example/api/v1/lei-records",
        "https://user:pass@api.gleif.org/api/v1/lei-records",
        "https://127.0.0.1/",
        "https://www.wikidata.org/w/api.php?action=edit&format=json",
        "https://api.gleif.org/api/v1/lei-records?filter%5Bfulltext%5D=Aster&page%5Bsize%5D=10000",
    ],
)
def test_network_allowlist_rejects_arbitrary_hosts_actions_and_bounds(url):
    with pytest.raises(ValueError):
        research._validate_url(url)


def test_redirects_are_rejected():
    with pytest.raises(ValueError, match="redirect"):
        research._NoRedirects().redirect_request(
            None, None, 302, "redirect", {}, "http://127.0.0.1"
        )


@pytest.mark.parametrize(
    "raw",
    [
        b'{"data": [], "data": []}',
        b'{"n": NaN}',
        b"[]",
        b"{}" + b" " * research.MAX_BYTES,
    ],
)
def test_invalid_provider_documents_are_bounded(raw):
    with pytest.raises(ValueError):
        research._decode(raw)


def test_malformed_json_is_retained_and_successful_other_provider_survives(
    tmp_path, monkeypatch
):
    install_provider(monkeypatch, entities=wikidata_records())
    original = research._download
    monkeypatch.setattr(
        research,
        "_download",
        lambda url: b'{"data":' if "gleif.org" in url else original(url),
    )
    path = tmp_path / "provider"
    report = research.research_subject("Aster Research", path)
    assert report["status"] == "candidates"
    assert report["providers"][0]["status"] == "unavailable"
    assert (path / "raw-001.json").read_bytes() == b'{"data":'
    assert research.load_research(path) == report


def test_malformed_directory_statement_does_not_erase_gleif_result(
    tmp_path, monkeypatch
):
    entities = wikidata_records()
    entities["Q100"]["claims"]["P159"][0]["qualifiers"] = "invalid"
    install_provider(monkeypatch, gleif=[gleif_record()], entities=entities)
    report = research.research_subject("Aster Research", tmp_path / "provider")
    assert report["status"] == "candidates"
    assert report["providers"][1]["status"] == "unavailable"
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["fields"]["lei"] == "12345678901234567890"


def test_future_headquarters_in_same_year_are_not_used():
    entity = {
        "claims": {
            "P159": [
                statement(
                    item("Q200"),
                    qualifiers={"P580": [snak({"time": "+2026-12-01T00:00:00Z"})]},
                )
            ]
        }
    }
    assert research._current(entity, "P159", "2026-10-15T12:00:00Z") == []


def test_gleif_search_is_name_specific_and_punctuation_is_not_filter_syntax(
    tmp_path, monkeypatch
):
    calls = install_provider(monkeypatch)
    report = research.research_subject("Aster, Inc.", tmp_path / "provider")
    assert report["query"] == "Aster, Inc."
    queries = [parse_qs(urlsplit(url).query) for url in calls if "gleif.org" in url]
    assert queries[0]["filter[entity.legalName]"] == ["Aster Inc"]
    assert all("filter[fulltext]" not in query for query in queries)
    assert research.load_research(tmp_path / "provider") == report


def test_legacy_fulltext_reports_still_replay_under_original_parser(
    tmp_path, monkeypatch
):
    entities = wikidata_records()
    del entities["Q200"]["claims"]["P31"]
    calls = install_provider(monkeypatch, entities=entities)
    monkeypatch.setattr(research, "SCHEMA_VERSION", 1)
    path = tmp_path / "legacy"
    report = research.research_subject("Aster Research", path)
    assert report["schema_version"] == 1
    assert report["candidates"][0]["fields"]["city"] == "Oxford"
    assert "filter[fulltext]" in parse_qs(urlsplit(calls[0]).query)
    monkeypatch.setattr(research, "SCHEMA_VERSION", 2)
    assert research.load_research(path) == report


@pytest.mark.parametrize(
    "placeholder", ["N/A", "NOT APPLICABLE", "Not Available", "UNKNOWN", "---", "___"]
)
def test_gleif_placeholder_is_not_a_registration_identifier(placeholder):
    record = gleif_record()
    record["attributes"]["entity"]["registeredAs"] = placeholder
    record["attributes"]["entity"]["status"] = "INACTIVE"
    candidate = research._gleif({"data": [record]})[0]
    assert "registration_id" not in candidate["fields"]
    assert "INACTIVE" in candidate["description"]


def test_gleif_transliterated_name_is_preserved():
    record = gleif_record()
    record["attributes"]["entity"]["transliteratedOtherNames"] = [{"name": "Астра"}]
    assert "Астра" in research._gleif({"data": [record]})[0]["aliases"]


def test_headquarters_building_is_not_asserted_as_city(tmp_path, monkeypatch):
    entities = wikidata_records()
    entities["Q200"]["labels"]["en"]["value"] = "Aster Tower"
    entities["Q200"]["claims"]["P31"] = [statement(item("Q41176"))]
    install_provider(monkeypatch, entities=entities)
    report = research.research_subject("Aster Research", tmp_path / "provider")
    candidate = report["candidates"][0]
    assert "city" not in candidate["fields"]
    assert candidate["fields"]["country"] == "GB"


def test_country_provenance_points_to_actual_country_statement(tmp_path, monkeypatch):
    entities = wikidata_records()
    entities["Q200"]["claims"]["P17"] = [
        {"mainsnak": {"snaktype": "novalue"}, "rank": "normal"},
        statement(item("Q300")),
    ]
    install_provider(monkeypatch, entities=entities)
    report = research.research_subject("Aster Research", tmp_path / "provider")
    country = next(
        c for c in report["candidates"][0]["claims"] if c["field"] == "country"
    )
    assert country["via"][1]["pointer"] == "/entities/Q200/claims/P17/1/mainsnak"


def test_future_end_date_does_not_hide_current_headquarters():
    entity = {
        "claims": {
            "P159": [
                statement(
                    item("Q200"),
                    qualifiers={"P582": [snak({"time": "+2027-01-01T00:00:00Z"})]},
                )
            ]
        }
    }
    assert len(research._current(entity, "P159", "2026-10-15T12:00:00Z")) == 1
    assert (
        research._current(entity, "P159", "2026-10-15T12:00:00Z", schema_version=1)
        == []
    )


def test_malformed_optional_identifiers_and_links_do_not_erase_successes(
    tmp_path, monkeypatch
):
    entities = wikidata_records()
    entities["Q100"]["claims"]["P31"].append(statement({"id": 42}))
    entities["Q100"]["claims"]["P856"] = [statement("https://[invalid")]
    entities["Q100"]["claims"]["P159"][0]["references"][0]["snaks"]["P854"].append(
        snak("https://[invalid")
    )
    install_provider(monkeypatch, gleif=[gleif_record()], entities=entities)
    report = research.research_subject("Aster Research", tmp_path / "provider")
    assert len(report["candidates"]) == 2
    assert research.load_research(tmp_path / "provider") == report


def test_deprecated_person_type_does_not_turn_company_into_person(
    tmp_path, monkeypatch
):
    entities = wikidata_records()
    entities["Q100"]["claims"]["P31"].append(statement(item("Q5"), rank="deprecated"))
    install_provider(monkeypatch, entities=entities)
    report = research.research_subject("Aster Research", tmp_path / "provider")
    assert report["candidates"][0]["entity_type"] == "organization"
    assert report["candidates"][0]["fields"]["country"] == "GB"


def test_one_malformed_gleif_record_keeps_valid_records_with_partial_status(
    tmp_path, monkeypatch
):
    broken = gleif_record()
    broken["attributes"]["entity"]["legalName"] = None
    install_provider(monkeypatch, gleif=[broken, gleif_record()])
    report = research.research_subject("Aster Research", tmp_path / "provider")
    assert report["status"] == "candidates"
    assert report["providers"][0]["status"] == "partial"
    assert "record 1" in report["providers"][0]["error"]
    assert len(report["candidates"]) == 1
    assert all(
        claim["pointer"].startswith("/data/1/")
        for claim in report["candidates"][0]["claims"]
    )
    assert research.load_research(tmp_path / "provider") == report


def test_interactive_wikidata_query_omits_bot_lag_parameter_but_legacy_replays():
    params = {
        "action": "wbsearchentities",
        "search": "Example",
        "language": "en",
        "limit": 5,
        "type": "item",
    }
    current = research._url(params)
    legacy = research._url(params, schema_version=1)
    assert "maxlag" not in parse_qs(urlsplit(current).query)
    assert parse_qs(urlsplit(legacy).query)["maxlag"] == ["10"]
    research._validate_url(current)
    research._validate_url(legacy)


def test_exact_primary_name_precedes_alias_and_provider_relevance_breaks_ties(
    tmp_path, monkeypatch
):
    entities = {}
    for qid, name in [
        ("Q900", "Example Person"),
        ("Q100", "Example Person"),
        ("Q10", "Other Person"),
    ]:
        entities[qid] = {
            "labels": {"en": {"value": name}},
            "aliases": {"en": [{"value": "Example Person"}]},
            "claims": {"P31": [statement(item("Q5"))]},
        }

    def download(url):
        query = parse_qs(urlsplit(url).query)
        if "gleif.org" in url:
            return canonical_json({"data": []})
        if query["action"] == ["wbsearchentities"]:
            return canonical_json(
                {"search": [{"id": qid} for qid in ("Q10", "Q900", "Q100")]}
            )
        return canonical_json(
            {"entities": {qid: entities[qid] for qid in sorted(entities)}}
        )

    monkeypatch.setattr(research, "_download", download)
    report = research.research_subject("Example Person", tmp_path / "provider")
    assert [c["claims"][0]["record_id"] for c in report["candidates"]] == [
        "Q900",
        "Q100",
        "Q10",
    ]
    assert research.load_research(tmp_path / "provider") == report


def test_punctuation_only_query_cannot_become_an_unfiltered_company_search(
    tmp_path, monkeypatch
):
    def unexpected(url):
        pytest.fail("Invalid names must be rejected before network access")

    monkeypatch.setattr(research, "_download", unexpected)
    with pytest.raises(ValueError, match="name"):
        research.research_subject("---", tmp_path / "provider")
    assert not (tmp_path / "provider").exists()

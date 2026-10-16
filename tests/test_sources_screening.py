from datetime import date
from decimal import Decimal

import pytest

from omphalos.investigations import analyze
from omphalos.screening import candidate_findings, name_score
from omphalos.sources import _checked_url, _parse_ofac, import_source, load_source
from omphalos.util import read_json, sha256_file, write_json


def csl_payload():
    return {
        "total": 3,
        "offset": 0,
        "search_performed_at": "2026-10-13T12:00:00Z",
        "sources_used": [],
        "results": [
            {
                "id": "one",
                "source": "Denied Persons List (DPL)",
                "name": "Synthetic Harbor Instruments",
                "start_date": " 8/11/2015",
                "end_date": "2020-01-01",
                "addresses": [{"country": "US"}],
            },
            {
                "id": "two",
                "source": "Entity List (EL)",
                "name": "Synthetic Harbor Instruments",
                "alt_names": ["Harbor Synthetic Instruments"],
                "start_date": "2020-01-01",
                "addresses": [{"country": "US"}],
            },
            {
                "id": "three",
                "source": "Entity List (EL)",
                "name": "Synthetic Harbor Instruments",
                "start_date": "2030-01-01",
                "addresses": [{"country": "US"}],
            },
        ],
    }


def import_csl(tmp_path, payload=None):
    raw = tmp_path / "csl.json"
    write_json(raw, payload or csl_payload())
    import_source("csl", raw, tmp_path / "snapshot")
    return load_source(tmp_path / "snapshot")


def test_csl_dates_originals_and_identity_candidates(tmp_path):
    snapshot = import_csl(tmp_path)
    findings, counts = candidate_findings(
        [
            {
                "entity_id": "E1",
                "name": "Synthetic Harbor Instruments",
                "country": "US",
            },
            {
                "entity_id": "E2",
                "name": "Synthetic Harbor Instruments",
                "country": "GB",
            },
        ],
        snapshot,
        date(2026, 10, 13),
    )
    assert counts["source_records_excluded_by_dates"] == 2
    assert len(findings) == 2
    assert findings[0]["entity_ids"] != findings[1]["entity_ids"]
    assert {f["metrics"]["country_context"] for f in findings} == {
        "corroborates",
        "differs",
    }
    assert all(f["metrics"]["name_similarity"] == "1.0000" for f in findings)
    assert all(f["source_refs"][0]["snapshot_id"] == "snapshot" for f in findings)
    assert b"Denied Persons List" in (tmp_path / "snapshot" / "raw.json").read_bytes()


def test_unicode_and_token_order_similarity_not_probability():
    assert name_score("Société Ágora", "Societe Agora") == 1
    assert name_score("Acme Maritime Ltd", "Maritime Acme Ltd") == 1
    assert name_score("", "Acme") == 0
    assert name_score("Alpha", "Completely Different") < Decimal("0.90")
    assert name_score("华为技术", "华为技术") == 1


def test_snapshot_display_limit_omissions_explicit(tmp_path):
    payload = csl_payload()
    for row in payload["results"]:
        row.pop("start_date", None)
        row.pop("end_date", None)
    snapshot = import_csl(tmp_path, payload)
    findings, counts = candidate_findings(
        [{"entity_id": "E1", "name": "Synthetic Harbor Instruments"}],
        snapshot,
        date(2026, 10, 13),
        max_candidates=1,
    )
    assert len(findings) == 1 and counts["candidates_omitted_by_display_limit"] == 2


def test_partial_list_rejected(tmp_path):
    payload = csl_payload()
    payload["total"] = 4
    raw = tmp_path / "source.json"
    write_json(raw, payload)
    with pytest.raises(ValueError, match="paginated"):
        import_source("csl", raw, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_duplicate_source_ids_rejected(tmp_path):
    payload = csl_payload()
    payload["results"][2] = payload["results"][1]
    raw = tmp_path / "source.json"
    write_json(raw, payload)
    with pytest.raises(ValueError, match="Duplicate"):
        import_source("csl", raw, tmp_path / "bad")


OFAC = b"""<?xml version="1.0"?><sdnList xmlns="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"><publshInformation><Publish_Date>10/13/2026</Publish_Date><Record_Count>1</Record_Count></publshInformation><sdnEntry><uid>123</uid><firstName>EXAMPLE</firstName><lastName>PERSON</lastName><sdnType>Individual</sdnType><programList><program>TEST-FIXTURE</program></programList><akaList><aka><uid>456</uid><type>a.k.a.</type><category>weak</category><lastName>Example Alias</lastName></aka></akaList><addressList><address><uid>789</uid><address1>Example Street</address1><country>United States</country></address></addressList><idList><id><uid>1000</uid><idType>Legal Entity Identifier</idType><idNumber>12345678901234567890</idNumber></id></idList></sdnEntry></sdnList>"""


def test_ofac_nested_uids_alias_strength_and_dates(tmp_path):
    raw = tmp_path / "ofac.xml"
    raw.write_bytes(OFAC)
    import_source("ofac_sdn", raw, tmp_path / "ofac")
    snapshot = load_source(tmp_path / "ofac")
    entry = snapshot["entries"][0]
    assert entry["record_id"] == "123" and entry["name"] == "EXAMPLE PERSON"
    assert entry["alias_details"][0]["quality"] == "weak"
    assert entry["start_date"] is None and entry["end_date"] is None
    assert snapshot["metadata"]["source_updated_at"] == "2026-10-13"
    # The source full country name does not become a fabricated ISO-code disagreement.
    findings, _ = candidate_findings(
        [{"entity_id": "E1", "name": "Example Alias", "country": "US"}],
        snapshot,
        date(2026, 10, 13),
    )
    assert findings[0]["metrics"]["alias_quality"] == ["weak"]
    assert findings[0]["metrics"]["country_context"] == "unknown"


def test_typed_identifier_match_survives_different_name(tmp_path):
    raw = tmp_path / "ofac.xml"
    raw.write_bytes(OFAC)
    import_source("ofac_sdn", raw, tmp_path / "ofac")
    snapshot = load_source(tmp_path / "ofac")
    findings, _ = candidate_findings(
        [
            {
                "entity_id": "E1",
                "name": "Different Company",
                "lei": "12345678901234567890",
            }
        ],
        snapshot,
        date(2026, 10, 13),
    )
    assert (
        len(findings) == 1
        and findings[0]["metrics"]["identifier_matches"][0]["field"] == "lei"
    )
    snapshot["entries"][0]["identifiers"][0]["idType"] = "Passport"
    findings, _ = candidate_findings(
        [
            {
                "entity_id": "E1",
                "name": "Different Company",
                "registration_id": "12345678901234567890",
            }
        ],
        snapshot,
        date(2026, 10, 13),
    )
    assert findings == []


@pytest.mark.parametrize(
    "raw",
    [
        b'<!DOCTYPE foo [<!ENTITY x "boom">]><sdnList/>',
        '<!DOCTYPE foo [<!ENTITY x "boom">]><sdnList/>'.encode("utf-16"),
        b"<other/>",
    ],
)
def test_xml_unsafe_or_wrong_schema_rejected(raw):
    with pytest.raises((ValueError, UnicodeError)):
        _parse_ofac("ofac_sdn", raw)


@pytest.mark.parametrize(
    "url",
    [
        "http://data.trade.gov/list",
        "https://evil.example/list",
        "https://data.trade.gov.evil.example/list",
        "https://user:pass@data.trade.gov/list",
        "https://data.trade.gov:444/list",
        "file:///etc/passwd",
        "https://127.0.0.1/",
    ],
)
def test_source_url_allowlist(url):
    with pytest.raises(ValueError):
        _checked_url(url)


def test_rehashed_source_is_still_bound_to_raw(tmp_path):
    import_csl(tmp_path)
    path = tmp_path / "snapshot"
    snapshot = read_json(path / "source.json")
    snapshot["entries"][0]["name"] = "Fabricated"
    write_json(path / "source.json", snapshot)
    manifest = read_json(path / "source-manifest.json")
    manifest["normalized_sha256"] = sha256_file(path / "source.json")
    write_json(path / "source-manifest.json", manifest)
    with pytest.raises(ValueError, match="differ from original"):
        load_source(path)


def test_stale_source_reported_and_snapshot_id_required(tmp_path):
    snapshot = import_csl(tmp_path)
    data = {
        "metadata": {"dataset_id": "data"},
        "tables": {"entities": [{"entity_id": "E1", "name": "Example"}]},
    }
    case = {
        "case_id": "case1",
        "dataset_id": "data",
        "question": "Which entity records require further identity review?",
        "as_of": "2027-01-01",
        "investigations": ["screening_candidates"],
        "watchlist_snapshot_id": "snapshot",
    }
    result = analyze(data, case, snapshot)
    assert any(
        "precedes case as-of" in text for text in result["coverage"][0]["limitations"]
    )
    case["watchlist_snapshot_id"] = "different"
    with pytest.raises(ValueError, match="snapshot ID"):
        analyze(data, case, snapshot)


def test_upper_bound_has_no_false_negatives_for_name_scores():
    from itertools import product

    from omphalos.screening import _can_reach, _prepare_name

    names = [
        "A B C",
        "C B A",
        "Société Agora",
        "Societe Agora",
        "AAABBB",
        "BBBBBA",
        "华为 技术",
        "技术 华为",
        "Acme-Ltd",
        "Acme Ltd",
        "ABCDEF",
        "ABXDEF",
    ]
    for left, right in product(names, names):
        actual = name_score(left, right)
        for threshold in (
            Decimal("0.50"),
            Decimal("0.70"),
            Decimal("0.90"),
            Decimal("1"),
        ):
            numerator, denominator = threshold.as_integer_ratio()
            if actual >= threshold:
                assert _can_reach(
                    _prepare_name(left), _prepare_name(right), numerator, denominator
                )


def test_ofac_published_bucket_only():
    host = "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com"
    assert _checked_url(f"https://{host}/Published/example/SDN.XML")
    with pytest.raises(ValueError):
        _checked_url(f"https://{host}/private/SDN.XML")


def test_cyrillic_preserved_and_cross_script_identity_not_inferred():
    assert name_score("Торговая Компания", "Компания Торговая") == 1
    assert name_score("Москва", "Moskva") != 1
    assert name_score("A", "А") == 0  # Latin A and Cyrillic A are not collapsed.


def test_identifier_and_entity_type_disagreements_are_visible(tmp_path):
    raw = tmp_path / "ofac.xml"
    raw.write_bytes(OFAC)
    import_source("ofac_sdn", raw, tmp_path / "ofac")
    snapshot = load_source(tmp_path / "ofac")
    findings, _ = candidate_findings(
        [
            {
                "entity_id": "E1",
                "name": "EXAMPLE PERSON",
                "entity_type": "organization",
                "lei": "99999999999999999999",
            }
        ],
        snapshot,
        date(2026, 10, 13),
    )
    assert findings[0]["metrics"]["entity_type_context"] == "differs"
    assert (
        findings[0]["metrics"]["identifier_comparisons"][0]["comparison"] == "different"
    )
    assert findings[0]["metrics"]["identifier_matches"] == []


@pytest.mark.parametrize(
    "failure", ["timeout", "oversize", "invalid_payload", "blocked_redirect"]
)
def test_failed_fetch_never_creates_partial_snapshot(tmp_path, monkeypatch, failure):
    import urllib.request

    from omphalos.sources import MAX_BYTES, fetch_source

    class Response:
        url = (
            "https://evil.example/list"
            if failure == "blocked_redirect"
            else "https://data.trade.gov/list"
        )
        headers = (
            {"Content-Length": str(MAX_BYTES + 1)} if failure == "oversize" else {}
        )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, amount):
            return b'{"not":"a snapshot"}'

    class Opener:
        def open(self, request, timeout):
            if failure == "timeout":
                raise TimeoutError("source did not respond")
            return Response()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises((ValueError, TimeoutError)):
        fetch_source("csl", tmp_path / "snapshot")
    assert not (tmp_path / "snapshot").exists()
    assert not list(tmp_path.glob(".source-*"))

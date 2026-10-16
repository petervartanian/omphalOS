"""Bounded public identity discovery, retained separately from screening lists.

These are candidate identities, never an automatic decision about the subject.
Wikidata statements remain directory claims even when they cite a primary site.
"""

from __future__ import annotations

import json
import re
import shutil
import ssl
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from .util import canonical_json, safe_child, sha256_bytes, utc_now

SCHEMA_VERSION = 2
MAX_BYTES = 2 * 1024 * 1024
MAX_REQUESTS = 8
MAX_CANDIDATES = 5
TIMEOUT_SECONDS = 8
WIKIDATA_MAXLAG = 10
GLEIF = "https://api.gleif.org/api/v1/lei-records"
WIKIDATA = "https://www.wikidata.org/w/api.php"
LABELS = {
    "gleif": "GLEIF legal entity records",
    "wikidata": "Wikidata public directory",
}
FIELD_NAMES = {"country", "address", "city", "postal_code", "registration_id", "lei"}
QID = re.compile(r"Q[1-9][0-9]{0,11}\Z")


class _EvidenceError(ValueError):
    """A broken retained transcript must never become a provider outage."""


def _text(value: object, limit: int = 2000) -> str:
    if not isinstance(value, str) or len(value) > limit:
        return ""
    return value.strip()


def _decode(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Provider JSON contains duplicate keys")
            result[key] = value
        return result

    def invalid(_value):
        raise ValueError("Provider JSON contains a non-finite number")

    if len(raw) > MAX_BYTES:
        raise ValueError("Identity response exceeds the supported size")
    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Identity provider returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Identity response must be a JSON object")
    # This also rejects overflowed JSON floating-point values.
    canonical_json(value)
    return value


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.fragment
        or len(url) > 4000
    ):
        raise ValueError("Unsupported identity provider URL")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if parsed.netloc == "api.gleif.org" and parsed.path == "/api/v1/lei-records":
        if set(query) not in (
            {"filter[fulltext]", "page[size]"},  # Retained version 1 evidence.
            {"filter[entity.legalName]", "page[size]"},
        ):
            raise ValueError("Unsupported GLEIF request")
        if query["page[size]"] != [str(MAX_CANDIDATES)]:
            raise ValueError("Unbounded GLEIF request")
    elif parsed.netloc == "www.wikidata.org" and parsed.path == "/w/api.php":
        action = query.get("action")
        common = {"action", "format"} | ({"maxlag"} if "maxlag" in query else set())
        if action == ["wbsearchentities"]:
            allowed = common | {"search", "language", "limit", "type"}
            if (
                query.get("limit") != [str(MAX_CANDIDATES)]
                or query.get("language") != ["en"]
                or query.get("type") != ["item"]
            ):
                raise ValueError("Unbounded Wikidata search request")
        elif action == ["wbgetentities"]:
            allowed = common | {"ids", "props", "languages"}
            ids = query.get("ids", [""])[0].split("|")
            if len(ids) > MAX_CANDIDATES * 2 or not all(QID.fullmatch(i) for i in ids):
                raise ValueError("Unbounded Wikidata entity request")
            if query.get("props") != [
                "labels|descriptions|aliases|claims"
            ] or query.get("languages") != ["en|ru"]:
                raise ValueError("Unsupported Wikidata fields")
        else:
            raise ValueError("Unsupported Wikidata action")
        if (
            set(query) != allowed
            or query.get("format") != ["json"]
            or ("maxlag" in query and query["maxlag"] != [str(WIKIDATA_MAXLAG)])
        ):
            raise ValueError("Unsupported Wikidata request")
    else:
        raise ValueError("Identity URL is outside the public provider allowlist")
    if any(len(values) != 1 for values in query.values()):
        raise ValueError("Duplicate identity request parameter")


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Identity providers may not redirect requests")


def _download(url: str) -> bytes:
    """No caller-controlled hosts, credentials, redirects, or TLS exceptions."""
    _validate_url(url)
    import truststore

    opener = urllib.request.build_opener(
        _NoRedirects(),
        urllib.request.HTTPSHandler(
            context=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ),
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "omphalOS/2.0 (public legal-entity identity discovery)",
            "Accept": "application/json",
        },
    )
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("Unexpected identity provider response")
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_BYTES:
            raise ValueError("Identity response exceeds the supported size")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Identity response exceeds the supported size")
    return raw


def _terms(name: str) -> list[str]:
    # A second discovery query can remove formal wording; it does not change identity.
    normalized = re.sub(
        r"\b(?:joint[ -]stock company|limited liability company|public limited company|"
        r"research and production association|scientific production association|"
        r"named after|incorporated|corporation|company|limited|llc|plc|ltd|inc|jsc|npo)\b",
        " ",
        name,
        flags=re.I,
    )
    normalized = re.sub(r"\b[A-Za-z]\b[.]?", " ", normalized)
    normalized = re.sub(r"[\s.,\"'“”«»]+", " ", normalized).strip()
    return [name] + (
        [normalized] if len(normalized) >= 3 and normalized != name else []
    )


def _claim(field, value, provider, record_id, pointer, references=None):
    source = (
        f"{GLEIF}/{record_id}"
        if provider == "gleif"
        else f"https://www.wikidata.org/wiki/{record_id}"
    )
    result = {
        "field": field,
        "value": value,
        "source_url": source,
        "source_label": LABELS[provider],
        "kind": "gleif_reference" if provider == "gleif" else "directory_claim",
        "record_id": record_id,
        "pointer": pointer,
    }
    if references:
        result["reference_urls"] = sorted(set(references))
    return result


def _candidate(provider, record_id, name, description="", aliases=None):
    return {
        "candidate_id": sha256_bytes(f"{provider}:{record_id}".encode())[:32],
        "name": name,
        "description": description,
        "aliases": sorted(set(aliases or [])),
        "entity_type": "organization",
        "fields": {},
        "claims": [],
        "source_urls": [],
    }


def _put(candidate, field, value, provider, record_id, pointer, references=None):
    if not value:
        return
    candidate["claims"].append(
        _claim(field, value, provider, record_id, pointer, references)
    )
    if field in FIELD_NAMES:
        candidate["fields"][field] = value


def _gleif(
    payload: dict, *, schema_version=SCHEMA_VERSION, warnings=None, _one_row=False
) -> list[dict]:
    rows = payload.get("data")
    if not isinstance(rows, list) or len(rows) > MAX_CANDIDATES:
        raise ValueError("GLEIF response has an invalid records array")
    if schema_version >= 2 and not _one_row:
        result = []
        for index, row in enumerate(rows):
            try:
                parsed = _gleif(
                    {"data": [row]}, schema_version=schema_version, _one_row=True
                )
                if not parsed:
                    raise ValueError("Missing legal name or valid LEI")
            except (ValueError, TypeError, AttributeError, KeyError, IndexError) as exc:
                if warnings is not None:
                    warnings.append(
                        f"GLEIF record {index + 1} could not be used: {exc}"[:240]
                    )
                continue
            for candidate in parsed:
                for claim in candidate["claims"]:
                    claim["pointer"] = claim["pointer"].replace(
                        "/data/0/", f"/data/{index}/", 1
                    )
            result.extend(parsed)
        return result
    result = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("Invalid GLEIF record")
        attrs = row.get("attributes", {})
        entity = attrs.get("entity", {}) if isinstance(attrs, dict) else {}
        lei = _text(row.get("id"), 20)
        if not re.fullmatch(r"[A-Z0-9]{20}", lei) or not isinstance(entity, dict):
            continue
        name = _text(entity.get("legalName", {}).get("name"))
        if not name:
            continue
        alias_rows = entity.get("otherNames") or []
        if schema_version >= 2:
            alias_rows = [*alias_rows, *(entity.get("transliteratedOtherNames") or [])]
        aliases = [
            _text(n.get("name"))
            for n in alias_rows[: (100 if schema_version >= 2 else 50)]
            if isinstance(n, dict) and _text(n.get("name"))
        ]
        registration = attrs.get("registration") or {}
        status = _text(registration.get("status"), 40)
        description = f"GLEIF legal entity record; LEI registration status: {status or 'not supplied'}."
        if schema_version >= 2:
            entity_status = _text(entity.get("status"), 40)
            if entity_status:
                description += f" Entity status: {entity_status}."
        c = _candidate("gleif", lei, name, description, aliases)
        prefix = f"/data/{index}/attributes"
        _put(c, "name", name, "gleif", lei, prefix + "/entity/legalName/name")
        _put(c, "lei", lei, "gleif", lei, f"/data/{index}/id")
        registration_id = _text(entity.get("registeredAs"))
        normalized_registration = "".join(
            c for c in registration_id.upper() if c.isalnum()
        )
        if schema_version >= 2 and normalized_registration in {
            "",
            "NA",
            "NOTAPPLICABLE",
            "NOTAVAILABLE",
            "UNKNOWN",
            "NONE",
            "NIL",
        }:
            registration_id = ""
        _put(
            c,
            "registration_id",
            registration_id,
            "gleif",
            lei,
            prefix + "/entity/registeredAs",
        )
        address = entity.get("legalAddress") or {}
        if not isinstance(address, dict):
            raise ValueError("Invalid GLEIF legal address")
        country = _text(address.get("country"), 2)
        if re.fullmatch(r"[A-Z]{2}", country):
            _put(
                c,
                "country",
                country,
                "gleif",
                lei,
                prefix + "/entity/legalAddress/country",
            )
        for field, key in (("city", "city"), ("postal_code", "postalCode")):
            _put(
                c,
                field,
                _text(address.get(key)),
                "gleif",
                lei,
                prefix + f"/entity/legalAddress/{key}",
            )
        lines = address.get("addressLines") or []
        if not isinstance(lines, list) or len(lines) > 10:
            raise ValueError("Invalid GLEIF address lines")
        parts = [_text(line) for line in lines] + [
            _text(address.get(key))
            for key in ("city", "region", "postalCode", "country")
        ]
        _put(
            c,
            "address",
            ", ".join(p for p in parts if p),
            "gleif",
            lei,
            prefix + "/entity/legalAddress",
        )
        result.append(c)
    return result


def _value(snak):
    if not isinstance(snak, dict) or snak.get("snaktype") != "value":
        return None
    data = snak.get("datavalue")
    return data.get("value") if isinstance(data, dict) else None


def _current(entity, prop, researched_at, *, schema_version=SCHEMA_VERSION):
    rows = entity.get("claims", {}).get(prop, [])
    if not isinstance(rows, list) or len(rows) > 500:
        return []
    result = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("rank") == "deprecated":
            continue
        qualifiers = row.get("qualifiers") or {}
        ends = qualifiers.get("P582") or []
        if ends and (
            schema_version == 1
            or not all(_future_date(_value(s), researched_at) for s in ends)
        ):
            continue
        starts = [_value(s) for s in qualifiers.get("P580", [])]
        if any(_future_date(v, researched_at) for v in starts):
            continue
        result.append((i, row))
    preferred = [(i, r) for i, r in result if r.get("rank") == "preferred"]
    return preferred or result


def _future_date(value, researched_at):
    if not isinstance(value, dict):
        return False
    date = _text(value.get("time")).lstrip("+")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return False
    year, month, day = date.split("-")
    return (
        f"{year}-{month if month != '00' else '01'}-{day if day != '00' else '01'}"
        > researched_at[:10]
    )


def _qid(snak):
    value = _value(snak)
    qid = value.get("id", "") if isinstance(value, dict) else ""
    return qid if isinstance(qid, str) and QID.fullmatch(qid) else ""


def _label(entity):
    labels = entity.get("labels") or {}
    if not isinstance(labels, dict):
        return ""
    if _text(labels.get("en", {}).get("value")):
        return _text(labels["en"]["value"])
    return next(
        (
            _text(v.get("value"))
            for v in labels.values()
            if isinstance(v, dict) and _text(v.get("value"))
        ),
        "",
    )


def _web_url(url):
    try:
        parsed = urlsplit(url)
        return bool(
            parsed.scheme in ("http", "https")
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not any(ord(c) < 32 for c in url)
        )
    except ValueError:
        return False


def _reference_urls(row):
    result = []
    for ref in (row.get("references") or [])[:30]:
        if not isinstance(ref, dict) or not isinstance(ref.get("snaks"), dict):
            continue
        urls = ref["snaks"].get("P854", [])
        if not isinstance(urls, list):
            continue
        for snak in urls[:10]:
            url = _text(_value(snak))
            if _web_url(url):
                result.append(url)
    return result


def _organization(entity, researched_at=None):
    rows = (
        [row for _, row in _current(entity, "P31", researched_at)]
        if researched_at
        else entity.get("claims", {}).get("P31", [])
    )
    kinds = {_qid(row.get("mainsnak")) for row in rows if isinstance(row, dict)}
    if "Q5" in kinds:
        return False
    if kinds & {"Q4830453", "Q6881511", "Q783794", "Q43229", "Q891723", "Q167037"}:
        return True
    desc = _text(entity.get("descriptions", {}).get("en", {}).get("value"))
    return bool(
        re.search(
            r"\b(company|corporation|enterprise|business|bank|organization|organisation|studio|bureau|manufacturer|agency|institute|university)\b",
            desc,
            re.I,
        )
    )


def _person(entity, researched_at=None):
    rows = (
        [row for _, row in _current(entity, "P31", researched_at)]
        if researched_at
        else entity.get("claims", {}).get("P31", [])
    )
    return any(
        isinstance(row, dict) and _qid(row.get("mainsnak")) == "Q5" for row in rows
    )


def _city(entity, researched_at):
    # Headquarters can be a building, campus, region, or country. Its label must
    # not be promoted to a city unless the directory actually calls it a settlement.
    settlement_kinds = {
        "Q515",
        "Q3957",
        "Q532",
        "Q486972",
        "Q1549591",
        "Q5119",
        "Q15284",
    }
    return any(
        _qid(row.get("mainsnak")) in settlement_kinds
        for _, row in _current(entity, "P31", researched_at)
    )


def _wikidata(
    subjects, places, countries, researched_at, *, schema_version=SCHEMA_VERSION
):
    type_time = researched_at if schema_version >= 2 else None

    def current(entity, prop):
        return _current(entity, prop, researched_at, schema_version=schema_version)

    result = []
    for qid, entity in subjects.items():
        name = _label(entity)
        if not name or not (
            _organization(entity, type_time) or _person(entity, type_time)
        ):
            continue
        aliases = [
            _text(a.get("value"))
            for rows in (entity.get("aliases") or {}).values()
            for a in rows[:30]
            if isinstance(a, dict) and _text(a.get("value"))
        ][:100]
        desc = _text(entity.get("descriptions", {}).get("en", {}).get("value"))
        c = _candidate("wikidata", qid, name, desc, aliases)
        _put(c, "name", name, "wikidata", qid, f"/entities/{qid}/labels")
        if _person(entity, type_time):
            # Public directory discovery only; no personal contact or location
            # information is copied into a screening record.
            c["entity_type"] = "person"
            result.append(c)
            continue
        addresses = []
        locations = []
        for i, row in current(entity, "P159"):
            place_id = _qid(row.get("mainsnak"))
            if place_id:
                locations.append((place_id, i, row))
            values = row.get("qualifiers", {}).get("P6375", [])
            text_values = [(j, _value(v)) for j, v in enumerate(values)]
            text_values = [
                (j, v)
                for j, v in text_values
                if isinstance(v, dict) and _text(v.get("text"))
            ]
            english = [(j, v) for j, v in text_values if v.get("language") == "en"]
            for j, value in english or text_values[:1]:
                addresses.append(
                    (
                        _text(value["text"]),
                        f"/entities/{qid}/claims/P159/{i}/qualifiers/P6375/{j}/datavalue/value/text",
                        row,
                    )
                )
        if len({a[0] for a in addresses}) == 1:
            value, pointer, row = addresses[0]
            _put(c, "address", value, "wikidata", qid, pointer, _reference_urls(row))
        # A current headquarters location can provide present geography. The
        # organization's own P17 may describe a predecessor state and is ignored.
        if len({p[0] for p in locations}) == 1 and locations:
            place_id, i, hq_row = locations[0]
            place = places.get(place_id, {})
            city = (
                _label(place)
                if schema_version == 1 or _city(place, researched_at)
                else ""
            )
            _put(
                c,
                "city",
                city,
                "wikidata",
                place_id,
                f"/entities/{place_id}/labels",
                _reference_urls(hq_row),
            )
            if city and schema_version >= 2:
                c["claims"][-1]["via"] = [
                    {
                        "record_id": qid,
                        "pointer": f"/entities/{qid}/claims/P159/{i}/mainsnak",
                    }
                ]
            country_rows = current(place, "P17")
            country_ids = {_qid(r.get("mainsnak")) for _, r in country_rows} - {""}
            if len(country_ids) == 1:
                country_id = next(iter(country_ids))
                country = countries.get(country_id, {})
                codes = [
                    (j, _text(_value(r.get("mainsnak")), 2))
                    for j, r in current(country, "P297")
                ]
                codes = [(j, v) for j, v in codes if re.fullmatch(r"[A-Z]{2}", v)]
                if len({v for _, v in codes}) == 1 and not country.get(
                    "claims", {}
                ).get("P576"):
                    j, code = codes[0]
                    _put(
                        c,
                        "country",
                        code,
                        "wikidata",
                        country_id,
                        f"/entities/{country_id}/claims/P297/{j}/mainsnak/datavalue/value",
                    )
                    country_index = (
                        next(
                            j
                            for j, r in country_rows
                            if _qid(r.get("mainsnak")) == country_id
                        )
                        if schema_version >= 2
                        else country_rows[0][0]
                    )
                    c["claims"][-1]["via"] = [
                        {
                            "record_id": qid,
                            "pointer": f"/entities/{qid}/claims/P159/{i}/mainsnak",
                        },
                        {
                            "record_id": place_id,
                            "pointer": f"/entities/{place_id}/claims/P17/{country_index}/mainsnak",
                        },
                    ]
        for i, row in current(entity, "P856"):
            url = _text(_value(row.get("mainsnak")))
            if _web_url(url):
                _put(
                    c,
                    "website",
                    url,
                    "wikidata",
                    qid,
                    f"/entities/{qid}/claims/P856/{i}/mainsnak/datavalue/value",
                )
        result.append(c)
    return result


def _url(params, *, schema_version=SCHEMA_VERSION):
    # This endpoint serves an interactive user waiting for a few read-only
    # requests. MediaWiki permits interactive clients to omit the bot maxlag
    # parameter: https://www.mediawiki.org/wiki/Manual:Maxlag_parameter
    lag = {"maxlag": WIKIDATA_MAXLAG} if schema_version == 1 else {}
    return WIKIDATA + "?" + urlencode({**params, "format": "json", **lag})


def _entities(payload):
    entities = payload.get("entities")
    if not isinstance(entities, dict) or len(entities) > MAX_CANDIDATES * 2:
        raise ValueError("Wikidata response has an invalid entities object")
    result = {}
    for key, value in entities.items():
        if not QID.fullmatch(key) or not isinstance(value, dict) or "missing" in value:
            continue
        if any(
            not isinstance(value.get(field, {}), dict)
            for field in ("labels", "descriptions", "aliases", "claims")
        ):
            raise ValueError("Invalid Wikidata entity structure")
        for field in ("labels", "descriptions"):
            if any(
                not isinstance(entry, dict) or not isinstance(entry.get("value"), str)
                for entry in value.get(field, {}).values()
            ):
                raise ValueError("Invalid Wikidata language value")
        if any(
            not isinstance(rows, list) or len(rows) > 100
            for rows in value.get("aliases", {}).values()
        ):
            raise ValueError("Invalid Wikidata aliases")
        if any(
            not isinstance(rows, list) or len(rows) > 500
            for rows in value.get("claims", {}).values()
        ):
            raise ValueError("Invalid Wikidata statements")
        for rows in value.get("claims", {}).values():
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("mainsnak"), dict)
                    or not isinstance(row.get("qualifiers", {}), dict)
                    or not isinstance(row.get("references", []), list)
                ):
                    raise ValueError("Invalid Wikidata statement structure")
                if any(
                    not isinstance(snaks, list)
                    for snaks in row.get("qualifiers", {}).values()
                ):
                    raise ValueError("Invalid Wikidata qualifier structure")
        result[key] = value
    return result


def _run(query, researched_at, request, *, schema_version=SCHEMA_VERSION):
    errors = {p: [] for p in LABELS}
    success = {p: 0 for p in LABELS}

    def wikidata_url(params):
        return _url(params, schema_version=schema_version)

    def get(provider, url, parser):
        try:
            payload = request(provider, url)
            if isinstance(payload.get("error"), dict):
                error = payload["error"]
                raise ValueError(
                    f"Provider error {_text(error.get('code'), 60)}: {_text(error.get('info'), 180)}"
                )
            result = parser(payload)
            success[provider] += 1
            return result
        except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
            if isinstance(exc, _EvidenceError):
                raise
            errors[provider].append(
                str(exc)[:240] or "Provider response could not be used"
            )
            return None

    candidates = []
    for term in _terms(query):
        # Full-text search also matches addresses and parent records. A person's
        # name appearing on a street must not turn its tenants into identities.
        search_field = (
            "filter[entity.legalName]" if schema_version >= 2 else "filter[fulltext]"
        )
        # GLEIF treats commas as alternative filter values. Keep punctuation in
        # the recorded query, but never send it as Boolean query syntax.
        gleif_term = re.sub(r"[^\w\s]", " ", term) if schema_version >= 2 else term
        gleif_term = " ".join(gleif_term.split()) if schema_version >= 2 else gleif_term
        found = get(
            "gleif",
            GLEIF
            + "?"
            + urlencode({search_field: gleif_term, "page[size]": MAX_CANDIDATES}),
            lambda payload: _gleif(
                payload, schema_version=schema_version, warnings=errors["gleif"]
            ),
        )
        if found:
            candidates.extend(found)
            break

    def search(payload):
        rows = payload.get("search")
        if not isinstance(rows, list) or len(rows) > MAX_CANDIDATES:
            raise ValueError("Wikidata response has an invalid search array")
        return [
            r["id"]
            for r in rows
            if isinstance(r, dict) and QID.fullmatch(str(r.get("id", "")))
        ]

    ids = []
    for term in _terms(query):
        ids = (
            get(
                "wikidata",
                wikidata_url(
                    {
                        "action": "wbsearchentities",
                        "search": term,
                        "language": "en",
                        "limit": MAX_CANDIDATES,
                        "type": "item",
                    }
                ),
                search,
            )
            or []
        )
        if ids:
            break

    def fetch_entities(ids):
        if not ids:
            return {}
        requested = sorted(set(ids))[: MAX_CANDIDATES * 2]
        result = (
            get(
                "wikidata",
                wikidata_url(
                    {
                        "action": "wbgetentities",
                        "ids": "|".join(requested),
                        "props": "labels|descriptions|aliases|claims",
                        "languages": "en|ru",
                    }
                ),
                _entities,
            )
            or {}
        )
        return {qid: entity for qid, entity in result.items() if qid in requested}

    type_time = researched_at if schema_version >= 2 else None
    subjects = fetch_entities(ids)
    subject_order = ids if schema_version >= 2 else list(subjects)
    subjects = {
        qid: subjects[qid]
        for qid in subject_order
        if qid in subjects
        and (
            _organization(subjects[qid], type_time) or _person(subjects[qid], type_time)
        )
    }
    place_ids = {
        _qid(r.get("mainsnak"))
        for e in subjects.values()
        if not _person(e, type_time)
        for _, r in _current(e, "P159", researched_at, schema_version=schema_version)
    } - {""}
    places = fetch_entities(place_ids)
    country_ids = {
        _qid(r.get("mainsnak"))
        for e in places.values()
        for _, r in _current(e, "P17", researched_at, schema_version=schema_version)
    } - {""}
    countries = fetch_entities(country_ids)
    candidates.extend(
        _wikidata(
            subjects, places, countries, researched_at, schema_version=schema_version
        )
    )
    for candidate in candidates:
        candidate["source_urls"] = sorted(
            {claim["source_url"] for claim in candidate["claims"]}
        )

    def normalized(text):
        return re.sub(r"\W+", " ", text.casefold()).strip()

    def score(candidate):
        names = [candidate["name"], *candidate["aliases"]]
        return max(
            SequenceMatcher(None, normalized(query), normalized(n)).ratio()
            for n in names
        )

    if schema_version == 1:
        candidates.sort(key=lambda c: (-score(c), c["candidate_id"]))
    else:
        # A coincident alias must not outrank an exact primary legal/name match.
        # Stable sorting retains the provider's relevance order for genuine ties.
        candidates.sort(
            key=lambda c: (
                normalized(c["name"]) != normalized(query),
                -score(c),
                -SequenceMatcher(
                    None, normalized(query), normalized(c["name"])
                ).ratio(),
            )
        )
    providers = []
    for provider, label in LABELS.items():
        found = any(
            c["claims"] and c["claims"][0]["source_label"] == label for c in candidates
        )
        status = (
            "partial"
            if found and errors[provider]
            else (
                "available"
                if found
                else "unavailable" if errors[provider] else "no_match"
            )
        )
        entry = {"id": provider, "label": label, "status": status}
        if errors[provider]:
            entry["error"] = "; ".join(dict.fromkeys(errors[provider]))[:500]
        providers.append(entry)
    status = (
        "candidates"
        if candidates
        else (
            "unavailable"
            if any(p["status"] == "unavailable" for p in providers)
            else "no_match"
        )
    )
    return {
        "schema_version": schema_version,
        "query": query,
        "researched_at": researched_at,
        "status": status,
        "providers": providers,
        "candidates": candidates,
    }


def _query(name, *, schema_version=SCHEMA_VERSION):
    minimum = 1 if schema_version >= 2 else 2
    if (
        not isinstance(name, str)
        or not minimum <= len(name.strip()) <= 300
        or any(ord(c) < 32 for c in name)
        or (schema_version >= 2 and not any(c.isalnum() for c in name))
    ):
        raise ValueError(
            f"Enter a person or organization name between {minimum} and 300 characters"
        )
    return name.strip()


def research_subject(name: str, dest: Path) -> dict:
    """Write a new immutable research directory; existing evidence is never replaced."""
    query = _query(name, schema_version=SCHEMA_VERSION)
    dest = Path(dest)
    if dest.is_symlink():
        raise ValueError("Research directories cannot be symbolic links")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.mkdir(exist_ok=False)
    requests = []
    researched_at = utc_now()

    def request(provider, url):
        if len(requests) >= MAX_REQUESTS:
            raise ValueError("Public identity request limit reached")
        _validate_url(url)
        entry = {"provider": provider, "url": url}
        requests.append(entry)
        try:
            raw = _download(url)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            entry["error"] = str(exc)[:240] or "Provider unavailable"
            raise ValueError(entry["error"]) from exc
        filename = f"raw-{len(requests):03d}.json"
        with (dest / filename).open("xb") as handle:
            handle.write(raw)
        entry["file"] = filename
        return _decode(raw)

    try:
        report = _run(query, researched_at, request, schema_version=SCHEMA_VERSION)
        with (dest / "report.json").open("xb") as handle:
            handle.write(canonical_json(report))
        inventory = {
            p.name: {"sha256": sha256_bytes(p.read_bytes()), "bytes": p.stat().st_size}
            for p in sorted(dest.iterdir())
        }
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "query": query,
            "researched_at": researched_at,
            "requests": requests,
            "files": inventory,
        }
        with (dest / "manifest.json").open("xb") as handle:
            handle.write(canonical_json(manifest))
        return load_research(dest)
    except Exception:
        shutil.rmtree(dest)
        raise


def load_research(path: Path) -> dict:
    """Verify the complete inventory, then reconstruct every candidate from raw data."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Research evidence directory is missing or unsafe")
    manifest_path = safe_child(path, "manifest.json")
    if manifest_path.stat().st_size > MAX_BYTES:
        raise ValueError("Oversized research manifest")
    manifest = _decode(manifest_path.read_bytes())
    schema_version = manifest.get("schema_version")
    if type(schema_version) is not int or schema_version not in {1, 2}:
        raise ValueError("Unsupported identity research schema")
    query = _query(manifest.get("query"), schema_version=schema_version)
    researched_at = manifest.get("researched_at")
    if not isinstance(researched_at, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T[0-9:.]+Z", researched_at
    ):
        raise ValueError("Invalid research time")
    files = manifest.get("files")
    requests = manifest.get("requests")
    if (
        not isinstance(files, dict)
        or not isinstance(requests, list)
        or len(requests) > MAX_REQUESTS
        or len(files) > MAX_REQUESTS + 1
    ):
        raise ValueError("Invalid research evidence inventory")
    actual = set()
    for file in path.iterdir():
        if file.is_symlink() or not file.is_file():
            raise ValueError("Research evidence contains an unsafe artifact")
        actual.add(file.name)
    if actual != set(files) | {"manifest.json"} or "report.json" not in files:
        raise ValueError("Research evidence inventory does not match its files")
    raw_files = {r.get("file") for r in requests if isinstance(r, dict) and "file" in r}
    if set(files) != raw_files | {"report.json"}:
        raise ValueError("Research request inventory does not match its files")
    for filename, expected in files.items():
        file = safe_child(path, filename)
        if not isinstance(expected, dict) or file.stat().st_size > MAX_BYTES:
            raise ValueError("Invalid research artifact size")
        raw = file.read_bytes()
        if expected != {"bytes": len(raw), "sha256": sha256_bytes(raw)}:
            raise ValueError("Research evidence hash mismatch")
    cursor = 0

    def replay(provider, url):
        nonlocal cursor
        _validate_url(url)
        if cursor >= len(requests):
            raise _EvidenceError("Research request log is incomplete")
        entry = requests[cursor]
        cursor += 1
        if (
            not isinstance(entry, dict)
            or entry.get("provider") != provider
            or entry.get("url") != url
        ):
            raise _EvidenceError("Research request log does not reproduce its query")
        if "error" in entry:
            if set(entry) != {"provider", "url", "error"} or not isinstance(
                entry["error"], str
            ):
                raise _EvidenceError("Invalid research error record")
            raise ValueError(entry["error"])
        if (
            set(entry) != {"provider", "url", "file"}
            or entry["file"] != f"raw-{cursor:03d}.json"
        ):
            raise _EvidenceError("Invalid research response record")
        return _decode(safe_child(path, entry["file"]).read_bytes())

    reconstructed = _run(query, researched_at, replay, schema_version=schema_version)
    report = _decode(safe_child(path, "report.json").read_bytes())
    if cursor != len(requests) or canonical_json(report) != canonical_json(
        reconstructed
    ):
        raise ValueError("Research report differs from its retained provider responses")
    return report

"""Explicit official-list snapshots: bounded downloads and immutable raw evidence."""

from __future__ import annotations

import os
import shutil
import ssl
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .data import _json
from .util import (
    canonical_json,
    read_json,
    safe_child,
    safe_id,
    sha256_bytes,
    sha256_file,
    utc_now,
    write_json,
)

MAX_BYTES = 100 * 1024 * 1024
MAX_ENTRIES = 150_000
SOURCES = {
    "csl": {
        "title": "U.S. Consolidated Screening List",
        "format": "json",
        "url": "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json",
        "documentation_url": "https://www.trade.gov/consolidated-screening-list",
        "description": "Commerce, State, and Treasury listing records; preserve each list's distinct restriction and effective dates.",
    },
    "ofac_sdn": {
        "title": "OFAC Specially Designated Nationals",
        "format": "xml",
        "url": "https://sanctionslistservice.ofac.treas.gov/api/download/sdn.xml",
        "documentation_url": "https://ofac.treasury.gov/sanctions-list-service",
        "description": "OFAC SDN listing records with aliases, identifiers, addresses, and program tags.",
    },
    "ofac_non_sdn": {
        "title": "OFAC Consolidated Non-SDN Lists",
        "format": "xml",
        "url": "https://sanctionslistservice.ofac.treas.gov/api/download/consolidated.xml",
        "documentation_url": "https://ofac.treasury.gov/consolidated-sanctions-list-non-sdn-lists",
        "description": "OFAC non-SDN records; program-specific restrictions differ from SDN blocking measures.",
    },
}
OFAC_DOWNLOAD_HOST = "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com"
ALLOWED_HOSTS = {
    "data.trade.gov",
    "sanctionslistservice.ofac.treas.gov",
    OFAC_DOWNLOAD_HOST,
}


def source_catalog() -> list[dict]:
    return [
        {
            "id": key,
            "source_id": key,
            **value,
            "requires_key": False,
            "max_bytes": MAX_BYTES,
            "limitations": [
                "A candidate match is not an identity or legal determination.",
                "The snapshot may not cover unlisted ownership interests or all restrictions.",
                "Source update times and retrieval times may differ; no automatic refresh occurs.",
            ],
        }
        for key, value in SOURCES.items()
    ]


def _definition(source_id: str) -> dict:
    if source_id not in SOURCES:
        raise ValueError(f"Unsupported official source: {source_id}")
    return SOURCES[source_id]


def _strings(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str) and len(value) <= 5000:
        return [value.strip()] if value.strip() else []
    if (
        isinstance(value, list)
        and len(value) <= 1000
        and all(isinstance(v, str) and len(v) <= 5000 for v in value)
    ):
        return sorted(set(v.strip() for v in value if v.strip()))
    raise ValueError("Expected text or a list of text values in source record")


def _date(value: object) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("Source date must be a string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Unsupported source date: {value}")


def _parse_csl(raw: bytes) -> tuple[list[dict], dict]:
    payload = _json(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("CSL JSON must contain a results array")
    rows = payload["results"]
    if (
        not rows
        or len(rows) > MAX_ENTRIES
        or payload.get("total") != len(rows)
        or payload.get("offset", 0) != 0
    ):
        raise ValueError(
            "CSL snapshot is empty, oversized, paginated, or has a mismatched total"
        )
    entries = []
    for i, row in enumerate(rows):
        if (
            not isinstance(row, dict)
            or not row.get("name")
            or not row.get("id")
            or not row.get("source")
        ):
            raise ValueError(f"CSL record {i + 1} is missing name, id, or source")
        addresses = row.get("addresses") or []
        if not isinstance(addresses, list) or any(
            not isinstance(a, dict) for a in addresses
        ):
            raise ValueError(
                f"CSL record {i + 1}: addresses must be an array of objects"
            )
        if not isinstance(row["name"], str) or len(row["name"]) > 5000:
            raise ValueError(f"CSL record {i + 1}: invalid or oversized name")
        listing_key = f"{row['source']}:{row['id']}"
        entries.append(
            {
                "record_id": sha256_bytes(listing_key.encode())[:32],
                "upstream_id": str(row["id"]),
                "source_id": "csl",
                "list_name": str(row["source"]),
                "name": str(row["name"]),
                "aliases": _strings(row.get("alt_names")),
                "alias_details": [],
                "entity_type": row.get("type"),
                "programs": _strings(row.get("programs")),
                "countries": sorted(
                    {
                        a["country"]
                        for a in addresses
                        if isinstance(a.get("country"), str) and a["country"]
                    }
                ),
                "addresses": addresses,
                "identifiers": row.get("ids") or [],
                "start_date": _date(row.get("start_date")),
                "end_date": _date(row.get("end_date")),
                "source_url": row.get("source_list_url")
                or SOURCES["csl"]["documentation_url"],
                "source_row": i + 1,
                "raw_record": row,
            }
        )
    return entries, {
        "source_updated_at": payload.get("search_performed_at"),
        "sources_used": payload.get("sources_used", []),
        "date_note": "CSL search_performed_at is aggregation time; sources_used carries individual source update dates.",
    }


def _parse_ofac(source_id: str, raw: bytes) -> tuple[list[dict], dict]:
    raw.decode(
        "utf-8-sig"
    )  # Official standard XML is UTF-8; reject alternate-encoding evasions.
    if b"\x00" in raw or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("DTD and custom XML entity declarations are not accepted")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid OFAC XML: {exc}") from exc
    if root.tag.rsplit("}", 1)[-1] != "sdnList":
        raise ValueError(
            "Expected standard OFAC sdnList XML, not advanced/enhanced XML"
        )
    for elem in root.iter():
        elem.tag = elem.tag.rsplit("}", 1)[-1]
    publication = root.find("publshInformation")
    rows = root.findall("sdnEntry")
    if publication is None or not rows or len(rows) > MAX_ENTRIES:
        raise ValueError(
            "OFAC publication metadata/entries missing or too many entries"
        )
    if int(publication.findtext("Record_Count", "-1")) != len(rows):
        raise ValueError("OFAC publication record count differs from parsed entries")
    entries = []
    for i, row in enumerate(rows):
        uid = row.findtext("uid")
        name = " ".join(
            filter(None, [row.findtext("firstName"), row.findtext("lastName")])
        )
        if not uid or not name or len(name) > 5000:
            raise ValueError(f"OFAC record {i + 1} lacks UID or name")
        aliases = []
        for alias in row.findall("akaList/aka"):
            alias_name = " ".join(
                filter(None, [alias.findtext("firstName"), alias.findtext("lastName")])
            )
            if len(alias_name) > 5000 or len(aliases) >= 1000:
                raise ValueError("OFAC alias list exceeds supported bounds")
            if alias_name:
                aliases.append(
                    {
                        "name": alias_name,
                        "quality": alias.findtext("category"),
                        "type": alias.findtext("type"),
                    }
                )
        addresses = [
            {c.tag: c.text or "" for c in a} for a in row.findall("addressList/address")
        ]
        identifiers = [
            {c.tag: c.text or "" for c in ident} for ident in row.findall("idList/id")
        ]
        entries.append(
            {
                "record_id": uid,
                "upstream_id": uid,
                "source_id": source_id,
                "list_name": SOURCES[source_id]["title"],
                "name": name,
                "aliases": sorted({a["name"] for a in aliases}),
                "alias_details": aliases,
                "entity_type": row.findtext("sdnType"),
                "programs": [
                    p.text for p in row.findall("programList/program") if p.text
                ],
                "countries": sorted(
                    {a["country"] for a in addresses if a.get("country")}
                ),
                "addresses": addresses,
                "identifiers": identifiers,
                "start_date": None,
                "end_date": None,
                "source_url": SOURCES[source_id]["documentation_url"],
                "source_row": i + 1,
                "raw_record_xml": ET.tostring(row, encoding="unicode"),
            }
        )
    return entries, {
        "source_updated_at": _date(publication.findtext("Publish_Date")),
        "date_note": "OFAC snapshot membership is observed on publication date; absent individual listing dates are unknown.",
    }


def _store(
    source_id: str,
    raw: bytes,
    dest: Path,
    *,
    fetched_at: str,
    method: str,
    headers: dict | None = None,
) -> dict:
    definition = _definition(source_id)
    dest = Path(dest)
    safe_id(dest.name)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError(f"Snapshot must contain 1–{MAX_BYTES} bytes")
    if (
        dest.is_symlink()
        or dest.exists()
        and (not dest.is_dir() or any(dest.iterdir()))
    ):
        raise ValueError("Snapshot destination must not exist or be empty")
    entries, source_metadata = (
        _parse_csl(raw) if source_id == "csl" else _parse_ofac(source_id, raw)
    )
    ids = [entry["record_id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source record IDs; snapshot rejected")
    entries.sort(key=lambda e: e["record_id"])
    raw_name = f"raw.{definition['format']}"
    metadata = {
        "snapshot_id": dest.name,
        "source_id": source_id,
        "title": definition["title"],
        "fetched_at": fetched_at,
        "ingestion_method": method,
        "source_url": definition["url"],
        "sha256": sha256_bytes(raw),
        "raw_file": raw_name,
        "record_count": len(entries),
        "parser_version": "2.0",
        "http_headers": headers or {},
        **source_metadata,
        "warnings": [
            "List membership is source-specific evidence, not a legal determination."
        ],
    }
    if method == "manual_import":
        metadata["warnings"].append(
            "Manually imported content is parsed in the chosen official format; its origin was not independently authenticated."
        )
    snapshot = {
        "schema_version": "2.0",
        "source_id": source_id,
        "snapshot_id": dest.name,
        "entries": entries,
        "metadata": metadata,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".source-", dir=dest.parent))
    try:
        (stage / raw_name).write_bytes(raw)
        write_json(stage / "source.json", snapshot)
        write_json(
            stage / "source-manifest.json",
            {
                "schema_version": "2.0",
                **metadata,
                "normalized_sha256": sha256_file(stage / "source.json"),
            },
        )
        if dest.exists():
            dest.rmdir()
        os.replace(stage, dest)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return metadata


def import_source(source_id: str, path: Path, dest: Path) -> dict:
    _definition(source_id)
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Source file missing, symbolic, or oversized")
    return _store(
        source_id,
        path.read_bytes(),
        Path(dest),
        fetched_at=utc_now(),
        method="manual_import",
    )


def _checked_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError(
            "Official source download redirected outside the HTTPS allowlist"
        )
    if parsed.hostname == OFAC_DOWNLOAD_HOST and not parsed.path.startswith(
        "/Published/"
    ):
        raise ValueError("OFAC download redirect is outside its publication prefix")
    return url


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_source(source_id: str, dest: Path) -> dict:
    definition = _definition(source_id)
    try:
        import truststore

        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        context = ssl.create_default_context()
    opener = urllib.request.build_opener(
        _Redirects(), urllib.request.HTTPSHandler(context=context)
    )
    request = urllib.request.Request(
        _checked_url(definition["url"]),
        headers={
            "User-Agent": "omphalOS/2 official-public-list-snapshot",
            "Accept-Encoding": "identity",
        },
    )
    with opener.open(request, timeout=30) as response:
        _checked_url(response.url)
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_BYTES:
            raise ValueError("Official snapshot exceeds the configured size limit")
        raw = response.read(MAX_BYTES + 1)
        headers = {
            k: response.headers[k]
            for k in ("ETag", "Last-Modified", "Content-Type")
            if k in response.headers
        }
    return _store(
        source_id,
        raw,
        Path(dest),
        fetched_at=utc_now(),
        method="official_https",
        headers=headers,
    )


def load_source(path: Path) -> dict:
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Source snapshot symlinks are not accepted")
    manifest = read_json(safe_child(path, "source-manifest.json"))
    normalized = safe_child(path, "source.json")
    if sha256_file(normalized) != manifest.get("normalized_sha256"):
        raise ValueError("Normalized source snapshot checksum mismatch")
    raw_path = safe_child(path, manifest.get("raw_file", ""))
    if raw_path.stat().st_size > MAX_BYTES or sha256_file(raw_path) != manifest.get(
        "sha256"
    ):
        raise ValueError("Original source snapshot checksum mismatch")
    snapshot = read_json(normalized)
    if (
        snapshot.get("schema_version") != "2.0"
        or snapshot.get("source_id") not in SOURCES
    ):
        raise ValueError("Unknown source snapshot schema or source")
    if not snapshot.get("entries") or len(snapshot["entries"]) != snapshot[
        "metadata"
    ].get("record_count"):
        raise ValueError("Source snapshot entry count mismatch")
    metadata = snapshot.get("metadata", {})
    if any(manifest.get(k) != v for k, v in metadata.items()):
        raise ValueError("Source metadata differs from manifest")
    safe_id(snapshot["snapshot_id"])
    if snapshot["snapshot_id"] != metadata.get("snapshot_id") or snapshot[
        "source_id"
    ] != metadata.get("source_id"):
        raise ValueError("Source snapshot identity differs from metadata")
    reparsed, _ = (
        _parse_csl(raw_path.read_bytes())
        if snapshot["source_id"] == "csl"
        else _parse_ofac(snapshot["source_id"], raw_path.read_bytes())
    )
    reparsed.sort(key=lambda entry: entry["record_id"])
    if canonical_json(reparsed) != canonical_json(snapshot["entries"]):
        raise ValueError("Normalized source entries differ from original snapshot")
    return snapshot

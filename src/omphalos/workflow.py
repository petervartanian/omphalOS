"""Explicit, reproducible vendor intake and goal-based investigation planning.

No network requests, identity merges, or transaction-link inference occur here.
The strict dataset importer remains a separate, unchanged ingestion path.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import shutil
import tempfile
import unicodedata
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from .data import DatasetError, Entity, import_dataset, validate_tables
from .investigations import analyze, catalog
from .models import Case
from .screening import applicable_source_records, eligible_screening_entities
from .util import (
    canonical_json,
    safe_child,
    safe_id,
    sha256_bytes,
    sha256_file,
    write_json,
)

LOG = logging.getLogger(__name__)
VENDOR_TRANSFORM = "vendor_csv_v1"
ID_STRATEGY = "file_sha256_physical_row_v1"
MAX_VENDOR_BYTES = 20 * 1024 * 1024
MAX_VENDOR_ROWS = 50_000
MAX_VENDOR_COLUMNS = 100

# Exact header aliases, after punctuation/spacing normalization. Generic internal
# vendor/customer IDs are not mislabeled as government registration identifiers.
HEADER_ALIASES = {
    "entity_id": {"entity id", "record id"},
    "name": {
        "name",
        "entity name",
        "company",
        "company name",
        "legal name",
        "legal entity name",
        "vendor",
        "vendor name",
        "supplier",
        "supplier name",
        "customer",
        "customer name",
        "counterparty",
        "counterparty name",
        "business name",
        "organization name",
    },
    "country": {
        "country",
        "country code",
        "country name",
        "country iso",
        "country iso2",
        "iso country",
        "iso country code",
        "country of registration",
    },
    "registration_id": {
        "registration id",
        "registration number",
        "company registration number",
        "business registration number",
        "company number",
        "reg number",
        "reg no",
    },
    "lei": {"lei", "legal entity identifier", "lei code"},
    "aliases": {
        "aliases",
        "alias",
        "other names",
        "also known as",
        "aka",
        "trading names",
    },
    "entity_type": {"entity type", "organization type", "counterparty type"},
    "address": {
        "address",
        "street address",
        "address line 1",
        "address1",
        "registered address",
    },
    "city": {"city", "town", "registered city"},
    "postal_code": {"postal code", "postcode", "zip", "zip code"},
    "notes": {"notes", "comments"},
}

# Deliberately finite: ambiguous country labels (for example "Korea" or "Congo")
# are never guessed. The preview exposes every actual conversion.
COUNTRY_NAMES = {
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "u s a": "US",
    "u s": "US",
    "united kingdom": "GB",
    "great britain": "GB",
    "uk": "GB",
    "u k": "GB",
    "china": "CN",
    "people s republic of china": "CN",
    "prc": "CN",
    "hong kong": "HK",
    "taiwan": "TW",
    "macao": "MO",
    "macau": "MO",
    "germany": "DE",
    "france": "FR",
    "italy": "IT",
    "spain": "ES",
    "netherlands": "NL",
    "belgium": "BE",
    "switzerland": "CH",
    "austria": "AT",
    "poland": "PL",
    "sweden": "SE",
    "norway": "NO",
    "denmark": "DK",
    "finland": "FI",
    "ireland": "IE",
    "portugal": "PT",
    "czechia": "CZ",
    "czech republic": "CZ",
    "greece": "GR",
    "romania": "RO",
    "canada": "CA",
    "mexico": "MX",
    "brazil": "BR",
    "argentina": "AR",
    "chile": "CL",
    "colombia": "CO",
    "peru": "PE",
    "australia": "AU",
    "new zealand": "NZ",
    "japan": "JP",
    "south korea": "KR",
    "republic of korea": "KR",
    "north korea": "KP",
    "democratic people s republic of korea": "KP",
    "india": "IN",
    "singapore": "SG",
    "malaysia": "MY",
    "indonesia": "ID",
    "thailand": "TH",
    "vietnam": "VN",
    "viet nam": "VN",
    "philippines": "PH",
    "pakistan": "PK",
    "bangladesh": "BD",
    "russia": "RU",
    "russian federation": "RU",
    "ukraine": "UA",
    "belarus": "BY",
    "kazakhstan": "KZ",
    "armenia": "AM",
    "georgia": "GE",
    "azerbaijan": "AZ",
    "turkey": "TR",
    "turkiye": "TR",
    "iran": "IR",
    "islamic republic of iran": "IR",
    "iraq": "IQ",
    "israel": "IL",
    "saudi arabia": "SA",
    "united arab emirates": "AE",
    "uae": "AE",
    "qatar": "QA",
    "oman": "OM",
    "jordan": "JO",
    "lebanon": "LB",
    "syria": "SY",
    "south africa": "ZA",
    "egypt": "EG",
    "nigeria": "NG",
    "kenya": "KE",
    "morocco": "MA",
    "ghana": "GH",
    "cote d ivoire": "CI",
    "ivory coast": "CI",
}
GOALS = {
    "counterparty_screening": {
        "id": "counterparty_screening",
        "title": "Screen counterparties",
        "description": "Review name and identifier candidates against a selected official list, with missing identity context made visible.",
        "checks": ["screening_candidates", "shared_address", "data_quality"],
        "requires_source": True,
    },
    "data_readiness": {
        "id": "data_readiness",
        "title": "Understand data readiness",
        "description": "Check which identity and transaction fields are missing before choosing further investigations.",
        "checks": ["data_quality"],
        "requires_source": False,
    },
    "transaction_review": {
        "id": "transaction_review",
        "title": "Review transaction patterns",
        "description": "Examine shipments and linked payments using checks supported by the supplied records.",
        "checks": [
            "payment_fragmentation",
            "mixed_payment_methods",
            "unit_price_outlier",
            "invoice_overlap",
            "volume_spike",
            "multi_domain",
            "broker_concentration",
            "shared_address",
            "data_quality",
        ],
        "requires_source": False,
    },
}


def _key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(
        "".join(
            c if c.isalnum() else " " for c in text if not unicodedata.combining(c)
        ).split()
    )


def goal_catalog() -> list[dict]:
    return [{**goal, "checks": list(goal["checks"])} for goal in GOALS.values()]


def import_subject(name: str, dest: Path) -> dict:
    """Retain a directly entered name without asserting an external identity.

    The generated record states its origin. Its original JSON preserves the
    submitted name before outer whitespace is removed by the standard importer.
    No external source, country, entity type, or identity is inferred.
    """
    if not isinstance(name, str) or not 1 <= len(name) <= 200 or not name.strip():
        raise ValueError("Enter one company or person name, up to 200 characters.")
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        for character in name
    ):
        raise ValueError("The subject name must not contain control characters.")
    record = {
        "entity_id": f"subject_{uuid.uuid4().hex}",
        "name": name,
        "entity_type": "unknown",
        "notes": (
            "User-provided subject name entered directly in omphalOS. "
            "Identity and entity type have not been verified. "
            "This record was created from the submitted text, not from an "
            "uploaded file or an external source."
        ),
    }
    with tempfile.TemporaryDirectory(prefix="omphalos-subject-") as temporary:
        source = Path(temporary)
        write_json(source / "entities.json", [record])
        return import_dataset(
            source,
            dest,
            label=name.strip(),
            synthetic=False,
            intake_method="subject_name",
        )


def _read_vendor(path: Path) -> tuple[bytes, list[str], list[dict], str]:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".csv":
        raise DatasetError(
            ["Choose one regular UTF-8 CSV vendor or counterparty list."]
        )
    safe_child(path.parent, path.name)
    if path.stat().st_size > MAX_VENDOR_BYTES:
        raise DatasetError(
            [
                "Guided vendor lists are limited to 20 MiB; use the strict import path for larger normalized datasets."
            ]
        )
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("NUL characters are not accepted")
        try:
            delimiter = csv.Sniffer().sniff(text[:65536], delimiters=",;\t").delimiter
        except csv.Error:
            delimiter = ","
        reader = csv.reader(
            io.StringIO(text, newline=""), delimiter=delimiter, strict=True
        )
        headers = next(reader, [])
        if (
            not headers
            or len(headers) > MAX_VENDOR_COLUMNS
            or any(not h.strip() or len(h) > 200 for h in headers)
        ):
            raise ValueError(
                "Use a header with 1–100 nonblank column names of at most 200 characters"
            )
        if len(headers) != len(set(headers)):
            raise ValueError("Repeated CSV column names are ambiguous")
        rows = []
        for cells in reader:
            # Entirely blank physical lines are not records; csv.reader omits no
            # populated cells. Blank populated rows still fail required-name validation.
            if not cells:
                continue
            if len(cells) != len(headers):
                raise ValueError(
                    f"line {reader.line_num}: row width differs from the header"
                )
            rows.append(
                {"source_row": reader.line_num, "values": dict(zip(headers, cells))}
            )
            if len(rows) > MAX_VENDOR_ROWS:
                raise ValueError("Guided vendor lists are limited to 50,000 records")
        if not rows:
            raise ValueError("The CSV contains no counterparty records")
        return raw, headers, rows, delimiter
    except (UnicodeError, ValueError, csv.Error) as exc:
        raise DatasetError([f"{path.name}: {exc}"]) from exc


def _suggest_mapping(headers: list[str]) -> tuple[dict[str, str | None], list[str]]:
    aliases = {
        alias: target for target, names in HEADER_ALIASES.items() for alias in names
    }
    mapping = {header: aliases.get(_key(header)) for header in headers}
    targets = Counter(target for target in mapping.values() if target)
    errors = [
        f"Several columns could supply {target}: {', '.join(h for h in headers if mapping[h] == target)}. Choose one and retain the others only in the original file."
        for target, count in targets.items()
        if count > 1
    ]
    return mapping, errors


def _check_mapping(headers: list[str], mapping: dict) -> list[str]:
    errors = []
    if not isinstance(mapping, dict) or set(mapping) != set(headers):
        return [
            "Mapping must contain every original column exactly once, with no additional columns."
        ]
    for column, target in mapping.items():
        if target is not None and (
            not isinstance(target, str) or target not in Entity.model_fields
        ):
            errors.append(f"Column {column}: unsupported entity field {target!r}.")
    targets = Counter(target for target in mapping.values() if isinstance(target, str))
    errors.extend(
        f"More than one column maps to {target}; choose one source column."
        for target, count in targets.items()
        if count > 1
    )
    if targets.get("name", 0) != 1:
        errors.append("Map exactly one column to the counterparty name.")
    return errors


def _mapped_rows(
    raw: bytes, rows: list[dict], mapping: dict[str, str | None]
) -> tuple[list[dict], list[dict], list[dict], int]:
    file_hash = sha256_bytes(raw)
    normalized, origins = [], []
    conversions: Counter = Counter()
    generated = 0
    for original in rows:
        row = {
            target: original["values"][column]
            for column, target in mapping.items()
            if target is not None
        }
        if not row.get("entity_id", "").strip():
            row["entity_id"] = (
                "E_"
                + sha256_bytes(f"{file_hash}:{original['source_row']}".encode())[:24]
            )
            generated += 1
        country = row.get("country", "").strip()
        if country:
            cleaned = _key(country)
            if cleaned in COUNTRY_NAMES:
                country = COUNTRY_NAMES[cleaned]
            elif re.fullmatch(r"[A-Za-z]{2}", country):
                country = country.upper()
            if country != row["country"]:
                conversions[(row["country"], country)] += 1
            row["country"] = country
        if row.get("lei"):
            upper = row["lei"].strip().upper()
            if upper != row["lei"]:
                conversions[(row["lei"], upper)] += 1
            row["lei"] = upper
        normalized.append(row)
        origins.append({"source_row": original["source_row"]})
    changes = [
        {"source_value": before, "normalized_value": after, "record_count": count}
        for (before, after), count in sorted(conversions.items())
    ]
    return normalized, origins, changes, generated


def _vendor_result(path: Path, mapping: dict | None) -> dict:
    raw, headers, rows, delimiter = _read_vendor(path)
    suggestion, ambiguity = _suggest_mapping(headers)
    chosen = suggestion if mapping is None else mapping
    if not isinstance(chosen, dict):
        raise DatasetError(["Column mapping must be an object."])
    errors = (ambiguity if mapping is None else []) + _check_mapping(headers, chosen)
    normalized, origins, changes, generated = [], [], [], 0
    if not errors:
        mapped, origins, changes, generated = _mapped_rows(raw, rows, chosen)
        for origin in origins:
            origin["source_file"] = path.name
        try:
            tables, _ = validate_tables({"entities": mapped}, {"entities": origins})
            normalized = tables["entities"]
        except DatasetError as exc:
            errors.extend(exc.errors)
    preview_id = sha256_bytes(
        canonical_json(
            {
                "file_sha256": sha256_bytes(raw),
                "file_name": path.name,
                "mapping": chosen,
                "kind": VENDOR_TRANSFORM,
                "id_strategy": ID_STRATEGY,
                "delimiter": delimiter,
            }
        )
    )
    return {
        "raw": raw,
        "headers": headers,
        "rows": rows,
        "mapping": chosen,
        "errors": errors,
        "entities": normalized,
        "origins": origins,
        "changes": changes,
        "generated": generated,
        "delimiter": delimiter,
        "preview_id": preview_id,
    }


def preview_vendor_csv(
    path: Path, mapping: dict[str, str | None] | None = None
) -> dict:
    """Preview every mapping choice and validate all records, without storing data."""
    path = Path(path)
    result = _vendor_result(path, mapping)
    return _preview_result(path, result)


def _preview_result(path: Path, result: dict) -> dict:
    """Describe one parsed input consistently, without reading it a second time."""
    chosen = result["mapping"]
    warnings = [
        "Same-name records remain separate entities. No identity merge or transaction linking occurs.",
        "Original CSV bytes and unmapped columns will be retained. Only mapped fields participate in analysis.",
        "Text fields are trimmed; entity type defaults to organization when absent. Country conversions are explicitly listed below.",
    ]
    if "aliases" in chosen.values():
        warnings.append(
            "Aliases accept a JSON array or | separators; they are trimmed, sorted, and deduplicated within each record. The original cell remains in the retained CSV."
        )
    retained = [column for column, target in chosen.items() if target is None]
    if retained:
        warnings.append(
            "Columns retained only in the original file: " + ", ".join(retained)
        )
    if result["generated"]:
        warnings.append(
            f"Generated {result['generated']} deterministic record IDs from the complete file hash and source row; they are not verified business identifiers."
        )
    source_order = {}
    if not result["errors"]:
        mapped_rows, row_origins, _, _ = _mapped_rows(
            result["raw"], result["rows"], chosen
        )
        source_order = {
            str(row["entity_id"]).strip(): origin["source_row"]
            for row, origin in zip(mapped_rows, row_origins)
        }
    duplicates = len(result["entities"]) - len(
        {row["name"].casefold() for row in result["entities"]}
    )
    if duplicates:
        warnings.append(f"{duplicates} repeated-name records are retained separately.")
    return {
        "preview_id": result["preview_id"],
        "file_name": path.name,
        "sha256": sha256_bytes(result["raw"]),
        "row_count": len(result["rows"]),
        "mapping": chosen,
        "delimiter": "tab" if result["delimiter"] == "\t" else result["delimiter"],
        "columns": [
            {
                "name": column,
                "target_field": chosen.get(column),
                "status": "mapped" if chosen.get(column) else "retained_only",
                "samples": list(
                    dict.fromkeys(
                        row["values"][column][:200] for row in result["rows"][:10]
                    )
                )[:3],
            }
            for column in result["headers"]
        ],
        "target_fields": [
            {
                "id": field,
                "title": {
                    "entity_id": "Record ID",
                    "name": "Counterparty name",
                    "registration_id": "Registration number",
                    "lei": "Legal entity identifier (LEI)",
                }.get(field, field.replace("_", " ").capitalize()),
                "required": field == "name",
            }
            for field in Entity.model_fields
        ],
        "preview_rows": sorted(
            result["entities"], key=lambda row: source_order[row["entity_id"]]
        )[:5],
        "transformations": result["changes"],
        "generated_id_count": result["generated"],
        "retained_only_columns": retained,
        "warnings": warnings,
        "errors": list(dict.fromkeys(result["errors"])),
        "can_import": not result["errors"],
    }


def import_vendor_csv(
    path: Path,
    dest: Path,
    *,
    mapping: dict[str, str | None],
    preview_id: str,
    label: str = "",
    synthetic: bool = False,
) -> dict:
    """Apply the reviewed mapping, preserving original bytes and the exact recipe."""
    path, dest = Path(path), Path(dest)
    if not isinstance(mapping, dict):
        raise DatasetError(["An explicit column mapping object is required."])
    safe_id(dest.name)
    if (
        dest.is_symlink()
        or dest.exists()
        and (not dest.is_dir() or any(dest.iterdir()))
    ):
        raise DatasetError(["Destination must not exist or must be empty."])
    result = _vendor_result(path, mapping)
    if not isinstance(preview_id, str) or preview_id != result["preview_id"]:
        raise DatasetError(
            [
                "The file or mapping changed since preview. Preview the current mapping before importing."
            ]
        )
    if result["errors"]:
        raise DatasetError(result["errors"])
    preview = _preview_result(path, result)
    rows = result["entities"]
    mapped, origins, _, _ = _mapped_rows(result["raw"], result["rows"], mapping)
    provenance = {
        str(row["entity_id"]).strip(): {
            "source_file": path.name,
            "source_row": origin["source_row"],
        }
        for row, origin in zip(mapped, origins)
    }
    transform = {
        "kind": VENDOR_TRANSFORM,
        "source_file": path.name,
        "mapping": mapping,
        "id_strategy": ID_STRATEGY,
        "delimiter": result["delimiter"],
        "preview_id": preview_id,
    }
    metadata = {
        "dataset_id": dest.name,
        "intake_method": "vendor_csv",
        "label": label or path.stem,
        "synthetic": bool(synthetic),
        "counts": {"entities": len(rows)},
        "warnings": preview["warnings"]
        + [
            "Shipments and payments were not supplied; transaction-pattern investigations require linked transaction data."
        ],
        "source_files": [
            {
                "path": f"originals/{path.name}",
                "sha256": sha256_bytes(result["raw"]),
                "size_bytes": len(result["raw"]),
            }
        ],
        "field_coverage": {
            "entities": {
                field: sum(row.get(field) not in (None, "", []) for row in rows)
                for field in Entity.model_fields
            }
        },
        "provenance": {"entities": provenance},
        "import_transform": transform,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".vendor-", dir=dest.parent))
    try:
        (stage / "originals").mkdir()
        (stage / "originals" / path.name).write_bytes(result["raw"])
        write_json(
            stage / "dataset.json",
            {
                "schema_version": "2.0",
                "tables": {"entities": rows},
                "metadata": metadata,
            },
        )
        write_json(
            stage / "dataset-manifest.json",
            {
                "schema_version": "2.0",
                **metadata,
                "dataset_sha256": sha256_file(stage / "dataset.json"),
            },
        )
        if dest.exists():
            dest.rmdir()
        os.replace(stage, dest)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    LOG.info(
        "guided_vendor_imported",
        extra={"dataset_id": dest.name, "entity_count": len(rows)},
    )
    return metadata


def vendor_source_records(path: Path, transform: dict) -> dict:
    """Reconstruct original-row identities for data.load_dataset integrity checks."""
    if not isinstance(transform, dict) or set(transform) != {
        "kind",
        "source_file",
        "mapping",
        "id_strategy",
        "delimiter",
        "preview_id",
    }:
        raise DatasetError(["Invalid guided import transformation recipe."])
    if (
        transform["kind"] != VENDOR_TRANSFORM
        or transform["id_strategy"] != ID_STRATEGY
        or transform["source_file"] != path.name
        or not isinstance(transform["mapping"], dict)
    ):
        raise DatasetError(
            ["Unknown or inconsistent guided import transformation recipe."]
        )
    result = _vendor_result(path, transform["mapping"])
    if result["errors"]:
        raise DatasetError(result["errors"])
    if (
        result["preview_id"] != transform["preview_id"]
        or result["delimiter"] != transform["delimiter"]
    ):
        raise DatasetError(
            ["Guided import recipe does not reproduce the reviewed preview."]
        )
    mapped, origins, _, _ = _mapped_rows(
        result["raw"], result["rows"], transform["mapping"]
    )
    return {
        (path.name, "entities", origin["source_row"]): Entity.model_validate(
            row
        ).model_dump(mode="json")
        for row, origin in zip(mapped, origins)
    }


def _source_status(snapshot: dict | None, as_of: date, required: bool) -> dict:
    metadata = snapshot.get("metadata", {}) if snapshot else {}
    updated = str(metadata.get("source_updated_at") or "")
    status = {
        "required": required,
        "selected": bool(snapshot),
        "snapshot_id": snapshot.get("snapshot_id") if snapshot else None,
        "source_id": snapshot.get("source_id") if snapshot else None,
        "title": metadata.get("title"),
        "ingestion_method": metadata.get("ingestion_method"),
        "source_updated_at": metadata.get("source_updated_at"),
        "fetched_at": metadata.get("fetched_at"),
        "record_count": len(snapshot.get("entries", [])) if snapshot else 0,
        "freshness": "missing" if not snapshot else "unknown",
        "age_days": None,
        "date_note": metadata.get(
            "date_note",
            "Source dates do not establish completeness of list membership.",
        ),
        "warnings": list(metadata.get("warnings", [])),
        "recommended_source_id": "csl",
        "freshness_note": "The seven-day cutoff is a planning heuristic, not a guarantee that a list is current or complete. No live update check occurs during planning.",
    }
    if snapshot:
        try:
            age = (as_of - date.fromisoformat(updated[:10])).days
            status["age_days"] = age
            status["freshness"] = (
                "historical_mismatch"
                if age < 0
                else "stale" if age > 7 else "recent_as_of"
            )
            if age < 0:
                status["warnings"].append(
                    "This snapshot is dated after the assessment date; historical membership may be unestablished."
                )
            elif age > 7:
                status["warnings"].append(
                    f"The source timestamp precedes the assessment date by {age} days; later list changes may be missing."
                )
        except ValueError:
            status["warnings"].append(
                "The source publication or aggregation date is unavailable."
            )
    return status


def plan_case(
    dataset: dict,
    goal_id: str,
    *,
    as_of: str | None = None,
    snapshot: dict | None = None,
    case_id: str | None = None,
) -> dict:
    """Propose a reviewable case using actual detector eligibility, with no writes."""
    if goal_id not in GOALS:
        raise ValueError(
            "Choose counterparty_screening, transaction_review, or data_readiness."
        )
    goal = GOALS[goal_id]
    dataset_id = safe_id(dataset["metadata"]["dataset_id"])
    day = as_of if as_of is not None else datetime.now(timezone.utc).date().isoformat()
    proposed_id = (
        case_id
        or f"{'screen' if goal['requires_source'] else 'review'}-{dataset_id[:36]}-{str(day).replace('-', '')}-{uuid.uuid4().hex[:8]}"
    )
    label = str(dataset["metadata"].get("label") or dataset_id)[:1000]
    question = (
        f"Which identity or transaction fields are missing in {label}, and what context is needed before further investigation?"
        if goal_id == "data_readiness"
        else (
            f"Which listed-name or identifier candidates among counterparties in {label} require identity review?"
            if goal["requires_source"]
            else f"Which transaction patterns in {label} require follow-up, and what records would explain them?"
        )
    )
    definitions = {definition["id"]: definition for definition in catalog()}
    defaults = {
        iid: {
            key: spec["default"]
            for key, spec in definitions[iid]["parameters"].items()
            if "default" in spec
        }
        for iid in goal["checks"]
    }
    proposed = Case.model_validate(
        {
            "case_id": proposed_id,
            "question": question,
            "dataset_id": dataset_id,
            "as_of": day,
            "investigations": goal["checks"],
            "parameters": {iid: values for iid, values in defaults.items() if values},
            "scope": {},
            "watchlist_snapshot_id": (
                snapshot["snapshot_id"]
                if snapshot and goal["requires_source"]
                else None
            ),
        }
    ).model_dump(mode="json")
    preflight = {
        **proposed,
        "investigations": [
            iid for iid in proposed["investigations"] if iid != "screening_candidates"
        ],
        "parameters": {
            iid: values
            for iid, values in proposed["parameters"].items()
            if iid != "screening_candidates"
        },
    }
    inspected = analyze(dataset, preflight)
    if goal["requires_source"]:
        entity_count = len(eligible_screening_entities(dataset["tables"]["entities"]))
        if snapshot is None:
            reason = "An explicitly selected official-list snapshot is required."
        elif not entity_count:
            reason = "No entity records have a usable name, alias, or supported identifier for screening."
        elif (
            len(dataset["tables"]["entities"]) * len(snapshot.get("entries", []))
            > 20_000_000
        ):
            reason = "Screening exceeds 20 million entity/list comparisons; narrow entity scope and run additional cases."
        elif not applicable_source_records(
            snapshot, date.fromisoformat(proposed["as_of"])
        )[0]:
            reason = "No source records remain within the case's effective-date scope; no identity comparisons can be performed."
        else:
            reason = ""
        inspected["coverage"].insert(
            0,
            {
                "investigation_id": "screening_candidates",
                "status": "not_evaluable" if reason else "executed",
                "records_evaluated": 0 if reason else entity_count,
                "findings_count": 0,
                "reason": reason,
                "limitations": definitions["screening_candidates"]["limitations"]
                + [
                    "Planning checks screening prerequisites only; identity comparisons execute when the case runs."
                ],
            },
        )
    checks = [
        {
            "id": row["investigation_id"],
            "title": definitions[row["investigation_id"]]["title"],
            "description": definitions[row["investigation_id"]]["description"],
            "parameters": defaults[row["investigation_id"]],
            **row,
        }
        for row in inspected["coverage"]
    ]
    selected = [row for row in checks if row["status"] == "executed"]
    unavailable = [row for row in checks if row["status"] == "not_evaluable"]
    # Preserve the entire goal's analytical scope in the saved case. The runner
    # records missing prerequisites as not_evaluable, so those limitations remain
    # visible in later reviews and exports, not only in this ephemeral preview.
    source_status = _source_status(
        snapshot if goal["requires_source"] else None,
        date.fromisoformat(proposed["as_of"]),
        goal["requires_source"],
    )
    screening_ready = any(row["id"] == "screening_candidates" for row in selected)
    transaction_ids = set(GOALS["transaction_review"]["checks"]) - {
        "data_quality",
        "shared_address",
    }
    can_run = (
        screening_ready
        if goal["requires_source"]
        else (
            True
            if goal_id == "data_readiness"
            else any(row["id"] in transaction_ids for row in selected)
        )
    )
    next_action = (
        "run"
        if can_run
        else (
            "add_source"
            if goal["requires_source"] and snapshot is None
            else "change_scope" if goal["requires_source"] else "add_transactions"
        )
    )
    dated = [
        row["date"]
        for table in ("shipments", "payments")
        for row in dataset["tables"].get(table, [])
        if row.get("date")
    ]
    notes = [
        "The proposed checks use existing deterministic analyses and default parameters; they do not decide legal status.",
        "Unavailable checks are listed separately, not treated as checks with no findings.",
    ]
    if goal_id == "transaction_review":
        notes.append(
            "Threshold proximity needs an explicit analyst threshold and currency, so it is not automatically selected. Weekend dates alone are not selected as a review priority."
        )
    if dataset["metadata"].get("synthetic"):
        notes.append(
            "This dataset is synthetic; observations demonstrate the workflow, not real counterparty risk."
        )
    if any(
        not row.get("date")
        for table in ("shipments", "payments")
        for row in dataset["tables"].get(table, [])
    ):
        notes.append(
            "Undated records remain in the proposed broad scope; date-dependent checks exclude them and report coverage limits."
        )
    if dated and max(dated) > proposed["as_of"]:
        notes.append(
            "Records dated after the assessment date will be excluded, not moved into scope by changing the date automatically."
        )
    return {
        "goal": {key: value for key, value in goal.items() if key != "checks"},
        "case": proposed,
        "suggested_case_id": proposed["case_id"],
        "selected_checks": selected,
        "unavailable_checks": unavailable,
        "source_status": source_status,
        "dataset_summary": {
            "dataset_id": dataset_id,
            "label": label,
            "synthetic": bool(dataset["metadata"].get("synthetic")),
            "counts": {table: len(rows) for table, rows in dataset["tables"].items()},
            "earliest_record_date": min(dated) if dated else None,
            "latest_record_date": max(dated) if dated else None,
            "scope_counts": inspected["scope_counts"],
        },
        "notes": notes,
        "can_run": can_run,
        "next_action": next_action,
    }

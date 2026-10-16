"""Strict, local, provenance-preserving imports of analyst-provided records."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import shutil
import tempfile
from datetime import date as Date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .util import read_json, safe_child, safe_id, sha256_bytes, sha256_file, write_json

LOG = logging.getLogger(__name__)
MAX_FILE_BYTES = 80 * 1024 * 1024
MAX_ROWS = 250_000
Positive = Annotated[Decimal, Field(gt=0, max_digits=28, decimal_places=8)]
Percentage = Annotated[Decimal, Field(ge=0, le=100, max_digits=12, decimal_places=8)]


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def blanks(cls, value: Any, info: Any) -> Any:
        field = cls.model_fields[info.field_name]
        if info.field_name in {"date", "valid_from", "valid_to"} and value not in (
            None,
            "",
        ):
            if (
                not isinstance(value, (str, Date))
                or isinstance(value, str)
                and value.strip()
                and not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
            ):
                raise ValueError("dates must use YYYY-MM-DD")
        if isinstance(value, str) and not value.strip() and not field.is_required():
            return (
                field.default if not field.default_factory else field.default_factory()
            )
        return value

    @field_validator("*", mode="after")
    @classmethod
    def safe_values(cls, value: Any, info: Any) -> Any:
        if isinstance(value, str):
            if len(value) > 20_000 or "\x00" in value:
                raise ValueError("text is too long or contains a null character")
            if info.field_name == "source_url":
                parsed = urlparse(value)
                if (
                    parsed.scheme not in {"https", "http"}
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                ):
                    raise ValueError(
                        "source_url must be an HTTP(S) URL without embedded credentials"
                    )
            if info.field_name in {
                "entity_id",
                "shipment_id",
                "payment_id",
                "relationship_id",
                "evidence_id",
                "exporter_id",
                "importer_id",
                "child_id",
                "parent_id",
            }:
                safe_id(value)
        return value


class Entity(Row):
    entity_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=1000)
    entity_type: str = "organization"
    aliases: list[str] = Field(default_factory=list, max_length=100)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    registration_id: str | None = None
    lei: str | None = Field(default=None, pattern=r"^[A-Z0-9]{20}$")
    notes: str | None = None

    @field_validator("aliases", mode="before")
    @classmethod
    def aliases_cell(cls, value: Any) -> Any:
        if isinstance(value, str):
            return (
                json.loads(value)
                if value.lstrip().startswith("[")
                else [v.strip() for v in value.split("|") if v.strip()]
            )
        return value

    @field_validator("aliases")
    @classmethod
    def alias_text(cls, value: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 1000 or "\x00" in v for v in value):
            raise ValueError("aliases must be nonblank text of at most 1000 characters")
        return sorted(set(v.strip() for v in value))


class Shipment(Row):
    shipment_id: str
    exporter_id: str
    importer_id: str | None = None
    domain: str | None = None
    date: Date | None = None
    qty: Positive | None = None
    unit: str | None = None
    commodity_code: str | None = None
    hs_code: str | None = Field(default=None, pattern=r"^\d{2,12}$")
    eccn: str | None = None
    invoice_id: str | None = None
    declared_value: Positive | None = None
    ccy: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    mode: str | None = None
    incoterm: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def money_unit(self) -> Shipment:
        if (self.declared_value is None) != (self.ccy is None):
            raise ValueError("declared_value and ccy must be supplied together")
        return self


class Payment(Row):
    payment_id: str
    shipment_id: str
    amount: Positive
    ccy: str = Field(pattern=r"^[A-Z]{3}$")
    method: str | None = None
    date: Date | None = None
    bank: str | None = None
    broker: str | None = None


class Ownership(Row):
    relationship_id: str
    child_id: str
    parent_id: str
    ownership_percent: Percentage | None = None
    valid_from: Date | None = None
    valid_to: Date | None = None
    source_url: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def relationship_dates(self) -> Ownership:
        if self.child_id == self.parent_id:
            raise ValueError("parent_id and child_id must differ")
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_to precedes valid_from")
        return self


class Diligence(Row):
    evidence_id: str
    entity_id: str
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_url: str | None = None
    date: Date | None = None


TABLES: dict[str, tuple[type[Row], str]] = {
    "entities": (Entity, "entity_id"),
    "shipments": (Shipment, "shipment_id"),
    "payments": (Payment, "payment_id"),
    "ownership": (Ownership, "relationship_id"),
    "diligence": (Diligence, "evidence_id"),
}


class DatasetError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Dataset rejected:\n" + "\n".join(errors))


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError(f"duplicate JSON key: {k}")
        result[k] = v
    return result


def _json(raw: bytes) -> Any:
    return json.loads(
        raw.decode("utf-8-sig"),
        object_pairs_hook=_pairs,
        parse_float=Decimal,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON number: {value}")
        ),
    )


def _dataset_tables(value: Any) -> dict:
    """Recognize the explicit linked-dataset envelope independently of its name."""
    if (
        not isinstance(value, dict)
        or "tables" not in value
        or set(value) - {"tables", "schema_version"}
    ):
        raise ValueError(
            "a complete dataset JSON must contain tables and optionally schema_version"
        )
    if value.get("schema_version", "2.0") != "2.0":
        raise ValueError("unsupported dataset schema version")
    if not isinstance(value["tables"], dict):
        raise ValueError("tables must be an object")
    return value["tables"]


def validate_tables(
    tables: dict, origins: dict | None = None
) -> tuple[dict, list[str]]:
    """Validate all rows and references; never silently drop an invalid row."""
    errors: list[str] = []
    result: dict = {}
    origins = origins or {}
    if not isinstance(tables, dict):
        raise DatasetError(["tables must be an object"])
    if "entities" not in tables or not tables.get("entities"):
        errors.append("entities: at least one entity is required")
    for table, rows in tables.items():
        if table not in TABLES:
            errors.append(f"unknown table: {table}")
            continue
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            errors.append(f"{table}: expected an array with at most {MAX_ROWS} records")
            continue
        cls, id_key = TABLES[table]
        result[table] = []
        seen: set[str] = set()
        for index, raw in enumerate(rows):
            origin = origins.get(table, [])
            location = (
                f"{origin[index]['source_file']}:{origin[index]['source_row']}"
                if index < len(origin)
                else f"{table}[{index + 1}]"
            )
            try:
                model = cls.model_validate(raw)
                row = model.model_dump(mode="json")
                if row[id_key] in seen:
                    errors.append(f"{location}: duplicate {id_key} {row[id_key]}")
                seen.add(row[id_key])
                result[table].append(row)
            except (ValidationError, ValueError, TypeError) as exc:
                if isinstance(exc, ValidationError):
                    for item in exc.errors(include_input=False, include_url=False):
                        errors.append(
                            f"{location}: {'.'.join(map(str, item['loc']))}: {item['msg']}"
                        )
                else:
                    errors.append(f"{location}: {exc}")
            if len(errors) >= 100:
                raise DatasetError(
                    errors + ["Stopped after 100 errors; no records imported."]
                )
    entities = {r["entity_id"] for r in result.get("entities", [])}
    shipments = {r["shipment_id"] for r in result.get("shipments", [])}
    for table, fields, target in [
        ("shipments", ("exporter_id", "importer_id"), entities),
        ("payments", ("shipment_id",), shipments),
        ("ownership", ("child_id", "parent_id"), entities),
        ("diligence", ("entity_id",), entities),
    ]:
        for row in result.get(table, []):
            for field in fields:
                if row.get(field) is not None and row[field] not in target:
                    errors.append(
                        f"{table}/{row[TABLES[table][1]]}: {field} references missing record {row[field]}"
                    )
    if errors:
        raise DatasetError(
            errors[:100]
            + (
                ["Further errors omitted; no records imported."]
                if len(errors) > 100
                else []
            )
        )
    for table in result:
        result[table].sort(key=lambda row: row[TABLES[table][1]])
    warnings = [
        f"{table} table not supplied."
        for table in ("shipments", "payments")
        if table not in result
    ]
    return result, warnings


def import_dataset(
    source_dir: Path,
    dest: Path,
    *,
    label: str = "",
    synthetic: bool = False,
    intake_method: str = "linked_records",
) -> dict:
    source_dir, dest = Path(source_dir), Path(dest)
    if intake_method not in {"linked_records", "subject_name"}:
        raise DatasetError(["Unsupported dataset intake method."])
    safe_id(dest.name)
    if not source_dir.is_dir() or source_dir.is_symlink():
        raise DatasetError(["source must be a real directory"])
    if (
        dest.is_symlink()
        or dest.exists()
        and (not dest.is_dir() or any(dest.iterdir()))
    ):
        raise DatasetError(["destination must not exist or must be empty"])
    files = sorted(
        p for p in source_dir.iterdir() if p.suffix.lower() in (".csv", ".json")
    )
    if not files:
        raise DatasetError(["no entities.csv/json or dataset.json found"])
    tables, origins, originals = {}, {}, {}
    for p in files:
        if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_FILE_BYTES:
            raise DatasetError(
                [f"{p.name}: invalid file or exceeds {MAX_FILE_BYTES} bytes"]
            )
        raw = p.read_bytes()
        originals[p.name] = raw
        try:
            value = _json(raw) if p.suffix.lower() == ".json" else None
            if p.name == "dataset.json" or (
                isinstance(value, dict) and "tables" in value
            ):
                if len(files) != 1:
                    raise ValueError(
                        "a complete dataset JSON cannot be combined with per-table files"
                    )
                tables = _dataset_tables(value)
                origins = {
                    t: [
                        {"source_file": p.name, "source_row": i + 1}
                        for i in range(len(rows))
                    ]
                    for t, rows in tables.items()
                    if isinstance(rows, list)
                }
                continue
            table = p.stem
            if table not in TABLES or table in tables:
                raise ValueError(f"unknown or repeated table filename: {p.name}")
            if p.suffix.lower() == ".json":
                rows = value
                if not isinstance(rows, list):
                    raise ValueError("per-table JSON must be an array of objects")
                locs = [
                    {"source_file": p.name, "source_row": i + 1}
                    for i in range(len(rows))
                ]
            else:
                reader = csv.DictReader(
                    io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True
                )
                if not reader.fieldnames or len(reader.fieldnames) != len(
                    set(reader.fieldnames)
                ):
                    raise ValueError("CSV header is missing or repeats a field")
                rows, locs = [], []
                for row in reader:
                    if None in row or any(v is None for v in row.values()):
                        raise ValueError(
                            f"line {reader.line_num}: row width does not match header"
                        )
                    rows.append(row)
                    locs.append({"source_file": p.name, "source_row": reader.line_num})
            tables[table], origins[table] = rows, locs
        except (ValueError, KeyError, UnicodeError, csv.Error, RecursionError) as exc:
            raise DatasetError([f"{p.name}: {exc}"]) from exc
    normalized, warnings = validate_tables(tables, origins)
    provenance = {
        table: {
            str(row[TABLES[table][1]]).strip(): origin
            for row, origin in zip(tables[table], origins[table])
        }
        for table in normalized
    }
    counts = {table: len(rows) for table, rows in sorted(normalized.items())}
    source_files = [
        {
            "path": f"originals/{name}",
            "sha256": sha256_bytes(raw),
            "size_bytes": len(raw),
        }
        for name, raw in sorted(originals.items())
    ]
    coverage = {
        table: {
            field: sum(row.get(field) not in (None, "", []) for row in rows)
            for field in TABLES[table][0].model_fields
        }
        for table, rows in normalized.items()
    }
    metadata = {
        "dataset_id": dest.name,
        "intake_method": intake_method,
        "label": label or dest.name,
        "synthetic": bool(synthetic),
        "counts": counts,
        "warnings": warnings,
        "source_files": source_files,
        "field_coverage": coverage,
        "provenance": provenance,
    }
    dataset = {"schema_version": "2.0", "tables": normalized, "metadata": metadata}
    dest.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".dataset-", dir=dest.parent))
    try:
        (stage / "originals").mkdir()
        for name, raw in originals.items():
            (stage / "originals" / name).write_bytes(raw)
        write_json(stage / "dataset.json", dataset)
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
        "dataset_imported",
        extra={"dataset_id": dest.name, "counts": counts, "synthetic": synthetic},
    )
    return metadata


def load_dataset(path: Path, *, _identity_depth: int = 0) -> dict:
    """Load only intact imports with complete, resolvable row provenance."""
    path = Path(path)
    if path.is_symlink():
        raise DatasetError(["dataset symlinks are not supported"])
    dataset_path = safe_child(path, "dataset.json")
    manifest = read_json(safe_child(path, "dataset-manifest.json"))
    if sha256_file(dataset_path) != manifest.get("dataset_sha256"):
        raise DatasetError(["normalized dataset checksum mismatch"])
    data = read_json(dataset_path)
    if not isinstance(data, dict) or data.get("schema_version") != "2.0":
        raise DatasetError(["unsupported dataset schema"])
    normalized, _ = validate_tables(data.get("tables"))
    if normalized != data["tables"]:
        raise DatasetError(["dataset is not normalized; import it before analysis"])
    metadata = data.get("metadata")
    if not isinstance(metadata, dict) or any(
        manifest.get(k) != v for k, v in metadata.items()
    ):
        raise DatasetError(["dataset metadata differs from import manifest"])
    if metadata.get("counts") != {k: len(v) for k, v in normalized.items()}:
        raise DatasetError(["dataset table counts differ from import metadata"])
    if (
        isinstance(metadata.get("import_transform"), dict)
        and metadata["import_transform"].get("kind") == "identity_research_v1"
    ):
        from .identity_workflow import validate_identity_dataset

        return validate_identity_dataset(path, data, depth=_identity_depth)
    source_files = metadata.get("source_files", [])
    if not source_files:
        raise DatasetError(["missing original input inventory"])
    originals = set()
    source_records = {}
    transform = metadata.get("import_transform")
    if transform is not None and (
        not isinstance(transform, dict)
        or transform.get("kind") != "vendor_csv_v1"
        or len(source_files) != 1
        or set(normalized) != {"entities"}
    ):
        raise DatasetError(["Unsupported or inconsistent import transformation."])
    for item in source_files:
        original = safe_child(path, item["path"])
        if not item["path"].startswith("originals/") or item["path"] in originals:
            raise DatasetError(["invalid original input inventory"])
        originals.add(item["path"])
        if (
            original.stat().st_size != item["size_bytes"]
            or sha256_file(original) != item["sha256"]
        ):
            raise DatasetError(
                [f"original input checksum/size mismatch: {item['path']}"]
            )
        if transform is not None:
            from .workflow import vendor_source_records

            source_records.update(vendor_source_records(original, transform))
        elif original.suffix.lower() == ".json":
            value = _json(original.read_bytes())
            original_tables = (
                _dataset_tables(value)
                if original.name == "dataset.json"
                or isinstance(value, dict)
                and "tables" in value
                else {original.stem: value}
            )
            for table, rows in original_tables.items():
                for index, raw_row in enumerate(rows):
                    source_records[(original.name, table, index + 1)] = (
                        TABLES[table][0].model_validate(raw_row).model_dump(mode="json")
                    )
        else:
            with original.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, strict=True)
                for raw_row in reader:
                    source_records[(original.name, original.stem, reader.line_num)] = (
                        TABLES[original.stem][0]
                        .model_validate(raw_row)
                        .model_dump(mode="json")
                    )
    provenance = metadata.get("provenance", {})
    if set(provenance) != set(normalized):
        raise DatasetError(["incomplete provenance table inventory"])
    for table, rows in normalized.items():
        expected = {row[TABLES[table][1]] for row in rows}
        if set(provenance[table]) != expected:
            raise DatasetError([f"incomplete row provenance: {table}"])
        for row in rows:
            origin = provenance[table][row[TABLES[table][1]]]
            if (
                f"originals/{origin.get('source_file')}" not in originals
                or type(origin.get("source_row")) is not int
                or origin["source_row"] < 1
            ):
                raise DatasetError([f"unresolvable row provenance: {table}"])
            if (
                source_records.get((origin["source_file"], table, origin["source_row"]))
                != row
            ):
                raise DatasetError(
                    [
                        f"normalized record differs from original input: {table}/{row[TABLES[table][1]]}"
                    ]
                )
    if transform is not None:
        represented = {
            (origin["source_file"], table, origin["source_row"])
            for table, records in provenance.items()
            for origin in records.values()
        }
        if represented != set(source_records):
            raise DatasetError(["Guided import does not represent every original row."])
    safe_id(metadata["dataset_id"])
    return data


def data_schema() -> dict:
    return {
        "schema_version": "2.0",
        "tables": {name: cls.model_json_schema() for name, (cls, _) in TABLES.items()},
        "notes": [
            "CSV aliases accept a JSON array or | separators.",
            "Dates use YYYY-MM-DD; amounts use decimal strings.",
            "ISO two-letter countries and three-letter currencies use uppercase.",
            "Only positive outgoing payments are supported; refunds require a separate data model.",
            "HS codes are strings, distinct from ECCNs. No currency conversion is inferred.",
        ],
    }


def create_demo(dest: Path) -> dict:
    """Small deterministic planted dataset, including benign and ambiguous cases."""
    entities = [
        {
            "entity_id": "E1",
            "name": "Synthetic Harbor Instruments",
            "country": "US",
            "address": "100 Example Industrial Road",
        },
        {
            "entity_id": "E2",
            "name": "Synthetic Harbor Instruments",
            "country": "GB",
            "address": "200 Demonstration Way",
        },
        {
            "entity_id": "E3",
            "name": "Synthetic Pacific Trading",
            "country": "US",
            "address": "100 Example Industrial Road",
        },
        {
            "entity_id": "E4",
            "name": "Synthetic Valley Labs",
            "country": "US",
            "address": "100 Example Industrial Road",
        },
        {
            "entity_id": "E5",
            "name": "Synthetic Counterparty",
            "country": "DE",
            "address": "300 Sample Street",
        },
    ]
    shipments, payments = [], []

    def add(
        sid: str,
        exporter: str,
        day: str | None,
        amount: str,
        *,
        domain: str = "machine_tools",
        hs: str = "845610",
        currency: str = "USD",
        invoice: str | None = None,
        splits: int = 1,
        unit: str = "pcs",
    ) -> None:
        shipments.append(
            {
                "shipment_id": sid,
                "exporter_id": exporter,
                "importer_id": "E5",
                "domain": domain,
                "date": day,
                "qty": "10",
                "unit": unit,
                "hs_code": hs,
                "invoice_id": invoice or f"DEMO-{sid}",
            }
        )
        for i in range(splits):
            payments.append(
                {
                    "payment_id": f"P-{sid}-{i}",
                    "shipment_id": sid,
                    "amount": str(Decimal(amount) / splits),
                    "ccy": currency,
                    "method": ("wire", "letter_of_credit", "cashlike")[i % 3],
                    "date": day,
                    "bank": "Synthetic Bank",
                    "broker": "Synthetic Broker",
                }
            )

    for i in range(7):
        add(
            f"S{i:02}",
            "E1",
            f"2026-{i + 1:02}-05",
            "1000",
            invoice="INV-1042" if i == 0 else None,
        )
    add("S07", "E1", "2026-08-05", "100000")
    add("S08", "E3", "2026-08-08", "30000", splits=3, invoice="INV-1042")
    add("S09", "E2", "2026-08-09", "1000", currency="EUR")
    add("S10", "E2", "2026-08-10", "1000", currency="JPY", unit="kg")
    add("S11", "E4", None, "1000", domain="laboratory_equipment", hs="902780")
    add("S12", "E3", "2026-08-11", "19400", splits=2, domain="chemicals", hs="290110")
    add("S13", "E3", "2026-08-12", "1000", domain="laboratory_equipment", hs="902780")
    for i in range(10):
        add(f"SPIKE{i}", "E1", f"2026-09-{i + 1:02}", "1000")
    # Benign installment: two wire payments, intentionally below default fragmentation threshold.
    add("BENIGN", "E4", "2026-09-14", "1000", splits=2, domain="chemicals", hs="290110")
    for p in payments:
        if p["shipment_id"] == "BENIGN":
            p["method"] = "wire"
    with tempfile.TemporaryDirectory(prefix="omphalos-demo-") as temp:
        directory = Path(temp)
        write_json(
            directory / "dataset.json",
            {
                "schema_version": "2.0",
                "tables": {
                    "entities": entities,
                    "shipments": shipments,
                    "payments": payments,
                },
            },
        )
        return import_dataset(
            directory,
            Path(dest),
            label="Synthetic demonstration: planted signals and benign counterexamples",
            synthetic=True,
        )

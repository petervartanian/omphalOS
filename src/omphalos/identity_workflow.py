"""Bound public identity research to immutable inputs and replayable derivations."""

from __future__ import annotations

import copy
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .data import TABLES, Entity, load_dataset, validate_tables
from .evidence import _paths
from .util import (
    canonical_json,
    read_json,
    safe_child,
    safe_id,
    sha256_file,
    utc_now,
    write_json,
)

TRANSFORM_KIND = "identity_research_v1"
MANIFEST = "identity-manifest.json"
MAX_DERIVATIONS = 8
SUPPORTED_FIELDS = frozenset(
    {"country", "address", "city", "postal_code", "registration_id", "lei"}
)
BINDING_FIELDS = {
    "schema_version",
    "research_id",
    "dataset_id",
    "dataset_sha256",
    "dataset_manifest_sha256",
    "entity_id",
    "query",
    "created_at",
}
TRANSFORM_FIELDS = {
    "kind",
    "parent_dataset_id",
    "parent_dataset_sha256",
    "parent_manifest_sha256",
    "research_id",
    "research_sha256",
    "entity_id",
    "candidate_id",
    "selected_at",
}


def _copy_tree(source: Path, destination: Path) -> None:
    paths = _paths(source)
    destination.mkdir(parents=True, exist_ok=False)
    for relative, path in paths.items():
        target = safe_child(destination, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def _timestamp(value: Any) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Identity research timestamps must be UTC with Z.")
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def _subject(dataset: dict, entity_id: str | None) -> dict:
    entities = dataset["tables"]["entities"]
    if entity_id is None:
        if len(entities) != 1:
            raise ValueError("Choose an entity from this dataset to research.")
        return entities[0]
    safe_id(entity_id)
    entity = next((row for row in entities if row["entity_id"] == entity_id), None)
    if entity is None:
        raise ValueError("The selected entity is absent from this dataset.")
    return entity


def load_bound_research(path: Path) -> tuple[dict, dict]:
    """Check the complete saved research inventory and reparse provider bytes."""
    from .identity_research import load_research

    path = Path(path)
    paths = _paths(path)
    manifest = read_json(paths.pop(MANIFEST))
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"schema_version", "research_id", "files"}
        or manifest["schema_version"] != "1.0"
        or not isinstance(manifest["files"], list)
    ):
        raise ValueError("Unsupported identity research inventory.")
    entries = manifest["files"]
    if len(entries) != len(paths) or {entry["path"] for entry in entries} != set(paths):
        raise ValueError("Identity research inventory differs from retained files.")
    for entry in entries:
        if set(entry) != {"path", "sha256", "size_bytes"}:
            raise ValueError("Malformed identity research inventory entry.")
        retained = paths[entry["path"]]
        if (
            retained.stat().st_size != entry["size_bytes"]
            or sha256_file(retained) != entry["sha256"]
        ):
            raise ValueError("Retained identity research bytes changed.")
    binding = read_json(safe_child(path, "binding.json"))
    if not isinstance(binding, dict) or set(binding) != BINDING_FIELDS:
        raise ValueError("Malformed identity research input binding.")
    if binding["schema_version"] != "1.0":
        raise ValueError("Unsupported identity research binding.")
    for field in ("research_id", "dataset_id", "entity_id"):
        safe_id(binding[field])
    if binding["research_id"] != manifest["research_id"]:
        raise ValueError("Identity research identifiers differ.")
    _timestamp(binding["created_at"])
    report = load_research(safe_child(path, "provider"))
    if report["query"] != binding["query"]:
        raise ValueError("Identity research query differs from its retained binding.")
    return binding, report


def research_identity(
    dataset_path: Path, destination: Path, entity_id: str | None = None
) -> dict:
    """Research a retained name and save even an empty or unavailable result."""
    from .identity_research import research_subject

    dataset_path, destination = Path(dataset_path), Path(destination)
    dataset = load_dataset(dataset_path)
    entity = _subject(dataset, entity_id)
    safe_id(destination.name)
    if destination.exists():
        raise FileExistsError("Identity research already exists.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".research-", dir=destination.parent))
    try:
        binding = {
            "schema_version": "1.0",
            "research_id": destination.name,
            "dataset_id": dataset["metadata"]["dataset_id"],
            "dataset_sha256": sha256_file(dataset_path / "dataset.json"),
            "dataset_manifest_sha256": sha256_file(
                dataset_path / "dataset-manifest.json"
            ),
            "entity_id": entity["entity_id"],
            "query": entity["name"],
            "created_at": utc_now(),
        }
        research_subject(entity["name"], stage / "provider")
        write_json(stage / "binding.json", binding)
        write_json(
            stage / MANIFEST,
            {
                "schema_version": "1.0",
                "research_id": destination.name,
                "files": [
                    {
                        "path": relative,
                        "sha256": sha256_file(path),
                        "size_bytes": path.stat().st_size,
                    }
                    for relative, path in _paths(stage).items()
                ],
            },
        )
        retained_binding, report = load_bound_research(stage)
        os.replace(stage, destination)
        return {
            **report,
            "research_id": destination.name,
            "dataset_id": retained_binding["dataset_id"],
            "entity_id": retained_binding["entity_id"],
        }
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _bind_parent(dataset_path: Path, dataset: dict, binding: dict) -> None:
    if (
        binding["dataset_id"] != dataset["metadata"]["dataset_id"]
        or binding["dataset_sha256"] != sha256_file(dataset_path / "dataset.json")
        or binding["dataset_manifest_sha256"]
        != sha256_file(dataset_path / "dataset-manifest.json")
        or binding["query"] != _subject(dataset, binding["entity_id"])["name"]
    ):
        raise ValueError("The dataset or subject changed after identity research.")


def _derive(base: dict, report: dict, transform: dict, dataset_id: str) -> dict:
    candidates = [
        row
        for row in report["candidates"]
        if row["candidate_id"] == transform["candidate_id"]
    ]
    if transform["candidate_id"] is not None and len(candidates) != 1:
        raise ValueError("Choose a candidate from this retained identity research.")
    candidate = candidates[0] if candidates else None
    tables = copy.deepcopy(base["tables"])
    original = _subject(base, transform["entity_id"])
    entity = next(
        row for row in tables["entities"] if row["entity_id"] == original["entity_id"]
    )
    applied: dict[str, Any] = {}
    conflicts: list[dict] = []
    if candidate is not None:
        # An explicit person/company contradiction must be resolved by choosing a
        # different profile, not by quietly adding corporate identifiers to a person.
        categories = {
            "person": "person",
            "individual": "person",
            "organization": "organization",
            "organisation": "organization",
            "entity": "organization",
            "company": "organization",
            "corporation": "organization",
            "business": "organization",
            "vessel": "vessel",
            "aircraft": "aircraft",
        }
        entered_type = categories.get(str(entity.get("entity_type", "")).casefold())
        candidate_type = categories.get(candidate.get("entity_type", ""))
        if (
            report["schema_version"] >= 2
            and entered_type
            and candidate_type
            and entered_type != candidate_type
        ):
            raise ValueError(
                "The selected public record describes a different entity type. "
                "Choose a matching record or continue without a profile."
            )
        for field, value in candidate.get("fields", {}).items():
            if field not in SUPPORTED_FIELDS or value in (None, "", []):
                continue
            claims = [
                claim
                for claim in candidate.get("claims", [])
                if claim.get("field") == field and claim.get("value") == value
            ]
            if not claims:
                raise ValueError(
                    f"Research field {field} lacks a retained source claim."
                )
            if entity.get(field) in (None, "", []):
                entity[field] = value
                applied[field] = {"value": value, "claims": claims}
            elif entity[field] != value:
                conflicts.append(
                    {
                        "field": field,
                        "retained_value": entity[field],
                        "source_value": value,
                        "claims": claims,
                    }
                )
        aliases = set(entity.get("aliases", []))
        additions = sorted(
            set([candidate["name"], *candidate.get("aliases", [])])
            - aliases
            - {entity["name"]}
        )
        aliases.update(additions[: max(0, 100 - len(aliases))])
        entity["aliases"] = sorted(aliases)
        if entity["aliases"] != original.get("aliases", []):
            applied["aliases"] = {
                "value": entity["aliases"],
                "source_urls": candidate.get("source_urls", []),
            }
        if entity.get("entity_type") in (None, "", "unknown") and candidate.get(
            "entity_type"
        ) in {"organization", "person"}:
            entity["entity_type"] = candidate["entity_type"]
            applied["entity_type"] = {
                "value": entity["entity_type"],
                "source_urls": candidate.get("source_urls", []),
            }
    Entity.model_validate(entity)
    normalized, _ = validate_tables(tables)
    previous = base["metadata"].get("identity_research")
    history = (
        [
            *previous.get("history", []),
            {k: v for k, v in previous.items() if k != "history"},
        ]
        if previous
        else []
    )
    context = {
        "research_id": transform["research_id"],
        "parent_dataset_id": transform["parent_dataset_id"],
        "entity_id": entity["entity_id"],
        "query": report["query"],
        "status": "selected" if candidate is not None else report["status"],
        "selected_at": transform["selected_at"],
        "selected_candidate": candidate,
        "claims": candidate.get("claims", []) if candidate else [],
        "applied_fields": applied,
        "conflicts": conflicts,
        "history": history,
        "providers": report.get("providers", []),
        "source_urls": candidate.get("source_urls", []) if candidate else [],
        "association": (
            "user_selected_public_record" if candidate else "no_profile_selected"
        ),
        "notice": "Public-source context is retained with its attribution. Selecting a record does not confirm the subject's identity or resolve screening candidates.",
    }
    metadata = {
        **copy.deepcopy(base["metadata"]),
        "dataset_id": safe_id(dataset_id),
        "import_transform": transform,
        "identity_research": context,
        "counts": {table: len(rows) for table, rows in sorted(normalized.items())},
        "field_coverage": {
            table: {
                field: sum(row.get(field) not in (None, "", []) for row in rows)
                for field in TABLES[table][0].model_fields
            }
            for table, rows in normalized.items()
        },
    }
    return {"schema_version": "2.0", "tables": normalized, "metadata": metadata}


def select_identity(
    dataset_path: Path, research_path: Path, destination: Path, candidate_id: str | None
) -> dict:
    """Create a new derived dataset; never mutate the entered records or run."""
    dataset_path, research_path, destination = map(
        Path, (dataset_path, research_path, destination)
    )
    base = load_dataset(dataset_path)
    binding, report = load_bound_research(research_path)
    _bind_parent(dataset_path, base, binding)
    if candidate_id is not None and (
        not isinstance(candidate_id, str) or not candidate_id or len(candidate_id) > 200
    ):
        raise ValueError(
            "Choose a retained identity candidate or continue without one."
        )
    transform = {
        "kind": TRANSFORM_KIND,
        "parent_dataset_id": base["metadata"]["dataset_id"],
        "parent_dataset_sha256": binding["dataset_sha256"],
        "parent_manifest_sha256": binding["dataset_manifest_sha256"],
        "research_id": binding["research_id"],
        "research_sha256": sha256_file(research_path / MANIFEST),
        "entity_id": binding["entity_id"],
        "candidate_id": candidate_id,
        "selected_at": utc_now(),
    }
    data = _derive(base, report, transform, destination.name)
    if destination.exists():
        raise FileExistsError("The derived dataset already exists.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".identity-dataset-", dir=destination.parent))
    try:
        _copy_tree(dataset_path, stage / "base")
        _copy_tree(research_path, stage / "research")
        _copy_tree(dataset_path / "originals", stage / "originals")
        write_json(stage / "dataset.json", data)
        write_json(
            stage / "dataset-manifest.json",
            {
                "schema_version": "2.0",
                **data["metadata"],
                "dataset_sha256": sha256_file(stage / "dataset.json"),
            },
        )
        load_dataset(stage)
        os.replace(stage, destination)
        return data["metadata"]
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def validate_identity_dataset(path: Path, data: dict, *, depth: int) -> dict:
    """Recompute each enriched field from the retained base and provider bytes."""
    if depth >= MAX_DERIVATIONS:
        raise ValueError("Identity research exceeds the retained derivation limit.")
    transform = data["metadata"].get("import_transform")
    if (
        not isinstance(transform, dict)
        or set(transform) != TRANSFORM_FIELDS
        or transform["kind"] != TRANSFORM_KIND
    ):
        raise ValueError("Unsupported identity research derivation.")
    _timestamp(transform["selected_at"])
    base_path = safe_child(path, "base")
    base = load_dataset(base_path, _identity_depth=depth + 1)
    research_path = safe_child(path, "research")
    binding, report = load_bound_research(research_path)
    _bind_parent(base_path, base, binding)
    if any(
        (
            transform["parent_dataset_id"] != binding["dataset_id"],
            transform["parent_dataset_sha256"] != binding["dataset_sha256"],
            transform["parent_manifest_sha256"] != binding["dataset_manifest_sha256"],
            transform["entity_id"] != binding["entity_id"],
            transform["research_id"] != binding["research_id"],
            transform["research_sha256"] != sha256_file(research_path / MANIFEST),
        )
    ):
        raise ValueError("Identity derivation differs from its retained input binding.")
    expected = _derive(base, report, transform, data["metadata"]["dataset_id"])
    if canonical_json(expected) != canonical_json(data):
        raise ValueError(
            "Enriched records differ from the retained research transformation."
        )
    expected_inventory = {"dataset.json", "dataset-manifest.json"}
    for directory in ("base", "research", "originals"):
        expected_inventory.update(
            f"{directory}/{relative}"
            for relative in _paths(safe_child(path, directory))
        )
    if set(_paths(path)) != expected_inventory:
        raise ValueError("Unexpected files in the derived identity dataset.")
    originals = _paths(safe_child(path, "originals"))
    expected_paths = {
        item["path"].removeprefix("originals/")
        for item in base["metadata"]["source_files"]
    }
    if set(originals) != expected_paths:
        raise ValueError(
            "Derived original input inventory differs from the base dataset."
        )
    for item in base["metadata"]["source_files"]:
        retained = safe_child(path, item["path"])
        if (
            retained.stat().st_size != item["size_bytes"]
            or sha256_file(retained) != item["sha256"]
        ):
            raise ValueError(
                "Derived original input bytes differ from the base dataset."
            )
    return data

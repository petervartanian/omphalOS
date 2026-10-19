"""Workspace orchestration with retained inputs, real analysis, and review gates."""

from __future__ import annotations

import importlib.metadata
import json
import logging
import platform
import shutil
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .models import Analysis, Case, parse_review
from .util import (
    OmphalOSError,
    canonical_json,
    read_json,
    safe_child,
    safe_id,
    sha256_bytes,
    sha256_file,
    utc_now,
    write_json,
)

LOGGER = logging.getLogger("omphalos")
PACKAGE_ROOT = Path(__file__).resolve().parent


def engine_inventory() -> dict[str, str]:
    return {
        path.relative_to(PACKAGE_ROOT).as_posix(): sha256_file(path)
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        if "__pycache__" not in path.parts
    }


def runtime_versions() -> dict[str, str]:
    names = ("pydantic", "pydantic_core", "cryptography", "truststore")
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            # Browser HTTPS uses the browser's transport. Unsigned evidence
            # packages do not need the optional native signing dependencies.
            if sys.platform != "emscripten" or name not in {
                "cryptography",
                "truststore",
            }:
                raise
    if sys.platform == "emscripten":
        import pyodide

        versions["pyodide"] = pyodide.__version__
    return versions


# A long-lived local service may retain imported modules while files are edited.
# Refuse to describe newer on-disk files as the code that produced its results.
PROCESS_ENGINE_INVENTORY = engine_inventory()
PROCESS_RUNTIME_VERSIONS = runtime_versions()


def assert_process_environment() -> None:
    if engine_inventory() != PROCESS_ENGINE_INVENTORY:
        raise OmphalOSError(
            "Application code changed after this process started. Restart omphalOS before running or replaying analysis."
        )
    if runtime_versions() != PROCESS_RUNTIME_VERSIONS:
        raise OmphalOSError(
            "Installed dependency versions changed after this process started. Restart omphalOS before running or replaying analysis."
        )


def _copy_regular_tree(source: Path, target: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise OmphalOSError("Snapshot source must be a regular directory.")
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise OmphalOSError("Dataset and source snapshots cannot contain symlinks.")
        relative = path.relative_to(source).as_posix()
        destination = safe_child(target, relative)
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        else:
            raise OmphalOSError(f"Unsupported snapshot entry: {relative}")


def _analysis(value: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    validated = Analysis.model_validate(value).model_dump(mode="json")
    selected = set(case["investigations"])
    executed = {row["investigation_id"] for row in validated["coverage"]}
    if selected != executed:
        raise OmphalOSError(
            "Analysis did not report coverage for every selected investigation."
        )

    def check_numbers(item: Any) -> None:
        if isinstance(item, float):
            raise OmphalOSError(
                "Analysis decimals must be serialized as exact strings."
            )
        if isinstance(item, dict):
            for child in item.values():
                check_numbers(child)
        elif isinstance(item, list):
            for child in item:
                check_numbers(child)

    check_numbers(validated)
    return validated


def _review_timestamp(value: str) -> datetime:
    """Compare recorded instants even when legacy precision differs."""
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Review timestamps must include a time and UTC offset.")
    return timestamp.astimezone(timezone.utc)


class Workspace:
    """Single-user local workspace; every run and review gets a unique identity."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in (
            "datasets",
            "sources",
            "research",
            "cases",
            "runs",
            "reviews",
            "exports",
            "events",
        ):
            path = safe_child(self.root, name)
            path.mkdir(exist_ok=True, mode=0o700)

    def _path(self, kind: str, resource_id: str) -> Path:
        return safe_child(self.root / kind, safe_id(resource_id))

    def _event(self, action: str, resource_id: str, **details: Any) -> None:
        # Each event is an independent, collision-free record. This local activity
        # history is not represented as an authenticated or tamper-proof audit log.
        event = {
            "at": utc_now(),
            "action": action,
            "resource_id": resource_id,
            **details,
        }
        write_json(
            safe_child(self.root, f"events/event-{uuid.uuid4().hex}.json"), event
        )
        LOGGER.info("workspace_event", extra={"event": event})

    def list_datasets(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(safe_child(self.root, "datasets").iterdir()):
            if not path.is_dir() or path.is_symlink() or path.name.startswith("."):
                continue
            try:
                manifest = read_json(safe_child(path, "dataset-manifest.json"))
                metadata = manifest.get("metadata", manifest)
                identity = metadata.get("identity_research")
                identity_summary = {}
                if isinstance(identity, dict):
                    candidate = identity.get("selected_candidate")
                    identity_summary = {
                        "parent_dataset_id": identity.get("parent_dataset_id"),
                        "identity_association": identity.get("association"),
                        "identity_profile": (
                            {
                                "name": candidate.get("name"),
                                "sources": sorted(
                                    {
                                        claim["source_label"]
                                        for claim in candidate.get("claims", [])
                                        if isinstance(claim, dict)
                                        and isinstance(claim.get("source_label"), str)
                                    }
                                ),
                            }
                            if isinstance(candidate, dict)
                            else None
                        ),
                    }
                records.append(
                    {
                        **identity_summary,
                        **{
                            key: metadata[key]
                            for key in (
                                "label",
                                "intake_method",
                                "synthetic",
                                "counts",
                                "warnings",
                                "field_coverage",
                                "source_files",
                            )
                            if key in metadata
                        },
                        "dataset_id": path.name,
                        "identity_research_retained": bool(
                            metadata.get("identity_research")
                        ),
                    }
                )
            except (ValueError, OSError, TypeError):
                records.append(
                    {
                        "dataset_id": path.name,
                        "status": "invalid",
                        "warnings": ["Dataset manifest cannot be read."],
                    }
                )
        return records

    def list_sources(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(safe_child(self.root, "sources").iterdir()):
            if not path.is_dir() or path.is_symlink() or path.name.startswith("."):
                continue
            try:
                manifest_path = safe_child(path, "source-manifest.json")
                if not manifest_path.exists():
                    manifest_path = safe_child(path, "snapshot-manifest.json")
                metadata = read_json(manifest_path)
                records.append({**metadata, "snapshot_id": path.name})
            except (ValueError, OSError, TypeError):
                records.append(
                    {
                        "snapshot_id": path.name,
                        "status": "invalid",
                        "warnings": ["Source manifest cannot be read."],
                    }
                )
        return records

    def list_cases(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        directory = safe_child(self.root, "cases")
        for path in sorted(directory.glob("*.json")):
            try:
                records.append(
                    Case.model_validate(
                        read_json(safe_child(directory, path.name))
                    ).model_dump(mode="json")
                )
            except (ValueError, OSError):
                records.append({"case_id": path.stem, "status": "invalid"})
        return records

    def list_runs(self, *, verify_reviews: bool = True) -> list[dict[str, Any]]:
        """List retained runs, optionally deferring expensive evidence verification.

        The lightweight path reports only that a structurally valid review is
        anchored to the current manifest. Its assessment and retained evidence
        remain unchecked until the run is opened or an explicit check is made.
        """
        records: list[dict[str, Any]] = []
        for path in sorted(safe_child(self.root, "runs").iterdir(), reverse=True):
            if not path.is_dir() or path.is_symlink() or path.name.startswith("."):
                continue
            try:
                manifest = read_json(safe_child(path, "manifest.json"))
                analysis = read_json(safe_child(path, "analysis.json"))
                retained_case = read_json(safe_child(path, "case.json"))
                review, review_validation = self._review_state(
                    path.name, verify_reviews=verify_reviews
                )
                records.append(
                    {
                        "run_id": path.name,
                        "case_id": manifest["case_id"],
                        "dataset_id": retained_case["dataset_id"],
                        "created_at": manifest["created_at"],
                        "analysis_digest": manifest["analysis_digest"],
                        "findings_count": len(analysis["findings"]),
                        "not_evaluable_count": sum(
                            row["status"] == "not_evaluable"
                            for row in analysis["coverage"]
                        ),
                        "status": (
                            ("reviewed" if verify_reviews else "review_recorded")
                            if review
                            else "awaiting_review"
                        ),
                        "case_decision": (
                            review["review"].get("decision") if review else None
                        ),
                        "reviewed_by": (
                            review["review"]["reviewer"] if review else None
                        ),
                        "reviewed_at": review["created_at"] if review else None,
                        "review_validation": review_validation,
                        "verification_status": "not_checked",
                    }
                )
            except (ValueError, OSError, KeyError, TypeError):
                records.append(
                    {
                        "run_id": path.name,
                        "status": "invalid",
                        "verification_status": "failed",
                    }
                )
        return sorted(records, key=lambda row: row.get("created_at", ""), reverse=True)

    def save_case(self, case_dict: dict[str, Any]) -> dict[str, Any]:
        from .investigations import catalog

        case = Case.model_validate(case_dict).model_dump(mode="json")
        known = {row["id"] for row in catalog()}
        unknown = set(case["investigations"]) - known
        if unknown:
            raise OmphalOSError(f"Unknown investigations: {', '.join(sorted(unknown))}")
        if not (self._path("datasets", case["dataset_id"]) / "dataset.json").is_file():
            raise OmphalOSError("Import the selected dataset before saving this case.")
        if (
            case["watchlist_snapshot_id"]
            and not self._path("sources", case["watchlist_snapshot_id"]).is_dir()
        ):
            raise OmphalOSError("The selected screening snapshot is unavailable.")
        destination = safe_child(self.root / "cases", f"{case['case_id']}.json")
        if destination.is_file():
            previous = read_json(destination)
            previous_digest = sha256_bytes(canonical_json(previous))
            archive = safe_child(
                self.root,
                f"cases/history/{case['case_id']}/{previous_digest}.json",
            )
            if not archive.exists():
                write_json(archive, previous)
        write_json(destination, case)
        self._event("case_saved", case["case_id"], case_sha256=sha256_file(destination))
        return case

    def get_case(self, case_id: str) -> dict[str, Any]:
        return Case.model_validate(
            read_json(safe_child(self.root / "cases", f"{safe_id(case_id)}.json"))
        ).model_dump(mode="json")

    def run_case(self, case_id: str) -> dict[str, Any]:
        assert_process_environment()
        from .data import load_dataset
        from .evidence import build_manifest, verify_run
        from .investigations import analyze, catalog
        from .sources import load_source

        case = self.get_case(case_id)
        run_id = "run-" + uuid.uuid4().hex
        destination = self._path("runs", run_id)
        staging = Path(
            tempfile.mkdtemp(prefix=".building-", dir=safe_child(self.root, "runs"))
        )
        try:
            _copy_regular_tree(
                self._path("datasets", case["dataset_id"]), staging / "data"
            )
            dataset = load_dataset(staging / "data")
            watchlist = None
            if case["watchlist_snapshot_id"]:
                _copy_regular_tree(
                    self._path("sources", case["watchlist_snapshot_id"]),
                    staging / "sources",
                )
                watchlist = load_source(staging / "sources")
            workflow = case.get("workflow")
            if workflow and (
                workflow["dataset_sha256"] != sha256_file(staging / "data/dataset.json")
                or workflow["source_sha256"]
                != (
                    sha256_file(staging / "sources/source.json")
                    if watchlist is not None
                    else None
                )
            ):
                raise OmphalOSError(
                    "Approved inputs changed. Review a new plan before running."
                )
            write_json(staging / "case.json", case)
            inventory_before = PROCESS_ENGINE_INVENTORY.copy()
            write_json(staging / "catalog.json", catalog())
            analysis = _analysis(analyze(dataset, case, watchlist), case)
            write_json(staging / "analysis.json", analysis)
            analysis_digest = sha256_file(staging / "analysis.json")
            for name in inventory_before:
                target = safe_child(staging / "engine", name)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(PACKAGE_ROOT / name, target)
                if sha256_file(target) != inventory_before[name]:
                    raise OmphalOSError(
                        "Archived engine bytes differ from the running engine."
                    )
            assert_process_environment()
            computation = {
                "python": platform.python_version(),
                "dependencies": runtime_versions(),
                "case_sha256": sha256_file(staging / "case.json"),
                "dataset_sha256": sha256_file(staging / "data" / "dataset.json"),
                "catalog_sha256": sha256_file(staging / "catalog.json"),
                "engine_files": inventory_before,
                "source_files": (
                    {
                        path.relative_to(staging / "sources").as_posix(): sha256_file(
                            path
                        )
                        for path in sorted((staging / "sources").rglob("*"))
                        if path.is_file()
                    }
                    if watchlist is not None
                    else {}
                ),
            }
            write_json(
                staging / "environment.json",
                {
                    "schema_version": "2.0",
                    "omphalos_version": __version__,
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                    "dependencies": runtime_versions(),
                    "serialization": "omphalos-json-v1",
                    "engine_files": inventory_before,
                    "computation_id": sha256_bytes(canonical_json(computation)),
                    "computation_inputs": computation,
                },
            )
            build_manifest(
                staging,
                run_id=run_id,
                case_id=case["case_id"],
                analysis_digest=analysis_digest,
            )
            verification = verify_run(staging)
            if not verification["ok"]:
                raise OmphalOSError(
                    "Run validation failed: " + "; ".join(verification["issues"])
                )
            staging.rename(destination)
            self._event(
                "run_completed",
                run_id,
                case_id=case_id,
                manifest_sha256=sha256_file(destination / "manifest.json"),
            )
            return {
                "run_id": run_id,
                "case_id": case_id,
                "path": str(destination),
                "findings_count": len(analysis["findings"]),
                "analysis_digest": analysis_digest,
                "status": "awaiting_review",
                "verification": verification,
            }
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def _review_state(
        self, run_id: str, *, verify_reviews: bool = True
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        from .evidence import _review_wrapper, validate_review

        directory = self._path("reviews", run_id)
        candidates: list[dict[str, Any]] = []
        try:
            if directory.exists():
                manifest = safe_child(self._path("runs", run_id), "manifest.json")
                manifest_bytes = manifest.read_bytes()
                for path in directory.glob("*.json"):
                    wrapper = _review_wrapper(
                        read_json(safe_child(directory, path.name)), manifest_bytes
                    )
                    if wrapper["review_id"] != path.stem:
                        raise OmphalOSError(
                            "Stored review ID differs from its filename."
                        )
                    _review_timestamp(wrapper["created_at"])
                    parsed = parse_review(wrapper["review"])
                    if parsed.run_id != run_id:
                        raise OmphalOSError("Stored review refers to a different run.")
                    candidates.append({**wrapper, "path": str(path)})
            if not candidates:
                return None, {"ok": False, "issues": [], "status": "awaiting_review"}
            latest = max(
                candidates,
                key=lambda row: (
                    _review_timestamp(row["created_at"]),
                    row["review_id"],
                ),
            )
            if not verify_reviews:
                return latest, {
                    "ok": False,
                    "issues": [],
                    "status": "not_checked",
                }
            assessment = validate_review(self._path("runs", run_id), latest["review"])
            return (latest if assessment["ok"] else None), assessment
        except (ValueError, OSError, KeyError, TypeError) as exc:
            return None, {
                "ok": False,
                "issues": ["Stored review could not be validated: " + str(exc)],
                **({"status": "invalid"} if not verify_reviews else {}),
            }

    def _latest_review(self, run_id: str) -> dict[str, Any] | None:
        return self._review_state(run_id)[0]

    def get_run(self, run_id: str) -> dict[str, Any]:
        path = self._path("runs", run_id)
        if not path.is_dir():
            raise FileNotFoundError("Run does not exist.")
        latest_review, review_validation = self._review_state(run_id)
        verification = self.verify_run(run_id)
        retained_dataset = read_json(safe_child(path, "data/dataset.json"))
        dataset_metadata = retained_dataset["metadata"]
        research = None
        if verification["ok"] and dataset_metadata.get("identity_research"):
            from .data import load_dataset

            try:
                retained = load_dataset(path / "data")["metadata"]
                if (
                    retained.get("import_transform", {}).get("kind")
                    != "identity_research_v1"
                ):
                    raise ValueError(
                        "Public identity context has no retained derivation."
                    )
                research = retained["identity_research"]
            except (ValueError, OSError, KeyError, TypeError) as exc:
                verification = {
                    **verification,
                    "ok": False,
                    "issues": [
                        *verification["issues"],
                        "Identity research validation failed: " + str(exc),
                    ],
                }
        entity_names = {}
        screening_source = None
        if verification["ok"]:
            entity_names = {
                entity["entity_id"]: entity["name"]
                for entity in retained_dataset["tables"]["entities"]
            }
            source_path = safe_child(path, "sources/source.json")
            if source_path.is_file():
                retained_source = read_json(source_path)
                screening_source = {
                    key: value
                    for key, value in retained_source["metadata"].items()
                    if key
                    in {
                        "snapshot_id",
                        "source_id",
                        "record_count",
                        "fetched_at",
                        "source_updated_at",
                        "ingestion_method",
                        "effective_date_issue_count",
                    }
                }
        retained_case = read_json(safe_child(path, "case.json"))
        recorded_workflow = (
            retained_case.get("workflow") if verification["ok"] else None
        )
        workflow_state = {
            "status": (
                "recorded"
                if recorded_workflow
                else "not_recorded" if verification["ok"] else "invalid"
            ),
            "records_selected": bool(recorded_workflow),
            "source_accepted": bool(recorded_workflow),
            "plan_approved": bool(recorded_workflow),
            **(recorded_workflow or {}),
        }
        return {
            "workflow": workflow_state,
            "entity_names": entity_names,
            "screening_source": screening_source,
            "manifest": read_json(safe_child(path, "manifest.json")),
            "case": retained_case,
            "analysis": read_json(safe_child(path, "analysis.json")),
            "latest_review": latest_review,
            "review_validation": review_validation,
            "dataset_metadata": {
                key: value
                for key, value in dataset_metadata.items()
                if key in {"synthetic", "label", "dataset_id", "counts"}
            },
            "identity_research": research,
            "latest_export": (
                self._latest_export(run_id, latest_review)
                if verification["ok"] and latest_review
                else None
            ),
            "verification": verification,
        }

    def _latest_export(self, run_id: str, review: dict) -> dict | None:
        """Expose a completed package only while its exact run and review verify."""
        from .evidence import verify_bundle

        pointer = safe_child(self.root / "exports", f"{safe_id(run_id)}-latest.json")
        if not pointer.is_file() or pointer.is_symlink():
            return None
        try:
            saved = read_json(pointer)
            if set(saved) != {"name", "sha256", "review_id", "run_manifest_sha256"}:
                return None
            name = saved["name"]
            if not isinstance(name, str) or not name.endswith(".zip"):
                return None
            safe_id(name[:-4])
            manifest = safe_child(self._path("runs", run_id), "manifest.json")
            if saved["review_id"] != review["review_id"] or saved[
                "run_manifest_sha256"
            ] != sha256_file(manifest):
                return None
            archive_path = safe_child(self.root / "exports", name)
            if (
                archive_path.is_symlink()
                or not archive_path.is_file()
                or sha256_file(archive_path) != saved["sha256"]
            ):
                return None
            if not verify_bundle(archive_path)["ok"]:
                return None
            with zipfile.ZipFile(archive_path) as archive:
                exported = json.loads(archive.read("review.json"))
                if any(
                    exported[key] != review[key]
                    for key in ("review_id", "review", "run_manifest_sha256")
                ):
                    return None
                if archive.read("run/manifest.json") != manifest.read_bytes():
                    return None
            return {"name": name, "download_url": f"/api/exports/{name}"}
        except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile):
            return None

    def verify_run(self, run_id: str) -> dict[str, Any]:
        from .evidence import verify_run

        return verify_run(self._path("runs", run_id))

    def save_review(self, run_id: str, review_dict: dict[str, Any]) -> dict[str, Any]:
        from .evidence import validate_review

        path = self._path("runs", run_id)
        verification = self.verify_run(run_id)
        if not verification["ok"]:
            raise OmphalOSError(
                "A damaged or incomplete run cannot be reviewed for export."
            )
        review = parse_review(review_dict).model_dump(mode="json")
        if review["run_id"] != run_id:
            raise OmphalOSError("Review refers to a different run.")
        assessment = validate_review(path, review)
        if not assessment["ok"]:
            raise OmphalOSError(
                "Review is incomplete: " + "; ".join(assessment["issues"])
            )
        previous, previous_validation = self._review_state(run_id)
        if previous is None and previous_validation.get("status") != "awaiting_review":
            raise OmphalOSError(
                "Stored review history could not be validated: "
                + "; ".join(previous_validation["issues"])
            )
        recorded_at = _review_timestamp(utc_now())
        if previous:
            # Web and browser mutations are serialized. A logical timestamp
            # preserves their saved revision order if the wall clock repeats or
            # moves backward, without changing existing review wrappers.
            prior_timestamp = _review_timestamp(previous["created_at"])
            if recorded_at <= prior_timestamp:
                try:
                    recorded_at = prior_timestamp + timedelta(microseconds=1)
                except OverflowError as exc:
                    raise OmphalOSError(
                        "Stored review timestamp leaves no room for a new revision."
                    ) from exc
        review_id = "review-" + uuid.uuid4().hex
        wrapper = {
            "review_id": review_id,
            "created_at": recorded_at.isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            ),
            "run_manifest_sha256": sha256_file(path / "manifest.json"),
            "review": review,
        }
        review_path = safe_child(self._path("reviews", run_id), f"{review_id}.json")
        write_json(review_path, wrapper)
        self._event(
            "review_recorded",
            run_id,
            review_id=review_id,
            review_sha256=sha256_file(review_path),
        )
        return {**wrapper, "path": str(review_path), "sha256": sha256_file(review_path)}

    def export_run(
        self, run_id: str, *, review_id: str | None = None
    ) -> dict[str, Any]:
        from .evidence import export_bundle

        if review_id:
            review_path = safe_child(
                self._path("reviews", run_id), f"{safe_id(review_id)}.json"
            )
        else:
            latest = self._latest_review(run_id)
            if not latest:
                raise OmphalOSError("Complete a named analyst review before exporting.")
            review_path = Path(latest["path"])
        destination = safe_child(
            self.root, f"exports/{safe_id(run_id)}-{uuid.uuid4().hex[:12]}.zip"
        )
        result = export_bundle(self._path("runs", run_id), review_path, destination)
        exported_review = read_json(review_path)
        current_review = self._latest_review(run_id)
        if (
            current_review
            and current_review["review_id"] == exported_review["review_id"]
        ):
            write_json(
                safe_child(self.root / "exports", f"{safe_id(run_id)}-latest.json"),
                {
                    "name": destination.name,
                    "sha256": sha256_file(destination),
                    "review_id": exported_review["review_id"],
                    "run_manifest_sha256": exported_review["run_manifest_sha256"],
                },
            )
        self._event(
            "bundle_exported",
            run_id,
            name=destination.name,
            sha256=sha256_file(destination),
        )
        return {
            **result,
            "path": str(destination),
            "name": destination.name,
            "sha256": sha256_file(destination),
        }

    def replay_run(self, run_id: str) -> dict[str, Any]:
        try:
            assert_process_environment()
        except OmphalOSError as exc:
            return {"ok": False, "issues": [str(exc)], "code_match": False}
        from .data import load_dataset
        from .investigations import analyze
        from .sources import load_source

        verification = self.verify_run(run_id)
        if not verification["ok"]:
            return {
                "ok": False,
                "issues": ["Run integrity must pass before replay."],
                "verification": verification,
            }
        path = self._path("runs", run_id)
        environment = read_json(path / "environment.json")
        issues: list[str] = []
        if environment["engine_files"] != engine_inventory():
            issues.append(
                "Installed analysis code differs from the archived engine. Restore the recorded version before replay."
            )
        if environment["python"] != platform.python_version():
            issues.append(
                "Installed Python version differs from the recorded environment."
            )
        if environment["dependencies"] != runtime_versions():
            issues.append(
                "Installed dependency versions differ from the recorded environment."
            )
        if issues:
            return {
                "ok": False,
                "issues": issues,
                "code_match": not any("code" in issue for issue in issues),
            }
        case = Case.model_validate(read_json(path / "case.json")).model_dump(
            mode="json"
        )
        dataset = load_dataset(path / "data")
        watchlist = (
            load_source(path / "sources") if case["watchlist_snapshot_id"] else None
        )
        analysis = _analysis(analyze(dataset, case, watchlist), case)
        actual = sha256_bytes(canonical_json(analysis))
        expected = read_json(path / "manifest.json")["analysis_digest"]
        return {
            "ok": actual == expected,
            "issues": (
                []
                if actual == expected
                else ["Recomputed analysis differs from the archived result."]
            ),
            "expected_digest": expected,
            "actual_digest": actual,
            "code_match": True,
            "meaning": (
                "Normalized findings and coverage reproduced; execution timestamps are intentionally different."
                if actual == expected
                else "Replay completed, but its findings or coverage did not reproduce the archived analysis."
            ),
        }

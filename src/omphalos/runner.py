"""Workspace orchestration with retained inputs, real analysis, and review gates."""

from __future__ import annotations

import importlib.metadata
import logging
import platform
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from . import __version__
from .models import Analysis, Case, Review
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
    return {name: importlib.metadata.version(name) for name in names}


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


class Workspace:
    """Single-user local workspace; every run and review gets a unique identity."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in (
            "datasets",
            "sources",
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
                records.append(
                    {
                        **{
                            key: metadata[key]
                            for key in (
                                "label",
                                "synthetic",
                                "counts",
                                "warnings",
                                "field_coverage",
                                "source_files",
                            )
                            if key in metadata
                        },
                        "dataset_id": path.name,
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

    def list_runs(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(safe_child(self.root, "runs").iterdir(), reverse=True):
            if not path.is_dir() or path.is_symlink() or path.name.startswith("."):
                continue
            try:
                manifest = read_json(safe_child(path, "manifest.json"))
                analysis = read_json(safe_child(path, "analysis.json"))
                review, review_validation = self._review_state(path.name)
                records.append(
                    {
                        "run_id": path.name,
                        "case_id": manifest["case_id"],
                        "created_at": manifest["created_at"],
                        "analysis_digest": manifest["analysis_digest"],
                        "findings_count": len(analysis["findings"]),
                        "not_evaluable_count": sum(
                            row["status"] == "not_evaluable"
                            for row in analysis["coverage"]
                        ),
                        "status": "reviewed" if review else "awaiting_review",
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
        self, run_id: str
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
                    candidates.append({**wrapper, "path": str(path)})
            if not candidates:
                return None, {"ok": False, "issues": [], "status": "awaiting_review"}
            latest = max(
                candidates, key=lambda row: (row["created_at"], row["review_id"])
            )
            assessment = validate_review(self._path("runs", run_id), latest["review"])
            return (latest if assessment["ok"] else None), assessment
        except (ValueError, OSError, KeyError, TypeError) as exc:
            return None, {
                "ok": False,
                "issues": ["Stored review could not be validated: " + str(exc)],
            }

    def _latest_review(self, run_id: str) -> dict[str, Any] | None:
        return self._review_state(run_id)[0]

    def get_run(self, run_id: str) -> dict[str, Any]:
        path = self._path("runs", run_id)
        if not path.is_dir():
            raise FileNotFoundError("Run does not exist.")
        latest_review, review_validation = self._review_state(run_id)
        return {
            "manifest": read_json(safe_child(path, "manifest.json")),
            "case": read_json(safe_child(path, "case.json")),
            "analysis": read_json(safe_child(path, "analysis.json")),
            "latest_review": latest_review,
            "review_validation": review_validation,
            "dataset_metadata": {
                key: value
                for key, value in read_json(safe_child(path, "data/dataset.json"))[
                    "metadata"
                ].items()
                if key in {"synthetic", "label", "dataset_id", "counts"}
            },
            "verification": self.verify_run(run_id),
        }

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
        review = Review.model_validate(review_dict).model_dump(mode="json")
        if review["run_id"] != run_id:
            raise OmphalOSError("Review refers to a different run.")
        assessment = validate_review(path, review)
        if not assessment["ok"]:
            raise OmphalOSError(
                "Review is incomplete: " + "; ".join(assessment["issues"])
            )
        review_id = "review-" + uuid.uuid4().hex
        wrapper = {
            "review_id": review_id,
            "created_at": utc_now(),
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

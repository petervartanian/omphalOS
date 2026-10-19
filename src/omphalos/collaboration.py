"""Portable case handoffs without overwriting or trusting another workspace.

A package is retained as immutable evidence. Continuation snapshots have new local
identities and no inherited workflow approvals. Receipt signatures and key trust
are handled separately; package integrity never establishes sender identity.
"""

from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .data import load_dataset
from .evidence import HASH_RE, MAX_FILES, _json_bytes, _paths, verify_bundle
from .investigations import catalog
from .models import Case
from .runner import Workspace
from .sources import load_source
from .util import (
    OmphalOSError,
    canonical_json,
    read_json,
    safe_child,
    safe_id,
    sha256_bytes,
    sha256_file,
    utc_now,
)

MAX_HANDOFF_BYTES = 48 * 1024 * 1024
MAX_HANDOFF_EXPANDED = 128 * 1024 * 1024


class HandoffConflict(OmphalOSError):
    """Local work differs; receiving a handoff must not silently replace it."""


def _package_contents(raw: bytes) -> tuple[dict[str, bytes], dict[str, Any]]:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_HANDOFF_BYTES:
        raise OmphalOSError("Choose an evidence package ZIP no larger than 48 MiB.")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if (
            not entries
            or len(entries) > MAX_FILES + 1
            or sum(item.file_size for item in entries) > MAX_HANDOFF_EXPANDED
            or any(
                item.file_size > MAX_HANDOFF_EXPANDED
                or item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                for item in entries
            )
        ):
            raise OmphalOSError(
                "The handoff exceeds the supported ZIP or 128 MiB expanded limits."
            )
        # The established verifier rejects aliases, duplicate keys, traversal,
        # symlinks, unknown inventory entries, altered bytes, and invalid reviews.
        with tempfile.TemporaryDirectory(prefix="omphalos-package-") as temporary:
            package = Path(temporary) / "package.zip"
            package.write_bytes(raw)
            verification = verify_bundle(package)
        if not verification["ok"]:
            raise OmphalOSError(
                "Evidence package validation failed: "
                + "; ".join(verification["issues"])
            )
        content = {item.filename: archive.read(item) for item in entries}
    case = _json_bytes(content["run/case.json"])
    analysis = _json_bytes(content["run/analysis.json"])
    manifest = _json_bytes(content["run/manifest.json"])
    wrapper = _json_bytes(content["review.json"])
    dataset = _json_bytes(content["run/data/dataset.json"])
    review = wrapper["review"]
    return content, {
        "package_sha256": sha256_bytes(raw),
        "run_id": manifest["run_id"],
        "analysis_digest": manifest["analysis_digest"],
        "run_manifest_sha256": sha256_bytes(content["run/manifest.json"]),
        "review_id": wrapper["review_id"],
        "case_id": case["case_id"],
        "case_title": case["question"],
        "analyst": review["reviewer"],
        "decision": review.get("decision"),
        "counts": dataset["metadata"]["counts"],
        "dataset_label": dataset["metadata"].get("label", ""),
        "findings_count": len(analysis["findings"]),
        "verification": verification,
    }


def _package(raw: bytes) -> tuple[dict[str, bytes], dict[str, Any]]:
    try:
        return _package_contents(raw)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise OmphalOSError(
            "The selected file is not a supported evidence package ZIP."
        ) from exc


def inspect_package(raw: bytes) -> dict[str, Any]:
    """Inspect original ZIP bytes without storing cases or trusting the sender."""
    return _package(raw)[1]


def _tree_bytes(directory: Path) -> dict[str, bytes]:
    return {name: path.read_bytes() for name, path in _paths(directory).items()}


def _write_tree(directory: Path, files: dict[str, bytes]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for relative, raw in files.items():
        target = safe_child(directory, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)


def _same_target(target: Path, payload: bytes | dict[str, bytes]) -> bool:
    if target.is_symlink():
        raise HandoffConflict("A local handoff destination is a symbolic link.")
    if not target.exists():
        return False
    same = (
        target.is_file() and target.read_bytes() == payload
        if isinstance(payload, bytes)
        else target.is_dir() and _tree_bytes(target) == payload
    )
    if not same:
        raise HandoffConflict(
            "This handoff conflicts with retained local work. Nothing was replaced."
        )
    return True


def _publish(target: Path, payload: bytes | dict[str, bytes]) -> None:
    """Publish under the workspace mutation lock, only to absent destinations."""
    if target.exists() or target.is_symlink():
        raise HandoffConflict("The handoff destination changed. Nothing was replaced.")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".handoff-", dir=target.parent))
    try:
        staged = stage / "item"
        if isinstance(payload, bytes):
            staged.write_bytes(payload)
        else:
            _write_tree(staged, payload)
        # Native and browser request handlers serialize workspace mutations.
        # A second check also prevents accidental replacement by direct callers.
        if target.exists() or target.is_symlink():
            raise HandoffConflict(
                "The handoff destination changed. Nothing was replaced."
            )
        staged.rename(target)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _continuation_record(event: Any, digest: str, run_id: str) -> dict[str, Any]:
    local_id = "handoff-" + digest
    if (
        not isinstance(event, dict)
        or set(event)
        not in (
            {"at", "action", "resource_id", "package_sha256", "continuation"},
            {
                "at",
                "action",
                "resource_id",
                "package_sha256",
                "continuation",
                "dataset_label",
            },
        )
        or event["action"] != "case_handoff_imported"
        or event["resource_id"] != run_id
        or event["package_sha256"] != digest
    ):
        raise HandoffConflict("The retained handoff record is inconsistent.")
    value = event["continuation"]
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "continuation_case_id",
            "continuation_dataset_id",
            "continuation_source_id",
            "unsupported_checks",
            "download_url",
        }
        or value["continuation_dataset_id"] != local_id
        or value["continuation_case_id"] not in {None, local_id}
        or value["continuation_source_id"] not in {None, local_id}
        or value["download_url"] != "/api/exports/" + local_id + ".zip"
        or not isinstance(value["unsupported_checks"], list)
        or any(not isinstance(item, str) for item in value["unsupported_checks"])
    ):
        raise HandoffConflict("The retained handoff continuation is inconsistent.")
    return value


def handoff_labels(workspace: Workspace) -> dict[str, str]:
    """Read optional display labels without opening or verifying any run evidence.

    Labels are local inventory metadata, not verified claims about retained data.
    Older handoffs without this convenience field remain supported.
    """
    labels = {}
    for marker in sorted((workspace.root / "events").glob("handoff-*.json")):
        try:
            digest = marker.stem.removeprefix("handoff-")
            if not HASH_RE.fullmatch(digest) or marker.is_symlink():
                continue
            event = read_json(marker)
            if not isinstance(event, dict):
                continue
            run_id = safe_id(event.get("resource_id"))
            _continuation_record(event, digest, run_id)
            label = event.get("dataset_label", "")
            if isinstance(label, str) and 0 < len(label) <= 1000:
                labels[run_id] = label
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return labels


def handoff_for_run(workspace: Workspace, run_id: str) -> dict[str, Any] | None:
    """Resolve a retained handoff to its exact ZIP and usable local input copy.

    This describes the origin of imported work, not a sender or reviewer identity.
    It remains an origin link when a later local assessment supersedes the import.
    """
    candidates = []
    for marker in sorted((workspace.root / "events").glob("handoff-*.json")):
        try:
            digest = marker.stem.removeprefix("handoff-")
            if not HASH_RE.fullmatch(digest) or marker.is_symlink():
                continue
            event = read_json(marker)
            if not isinstance(event, dict) or event.get("resource_id") != run_id:
                continue
            continuation = _continuation_record(event, digest, run_id)
            package = safe_child(workspace.root, "exports/handoff-" + digest + ".zip")
            if not package.is_file() or sha256_file(package) != digest:
                continue
            with zipfile.ZipFile(package) as archive:
                retained_manifest = archive.read("run/manifest.json")
            current_manifest = safe_child(
                workspace.root, f"runs/{run_id}/manifest.json"
            ).read_bytes()
            if retained_manifest != current_manifest:
                continue
            dataset = safe_child(
                workspace.root, "datasets/" + continuation["continuation_dataset_id"]
            )
            if (
                load_dataset(dataset)["metadata"]["dataset_id"]
                != continuation["continuation_dataset_id"]
            ):
                continue
            if continuation["continuation_source_id"]:
                copied_source = safe_child(
                    workspace.root, "sources/" + continuation["continuation_source_id"]
                )
                if (
                    load_source(copied_source)["snapshot_id"]
                    != continuation["continuation_source_id"]
                ):
                    continue
            if continuation["continuation_case_id"]:
                copied_case = workspace.get_case(continuation["continuation_case_id"])
                if copied_case["dataset_id"] != continuation["continuation_dataset_id"]:
                    continue
            candidates.append({"package_sha256": digest, **continuation})
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
            continue
    if not candidates:
        return None
    pointer_path = safe_child(workspace.root, f"exports/{run_id}-latest.json")
    try:
        current_digest = read_json(pointer_path).get("sha256")
    except (OSError, ValueError, TypeError, AttributeError):
        current_digest = None
    return next(
        (row for row in candidates if row["package_sha256"] == current_digest),
        candidates[0],
    )


def import_package(
    workspace: Workspace, raw: bytes, *, expected_sha256: str
) -> dict[str, Any]:
    """Retain and continue an inspected package without merging divergent work."""
    content, summary = _package(raw)
    digest = summary["package_sha256"]
    if expected_sha256 != digest:
        raise HandoffConflict(
            "The selected package changed. Inspect it again before opening."
        )
    run_id = summary["run_id"]
    local_id = "handoff-" + digest
    case = _json_bytes(content["run/case.json"])
    run_files = {
        name.removeprefix("run/"): data
        for name, data in content.items()
        if name.startswith("run/")
    }
    original_wrapper = _json_bytes(content["review.json"])
    run_path = safe_child(workspace.root, "runs/" + run_id)
    marker = safe_child(workspace.root, "events/" + local_id + ".json")
    package_name = local_id + ".zip"
    package_path = safe_child(workspace.root, "exports/" + package_name)
    _same_target(run_path, run_files)
    _same_target(package_path, raw)
    if marker.exists():
        saved = read_json(marker)
        continuation = _continuation_record(saved, digest, run_id)
        if not run_path.exists() or not package_path.exists():
            raise HandoffConflict(
                "The retained handoff is incomplete. Local work was preserved."
            )
        review_path = safe_child(
            workspace.root, f"reviews/{run_id}/{summary['review_id']}.json"
        )
        if not _same_target(review_path, content["review.json"]):
            raise HandoffConflict("The retained handoff assessment is missing.")
        if not handoff_for_run(workspace, run_id):
            raise HandoffConflict(
                "The retained handoff continuation could not be verified. Local work was preserved."
            )
        return {**summary, **continuation, "imported": False}
    review_directory = safe_child(workspace.root, "reviews/" + run_id)
    if review_directory.exists():
        latest, validation = workspace._review_state(run_id)
        if latest is None and validation.get("status") != "awaiting_review":
            raise HandoffConflict("Stored local assessments could not be validated.")
        if latest is not None and latest["review_id"] != summary["review_id"]:
            raise HandoffConflict(
                "This run has a different local assessment. Keep both packages separately; "
                "receiving a handoff does not replace a local decision."
            )
    pointer = safe_child(workspace.root, f"exports/{run_id}-latest.json")
    if pointer.exists():
        existing_pointer = read_json(pointer)
        if (
            not isinstance(existing_pointer, dict)
            or existing_pointer.get("sha256") != digest
        ):
            raise HandoffConflict(
                "This run already has a different package. The original was kept. "
                "Inspect the incoming ZIP separately; it cannot replace the package used for review."
            )
    data_files = {
        name.removeprefix("data/"): data
        for name, data in run_files.items()
        if name.startswith("data/")
    }
    dataset = _json_bytes(data_files["dataset.json"])
    dataset["metadata"]["dataset_id"] = local_id
    data_files["dataset.json"] = canonical_json(dataset)
    data_manifest = _json_bytes(data_files["dataset-manifest.json"])
    data_manifest["dataset_id"] = local_id
    data_manifest["dataset_sha256"] = sha256_bytes(data_files["dataset.json"])
    data_files["dataset-manifest.json"] = canonical_json(data_manifest)
    source_files = {
        name.removeprefix("sources/"): data
        for name, data in run_files.items()
        if name.startswith("sources/")
    }
    if source_files:
        source = _json_bytes(source_files["source.json"])
        source["snapshot_id"] = local_id
        source["metadata"]["snapshot_id"] = local_id
        source_files["source.json"] = canonical_json(source)
        manifest_name = (
            "source-manifest.json"
            if "source-manifest.json" in source_files
            else "snapshot-manifest.json"
        )
        source_manifest = _json_bytes(source_files[manifest_name])
        source_manifest["snapshot_id"] = local_id
        source_manifest["normalized_sha256"] = sha256_bytes(source_files["source.json"])
        source_files[manifest_name] = canonical_json(source_manifest)
    # Current loaders validate provenance and retained identity derivations, not
    # merely the package's internal checksum inventory. Archived code is never run.
    with tempfile.TemporaryDirectory(prefix="omphalos-continuation-") as temporary:
        validation_root = Path(temporary)
        _write_tree(validation_root / "data", data_files)
        load_dataset(validation_root / "data")
        if source_files:
            _write_tree(validation_root / "sources", source_files)
            load_source(validation_root / "sources")
    supported = {row["id"] for row in catalog()}
    unsupported = sorted(set(case["investigations"]) - supported)
    continued = {
        **case,
        "schema_version": "2.0",
        "case_id": local_id,
        "dataset_id": local_id,
        "watchlist_snapshot_id": local_id if source_files else None,
    }
    continued.pop("workflow", None)
    # An older package remains inspectable even if its checks were retired. New
    # work requires a fresh current plan; do not silently drop archived checks.
    continuation_case = (
        None if unsupported else Case.model_validate(continued).model_dump(mode="json")
    )
    continuation = {
        "continuation_case_id": local_id if continuation_case else None,
        "continuation_dataset_id": local_id,
        "continuation_source_id": local_id if source_files else None,
        "unsupported_checks": unsupported,
        "download_url": "/api/exports/" + package_name,
    }
    targets: list[tuple[Path, bytes | dict[str, bytes]]] = [
        (run_path, run_files),
        (
            safe_child(workspace.root, f"reviews/{run_id}/{summary['review_id']}.json"),
            content["review.json"],
        ),
        (safe_child(workspace.root, "datasets/" + local_id), data_files),
        (package_path, raw),
    ]
    if source_files:
        targets.append(
            (safe_child(workspace.root, "sources/" + local_id), source_files)
        )
    if continuation_case:
        targets.append(
            (
                safe_child(workspace.root, "cases/" + local_id + ".json"),
                canonical_json(continuation_case),
            )
        )
    # Imported package is current only for this exact retained assessment. Never
    # overwrite an existing export pointer, including a different equivalent ZIP.
    pointer = safe_child(workspace.root, f"exports/{run_id}-latest.json")
    if not pointer.exists():
        targets.append(
            (
                pointer,
                canonical_json(
                    {
                        "name": package_name,
                        "sha256": digest,
                        "review_id": original_wrapper["review_id"],
                        "run_manifest_sha256": original_wrapper["run_manifest_sha256"],
                    }
                ),
            )
        )
    pending = [
        (path, payload) for path, payload in targets if not _same_target(path, payload)
    ]
    published: list[Path] = []
    try:
        for path, payload in pending:
            _publish(path, payload)
            published.append(path)
        event = {
            "at": utc_now(),
            "action": "case_handoff_imported",
            "resource_id": run_id,
            "package_sha256": digest,
            "continuation": continuation,
            "dataset_label": summary["dataset_label"],
        }
        _publish(marker, canonical_json(event))
        published.append(marker)
    except Exception:
        for path in reversed(published):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        raise
    return {**summary, **continuation, "imported": True}

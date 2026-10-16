"""Complete file inventories, explicit review gates, and portable evidence bundles.

Integrity is a comparison with a manifest, never a claim of authenticated origin.
The version 2.0 JSON encoding is defined by util.canonical_json, not RFC 8785.
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import stat
import sys
import tempfile
import zipfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .models import Analysis, Case, CaseReview, Review, parse_review
from .util import (
    OmphalOSError,
    canonical_json,
    read_json,
    safe_id,
    sha256_bytes,
    sha256_file,
    utc_now,
)

MANDATORY_FILES = frozenset(
    {
        "case.json",
        "data/dataset.json",
        "analysis.json",
        "catalog.json",
        "environment.json",
    }
)
MAX_FILES = 20_000
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_JSON_BYTES = 128 * 1024 * 1024
MANIFEST_NAME = "manifest.json"
BUNDLE_MANIFEST = "bundle-manifest.json"
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
TABLE_IDS = {
    "entities": "entity_id",
    "shipments": "shipment_id",
    "payments": "payment_id",
    "ownership": "relationship_id",
    "diligence": "evidence_id",
}
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"""(?i)["']?\b(?:password|token|api[_-]?key|access[_-]?token|secret[_-]?key)["']?\s*[:=]\s*["']?[^\s"',;}{]{8,}"""
)
_CREDENTIAL_KEYS = re.compile(
    r"password|token|api[_-]?key|access[_-]?token|secret[_-]?key", re.IGNORECASE
)
_SECRET_PATTERNS = (
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")),
    (
        "credential_assignment",
        _CREDENTIAL_ASSIGNMENT,
    ),
)
_SOURCE_REFERENCES: OrderedDict[str, frozenset[tuple[str, str, str]]] = OrderedDict()
_SCAN_RESULTS: OrderedDict[tuple, tuple[str, ...]] = OrderedDict()


def _json_bytes(data: bytes, *, limit: int = MAX_JSON_BYTES) -> Any:
    if len(data) > limit:
        raise OmphalOSError("JSON exceeds the configured size limit.")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise OmphalOSError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise OmphalOSError(f"Non-finite JSON value: {value}")

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise OmphalOSError("JSON number exceeds finite floating-point range.")
        return parsed

    return json.loads(
        data.decode("utf-8"),
        object_pairs_hook=pairs,
        parse_constant=constant,
        parse_float=finite_float,
    )


def _portable_numbers(value: Any) -> None:
    """Integer JSON numbers and decimal strings make native replay unambiguous."""
    if isinstance(value, float):
        raise OmphalOSError(
            "Analysis decimals must be strings, not JSON floating-point numbers."
        )
    if type(value) is int and not -(2**63) <= value < 2**63:
        raise OmphalOSError(
            "Analysis integers outside signed 64-bit range must be strings."
        )
    if isinstance(value, dict):
        for item in value.values():
            _portable_numbers(item)
    elif isinstance(value, list):
        for item in value:
            _portable_numbers(item)


def _relative(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise OmphalOSError("Invalid artifact path.")
    if (
        PurePosixPath(value).is_absolute()
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 for character in value)
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise OmphalOSError(f"Unsafe artifact path: {value!r}")
    # Cross-platform inventories must not alias on common case-insensitive systems.
    for part in value.split("/"):
        if part.endswith((" ", ".")) or part.split(".")[0].upper() in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }:
            raise OmphalOSError(f"Nonportable artifact path: {value!r}")
    return value


def _paths(root: Path, *, exclude: frozenset[str] = frozenset()) -> dict[str, Path]:
    if root.is_symlink() or not root.is_dir():
        raise OmphalOSError("Evidence root must be an existing regular directory.")
    found: dict[str, Path] = {}
    aliases: set[str] = set()
    total = 0
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise OmphalOSError("Symbolic links are not evidence artifacts.")
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise OmphalOSError("Only regular files are evidence artifacts.")
        relative = _relative(path.relative_to(root).as_posix())
        alias = relative.casefold()
        if alias in aliases:
            raise OmphalOSError(
                "Artifact paths must be unique across supported platforms."
            )
        aliases.add(alias)
        size = path.stat().st_size
        total += size
        if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise OmphalOSError("Evidence exceeds the configured size limits.")
        if relative not in exclude:
            found[relative] = path
        if len(found) > MAX_FILES:
            raise OmphalOSError("Evidence has too many files.")
    return found


def _entry(path: str, content: bytes) -> dict[str, Any]:
    return {"path": path, "sha256": sha256_bytes(content), "size_bytes": len(content)}


def _entries(manifest: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(manifest, dict):
        raise OmphalOSError("Manifest must be an object.")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_FILES:
        raise OmphalOSError("Manifest requires a nonempty bounded file inventory.")
    result: dict[str, dict[str, Any]] = {}
    aliases: set[str] = set()
    total = 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "path",
            "sha256",
            "size_bytes",
        }:
            raise OmphalOSError(
                "Every inventory entry requires exactly path, sha256, size_bytes."
            )
        path = _relative(entry["path"])
        if path.casefold() in aliases:
            raise OmphalOSError(f"Duplicate artifact path: {path}")
        aliases.add(path.casefold())
        digest, size = entry["sha256"], entry["size_bytes"]
        if not isinstance(digest, str) or not HASH_RE.fullmatch(digest):
            raise OmphalOSError(f"Invalid SHA-256 digest: {path}")
        if type(size) is not int or size < 0 or size > MAX_FILE_BYTES:
            raise OmphalOSError(f"Invalid artifact size: {path}")
        total += size
        if total > MAX_TOTAL_BYTES:
            raise OmphalOSError("Inventory exceeds total size limit.")
        result[path] = entry
    return result


def _run_manifest(manifest: Any) -> dict[str, dict[str, Any]]:
    fields = {
        "schema_version",
        "run_id",
        "case_id",
        "created_at",
        "analysis_digest",
        "files",
    }
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise OmphalOSError("Run manifest has missing or unknown fields.")
    if manifest["schema_version"] != "2.0":
        raise OmphalOSError("Unsupported manifest schema version.")
    safe_id(manifest["run_id"])
    safe_id(manifest["case_id"])
    if not isinstance(manifest["created_at"], str) or not manifest[
        "created_at"
    ].endswith("Z"):
        raise OmphalOSError("Manifest timestamp must be UTC with Z.")
    datetime.fromisoformat(manifest["created_at"].replace("Z", "+00:00"))
    digest = manifest["analysis_digest"]
    if not isinstance(digest, str) or not HASH_RE.fullmatch(digest):
        raise OmphalOSError("Invalid analysis digest.")
    entries = _entries(manifest)
    if MANIFEST_NAME in entries:
        raise OmphalOSError("Manifest cannot inventory itself.")
    missing = MANDATORY_FILES - entries.keys()
    if missing:
        raise OmphalOSError(
            f"Missing mandatory inventory files: {', '.join(sorted(missing))}"
        )
    if not any(path.startswith("engine/") for path in entries):
        raise OmphalOSError("A nonempty engine source snapshot is required.")
    return entries


def _semantic_issues(contents: dict[str, bytes], manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    analysis = _json_bytes(contents["analysis.json"])
    _portable_numbers(analysis)
    Analysis.model_validate(analysis)
    if sha256_bytes(canonical_json(analysis)) != manifest["analysis_digest"]:
        issues.append("analysis_digest differs from the actual normalized analysis")
    case = Case.model_validate(_json_bytes(contents["case.json"]))
    if case.case_id != manifest["case_id"]:
        issues.append("case_id differs between manifest and case")
    selected = set(case.investigations)
    if selected != {row["investigation_id"] for row in analysis["coverage"]}:
        issues.append(
            "analysis coverage does not exactly match selected investigations"
        )
    return issues


def build_manifest(
    run_dir: Path, *, run_id: str, case_id: str, analysis_digest: str
) -> dict:
    """Finalize once. An existing manifest is never overwritten."""
    root = Path(run_dir)
    if (root / MANIFEST_NAME).exists():
        raise OmphalOSError("This run is already finalized.")
    paths = _paths(root)
    manifest = {
        "schema_version": "2.0",
        "run_id": safe_id(run_id),
        "case_id": safe_id(case_id),
        "created_at": utc_now(),
        "analysis_digest": analysis_digest,
        "files": [
            {
                "path": path,
                "sha256": sha256_file(file),
                "size_bytes": file.stat().st_size,
            }
            for path, file in paths.items()
        ],
    }
    _run_manifest(manifest)
    issues = _semantic_issues(
        {name: paths[name].read_bytes() for name in ("case.json", "analysis.json")},
        manifest,
    )
    if issues:
        raise OmphalOSError("; ".join(issues))
    # Exclusive creation makes finalization write-once even if two callers race.
    with (root / MANIFEST_NAME).open("xb") as handle:
        handle.write(canonical_json(manifest))
        handle.flush()
        os.fsync(handle.fileno())
    result = verify_run(root)
    if not result["ok"]:
        raise OmphalOSError(
            "Finalized run failed verification: " + "; ".join(result["issues"])
        )
    return manifest


def verify_run(run_dir: Path) -> dict:
    """Check a complete inventory and actual analysis content without executing code."""
    issues: list[str] = []
    checked = 0
    digest: str | None = None
    try:
        root = Path(run_dir)
        paths = _paths(root)
        if MANIFEST_NAME not in paths:
            raise OmphalOSError("manifest.json is missing.")
        manifest = _json_bytes(paths.pop(MANIFEST_NAME).read_bytes())
        entries = _run_manifest(manifest)
        digest = manifest["analysis_digest"]
        for path in sorted(entries.keys() - paths.keys()):
            issues.append(f"missing artifact: {path}")
        for path in sorted(paths.keys() - entries.keys()):
            issues.append(f"unlisted artifact: {path}")
        for path in sorted(entries.keys() & paths.keys()):
            file, entry = paths[path], entries[path]
            checked += 1
            if file.stat().st_size != entry["size_bytes"]:
                issues.append(f"size mismatch: {path}")
            if sha256_file(file) != entry["sha256"]:
                issues.append(f"checksum mismatch: {path}")
        if not issues:
            issues.extend(
                _semantic_issues(
                    {
                        name: paths[name].read_bytes()
                        for name in ("case.json", "analysis.json")
                    },
                    manifest,
                )
            )
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        issues.append(str(exc))
    return {
        "ok": not issues,
        "issues": issues,
        "files_checked": checked,
        "analysis_digest": digest,
        "authenticity": "not_assessed",
    }


def _review_issues(contents: dict[str, bytes], review: dict, run_id: str) -> list[str]:
    parsed = parse_review(review)
    issues: list[str] = []
    if parsed.run_id != run_id:
        issues.append("Review refers to a different run.")
    analysis = Analysis.model_validate(_json_bytes(contents["analysis.json"]))
    finding_ids = {finding.finding_id for finding in analysis.findings}
    case_review = isinstance(parsed, CaseReview)
    review_ids = (
        set(parsed.scope_finding_ids)
        if case_review
        else {finding.finding_id for finding in parsed.findings}
    )
    if finding_ids - review_ids:
        issues.append(
            (
                "Findings omitted from assessment scope: "
                if case_review
                else "Unreviewed findings: "
            )
            + ", ".join(sorted(finding_ids - review_ids))
        )
    if review_ids - finding_ids:
        issues.append(
            (
                "Unknown findings in assessment scope: "
                if case_review
                else "Unknown reviewed findings: "
            )
            + ", ".join(sorted(review_ids - finding_ids))
        )
    dataset = _json_bytes(contents["data/dataset.json"])
    tables = dataset.get("tables", {})
    references: dict[str, set[str]] = {
        table: {str(row.get(TABLE_IDS.get(table, "id"), "")) for row in rows}
        for table, rows in tables.items()
        if isinstance(rows, list)
    }
    source_references: set[tuple[str, str, str]] = set()
    for path, content in contents.items():
        if path.startswith("sources/") and path.endswith("source.json"):
            digest = sha256_bytes(content)
            references_for_source = _SOURCE_REFERENCES.get(digest)
            if references_for_source is None:
                source = _json_bytes(content)
                references_for_source = frozenset(
                    (source["snapshot_id"], source["source_id"], entry["record_id"])
                    for entry in source.get("entries", [])
                )
                _SOURCE_REFERENCES[digest] = references_for_source
                while len(_SOURCE_REFERENCES) > 4:
                    _SOURCE_REFERENCES.popitem(last=False)
            source_references.update(references_for_source)
    for finding in analysis.findings:
        for reference in finding.record_refs:
            if reference.record_id not in references.get(reference.table, set()):
                issues.append(
                    f"Unresolved evidence: {finding.finding_id} / {reference.table}:{reference.record_id}"
                )
        for reference in finding.source_refs:
            value = (
                reference.model_dump()
                if hasattr(reference, "model_dump")
                else reference
            )
            if (
                not isinstance(value, dict)
                or (
                    value.get("snapshot_id"),
                    value.get("source_id"),
                    value.get("record_id"),
                )
                not in source_references
            ):
                issues.append(f"Unresolved source evidence: {finding.finding_id}")
    by_id = {finding.finding_id: finding for finding in analysis.findings}
    for reviewed in parsed.findings if isinstance(parsed, Review) else []:
        original = by_id.get(reviewed.finding_id)
        if original and all(
            getattr(reviewed, field) == getattr(original, field)
            for field in ("unknowns", "alternatives", "falsifiers")
        ):
            issues.append(
                f"Review must assess the finding rather than copy all generated scaffolding: {reviewed.finding_id}"
            )
    return issues


def validate_review(run_dir: Path, review: dict) -> dict:
    verification = verify_run(run_dir)
    if not verification["ok"]:
        return {
            "ok": False,
            "issues": ["Run integrity failed.", *verification["issues"]],
        }
    try:
        paths = _paths(Path(run_dir))
        manifest = _json_bytes(paths[MANIFEST_NAME].read_bytes())
        needed = {
            name: file.read_bytes()
            for name, file in paths.items()
            if name in {"analysis.json", "data/dataset.json"}
            or (name.startswith("sources/") and name.endswith("source.json"))
        }
        issues = _review_issues(needed, review, manifest["run_id"])
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        issues = [str(exc)]
    return {"ok": not issues, "issues": issues, "identity": "self_asserted"}


def _reports(
    case: dict, analysis: dict, wrapper: dict, verification: dict
) -> tuple[bytes, bytes]:
    review = wrapper["review"]
    case_review = review.get("schema_version") == "2.1"

    def escape(value: Any) -> str:
        return html.escape(str(value), quote=True)

    if case_review:
        decision = {
            "keep_open": "Keep investigation open",
            "escalate": "Escalate investigation",
            "conclude": "Conclude investigation",
        }[review["decision"]]
        assessment_blocks = [
            f"<h2>Case decision</h2><p>{escape(decision)}</p>",
            "<p>This decision covers the retained investigation. The scope includes "
            f"{len(review['scope_finding_ids'])} observations; no individual "
            "dispositions are recorded by this case decision.</p>",
        ]
        assessment_lines = [
            "## Case decision",
            "",
            escape(decision),
            "",
            "This decision covers the retained investigation. The scope includes "
            f"{len(review['scope_finding_ids'])} observations; no individual "
            "dispositions are recorded by this case decision.",
            "",
        ]
        if review.get("summary"):
            assessment_blocks.append(
                f"<h3>Case note</h3><p>{escape(review['summary'])}</p>"
            )
            assessment_lines.extend(
                ["### Case note", "", escape(review["summary"]), ""]
            )
    else:
        assessment_blocks = [
            f"<h2>Review summary</h2><p>{escape(review['summary'])}</p>"
        ]
        assessment_lines = ["## Review summary", "", escape(review["summary"]), ""]

    blocks = [
        "<!doctype html><html lang='en'><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>omphalOS evidence record</title><style>body{font:16px/1.6 system-ui;max-width:1000px;margin:3rem auto;padding:0 1.5rem;color:#152b3c}h1,h2{line-height:1.2}article{border-top:1px solid #cad6df;margin-top:2rem;padding-top:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:1rem}dt{font-weight:700}dd{margin-bottom:.8rem}</style>",
        f"<h1>Evidence record: {escape(case['case_id'])}</h1><p>{escape(case['question'])}</p>",
        f"<p>Run: {escape(review['run_id'])}<br>Review: {escape(wrapper['review_id'])}<br>Reviewer: {escape(review['reviewer'])} (self-asserted identity)</p>",
        f"<p>File integrity checked at export: {verification['files_checked']} files. Publisher identity was not assessed. Analytical conclusions remain subject to review.</p>",
        *assessment_blocks,
        "<h2>Coverage and limitations</h2><pre>"
        + escape(json.dumps(analysis["coverage"], indent=2, ensure_ascii=False))
        + "</pre>",
        "<h2>Warnings</h2><pre>"
        + escape(json.dumps(analysis.get("warnings", []), indent=2, ensure_ascii=False))
        + "</pre>",
    ]
    lines = [
        f"# Evidence record: {escape(case['case_id'])}",
        "",
        escape(case["question"]),
        "",
        f"Run: {escape(review['run_id'])}",
        f"Review: {escape(wrapper['review_id'])}",
        f"Reviewer: {escape(review['reviewer'])} (self-asserted identity)",
        "",
        f"File integrity checked at export: {verification['files_checked']} files. Publisher identity was not assessed.",
        "",
        *assessment_lines,
        "## Coverage",
        "",
        "<pre>"
        + escape(json.dumps(analysis["coverage"], indent=2, ensure_ascii=False))
        + "</pre>",
    ]
    if case_review:
        context = (
            "The observations, unknowns, alternative explanations, and evidence "
            "requests below are the engine's retained analytical output. They "
            "are not statements authored or individually adopted by the reviewer."
        )
        blocks.append(f"<h2>Retained analysis</h2><p>{escape(context)}</p>")
        lines.extend(
            [
                "",
                "## Warnings",
                "",
                "<pre>"
                + escape(json.dumps(analysis.get("warnings", []), indent=2))
                + "</pre>",
                "",
                "## Retained analysis",
                "",
                escape(context),
            ]
        )
    reviews = {row["finding_id"]: row for row in review.get("findings", [])}
    for finding in analysis["findings"]:
        blocks.append(
            f"<article><h2>{escape(finding['title'])}</h2><p>{escape(finding['observation'])}</p><dl>"
        )
        lines.extend(
            ["", f"## {escape(finding['title'])}", "", escape(finding["observation"])]
        )
        sections = [
            ("Evidence references", finding["record_refs"]),
            ("Source references", finding.get("source_refs", [])),
            ("Metrics", finding["metrics"]),
        ]
        if case_review:
            sections = [
                ("Finding ID", finding["finding_id"]),
                ("Check", finding["investigation_id"]),
                ("Entities", finding.get("entity_ids", [])),
                *sections,
                ("Analysis: unknowns", finding["unknowns"]),
                ("Analysis: alternative explanations", finding["alternatives"]),
                (
                    "Analysis: evidence that could change the result",
                    finding["falsifiers"],
                ),
            ]
        else:
            adjudication = reviews[finding["finding_id"]]
            sections.extend(
                [
                    ("Disposition", adjudication["disposition"]),
                    ("Reasoning", adjudication["rationale"]),
                    ("Unknowns", adjudication["unknowns"]),
                    ("Alternatives", adjudication["alternatives"]),
                    ("Falsifiers", adjudication["falsifiers"]),
                ]
            )
        for label, value in sections:
            text = (
                value
                if isinstance(value, str)
                else json.dumps(value, indent=2, ensure_ascii=False)
            )
            blocks.append(f"<dt>{escape(label)}</dt><dd><pre>{escape(text)}</pre></dd>")
            lines.extend(["", f"### {label}", "", "<pre>" + escape(text) + "</pre>"])
        blocks.append("</dl></article>")
    blocks.append(
        "<p>All referenced artifacts are included in the run directory. See README.txt for verification and replay instructions.</p></html>"
    )
    return "\n".join(blocks).encode("utf-8"), ("\n".join(lines) + "\n").encode("utf-8")


def _credential_assignment_present(text: str) -> bool:
    """Locate key candidates, then apply the complete original detection rule."""
    position = 0
    while candidate := _CREDENTIAL_KEYS.search(text, position):
        # A leading quote is optional in the full rule. Starting at its key keeps
        # the original Unicode boundary, case matching, and value requirements.
        if _CREDENTIAL_ASSIGNMENT.match(text, candidate.start()):
            return True
        # A rejected outer key may contain a valid overlapping key, for example
        # "naccess-token=...". Advancing to its end would miss the inner token.
        position = candidate.start() + 1
    return False


def _scan(path: str, content: bytes) -> list[str]:
    # Scan user data, metadata, and reports, not archived implementation strings.
    if "/engine/" in "/" + path or Path(path).suffix.lower() not in {
        ".json",
        ".csv",
        ".txt",
        ".md",
        ".html",
        ".xml",
        ".yaml",
        ".yml",
    }:
        return []
    # These immutable results are keyed by actual bytes and the active scanner.
    # Rechecking a package never trusts a timestamp or a prior artifact path.
    key = (
        sha256_bytes(content),
        tuple(
            (label, pattern.pattern, pattern.flags)
            for label, pattern in _SECRET_PATTERNS
        ),
    )
    matches = _SCAN_RESULTS.get(key)
    if matches is None:
        text = content.decode("utf-8", errors="replace")
        matches = tuple(
            label
            for label, pattern in _SECRET_PATTERNS
            if (
                _credential_assignment_present(text)
                if pattern is _CREDENTIAL_ASSIGNMENT
                else pattern.search(text)
            )
        )
        _SCAN_RESULTS[key] = matches
        while len(_SCAN_RESULTS) > 64:
            _SCAN_RESULTS.popitem(last=False)
    return [f"Credential pattern {label} in {path}" for label in matches]


def _review_wrapper(wrapper: Any, manifest_bytes: bytes) -> dict:
    expected = {"review_id", "created_at", "run_manifest_sha256", "review"}
    if not isinstance(wrapper, dict) or set(wrapper) != expected:
        raise OmphalOSError("Review requires a versioned immutable review wrapper.")
    safe_id(wrapper["review_id"])
    if not isinstance(wrapper["created_at"], str) or not wrapper["created_at"].endswith(
        "Z"
    ):
        raise OmphalOSError("Review timestamp must be UTC with Z.")
    datetime.fromisoformat(wrapper["created_at"].replace("Z", "+00:00"))
    if wrapper["run_manifest_sha256"] != sha256_bytes(manifest_bytes):
        raise OmphalOSError("Review was not made against this exact run manifest.")
    return wrapper


def export_bundle(run_dir: Path, review_path: Path, dest: Path) -> dict:
    if Path(review_path).is_symlink():
        raise OmphalOSError("Stored reviews must be regular files, not symbolic links.")
    verification = verify_run(run_dir)
    if not verification["ok"]:
        raise OmphalOSError(
            "Run integrity failed: " + "; ".join(verification["issues"])
        )
    root = Path(run_dir)
    paths = _paths(root)
    contents = {name: path.read_bytes() for name, path in paths.items()}
    manifest = _json_bytes(contents[MANIFEST_NAME])
    entries = _run_manifest(manifest)
    for name, entry in entries.items():
        if _entry(name, contents[name]) != entry:
            raise OmphalOSError("Run changed while preparing export.")
    wrapper = _review_wrapper(read_json(review_path), contents[MANIFEST_NAME])
    issues = _review_issues(contents, wrapper["review"], manifest["run_id"])
    if issues:
        raise OmphalOSError("Review incomplete: " + "; ".join(issues))
    report_html, report_md = _reports(
        _json_bytes(contents["case.json"]),
        _json_bytes(contents["analysis.json"]),
        wrapper,
        verification,
    )
    payload = {"run/" + name: content for name, content in contents.items()}
    payload.update(
        {
            "review.json": canonical_json(wrapper),
            "report.html": report_html,
            "report.md": report_md,
            "README.txt": b"omphalOS evidence bundle format 2.0\n\nThis ZIP uses the documented omphalOS inventory format, not BagIt or RO-Crate.\nVerify with: omphalos verify PATH.zip\nVerification checks inventory and bytes; it does not authenticate a publisher or establish analytical truth.\nReview identity is self-asserted. The archived engine is evidence and is never executed by verification.\nReplay uses the installed compatible omphalOS engine and the archived case/data/source snapshots; consult the installed CLI help for replay.\nOpen report.html locally for the human-readable record. All computational evidence is under run/.\n",
        }
    )
    scan_issues = [
        issue for name, content in payload.items() for issue in _scan(name, content)
    ]
    if scan_issues:
        raise OmphalOSError("Export credential scan failed: " + "; ".join(scan_issues))
    bundle = {
        "schema_version": "2.0",
        "kind": "omphalos-evidence-bundle",
        "run_id": manifest["run_id"],
        "analysis_digest": manifest["analysis_digest"],
        "created_at": utc_now(),
        "files": [_entry(name, payload[name]) for name in sorted(payload)],
    }
    _entries(bundle)
    payload[BUNDLE_MANIFEST] = canonical_json(bundle)
    destination = Path(dest)
    if destination.exists() and destination.is_dir():
        destination = destination / f"{manifest['run_id']}-{wrapper['review_id']}.zip"
    if destination.suffix.lower() != ".zip":
        raise OmphalOSError(
            "Export destination must be a ZIP file or existing directory."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".bundle-", suffix=".zip", delete=False
        ) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            for name in sorted(payload):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(info, payload[name])
        result = verify_bundle(temporary)
        if not result["ok"]:
            raise OmphalOSError(
                "Export validation failed: " + "; ".join(result["issues"])
            )
        _publish_export(temporary, destination)
        return {
            "path": str(destination),
            "name": destination.name,
            "digest": sha256_file(destination),
            "run_id": manifest["run_id"],
            "review_id": wrapper["review_id"],
            "verification": result,
        }
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def _publish_export(temporary: Path, destination: Path) -> None:
    if sys.platform == "emscripten":
        # MEMFS has no hard links. The browser worker owns this filesystem and
        # serializes operations under a cross-tab Web Lock. A checked rename
        # publishes the completed ZIP without exposing a partially written file.
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("An evidence package already uses this name.")
        temporary.rename(destination)
    else:
        # Native publication atomically refuses to replace an existing export.
        os.link(temporary, destination)


def verify_bundle(path: Path) -> dict:
    """Bounded verification in memory; archive members are never extracted."""
    issues: list[str] = []
    checked = 0
    try:
        if Path(path).stat().st_size > MAX_TOTAL_BYTES:
            raise OmphalOSError("Archive exceeds compressed size limit.")
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_FILES + 1:
                raise OmphalOSError("Archive has an invalid member count.")
            content: dict[str, bytes] = {}
            aliases: set[str] = set()
            total = 0
            for info in infos:
                name = _relative(info.filename)
                if name.casefold() in aliases:
                    raise OmphalOSError(f"Duplicate archive member: {name}")
                aliases.add(name.casefold())
                mode = (info.external_attr >> 16) & 0xFFFF
                if (
                    info.is_dir()
                    or stat.S_ISLNK(mode)
                    or (stat.S_IFMT(mode) not in {0, stat.S_IFREG})
                ):
                    raise OmphalOSError("Archive members must be regular files.")
                if info.flag_bits & 1:
                    raise OmphalOSError("Encrypted archive members are unsupported.")
                total += info.file_size
                if info.file_size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                    raise OmphalOSError("Archive exceeds uncompressed size limits.")
                with archive.open(info) as member:
                    data = member.read(min(MAX_FILE_BYTES, info.file_size) + 1)
                if len(data) != info.file_size:
                    raise OmphalOSError(f"Archive size mismatch: {name}")
                content[name] = data
            if BUNDLE_MANIFEST not in content:
                raise OmphalOSError("Bundle manifest is missing.")
            bundle = _json_bytes(content.pop(BUNDLE_MANIFEST))
            expected_fields = {
                "schema_version",
                "kind",
                "run_id",
                "analysis_digest",
                "created_at",
                "files",
            }
            if (
                set(bundle) != expected_fields
                or bundle["schema_version"] != "2.0"
                or bundle["kind"] != "omphalos-evidence-bundle"
            ):
                raise OmphalOSError("Unsupported or malformed bundle manifest.")
            entries = _entries(bundle)
            if set(content) != set(entries):
                raise OmphalOSError(
                    "Bundle inventory does not match actual archive files."
                )
            mandatory = {
                "report.html",
                "report.md",
                "review.json",
                "README.txt",
                "run/manifest.json",
            }
            if not mandatory <= set(content):
                raise OmphalOSError("Bundle is missing required evidence or reports.")
            for name, data in content.items():
                checked += 1
                if _entry(name, data) != entries[name]:
                    issues.append(f"Bundle artifact mismatch: {name}")
            if issues:
                return {
                    "ok": False,
                    "issues": issues,
                    "files_checked": checked,
                    "authenticity": "not_assessed",
                }
            run = {
                name[4:]: data
                for name, data in content.items()
                if name.startswith("run/")
            }
            manifest = _json_bytes(run.pop(MANIFEST_NAME))
            run_entries = _run_manifest(manifest)
            if set(run) != set(run_entries):
                raise OmphalOSError(
                    "Embedded run inventory is incomplete or has extra files."
                )
            for name, data in run.items():
                if _entry(name, data) != run_entries[name]:
                    issues.append(f"Embedded run artifact mismatch: {name}")
            if (
                bundle["run_id"] != manifest["run_id"]
                or bundle["analysis_digest"] != manifest["analysis_digest"]
            ):
                issues.append("Bundle and run identities disagree.")
            issues.extend(_semantic_issues(run, manifest))
            wrapper = _review_wrapper(
                _json_bytes(content["review.json"]), content["run/manifest.json"]
            )
            issues.extend(_review_issues(run, wrapper["review"], manifest["run_id"]))
            issues.extend(
                issue for name, data in content.items() for issue in _scan(name, data)
            )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        RecursionError,
        zipfile.BadZipFile,
    ) as exc:
        issues.append(str(exc))
    return {
        "ok": not issues,
        "issues": issues,
        "files_checked": checked,
        "authenticity": "not_assessed",
    }


def verify_ed25519_signature(
    artifact: Path, signature: Path, trusted_public_key: Path
) -> dict:
    """Verify an external raw 64-byte signature against an external trusted PEM key.

    The caller supplies the trust decision. A key packaged with the artifact is
    not automatically trusted. No private signing key is read or generated here.
    """
    try:
        from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return {
            "ok": False,
            "status": "unavailable",
            "issues": [
                "Install the project's cryptography dependency to verify Ed25519 signatures."
            ],
        }
    try:
        if (
            artifact.stat().st_size > MAX_TOTAL_BYTES
            or signature.stat().st_size != 64
            or trusted_public_key.stat().st_size > 16384
        ):
            raise OmphalOSError("Invalid signature or artifact size.")
        with trusted_public_key.open("rb") as handle:
            public_key_bytes = handle.read(16385)
        with signature.open("rb") as handle:
            signature_bytes = handle.read(65)
        with artifact.open("rb") as handle:
            artifact_bytes = handle.read(MAX_TOTAL_BYTES + 1)
        if (
            len(public_key_bytes) > 16384
            or len(signature_bytes) != 64
            or len(artifact_bytes) > MAX_TOTAL_BYTES
        ):
            raise OmphalOSError("Invalid signature or artifact size.")
        key = serialization.load_pem_public_key(public_key_bytes)
        if not isinstance(key, Ed25519PublicKey):
            raise OmphalOSError("Trusted public key must be Ed25519.")
        key.verify(signature_bytes, artifact_bytes)
        fingerprint = sha256_bytes(
            key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        )
        return {
            "ok": True,
            "status": "signature_verified_against_supplied_key",
            "key_sha256": fingerprint,
            "artifact_sha256": sha256_bytes(artifact_bytes),
            "issues": [],
        }
    except (OSError, ValueError, InvalidSignature, UnsupportedAlgorithm) as exc:
        return {
            "ok": False,
            "status": "verification_failed",
            "issues": [str(exc) or "Signature does not match the artifact."],
        }

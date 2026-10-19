"""Local, single-user HTTP workbench. No network-facing deployment mode."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import logging
import secrets
import socket
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .data import TABLES, data_schema, import_dataset, load_dataset
from .investigations import catalog
from .models import Case, GuidedApproval, GuidedPreflight, GuidedWorkflow
from .runner import Workspace
from .sources import fetch_source, import_source, load_source, source_catalog
from .util import (
    canonical_json,
    read_json,
    safe_child,
    safe_id,
    sha256_bytes,
    sha256_file,
    utc_now,
)
from .workflow import (
    goal_catalog,
    import_subject,
    import_vendor_csv,
    plan_case,
    preview_vendor_csv,
)

LOG = logging.getLogger(__name__)
MAX_BODY_BYTES = 64 * 1024 * 1024
MAX_UPLOAD_BYTES = 48 * 1024 * 1024
UI_ROOT = Path(__file__).with_name("ui")
STATIC_FILES = {
    "/": "index.html",
    "/app.js": "app.js",
    "/box.js": "box.js",
    "/reviewer.js": "reviewer.js",
    "/styles.css": "styles.css",
    "/geist.woff2": "geist.woff2",
    "/geist-mono.woff2": "geist-mono.woff2",
    "/font-license.txt": "font-license.txt",
    "/logo.svg": "logo.svg",
    "/logo-512.png": "logo-512.png",
    "/apple-touch-icon.png": "apple-touch-icon.png",
    "/favicon.ico": "favicon.ico",
}
STATIC_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/vnd.microsoft.icon",
}


class RequestError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _json_object(pairs: list[tuple[str, Any]]) -> dict:
    value: dict = {}
    for key, item in pairs:
        if key in value:
            raise RequestError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def _fields(value: dict, allowed: set[str], required: set[str] | None = None) -> None:
    unknown = set(value) - allowed
    missing = (required or set()) - set(value)
    if unknown or missing:
        raise RequestError(
            f"Unexpected fields: {', '.join(sorted(unknown)) or 'none'}; "
            f"missing fields: {', '.join(sorted(missing)) or 'none'}."
        )


def _text(value: Any, name: str, maximum: int = 1000) -> str:
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise RequestError(f"{name} must be text of at most {maximum} characters.")
    return value


def _upload_files(value: Any, directory: Path, *, source: bool = False) -> list[Path]:
    if not isinstance(value, list) or not 1 <= len(value) <= (1 if source else 6):
        raise RequestError("Supply one source file, or one to six dataset files.")
    files: list[Path] = []
    total = 0
    for entry in value:
        if not isinstance(entry, dict):
            raise RequestError("Each uploaded file must be an object.")
        _fields(entry, {"name", "content_base64"}, {"name", "content_base64"})
        name = _text(entry["name"], "File name", 120)
        if (
            not name
            or name.startswith(".")
            or any(c in name for c in ("/", "\\", ":"))
            or Path(name).name != name
            or Path(name).suffix.lower()
            not in ({".json", ".xml", ".csv"} if source else {".csv", ".json"})
        ):
            raise RequestError(
                "Use a plain CSV/JSON dataset filename or CSV/JSON/XML source filename."
            )
        path = directory / name
        if path in files:
            raise RequestError(f"Repeated uploaded filename: {name}")
        encoded = entry["content_base64"]
        if not isinstance(encoded, str):
            raise RequestError("File content must use base64 encoding.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise RequestError("Invalid base64 file content.") from exc
        total += len(raw)
        if total > MAX_UPLOAD_BYTES:
            raise RequestError("The combined upload exceeds 48 MiB.", 413)
        path.write_bytes(raw)
        files.append(path)
    return files


def _record_research(metadata: dict, table: str, record_id: str) -> dict | None:
    context = metadata.get("identity_research")
    if table != "entities" or not context:
        return None
    if context["entity_id"] == record_id:
        return context
    return next(
        (
            item
            for item in reversed(context.get("history", []))
            if item["entity_id"] == record_id
        ),
        None,
    )


def _record_evidence(metadata: dict, table: str, record: dict) -> dict[str, Any]:
    """Keep retained record rows and their original provenance together."""
    record_id = record[TABLES[table][1]]
    origin = metadata.get("provenance", {}).get(table, {}).get(record_id)
    return {
        "kind": "record",
        "ref": {"table": table, "record_id": record_id},
        "table": table,
        "id": record_id,
        "record": record,
        "origin": origin,
        "identity_research": _record_research(metadata, table, record_id),
        "source_files": [
            item
            for item in metadata.get("source_files", [])
            if origin and item["path"] == f"originals/{origin['source_file']}"
        ],
        "synthetic": metadata.get("synthetic", False),
    }


def _supporting_records(
    workspace: Workspace, run_id: str, offset: int, limit: int
) -> dict[str, Any]:
    """Page all retained diligence, without inferring relevance or filtering scope."""
    root = safe_child(workspace.root, f"runs/{run_id}")
    if not root.is_dir():
        raise RequestError("Run not found.", 404)
    if not workspace.verify_run(run_id)["ok"]:
        raise RequestError(
            "Run integrity failed. Supporting records cannot be presented as verified.",
            409,
        )
    data = read_json(safe_child(root, "data/dataset.json"))
    if data.get("metadata", {}).get("identity_research"):
        try:
            data = load_dataset(root / "data")
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise RequestError(
                "Retained identity research failed validation.", 409
            ) from exc
    records = data["tables"].get("diligence", [])
    if offset > len(records):
        raise RequestError(
            "Supporting-record offset exceeds the retained record count."
        )
    return {
        "run_id": run_id,
        "table": "diligence",
        "scope": "all_retained_diligence",
        "total": len(records),
        "offset": offset,
        "limit": limit,
        "rows": [
            _record_evidence(data.get("metadata", {}), "diligence", record)
            for record in records[offset : offset + limit]
        ],
    }


def _finding_evidence(
    workspace: Workspace, run_id: str, finding_id: str, offset: int
) -> dict[str, Any]:
    """Resolve one bounded page of citations against a single verified run."""
    root = safe_child(workspace.root, f"runs/{run_id}")
    if not root.is_dir():
        raise RequestError("Run not found.", 404)
    if not workspace.verify_run(run_id)["ok"]:
        raise RequestError(
            "Run integrity failed. Evidence cannot be presented as verified.", 409
        )
    analysis = read_json(safe_child(root, "analysis.json"))
    finding = next(
        (row for row in analysis["findings"] if row["finding_id"] == finding_id),
        None,
    )
    if finding is None:
        raise RequestError("Finding not found in this run.", 404)
    references = [("record", ref) for ref in finding["record_refs"]] + [
        ("source", ref) for ref in finding.get("source_refs", [])
    ]
    if offset > len(references):
        raise RequestError("Evidence offset exceeds the cited record count.")
    page = references[offset : offset + 40]
    data = (
        read_json(safe_child(root, "data/dataset.json"))
        if any(kind == "record" for kind, _ in page)
        else {}
    )
    source: dict = {}
    if any(kind == "source" for kind, _ in page):
        source_path = safe_child(root, "sources/source.json")
        if not source_path.is_file():
            raise RequestError("Cited listing is absent from the retained run.", 409)
        source = read_json(source_path)
    metadata = data.get("metadata", {})
    if metadata.get("identity_research"):
        # Public context comes from a checked derivation, never just a saved label.
        try:
            data = load_dataset(root / "data")
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise RequestError(
                "Retained identity research failed validation.", 409
            ) from exc
        metadata = data["metadata"]
    record_tables = {ref["table"] for kind, ref in page if kind == "record"}
    records = {
        table: {row[TABLES[table][1]]: row for row in data["tables"].get(table, [])}
        for table in record_tables
        if table in TABLES
    }
    listings = {row["record_id"]: row for row in source.get("entries", [])}
    rows: list[dict[str, Any]] = []
    for kind, ref in page:
        record_id = ref["record_id"]
        if kind == "record":
            table = ref["table"]
            record = records.get(table, {}).get(record_id)
            if record is None:
                raise RequestError("Cited record is absent from the retained run.", 409)
            rows.append(_record_evidence(metadata, table, record))
        else:
            record = listings.get(record_id)
            if record is None or any(
                source.get(key) != ref[key] for key in ("source_id", "snapshot_id")
            ):
                raise RequestError(
                    "Cited listing is absent from the retained run.", 409
                )
            rows.append(
                {
                    "kind": kind,
                    "ref": ref,
                    "table": "source",
                    "id": record_id,
                    "record": record,
                    "metadata": source["metadata"],
                    "source_id": source["source_id"],
                    "snapshot_id": source["snapshot_id"],
                }
            )
    return {
        "run_id": run_id,
        "finding_id": finding_id,
        "total": len(references),
        "offset": offset,
        "limit": 40,
        "rows": rows,
    }


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, workspace: Path, host: str, port: int):
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                "The workbench binds only to 127.0.0.1, localhost, or ::1."
            )
        if (
            not isinstance(port, int)
            or isinstance(port, bool)
            or not 0 <= port <= 65535
        ):
            raise ValueError("Port must be between 0 and 65535.")
        self.workspace = Workspace(Path(workspace))
        self.root = Path(workspace).resolve()
        self.token = secrets.token_urlsafe(32)
        self.workflow_secret = secrets.token_bytes(32)
        # Same-session approved runs may be retried after a dropped response or
        # transient execution failure. Never adopt a pre-existing user case.
        self.guided_runs: dict[str, str] = {}
        self.mutation_lock = threading.RLock()
        host = "127.0.0.1" if host == "localhost" else host
        if host == "::1":
            self.address_family = socket.AF_INET6
        super().__init__((host, port), WorkbenchHandler)
        self.port = self.server_address[1]
        self.authorities = {
            f"127.0.0.1:{self.port}",
            f"localhost:{self.port}",
            f"[::1]:{self.port}",
        }
        self.url = f"http://{'[::1]' if host == '::1' else host}:{self.port}"


class WorkbenchHandler(BaseHTTPRequestHandler):
    server: WorkbenchServer
    server_version = "omphalOS"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, format: str, *args: Any) -> None:
        # Never record upload bodies, query values, tokens, or evidence contents.
        LOG.info(
            "workbench_http",
            extra={
                "method": getattr(self, "command", ""),
                "status": str(args[1]) if len(args) > 1 else "request",
            },
        )

    def _check_request(self, *, mutation: bool = False) -> None:
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or hosts[0] not in self.server.authorities:
            raise RequestError(
                "Unexpected Host header. Open the local workbench URL.", 403
            )
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1 or (origins and origins[0] != f"http://{hosts[0]}"):
            raise RequestError("Cross-origin requests are not allowed.", 403)
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise RequestError("Cross-site requests are not allowed.", 403)
        if mutation:
            if len(origins) != 1:
                raise RequestError(
                    "An exact same-origin Origin header is required.", 403
                )
            tokens = self.headers.get_all("X-Omphalos-Token", [])
            if len(tokens) != 1 or not hmac.compare_digest(
                tokens[0], self.server.token
            ):
                raise RequestError(
                    "Session token is missing or expired. Reload this page.", 403
                )

    def _headers(
        self,
        status: int,
        content_type: str,
        length: int,
        *,
        filename: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        if filename:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
        self.end_headers()

    def _json(self, value: Any, status: int = 200) -> None:
        raw = canonical_json(value)
        self._headers(status, "application/json; charset=utf-8", len(raw))
        self.wfile.write(raw)

    def _body(self) -> dict:
        if self.headers.get_all("Transfer-Encoding"):
            raise RequestError("Transfer-Encoding is unsupported.")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isdigit():
            raise RequestError("A single valid Content-Length is required.", 411)
        length = int(lengths[0])
        if length > MAX_BODY_BYTES:
            raise RequestError("Request exceeds the 64 MiB limit.", 413)
        if self.headers.get_content_type() != "application/json":
            raise RequestError("Use application/json.", 415)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise RequestError("Incomplete request body.")
        try:
            value = json.loads(
                raw,
                object_pairs_hook=_json_object,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    ValueError("Non-finite number")
                ),
            )
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise RequestError(f"Invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise RequestError("The request body must be a JSON object.")
        return value

    def _route(self) -> tuple[list[str], dict[str, list[str]]]:
        if len(self.path) > 4096:
            raise RequestError("Request URL is too long.", 414)
        url = urlsplit(self.path)
        if url.scheme or url.netloc or url.fragment:
            raise RequestError("Only local relative request paths are allowed.")
        path = unquote(url.path, errors="strict")
        if (
            "\\" in path
            or "\x00" in path
            or any(p in {".", ".."} for p in path.split("/"))
        ):
            raise RequestError("Unsafe path.")
        return path.strip("/").split("/"), parse_qs(url.query, max_num_fields=10)

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, RequestError):
            status = exc.status
        elif isinstance(exc, FileNotFoundError):
            status = 404
        elif isinstance(exc, FileExistsError):
            status = 409
        elif isinstance(exc, (ValueError, KeyError, TypeError)):
            status = 400
        else:
            status = 500
            LOG.error(
                "workbench_request_failed", extra={"error_type": type(exc).__name__}
            )
        message = (
            str(exc)
            if status != 500
            else "The operation failed. See the local server log for details."
        )
        self.close_connection = True
        self._json({"error": message, "status": status}, status)

    def do_GET(self) -> None:
        try:
            self._check_request()
            parts, query = self._route()
            path = "/" + "/".join(parts) if parts != [""] else "/"
            if path in STATIC_FILES:
                raw = (UI_ROOT / STATIC_FILES[path]).read_bytes()
                content_type = STATIC_CONTENT_TYPES[Path(STATIC_FILES[path]).suffix]
                self._headers(200, content_type, len(raw))
                self.wfile.write(raw)
            elif parts == ["api", "state"]:
                ws = self.server.workspace
                dataset_fields = {
                    "dataset_id",
                    "label",
                    "intake_method",
                    "identity_research_retained",
                    "identity_profile",
                    "parent_dataset_id",
                    "identity_association",
                    "synthetic",
                    "counts",
                    "warnings",
                    "status",
                    "field_coverage",
                    "source_files",
                }
                self._json(
                    {
                        "token": self.server.token,
                        "datasets": [
                            {
                                key: value
                                for key, value in row.items()
                                if key in dataset_fields
                            }
                            for row in ws.list_datasets()
                        ],
                        "sources": ws.list_sources(),
                        "cases": ws.list_cases(),
                        "runs": ws.list_runs(verify_reviews=False),
                        "catalog": catalog(),
                        "source_catalog": source_catalog(),
                        "data_schema": data_schema(),
                        "workflow_goals": goal_catalog(),
                        "limits": {"upload_bytes": MAX_UPLOAD_BYTES},
                        "mode": "local_single_user",
                    }
                )
            elif len(parts) == 3 and parts[:2] == ["api", "cases"]:
                self._json(self.server.workspace.get_case(safe_id(parts[2])))
            elif len(parts) == 3 and parts[:2] == ["api", "runs"]:
                self._json(self.server.workspace.get_run(safe_id(parts[2])))
            elif (
                len(parts) == 4
                and parts[:2] == ["api", "runs"]
                and parts[3] == "supporting-records"
            ):
                query = parse_qs(
                    urlsplit(self.path).query, keep_blank_values=True, max_num_fields=10
                )
                if set(query) - {"offset", "limit"} or any(
                    len(value) != 1 for value in query.values()
                ):
                    raise RequestError(
                        "Supporting records accept one optional offset and limit."
                    )
                offset = query.get("offset", ["0"])[0]
                limit = query.get("limit", ["40"])[0]
                for value in (offset, limit):
                    if not value.isascii() or not value.isdigit() or len(value) > 10:
                        raise RequestError(
                            "Supporting-record offset and limit must be nonnegative integers."
                        )
                if not 1 <= int(limit) <= 40:
                    raise RequestError(
                        "Supporting-record limit must be between 1 and 40."
                    )
                self._json(
                    _supporting_records(
                        self.server.workspace,
                        safe_id(parts[2]),
                        int(offset),
                        int(limit),
                    )
                )
            elif (
                len(parts) == 4
                and parts[:2] == ["api", "runs"]
                and parts[3] == "finding-evidence"
            ):
                query = parse_qs(
                    urlsplit(self.path).query, keep_blank_values=True, max_num_fields=10
                )
                if not {"finding_id"} <= set(query) <= {"finding_id", "offset"} or any(
                    len(value) != 1 for value in query.values()
                ):
                    raise RequestError(
                        "Finding evidence requires one finding_id and an optional offset."
                    )
                offset = query.get("offset", ["0"])[0]
                if not offset.isascii() or not offset.isdigit() or len(offset) > 10:
                    raise RequestError("Evidence offset must be a nonnegative integer.")
                self._json(
                    _finding_evidence(
                        self.server.workspace,
                        safe_id(parts[2]),
                        safe_id(query["finding_id"][0]),
                        int(offset),
                    )
                )
            elif (
                len(parts) == 4
                and parts[:2] == ["api", "runs"]
                and parts[3] == "source-evidence"
            ):
                if set(query) != {"id"} or len(query["id"]) != 1:
                    raise RequestError("Source evidence requires one record id.")
                run_id = safe_id(parts[2])
                record_id = _text(query["id"][0], "Source record identifier", 10000)
                root = safe_child(self.server.root, f"runs/{run_id}")
                if not root.is_dir():
                    raise RequestError("Run not found.", 404)
                if not self.server.workspace.verify_run(run_id)["ok"]:
                    raise RequestError(
                        "Run integrity failed. Source evidence cannot be presented as verified.",
                        409,
                    )
                if not read_json(safe_child(root, "case.json")).get(
                    "watchlist_snapshot_id"
                ):
                    raise RequestError("This run has no screening snapshot.", 404)
                source = read_json(safe_child(root, "sources/source.json"))
                record = next(
                    (row for row in source["entries"] if row["record_id"] == record_id),
                    None,
                )
                if record is None:
                    raise RequestError(
                        "Source record not found in this run's snapshot.", 404
                    )
                self._json(
                    {
                        "record": record,
                        "metadata": source["metadata"],
                        "snapshot_id": source["snapshot_id"],
                        "run_id": run_id,
                    }
                )
            elif (
                len(parts) == 4
                and parts[:2] == ["api", "runs"]
                and parts[3] == "evidence"
            ):
                if set(query) != {"table", "id"} or any(
                    len(v) != 1 for v in query.values()
                ):
                    raise RequestError("Evidence requires one table and one id.")
                run_id, table, record_id = (
                    safe_id(parts[2]),
                    query["table"][0],
                    safe_id(query["id"][0]),
                )
                if table not in TABLES:
                    raise RequestError("Unknown evidence table.")
                root = safe_child(self.server.root, f"runs/{run_id}")
                if not root.is_dir():
                    raise RequestError("Run not found.", 404)
                if not self.server.workspace.verify_run(run_id)["ok"]:
                    raise RequestError(
                        "Run integrity failed. Evidence cannot be presented as verified.",
                        409,
                    )
                data = read_json(safe_child(root, "data/dataset.json"))
                if data.get("metadata", {}).get("identity_research"):
                    try:
                        data = load_dataset(root / "data")
                    except (ValueError, OSError, KeyError, TypeError) as exc:
                        raise RequestError(
                            "Retained identity research failed validation.", 409
                        ) from exc
                key = TABLES[table][1]
                record = next(
                    (r for r in data["tables"].get(table, []) if r[key] == record_id),
                    None,
                )
                if record is None:
                    raise RequestError(
                        "Record not found in this run's archived dataset.", 404
                    )
                metadata = data.get("metadata", {})
                origin = metadata.get("provenance", {}).get(table, {}).get(record_id)
                originals = metadata.get("source_files", [])
                source = [
                    r
                    for r in originals
                    if origin and r["path"] == f"originals/{origin['source_file']}"
                ]
                self._json(
                    {
                        "run_id": run_id,
                        "table": table,
                        "record": record,
                        "origin": origin,
                        "identity_research": _record_research(
                            metadata, table, record_id
                        ),
                        "source_files": source,
                        "synthetic": metadata.get("synthetic", False),
                    }
                )
            elif len(parts) == 3 and parts[:2] == ["api", "exports"]:
                name = parts[2]
                if not name.endswith(".zip"):
                    raise RequestError("Only generated ZIP exports can be downloaded.")
                safe_id(name[:-4])
                target = safe_child(self.server.root / "exports", name)
                if target.is_symlink() or not target.is_file():
                    raise FileNotFoundError("Export not found.")
                self._headers(
                    200, "application/zip", target.stat().st_size, filename=name
                )
                with target.open("rb") as handle:
                    while chunk := handle.read(128 * 1024):
                        self.wfile.write(chunk)
            else:
                raise RequestError("Route not found.", 404)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            self._handle_error(exc)

    def do_POST(self) -> None:
        try:
            self._check_request(mutation=True)
            parts, query = self._route()
            if query:
                raise RequestError("POST routes do not accept query parameters.")
            body = self._body()
            with self.server.mutation_lock:
                result = self._mutate(parts, body)
            self._json(result)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            self._handle_error(exc)

    def _destination(self, group: str, requested: Any, prefix: str) -> Path:
        identifier = safe_id(
            _text(requested or f"{prefix}_{secrets.token_hex(6)}", "Identifier", 80)
        )
        destination = safe_child(self.server.root / group, identifier)
        if destination.exists():
            raise FileExistsError(
                f"{identifier} already exists. Choose a new identifier."
            )
        return destination

    def _mutate(self, parts: list[str], body: dict) -> dict:
        ws = self.server.workspace
        if parts in (["api", "handoffs", "inspect"], ["api", "handoffs", "import"]):
            from .collaboration import HandoffConflict, import_package, inspect_package

            importing = parts[-1] == "import"
            _fields(
                body,
                {"file", "expected_sha256"} if importing else {"file"},
                {"file", "expected_sha256"} if importing else {"file"},
            )
            file = body["file"]
            if not isinstance(file, dict):
                raise RequestError("Choose an omphalOS evidence package ZIP.")
            _fields(file, {"name", "content_base64"}, {"name", "content_base64"})
            name = _text(file["name"], "File name", 120)
            if not name.lower().endswith(".zip"):
                raise RequestError("Choose an omphalOS evidence package ZIP.")
            encoded = file["content_base64"]
            if not isinstance(encoded, str) or len(encoded) > 4 * (
                (MAX_UPLOAD_BYTES + 2) // 3
            ):
                raise RequestError("The handoff exceeds 48 MiB.", 413)
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise RequestError("Invalid base64 file content.") from exc
            try:
                if importing:
                    return import_package(
                        ws,
                        raw,
                        expected_sha256=_text(
                            body["expected_sha256"], "Package digest", 64
                        ),
                    )
                return inspect_package(raw)
            except HandoffConflict as exc:
                raise RequestError(str(exc), 409) from exc
        if len(parts) == 3 and parts[:2] == ["api", "workflow"]:
            return self._workflow(parts[2], body)
        if parts == ["api", "datasets", "import"]:
            _fields(body, {"dataset_id", "label", "files"}, {"files"})
            dest = self._destination("datasets", body.get("dataset_id"), "dataset")
            label = _text(body.get("label", ""), "Label")
            with tempfile.TemporaryDirectory(prefix="omphalos-upload-") as temporary:
                _upload_files(body["files"], Path(temporary))
                return import_dataset(
                    Path(temporary), dest, label=label, synthetic=False
                )
        if parts in (["api", "sources", "fetch"], ["api", "sources", "import"]):
            manual = parts[-1] == "import"
            _fields(
                body,
                (
                    {"source_id", "snapshot_id", "files"}
                    if manual
                    else {"source_id", "snapshot_id"}
                ),
                {"source_id", "files"} if manual else {"source_id"},
            )
            source_id = safe_id(_text(body["source_id"], "Source identifier", 80))
            dest = self._destination("sources", body.get("snapshot_id"), source_id)
            if manual:
                with tempfile.TemporaryDirectory(
                    prefix="omphalos-source-"
                ) as temporary:
                    files = _upload_files(body["files"], Path(temporary), source=True)
                    return import_source(source_id, files[0], dest)
            return fetch_source(source_id, dest)
        if parts == ["api", "cases"]:
            return ws.save_case(body)
        if len(parts) == 4 and parts[:2] == ["api", "cases"] and parts[3] == "run":
            _fields(body, set())
            return ws.run_case(safe_id(parts[2]))
        if len(parts) == 4 and parts[:2] == ["api", "runs"]:
            run_id, action = safe_id(parts[2]), parts[3]
            if action == "review":
                return ws.save_review(run_id, body)
            if action in {"verify", "replay"}:
                _fields(body, set())
                return (
                    ws.verify_run(run_id)
                    if action == "verify"
                    else ws.replay_run(run_id)
                )
            if action == "export":
                _fields(body, {"review_id"})
                review_id = body.get("review_id")
                if review_id is not None:
                    review_id = safe_id(_text(review_id, "Review identifier", 80))
                result = ws.export_run(run_id, review_id=review_id)
                name = Path(result["path"]).name
                safe_id(name.removesuffix(".zip"))
                return {**result, "download_url": f"/api/exports/{name}"}
        raise RequestError("Route not found.", 404)

    def _workflow(self, action: str, body: dict) -> dict:
        """Prepare and execute explicit plans against verified local inputs."""
        if action == "subject":
            _fields(body, {"name"}, {"name"})
            return import_subject(
                body["name"], self._destination("datasets", None, "subject")
            )
        if action in {"identity-research", "identity-select"}:
            from .identity_workflow import research_identity, select_identity

            selecting = action == "identity-select"
            _fields(
                body,
                (
                    {"dataset_id", "research_id", "candidate_id"}
                    if selecting
                    else {"dataset_id", "entity_id"}
                ),
                (
                    {"dataset_id", "research_id", "candidate_id"}
                    if selecting
                    else {"dataset_id"}
                ),
            )
            dataset_id = safe_id(_text(body["dataset_id"], "Dataset identifier", 80))
            dataset_path = safe_child(self.server.root / "datasets", dataset_id)
            if selecting:
                research_id = safe_id(
                    _text(body["research_id"], "Research identifier", 80)
                )
                return select_identity(
                    dataset_path,
                    safe_child(self.server.root / "research", research_id),
                    self._destination("datasets", None, "identity"),
                    (
                        _text(body["candidate_id"], "Candidate identifier", 200)
                        if body["candidate_id"] is not None
                        else None
                    ),
                )
            entity_id = body.get("entity_id")
            if entity_id is not None:
                entity_id = safe_id(_text(entity_id, "Entity identifier", 80))
            return research_identity(
                dataset_path,
                self._destination("research", None, "research"),
                entity_id,
            )
        if action in {"preview", "import"}:
            importing = action == "import"
            _fields(
                body,
                (
                    {"files", "mapping", "preview_id", "label"}
                    if importing
                    else {"files", "mapping"}
                ),
                {"files", "mapping", "preview_id"} if importing else {"files"},
            )
            with tempfile.TemporaryDirectory(prefix="omphalos-vendors-") as temporary:
                paths = _upload_files(body["files"], Path(temporary))
                if len(paths) != 1 or paths[0].suffix.lower() != ".csv":
                    raise RequestError("Choose one vendor CSV file to preview.")
                mapping = body.get("mapping")
                if (importing or mapping is not None) and not isinstance(mapping, dict):
                    raise RequestError("Column mapping must be an object.")
                if not importing:
                    return preview_vendor_csv(paths[0], mapping=mapping)
                return import_vendor_csv(
                    paths[0],
                    self._destination("datasets", None, "vendors"),
                    mapping=mapping,
                    preview_id=_text(body["preview_id"], "Preview identifier", 128),
                    label=_text(body.get("label", ""), "Label"),
                    synthetic=False,
                )
        if action not in {"plan", "approve", "run"}:
            raise RequestError("Route not found.", 404)
        executing = action == "run"
        approving = action == "approve"
        fields = {"dataset_id", "goal_id", "as_of", "watchlist_snapshot_id"}
        required = {"dataset_id", "goal_id", "as_of"}
        if executing or approving:
            fields |= {"plan_id", "case_id"}
            required |= {"plan_id", "case_id"}
        if approving:
            fields |= {"acknowledge_records", "acknowledge_source"}
            required |= {"acknowledge_records", "acknowledge_source"}
        if executing:
            fields |= {"approval", "acknowledge_plan"}
            required |= {"approval", "acknowledge_plan"}
        _fields(body, fields, required)
        dataset_id = safe_id(_text(body["dataset_id"], "Dataset identifier", 80))
        dataset_path = safe_child(self.server.root / "datasets", dataset_id)
        dataset = load_dataset(dataset_path)
        snapshot_id = body.get("watchlist_snapshot_id")
        snapshot = None
        snapshot_path = None
        if snapshot_id is not None:
            snapshot_id = safe_id(_text(snapshot_id, "Snapshot identifier", 80))
            snapshot_path = safe_child(self.server.root / "sources", snapshot_id)
            snapshot = load_source(snapshot_path)
        case_id = (
            safe_id(_text(body["case_id"], "Case identifier", 80))
            if executing or approving
            else None
        )
        plan = plan_case(
            dataset,
            _text(body["goal_id"], "Goal identifier", 80),
            as_of=_text(body["as_of"], "Analysis date", 10),
            snapshot=snapshot,
            case_id=case_id,
        )
        binding = {
            "schema": "omphalos-guided-plan-v1",
            "plan": plan,
            "dataset_sha256": sha256_file(safe_child(dataset_path, "dataset.json")),
            "source_sha256": (
                sha256_file(safe_child(snapshot_path, "source.json"))
                if snapshot_path is not None and plan["case"]["watchlist_snapshot_id"]
                else None
            ),
        }
        plan_id = hmac.digest(
            self.server.workflow_secret, canonical_json(binding), "sha256"
        ).hex()
        if not (executing or approving):
            return {**plan, "plan_id": plan_id}
        supplied_id = _text(body["plan_id"], "Plan identifier", 128)
        if not hmac.compare_digest(plan_id, supplied_id):
            raise RequestError(
                "The plan or its inputs changed. Prepare a new plan before running.",
                409,
            )
        expected_preflight = {
            "schema_version": "1.0",
            "plan_id": plan_id,
            "case_sha256": sha256_bytes(canonical_json(plan["case"])),
            "dataset_id": dataset_id,
            "dataset_sha256": binding["dataset_sha256"],
            "source_snapshot_id": plan["case"]["watchlist_snapshot_id"],
            "source_sha256": binding["source_sha256"],
            "records_selected": True,
            "source_accepted": True,
        }
        if approving:
            if (
                plan["source_status"]["required"]
                and not plan["source_status"]["selected"]
            ):
                raise RequestError(
                    "Retain the required screening source before accepting it."
                )
            if (
                body["acknowledge_records"] is not True
                or body["acknowledge_source"] is not True
            ):
                raise RequestError(
                    "Confirm the selected records and source choices before continuing."
                )
            receipt = GuidedPreflight.model_validate(
                {**expected_preflight, "source_accepted_at": utc_now()}
            ).model_dump(mode="json")
            signature = hmac.digest(
                self.server.workflow_secret,
                canonical_json(
                    {"kind": "omphalos-source-approval-v1", "approval": receipt}
                ),
                "sha256",
            ).hex()
            return {"approval": {**receipt, "signature": signature}}
        if not plan["can_run"]:
            raise RequestError("Complete the missing plan requirements before running.")
        if body["acknowledge_plan"] is not True:
            raise RequestError("Review the plan and explicitly authorize execution.")
        approval = GuidedApproval.model_validate(body["approval"]).model_dump(
            mode="json"
        )
        signature = approval.pop("signature")
        expected_signature = hmac.digest(
            self.server.workflow_secret,
            canonical_json(
                {"kind": "omphalos-source-approval-v1", "approval": approval}
            ),
            "sha256",
        ).hex()
        if not hmac.compare_digest(signature, expected_signature) or any(
            approval[key] != value for key, value in expected_preflight.items()
        ):
            raise RequestError(
                "The source approval or plan changed. Review the current sources and plan again.",
                409,
            )
        ws = self.server.workspace
        case_path = safe_child(self.server.root / "cases", f"{case_id}.json")
        if case_path.exists():
            saved = ws.get_case(case_id)
            workflow = saved.get("workflow")
            proposed = {key: value for key, value in saved.items() if key != "workflow"}
            proposed["schema_version"] = "2.0"
            if (
                self.server.guided_runs.get(case_id) != supplied_id
                or proposed != plan["case"]
                or not workflow
                or any(workflow.get(key) != value for key, value in approval.items())
            ):
                raise RequestError(
                    "This case already exists or changed. Prepare a new plan to run again.",
                    409,
                )
            recovered = self._completed_guided_run(saved, binding)
            if recovered is not None:
                return recovered
        else:
            workflow = GuidedWorkflow.model_validate(
                {**approval, "plan_approved": True, "plan_approved_at": utc_now()}
            ).model_dump(mode="json")
            recorded_case = Case.model_validate(
                {**plan["case"], "schema_version": "2.1", "workflow": workflow}
            ).model_dump(mode="json")
            self.server.guided_runs[case_id] = supplied_id
            ws.save_case(recorded_case)
        return ws.run_case(case_id)

    def _completed_guided_run(self, case: dict, binding: dict) -> dict | None:
        """Recover an exact retained result after a response or event-write failure."""
        ws = self.server.workspace
        for directory in sorted((self.server.root / "runs").iterdir()):
            if (
                not directory.is_dir()
                or directory.is_symlink()
                or directory.name.startswith(".")
            ):
                continue
            try:
                retained_case = read_json(safe_child(directory, "case.json"))
            except (ValueError, OSError):
                continue
            if retained_case != case:
                continue
            verification = ws.verify_run(directory.name)
            if not verification["ok"]:
                raise RequestError(
                    "The saved result for this plan failed integrity verification. Open the retained investigation to inspect it.",
                    409,
                )
            environment = read_json(safe_child(directory, "environment.json"))
            inputs = environment["computation_inputs"]
            if (
                inputs["dataset_sha256"] != binding["dataset_sha256"]
                or inputs["source_files"].get("source.json") != binding["source_sha256"]
            ):
                raise RequestError(
                    "The saved result uses different inputs. Prepare a new plan to run again.",
                    409,
                )
            manifest = read_json(safe_child(directory, "manifest.json"))
            if manifest["run_id"] != directory.name:
                raise RequestError(
                    "The saved result identifier differs from its directory.", 409
                )
            analysis = read_json(safe_child(directory, "analysis.json"))
            return {
                "run_id": manifest["run_id"],
                "case_id": case["case_id"],
                "path": str(directory),
                "findings_count": len(analysis["findings"]),
                "analysis_digest": manifest["analysis_digest"],
                "status": (
                    "reviewed"
                    if ws._latest_review(directory.name)
                    else "awaiting_review"
                ),
                "verification": verification,
                "reused": True,
            }
        return None


def create_server(
    workspace: Path, host: str = "127.0.0.1", port: int = 8765
) -> WorkbenchServer:
    """Construct without starting; useful for embedded use and service tests."""
    return WorkbenchServer(workspace, host, port)


def serve(
    workspace: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
) -> None:
    """Serve until interrupted. Local access is not multi-user authentication."""
    server = create_server(workspace, host, port)
    print(f"omphalOS local workbench: {server.url}", flush=True)
    if open_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

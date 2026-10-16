"""Request bridge for the unchanged Python engine in a dedicated browser worker.

The worker mounts persistent storage before constructing BrowserApp, serializes
requests (including across tabs), and flushes it after every dispatch, including
errors. Public-provider bytes arrive through its bounded HTTPS transport. There
is no listening socket, shared server, native networking, or remote workspace.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import logging
import os
import secrets
import shutil
import stat
import struct
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import identity_research, sources
from .data import load_dataset
from .evidence import (
    _entries,
    _json_bytes,
    _paths,
    _review_wrapper,
    validate_review,
    verify_bundle,
)
from .identity_workflow import load_bound_research
from .models import Case
from .runner import Workspace
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
from .web import MAX_UPLOAD_BYTES, RequestError, WorkbenchHandler, _json_object

LOG = logging.getLogger(__name__)
Transport = Callable[[str, int, str], Any]
MAX_BACKUP_BYTES = 512 * 1024 * 1024
BACKUP_MANIFEST = "browser-backup.json"
WORKSPACE_GROUPS = frozenset(
    {"datasets", "sources", "research", "cases", "runs", "reviews", "exports", "events"}
)
RESTORE_JOURNAL = "browser-restore.json"


class BrowserState(BaseModel):
    """Local browser continuity, never evidence or an identity assertion."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["1.0"] = "1.0"
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    workflow_secret: str = Field(pattern=r"^[0-9a-f]{64}$")
    guided_runs: dict[str, str] = Field(default_factory=dict)

    @field_validator("guided_runs")
    @classmethod
    def check_approved_plans(cls, value: dict[str, str]) -> dict[str, str]:
        for case_id, plan_id in value.items():
            safe_id(case_id)
            if len(plan_id) != 64 or any(c not in "0123456789abcdef" for c in plan_id):
                raise ValueError("Invalid saved plan authorization.")
        return value


@dataclass
class BrowserContext:
    workspace: Workspace
    root: Path
    token: str
    workflow_secret: bytes
    guided_runs: dict[str, str]
    mutation_lock: contextlib.AbstractContextManager[None]


def _public_result(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _public_result(item)
            for key, item in value.items()
            if not (key == "path" and isinstance(item, str) and os.path.isabs(item))
        }
    if isinstance(value, list):
        return [_public_result(item) for item in value]
    return value


def _plain(value: Any) -> Any:
    """Convert a Pyodide JS proxy without depending on js in native tests."""
    return value.to_py() if callable(getattr(value, "to_py", None)) else value


class BrowserRequest(WorkbenchHandler):
    """Invoke existing route validation and operations without an HTTP server."""

    def __init__(self, app: BrowserApp, path: str, body: dict[str, Any] | None) -> None:
        self.app = app
        self.server = app.context
        self.path = path
        self.command = "POST" if body is not None else "GET"
        self.headers = Message()
        self.parsed_body = body
        self.wfile = io.BytesIO()
        self.response_status = 200
        self.response_body: Any = None
        self.close_connection = True

    def _check_request(self, *, mutation: bool = False) -> None:
        # Only the dedicated same-origin worker can call this in-process bridge.
        parts, _ = self._route()
        if not parts or parts[0] != "api":
            raise RequestError("Route not found.", 404)

    def _body(self) -> dict[str, Any]:
        if not isinstance(self.parsed_body, dict):
            raise RequestError("The request body must be a JSON object.")
        return self.parsed_body

    def send_response(self, code: int, message: str | None = None) -> None:
        self.response_status = code

    def send_header(self, keyword: str, value: Any) -> None:
        return None

    def end_headers(self) -> None:
        return None

    def _json(self, value: Any, status: int = 200) -> None:
        self.response_status = status
        self.response_body = _public_result(value)
        if self.path == "/api/state" and status == 200:
            self.response_body.update(
                mode="browser_local",
                storage={
                    "mode": "browser",
                    "max_upload_bytes": MAX_UPLOAD_BYTES,
                    "description": "Saved in this browser. Download evidence packages to keep a separate copy.",
                },
                capabilities={
                    "network_transport": "browser_https",
                    "source_fetch": ["csl"],
                    "source_import": list(sources.SOURCES),
                    "package_signing": False,
                    "ed25519_signature_verification": importlib.util.find_spec(
                        "cryptography"
                    )
                    is not None,
                },
            )

    def _mutate(self, parts: list[str], body: dict[str, Any]) -> dict[str, Any]:
        if parts == ["api", "sources", "fetch"]:
            from .web import _fields, _text

            _fields(body, {"source_id", "snapshot_id"}, {"source_id"})
            source_id = safe_id(_text(body["source_id"], "Source identifier", 80))
            destination = self._destination(
                "sources", body.get("snapshot_id"), source_id
            )
            return self.app.fetch_source(source_id, destination)
        return super()._mutate(parts, body)

    def execute(self) -> dict[str, Any]:
        if self.command == "GET":
            # Binary exports have their own transfer method, avoiding JSON/base64.
            parts, _ = self._route()
            if parts[:2] == ["api", "exports"]:
                raise RequestError("Use the browser download operation.", 400)
            self.do_GET()
        else:
            self.do_POST()
        return {"status": self.response_status, "body_json": self.response_body}


class BrowserApp:
    """One serialized actor, backed by the worker's persistent filesystem."""

    def __init__(
        self,
        root: Path | str = "/workspace",
        transport: Transport | None = None,
    ) -> None:
        self.root = Path(root)
        if self.root.is_symlink():
            raise ValueError("Browser workspace cannot be a symbolic link.")
        self.root.mkdir(parents=True, exist_ok=True)
        self._recover_restore()
        self.state_path = safe_child(self.root, "browser-state.json")
        if self.state_path.exists():
            state = BrowserState.model_validate(read_json(self.state_path))
        else:
            if any(self.root.iterdir()):
                raise ValueError(
                    "Browser workspace state is missing. Existing records were left unchanged."
                )
            state = BrowserState(
                token=secrets.token_urlsafe(32),
                workflow_secret=secrets.token_hex(32),
            )
            write_json(self.state_path, state.model_dump())
        self.context = BrowserContext(
            workspace=Workspace(self.root),
            root=self.root,
            token=state.token,
            workflow_secret=bytes.fromhex(state.workflow_secret),
            guided_runs=state.guided_runs,
            mutation_lock=contextlib.nullcontext(),
        )
        self.transport = transport
        self.busy = False

    @staticmethod
    def _workspace_path(relative: str) -> None:
        parts = relative.split("/")
        if relative != "browser-state.json" and (
            len(parts) < 2 or parts[0] not in WORKSPACE_GROUPS
        ):
            raise ValueError("Backup contains an unexpected workspace artifact.")

    def backup_bytes(self) -> bytes:
        """Save all work, including unassessed records, without a review gate."""
        if self.busy:
            raise RequestError("Another operation is running.", 409)
        self.busy = True
        try:
            self._ensure_ready()
            self._persist()
            paths = _paths(self.root)
            total = sum(path.stat().st_size for path in paths.values())
            if total > MAX_BACKUP_BYTES:
                raise ValueError("Workspace backup exceeds the 512 MiB expanded limit.")
            for name in paths:
                self._workspace_path(name)
            manifest = {
                "schema_version": "1.0",
                "kind": "omphalos-browser-backup",
                "created_at": utc_now(),
                "files": [
                    {
                        "path": name,
                        "size_bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                    for name, path in paths.items()
                ],
            }
            output = io.BytesIO()
            with zipfile.ZipFile(
                output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as archive:
                archive.writestr(BACKUP_MANIFEST, canonical_json(manifest))
                for name, path in paths.items():
                    archive.write(path, "workspace/" + name)
            raw = output.getvalue()
            if len(raw) > MAX_BACKUP_BYTES:
                raise ValueError("Workspace backup exceeds the 512 MiB ZIP limit.")
            return raw
        finally:
            self.busy = False

    @staticmethod
    def _validate_backup_workspace(root: Path) -> BrowserState:
        """Validate retained artifacts without running archived Python code."""
        state = BrowserState.model_validate(read_json(root / "browser-state.json"))
        ws = Workspace(root)
        for kind, loader in (
            ("datasets", load_dataset),
            ("sources", sources.load_source),
            ("research", load_bound_research),
        ):
            for directory in (root / kind).iterdir():
                safe_id(directory.name)
                if not directory.is_dir():
                    raise ValueError(
                        "Backup contains a malformed workspace collection."
                    )
                retained = loader(directory)
                retained_id = (
                    retained["metadata"]["dataset_id"]
                    if kind == "datasets"
                    else (
                        retained["snapshot_id"]
                        if kind == "sources"
                        else retained[0]["research_id"]
                    )
                )
                if retained_id != directory.name:
                    raise ValueError(
                        "Backup artifact identity differs from its directory."
                    )
        for path in (root / "cases").rglob("*"):
            if not path.is_file():
                continue
            case = Case.model_validate(read_json(path))
            relative = path.relative_to(root / "cases").parts
            current = len(relative) == 1 and path.name == f"{case.case_id}.json"
            history = (
                len(relative) == 3
                and relative[:2] == ("history", case.case_id)
                and path.name
                == sha256_bytes(canonical_json(case.model_dump(mode="json"))) + ".json"
            )
            if not (current or history):
                raise ValueError("Backup contains a malformed saved case.")
            if current and not (root / "datasets" / case.dataset_id).is_dir():
                raise ValueError("Saved case dataset is missing from backup.")
            if (
                current
                and case.watchlist_snapshot_id
                and not (root / "sources" / case.watchlist_snapshot_id).is_dir()
            ):
                raise ValueError("Saved case screening source is missing from backup.")
        for directory in (root / "runs").iterdir():
            safe_id(directory.name)
            if not ws.verify_run(directory.name)["ok"]:
                raise ValueError("A retained run failed integrity validation.")
            if read_json(directory / "manifest.json")["run_id"] != directory.name:
                raise ValueError("A retained run identity differs from its directory.")
            load_dataset(directory / "data")
            if (directory / "sources").exists():
                sources.load_source(directory / "sources")
        for directory in (root / "reviews").iterdir():
            safe_id(directory.name)
            run = root / "runs" / directory.name
            for review in directory.iterdir():
                wrapper = _review_wrapper(
                    read_json(review), (run / "manifest.json").read_bytes()
                )
                if (
                    review.name != wrapper["review_id"] + ".json"
                    or not validate_review(run, wrapper["review"])["ok"]
                ):
                    raise ValueError("A retained assessment failed validation.")
        for file in (root / "exports").iterdir():
            if file.suffix == ".zip":
                if not verify_bundle(file)["ok"]:
                    raise ValueError("An evidence package failed integrity validation.")
            elif file.name.endswith("-latest.json"):
                pointer = read_json(file)
                if set(pointer) != {
                    "name",
                    "sha256",
                    "review_id",
                    "run_manifest_sha256",
                }:
                    raise ValueError("Invalid evidence package pointer.")
                target = safe_child(root / "exports", pointer["name"])
                if sha256_file(target) != pointer["sha256"]:
                    raise ValueError("Evidence package pointer checksum mismatch.")
            else:
                raise ValueError("Unexpected evidence package artifact.")
        for file in (root / "events").iterdir():
            event = read_json(file)
            if not isinstance(event, dict) or not {
                "at",
                "action",
                "resource_id",
            } <= set(event):
                raise ValueError("Invalid retained activity record.")
        return state

    def _recover_restore(self) -> None:
        """A failed child swap is recoverable without renaming the IDBFS mount."""
        journal_path = safe_child(self.root, RESTORE_JOURNAL)
        if not journal_path.exists():
            return
        journal = read_json(journal_path)
        if not isinstance(journal, dict) or set(journal) != {
            "stage",
            "backup",
            "original",
            "incoming",
            "phase",
        }:
            raise ValueError("Invalid browser restore recovery journal.")
        names = set(WORKSPACE_GROUPS) | {"browser-state.json"}
        if journal["phase"] not in {"prepared", "published"} or any(
            not isinstance(journal[key], list)
            or len(journal[key]) != len(set(journal[key]))
            or not set(journal[key]) <= names
            for key in ("original", "incoming")
        ):
            raise ValueError("Invalid browser restore recovery entries.")
        stage = safe_child(self.root, journal["stage"])
        backup = safe_child(self.root, journal["backup"])
        if not stage.name.startswith(".restore-stage-") or not backup.name.startswith(
            ".restore-old-"
        ):
            raise ValueError("Invalid browser restore recovery paths.")
        if journal["phase"] == "prepared":
            for name in journal["incoming"]:
                if name not in journal["original"] or (backup / name).exists():
                    target = safe_child(self.root, name)
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink(missing_ok=True)
            if backup.exists():
                for path in backup.iterdir():
                    if path.name not in journal["original"]:
                        raise ValueError(
                            "Unexpected browser restore recovery artifact."
                        )
                    path.rename(safe_child(self.root, path.name))
        for directory in (stage, backup):
            if directory.exists():
                shutil.rmtree(directory)
        journal_path.unlink()

    def _ensure_ready(self) -> None:
        if not (self.root / RESTORE_JOURNAL).exists():
            return
        try:
            self._recover_restore()
            state = BrowserState.model_validate(read_json(self.state_path))
            self.context = BrowserContext(
                Workspace(self.root),
                self.root,
                state.token,
                bytes.fromhex(state.workflow_secret),
                state.guided_runs,
                contextlib.nullcontext(),
            )
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise RequestError(
                "The workspace is recovering an interrupted restore. Reload to retry; retained files were not discarded.",
                503,
            ) from exc

    @staticmethod
    def _check_zip_envelope(raw: bytes) -> None:
        """Bound central-directory allocation before ZipFile builds its objects."""
        position = raw.rfind(b"PK\x05\x06", max(0, len(raw) - 65557))
        if position < 0 or position + 22 > len(raw):
            raise ValueError("Workspace backup has no valid ZIP directory.")
        _, disk, central_disk, disk_count, count, size, offset, comment = (
            struct.unpack_from("<4s4H2LH", raw, position)
        )
        if (
            disk
            or central_disk
            or disk_count != count
            or count > 20001
            or size > 8 * 1024 * 1024
            or offset + size != position
            or position + 22 + comment != len(raw)
        ):
            raise ValueError(
                "Workspace backup ZIP directory is unsupported or exceeds limits."
            )
        cursor, observed = offset, 0
        while cursor < position:
            if cursor + 46 > position or raw[cursor : cursor + 4] != b"PK\x01\x02":
                raise ValueError("Invalid workspace backup ZIP directory entry.")
            name, extra, entry_comment = struct.unpack_from("<3H", raw, cursor + 28)
            cursor += 46 + name + extra + entry_comment
            observed += 1
            if observed > 20001 or cursor > position:
                raise ValueError("Workspace backup has too many ZIP entries.")
        if observed != count:
            raise ValueError("Workspace backup ZIP entry count is inconsistent.")

    def _restore(self, raw: bytes) -> dict[str, Any]:
        if not raw or len(raw) > MAX_BACKUP_BYTES:
            raise ValueError("Choose a workspace backup ZIP no larger than 512 MiB.")
        self._check_zip_envelope(raw)
        stage = Path(tempfile.mkdtemp(prefix=".restore-stage-", dir=self.root))
        backup: Path | None = None
        journal_path = self.root / RESTORE_JOURNAL
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                if any(
                    item.flag_bits & 1
                    or item.compress_type
                    not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    for item in entries
                ):
                    raise ValueError(
                        "Encrypted or unsupported-compression backups are not accepted."
                    )
                if len(entries) > 20001 or len(
                    {item.filename.casefold() for item in entries}
                ) != len(entries):
                    raise ValueError(
                        "Backup inventory is oversized or contains repeated paths."
                    )
                manifest_info = archive.getinfo(BACKUP_MANIFEST)
                manifest = (
                    _json_bytes(archive.read(manifest_info), limit=4 * 1024 * 1024)
                    if manifest_info.file_size <= 4 * 1024 * 1024
                    else None
                )
                if (
                    not isinstance(manifest, dict)
                    or set(manifest)
                    != {"schema_version", "kind", "created_at", "files"}
                    or manifest["schema_version"] != "1.0"
                    or manifest["kind"] != "omphalos-browser-backup"
                ):
                    raise ValueError("This file is not an omphalOS workspace backup.")
                inventory = _entries(manifest)
                if (
                    sum(row["size_bytes"] for row in inventory.values())
                    > MAX_BACKUP_BYTES
                ):
                    raise ValueError("Backup exceeds the 512 MiB expanded limit.")
                if {item.filename for item in entries} != {BACKUP_MANIFEST} | {
                    "workspace/" + name for name in inventory
                }:
                    raise ValueError("Backup files differ from the complete inventory.")
                for name, record in inventory.items():
                    self._workspace_path(name)
                    item = archive.getinfo("workspace/" + name)
                    if (
                        item.is_dir()
                        or stat.S_IFMT(item.external_attr >> 16)
                        not in {0, stat.S_IFREG}
                        or item.flag_bits & 1
                        or item.file_size != record["size_bytes"]
                    ):
                        raise ValueError(
                            "Backup contains an unsafe or inconsistent file."
                        )
                    target = safe_child(stage, name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output, length=128 * 1024)
                    if (
                        target.stat().st_size != record["size_bytes"]
                        or sha256_file(target) != record["sha256"]
                    ):
                        raise ValueError("Backup file failed its integrity check.")
            state = self._validate_backup_workspace(stage)
            original = sorted(
                path.name for path in self.root.iterdir() if path != stage
            )
            if not set(original) <= WORKSPACE_GROUPS | {"browser-state.json"}:
                raise ValueError(
                    "Current workspace has unexpected files; restore left it unchanged."
                )
            incoming = sorted(path.name for path in stage.iterdir())
            backup = Path(tempfile.mkdtemp(prefix=".restore-old-", dir=self.root))
            journal = {
                "stage": stage.name,
                "backup": backup.name,
                "original": original,
                "incoming": incoming,
                "phase": "prepared",
            }
            write_json(journal_path, journal)
            try:
                for name in original:
                    (self.root / name).rename(backup / name)
                for name in incoming:
                    (stage / name).rename(self.root / name)
                write_json(journal_path, {**journal, "phase": "published"})
            except Exception:
                self._recover_restore()
                raise
            self.context = BrowserContext(
                Workspace(self.root),
                self.root,
                state.token,
                bytes.fromhex(state.workflow_secret),
                state.guided_runs,
                contextlib.nullcontext(),
            )
            self._recover_restore()
            return {
                "restored": True,
                "datasets": len(list((self.root / "datasets").iterdir())),
                "runs": len(list((self.root / "runs").iterdir())),
            }
        finally:
            if not journal_path.exists():
                for directory in (stage, backup):
                    if directory is not None and directory.exists():
                        shutil.rmtree(directory)

    def restore_bytes(self, raw: Any) -> dict[str, Any]:
        """Validate a complete backup before replacing work; never execute its code."""
        if self.busy:
            return {
                "status": 409,
                "body_json": {"error": "Another operation is running.", "status": 409},
            }
        self.busy = True
        try:
            self._ensure_ready()
            converted = _plain(raw)
            if not isinstance(converted, (bytes, bytearray, memoryview)):
                raise ValueError("Workspace restore requires original ZIP bytes.")
            if (
                converted.nbytes
                if isinstance(converted, memoryview)
                else len(converted)
            ) > MAX_BACKUP_BYTES:
                raise ValueError(
                    "Choose a workspace backup ZIP no larger than 512 MiB."
                )
            result = self._restore(bytes(converted))
            return {"status": 200, "body_json": result}
        except (
            ValueError,
            OSError,
            KeyError,
            TypeError,
            RuntimeError,
            zipfile.BadZipFile,
        ) as exc:
            LOG.warning(
                "browser_restore_rejected", extra={"error_type": type(exc).__name__}
            )
            status = exc.status if isinstance(exc, RequestError) else 400
            return {
                "status": status,
                "body_json": {"error": str(exc), "status": status},
            }
        finally:
            self.busy = False

    def _persist(self) -> None:
        state = BrowserState(
            token=self.context.token,
            workflow_secret=self.context.workflow_secret.hex(),
            guided_runs=self.context.guided_runs,
        )
        write_json(self.state_path, state.model_dump())

    def _download(
        self, url: str, maximum: int, provider: str
    ) -> tuple[bytes, dict[str, str]]:
        if self.transport is None:
            raise ValueError("Browser public-source transport is unavailable.")
        try:
            response = _plain(self.transport(url, maximum, provider))
        except Exception as exc:
            raise ValueError(
                f"{provider} could not be reached from this browser. Try again or import a source file."
            ) from exc
        if not isinstance(response, dict) or response.get("status") != 200:
            raise ValueError(f"{provider} did not return a successful public response.")
        final_url = response.get("url")
        if not isinstance(final_url, str):
            raise ValueError("Public response is missing its final URL.")
        if final_url != url:
            # Wikidata's CORS flag is transport-only; retained query URLs stay
            # canonical so existing research validation and replay are exact.
            expected, actual = urlsplit(url), urlsplit(final_url)
            query = parse_qs(actual.query, keep_blank_values=True)
            cors = query.pop("origin", None)
            if not (
                provider == "wikidata"
                and expected.scheme == actual.scheme == "https"
                and expected.netloc == actual.netloc == "www.wikidata.org"
                and expected.path == actual.path
                and not actual.fragment
                and cors == ["*"]
                and query == parse_qs(expected.query, keep_blank_values=True)
            ):
                raise ValueError("Public-source redirects are not accepted.")
        raw = _plain(response.get("body"))
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            raise ValueError("Public response must contain its original bytes.")
        if not 0 < len(raw) <= maximum:
            raise ValueError("Public response exceeds the supported size or is empty.")
        supplied_headers = _plain(response.get("headers", {}))
        if not isinstance(supplied_headers, dict):
            raise ValueError("Invalid public response headers.")
        headers = {}
        for key, value in supplied_headers.items():
            if isinstance(key, str) and isinstance(value, str):
                normalized = key.lower()
                if normalized in {"etag", "last-modified", "content-type"}:
                    headers[
                        {
                            "etag": "ETag",
                            "last-modified": "Last-Modified",
                            "content-type": "Content-Type",
                        }[normalized]
                    ] = value
        return bytes(raw), headers

    def fetch_source(self, source_id: str, destination: Path) -> dict[str, Any]:
        definition = sources._definition(source_id)
        if source_id != "csl":
            raise RequestError(
                "This official source does not permit direct browser downloads. Download its published file and import it here.",
                422,
            )
        url = sources._checked_url(definition["url"])
        raw, headers = self._download(url, sources.MAX_BYTES, source_id)
        return sources._store(
            source_id,
            raw,
            destination,
            fetched_at=utc_now(),
            method="official_https",
            headers=headers,
        )

    def _identity_download(self, url: str) -> bytes:
        identity_research._validate_url(url)
        provider = "gleif" if urlsplit(url).hostname == "api.gleif.org" else "wikidata"
        raw, _ = self._download(url, identity_research.MAX_BYTES, provider)
        return raw

    @contextlib.contextmanager
    def _transport(self) -> Iterator[None]:
        # Worker operations are serialized. Patch only the native network edge;
        # the research request log, parsers, and offline replay stay unchanged.
        original = identity_research._download
        identity_research._download = self._identity_download
        try:
            yield
        finally:
            identity_research._download = original

    def dispatch(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.busy:
            return {
                "status": 409,
                "body_json": {"error": "Another operation is running.", "status": 409},
            }
        self.busy = True
        adapter = BrowserRequest(self, path, body)
        try:
            with self._transport():
                try:
                    self._ensure_ready()
                    adapter.server = self.context
                    return adapter.execute()
                except Exception as exc:
                    adapter._handle_error(exc)
                    return {
                        "status": adapter.response_status,
                        "body_json": adapter.response_body,
                    }
                finally:
                    # Plans can become approved before a later operation fails.
                    # The worker must flush these bytes even on error responses.
                    if not (self.root / RESTORE_JOURNAL).exists():
                        self._persist()
        finally:
            LOG.info(
                "browser_request",
                extra={"method": adapter.command, "status": adapter.response_status},
            )
            self.busy = False

    def dispatch_json(self, path: str, body_json: str | None = None) -> str:
        try:
            body = (
                None
                if body_json is None
                else json.loads(
                    body_json,
                    object_pairs_hook=_json_object,
                    parse_constant=lambda _: (_ for _ in ()).throw(
                        ValueError("Non-finite JSON number")
                    ),
                )
            )
            if body_json is not None and not isinstance(body, dict):
                raise RequestError("The request body must be a JSON object.")
            result = self.dispatch(path, body)
        except (ValueError, TypeError, RecursionError) as exc:
            result = {"status": 400, "body_json": {"error": str(exc), "status": 400}}
        return canonical_json(result).decode("utf-8")

    def export_bytes(self, path: str) -> bytes:
        if self.busy:
            raise RequestError("Another operation is running.", 409)
        self._ensure_ready()
        adapter = BrowserRequest(self, path, None)
        parts, query = adapter._route()
        if query or len(parts) != 3 or parts[:2] != ["api", "exports"]:
            raise RequestError(
                "Only generated evidence packages can be downloaded.", 404
            )
        name = parts[2]
        if not name.endswith(".zip"):
            raise RequestError("Only generated ZIP exports can be downloaded.", 400)
        safe_id(name[:-4])
        target = safe_child(self.root / "exports", name)
        if not target.is_file():
            raise RequestError("Export not found.", 404)
        return target.read_bytes()

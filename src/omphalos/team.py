"""Optional authenticated ASGI team service, separate from the local workbench."""

from __future__ import annotations

import asyncio
import hmac
import io
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .runner import Workspace
from .team_store import SESSION_SECONDS, TeamStore
from .util import canonical_json, safe_id
from .web import (
    MAX_BODY_BYTES,
    STATIC_CONTENT_TYPES,
    STATIC_FILES,
    UI_ROOT,
    RequestError,
    WorkbenchHandler,
    _fields,
    _json_object,
    _text,
)

LOG = logging.getLogger(__name__)
COOKIE = "omphalos_team"


@dataclass
class TeamContext:
    workspace: Workspace
    root: Path
    token: str
    workflow_secret: bytes
    guided_runs: dict[str, str]
    mutation_lock: threading.RLock


def _public(value: Any, prefix: str) -> Any:
    # Transform only known application links, never retained evidence fields.
    if not isinstance(value, dict):
        return value
    result = dict(value)
    # These response wrappers use `path` for server filesystem metadata, whether
    # absolute, drive-relative, or workspace-relative. Its syntax must not depend
    # on the OS serving the request. Record/review contents are not traversed.
    if isinstance(result.get("path"), str):
        del result["path"]
    for key in ("latest_export", "latest_review", "handoff"):
        if isinstance(result.get(key), dict):
            result[key] = _public(result[key], prefix)
    link = result.get("download_url")
    if isinstance(link, str) and link.startswith("/api/exports/"):
        result["download_url"] = prefix + link[5:]
    return result


class TeamRequest(WorkbenchHandler):
    """Use the original route validation without running an HTTP server."""

    def __init__(self, context: TeamContext, path: str, body: dict | None, prefix: str):
        self.server = context
        self.path = path
        self.command = "POST" if body is not None else "GET"
        self.headers = Message()
        self.parsed_body = body
        self.prefix = prefix
        self.wfile = io.BytesIO()
        self.response_status = 200
        self.response_body = None
        self.response_headers: dict[str, str] = {}
        self.close_connection = True

    def _check_request(self, *, mutation: bool = False) -> None:
        if not self.path.startswith("/api/"):
            raise RequestError("Route not found.", 404)

    def _body(self) -> dict:
        return self.parsed_body

    def send_response(self, code: int, message: str | None = None) -> None:
        self.response_status = code

    def send_header(self, keyword: str, value: Any) -> None:
        self.response_headers[keyword.lower()] = str(value)

    def end_headers(self) -> None:
        return None

    def _json(self, value: Any, status: int = 200) -> None:
        self.response_status = status
        self.response_body = _public(value, self.prefix)

    def execute(self) -> tuple[int, Any, dict]:
        if self.command == "GET":
            self.do_GET()
        else:
            self.do_POST()
        return (
            self.response_status,
            (
                self.response_body
                if self.response_body is not None
                else self.wfile.getvalue()
            ),
            self.response_headers,
        )


class TeamApp:
    def __init__(self, root: Path | str, *, origin: str):
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError(
                "Use an exact origin such as https://omphalos.example.org, without a path."
            )
        if parsed.scheme == "http" and parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("Team access outside this computer requires HTTPS.")
        self.origin = origin
        self.authority = parsed.netloc
        self.secure = parsed.scheme == "https"
        self.store = TeamStore(root)
        self.contexts: dict[str, TeamContext] = {}
        self.context_lock = threading.Lock()
        self.request_slots = asyncio.Semaphore(8)
        self.event_slots = asyncio.Semaphore(32)
        self.lease = None

    def _context(self, identifier: str) -> TeamContext:
        with self.context_lock:
            if identifier not in self.contexts:
                saved = self.store.context(identifier)
                root = self.store.workspace_path(identifier)
                self.contexts[identifier] = TeamContext(
                    Workspace(root),
                    root,
                    saved["token"],
                    bytes.fromhex(saved["workflow_secret"]),
                    json.loads(saved["guided_runs"]),
                    threading.RLock(),
                )
            return self.contexts[identifier]

    def _lease(self) -> None:
        """A second worker/process must not serve the same filesystem workspace."""
        path = self.store.root / "server.lock"
        self.lease = path.open("a+b")
        self.lease.seek(0)
        try:
            import fcntl

            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            import msvcrt

            self.lease.write(b"0")
            self.lease.flush()
            self.lease.seek(0)
            msvcrt.locking(self.lease.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.lease.close()
            self.lease = None
            raise RuntimeError(
                "Another team server already owns this workspace."
            ) from None

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    try:
                        if not self.store.initialized():
                            raise RuntimeError(
                                "Run 'omphalos team init' before starting the server."
                            )
                        self._lease()
                        await send({"type": "lifespan.startup.complete"})
                    except Exception as exc:
                        await send(
                            {"type": "lifespan.startup.failed", "message": str(exc)}
                        )
                        return
                elif message["type"] == "lifespan.shutdown":
                    if self.lease:
                        self.lease.close()
                        self.lease = None
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        status, result, extra = 500, {"error": "The operation failed."}, {}
        try:
            headers = self._headers(scope)
            method, path = scope["method"], scope["path"]
            if method not in {"GET", "POST"}:
                raise RequestError("Use GET or POST.", 405)
            if not path.startswith("/team/api/"):
                if method != "GET":
                    raise RequestError("Route not found.", 404)
                status, result, extra = self._static(path)
            else:
                token = self._cookie(headers.get("cookie", ""))
                session = self.store.session(token)
                if method == "POST" and path != "/team/api/login":
                    if not session:
                        raise RequestError("Sign in to continue.", 401)
                    if not hmac.compare_digest(
                        headers.get("x-omphalos-csrf", ""), session["csrf"]
                    ):
                        raise RequestError(
                            "Your security token expired. Sign in again.", 403
                        )
                if method == "GET" and re.fullmatch(
                    r"/team/api/matters/[^/]+/events", path
                ):
                    async with self.event_slots:
                        status, result, extra = await self._events(
                            scope, receive, token, path
                        )
                else:
                    async with self.request_slots:
                        body = (
                            await self._body(scope, headers, receive)
                            if method == "POST"
                            else None
                        )
                        status, result, extra = await asyncio.to_thread(
                            self._route, scope, headers, session, token, body
                        )
        except RequestError as exc:
            status, result = exc.status, {"error": str(exc), "status": exc.status}
        except (ValueError, TypeError, KeyError) as exc:
            status, result = 400, {"error": str(exc), "status": 400}
        except asyncio.CancelledError:
            raise
        except Exception:
            LOG.exception("team_request_failed")
        await self._send(send, status, result, extra)

    def _headers(self, scope) -> dict[str, str]:
        values: dict[str, str] = {}
        protected = {
            "host",
            "origin",
            "cookie",
            "x-omphalos-csrf",
            "if-match",
            "content-length",
            "content-type",
        }
        for raw_key, raw_value in scope["headers"]:
            key, value = raw_key.decode("latin1").lower(), raw_value.decode("latin1")
            if key in protected and key in values:
                raise RequestError("Duplicate request header.", 400)
            values[key] = value
        if values.get("host") != self.authority:
            raise RequestError("Unexpected host.", 403)
        origin = values.get("origin")
        if (origin is not None and origin != self.origin) or (
            scope["method"] == "POST" and origin != self.origin
        ):
            raise RequestError("Use the team's own origin.", 403)
        if values.get("sec-fetch-site") == "cross-site":
            raise RequestError("Cross-site requests are not allowed.", 403)
        return values

    def _cookie(self, value: str) -> str | None:
        found = [
            part.strip().partition("=")[2]
            for part in value.split(";")
            if part.strip().partition("=")[0] == COOKIE
        ]
        if len(found) > 1:
            raise RequestError("Duplicate session cookie.", 400)
        return found[0] if found else None

    async def _body(self, scope, headers, receive) -> dict:
        limit = MAX_BODY_BYTES if "/engine/" in scope["path"] else 16_384
        if (
            headers.get("content-type", "").split(";", 1)[0].strip()
            != "application/json"
        ):
            raise RequestError("Use application/json.", 415)
        supplied = headers.get("content-length")
        if supplied is not None and (not supplied.isascii() or not supplied.isdigit()):
            raise RequestError("Invalid Content-Length.", 400)
        if supplied and int(supplied) > limit:
            raise RequestError("The request is too large.", 413)
        data = bytearray()
        deadline = time.monotonic() + 20
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RequestError("The upload timed out.", 408)
            try:
                message = await asyncio.wait_for(receive(), remaining)
            except TimeoutError as exc:
                raise RequestError("The upload timed out.", 408) from exc
            if message["type"] == "http.disconnect":
                raise RequestError(
                    "The connection closed before the request completed.", 400
                )
            data.extend(message.get("body", b""))
            if len(data) > limit:
                raise RequestError("The request is too large.", 413)
            if not message.get("more_body", False):
                break
        if supplied is not None and int(supplied) != len(data):
            raise RequestError("Content-Length differs from the request body.")
        try:
            body = json.loads(
                data,
                object_pairs_hook=_json_object,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    ValueError("Non-finite JSON value")
                ),
            )
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise RequestError("Invalid JSON request.") from exc
        if not isinstance(body, dict):
            raise RequestError("The request must be a JSON object.")
        return body

    def _static(self, path: str) -> tuple:
        if path == "/":
            raw = (UI_ROOT / "index.html").read_text()
            raw = raw.replace(
                '<script src="/app.js"',
                '<script src="/team.js" defer></script>\n    <script src="/app.js"',
            )
            raw = raw.replace(
                '<link rel="stylesheet" href="/styles.css" />',
                '<link rel="stylesheet" href="/styles.css" />\n    <link rel="stylesheet" href="/team.css" />',
            )
            return 200, raw.encode(), {"content-type": "text/html; charset=utf-8"}
        filename = {**STATIC_FILES, "/team.js": "team.js", "/team.css": "team.css"}.get(
            path
        )
        if not filename or filename == "index.html":
            raise RequestError("Route not found.", 404)
        return (
            200,
            (UI_ROOT / filename).read_bytes(),
            {"content-type": STATIC_CONTENT_TYPES[Path(filename).suffix]},
        )

    def _session_cookie(self, token: str, *, expired: bool = False) -> str:
        return (
            f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if expired else SESSION_SECONDS}"
            + ("; Secure" if self.secure else "")
        )

    def _require_session(self, token: str | None) -> dict:
        session = self.store.session(token)
        if not session:
            raise RequestError("Sign in to continue.", 401)
        return session

    def _revision(self, headers: dict) -> int:
        value = headers.get("if-match", "")
        if not re.fullmatch(r'"(?:0|[1-9][0-9]{0,14})"', value):
            raise RequestError(
                'Supply the matter revision in If-Match: "<revision>".', 428
            )
        return int(value[1:-1])

    def _route(self, scope, headers, session, token, body) -> tuple:
        method, path = scope["method"], scope["path"]
        query = scope.get("query_string", b"").decode("ascii")
        if method == "POST" and query:
            raise RequestError("POST routes do not accept query parameters.")
        if path == "/team/api/session" and method == "GET":
            return 200, self.store.session(token) or {"authenticated": False}, {}
        if path == "/team/api/login" and method == "POST":
            _fields(body, {"username", "password"}, {"username", "password"})
            token, result = self.store.login(
                body["username"],
                body["password"],
                str(scope.get("client", ("unknown", 0))[0]),
            )
            return 200, result, {"set-cookie": self._session_cookie(token)}
        session = self._require_session(token)
        actor = session["user"]
        if method == "POST" and not hmac.compare_digest(
            headers.get("x-omphalos-csrf", ""), session["csrf"]
        ):
            raise RequestError("Your security token expired. Sign in again.", 403)
        if path == "/team/api/logout" and method == "POST":
            _fields(body, set())
            self.store.logout(token, actor)
            return (
                200,
                {"authenticated": False},
                {"set-cookie": self._session_cookie("", expired=True)},
            )
        if path == "/team/api/password" and method == "POST":
            _fields(
                body,
                {"current_password", "new_password"},
                {"current_password", "new_password"},
            )
            self.store.change_password(
                actor,
                body["current_password"],
                body["new_password"],
                str(scope.get("client", ("unknown", 0))[0]),
                token=token,
            )
            return (
                200,
                {"authenticated": False},
                {"set-cookie": self._session_cookie("", expired=True)},
            )
        if path == "/team/api/matters":
            if method == "GET":
                return 200, {"matters": self.store.list_matters(actor)}, {}
            _fields(body, {"title"}, {"title"})
            return 200, self.store.create_matter(actor, body["title"], token=token), {}
        if path == "/team/api/admin/users":
            self.store.require_admin(actor)
            if method == "GET":
                return 200, {"users": self.store.users(actor)}, {}
            _fields(
                body,
                {"username", "display_name", "password", "is_admin"},
                {"username", "display_name", "password"},
            )
            return (
                200,
                self.store.create_user(
                    body["username"],
                    body["display_name"],
                    body["password"],
                    is_admin=body.get("is_admin", False),
                    actor=actor,
                    token=token,
                ),
                {},
            )
        match = re.fullmatch(r"/team/api/admin/users/([^/]+)", path)
        if match and method == "POST":
            self.store.require_admin(actor)
            return (
                200,
                self.store.update_user(actor, safe_id(match[1]), body, token=token),
                {},
            )
        if path == "/team/api/admin/matters" and method == "GET":
            return 200, {"matters": self.store.list_matters(actor, admin=True)}, {}
        match = re.fullmatch(r"/team/api/admin/matters/([^/]+)/members", path)
        if match:
            self.store.require_admin(actor)
            identifier = safe_id(match[1])
            if method == "GET":
                with self._context(identifier).mutation_lock:
                    members = self.store.members(actor, identifier)
                    revision = self.store.context(identifier)["revision"]
                return (
                    200,
                    {"members": members, "revision": revision},
                    {"x-omphalos-revision": str(revision)},
                )
            _fields(body, {"user_id", "role"}, {"user_id", "role"})
            with self._context(identifier).mutation_lock:
                result = self.store.set_member(
                    actor,
                    identifier,
                    _text(body["user_id"], "Account identifier", 80),
                    body["role"],
                    expected=self._revision(headers),
                    token=token,
                )
            return 200, result, {"x-omphalos-revision": str(result["revision"])}
        match = re.fullmatch(
            r"/team/api/matters/([^/]+)/(engine/(.+)|approval|submission)", path
        )
        if not match:
            raise RequestError("Route not found.", 404)
        identifier, operation = safe_id(match[1]), match[2]
        self.store.matter(actor, identifier)
        context = self._context(identifier)
        with context.mutation_lock:
            session = self._require_session(token)
            actor = session["user"]
            matter = self.store.matter(actor, identifier)
            extra = {"x-omphalos-revision": str(matter["revision"])}
            try:
                if operation.startswith("engine/"):
                    result = self._engine(
                        context, actor, matter, match[3], query, headers, body, token
                    )
                else:
                    result = self._approval(
                        context, actor, matter, operation, query, headers, body, token
                    )
            except RequestError as exc:
                current = self.store.matter(actor, identifier)
                return (
                    exc.status,
                    {
                        "error": str(exc),
                        "status": exc.status,
                        "revision": current["revision"],
                    },
                    {"x-omphalos-revision": str(current["revision"])},
                )
            # A disabled user or removed membership never receives the result of a
            # request that completed while the account was being revoked.
            self._require_session(token)
            current = self.store.matter(actor, identifier)
            extra["x-omphalos-revision"] = str(current["revision"])
            return result[0], result[1], {**result[2], **extra}

    def _engine(
        self, context, actor, matter, path, query, headers, body, token
    ) -> tuple:
        if (
            "%" in path
            or "\\" in path
            or "//" in path
            or any(part in {".", ".."} for part in path.split("/"))
        ):
            raise RequestError("Use the canonical engine route.")
        prefix = f"/team/api/matters/{matter['id']}/engine/"
        if body is not None:
            readonly_post = bool(re.fullmatch(r"runs/[^/]+/(verify|replay)", path))
            if matter["role"] != "analyst" and not readonly_post:
                raise RequestError(
                    "Only an assigned analyst can change this matter.", 403
                )
            if re.fullmatch(r"runs/[^/]+/review", path):
                if body.get("schema_version") != "2.2":
                    raise RequestError(
                        "Save a current assessment with an explained reason and next step (schema 2.2)."
                    )
                # The account identity is authoritative; a forged request cannot
                # claim a colleague's display name in the exported assessment.
                body = {**body, "reviewer": actor["display_name"]}
            expected = self._revision(headers)
            revision = self.store.begin_mutation(
                actor,
                matter["id"],
                expected,
                "engine:" + path,
                token=token,
                roles=(
                    frozenset({"analyst", "reviewer", "viewer"})
                    if readonly_post
                    else frozenset({"analyst"})
                ),
            )
        else:
            revision = matter["revision"]
        adapter = TeamRequest(
            context, "/api/" + path + ("?" + query if query else ""), body, prefix
        )
        status, result, extra = 500, None, {}
        try:
            status, result, extra = adapter.execute()
            if path == "state" and status == 200:
                result.update(
                    mode="team",
                    token="",
                    storage={
                        "mode": "team",
                        "description": "Stored in this team's shared workspace.",
                    },
                    team={
                        "matter_id": matter["id"],
                        "title": matter["title"],
                        "revision": revision,
                        "role": matter["role"],
                        "user": actor,
                    },
                )
            return status, result, extra
        finally:
            if body is not None:
                author = (
                    (result["review_id"], actor["id"])
                    if status < 400
                    and re.fullmatch(r"runs/[^/]+/review", path)
                    and isinstance(result, dict)
                    else None
                )
                self.store.finish_mutation(
                    actor,
                    matter["id"],
                    revision,
                    "engine:" + path,
                    context.guided_runs,
                    status=status,
                    author=author,
                )

    def _approval_context(self, context, actor, matter, run_id: str) -> dict:
        run = context.workspace.get_run(safe_id(run_id))
        exported = run.get("latest_export")
        package = (
            {
                "run_id": run_id,
                "review_id": exported["review_id"],
                "package_sha256": exported["sha256"],
                "analysis_digest": run["manifest"]["analysis_digest"],
            }
            if exported
            else None
        )
        submission, decisions, author = self.store.approval_records(
            matter["id"],
            run_id,
            package["package_sha256"] if package else None,
            package["review_id"] if package else None,
        )
        return {
            "package": package,
            "submission": submission,
            "decisions": decisions,
            "submission_blocker": (
                "Save a fresh assessment under a team account before submitting an imported package for independent team review."
                if package and not author
                else None
            ),
            "can_submit": bool(
                package
                and author
                and matter["role"] == "analyst"
                and (
                    submission is None
                    or submission["submitted_by"]["id"] == actor["id"]
                )
            ),
            "can_review": bool(
                package
                and author
                and submission
                and matter["role"] == "reviewer"
                and submission["submitted_by"]["id"] != actor["id"]
                and author != actor["id"]
            ),
        }

    def _approval(
        self, context, actor, matter, operation, query, headers, body, token
    ) -> tuple:
        if body is None:
            params = parse_qs(query, keep_blank_values=True, max_num_fields=2)
            if (
                operation != "approval"
                or set(params) != {"run_id"}
                or len(params["run_id"]) != 1
            ):
                raise RequestError("Supply one run_id.")
            return (
                200,
                self._approval_context(context, actor, matter, params["run_id"][0]),
                {},
            )
        required = {"run_id", "package_sha256"} | (
            {"decision", "note"} if operation == "approval" else set()
        )
        _fields(body, required, required)
        run_id = safe_id(_text(body["run_id"], "Run identifier", 80))
        result = self._approval_context(context, actor, matter, run_id)
        if (
            not result["package"]
            or result["package"]["package_sha256"] != body["package_sha256"]
        ):
            raise RequestError(
                "The reviewed package changed or no longer verifies. Reopen Package.",
                409,
            )
        if operation == "approval":
            if not result["can_review"]:
                raise RequestError(
                    "An independent assigned reviewer must review this submitted package.",
                    403,
                )
            if body["decision"] not in {"approve", "request_changes"}:
                raise RequestError("Choose approve or request_changes.")
            note = _text(body["note"], "Review note", 4000).strip()
            if not note:
                raise RequestError("Record a reason and next step.")
        elif not result["can_submit"]:
            raise RequestError("An assigned analyst must submit this package.", 403)
        revision = self.store.begin_mutation(
            actor,
            matter["id"],
            self._revision(headers),
            operation,
            token=token,
            roles=frozenset({"reviewer" if operation == "approval" else "analyst"}),
        )
        status = 500
        try:
            if operation == "approval":
                self.store.decide(
                    actor,
                    matter["id"],
                    result["package"],
                    body["decision"],
                    note,
                    token=token,
                )
            else:
                self.store.submit(actor, matter["id"], result["package"], token=token)
            status = 200
            return status, self._approval_context(context, actor, matter, run_id), {}
        except RequestError as exc:
            status = exc.status
            raise
        finally:
            self.store.finish_mutation(
                actor,
                matter["id"],
                revision,
                operation,
                context.guided_runs,
                status=status,
            )

    async def _events(self, scope, receive, token, path) -> tuple:
        identifier = safe_id(path.split("/")[-2])
        params = parse_qs(
            scope.get("query_string", b"").decode("ascii"),
            keep_blank_values=True,
            max_num_fields=4,
        )
        if set(params) - {"after", "wait"} or any(len(v) != 1 for v in params.values()):
            raise RequestError("Use one after revision and wait duration.")
        values = [
            params.get(key, [default])[0]
            for key, default in (("after", "0"), ("wait", "20"))
        ]
        if any(not re.fullmatch(r"[0-9]{1,15}", value) for value in values):
            raise RequestError("Use nonnegative integer event parameters.")
        after, wait = map(int, values)
        if wait > 25:
            raise RequestError("Wait must be at most 25 seconds.")
        deadline = time.monotonic() + wait
        while True:
            actor = self._require_session(token)["user"]
            result = self.store.events(actor, identifier, after)
            if result["revision"] != after or time.monotonic() >= deadline:
                return 200, result, {"x-omphalos-revision": str(result["revision"])}
            try:
                message = await asyncio.wait_for(
                    receive(), min(0.5, max(0.01, deadline - time.monotonic()))
                )
                if message["type"] == "http.disconnect":
                    raise RequestError("The connection closed.", 400)
            except TimeoutError:
                pass

    async def _send(self, send, status, result, extra):
        raw = result if isinstance(result, bytes) else canonical_json(result)
        headers = {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
            "referrer-policy": "no-referrer",
            "cross-origin-resource-policy": "same-origin",
            "content-security-policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            **extra,
            "content-length": str(len(raw)),
        }
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (key.encode("ascii"), str(value).encode("latin1"))
                    for key, value in headers.items()
                ],
            }
        )
        await send({"type": "http.response.body", "body": raw})


def serve_team(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8770,
    origin: str | None = None,
    certfile: Path | None = None,
    keyfile: Path | None = None,
    behind_proxy: bool = False,
) -> None:
    if bool(certfile) != bool(keyfile):
        raise ValueError("Supply both the HTTPS certificate and private key.")
    local = host in {"127.0.0.1", "localhost", "::1"}
    if not local and not certfile:
        raise ValueError(
            "A non-loopback team server requires an HTTPS certificate and key."
        )
    if behind_proxy and (not local or not origin or not origin.startswith("https://")):
        raise ValueError(
            "A reverse proxy requires a loopback listener and explicit HTTPS origin."
        )
    scheme = "https" if certfile else "http"
    origin = origin or f"{scheme}://{'[::1]' if host == '::1' else host}:{port}"
    if origin.startswith("https://") and not certfile and not behind_proxy:
        raise ValueError(
            "Supply HTTPS certificate/key or explicitly configure a loopback reverse proxy."
        )
    if certfile and not origin.startswith("https://"):
        raise ValueError("The public origin must use HTTPS with a certificate.")
    try:
        import uvicorn
    except ImportError as exc:
        raise ValueError(
            "From the repository root, install optional team support with: python -m pip install '.[team]'"
        ) from exc
    app = TeamApp(root, origin=origin)
    print(f"omphalOS team: {origin}", flush=True)
    uvicorn.run(
        app,
        host=host,
        port=port,
        http="h11",
        workers=1,
        proxy_headers=False,
        access_log=False,
        server_header=False,
        limit_concurrency=64,
        limit_max_requests=None,
        timeout_keep_alive=5,
        ssl_certfile=str(certfile) if certfile else None,
        ssl_keyfile=str(keyfile) if keyfile else None,
    )

"""Durable identities, membership, revisions, and audit records for team mode."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .util import canonical_json, safe_child, safe_id, utc_now
from .web import RequestError

PASSWORD_ROUNDS = 600_000
SESSION_SECONDS = 8 * 60 * 60
ROLES = frozenset({"analyst", "reviewer", "viewer"})


def _password(value: Any) -> str:
    if not isinstance(value, str) or not 14 <= len(value) <= 256:
        raise RequestError("Use a passphrase between 14 and 256 characters.")
    return value


def _name(value: Any, *, username: bool = False) -> str:
    if not isinstance(value, str):
        raise RequestError("A name is required.")
    value = value.strip()
    if username:
        value = value.casefold()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,63}", value):
            raise RequestError(
                "Use 2–64 letters, digits, periods, hyphens, or underscores."
            )
    elif not 1 <= len(value) <= 120 or any(ord(c) < 32 for c in value):
        raise RequestError("Use a name between 1 and 120 characters.")
    return value


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ROUNDS)


def _user(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "is_admin": bool(row["is_admin"]),
        "active": bool(row["active"]),
    }


class TeamStore:
    """One process owns a store; SQLite transactions also protect durable invariants."""

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.root / "matters").mkdir(exist_ok=True, mode=0o700)
        self.db_path = self.root / "team.sqlite3"
        if self.db_path.is_symlink():
            raise ValueError("The team database must not be a symbolic link.")
        self.lock = threading.RLock()
        self.hash_slots = threading.BoundedSemaphore(2)
        self.login_attempts: dict[str, list[float]] = {}
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL, is_admin INTEGER NOT NULL,
                    active INTEGER NOT NULL, salt BLOB NOT NULL, password BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    digest TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    csrf TEXT NOT NULL, expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS matters (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 0,
                    workflow_secret TEXT NOT NULL, token TEXT NOT NULL,
                    guided_runs TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS members (
                    matter_id TEXT NOT NULL, user_id TEXT NOT NULL, role TEXT NOT NULL,
                    PRIMARY KEY(matter_id,user_id)
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, matter_id TEXT,
                    revision INTEGER, actor_id TEXT NOT NULL, actor_name TEXT NOT NULL,
                    action TEXT NOT NULL, at TEXT NOT NULL, details TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS audit_matter ON audit(matter_id,revision,id);
                CREATE TABLE IF NOT EXISTS authors (
                    matter_id TEXT NOT NULL, review_id TEXT NOT NULL, user_id TEXT NOT NULL,
                    PRIMARY KEY(matter_id,review_id)
                );
                CREATE TABLE IF NOT EXISTS submissions (
                    matter_id TEXT NOT NULL, package_sha256 TEXT NOT NULL,
                    run_id TEXT NOT NULL, user_id TEXT NOT NULL, user_name TEXT NOT NULL,
                    at TEXT NOT NULL,
                    PRIMARY KEY(matter_id,package_sha256)
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY, matter_id TEXT NOT NULL,
                    package_sha256 TEXT NOT NULL, run_id TEXT NOT NULL,
                    user_id TEXT NOT NULL, user_name TEXT NOT NULL,
                    decision TEXT NOT NULL, note TEXT NOT NULL, at TEXT NOT NULL
                );
                """)
        self.db_path.chmod(0o600)
        self.dummy_salt = secrets.token_bytes(16)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialized(self) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def create_user(
        self,
        username: str,
        display_name: str,
        password: str,
        *,
        is_admin: bool = False,
        actor: dict | None = None,
        token: str | None = None,
        trusted: bool = False,
    ) -> dict:
        username, display_name = _name(username, username=True), _name(display_name)
        password = _password(password)
        if not isinstance(is_admin, bool):
            raise RequestError("Administrator status must be true or false.")
        if not self.hash_slots.acquire(blocking=False):
            raise RequestError("Authentication is busy. Try again shortly.", 429)
        try:
            salt = secrets.token_bytes(16)
            derived = _derive(password, salt)
        finally:
            self.hash_slots.release()
        identifier = "user-" + uuid.uuid4().hex
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if actor is None:
                if count or not is_admin:
                    raise RequestError(
                        "Initialize exactly one first administrator.", 409
                    )
            else:
                if not trusted:
                    self._require_token(db, actor, token)
                self.require_admin(actor, db=db)
            if count >= 1000:
                raise RequestError(
                    "This team has reached its 1,000-account limit.", 409
                )
            try:
                db.execute(
                    "INSERT INTO users VALUES(?,?,?,?,?,?,?)",
                    (
                        identifier,
                        username,
                        display_name,
                        int(is_admin),
                        1,
                        salt,
                        derived,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise RequestError("That username already exists.", 409) from exc
            result = _user(
                db.execute("SELECT * FROM users WHERE id=?", (identifier,)).fetchone()
            )
            self._audit(
                db, actor or result, "account_created", details={"user_id": identifier}
            )
            return result

    def require_admin(self, actor: dict, *, db=None) -> None:
        if db is None:
            with self.connect() as connection:
                return self.require_admin(actor, db=connection)
        row = db.execute("SELECT * FROM users WHERE id=?", (actor["id"],)).fetchone()
        if not row or not row["active"] or not row["is_admin"]:
            raise RequestError("Administrator access is required.", 403)

    def update_user(
        self,
        actor: dict,
        identifier: str,
        changes: dict,
        *,
        token: str | None = None,
        trusted: bool = False,
    ) -> dict:
        self.require_admin(actor)
        if not changes or set(changes) - {
            "active",
            "is_admin",
            "password",
            "display_name",
        }:
            raise RequestError(
                "Choose account status, role, name, or a new passphrase."
            )
        for key in ("active", "is_admin"):
            if key in changes and not isinstance(changes[key], bool):
                raise RequestError(f"{key} must be true or false.")
        if "display_name" in changes:
            changes = {**changes, "display_name": _name(changes["display_name"])}
        password = None
        if "password" in changes:
            value = _password(changes["password"])
            if not self.hash_slots.acquire(blocking=False):
                raise RequestError("Authentication is busy. Try again shortly.", 429)
            try:
                salt = secrets.token_bytes(16)
                password = (salt, _derive(value, salt))
            finally:
                self.hash_slots.release()
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not trusted:
                self._require_token(db, actor, token)
            self.require_admin(actor, db=db)
            row = db.execute("SELECT * FROM users WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise RequestError("Account not found.", 404)
            active = changes.get("active", bool(row["active"]))
            admin = changes.get("is_admin", bool(row["is_admin"]))
            if row["active"] and row["is_admin"] and not (active and admin):
                count = db.execute(
                    "SELECT COUNT(*) FROM users WHERE active=1 AND is_admin=1"
                ).fetchone()[0]
                if count <= 1:
                    raise RequestError("Keep at least one active administrator.", 409)
                if identifier == actor["id"]:
                    raise RequestError(
                        "Another administrator must change your administrator access.",
                        409,
                    )
            db.execute(
                "UPDATE users SET active=?,is_admin=?,display_name=?,salt=?,password=? WHERE id=?",
                (
                    int(active),
                    int(admin),
                    changes.get("display_name", row["display_name"]),
                    password[0] if password else row["salt"],
                    password[1] if password else row["password"],
                    identifier,
                ),
            )
            if password or not active or "is_admin" in changes:
                db.execute("DELETE FROM sessions WHERE user_id=?", (identifier,))
            self._audit(
                db,
                actor,
                "account_changed",
                details={"user_id": identifier, "fields": sorted(changes)},
            )
            return _user(
                db.execute("SELECT * FROM users WHERE id=?", (identifier,)).fetchone()
            )

    def users(self, actor: dict) -> list[dict]:
        with self.connect() as db:
            self.require_admin(actor, db=db)
            return [
                _user(row)
                for row in db.execute("SELECT * FROM users ORDER BY username")
            ]

    def login(self, username: Any, password: Any, client: str) -> tuple[str, dict]:
        # Bound both the expensive work and the rate-limit table. Unknown usernames
        # perform the same derivation; errors do not reveal account existence.
        if (
            not isinstance(username, str)
            or not isinstance(password, str)
            or len(password) > 1024
        ):
            raise RequestError("Username or passphrase is incorrect.", 401)
        username = username.strip().casefold()[:64]
        now = time.time()
        keys = ("ip:" + _digest(client), "name:" + _digest(username), "global")
        with self.lock:
            self.login_attempts = {
                key: [t for t in times if t > now - 300]
                for key, times in self.login_attempts.items()
                if times and times[-1] > now - 300
            }
            if len(self.login_attempts) > 4096:
                raise RequestError("Sign-in is temporarily rate limited.", 429)
            for key, limit in zip(keys, (20, 8, 100), strict=True):
                if len(self.login_attempts.get(key, [])) >= limit:
                    raise RequestError(
                        "Too many sign-in attempts. Try again in five minutes.", 429
                    )
            for key in keys:
                self.login_attempts.setdefault(key, []).append(now)
        if not self.hash_slots.acquire(blocking=False):
            raise RequestError("Sign-in is busy. Try again shortly.", 429)
        try:
            with self.connect() as db:
                row = db.execute(
                    "SELECT * FROM users WHERE username=?", (username,)
                ).fetchone()
            derived = _derive(password, row["salt"] if row else self.dummy_salt)
            if (
                not row
                or not hmac.compare_digest(derived, row["password"])
                or not row["active"]
            ):
                raise RequestError("Username or passphrase is incorrect.", 401)
        finally:
            self.hash_slots.release()
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.lock, self.connect() as db:
            current = db.execute(
                "SELECT * FROM users WHERE id=?", (row["id"],)
            ).fetchone()
            if not current["active"] or current["password"] != row["password"]:
                raise RequestError("Username or passphrase is incorrect.", 401)
            db.execute("DELETE FROM sessions WHERE expires<=?", (now,))
            # Eight simultaneous sessions per account; signing in invalidates oldest.
            old = db.execute(
                "SELECT digest FROM sessions WHERE user_id=? ORDER BY expires DESC",
                (row["id"],),
            ).fetchall()
            for entry in old[7:]:
                db.execute("DELETE FROM sessions WHERE digest=?", (entry["digest"],))
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?)",
                (_digest(token), row["id"], csrf, now + SESSION_SECONDS),
            )
            self._audit(db, _user(current), "signed_in")
        return token, {"authenticated": True, "user": _user(current), "csrf": csrf}

    def session(self, token: str | None) -> dict | None:
        if not token or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return None
        with self.connect() as db:
            row = db.execute(
                "SELECT u.*,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.digest=? AND s.expires>? AND u.active=1",
                (_digest(token), time.time()),
            ).fetchone()
            return (
                {"authenticated": True, "user": _user(row), "csrf": row["csrf"]}
                if row
                else None
            )

    def logout(self, token: str, actor: dict) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE digest=?", (_digest(token),))
            self._audit(db, actor, "signed_out")

    def change_password(
        self, actor: dict, current: str, new: str, client: str, *, token: str
    ) -> None:
        new = _password(new)
        temporary, _ = self.login(actor["username"], current, client)
        try:
            if not self.hash_slots.acquire(blocking=False):
                raise RequestError("Authentication is busy. Try again shortly.", 429)
            try:
                salt = secrets.token_bytes(16)
                password = _derive(new, salt)
            finally:
                self.hash_slots.release()
            with self.lock, self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                self._require_token(db, actor, token)
                row = db.execute(
                    "SELECT user_id FROM sessions WHERE digest=?", (_digest(temporary),)
                ).fetchone()
                if not row or row["user_id"] != actor["id"]:
                    raise RequestError(
                        "Sign in again before changing your passphrase.", 401
                    )
                db.execute(
                    "UPDATE users SET salt=?,password=? WHERE id=?",
                    (salt, password, actor["id"]),
                )
                db.execute("DELETE FROM sessions WHERE user_id=?", (actor["id"],))
                self._audit(db, actor, "passphrase_changed")
        finally:
            with self.connect() as db:
                db.execute("DELETE FROM sessions WHERE digest=?", (_digest(temporary),))

    def create_matter(
        self,
        actor: dict,
        title: str,
        *,
        token: str | None = None,
        trusted: bool = False,
    ) -> dict:
        title = _name(title)
        identifier = "matter-" + uuid.uuid4().hex
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not trusted:
                self._require_token(db, actor, token)
            self.require_admin(actor, db=db)
            if db.execute("SELECT COUNT(*) FROM matters").fetchone()[0] >= 1000:
                raise RequestError(
                    "This server has reached its 1,000-matter limit.", 409
                )
            db.execute(
                "INSERT INTO matters(id,title,workflow_secret,token) VALUES(?,?,?,?)",
                (identifier, title, secrets.token_hex(32), secrets.token_urlsafe(32)),
            )
            db.execute(
                "INSERT INTO members VALUES(?,?,?)",
                (identifier, actor["id"], "analyst"),
            )
            self._audit(db, actor, "matter_created", matter=identifier, revision=0)
        return self.matter(actor, identifier)

    def list_matters(self, actor: dict, *, admin: bool = False) -> list[dict]:
        with self.connect() as db:
            if admin:
                self.require_admin(actor, db=db)
                rows = db.execute(
                    "SELECT m.id,m.title,m.revision,b.role FROM matters m LEFT JOIN members b ON b.matter_id=m.id AND b.user_id=? ORDER BY m.title",
                    (actor["id"],),
                )
            else:
                rows = db.execute(
                    "SELECT m.id,m.title,m.revision,b.role FROM matters m JOIN members b ON b.matter_id=m.id WHERE b.user_id=? ORDER BY m.title",
                    (actor["id"],),
                )
            return [dict(row) for row in rows]

    def matter(self, actor: dict, identifier: str) -> dict:
        safe_id(identifier)
        with self.connect() as db:
            row = db.execute(
                "SELECT m.id,m.title,m.revision,b.role FROM matters m JOIN members b ON b.matter_id=m.id JOIN users u ON u.id=b.user_id WHERE m.id=? AND b.user_id=? AND u.active=1",
                (identifier, actor["id"]),
            ).fetchone()
            if not row:
                raise RequestError("This matter is unavailable to your account.", 403)
            return dict(row)

    def members(self, actor: dict, identifier: str) -> list[dict]:
        with self.connect() as db:
            self.require_admin(actor, db=db)
            if not db.execute(
                "SELECT 1 FROM matters WHERE id=?", (identifier,)
            ).fetchone():
                raise RequestError("Matter not found.", 404)
            return [
                {"user": _user(row), "role": row["role"]}
                for row in db.execute(
                    "SELECT u.*,b.role FROM members b JOIN users u ON u.id=b.user_id WHERE b.matter_id=? ORDER BY u.username",
                    (identifier,),
                )
            ]

    def set_member(
        self,
        actor: dict,
        identifier: str,
        user_id: str,
        role: str | None,
        *,
        expected: int | None = None,
        token: str | None = None,
        trusted: bool = False,
    ) -> dict:
        if role is not None and (not isinstance(role, str) or role not in ROLES):
            raise RequestError(
                "Choose analyst, reviewer, viewer, or null to remove access."
            )
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not trusted:
                self._require_token(db, actor, token)
            self.require_admin(actor, db=db)
            if expected is not None:
                current = db.execute(
                    "SELECT revision FROM matters WHERE id=?", (identifier,)
                ).fetchone()
                if not current or current["revision"] != expected:
                    raise RequestError(
                        "Workspace access changed. Review current membership before updating it.",
                        409,
                    )
            if (
                not db.execute(
                    "SELECT 1 FROM matters WHERE id=?", (identifier,)
                ).fetchone()
                or not db.execute(
                    "SELECT 1 FROM users WHERE id=?", (user_id,)
                ).fetchone()
            ):
                raise RequestError("Matter or account not found.", 404)
            if role is None:
                db.execute(
                    "DELETE FROM members WHERE matter_id=? AND user_id=?",
                    (identifier, user_id),
                )
            else:
                db.execute(
                    "INSERT INTO members VALUES(?,?,?) ON CONFLICT(matter_id,user_id) DO UPDATE SET role=excluded.role",
                    (identifier, user_id, role),
                )
            db.execute(
                "UPDATE matters SET revision=revision+1 WHERE id=?", (identifier,)
            )
            revision = db.execute(
                "SELECT revision FROM matters WHERE id=?", (identifier,)
            ).fetchone()[0]
            self._audit(
                db,
                actor,
                "membership_changed",
                matter=identifier,
                revision=revision,
                details={"user_id": user_id, "role": role},
            )
            return {"revision": revision, "user_id": user_id, "role": role}

    def context(self, identifier: str) -> dict:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM matters WHERE id=?", (identifier,)
            ).fetchone()
            if not row:
                raise RequestError("Matter not found.", 404)
            return dict(row)

    def workspace_path(self, identifier: str) -> Path:
        return safe_child(self.root / "matters", safe_id(identifier))

    def begin_mutation(
        self,
        actor: dict,
        identifier: str,
        expected: int,
        action: str,
        *,
        token: str | None = None,
        trusted: bool = False,
        roles: frozenset[str] = ROLES,
    ) -> int:
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not trusted:
                self._require_token(db, actor, token)
                member = db.execute(
                    "SELECT role FROM members WHERE matter_id=? AND user_id=?",
                    (identifier, actor["id"]),
                ).fetchone()
                if not member or member["role"] not in roles:
                    raise RequestError(
                        "Your current role does not permit this action.", 403
                    )
            changed = db.execute(
                "UPDATE matters SET revision=revision+1 WHERE id=? AND revision=?",
                (identifier, expected),
            ).rowcount
            if changed != 1:
                raise RequestError(
                    "This matter changed. Keep your draft and reload before saving.",
                    409,
                )
            revision = expected + 1
            self._audit(
                db, actor, action + ":started", matter=identifier, revision=revision
            )
            return revision

    def finish_mutation(
        self,
        actor: dict,
        identifier: str,
        revision: int,
        action: str,
        guided_runs: dict,
        *,
        status: int,
        author: tuple[str, str] | None = None,
    ) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE matters SET guided_runs=? WHERE id=?",
                (canonical_json(guided_runs).decode(), identifier),
            )
            if author and status < 400:
                db.execute(
                    "INSERT INTO authors VALUES(?,?,?)",
                    (identifier, author[0], author[1]),
                )
            # Completion has its own durable revision. A listener that saw the
            # started event must also be able to observe completion/failure.
            db.execute(
                "UPDATE matters SET revision=revision+1 WHERE id=?", (identifier,)
            )
            completed = db.execute(
                "SELECT revision FROM matters WHERE id=?", (identifier,)
            ).fetchone()[0]
            self._audit(
                db,
                actor,
                action + ":finished",
                matter=identifier,
                revision=completed,
                details={"status": status, "started_revision": revision},
            )

    def events(self, actor: dict, identifier: str, after: int) -> dict:
        matter = self.matter(actor, identifier)
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM audit WHERE matter_id=? AND revision>? ORDER BY id LIMIT 101",
                (identifier, after),
            )
            events = [
                {
                    "id": row["id"],
                    "revision": row["revision"],
                    "actor": {"id": row["actor_id"], "display_name": row["actor_name"]},
                    "action": row["action"],
                    "at": row["at"],
                    "details": json.loads(row["details"]),
                }
                for row in rows
            ]
        has_more = len(events) > 100
        events = events[:100]
        return {
            "revision": matter["revision"],
            "events": events,
            "next_after": events[-1]["revision"] if has_more else matter["revision"],
            "has_more": has_more,
        }

    def _audit(
        self,
        db,
        actor: dict,
        action: str,
        *,
        matter: str | None = None,
        revision: int | None = None,
        details: dict | None = None,
    ) -> None:
        db.execute(
            "INSERT INTO audit(matter_id,revision,actor_id,actor_name,action,at,details) VALUES(?,?,?,?,?,?,?)",
            (
                matter,
                revision,
                actor["id"],
                actor["display_name"],
                action,
                utc_now(),
                canonical_json(details or {}).decode(),
            ),
        )

    def approval_records(
        self, identifier: str, run_id: str, digest: str | None, review_id: str | None
    ) -> tuple[dict | None, list[dict], str | None]:
        with self.connect() as db:
            row = (
                db.execute(
                    "SELECT * FROM submissions WHERE matter_id=? AND package_sha256=?",
                    (identifier, digest),
                ).fetchone()
                if digest
                else None
            )
            submission = (
                {
                    "submitted_by": {
                        "id": row["user_id"],
                        "display_name": row["user_name"],
                    },
                    "at": row["at"],
                }
                if row
                else None
            )
            author = (
                db.execute(
                    "SELECT user_id FROM authors WHERE matter_id=? AND review_id=?",
                    (identifier, review_id),
                ).fetchone()
                if review_id
                else None
            )
            decisions = [
                {
                    "id": r["id"],
                    "reviewer": {"id": r["user_id"], "display_name": r["user_name"]},
                    "decision": r["decision"],
                    "note": r["note"],
                    "at": r["at"],
                    "package_sha256": r["package_sha256"],
                    "current": r["package_sha256"] == digest,
                }
                for r in db.execute(
                    "SELECT * FROM decisions WHERE matter_id=? AND run_id=? ORDER BY at,id",
                    (identifier, run_id),
                )
            ]
            return submission, decisions, author["user_id"] if author else None

    def _require_token(self, db, actor: dict, token: str | None) -> None:
        if not isinstance(token, str) or not token:
            raise RequestError("A live session is required for this change.", 401)
        row = db.execute(
            "SELECT u.id FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.digest=? AND s.expires>? AND u.active=1",
            (_digest(token), time.time()),
        ).fetchone()
        if not row or row["id"] != actor["id"]:
            raise RequestError(
                "Sign in again; your account or session access changed.", 401
            )

    def _authorize_commit(
        self, db, actor: dict, identifier: str, token: str, role: str
    ) -> None:
        row = db.execute(
            "SELECT u.id,b.role FROM sessions s JOIN users u ON u.id=s.user_id JOIN members b ON b.user_id=u.id WHERE s.digest=? AND s.expires>? AND u.active=1 AND b.matter_id=?",
            (_digest(token), time.time(), identifier),
        ).fetchone()
        if not row or row["id"] != actor["id"]:
            raise RequestError(
                "Sign in again; your account or session access changed.", 401
            )
        if row["role"] != role:
            raise RequestError("Your role no longer permits this action.", 403)

    def submit(
        self, actor: dict, identifier: str, package: dict, *, token: str
    ) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._authorize_commit(db, actor, identifier, token, "analyst")
            author = db.execute(
                "SELECT user_id FROM authors WHERE matter_id=? AND review_id=?",
                (identifier, package["review_id"]),
            ).fetchone()
            if not author:
                raise RequestError(
                    "Save an authenticated team assessment before submission.", 403
                )
            existing = db.execute(
                "SELECT * FROM submissions WHERE matter_id=? AND package_sha256=?",
                (identifier, package["package_sha256"]),
            ).fetchone()
            if existing and existing["user_id"] != actor["id"]:
                raise RequestError(
                    "This package already has a recorded submitter.", 409
                )
            if not existing:
                db.execute(
                    "INSERT INTO submissions VALUES(?,?,?,?,?,?)",
                    (
                        identifier,
                        package["package_sha256"],
                        package["run_id"],
                        actor["id"],
                        actor["display_name"],
                        utc_now(),
                    ),
                )

    def decide(
        self,
        actor: dict,
        identifier: str,
        package: dict,
        decision: str,
        note: str,
        *,
        token: str,
    ) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._authorize_commit(db, actor, identifier, token, "reviewer")
            author = db.execute(
                "SELECT user_id FROM authors WHERE matter_id=? AND review_id=?",
                (identifier, package["review_id"]),
            ).fetchone()
            submitter = db.execute(
                "SELECT user_id FROM submissions WHERE matter_id=? AND package_sha256=?",
                (identifier, package["package_sha256"]),
            ).fetchone()
            if (
                not author
                or not submitter
                or actor["id"] in {author["user_id"], submitter["user_id"]}
            ):
                raise RequestError(
                    "A distinct reviewer account is required for this submitted package.",
                    403,
                )
            db.execute(
                "INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    "decision-" + uuid.uuid4().hex,
                    identifier,
                    package["package_sha256"],
                    package["run_id"],
                    actor["id"],
                    actor["display_name"],
                    decision,
                    note,
                    utc_now(),
                ),
            )

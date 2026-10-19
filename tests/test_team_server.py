"""Team authorization is enforced by the server, independent of the interface."""

from __future__ import annotations

import asyncio
import base64
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from test_case_handoff import package as package
from test_case_review import case_review as legacy_case_review
from test_workflow import workspace as workspace

from omphalos import team_store
from omphalos.cli import dispatch, parser
from omphalos.team import TeamApp, _public, serve_team
from omphalos.util import sha256_bytes

PASSWORD = "A synthetic passphrase 2026"
ORIGIN = "http://127.0.0.1:8770"


class Client:
    def __init__(self, app, username=None):
        self.app = app
        self.cookie = ""
        self.csrf = ""
        self.revision = 0
        if username:
            status, _, _ = self.request(
                "login", {"username": username, "password": PASSWORD}
            )
            assert status == 200

    def request(
        self, path, body=None, *, method=None, revision=None, headers=None, raw=False
    ):
        if not path.startswith("/"):
            path = "/team/api/" + path
        route, _, query = path.partition("?")
        content = json.dumps(body).encode() if body is not None else b""
        values = {"host": "127.0.0.1:8770", "origin": ORIGIN, "cookie": self.cookie}
        if body is not None:
            values.update(
                {
                    "content-type": "application/json",
                    "content-length": str(len(content)),
                    "x-omphalos-csrf": self.csrf,
                    "if-match": f'"{self.revision if revision is None else revision}"',
                }
            )
        values.update(headers or {})
        scope = {
            "type": "http",
            "method": method or ("POST" if body is not None else "GET"),
            "path": route,
            "query_string": query.encode(),
            "headers": [(k.encode(), v.encode()) for k, v in values.items()],
            "client": ("127.0.0.1", 1234),
        }
        messages = []
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": content, "more_body": False}
            await asyncio.sleep(30)
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        asyncio.run(self.app(scope, receive, send))
        status = messages[0]["status"]
        returned_headers = {k.decode(): v.decode() for k, v in messages[0]["headers"]}
        content = b"".join(m.get("body", b"") for m in messages[1:])
        result = (
            content
            if raw
            or not returned_headers["content-type"].startswith("application/json")
            else json.loads(content)
        )
        if "set-cookie" in returned_headers:
            self.cookie = returned_headers["set-cookie"].split(";", 1)[0]
        if isinstance(result, dict) and result.get("csrf"):
            self.csrf = result["csrf"]
        if "x-omphalos-revision" in returned_headers:
            self.revision = int(returned_headers["x-omphalos-revision"])
        return status, result, returned_headers


@pytest.fixture
def team(tmp_path, monkeypatch):
    # Test authorization and concurrency quickly; one separate test checks the
    # production work factor. No shipped path changes its work factor dynamically.
    monkeypatch.setattr(team_store, "PASSWORD_ROUNDS", 1000)
    app = TeamApp(tmp_path / "team", origin=ORIGIN)
    admin = app.store.create_user(
        "admin", "Test administrator", PASSWORD, is_admin=True, trusted=True
    )
    users = {"admin": admin}
    for name in ("analyst", "reviewer", "viewer", "outsider"):
        users[name] = app.store.create_user(
            name, "Test " + name, PASSWORD, actor=admin, trusted=True
        )
    matter = app.store.create_matter(admin, "Private matter", trusted=True)
    for role in ("analyst", "reviewer", "viewer"):
        app.store.set_member(admin, matter["id"], users[role]["id"], role, trusted=True)
    return app, users, matter["id"]


def case_review(*args, **kwargs):
    return {**legacy_case_review(*args, **kwargs), "schema_version": "2.2"}


def engine(matter, path):
    return f"matters/{matter}/engine/{path}"


def active_client(team, user="analyst"):
    app, _, matter = team
    client = Client(app, user)
    assert client.request(engine(matter, "state"))[0] == 200
    return client


def import_fixture(team, package):
    _, _, raw = package
    client = active_client(team)
    matter = team[2]
    body = {
        "file": {"name": "case.zip", "content_base64": base64.b64encode(raw).decode()},
        "expected_sha256": sha256_bytes(raw),
    }
    status, imported, _ = client.request(engine(matter, "handoffs/import"), body)
    assert status == 200, imported
    return client, imported


def authenticated_package(team, package):
    client, imported = import_fixture(team, package)
    run_id = imported["run_id"]
    status, run, _ = client.request(engine(team[2], "runs/" + run_id))
    assert status == 200
    review = case_review(
        run, "keep_open", "Obtain the original contract and reconcile these records."
    )
    review["reviewer"] = "Forged colleague"
    status, saved, _ = client.request(engine(team[2], f"runs/{run_id}/review"), review)
    assert status == 200, saved
    assert saved["review"]["reviewer"] == "Test analyst"
    status, exported, _ = client.request(engine(team[2], f"runs/{run_id}/export"), {})
    assert status == 200, exported
    status, approval, _ = client.request(f"matters/{team[2]}/approval?run_id={run_id}")
    assert status == 200 and approval["can_submit"]
    return client, run_id, approval["package"]


def test_session_cookie_origin_csrf_and_logout(team):
    app, _, matter = team
    client = Client(app)
    assert client.request("session")[1] == {"authenticated": False}
    assert client.request(engine(matter, "state"))[0] == 401
    assert (
        client.request(
            "login",
            {"username": "admin", "password": PASSWORD},
            headers={"origin": "https://attacker.example"},
        )[0]
        == 403
    )
    status, session, headers = client.request(
        "login", {"username": "admin", "password": PASSWORD}
    )
    assert status == 200 and session["user"]["is_admin"]
    assert (
        "HttpOnly" in headers["set-cookie"]
        and "SameSite=Strict" in headers["set-cookie"]
    )
    assert (
        client.request(
            "matters", {"title": "Unwanted"}, headers={"x-omphalos-csrf": "wrong"}
        )[0]
        == 403
    )
    assert (
        client.request(
            "matters", {"title": "Unwanted"}, headers={"host": "attacker.example"}
        )[0]
        == 403
    )
    assert client.request("logout", {})[0] == 200
    assert client.request(engine(matter, "state"))[0] == 401


def test_https_secure_cookie_and_nonloopback_requires_https(tmp_path):
    with pytest.raises(ValueError, match="HTTPS"):
        TeamApp(tmp_path, origin="http://example.org")
    app = TeamApp(tmp_path, origin="https://example.org")
    assert "; Secure" in app._session_cookie("test")
    with pytest.raises(ValueError, match="HTTPS"):
        serve_team(tmp_path, host="0.0.0.0")
    with pytest.raises(ValueError, match="reverse proxy"):
        serve_team(
            tmp_path,
            host="0.0.0.0",
            behind_proxy=True,
            certfile=Path("a"),
            keyfile=Path("b"),
            origin="https://example.org",
        )


def test_roles_isolation_and_revocation(team):
    app, users, matter = team
    outsider = Client(app, "outsider")
    assert outsider.request("matters")[1] == {"matters": []}
    assert outsider.request(engine(matter, "state"))[0] == 403
    for name in ("reviewer", "viewer"):
        client = active_client(team, name)
        assert (
            client.request(engine(matter, "workflow/subject"), {"name": "Forbidden"})[0]
            == 403
        )
        assert client.request("admin/users")[0] == 403
    analyst = active_client(team)
    status, imported, _ = analyst.request(
        engine(matter, "workflow/subject"), {"name": "Visible only here"}
    )
    assert status == 200, imported
    second = app.store.create_matter(users["admin"], "Other matter", trusted=True)
    app.store.set_member(
        users["admin"], second["id"], users["analyst"]["id"], "analyst", trusted=True
    )
    assert analyst.request(engine(second["id"], "state"))[1]["datasets"] == []
    app.store.set_member(
        users["admin"], matter, users["analyst"]["id"], None, trusted=True
    )
    assert analyst.request(engine(matter, "state"))[0] == 403
    assert analyst.request(f"matters/{matter}/events?after=0&wait=0")[0] == 403


def test_revision_precondition_and_concurrent_writes(team):
    client = active_client(team)
    first = client.revision
    path = engine(team[2], "workflow/subject")
    assert (
        client.request(path, {"name": "No precondition"}, headers={"if-match": ""})[0]
        == 428
    )
    assert client.request(path, {"name": "First"}, revision=first)[0] == 200
    assert client.request(path, {"name": "Stale"}, revision=first)[0] == 409
    current = client.revision
    clients = [active_client(team), active_client(team)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda pair: pair[1].request(
                    path, {"name": f"Concurrent {pair[0]}"}, revision=current
                ),
                enumerate(clients),
            )
        )
    assert sorted(response[0] for response in responses) == [200, 409]
    datasets = client.request(engine(team[2], "state"))[1]["datasets"]
    assert len(datasets) == 2


def test_completion_events_and_context_survive_restart(team):
    app, users, matter = team
    client = active_client(team)
    start = client.revision
    assert (
        client.request(
            engine(matter, "workflow/subject"), {"name": "Persistent subject"}
        )[0]
        == 200
    )
    status, changes, _ = client.request(f"matters/{matter}/events?after={start}&wait=0")
    assert status == 200
    assert [event["action"].split(":")[-1] for event in changes["events"]] == [
        "started",
        "finished",
    ]
    assert changes["events"][1]["revision"] > changes["events"][0]["revision"]
    late = app.store.events(users["analyst"], matter, changes["events"][0]["revision"])
    assert late["events"][0]["action"].endswith(":finished")
    context = app._context(matter)
    secret = context.workflow_secret
    context.guided_runs["case-test"] = "a" * 64
    app.store.finish_mutation(
        users["analyst"],
        matter,
        client.revision,
        "fixture",
        context.guided_runs,
        status=200,
    )
    reopened = TeamApp(app.store.root, origin=ORIGIN)
    assert reopened._context(matter).workflow_secret == secret
    assert reopened._context(matter).guided_runs == context.guided_runs
    assert reopened.store.session(client.cookie.partition("=")[2])
    assert (
        reopened._context(matter).workspace.list_datasets()[0]["label"]
        == "Persistent subject"
    )


def test_imported_package_requires_authenticated_assessment_and_download_is_scoped(
    team, package
):
    client, imported = import_fixture(team, package)
    run_id = imported["run_id"]
    status, approval, _ = client.request(f"matters/{team[2]}/approval?run_id={run_id}")
    assert status == 200 and not approval["can_submit"]
    assert "fresh assessment" in approval["submission_blocker"]
    assert (
        client.request(
            f"matters/{team[2]}/submission",
            {"run_id": run_id, "package_sha256": approval["package"]["package_sha256"]},
        )[0]
        == 403
    )
    url = imported["download_url"]
    assert url.startswith(f"/team/api/matters/{team[2]}/engine/exports/")
    status, raw, headers = client.request(url, raw=True)
    assert status == 200 and raw == package[2]
    assert headers["content-type"] == "application/zip"
    assert "attachment" in headers["content-disposition"]
    outsider = Client(team[0], "outsider")
    assert outsider.request(url)[0] == 403
    assert client.request(url, method="HEAD")[0] == 405
    team[0].store.set_member(
        team[1]["admin"], team[2], team[1]["analyst"]["id"], None, trusted=True
    )
    assert client.request(url)[0] == 403


def test_approval_is_independent_exact_and_preserves_conflicts(team, package):
    client, run_id, item = authenticated_package(team, package)
    matter = team[2]
    body = {"run_id": run_id, "package_sha256": item["package_sha256"]}
    assert client.request(f"matters/{matter}/submission", body)[0] == 200
    reviewer = active_client(team, "reviewer")
    decision = {
        **body,
        "decision": "approve",
        "note": "The records support the documented next step.",
    }
    assert (
        reviewer.request(
            f"matters/{matter}/approval", {**decision, "package_sha256": "0" * 64}
        )[0]
        == 409
    )
    assert reviewer.request(f"matters/{matter}/approval", decision)[0] == 200
    assert (
        reviewer.request(
            f"matters/{matter}/approval",
            {
                **decision,
                "decision": "request_changes",
                "note": "A later check identifies an unresolved source gap.",
            },
        )[0]
        == 200
    )
    result = reviewer.request(f"matters/{matter}/approval?run_id={run_id}")[1]
    assert {row["decision"] for row in result["decisions"]} == {
        "approve",
        "request_changes",
    }
    assert all(row["current"] for row in result["decisions"])
    # Changing the analyst assessment invalidates the package and all approvals.
    client.request(engine(matter, "state"))
    run = client.request(engine(matter, "runs/" + run_id))[1]
    assert (
        client.request(
            engine(matter, f"runs/{run_id}/review"),
            case_review(
                run,
                "keep_open",
                "New evidence must be reconciled before concluding this matter.",
            ),
        )[0]
        == 200
    )
    updated = reviewer.request(f"matters/{matter}/approval?run_id={run_id}")[1]
    assert updated["package"] is None
    assert not any(row["current"] for row in updated["decisions"])


def test_original_assessment_author_cannot_review_after_role_reassignment(
    team, package
):
    client, run_id, item = authenticated_package(team, package)
    app, users, matter = team
    admin = active_client(team, "admin")
    body = {"run_id": run_id, "package_sha256": item["package_sha256"]}
    assert admin.request(f"matters/{matter}/submission", body)[0] == 200
    app.store.set_member(
        users["admin"], matter, users["analyst"]["id"], "reviewer", trusted=True
    )
    client.request(engine(matter, "state"))
    assert not client.request(f"matters/{matter}/approval?run_id={run_id}")[1][
        "can_review"
    ]
    assert (
        client.request(
            f"matters/{matter}/approval",
            {
                **body,
                "decision": "approve",
                "note": "Attempted self-review with a different submitter.",
            },
        )[0]
        == 403
    )
    app.store.set_member(
        users["admin"], matter, users["admin"]["id"], "reviewer", trusted=True
    )
    admin.request(engine(matter, "state"))
    assert (
        admin.request(
            f"matters/{matter}/approval",
            {
                **body,
                "decision": "approve",
                "note": "Attempted review by the submitting account.",
            },
        )[0]
        == 403
    )


def test_account_deactivation_password_reset_and_last_admin(team):
    app, users, matter = team
    analyst = active_client(team)
    admin = Client(app, "admin")
    assert (
        admin.request("admin/users/" + users["admin"]["id"], {"active": False})[0]
        == 409
    )
    assert (
        admin.request("admin/users/" + users["analyst"]["id"], {"active": False})[0]
        == 200
    )
    assert analyst.request(engine(matter, "state"))[0] == 401
    assert (
        admin.request("admin/users/" + users["analyst"]["id"], {"active": True})[0]
        == 200
    )
    analyst = active_client(team)
    assert (
        analyst.request(
            "password",
            {
                "current_password": "Incorrect password",
                "new_password": "A replacement passphrase 2026",
            },
        )[0]
        == 401
    )
    assert (
        analyst.request(
            "password",
            {
                "current_password": PASSWORD,
                "new_password": "A replacement passphrase 2026",
            },
        )[0]
        == 200
    )
    assert analyst.request(engine(matter, "state"))[0] == 401
    assert (
        analyst.request("login", {"username": "analyst", "password": PASSWORD})[0]
        == 401
    )
    assert (
        analyst.request(
            "login",
            {"username": "analyst", "password": "A replacement passphrase 2026"},
        )[0]
        == 200
    )


def test_login_rate_limits_and_password_storage(team):
    app, users, _ = team
    client = Client(app)
    for _ in range(8):
        assert (
            client.request("login", {"username": "unknown", "password": PASSWORD})[0]
            == 401
        )
    assert (
        client.request("login", {"username": "unknown", "password": PASSWORD})[0] == 429
    )
    with app.store.connect() as db:
        row = db.execute(
            "SELECT password,salt FROM users WHERE id=?", (users["admin"]["id"],)
        ).fetchone()
    assert len(row["password"]) == 32 and len(row["salt"]) == 16
    assert PASSWORD.encode() not in app.store.db_path.read_bytes()


def test_no_process_wide_token_or_path_exposed_and_canonical_routes(team):
    client = active_client(team)
    state = client.request(engine(team[2], "state"))[1]
    assert state["token"] == "" and state["mode"] == "team"
    assert str(team[0].store.root) not in json.dumps(state)
    assert client.request(engine(team[2], "runs/not-real%2Freview"), {})[0] == 400
    assert client.request("session", method="HEAD")[0] == 405


def test_process_lease_and_cli_init(tmp_path, monkeypatch):
    monkeypatch.setattr(team_store, "PASSWORD_ROUNDS", 1000)
    monkeypatch.setattr("getpass.getpass", lambda _: PASSWORD)
    args = parser().parse_args(
        [
            "--workspace",
            str(tmp_path / "team"),
            "team",
            "init",
            "--username",
            "owner",
            "--name",
            "Test owner",
        ]
    )
    result = dispatch(args)
    assert result["is_admin"]
    with pytest.raises(ValueError, match="already initialized"):
        dispatch(args)
    first = TeamApp(tmp_path / "team", origin=ORIGIN)
    second = TeamApp(tmp_path / "team", origin=ORIGIN)
    first._lease()
    try:
        with pytest.raises((RuntimeError, OSError)):
            second._lease()
    finally:
        first.lease.close()
        if second.lease:
            second.lease.close()


def test_secure_production_work_factor():
    assert team_store.PASSWORD_ROUNDS >= 600_000


def test_admin_access_required_before_context_creation(team):
    client = Client(team[0], "outsider")
    status, _, _ = client.request(
        f"admin/matters/{team[2]}/members",
        {"user_id": team[1]["outsider"]["id"], "role": "analyst"},
    )
    assert status == 403
    assert not team[0].store.list_matters(team[1]["outsider"])


def test_long_poll_rechecks_revoked_membership(team):
    app, users, matter = team
    client = active_client(team)
    before = client.revision
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(
            client.request, f"matters/{matter}/events?after={before}&wait=5"
        )
        app.store.set_member(
            users["admin"], matter, users["analyst"]["id"], None, trusted=True
        )
        assert pending.result(timeout=8)[0] == 403


def test_event_pagination_preserves_every_completed_event(team):
    app, users, matter = team
    for _ in range(60):
        revision = app.store.matter(users["analyst"], matter)["revision"]
        started = app.store.begin_mutation(
            users["analyst"], matter, revision, "test", trusted=True
        )
        app.store.finish_mutation(
            users["analyst"], matter, started, "test", {}, status=200
        )
    after, collected = 0, []
    while True:
        page = app.store.events(users["analyst"], matter, after)
        collected.extend(page["events"])
        after = page["next_after"]
        if not page["has_more"]:
            break
    assert len({event["id"] for event in collected}) == 123
    assert sum(event["action"] == "test:finished" for event in collected) == 60
    assert after == page["revision"]


def test_scoping_preserves_literal_evidence_paths_and_text():
    original = {
        "record": {
            "name": "/api/customer",
            "raw_record": {
                "path": "/original/source/path",
                "download_url": "/api/exports/not-an-application-link.zip",
            },
        },
        "latest_export": {"download_url": "/api/exports/package.zip"},
        "path": "/private/server/path",
    }
    result = _public(original, "/team/api/matters/example/engine/")
    assert result["record"] == original["record"]
    assert "path" not in result
    assert (
        result["latest_export"]["download_url"]
        == "/team/api/matters/example/engine/exports/package.zip"
    )
    assert original["latest_export"]["download_url"] == "/api/exports/package.zip"


def test_unauthorized_password_change_does_not_start_hashing(team, monkeypatch):
    client = Client(team[0], "viewer")

    def forbidden(*args):
        raise AssertionError("Unauthorized actor reached password derivation")

    monkeypatch.setattr(team_store, "_derive", forbidden)
    assert (
        client.request(
            "admin/users/" + team[1]["analyst"]["id"],
            {"password": "An unauthorized replacement password"},
        )[0]
        == 403
    )


def test_stale_administrator_cannot_restore_revoked_membership(team):
    admin = Client(team[0], "admin")
    path = f"admin/matters/{team[2]}/members"
    assert admin.request(path)[0] == 200
    old_revision = admin.revision
    body = {"user_id": team[1]["analyst"]["id"], "role": None}
    assert admin.request(path, body)[0] == 200
    assert (
        admin.request(path, {**body, "role": "analyst"}, revision=old_revision)[0]
        == 409
    )
    assert not team[0].store.list_matters(team[1]["analyst"])


@pytest.mark.parametrize("revocation", ["disable", "password_reset"])
def test_revoked_reviewer_cannot_commit_an_approval_after_validation(
    team, package, monkeypatch, revocation
):
    analyst, run_id, item = authenticated_package(team, package)
    app, users, matter = team
    payload = {"run_id": run_id, "package_sha256": item["package_sha256"]}
    assert analyst.request(f"matters/{matter}/submission", payload)[0] == 200
    reviewer = active_client(team, "reviewer")
    original = app.store.decide

    def revoke_before_commit(*args, **kwargs):
        changes = (
            {"active": False}
            if revocation == "disable"
            else {"password": "An administrator replacement passphrase"}
        )
        app.store.update_user(
            users["admin"], users["reviewer"]["id"], changes, trusted=True
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(app.store, "decide", revoke_before_commit)
    response = reviewer.request(
        f"matters/{matter}/approval",
        {
            **payload,
            "decision": "approve",
            "note": "A decision racing with account revocation.",
        },
    )
    assert response[0] in {401, 403}
    with app.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0


@pytest.mark.parametrize(
    "operation", ["create_user", "update_user", "create_matter", "set_member"]
)
@pytest.mark.parametrize("revocation", [None, "password_reset", "disable"])
def test_privileged_write_rechecks_actual_session_at_commit(
    team, monkeypatch, operation, revocation
):
    app, users, matter = team
    second = app.store.create_user(
        "second-admin",
        "Other administrator",
        PASSWORD,
        is_admin=True,
        actor=users["admin"],
        trusted=True,
    )
    client = Client(app, "admin")
    client.request(f"admin/matters/{matter}/members")
    routes = {
        "create_user": (
            "admin/users",
            {
                "username": "unwanted-admin",
                "display_name": "New administrator",
                "password": PASSWORD,
                "is_admin": True,
            },
        ),
        "update_user": ("admin/users/" + users["outsider"]["id"], {"active": False}),
        "create_matter": ("matters", {"title": "Racing matter"}),
        "set_member": (
            f"admin/matters/{matter}/members",
            {"user_id": users["outsider"]["id"], "role": "analyst"},
        ),
    }
    original = getattr(app.store, operation)
    updater = app.store.update_user

    def revoke_then_write(*args, **kwargs):
        if revocation:
            changes = (
                {"password": "Administrator reset during request"}
                if revocation == "password_reset"
                else {"active": False}
            )
            updater(second, users["admin"]["id"], changes, trusted=True)
        return original(*args, **kwargs)

    monkeypatch.setattr(app.store, operation, revoke_then_write)
    response = client.request(*routes[operation])
    assert response[0] in ({401, 403} if revocation else {200})
    with app.store.connect() as db:
        actual = {
            "create_user": bool(
                db.execute(
                    "SELECT 1 FROM users WHERE username='unwanted-admin'"
                ).fetchone()
            ),
            "update_user": not bool(
                db.execute(
                    "SELECT active FROM users WHERE id=?", (users["outsider"]["id"],)
                ).fetchone()[0]
            ),
            "create_matter": bool(
                db.execute(
                    "SELECT 1 FROM matters WHERE title='Racing matter'"
                ).fetchone()
            ),
            "set_member": bool(
                db.execute(
                    "SELECT 1 FROM members WHERE matter_id=? AND user_id=?",
                    (matter, users["outsider"]["id"]),
                ).fetchone()
            ),
        }
    assert actual[operation] is (revocation is None)


def test_account_creation_rechecks_session_after_expensive_hashing(team, monkeypatch):
    app, users, _ = team
    second = app.store.create_user(
        "second-admin",
        "Other administrator",
        PASSWORD,
        is_admin=True,
        actor=users["admin"],
        trusted=True,
    )
    client = Client(app, "admin")
    original = team_store._derive
    wanted = "A new administrative account passphrase"

    def derive(password, salt):
        if password == wanted:
            app.store.update_user(
                second,
                users["admin"]["id"],
                {"password": "Reset before account creation commits"},
                trusted=True,
            )
        return original(password, salt)

    monkeypatch.setattr(team_store, "_derive", derive)
    assert (
        client.request(
            "admin/users",
            {
                "username": "unwanted-admin",
                "display_name": "Unwanted",
                "password": wanted,
                "is_admin": True,
            },
        )[0]
        == 401
    )
    with app.store.connect() as db:
        assert not db.execute(
            "SELECT 1 FROM users WHERE username='unwanted-admin'"
        ).fetchone()


def test_password_change_checks_original_session_after_admin_reset(team, monkeypatch):
    app, users, _ = team
    client = Client(app, "analyst")
    original = team_store._derive
    requested = "Analyst's requested new passphrase"
    reset = "Administrator reset before commit"

    def derive(password, salt):
        if password == requested:
            app.store.update_user(
                users["admin"],
                users["analyst"]["id"],
                {"password": reset},
                trusted=True,
            )
        return original(password, salt)

    monkeypatch.setattr(team_store, "_derive", derive)
    assert (
        client.request(
            "password", {"current_password": PASSWORD, "new_password": requested}
        )[0]
        == 401
    )
    assert (
        client.request("login", {"username": "analyst", "password": requested})[0]
        == 401
    )
    assert client.request("login", {"username": "analyst", "password": reset})[0] == 200


def test_team_requires_current_explained_assessment_but_retains_legacy_archive(
    team, package
):
    client, imported = import_fixture(team, package)
    run_id = imported["run_id"]
    run = client.request(engine(team[2], "runs/" + run_id))[1]
    assert run["latest_review"]["review"]["schema_version"] == "2.1"
    assert "path" not in run["latest_review"]
    legacy = legacy_case_review(run, "keep_open", "")
    assert client.request(engine(team[2], f"runs/{run_id}/review"), legacy)[0] == 400
    assert (
        client.request(
            engine(team[2], f"runs/{run_id}/review"),
            {**legacy, "schema_version": "2.2"},
        )[0]
        == 400
    )
    preserved = client.request(engine(team[2], "runs/" + run_id))[1]
    assert preserved["latest_review"]["review_id"] == run["latest_review"]["review_id"]


def test_internal_privileged_calls_require_explicit_trust_or_a_live_session(team):
    app, users, _ = team
    with pytest.raises(ValueError, match="live session"):
        app.store.create_matter(users["admin"], "An implicit bypass")

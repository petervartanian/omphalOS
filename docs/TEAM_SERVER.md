# Optional shared team server

The public website runs entirely in each visitor's browser. The optional team server adds centrally enforced accounts, matter access, shared records, authenticated assessment authorship, independent package review, and notifications when another member changes a matter. It uses the same Python analysis engine. It does not change the public website into a hosted multiuser service.

The software has no subscription or usage fee. An existing computer or organization server can host it. That host must remain available, and its operator is responsible for HTTPS, backups, updates, and access decisions. This release does not provision a public host, create a cloud account, or purchase a service.

## Start on this computer

From the omphalOS source repository, install the optional dependencies and use a separate directory from any existing single-user workspace:

```sh
python -m pip install '.[team]'
omphalos --workspace /path/to/team-workspace team init --username owner --name 'Your name'
omphalos --workspace /path/to/team-workspace team serve
```

Initialization prompts for the first administrator's passphrase twice without putting it in shell history or command arguments. Use 14–256 characters. Open `http://127.0.0.1:8770` yourself; the server does not open or raise a browser. The first administrator creates a matter, creates team accounts, and assigns membership from **Workspaces → Manage team**. Account holders can change their initial passphrase after signing in. Passphrase changes revoke all of that account's sessions.

Each matter is an isolated engine workspace. Its administrator is initially assigned as an analyst. Creating an account does not grant access to any other matter. An administrator may administer membership without reading a matter unless explicitly assigned membership.

## Roles and workflow

| Role | Permitted work |
| --- | --- |
| Analyst | Import records and packages, inspect evidence, prepare and authorize checks, run analysis, save assessments, produce and submit packages. |
| Reviewer | Read and download the matter, verify or replay a run, and record an independent decision on a submitted package. |
| Viewer | Read and download the matter, and verify or replay a run. |
| Administrator | Create and disable accounts, create matters, and assign membership. Administration does not bypass a matter's analyst/reviewer role or self-review restrictions. |

An analyst's saved assessment is attributed to their authenticated account, regardless of any name supplied by a modified client. A reviewer approves or requests changes against the exact current package digest. Both the submitting account and the account that authored the current assessment are excluded from independent approval, including after reassignment to a reviewer role. An imported package has no authenticated team author; it therefore requires a fresh assessment under a team account before submission for independent team review. The original imported package and provenance remain retained.

Reviewer decisions are separate from the analyst's assessment. Contrary decisions remain visible together, and changed assessments or packages invalidate the prior package's current approval status. The account system establishes distinct accounts, not proof of distinct humans or an agency's employment authority; administrators must enroll actual people accurately. Browser signed receipts remain a separate portable protocol, not substitutes for server-enforced membership.

Several people may inspect and work in a matter at once. Saves use the revision that each person actually opened. If another person changes the matter, the interface preserves the draft and requires explicit reloading before another save; the server rejects stale writes even if the client is modified. This is shared case work with conflict detection, not simultaneous character-by-character text merging.

## HTTPS deployment

The default listener accepts only local connections. Direct access from another computer requires a certificate and private key:

```sh
omphalos --workspace /path/to/team-workspace team serve \
  --host 0.0.0.0 --port 8770 \
  --origin https://omphalos.example.org:8770 \
  --certfile /path/to/fullchain.pem --keyfile /path/to/privkey.pem
```

Alternatively, put an existing HTTPS reverse proxy in front of a loopback-only listener:

```sh
omphalos --workspace /path/to/team-workspace team serve \
  --host 127.0.0.1 --port 8770 \
  --origin https://omphalos.example.org --behind-proxy
```

The proxy must forward the exact configured `Host`, retain the browser's `Origin`, disable response caching, enforce request limits, and expose only the HTTPS endpoint. Forwarded identity and client-IP headers are not trusted. Consequently, login throttling behind a proxy conservatively shares its IP limit. No cross-origin browser credentials or automatic connection from the public website are enabled. A website link to an organization's separately hosted team origin is sufficient.

Only one server process may own a team directory; a lifetime operating-system lock enforces this. Run one Uvicorn worker with the h11 HTTP implementation. The supported launcher sets these options, disables access logs, and bounds concurrent connections, request work, upload size, upload duration, login hashing, and event waits. Horizontal scaling across copies of the same filesystem is unsupported.

## Persistence and recovery

The team directory contains `team.sqlite3` and one workspace under `matters/` per matter. Account password verifiers use salted PBKDF2-HMAC-SHA-256 with 600,000 iterations. Session cookies are HttpOnly, SameSite=Strict, and Secure when the configured origin is HTTPS; only session-token digests are stored. Sessions expire after eight hours. Role removal and account disabling are checked again on subsequent API calls, downloads, and bounded event waits.

SQLite retains membership, revisions, authenticated actor events, supervisor decisions, workflow secrets, and approval continuity. Every engine write is serialized per matter; a started operation consumes a revision before touching engine files, and completion consumes a further revision. A failed or interrupted operation does not silently restore an older revision. After a process failure, inspect the recorded started operation and retained engine state before retrying. Engine writes and their SQLite metadata are not one cross-filesystem transaction; an assessment lacking a completed authenticated-author record cannot receive independent team approval.

Back up the entire team directory while the server is stopped, including SQLite and any WAL files. Restore it into a separate directory and verify retained runs before using it. A browser workspace backup does not contain team identities or membership. The local administrator can reset another account's passphrase; there is no email reset service. Keep another active administrator for recovery. The last active administrator cannot be disabled or demoted through the application.

Records and database files are not encrypted by team mode. Use the host's disk encryption and organization backup protections. An operating-system administrator can alter files and the database; the authenticated activity history is not a tamper-proof ledger. Stop the team server before using filesystem tools or CLI commands against its matter directories.

## API boundaries

- `/team/api/session`, `/login`, `/logout`, and `/password` manage sessions and passphrases.
- `/team/api/matters` lists only assigned matters. Creating a matter requires an administrator.
- `/team/api/matters/{id}/engine/{path}` scopes the existing engine API and generated downloads to one matter. Engine mutations require `X-Omphalos-CSRF` and `If-Match: "<revision>"`. Responses expose `X-Omphalos-Revision`.
- `/team/api/matters/{id}/submission` and `/approval` bind team review to the current verified package. Their POST requests require the same preconditions.
- `/team/api/matters/{id}/events?after=<revision>&wait=<seconds>` waits at most 25 seconds, rechecking access during the wait. Responses include the current `revision`, up to 100 events, and `next_after`/`has_more` for lossless pagination. A history reader advances using `next_after`, not the current matter revision.
- `/team/api/admin/users` and `/admin/matters/{id}/members` manage accounts and assignment. Membership writes require the revision returned by the corresponding membership read; stale administration forms cannot silently restore revoked access.

Exact origin and host validation, CSRF tokens, duplicate-header rejection, request-size limits, and role authorization apply on the server. No administrative secret appears in a browser build. Team Python modules and team UI files are excluded from the static browser runtime.

## Free hosting choices and limits

An existing host is the implemented path. GitHub Pages is static hosting and cannot enforce team writes or run this service. [GitHub Pages documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/about-github-pages)

A separately implemented synchronization service could use Cloudflare Workers/D1 Free or Supabase Free, but neither is automatically provisioned here. Cloudflare Workers Free currently permits 100,000 requests/day and 10 ms CPU per invocation; D1 Free includes bounded reads/writes and 5 GB storage, returning quota errors when exhausted. Those limits do not fit the unchanged Python/filesystem engine without an adapter. [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/), [D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/)

Supabase Free currently includes 500 MB database storage, 1 GB files, and 5 GB egress; inactive projects pause after a week. Its default email sender is restricted to project-team addresses and two messages/hour, so ordinary invitation and account recovery need additional setup. [Supabase pricing](https://supabase.com/pricing), [SMTP restrictions](https://supabase.com/docs/guides/auth/auth-smtp)

These are deployment options, not claims that any provider offers unlimited capacity, assured availability, or an already configured omphalOS team service. No paid plan is required by this implementation.

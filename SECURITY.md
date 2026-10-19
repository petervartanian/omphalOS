# Security and trust boundaries

The local omphalOS server is a single-user application on a local computer. The operating-system user controls the files, process, and keys. Use OS account separation, disk protection, and appropriate backups for sensitive case material. Local mode does not implement multi-user authentication, role separation, remote access, or independently witnessed custody.

The local browser server accepts loopback hosts only, checks Host/Origin and a per-session mutation token, bounds request sizes, and uses contained paths. It loads packaged assets with no third-party scripts. Do not expose it through a reverse proxy or tunnel as a shared service.

The website edition loads a pinned Python runtime and engine from the same site into a dedicated worker. It opens no listening server and sends no case records to a hosted omphalOS backend. IndexedDB holds the browser workspace; a Web Lock permits one writer tab at a time. Other scripts served from the same website origin share the browser's origin boundary. Browser profiles and operating-system accounts provide user separation, not application accounts.

Browser storage may be removed by the user, private-browsing policies, or storage eviction. Download evidence packages for durable copies. Public-source requests use browser HTTPS and CORS enforcement. Direct CSL, GLEIF, and Wikidata requests are supported; standalone OFAC downloads require file import. Native detached Ed25519 signature verification remains available through the desktop command line and is not exposed as a browser capability.

The optional team server is a separate ASGI service. It requires authenticated sessions and per-matter membership for every case request and download, exact-origin CSRF protection for mutations, and a revision precondition for shared writes. It binds new assessments to server accounts and requires the supervisor reviewer to be distinct from both the assessment author and package submitter. An administrator enrolls people and assigns their roles; the application cannot establish that separate accounts correspond to separate real people. HTTPS is required outside loopback. Do not substitute the single-user server for team mode.

The team host and its administrator remain trusted: they control the database, stored evidence, application, and account enrollment. Team audit entries identify the authenticated account and server time but are not independently witnessed or protected against a malicious machine owner. Team files are not encrypted by the application. Back up the complete team directory, including its database; ordinary evidence ZIPs do not include team accounts, sessions, or later team decisions. See [team deployment and backup boundaries](docs/TEAM_SERVER.md).

Imports validate supported schema fields and references; original bytes and row provenance remain available. Analysis does not execute user-provided SQL or archived Python code. Official-source fetching uses fixed HTTPS endpoints and verified TLS. It is explicit and sends no case data.

Run and bundle verifiers require complete inventories and reject unsafe paths, symlinks, duplicate JSON keys, duplicate archive members, unsupported numbers, and missing or extra payload files. Review is anchored to the exact manifest. A machine owner can still replace files and recompute ordinary hashes; authenticity requires a separately trusted receipt/key. Optional Ed25519 verification does not supply a key-management system.

Export includes source records and code, not merely a summary. Review its sensitivity before sharing. The credential-pattern scan is a bounded defense against several recognizable secret formats, not a guarantee of complete secret or personal-data detection. Pattern details and limits are documented in the evidence implementation and guide.

If a verifier fails, retain the original files and investigate; do not rewrite their manifest to make the check pass. No cleanup command silently deletes evidence. Local-workspace events aid troubleshooting but are not an authenticated audit log.

Report a suspected defect to the repository maintainer without publishing sensitive case records or exploitable credentials. Provide a small synthetic reproduction where possible.

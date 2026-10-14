# Security and trust boundaries

omphalOS 2 is a single-user application on a local computer. The operating-system user controls the files, process, and keys. Use OS account separation, disk protection, and appropriate backups for sensitive case material. The application does not implement multi-user authentication, role separation, remote access, or independently witnessed custody.

The browser server accepts loopback hosts only, checks Host/Origin and a per-session mutation token, bounds request sizes, and uses contained paths. It loads packaged assets with no third-party scripts. Do not expose it through a reverse proxy or tunnel as a shared service.

Imports validate supported schema fields and references; original bytes and row provenance remain available. Analysis does not execute user-provided SQL or archived Python code. Official-source fetching uses fixed HTTPS endpoints and verified TLS. It is explicit and sends no case data.

Run and bundle verifiers require complete inventories and reject unsafe paths, symlinks, duplicate JSON keys, duplicate archive members, unsupported numbers, and missing or extra payload files. Review is anchored to the exact manifest. A machine owner can still replace files and recompute ordinary hashes; authenticity requires a separately trusted receipt/key. Optional Ed25519 verification does not supply a key-management system.

Export includes source records and code, not merely a summary. Review its sensitivity before sharing. The credential-pattern scan is a bounded defense against several recognizable secret formats, not a guarantee of complete secret or personal-data detection. Pattern details and limits are documented in the evidence implementation and guide.

If a verifier fails, retain the original files and investigate; do not rewrite their manifest to make the check pass. No cleanup command silently deletes evidence. Workspace events aid troubleshooting but are not an authenticated audit log.

Report a suspected defect to the repository maintainer without publishing sensitive case records or exploitable credentials. Provide a small synthetic reproduction where possible.

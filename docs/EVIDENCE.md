# Evidence records and portable exports

Every completed run preserves its case, normalized dataset and original inputs, selected source snapshot when used, analysis results and coverage, catalog, application source snapshot, and recorded environment. `manifest.json` inventories every regular file except itself with a relative path, SHA-256 digest, and byte count. Required artifacts cannot be removed from the inventory to disable verification. Unlisted files, duplicate entries, symbolic links, and unsupported paths fail verification.

Finalization is write-once through the application. A failed verification does not repair or silently replace a run. Operating-system owners can still modify their files; the application does not claim otherwise.

`analysis_digest` is recomputed from the actual analysis using the documented `omphalos-json-v1` encoding: UTF-8, sorted object keys, compact separators, no nonfinite values, and a terminating newline. Analysis numbers are signed 64-bit integers; decimals and larger exact numbers are strings. This is an application encoding, not a claim of RFC 8785 conformance. Timestamps and execution IDs remain outside the deterministic analytical content.

## Review

A named review must cover every finding exactly once, acknowledge coverage limitations, and supply a disposition, rationale, unknowns, alternatives, and falsifiers. A zero-findings result still needs a named reviewer, a substantive summary, and acknowledgment of limitations. Dataset references and source references must resolve to preserved records. Merely copying all generated uncertainty sections does not complete a review.

The immutable review wrapper records its own ID and timestamp and the SHA-256 of the exact run manifest reviewed. A review against a different manifest cannot authorize export. Review identities are self-asserted; text validation cannot establish the adequacy or truth of the reasoning.

The workbench shows a review as recorded only after checking its anchor and completeness. A damaged latest revision blocks the default export instead of silently selecting an older review. An explicitly selected, intact earlier revision can still be exported with its own attribution. Unreadable stored review records are reported for inspection.

## Bundle format 2.0

Export creates a real ZIP containing:

```text
bundle-manifest.json
README.txt
report.html
report.md
review.json
run/
  manifest.json
  case.json
  analysis.json
  catalog.json
  environment.json
  data/
  engine/
  sources/             when a source snapshot was used
```

This release uses a minimal, versioned omphalOS inventory format. It does not claim BagIt or RO-Crate conformance. Its descriptive metadata and exhaustive inventory could be mapped into those standards later without changing the underlying evidence.

`bundle-manifest.json` includes `schema_version`, `kind`, `run_id`, `analysis_digest`, `created_at`, and a nonempty `files` list. Each file entry has exactly `path`, `sha256`, and `size_bytes`. Every bundle file other than the bundle manifest is listed, including the embedded run manifest and review. The embedded run is checked again, not merely trusted because the outer ZIP is readable.

```sh
omphalos verify /absolute/path/to/evidence.zip
omphalos verify /absolute/path/to/run-directory
```

The bundle verifier reads bounded archive members without extracting them or executing archived code. Its default limits are 20,000 payload files, 256 MiB for one file, and 1 GiB total. Duplicate members, encrypted members, special-file members, unsupported paths, incorrect sizes, incomplete inventories, and changed digests fail verification. Passing ZIP CRC checks alone is insufficient.

Export first validates the run and exact review anchor, then builds and verifies a new bundle. Existing exports are never overwritten. Report HTML escapes supplied text; it contains no remote dependencies. Reports identify review attribution as self-asserted and report actual byte checks without claiming independent review or authenticated publication.

## Credential scan

The export path scans textual evidence and reports for defined patterns: AWS access-key prefixes, private-key headers, and sufficiently long password, token, API-key, access-token, or secret-key assignments. A match blocks export and identifies the artifact and pattern without printing the matched value. Archived implementation files under `engine/` are excluded because they contain scanner definitions and application source. Other binary and unrecognized text formats are outside this pattern scan.

This is a limited accidental-disclosure check. It is not a comprehensive secret detector or a classification-boundary control. Nothing in a successful scan establishes permission to distribute an input or report.

## Optional external signatures

```sh
omphalos verify-signature artifact.zip artifact.sig externally-trusted-public-key.pem
```

The optional signature verifier uses `cryptography` for Ed25519. The signature is the raw 64-byte detached signature over the exact artifact bytes; the external public key is PEM SubjectPublicKeyInfo. The caller supplies the trust decision. A public key bundled with an artifact is not automatically trusted. Verification reports the artifact and key fingerprints and whether that supplied key validates the signature. It does not claim the key belongs to a publisher without an external basis for that identity.

Checksums answer whether bytes agree with a supplied manifest. A trusted signature can additionally establish who signed those bytes. Neither establishes analytical truth. The Go and Rust tools provide independent inventory implementations, documented in `native/README.md`; they do not rerun investigations or review findings.

## Reproducibility and provenance

Replay uses the installed compatible engine with the archived case, dataset, and optional source snapshot. The runtime checks recorded engine/dependency compatibility instead of executing arbitrary archived source. Reproducibility refers to the declared normalized analytical output, not new execution timestamps, ZIP metadata, or every host's database bytes.

The application records its source and dependency versions when its process starts. A source edit or dependency change requires a restart before a new run or replay, preventing a long-lived service from archiving changed files as if its previously imported code executed them. Every copied engine file must also match that process snapshot. A failed replay reports differing output without claiming reproduction.

Source records distinguish acquisition timestamps from publisher update dates. Original bytes and normalization metadata remain available alongside findings. These choices follow the separation of entities, activities, and responsible agents described by [W3C PROV](https://www.w3.org/TR/prov-overview/). [RO-Crate](https://www.researchobject.org/ro-crate/specification/1.3/structure.html) provides an interoperable descriptive model, while [BagIt](https://www.rfc-editor.org/rfc/rfc8493.html) specifies archival inventory conventions. This implementation states its own format precisely rather than implying those standards are already implemented.

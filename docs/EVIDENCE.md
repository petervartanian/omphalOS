# Evidence records and portable exports

Every completed run preserves its case, normalized dataset and original inputs, selected source snapshot when used, analysis results and coverage, catalog, application source snapshot, and recorded environment. `manifest.json` inventories every regular file except itself with a relative path, SHA-256 digest, and byte count. Required artifacts cannot be removed from the inventory to disable verification. Unlisted files, duplicate entries, symbolic links, and unsupported paths fail verification.

Finalization is write-once through the application. A failed verification does not repair or silently replace a run. Operating-system owners can still modify their files; the application does not claim otherwise.

`analysis_digest` is recomputed from the actual analysis using the documented `omphalos-json-v1` encoding: UTF-8, sorted object keys, compact separators, no nonfinite values, and a terminating newline. Analysis numbers are signed 64-bit integers; decimals and larger exact numbers are strings. This is an application encoding, not a claim of RFC 8785 conformance. Timestamps and execution IDs remain outside the deterministic analytical content.

## Guided workflow record

New guided runs use case schema 2.1. Its `workflow` records the selected dataset, accepted source snapshot when required, input digests, plan identifier, and source-acceptance and execution-approval timestamps. **Use these sources** issues a receipt bound to the exact proposed case and inputs. **Run reviewed plan** requires that receipt and an explicit execution acknowledgment before retaining the case and run. Changing an input invalidates the receipt; a repeated unchanged request reuses its verified run.

The service authenticates the temporary receipt with its own secret. That receipt signature is not included in the evidence package and is not a publisher signature. The retained workflow describes local user actions, not verified identities or supervisor authorization. Run verification checks that its recorded case and input digests agree with the archived evidence.

Earlier case schema 2.0 remains supported with its original serialization. Its absent approval history is reported as not recorded, never inferred from completed checks or a later assessment. The case schema and review schema are separate contracts; existing reviews and packages retain their original attribution.

**Mark results reviewed** opens Assessment in the current session. It is not a separately persisted attestation. A valid saved review against the exact run manifest provides the durable findings-and-coverage acknowledgment described below.

## Review

A new interface decision uses review schema 2.2. It records a named reviewer, a decision to keep the investigation open, escalate it, or conclude it, one substantive reason and next-step note of at least 12 characters, and an acknowledgment of the coverage limitations. Its scope includes every retained finding exactly once. This scope identifies the observations included in the decision; it does not assert that the reviewer individually assessed each observation. A zero-findings result requires the same explicit decision, note, and acknowledgment.

Review schema 2.1 remains readable and exportable under its original rules: notes are optional for open or escalated cases and required for conclusions; any supplied note must be substantive. Opening a retained 2.1 decision leaves its content and schema unchanged. Explicitly saving a revision in the interface creates a 2.2 decision with the required note.

Existing individual reviews (schema 2.0) remain supported. They cover every finding exactly once and supply a disposition, rationale, unknowns, alternatives, and falsifiers. Merely copying all generated uncertainty sections does not complete an individual review. Both formats require dataset and source references to resolve to preserved records.

Case-decision reports retain every original observation and its evidence, unknowns, alternatives, and evidence requests as analytical output. They identify the case decision separately and do not manufacture individual dispositions or attribute generated reasoning to the reviewer. `omphalos schema review` describes the supported review formats.

The immutable review wrapper records its own ID and timestamp and the SHA-256 of the exact run manifest reviewed. A review against a different manifest cannot authorize export. Review identities are self-asserted; text validation cannot establish the adequacy or truth of the reasoning.

New review timestamps preserve saved revision order within a run. The application uses the current UTC clock value unless it is no later than the previous revision; in that case it uses the previous timestamp plus one microsecond. Earlier wrappers remain unchanged, and comparison accounts for differing timestamp precision and UTC offsets. These are logical ordering timestamps, not trusted time or proof of when a person acted.

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

Export first validates the run and exact review anchor, then builds and verifies a new bundle. Existing exports are never overwritten. Report HTML escapes supplied text; it contains no remote dependencies. Reports identify review attribution as self-asserted and explicitly state **Separate supervisory approval: not recorded.** They report actual byte checks without claiming independent review or authenticated publication.

HTML and Markdown reports include a readable coverage table with check, status, evaluated-record count, observation count, reason, and limitations. Check titles come from the run's archived `catalog.json`; missing or ambiguous titles fall back to the archived check ID. Package creation is independent of the recorded decision: an exported case can remain open or escalated.

The **Supplied supporting records** section includes every diligence row in the retained dataset, independently of generated findings. It preserves the record and entity IDs, title, date, attributed text, source URL as text, and available original-file provenance. These are supplied claims, not automatically corroborated or adopted by the analyst. The report states that records outside the selected entity or date scope may be included; their presence does not establish relevance. Original input bytes remain unchanged in the package.

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

## Public identity research

Identity research is a separate acquisition from list screening. Its manifest inventories the query transcript, raw provider replies, and parsed report. Loading research replays the parser over those retained replies and compares the reconstructed report. A selection is bound to the original dataset hashes and entity ID. The derived dataset retains both the original data and the research, then deterministically reconstructs the permitted enrichment. Unsupported fields cannot be submitted by the browser, and existing supplied values are preserved when a source differs. Explicit continuation without a profile retains the attempt without adding facts.

Runs and evidence packages carry the complete derivation, including failed provider coverage and original bytes. Wikidata content is attributed directory data, not independently authenticated company documentation. Byte integrity and reproducible derivation do not establish factual truth.

Package completion is persisted only after the archive verifies. The completion pointer binds its archive hash, run-manifest hash, and review ID. A new review, corrupt archive, or changed run invalidates that completion state.

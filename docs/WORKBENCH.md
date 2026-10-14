# Local investigation workbench

omphalOS helps an analyst inspect imported transaction records, generate explainable observations, assess official-list identity candidates, and retain the reasoning behind a review. It is a single-user local application. It does not decide whether an entity is sanctioned, determine an ECCN or license requirement, infer an intent to evade controls, or establish that a transaction is lawful.

## Open the workbench

After the installation described in the root README, run:

```sh
poetry run omphalos --workspace ./workspace serve --open
```

The terminal prints the local URL. The server binds only to loopback, with port 8765 by default. The interface uses packaged HTML, CSS, and JavaScript; no CDN, web font, frontend build, account, or online service is needed to import and analyze local records. Public-source downloads occur only when you explicitly choose **Fetch official snapshot**. They send no case data.

The four navigation pages follow the investigation: **Overview**, **Data & sources**, **Cases**, and **Findings & review**. Counts and results come from the workspace. An empty workspace has no invented observations.

## 1. Import the records

On **Data & sources**, choose a dataset ID and label, select files, then choose **Validate & import**. IDs use letters, digits, underscores, and hyphens. A blank ID generates a unique one. Importing cannot replace an existing dataset.

Use one of these formats:

- Named UTF-8 CSV files with headers: `entities.csv`, `shipments.csv`, `payments.csv`, `ownership.csv`, and `diligence.csv`.
- Named JSON files, such as `entities.json`, each containing an array of records.
- A single `dataset.json` containing `{"tables": {"entities": [...], "shipments": [...]}}`.

An entities table is required. Other tables are optional, but an investigation cannot run without its prerequisites. Exact required and optional fields appear under **File names, fields, and import rules**, generated from the same schemas that validate the import. The examples directory also contains importable files.

For example, a minimal entities file is:

```csv
entity_id,name,country,address
E1,Example Instruments,US,12 Example Road
E2,Example Distributor,DE,34 Sample Street
```

Positive monetary amounts are decimal values with three-letter currencies. Refunds are outside this data model. Dates use `YYYY-MM-DD`. HS codes remain strings and are distinct from ECCNs. No currency or unit conversion is inferred. A matching name does not merge two different entity IDs.

The importer rejects duplicate IDs, unexpected fields, broken references, malformed rows, and invalid values. It reports errors rather than silently discarding records. Original uploaded bytes are retained with hashes and normalized records retain the original filename and row number. The browser accepts up to six files and at most 48 MiB combined per import; the command line supports the importer’s larger file limits.

**Create synthetic dataset** adds a visibly labeled, separate fixture with planted signals, benign counterexamples, and missing context. It never substitutes for a real import. Synthetic status follows the archived dataset into the run and exported report. It is appropriate for exploring the interface and testing the mechanics, not validating performance on operational data.

## 2. Add a screening snapshot when needed

Select the Consolidated Screening List, OFAC SDN, or OFAC non-SDN source. **Fetch official snapshot** retrieves the allowlisted official HTTPS endpoint with download limits. Alternatively, import a downloaded file using the format displayed for the selected source. CSL uses bulk JSON; the two OFAC adapters use standard XML.

A saved snapshot retains the original download, its SHA-256, retrieval/import time, normalized records, original record content, list category, and available source dates. It remains fixed until a new snapshot is explicitly acquired. The interface shows publisher timing as unknown when the source did not provide it. Fetch failures are errors; there is no fallback to a fabricated list.

Choose the snapshot in the case. Selecting the screening investigation without a usable snapshot produces **not evaluable** coverage. A candidate’s name-similarity value is a string comparison, not a calibrated identity probability or a likelihood of wrongdoing. Dates, category-specific restrictions, identifiers, and independent corroboration require review. Current snapshots do not necessarily establish historical list membership, and unlisted ownership relationships are not comprehensively screened.

## 3. Define a bounded case

On **Cases**, enter a stable case ID, investigative question, dataset, and analysis-as-of date. Add an optional date range, exact domain labels, or explicit entity IDs. The as-of date and scope control which records are considered; they do not silently make a newly fetched source historically valid.

Select the investigations relevant to the question. Each card describes the algorithm, required tables, parameters, and limitations. Numeric comparison thresholds are analyst choices. **Payments below a chosen threshold**, for example, requires the chosen threshold and currency and does not assume a statutory reporting threshold.

Choose **Save case** to retain the definition, or **Save & run investigation** to execute it. Saved cases can be reopened. Changing a case does not change an existing run: each run retains the case, data, selected source, catalog, engine files, environment record, and analysis used at that time.

## 4. Inspect coverage and evidence

On **Findings & review**, select a run. The integrity indicator concerns the retained file inventory and analysis digest. It is separate from the quality or truth of the underlying evidence.

- **Observations** shows neutral computed statements, metrics, source references, unknowns, alternative explanations, and potential falsifiers. Record buttons open the exact normalized record frozen in this run with its original filename, source row, and file hash. Official-source buttons expose the matched normalized listing and original source record/XML, with snapshot provenance.
- **Coverage & limits** distinguishes **executed** from **not evaluable**, shows the evaluated record count and finding count, and retains detector-specific limits and missing-data warnings. Zero observations are not a clearance.
- **Run context** exposes the frozen case, analysis digest, manifest, and verification record.

Observations and review forms are paged in groups of 20, with the displayed range and full count shown. All observations must still be assessed before saving. Findings with many supporting records initially show 40 record buttons, with an explicit control to reveal the next records; no count is presented as though the partial display were complete. Run-detail tabs support Left/Right arrows, Home, and End from the keyboard.

The interface refuses evidence drilldowns from a run that fails integrity verification. It can still display the failed verification and run context so the analyst can identify the problem. A file hash shows whether content changed relative to the inventory; it does not prove authenticity, accuracy, completeness, or legal admissibility.

## 5. Record the assessment

In **Analyst review**, supply a reviewer name and an overall assessment. For every observation, choose **Follow up**, **Explained**, or **Escalate** and write:

- The evidence-based rationale.
- Unresolved questions and how to resolve them.
- Alternative explanations considered.
- The evidence that would change the assessment.

Analytical caveats are available as context, but a new review has no automatically completed rationale or checked acknowledgment. Write a case-specific assessment. Required fields and exact finding coverage are validated; software cannot establish that a rationale is substantively correct or that a reviewer exercised sound judgment. The reviewer name is self-asserted, not externally authenticated.

Complete the coverage acknowledgment and choose **Save complete review**. Every finding needs an assessment, including findings assigned open follow-up or escalation. A run with zero observations still needs a named overall assessment and acknowledgment of the coverage limits. Reviews are retained as separate immutable revisions; saving a revised review does not overwrite the earlier record or the original run. Unsaved review edits persist in the current page session when switching among run tabs and prompt before closing the page; they are not durable until saved. The assessment-field counter describes filled required fields, not the correctness or quality of the analyst’s judgment. A damaged or incomplete stored review is surfaced as a validation issue and cannot silently enable export.

## 6. Verify, replay, and export

**Verify files** checks the complete archived inventory, including modified, missing, unexpected, and unsafe paths. **Replay analysis** recomputes the case using retained inputs and compares the normalized result digest. It reports a mismatch when installed engine files or dependency versions differ; it does not execute arbitrary archived code. Results are shown in full.

**Create evidence package** is disabled until a review exists and integrity verification passes. The server independently rechecks the run and review before export; enabling a browser button cannot bypass the gate. The resulting download is a ZIP with the run snapshot, review, generated HTML/Markdown report, and verification material. The UI shows its SHA-256 and links to the actual generated file. See `EVIDENCE.md` for the package format, independent verification, and limits.

An exported package can record unresolved concerns and specialist escalation. Export does not certify a conclusion, prove reviewer identity, or confer court admissibility. Keep the original package and separately document the trust and handling requirements applicable to your organization.

## Local-service boundaries

The server rejects unexpected Host headers and cross-origin requests, requires a random session token plus an exact same-origin Origin header for modifications, bounds JSON bodies and uploads, contains filesystem paths, rejects symlink exports, escapes displayed data, and permits no arbitrary network-URL fetch API. Assets have a restrictive content security policy and are served without third-party dependencies. Request bodies and tokens are not written to HTTP access logs.

These controls protect a local workflow against accidental exposure and common browser-origin attacks. They are not multi-user authentication, workstation access control, a network deployment architecture, or encrypted storage. Anyone with sufficient access to this operating-system account can access the workspace. Use normal organizational controls for the underlying files.

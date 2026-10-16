# Investigation guide

omphalOS starts from a company or person name, or from transaction records, and runs the supported checks. It helps an analyst assess official-list identity candidates, inspect explainable observations, and retain the reasoning behind a review. It is a single-user local application. It does not decide whether an entity is sanctioned, determine an ECCN or license requirement, infer an intent to evade controls, or establish that a transaction is lawful.

## Open the investigation

After the installation described in the root README, run:

```sh
poetry run omphalos --workspace ./workspace serve --open
```

The terminal prints the local URL. The server binds only to loopback, with port 8765 by default. The interface includes packaged HTML, CSS, JavaScript, and Geist fonts; it needs no CDN, external font service, frontend build, or account. Name-based intake sends the entered name to GLEIF and Wikidata for public identity discovery. Screening separately obtains the official public list when needed, then compares retained records locally. That list download sends no case records or search names.

**Investigate** opens a shallow evidence box with six named stages: **Records**, **Sources**, **Plan**, **Findings**, **Assessment**, and **Package**. Selecting an available panel or its matching external control opens that part of the investigation; **Back to the box** returns to the overview without discarding a draft. The current stage and next action are named. Earlier retained stages remain accessible; later stages unlock when their prerequisites are present. The header reads **omphalOS: the center of the investigation**, with the subtitle in small caps and a Refresh control. **Open** lists retained work; the supporting record and case screens remain part of the same application. Counts and results come from the workspace; an empty workspace has no invented observations.

On desktop, an open stage appears beside the box. On narrow screens, compact named stage controls stay above the work and **Back to the box** restores the full illustration. The external controls retain the complete stage names and Roman numerals, with larger labels and at least 44px height; you do not need to read a narrow folded panel to navigate.

## Start an investigation

Enter a company or person's name under **Who are you looking into?** and choose **Investigate**. omphalOS retains the name and looks it up in public directories. Choose **Use this identity** for the relevant sourced profile, or **Continue with name only** when no profile fits. The app then obtains the official U.S. Consolidated Screening List (CSL), prepares the screening checks, executes them, and returns to the overview with the result count and an **Open findings** action. The question, case ID, and checks are prepared automatically. The assessment date defaults to today. The information button beside the name field explains which services receive the name and how the local list comparison works. **Sources** and **Plan** remain available for inspection; the ordinary startup path does not require separate source-selection, plan-preparation, or run clicks.

Name intake accepts one name of up to 200 characters. It records that name as user-provided and unverified, with an unknown entity type and no inferred country, registration number, or identity. The generated record explicitly describes its origin as directly entered text. Its original JSON and normalized record remain available with hashes and row provenance. The intake itself makes no network requests. The separate research step searches GLEIF and Wikidata through bounded, verified HTTPS requests. It does not crawl arbitrary websites. GLEIF values remain attributed reference records; Wikidata values remain directory claims even when they cite a company website. Sources are not taken from the screening list to fabricate independent corroboration. A current headquarters location can establish directory-sourced geography; an obsolete country statement is not silently treated as current.

Choosing a profile creates an immutable derived dataset, fills only supported missing fields, preserves conflicting supplied values, and retains aliases, claims, source links, raw provider replies, and the selection. Continuing without a profile retains the unsuccessful or skipped research with the unchanged subject. **Research identity** on an existing single-subject case offers the same workflow and creates a new run; the previous run remains available. Provider failures and no-match results remain distinct.

The compact action row below the name field contains **Import** and **Open**. **Import** opens **Import records**, where **Choose records** accepts a counterparty CSV, dataset JSON, or linked transaction files. The information button **About record formats and privacy** explains the supported files and local storage; **Start with a name** returns to name entry. **Open** lists saved investigations and retained record sets in a dialog; select an investigation to resume it, or a record set to run the supported checks. Dates and observation counts appear in this picker.

After intake, **New** and **Open** remain available beside the stage guidance during ordinary navigation. **New** starts a fresh investigation without deleting earlier runs. Review drafts captured in the current page session remain available when returning to their investigation.

Selecting an unfinished investigation in **Open** restores its overview. Open **Assessment** to return to the case decision. Existing draft notes and decisions remain intact.

A purpose is optional at the start. When no purpose was explicitly selected, a dataset with shipments or payments suggests **Review transaction patterns**; entity-only records suggest **Screen counterparties**. Changing datasets updates an inferred purpose. A purpose you explicitly chose remains in force, so the plan may report that the selected records lack its prerequisites.

You can explicitly start with one of three purposes:

- **Screen counterparties** compares imported entity names with a retained official-list snapshot, examines shared addresses, and checks data quality. It produces candidates for identity assessment.
- **Understand data readiness** identifies missing or inconsistent context before an analyst relies on the records.
- **Review transaction patterns** proposes transaction checks from the available shipment, payment, and entity records. A company-name list alone cannot support a transaction investigation.

### Preview a counterparty CSV

Selecting one CSV through **Choose records** automatically prepares its interpretation preview. It does not import the records until you confirm the mapping. The importer accepts one UTF-8 CSV, up to 20 MiB, 50,000 data rows, and 100 columns. A company name is the minimum. Recognizable headers such as `Company Name`, `Vendor Name`, `Country`, and `Registration Number` receive suggested mappings. You can change each mapping before importing. Ambiguous mappings and invalid rows produce errors; records are not silently discarded.

The preview shows original columns, proposed uses, example values, generated-ID count, actual value conversions, validation issues, and sample normalized records. Columns designated **Retain in original file only** remain in the exact uploaded file but do not participate in analytical checks. Finite, explicit conversions can normalize recognized country names or LEI capitalization. Unrecognized country labels are not guessed.

If no entity ID is mapped, the importer generates distinct local IDs from the file hash and physical source row. It does not merge similar company names or infer relationships between transactions. After changing a mapping, choose **Update preview** and inspect the revised result. **Change files** clears the preview and returns to file selection while preserving the investigation settings. **Investigate these records** confirms the interpretation, imports the records, obtains a screening list when needed, and runs the supported checks. The server checks that the preview still matches the file and mapping. Original bytes, file hash, row provenance, and mapping remain available to reproduce the normalization.

The same picker accepts a complete dataset JSON under any filename, a named JSON table, or multiple named entity, shipment, and payment files. This path validates the strict dataset format, imports it, and starts the supported analysis; it does not provide the ordinary CSV mapping preview. Explicit IDs preserve relationships without inferred joins. The format requirements for linked records are described below.

### Inspect sources and the prepared plan

**Plan** shows the proposed question, assessment date, record counts, prepared checks, and checks still needing evidence. Use **Method** or **Needs data** to inspect a check's parameters and limitations. The complete purpose-specific check set is retained in the case, including unavailable checks, so later coverage does not conceal omissions. Threshold-dependent and context-dependent checks that need an analyst's choice remain available in the detailed case editor.

Use **Change date or source** to inspect or revise those inputs. Changing them invalidates the current plan and requires preparation again. The assessment date controls which records are considered; it does not turn a newly acquired list into a complete historical snapshot.

**Sources** holds the reference-list context. For the default current-date screening workflow, omphalOS reuses a valid official HTTPS CSL snapshot acquired less than 24 hours ago or downloads a new one. A manually imported list is not silently substituted for an official download in that automatic path. An explicitly selected source is preserved; changing the assessment date also preserves the selected snapshot rather than replacing it solely because it is old. If no snapshot is available, the application still needs one before screening can run. A newly downloaded list does not establish historical membership.

The selected snapshot remains inspectable, with its acquisition method, available timestamps, and age relative to the assessment date. **Download official CSL & prepare plan** also remains available as a deliberate source update. All official-list downloads send no case records. Retrieval time and freshness warnings do not establish current or historical legal status. If an automatic download fails, the records remain saved and **Retry screening** resumes the attempt; no successful screening result is invented.

The automatic path prepares and runs the plan in sequence. The server revalidates its inputs before creating the case and executing the checks, then returns to the overview with the result count. **Open findings** shows the screening outcome and retained observations. Select an observation to inspect its evidence. If required evidence is missing, the plan explains what could not run. An edited plan can be inspected and executed with **Run investigation**. Changed inputs invalidate its earlier execution authorization.

## From findings to assessment

**Findings** shows the result summary and all resulting observations. Selecting an observation opens an evidence detail view with the computed result, cited records, and analytical limits. For a run with no observations, coverage remains available and a case decision can still be recorded; zero findings is not clearance.

The evidence detail presents cited records together in tables, grouped by record type. Pages contain up to 40 references and show the current range when more are available. Each **View** control opens the exact retained record or source listing with its provenance. The server verifies the run before resolving a page and returns only references belonging to the selected observation. **All findings**, **Previous finding**, and **Next finding** navigate the retained results. The monthly shipment increase view also plots the retained monthly counts and shows the prior mean.

**Limits of this result** and **Evidence that could resolve it** display the check's uncertainties, alternative explanations, and evidence requests directly. These remain analytical output. Viewing them does not adopt them as the analyst's own words or assign a disposition to the observation.

**Case assessment** opens directly to the decision. **Review findings** returns to the complete observation index and supporting records; **Checks and sources** shows coverage and unavailable-check reasons. The assessment does not repeat the findings report or require per-observation writing.

Choose **Keep open**, **Escalate**, or **Conclude**, enter the reviewer name, and acknowledge review of the findings, coverage, and missing evidence. **Case note** is optional when keeping the investigation open or escalating it. Concluding requires a specific note of at least 12 characters; any supplied note must be substantive. The application does not generate a note or select a decision on the analyst's behalf.

**Record case decision** saves an immutable review revision and opens **Package**. The decision covers the full retained investigation without assigning individual dispositions. Keeping a case open or escalating it leaves the underlying questions unresolved. Unsaved notes and decisions survive in-page navigation and refresh of workspace data, but remain in the current browser session until saved. Existing unfinished individual-review drafts retain their original format and are not silently converted.

## Keep the investigation together

**Package** shows the recorded case decision, any case note, the reviewer, and the number of observations included. Older individual reviews retain their original assessment and disposition counts. **Create evidence package** is available when a valid recorded review and verified run are present. The server independently checks both before producing the ZIP. **Revise assessment** opens a new review revision. **Verify files** and **Replay analysis** inspect retained-file integrity and reproducibility, respectively; neither establishes the truth of the evidence or legal clearance.

Verification reports whether the retained files match their recorded checksums. Replay reports whether findings and coverage reproduce from those records. Both show a plain-language outcome, the number of files checked when available, and specific issues. A valid **Download evidence package** link remains alongside these results.

The box folds from retained completion, one panel at a time. **Records** stays flat as the base. **Sources**, **Plan**, **Findings**, and **Assessment** form the walls in that order; **Package** is the lid. Records completes after confirmed, valid intake. Sources completes when retained source requirements are met, including when no reference list is needed. Plan completes when a runnable plan is prepared, Findings after verified analysis, and Assessment after a valid decision is saved without differing unsaved edits. The lid closes only after a verified export matches the current decision and run. An import preview, pending identity choice, failed verification, or changed inputs cannot inherit completion from an older run. If work becomes incomplete, affected panels unfold in reverse order; the Records base stays flat.

Each unfinished panel has its own light color: blue Records, teal Sources, orange Plan, yellow Findings, pink Assessment, and brown Package. Its pigment becomes visibly darker as its hinge folds; the Records base changes after valid intake. Restrained sheen preserves these differences. The exact light/completed pairs are listed in [Panel colors](DESIGN.md#panel-colors).

Permanent numerals identify the sequence: **I Records**, **II Sources**, **III Plan**, **IV Findings**, **V Assessment**, and **VI Package**. Completion adds a checkmark without replacing the numeral. Larger panel titles appear where they fit; narrow folded walls show the numeral. Full names and numerals remain in the external controls. Color and folds indicate completed work, not clearance or risk. Selecting earlier retained material does not undo completion or reopen a folded panel. Left/Right arrows, Home, and End move among available controls. Reduced-motion preferences show the resulting folds without animation.

The package download remains available after reopening the case and alongside verification or replay results, while the current decision and run remain valid.

The remaining sections describe supporting record and case screens. **Saved investigations** opens **Findings & review**, whose navigation also provides **Overview**, **Data & sources**, and **Cases**. These screens retain tables, case settings, and optional technical disclosures. Their direct local URL fragments are `#runs`, `#overview`, `#data`, and `#cases`; use them after the local server address when direct access is needed.

## 1. Import the records

On **Data & sources**, choose **Import records** to open the dataset form. Enter a label and optional dataset ID, select files, then choose **Validate & import**. IDs use letters, digits, underscores, and hyphens. A blank ID generates a unique one. Importing cannot replace an existing dataset.

Use one of these formats:

- Named UTF-8 CSV files with headers: `entities.csv`, `shipments.csv`, `payments.csv`, `ownership.csv`, and `diligence.csv`.
- Named JSON files, such as `entities.json`, each containing an array of records.
- A single `dataset.json` containing `{"tables": {"entities": [...], "shipments": [...]}}`.

An entities table is required. Other tables are optional, but an investigation cannot run without its prerequisites. Exact required and optional fields appear under **Import format and field reference**, generated from the same schemas that validate the import.

For example, a minimal entities file is:

```csv
entity_id,name,country,address
E1,Example Instruments,US,12 Example Road
E2,Example Distributor,DE,34 Sample Street
```

Positive monetary amounts are decimal values with three-letter currencies. Refunds are outside this data model. Dates use `YYYY-MM-DD`. HS codes remain strings and are distinct from ECCNs. No currency or unit conversion is inferred. A matching name does not merge two different entity IDs.

The importer rejects duplicate IDs, unexpected fields, broken references, malformed rows, and invalid values. It reports errors rather than silently discarding records. Original uploaded bytes are retained with hashes and normalized records retain the original filename and row number. The browser accepts up to six files and at most 48 MiB combined per import; the command line supports the importer’s larger file limits.

Synthetic records used in software tests retain their provenance labels in archived data and reports. Passing those tests demonstrates implementation behavior, not operational detection accuracy.

## 2. Add a screening snapshot when needed

Choose **Add snapshot**, then select the Consolidated Screening List, OFAC SDN, or OFAC non-SDN source. **Fetch official snapshot** retrieves the allowlisted official HTTPS endpoint with download limits. Alternatively, import a downloaded file using the format displayed for the selected source. CSL uses bulk JSON; the two OFAC adapters use standard XML.

A saved snapshot retains the original download, its SHA-256, retrieval/import time, normalized records, original record content, list category, and available source dates. It remains immutable; later downloads create new snapshots. The interface labels available timing as **Source timestamp**. For CSL this is aggregation time, not necessarily the update time of each underlying list; the retained source metadata explains the distinction. Missing timing is shown as not supplied. Manual uploads are visibly labeled and their origin is not independently authenticated. Official HTTPS downloads are identified separately. Fetch failures are errors; there is no fallback to a fabricated list.

Choose the snapshot in the case. Selecting the screening investigation without a usable snapshot produces **Not evaluated** coverage (stored as `not_evaluable`). A candidate’s name-similarity value is a string comparison, not a calibrated identity probability or a likelihood of wrongdoing. Dates, category-specific restrictions, identifiers, and independent corroboration require review. Current snapshots do not necessarily establish historical list membership, and unlisted ownership relationships are not comprehensively screened.

## 3. Define a bounded case

On **Cases**, saved cases appear first. Choose **Open case** for an existing definition or **New case** to open the editor, then enter a stable case ID, investigative question, dataset, and analysis-as-of date. Add an optional date range, exact domain labels, or explicit entity IDs. The as-of date and scope control which records are considered; they do not silently make a newly fetched source historically valid.

Select the investigations relevant to the question. Each investigation row shows its purpose and required tables. Open **Settings and limitations** to inspect parameters and interpretation limits. Numeric comparison thresholds are analyst choices. **Payments below a chosen threshold**, for example, requires the chosen threshold and currency and does not assume a statutory reporting threshold.

Choose **Save case** to retain the definition, or **Save & run investigation** to execute it. Saved cases can be reopened. Unsaved case edits are retained while navigating among pages or using **Refresh**, and the header indicates unsaved changes. They remain in the current page session until explicitly saved; leaving the page prompts when changes remain. Explicitly starting a new case or opening another case asks before replacing unsaved case edits; ordinary navigation and refresh retain them without a prompt. Changing a case does not change an existing run: each run retains the case, data, selected source, catalog, engine files, environment record, and analysis used at that time.

## 4. Inspect coverage and evidence

On **Findings & review**, select a run. The run header separates review status, observation count, completed checks, checks that need attention, and file verification. The file verification indicator concerns the retained file inventory and analysis digest. It is separate from the quality or truth of the underlying evidence.

- **Observations** shows neutral computed statements, metrics, source references, unknowns, alternative explanations, and potential falsifiers. Record buttons open the exact normalized record frozen in this run with its original filename, source row, and file hash. Official-source buttons expose the matched normalized listing and original source record/XML, with snapshot provenance.
- **Coverage** distinguishes **Completed** (stored as `executed`) from **Not evaluated** (stored as `not_evaluable`), shows the evaluated record count and finding count, and retains detector-specific limits and missing-data warnings. Zero observations are not a clearance.
- **Details** exposes the frozen case, analysis digest, manifest, and verification record.

The supporting observations screen uses pages of 20, with the displayed range and full count shown. Its record buttons initially show 40 references and provide a control for additional records. Opening an observation in Findings displays the grouped evidence tables described above. Run-detail tabs support Left/Right arrows, Home, and End from the keyboard.

Identity candidates show the compared names, underlying list, country and entity-type comparisons, identifier comparisons, and available source timing before the raw details. The name similarity is omphalOS’s own string comparison, not an official OFAC search score. For organizations, bounded corporate forms and generic organizational phrases are discounted: the effective score is the lower of the full-name score and the mean of full-name and distinctive-name scores. This never increases the earlier character score. Exact normalized or reordered-token matches are preserved, while entirely generic aliases cannot establish a candidate by themselves. Known people, vessels, and aircraft retain the full-name comparison; typed identifier matches remain independent. Both scores, the compared names, and the comparison method are retained. Short spelling variants may still fall below the configured threshold; this is candidate retrieval, not comprehensive identity resolution.

The interface refuses evidence drilldowns from a run that fails integrity verification. It can still display the failed verification and run context so the analyst can identify the problem. A file hash shows whether content changed relative to the inventory; it does not prove authenticity, accuracy, completeness, or legal admissibility.

## 5. Record the assessment

**Analyst review** uses the same case decision and evidence navigation as **Assessment** on the box. Choose whether to keep the investigation open, escalate it, or conclude it. Supply a reviewer name, any case note, and the coverage acknowledgment, then choose **Record case decision**. A conclusion requires a substantive note; a note is optional for the other decisions. The reviewer name is self-asserted, not externally authenticated.

The saved case review uses schema 2.1. Its scope identifies every observation included in the retained investigation; it does not claim that each observation received an individual judgment. The server validates the exact scope, run binding, explicit decision, reviewer, and acknowledgment. It retains the engine's observations and analytical context separately from the case note. A run with zero observations still requires an explicit named decision and acknowledgment of coverage limits.

Existing schema 2.0 individual reviews remain valid and exportable. Unfinished drafts in that format preserve their individual fields rather than converting their content automatically. Reviews are retained as separate immutable revisions; saving a revised review does not overwrite the earlier record or original run. Unsaved edits persist in the current page session when switching among run tabs and prompt before closing the page; they are not durable until saved. A damaged or incomplete stored review is surfaced as a validation issue and cannot silently enable export.

## 6. Verify, replay, and export

Under **Evidence integrity**, **Verify files** checks the complete archived inventory, including modified, missing, unexpected, and unsafe paths. **Replay analysis** recomputes the case using retained inputs and compares the normalized result digest. It reports a mismatch when installed engine files or dependency versions differ; it does not execute arbitrary archived code. Results are shown in full.

**Create evidence package** is disabled until a valid review exists and integrity verification passes. The server independently rechecks the run and review before export; enabling a browser button cannot bypass the gate. The resulting download is a ZIP with the run snapshot, recorded case decision or legacy review, generated HTML/Markdown report, and verification material. Case-decision reports distinguish the analyst's decision and optional note from the retained analytical output, without inventing individual dispositions. The UI shows its SHA-256 and links to the actual generated file. See `EVIDENCE.md` for the package format, independent verification, and limits.

An exported package can record unresolved concerns and specialist escalation. Export does not certify a conclusion, prove reviewer identity, or confer court admissibility. Keep the original package and separately document the trust and handling requirements applicable to your organization.

## Local-service boundaries

Long-running operations identify the actual stage in a status message. Inspecting an available stage during automatic preparation leaves the investigation running and preserves the selected panel; completion does not scroll over that view. Future-stage controls remain unavailable until their prerequisites are present. Leaving the page, changing its inputs, or opening another run prevents later automatic stages from replacing the current investigation. Delayed responses do not open a record dialog after the analyst navigates elsewhere. Submission fields are temporarily locked after their payload is captured, and newer drafts are not cleared by an earlier save.

The server rejects unexpected Host headers and cross-origin requests, requires a random session token plus an exact same-origin Origin header for modifications, bounds JSON bodies and uploads, contains filesystem paths, rejects symlink exports, escapes displayed data, and permits no arbitrary network-URL fetch API. Assets have a restrictive content security policy and are served without third-party dependencies. Request bodies and tokens are not written to HTTP access logs.

These controls protect a local workflow against accidental exposure and common browser-origin attacks. They are not multi-user authentication, workstation access control, a network deployment architecture, or encrypted storage. Anyone with sufficient access to this operating-system account can access the workspace. Use normal organizational controls for the underlying files.

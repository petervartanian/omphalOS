# Investigation interface design

The primary interface treats an investigation as a shallow evidence box assembled through six stages: Records, Sources, Plan, Findings, Assessment, and Package. One panel folds at a time as work completes. Opening a stage puts its working surface beside the box on desktop. Narrow screens show compact stage navigation above the work; **Back to the box** restores the full object. Earlier retained material remains accessible; future stages unlock when their prerequisites are present.

Records is the base. Sources, Plan, Findings, and Assessment form the walls. Package is the lid, which closes after export. Selecting a completed panel inspects its contents without unfolding it or changing the case.

The wordmark is **omphalOS: the center of the investigation**, with the subtitle in small caps. The primary header contains the wordmark and Refresh. The box and its matching named controls provide the main navigation; supporting screens expose record inventories and case settings.

## Design principles

1. **Begin with the material.** Enter a subject or import records. Choosing a purpose first is optional. When no explicit purpose exists, the contents of the dataset suggest screening or transaction review. The application prepares the question, case ID, compatible checks, and defaults for inspection.
2. **One investigation, sequential stages.** Available panels open the corresponding working surface. The next action follows Records → Sources → Plan → Findings → Assessment → Package. Retained earlier stages can be inspected without restarting work.
3. **Prepare automatically, decide explicitly.** Confirm a CSV interpretation or choose a public identity. The ordinary intake path then obtains required sources, prepares a plan, and runs supported checks. The application does not insert manual approval steps for each prepared stage or record a human decision automatically.
4. **Evidence before assessment.** Completed analyses lead to Findings. Observation details expose computed values, grouped cited records, provenance, and analytical limits. Assessment records one case decision, with no required questionnaire for each observation.
5. **Color identifies a stage.** Each panel keeps a stable identity color before and after completion. Explicit names, checkmarks, and text states carry meaning without requiring hue recognition. Color does not classify severity, legal status, or risk.
6. **Preserve the work and its limits.** Drafts survive in-page navigation and workspace refresh. A response cannot replace a newer selection. Activity identifies the operation without an invented percentage. Completion tracks retained actions, not judgment quality.

## Visual language and tokens

`src/omphalos/ui/styles.css` contains shared tokens, supporting record-screen components, and the central investigation surface. The overview uses a neutral white background, fine dividers, and a centered object. `src/omphalos/ui/box.js` projects hinged panels into an SVG evidence box. Light identity colors deepen on completion; restrained reflections preserve their hue. Local Geist typography remains consistent throughout.

At widths of 960px and above, an open stage uses two columns: the box and navigation on the left, the working surface on the right. Below that breakpoint, the illustration is hidden while the stage is open and the six named controls form a compact three-column grid. Returning to the overview restores the full box without changing completion or discarding drafts. External stage controls use 12px labels and at least 44px height. Mobile surface inputs use 16px text.

| Layer | Rules |
| --- | --- |
| Surfaces | Neutral white background with shared surface, subtle, and hover tokens |
| Text | Primary, secondary, and muted text tokens; persistent stage names |
| Boundaries | Light group dividers and separate input borders |
| Panel identity | Distinct light colors before completion and darker versions of the same hue afterward |
| Status | Explicit warning and error text with supporting color; integrity and review remain separate concepts |
| Type | Packaged Geist for text; Geist Mono for identifiers and compact metadata, with system fallbacks |
| Spacing | Named shared spacing scale, supplemented by the central object layout |
| Shape | A flat base, four hinged walls, and a lid rendered in SVG |
| Motion | One completion fold at a time; invalidated panels unfold in reverse order; reduced-motion support |

### Panel colors

Stages I–V retain their blue, teal, orange, yellow, and pink identities, with explicit light unfinished colors and deeper completed colors. Pigment follows its own hinge, so queued panels stay light until their fold starts. The Records base changes color when valid intake completes. VI uses a distinct pearl and rainbow material. The entire box adopts that material only after verified export completion.

| Panel | Identity | Unfinished | Complete |
| --- | --- | --- | --- |
| I Records | Blue | `#A6C8E8` | `#5A84AF` |
| II Sources | Teal | `#83C3B8` | `#42978D` |
| III Plan | Orange | `#FFD4AF` | `#D88B49` |
| IV Findings | Yellow | `#FFF1A8` | `#CCAE3B` |
| V Assessment | Pink | `#F5BCD3` | `#CC7FA1` |
| VI Package | Pearl with rainbow reflection | `#DCE4ED` | `#DCE4ED` |

Package adds a fine interlaced engraving, an embossed border, and a soft rainbow reflection over a cool pearl base. Broad violet, cyan, rose, and gold pools form one continuous reflection field. Before completion, only VI carries that material. Verified export completion transforms every panel to the same pearl base and continuous reflection as the lid folds; no brown or other stage pigment remains underneath. Invalidation restores the I–V stage colors while VI stays pearl. The reflection is uninterrupted beneath the captions. Ink adapts to the reflected color, with a fine glyph outline only when needed for contrast. There is no idle animation or repeated rainbow painted independently on each panel. Changing the assessment removes the completed finish until a new matching package is created.

Completion adds a checkmark alongside the permanent Roman numeral. Panel titles start at 14 SVG units and fit down to 11; narrow folded walls retain the smaller circled numeral. Labels are clipped to their own panel. External controls retain every full name and numeral. Ink adapts to the actual reflected surface throughout folding; a fine glyph outline protects exceptional intermediate contrast crossings. Text states and accessible completion descriptions supplement color.

Teal on Sources means Sources. Orange on Plan means Plan. Neither encodes a favorable or unfavorable analytical result.

### Local font provenance

The packaged `geist.woff2` and `geist-mono.woff2` assets were sourced from the npm package **`geist@1.7.2`**. They are served by the local application as Geist and Geist Mono; no font request reaches a CDN or third party. CSS uses variable weights from 100 to 900, `font-display: swap`, and system-font fallbacks.

The fonts retain their **SIL Open Font License, Version 1.1**. The copied copyright notice and complete license are in [`src/omphalos/ui/font-license.txt`](../src/omphalos/ui/font-license.txt), identifying Vercel in collaboration with basement.studio. That license applies to the font assets independently of the application code's CC0 license. The font binaries and license are included with the packaged interface.

## The central investigation

### Records and prepared work

**Import** opens ordinary CSV intake and explicitly linked transaction files; **Open** lists retained work. The compact import surface contains **Choose records**, the CSV/JSON file input, and **Start with a name**. Its information button, labeled **About record formats and privacy**, opens the format requirements and local-storage explanation. It does not repeat saved dataset rows. After intake, **New** and **Open** remain beside the stage guidance during ordinary navigation. New returns to name entry while retaining earlier runs and captured review drafts.

A new page starts with name entry, and an empty workspace contains no seeded records. All tabs connected to one local server share that server's workspace; browser sessions are not separate user accounts. Selecting an ordinary counterparty CSV triggers a preview, which displays proposed column uses, examples, conversion notes, issues, and a sample of interpreted records. Unknown columns remain explicitly retained in the original file only. Generated local IDs preserve distinct rows; the importer does not merge identities or infer transaction joins.

**Investigate these records** confirms the preview and starts the supported analysis. **Change files** returns to file selection without importing the rejected preview or discarding investigation settings. For an unspecified purpose, shipments or payments suggest transaction review; entity-only records suggest counterparty screening. An explicitly chosen purpose takes precedence. Linked transaction files use the strict schema and proceed through validation and import without the ordinary CSV mapping preview.

**Sources** exposes the retained official-list snapshot and its dates, or explains when no reference list is required. Normal intake obtains an eligible official snapshot automatically when needed. Source failures retain the input and offer a retry. Historical dates and explicitly selected snapshots remain part of the case context.

**Plan** presents the question, record coverage, assessment date, prepared checks, and unavailable checks. Normal intake executes the supported plan automatically. Edited settings invalidate the earlier plan; an updated plan remains inspectable and can be executed with **Run investigation**. Missing prerequisites remain visible in saved coverage.

### Findings and case assessment

A completed run opens **Findings**, an index of its observations. Selecting one opens its computed result, grouped evidence tables, and analytical limits within Findings. Evidence pages contain up to 40 references. Opening a record shows its retained source and provenance. Displayed entity names come from verified retained records; original IDs remain available.

**Assessment** opens directly to one explicit case decision: **Keep open**, **Escalate**, or **Conclude**. **Review findings** and **Checks and sources** keep the supporting material one action away without repeating the report above the form. A reviewer name and coverage acknowledgment are required. A case note is optional except when concluding. The application neither chooses the decision nor invents individual observation judgments.

Analytical uncertainties and evidence requests remain attributed to the checks. Reading them creates no review draft. Existing individual-review records and unfinished legacy drafts retain their original format; new reviews use the case decision.

Zero-observation runs still require an explicit case decision and acknowledgment. Saving a valid decision makes Package available. It does not create the export or close the lid.

### Completion and the evidence box

Panel values come from preview, dataset, plan, run, and review state. Records counts rows; Sources counts retained list entries; Plan distinguishes prepared and executed checks; Findings counts observations; Assessment distinguishes a draft from a recorded decision; Package distinguishes readiness from an actual export.

The Records base stays flat. The Sources wall folds after source requirements are met, including when no list is required. Plan folds after a runnable plan is prepared, Findings after verified analysis, and Assessment after a valid case decision is recorded. Package closes the lid only after export. When several stages complete together, their folds play sequentially in that order. Merely selecting a panel never completes it.

Changed inputs, failed verification, or differing unsaved decision edits invalidate the relevant completion states. Affected panels unfold in reverse order, beginning with the lid when necessary. The renderer keeps its current pose through workflow updates and reverses an interrupted fold from its visible position. Reduced-motion preferences and a hidden document settle the geometry immediately. Named controls remain available independently of the illustration.

**Package** combines the recorded decision, case note, export, verification, and replay. **Verify files** reports whether retained files match their recorded checksums. **Replay analysis** reports whether findings and coverage reproduce. Each result shows a readable outcome, the checked-file count when supplied, and specific issues; the primary surface does not require reading raw JSON. The server independently checks the run and review before export. A matching download remains available after reopening and alongside verification or replay results. Unsaved decision changes prevent the old package from appearing as the current result. **Revise assessment** creates another immutable review revision; starting another investigation preserves earlier runs.

## Supporting record and case screens

**Saved investigations** from Package, or **View all** beside recent investigations, opens retained runs. The existing record-screen navigation exposes these supporting views:

- **Overview:** recent analyses, operational counts, and saved cases.
- **Data & sources:** dataset and snapshot inventories, strict import forms, acquisition controls, and format references.
- **Cases:** saved definitions and an explicit editor for the question, dataset, dates, scope, selected investigations, parameters, and snapshot.
- **Findings & review:** run selection, observations, coverage, case decisions, retained context, verification, and replay.

These views retain table panels and optional technical disclosures. Observations and legacy individual-review forms use pages of 20. Evidence pages show up to 40 references. Counts distinguish each visible subset from the complete retained result.

## Frontend organization and state

The product ships `index.html`, `styles.css`, `app.js`, `box.js`, two local font binaries, and their license. It requires no frontend build, graphics library, or JavaScript runtime dependency. The box and navigation icons use SVG.

`app.js` separates formatting and escaping, requests and state, view components, page composition, draft capture, asynchronous operations, and guided-flow behavior. All untrusted text is escaped before insertion into HTML. Evidence values remain text. External source links accept HTTPS and open with `noopener` and `noreferrer`. Backend validation and export gates remain authoritative.

Navigation generation, selected run, and current page identify which view owns a request. Guided-flow revisions additionally bind previews and plans to the selected purpose, dataset, source, assessment date, and mapping. Changing an input invalidates the relevant prepared work. A stale response can be retained on the server without advancing or replacing the user's current view. The server independently verifies confirmed previews and plans before import or execution.

Explicit New/Open case actions protect unsaved edits. Ordinary navigation and workspace refresh preserve drafts. Case drafts may be incomplete. New review drafts retain the explicit case decision and authored note; legacy drafts preserve their individual fields. A save captures its submitted values before locking the form and does not clear a newer draft. Drafts remain in memory until saved, with a browser-close warning for unsaved work.

## Accessibility and verification

Semantic landmarks, persistent labels, a route-preserving skip link, native dialogs, visible focus indicators, and text statuses support keyboard and assistive-technology use. Each box panel has an equivalent external control with the same name and accessible completion state. Left/Right arrows, Home, and End navigate available stages; future controls are disabled. Run tabs have equivalent keyboard support. A live status region sits outside the busy main region so operation announcements are not deferred. Wide tables scroll within their containers.

Renderer tests check title, numeral, and checkmark contrast of at least 4.5:1 against every gradient stop throughout folding and reversal. They also check a completion lightness change under normal and modeled red-green color vision. These checks do not establish that every user can distinguish all six hues, or constitute a comprehensive accessibility audit. Browser inspection, keyboard checks, reduced-motion checks, and complete workflow tests remain necessary alongside static checks.

Development checks run through `npm run lint` and `npm run format:check`. They are not product dependencies. The Python suite includes HTTP workflow tests and offline Node tests of stage gates, fold order, reversal, reduced motion, draft retention, case decisions, evidence navigation, and delayed responses. Automated checks do not establish that an analyst's reasoning is sound.

At widths of 400px or less, stage navigation uses two columns so the full names remain readable, and name entry places the action below the input. A smaller box keeps the default overview within a short phone viewport.

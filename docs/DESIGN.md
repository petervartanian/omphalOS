# Workbench design system

The interface takes inspiration from precise, restrained developer tools such as Vercel’s dashboard. It is an independent omphalOS design, with no copied product assets or implied affiliation. Its purpose is to make investigative work inspectable: what records were considered, what was observed, what remains unresolved, and what an analyst assessed.

## Design principles

1. **Current work before explanation.** Returning analysts see recent runs and review state first. Instructions appear when the workspace is empty or within the relevant form.
2. **A neutral workspace.** White and off-white surfaces, fine gray dividers, compact controls, and system typography establish hierarchy. Panels have no decorative shadows. The dialog alone uses elevation to distinguish an overlay.
3. **Color means a state.** Amber identifies missing evidence, an unreviewed assessment, or synthetic records. Red identifies an error. File integrity is visually separate from analyst review. A recorded review is not shown as a green clearance.
4. **Evidence beside judgment.** Review forms retain the observation and direct evidence controls. Screening candidates expose compared names, list category, contradictory identity context, and available source timestamps before raw technical detail. Source acquisition distinguishes manual uploads of unauthenticated origin from official HTTPS downloads, and CSL aggregation time is not presented as a publisher update for every underlying list.
5. **Details on demand.** Catalog parameters, source formats, inventories, hashes, and raw JSON remain accessible in disclosures. They do not lead the normal workflow.
6. **No hidden loss or invented progress.** Drafts survive in-page navigation and workspace refresh. Long-running operations report an actual stage, without an estimated percentage. Stale responses do not replace the user’s current view.

## Tokens and components

`src/omphalos/ui/styles.css` defines the tokens and groups rules by component. The CSS is source code, not a generated or minified artifact.

| Layer | Rules |
| --- | --- |
| Surfaces | `--color-background`, `--color-surface`, `--color-subtle` |
| Text | `--color-text`, `--color-secondary`, `--color-muted` |
| Boundaries | Light `--color-border` for groups and rows; separate `--color-input-border` for recognizable input boundaries |
| Meaningful states | Positive, warning, and error foreground/background/border tokens |
| Type | Operating-system sans serif; system monospace for IDs and retained technical detail |
| Type sizes | 26px page title, 16–21px section/question hierarchy, 14px body and actions, 13px secondary text, 12px labels and compact metadata |
| Spacing | Named 4–40px spacing scale; 36px standard control height |
| Shape | 6px controls, 8px panels; no decorative gradients |
| Motion | Short control feedback; no entrance animation; reduced-motion preference respected |

Buttons have primary, secondary, and text variants. Use one clear primary action in the immediate task context. Disabled and busy states remain distinct. Status badges always include text; color never carries the meaning alone. Numeric counts use tabular numerals.

Panels group related content. Table panels have a compact header, a consistent row rhythm, and a horizontally scrollable table area when necessary. Inputs use persistent labels and contextual instructions. Details disclosures provide optional depth without removing access to the underlying information.

## Page hierarchy

- **Overview:** recent analysis, operational counts, and saved cases. An empty workspace provides a short path through import, case definition, and review.
- **Data & sources:** dataset inventory, dataset import disclosure, source inventory, and snapshot acquisition disclosure. Synthetic data is an explicit secondary action, with a persistent synthetic designation in runs and reports.
- **Cases:** saved definitions first; a new-case editor opens on request or when a draft is active. The editor contains the question, dataset, date, optional scope, investigation selection, and optional screening snapshot. Investigation settings remain in each row’s disclosure. A workspace without a dataset shows the action required to proceed.
- **Findings & review:** run selection, question, coverage counts, review state, and the next action. Verification and replay live under **Evidence integrity**. The detail tabs organize observations, coverage, assessment, and retained context.

Observations and review fields are paged in groups of 20. Large evidence-reference groups show the first 40 records and explicitly offer the next group. Counts always distinguish the visible subset from the complete result. Pagination is a display concern; every finding still requires assessment before a complete review can be saved.

## Frontend organization

The product consists of three packaged assets: `index.html`, `styles.css`, and `app.js`. It requires no frontend build or runtime dependency. No font, script, icon, or stylesheet is fetched from a CDN. The navigation icons are small inline SVG shapes.

`app.js` separates:

- Shared formatting, escaping, request handling, and state.
- Pure view components for tables, import forms, catalog rows, evidence details, and review fields.
- Page renderers that compose those components.
- Draft capture and view-ownership helpers.
- Named asynchronous operations and event handlers.

All untrusted text is escaped before it enters HTML. Evidence values remain text, not markup. External source links accept HTTPS and open with `noopener` and `noreferrer`. Backend validation and export gates remain authoritative.

The navigation generation, selected run, and current page identify which view owns an asynchronous request. Verification, export, run loading, and evidence dialogs check that context before updating the interface. A result can still be retained by the server without taking the user away from the page they chose.

Explicit New/Open case actions ask before replacing unsaved work. Ordinary navigation and refresh do not prompt. Case drafts may be incomplete: temporarily clearing every investigation does not discard the question. Review drafts merge the current page’s fields into the entire run assessment, preserving other pages. A save captures the submitted values before locking its form and does not clear a newer draft. Drafts are intentionally held in memory, rather than silently persisted to browser storage.

## Accessibility and verification

Semantic landmarks, persistent form labels, a route-preserving skip link, native dialogs, visible focus indicators, and textual statuses support keyboard and assistive-technology use. Run tabs support Left/Right arrows, Home, and End. The live status region sits outside the busy main region so progress announcements are not deferred. Layouts adapt to narrower windows; fixed-width tables scroll inside their container.

Input boundaries use a stronger neutral than decorative panel dividers. Color choices target readable contrast; the design does not claim a completed external WCAG certification. Browser inspection, keyboard checks, and actual workflow tests remain necessary alongside static linting.

The development checks are reproducible through `npm run lint` and `npm run format:check`. These development tools are not shipped as product dependencies. The Python suite includes actual HTTP workflow tests and offline Node tests of draft retention, pagination, route preservation, and delayed-response handling. Automated checks do not assess whether an analyst’s reasoning is sound.

# Usability decisions, October 16, 2026

omphalOS should carry a person from a subject or a set of records to evidence they can inspect, a decision they explicitly make, and a package they can reopen. Visual polish matters only if those actions are understandable and reliable.

## Research used

The review used primary design and accessibility guidance:

- [Vercel's product-design guidance for agents](https://vercel.com/blog/teaching-agents-product-design-at-vercel): define the user's job before choosing a visual treatment; inspect real empty, loading, error, and recovery states; verify the rendered result.
- [Vercel Web Interface Guidelines](https://vercel.com/design/guidelines): keyboard operation, visible focus, usable targets, necessary motion, and preservation of interface state.
- [Nielsen Norman Group's usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/): visible status, recognition instead of recall, user control, and constructive recovery.
- [Microsoft's human-AI interaction guidelines](https://www.microsoft.com/en-us/haxtoolkit/ai-guidelines/): make capabilities understandable, support correction, and leave consequential decisions under user control. These principles inform the automation; they do not imply that omphalOS uses a language model.
- [WCAG use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html), [text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html), and [target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html): meaning must survive loss of hue discrimination, ordinary text needs at least 4.5:1 contrast, and targets must be usable without precise pointing.

These sources informed specific decisions, rather than supplying a visual theme or a certification.

## Investigation controls

The Commerce Office of Inspector General's [May 4, 2026 audit of BIS enforcement of Russia and Belarus export controls](https://www.oig.doc.gov/audit-of-the-bureau-of-industry-and-securitys-enforcement-of-russia-and-belarus-export-controls/) examined end-use checks from fiscal years 2022–2023. Its [process diagram and findings](https://www.oig.doc.gov/wp-content/OIGPublications/OIG-26-019-A_FinalReport-SECURED.pdf) distinguish target approval, evidence collection and recommended ratings, and supervisory review; the audit also identifies manual-entry and evidence-retention weaknesses. This is a bounded example of an investigative process, not a universal BIS workflow.

The design implication is to automate retrieval and plan drafting while recording the user's source acceptance, execution approval, and assessment separately. **Use these sources** completes II; **Run reviewed plan** records III; **Mark results reviewed** acknowledges IV. Computation and file verification cannot substitute for those actions. Older runs retain their actual history, including absent approval records.

The [official CSL guidance](https://www.trade.gov/consolidated-screening-list) describes the list as a screening aid. Apparent matches require further due diligence and checking the underlying official lists and Federal Register. omphalOS supports evidence inspection; it does not conduct field inspections or interviews, authenticate supervisors, enforce separation of duties, or reproduce an agency's approval hierarchy.

## What separates a useful tool from a polished mockup

| Question | Implemented behavior |
| --- | --- |
| Can a new person begin without inventing technical inputs? | Name entry is primary. Import is optional. Source acquisition and plan drafting are automatic; identity selection, source acceptance, and authorization to run remain explicit. |
| Is the next action clear? | Six named stages follow Records, Sources, Plan, Findings, Assessment, and Package. A stage becomes available when its inputs exist. |
| Does completion mean something real? | Selected records complete I; accepted sources complete II; an explicitly authorized, verified run completes III. Results review completes IV, a saved decision completes V, and a matching export closes VI. Merely opening a panel does not complete it. |
| Can someone read and act without scrolling past decoration? | The overview fits one page at tested sizes. Opening a stage places work beside the box on desktop and uses compact stage navigation on narrow screens. |
| Can someone distinguish unfinished from finished without relying on red and green? | Stages I–V have light and deeper pigments. Every stage retains a numeral, name, completion check, and fold state; the completed package gains a shared dark rainbow finish and engraved pattern. |
| Is an error recoverable? | Invalid imports retain a preview with correction actions. Failed or lost-response execution can resume the exact approved plan. Evidence-page retries retain the requested page. |
| Does the application preserve ownership of the work? | Late responses cannot replace newer work. Drafts survive in-page navigation. New and Open remain available. Retained runs keep their original dataset identity. |
| Can the output be inspected independently? | Packages retain inputs, analysis, provenance, and the actual saved review. Verification and replay show readable outcomes and preserve the download. |

## Color and motion

Stages I–V use blue, teal, peach, yellow, and pink, with their own light and completed colors. VI starts neutral gray with a visible engraved pattern. The completed package uses the same charcoal base and continuous rainbow material across every panel. There is no diagonal stripe. Exact values are in [DESIGN.md](DESIGN.md).

The Package lid has an engraved weave and an embossed border over a neutral gray base before completion. After verified export, every panel takes on a neutral charcoal base with gentle highlights, continuous rainbow reflection, and fine engraved weave; no stage pigment remains underneath. The full red-to-magenta spectrum is ordered across the object, with balanced, subdued color strength and no blue base or overlapping color pools. Caption ink adapts to the reflected color, without a blank patch in the finish. The finish adds no idle motion. Changing the assessment removes the completed finish until a new matching export is created.

Tests check text contrast across gradient stops and intermediate folds, and completion lightness changes under normal and simulated red-green vision. Simulations cannot establish what any individual sees. Full names, Roman numerals, checkmarks, and geometry remain necessary cues.

There is no idle rotation. One hinge folds at a time after actual completion. Invalidated work unfolds in reverse order. Reduced-motion preferences settle the geometry immediately. External controls remain usable independently of the illustration.

## Boundaries

This is a local application with deterministic checks and public identity/reference providers. It does not perform unlimited open-web investigation, ingest arbitrary documents, establish identity automatically, or decide whether a person or organization is legally restricted. Checks can only examine supported records and the retained sources available to them.

The browser acceptance tests and regression suite are recorded in [VALIDATION.md](VALIDATION.md). They provide evidence for specific behavior, not proof of perfection, operational detection accuracy, or a complete accessibility certification. Real-world work should retain visible coverage limits and an explicit human decision.

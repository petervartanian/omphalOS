# Practitioner evaluation protocol

This is a prepared study protocol, not a completed study. No practitioner observations or operational accuracy results have been invented. Automated simulations and the labeled detection benchmark are documented separately.

## Participants and records

Recruit people who actually perform the intended work: intake analysts, investigators, and independent reviewers. Include keyboard users and users with color-vision differences. Use authorized, representative, de-identified records with known provenance. Do not place confidential records in the public repository, public issues, or test fixtures. Set the organization's definition of a material miss before examining the application's results.

Have two qualified reviewers label the reference outcomes independently, record disagreements, and adjudicate them before scoring. Distinguish a pattern the software should identify from an actual violation or a legally sufficient identity determination. Include benign records that share suspicious patterns; do not exclude difficult cases after seeing results. Separate development/tuning records from held-out evaluation records.

## Tasks

Give each participant the goal and records, without revealing interface steps. Observe without coaching; record assistance whenever it is necessary.

| Task | Evidence of success | Critical failure |
| --- | --- | --- |
| Start a new case from a subject | Correct identity candidate or explicit unresolved identity; relevant source and scope accepted | A similar name is treated as proven identity |
| Investigate linked transaction records | Original records and coverage inspected; missing sources distinguished from negative findings | A check that did not run is interpreted as clearance |
| Consider a benign explanation | Supporting evidence is found, attributed, and included in reasoning | The supplied explanation is mistaken for verified fact or overlooked |
| Keep a case open or escalate | Disposition and concrete reason/next step survive reload and export | Export completion is mistaken for case closure |
| Hand a case to another person | Recipient, seeing only the package, finds question, evidence, coverage, decision, and next action | Recipient must ask the original analyst to reconstruct missing context |
| Return independent review | Correct exact package signed, key independently confirmed, receipt checked by sender | A copied untrusted key, stale package, or self-review is treated as independent approval |
| Continue after new evidence | Original case is retained; separate current work receives new approvals | Prior approvals are silently reused or colleagues' decisions overwrite one another |

## Record and compare

For each attempt record participant role, task, case identifier, application revision, start/end time, completion without assistance, assistance count, wrong turns, critical error, evidence inspected, and the participant's explanation of the resulting state. Store these records privately. Report completion rates and distributions of time and assistance by task and participant type; do not replace them with a single overall score. Report confidence and denominator for detection estimates, class prevalence, unavailable checks, and benign-pattern burden. Do not compare test counts with usability scores.

Before release into an organization's operational workflow, review every critical failure, reproduce the cause, correct it, and repeat the affected task with participants who were not taught the workaround. Agree on organization-specific acceptance thresholds before running the study. This protocol does not supply invented universal thresholds or imply that a few participants establish population-level reliability.

The approach follows the UK government's primary guidance on [moderated usability testing](https://www.gov.uk/service-manual/user-research/using-moderated-usability-testing) and [usability benchmarking](https://www.gov.uk/service-manual/measuring-success/usability-benchmarking-a-website-or-whole-service). These research methods inform evaluation; they do not certify this product.

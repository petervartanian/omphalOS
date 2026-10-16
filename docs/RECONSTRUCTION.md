# Reconstruction from the original omphalOS

Audited public repository: https://github.com/petervartanian/omphalOS

Baseline commit: `09d100eb936a3d9b11e91958801b8240d4ab98d6`. Local examination date: October 13, 2026.

## What the original intended to do

The repository describes trade/sanctions investigations with reproducible evidence and disciplined treatment of uncertainty. Earlier code contained entity matching, analytical streams, lineage, and report generation. Its useful intent was to let an analyst trace, challenge, and reproduce a conclusion.

The public Git history begins December 14, 2025. That does not establish when private work began and does not disprove an older origin. The current application code was largely introduced in January 2026; the README continued changing afterward.

## What the audit reproduced

| Area | Reproduced result | Successor response |
|---|---|---|
| Main runner | Ignored investigation definitions and almost all case fields; counted synthetic rows and returned empty claims | Validated case contract; selected detectors actually execute; exact coverage is required |
| Investigation library | About 20,000 SQL files reduced to seven bodies/one domain template; five canonical patterns failed their schema | Small distinct catalog with prerequisites, parameters, limitations, and behavioral fixtures |
| Unit price | A purported median was an average; `[1,1,1,1,100]` exposed incorrect outlier behavior | Actual median within currency/unit/commodity cohorts |
| Invoice linkage | Generic invoice prefixes caused broad meaningless groups | Normalized meaningful invoice identities and supporting record references |
| Run identity | Same-second runs could retain previous rows | Unique run IDs and atomic finalization |
| Verification | Empty checksum inventories could pass | Mandatory artifacts, exhaustive inventory, schema/digest checks, and tamper tests |
| Export | The current runner's own output could not pass its export path | Shared review/export contract and actual round-trip tests |
| Installation | Archive path handling permitted traversal/deletion in isolated synthetic reproductions | Standard package installation; no custom archive-extracting installer |
| Native verifiers | Rust/C++ entrypoints did no useful verification; Go ignored parsing errors | Executable independent Go/Rust inventory verifiers, with stated scope |
| Workbench | Fixed demo figures rather than live analytical state | Browser reads actual workspace, results, coverage, reviews, and verifier responses |
| CI | All 92 retrieved GitHub Actions runs failed; latest failed at installation | Installable package and configured platform/version matrix; local results reported separately |

Earlier historical code was not a sound version to restore wholesale: tests exposed an unresolved golden-output failure, and a classification mismatch yielded zero scores while static packet prose still described elevated exposure. The successor preserves the aim and useful design ideas while replacing the broken execution and evidence paths.

The detailed original audit, isolated reproductions, historical snapshots, and original clone are preserved in the separate local audit directory. They are not imported into the successor's runtime or represented as successful feature tests.

## Migration

Version 2 does not automatically trust old run packets or copy old conclusions. Re-import original source records through the current schema, record a new case, execute a new run, and review its actual results. Keep the old packet as a separate historical record if needed. Legacy query counts and generated patterns are not compatibility promises.

# Standards of Review (v1.0)

omphalOS exists to make doubt institutional: the record must *force* modesty even when the analyst is confident, fatigued, or hurried.

This document is normative. The export gate enforces it.

## 1. Claim discipline

A packet may contain claims, but every claim is procedurally incomplete unless it carries:

- **Evidence**: explicit artifact pointers with cryptographic hashes.
- **Unknowns**: what the claim does not establish.
- **Alternatives**: rival explanations consistent with the evidence.
- **Falsifiers**: what would overturn, weaken, or reframe the claim.

No claim may be exported if any of the above is empty.

## 2. Admissibility of investigations

An investigation is admissible only if its SQL is self-identifying and reviewable.

Minimum requirements:

1. Header lines for **Investigation**, **Domain**, and **Intent**.
2. Canonical restraint: at least sixty `-- Canon` lines.
3. Margin reminders: at least forty-five `-- Margin` lines.
4. A terminal `LIMIT`, to prevent accidental materialization of unbounded rowsets.

These constraints are intentionally severe. They are a substitute for institutional oversight when operating offline.

## 3. Language discipline

Packets are prohibited from using conclusory certainty language (for example: “proves”, “must be”, “conclusively”).
If such language is necessary, it must be litigated in a separate document and attached as evidence.

## 4. Portability, provenance, and audit

A run is only a run if it is portable:

- the case is snapshotted into the run directory
- the packs used are snapshotted into the run directory
- every emitted artifact is checksummed in the run manifest

A verifier must be able to re-compute hashes without consulting the original repository.


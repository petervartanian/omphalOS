# Standards of Review

omphalOS exists to make doubt institutional: the record must force modesty even when the analyst is confident, fatigued, or hurried.

This document is normative. The export gate enforces it.

## Claim Discipline

A packet may contain claims, but every claim is procedurally incomplete unless it carries:

- **Evidence**: explicit artifact pointers with cryptographic hashes
- **Unknowns**: what the claim does not establish
- **Alternatives**: rival explanations consistent with the evidence
- **Falsifiers**: what would overturn, weaken, or reframe the claim

No claim may be exported if any of the above is empty. The export gate (implemented in `core/src/omphalos/standards.py`) enforces this programmatically.

## Admissibility of Investigations

An investigation is admissible only if its SQL is self-identifying and reviewable.

Minimum requirements:

(i) Header lines for **Investigation**, **Domain**, and **Intent**

(ii) Canonical restraint: at least sixty `-- Canon` lines

(iii) Margin reminders: at least forty-five `-- Margin` lines

(iv) Terminal `LIMIT`, to prevent accidental materialization of unbounded rowsets

These constraints are intentionally severe. They are a substitute for institutional oversight when operating offline. The standards module validates these requirements before investigations execute.

## Language Discipline

Packets are prohibited from using conclusory certainty language (for example: "proves", "must be", "conclusively", "certainly", "definitively", "undoubtedly", "irrefutably").

If such language is necessary, it must be litigated in a separate document and attached as evidence.

The export gate scans observation text for prohibited terms and rejects packets containing them.

## Portability, Provenance, and Audit

A run is only a run if it is portable:

- The case is snapshotted into the run directory
- The packs used are snapshotted into the run directory
- Every emitted artifact is checksummed in the run manifest

A verifier must be able to re-compute hashes without consulting the original repository. Years after a case closes, the exact analytical process can be reconstructed bit-for-bit.

## Export Gate Enforcement

The export gate operates as follows:

(i) Packet is loaded from `packet.json`

(ii) Schema validation confirms structure matches `packet.json` schema

(iii) Admissibility check confirms presence of unknowns, alternatives, falsifiers (all non-empty)

(iv) Language scan detects prohibited certainty terms in observations

(v) Annex validation confirms all evidence has SHA-256 hashes

If any check fails, the export gate returns `REJECT` with specific violations. The packet cannot be exported until remediated.

## The Principle

Institutionalized doubt through computational enforcement.

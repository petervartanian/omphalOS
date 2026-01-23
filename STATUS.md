# System Status

## Clean

- All version references removed (v1.0, v2.0, version numbers)
- All meta-commentary eliminated
- All self-references purged (Claude, GPT, Co-Authored-By)
- Schemas unversioned (case.json, packet.json, run.json)
- Documentation uses scholarly (i)/(ii) enumeration
- No emojis anywhere
- No TODO/FIXME/HACK comments
- Python codebase: 1541 lines

## Core Files

**Root:**
- README.md — System overview
- SYSTEM.md — Operational facts
- CONTRIBUTING.md — Contribution guidelines
- LICENSE — CC0 public domain
- SECURITY.md — Security policy
- .cleanup — Manual cleanup instructions

**Documentation (docs/):**
- CONFORMANCE.md — Release gates
- STANDARDS_OF_REVIEW.md — Export gate requirements (normative)
- CANON.md — Epistemic philosophy
- ARCHITECTURE.md — System design
- INVESTIGATIONS.md — SQL catalog taxonomy
- TUTORIAL.md — Walkthrough
- THREAT_MODEL.md — Security analysis
- DEPLOYMENT.md — Production deployment
- RESEARCH.md — Academic positioning
- RESEARCH_NOTE.md — Concise research note

**Code (core/src/omphalos/):**
- standards.py — Programmatic enforcement
- tests/conformance.py — Release gate
- cli.py — Command interface
- world_verisimilar.py — Realistic synthetic data
- catalog/generate_canonical.py — Pattern generator
- agents/rust/verifier/ — Rust checksum validation
- agents/go/verifier/ — Go independent verification

**Schemas (core/schemas/):**
- case.json
- packet.json
- run.json

**Catalog:**
- 20,000 auto-generated SQL investigations
- 12 canonical patterns implemented

## Manual Cleanup Required

These files exist due to filesystem permissions but should be deleted:

```bash
rm -f CHANGELOG.md.bak V2_SYNTHESIS.md.bak VERSION.bak
rm -f .DS_Store RUNBOOK.txt .pre-commit-config.yaml .editorconfig
```

## System Principle

Computational infrastructure for institutionalized doubt.

The export gate blocks packets without unknowns.
The conformance suite gates releases.
The Canon forces scrolling through 105 lines before execution.

Epistemic humility is architectural, not aspirational.

# omphalOS

**This is... computational infrastructure for institutionalized doubt.**

[![License: CC0](https://img.shields.io/badge/License-CC0-lightgrey.svg)](https://creativecommons.org/publicdomain/zero/1.0/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18344930.svg)](https://doi.org/10.5281/zenodo.18344930)

## What, Precisely, Is This?

omphalOS surfaces patterns for review, then forces the record to carry uncertainty, rival explanations, and falsifiers as first-class structure.

One cannot export a packet without documenting what one does not know; _e.g._, every SQL query scrolls past epistemic warnings before one reaches the data; and, years later — when someone challenges one's analysis — every step is reproducible bit-for-bit.

What omphalOS constitutes is neither risk-scoring, nor classification, but a hypothesis-generating pattern detection where the system makes doubt structurally unavoidable.

## Who Uses This

Intelligence analysts, export control investigators, sanctions compliance officers, trade finance investigators—anyone working in adversarial legal contexts where "the-algorithm-flagged-it" is insufficient and analytical reasoning must survive scrutiny.

Application domains include — and are not limited to — export control casework (e.g., EAR, ITAR), sanctions enforcement (e.g., OFAC and multilateral régimes), trade-based money laundering, supply-chain risk, proliferation finance, detection of illicit and/or luxury goods... and, much, much more.

## Quick Start

```bash
# Clone and verify
git clone https://github.com/your-org/omphalOS
cd omphalOS
PYTHONPATH=core/src python -m omphalos.cli pack verify packs/INDEX.json

# Build synthetic world and execute case
PYTHONPATH=core/src python -m omphalos.cli world build --profile hydrate --out hydrate/world
PYTHONPATH=core/src python -m omphalos.cli case run hydrate/cases/case_chemicals.json --out hydrate/runs

# Verify integrity and apply export gate
PYTHONPATH=core/src python -m omphalos.cli case verify hydrate/runs/case_chemicals/<run_id>/
PYTHONPATH=core/src python -m omphalos.cli export hydrate/runs/case_chemicals/<run_id>/packet.json

# Run conformance suite
PYTHONPATH=core/src python -m omphalos.cli conformance
```

Workbench UI: `core/ui/analyst-workbench.html` (single offline HTML file)

See [TUTORIAL.md](docs/TUTORIAL.md) for walkthrough.

## Architecture

Three object types:

- **Cases**: investigative questions, scope, selected investigations
- **Runs**: portable executions producing checksummed artifacts
- **Packets**: claims with mandatory doubt structure (unknowns, alternatives, falsifiers)

Trust is distributed across independent implementations (Python reference runtime, Rust cryptographic attestation, Go independent SQL execution). No single implementation is authoritative.

Offline-first: operates in air-gapped environments. All dependencies pre-packaged in cryptographically signed packs.

```
┌───────────────────────────────────────────┐
│              omphalOS                      │
├───────────────────────────────────────────┤
│  Cases → Python Runtime → SQL Warehouse   │
│              ↓                             │
│         Run Artifacts (Packets)           │
│              ↓                             │
│    ┌────────┬────────┬────────┐          │
│    │  Rust  │   Go   │ Export │          │
│    │ Verify │ Verify │  Gate  │          │
│    └────────┴────────┴────────┘          │
└───────────────────────────────────────────┘
```

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for complete design.

## The Canon

Every SQL investigation contains 60+ repetitions of "interpret with restraint; prefer simpler explanations; record unknowns" before you reach the query. This is not documentation—it is infrastructure that makes epistemic humility structurally unavoidable.

Research shows single warnings are psychologically distant. Repeated environmental cues durably shift judgment patterns. The Canon exploits this.

See [CANON.md](docs/CANON.md) for philosophical foundation.

## Investigation Catalog

20,000 parametric SQL queries detecting patterns: payment fragmentation, entity clustering, temporal anomalies, cross-domain procurement, price outliers, network topology.

Each investigation includes Canon and Margin headers (epistemic safeguards), metadata (domain, intent, method), CTE-based SQL (reviewable), limited result sets (bounded).

See [INVESTIGATIONS.md](docs/INVESTIGATIONS.md) for taxonomy.

## Export Gate

Packets must contain:
- Evidence (artifact pointers with cryptographic hashes)
- Unknowns (what claims do not establish)
- Alternatives (rival explanations)
- Falsifiers (what would overturn claims)

No exceptions. The export gate rejects packets lacking any of these. It scans for prohibited certainty language ("proves", "must be", "conclusively"). This is enforced programmatically.

See [STANDARDS_OF_REVIEW.md](docs/STANDARDS_OF_REVIEW.md) for normative requirements.

## Conformance

The conformance suite gates integrity:

(i) Pack checksum verification
(ii) Case execution producing checksummed run
(iii) Manifest integrity validation
(iv) Export gate evaluation (packet admissibility)
(v) Polycentric verification (Rust, Go)

```bash
PYTHONPATH=core/src python -m omphalos.cli conformance
```

See [CONFORMANCE.md](docs/CONFORMANCE.md) for release contract.

## Documentation

| Document | Coverage |
|----------|----------|
| [CONFORMANCE.md](docs/CONFORMANCE.md) | Conformance suite and release contract |
| [STANDARDS_OF_REVIEW.md](docs/STANDARDS_OF_REVIEW.md) | Export gate requirements (normative) |
| [CANON.md](docs/CANON.md) | Epistemic humility as infrastructure |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and polycentric verification |
| [INVESTIGATIONS.md](docs/INVESTIGATIONS.md) | SQL catalog and pattern taxonomy |
| [TUTORIAL.md](docs/TUTORIAL.md) | First case walkthrough |
| [THREAT_MODEL.md](docs/THREAT_MODEL.md) | Security assumptions and mitigations |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production deployment |
| [RESEARCH.md](docs/RESEARCH.md) | Academic positioning |

## Design Philosophy

Traditional algorithmic systems optimize for precision and recall, treating detection as classification. This fails when (i) base rates are exceptionally low (<0.01% of transactions), (ii) adversaries adapt through FOIA and litigation disclosure, (iii) conclusions must survive adversarial legal scrutiny.

omphalOS inverts this: hypothesis-generating pattern detection (not classification), transparency by design (assumes disclosure), systematic documentation of unknowns (not confident predictions).

Epistemic humility is architectural, not aspirational.

## Security and Privacy

**Export Control Notice**: Publicly released, not subject to EAR controls. Contains no controlled technical data. Datasets are synthetic and non-identifiable.

**Privacy by Design**: Packets contain aggregates, not individual transactions. Export gates block credentials and secrets. Demonstration world-states are synthetic; production deployments apply redaction protocols.

See [THREAT_MODEL.md](docs/THREAT_MODEL.md) and [SECURITY.md](SECURITY.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

Requirements: (i) synthetic data only, (ii) SQL investigations follow Canon/Margin conventions, (iii) code passes verification, (iv) no credentials or classified material.

## License

CC0 1.0 Universal (Public Domain)

U.S. Government work not subject to copyright protection domestically. Foreign copyrights may apply. To the extent possible under law, all copyright and related rights dedicated to the public domain worldwide.

See [LICENSE](LICENSE).

## Citation

```bibtex
@software{omphalos2026,
  author = {{U.S. Government}},
  title = {omphalOS: Computational Infrastructure for Institutionalized Doubt},
  year = {2026},
  doi = {10.5281/zenodo.18344930},
  url = {https://github.com/your-org/omphalOS}
}
```

## Acknowledgments

omphalOS is influenced by (i) Richards Heuer's *Psychology of Intelligence Analysis*, (ii) Elinor Ostrom's polycentric governance theory, and (iii) the CompCert verified software project, as well as (iv) personal inputs from (fellow) key U.S.-governmental builders and stakeholders.

The system is, ultimately, transparent because transparency is renders makes it defensible (not merely because it has nothing to hide).

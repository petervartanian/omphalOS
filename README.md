# omphalOS

**A polycentric, offline-first casework suite for export control and sanctions intelligence analysis.**

[![License: CC0](https://img.shields.io/badge/License-CC0-lightgrey.svg)](https://creativecommons.org/publicdomain/zero/1.0/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18344930.svg)](https://doi.org/10.5281/zenodo.18344930)

## Overview

omphalOS is computational infrastructure for intelligence analysis that prioritizes epistemic humility, transparency, and reproducibility over predictive optimization. The system surfaces patterns in trade data that merit analytical review while systematically documenting uncertainty, making it suitable for adversarial legal contexts where analytical reasoning must withstand scrutiny.

The architecture provides (i) polycentric verification through multiple independent implementations, (ii) offline-first operation in air-gapped environments, (iii) embedded procedural safeguards against overconfident assessments, (iv) human-readable SQL investigations under version control, and (v) checksummed artifacts enabling bit-identical re-execution.

Application domains include export control casework under EAR and ITAR, sanctions enforcement through OFAC and multilateral regimes, trade-based money laundering detection, supply chain risk analysis, and proliferation finance investigations.

The system explicitly rejects classification paradigms. It does not predict entity behavior, assign risk scores, or operate as real-time monitoring infrastructure. All analytical operations are batch-oriented and hypothesis-generating.

## Quick Start

```bash
# Clone and verify
git clone https://github.com/your-org/omphalOS
cd omphalOS
PYTHONPATH=core/src python -m omphalos.cli pack verify packs/INDEX.json

# Build world and execute case
PYTHONPATH=core/src python -m omphalos.cli world build --profile hydrate --out hydrate/world
PYTHONPATH=core/src python -m omphalos.cli case run hydrate/cases/case_chemicals.json --out hydrate/runs

# Verify and export
PYTHONPATH=core/src python -m omphalos.cli case verify hydrate/runs/case_chemicals/<run_id>/
PYTHONPATH=core/src python -m omphalos.cli export hydrate/runs/case_chemicals/<run_id>/packet.json
```

See [TUTORIAL.md](docs/TUTORIAL.md) for detailed walkthrough.

## Architecture

The system operates through three core object types: (i) cases articulate investigative questions with defined scope and investigation selection, (ii) runs materialize cases against world-states producing checksummed artifacts, and (iii) packets structure analytical findings with explicit claims (observations and unknowns), annexes, and provenance chains.

Trust is distributed across independent implementations in Python (reference runtime), Rust (cryptographic attestation), and Go (independent SQL execution). A run achieves validity only when all verifiers agree on artifact integrity.

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

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for complete system design.

## Documentation

| Document | Coverage |
|----------|----------|
| [TUTORIAL.md](docs/TUTORIAL.md) | First case walkthrough |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and verification |
| [CANON.md](docs/CANON.md) | Epistemic humility as architectural principle |
| [INVESTIGATIONS.md](docs/INVESTIGATIONS.md) | SQL catalog and pattern taxonomy |
| [THREAT_MODEL.md](docs/THREAT_MODEL.md) | Security assumptions and mitigations |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production deployment and scaling |
| [RESEARCH.md](docs/RESEARCH.md) | Academic positioning and research agenda |

## Design Philosophy

Traditional algorithmic systems for intelligence analysis optimize for precision and recall, treating detection as a classification problem. This approach fails in domains where (i) base rates are exceptionally low (illicit transactions represent less than 0.01% of flows), (ii) adversaries adapt to disclosed detection logic through FOIA and litigation, and (iii) analytical conclusions must withstand adversarial legal scrutiny requiring transparent reasoning.

omphalOS inverts this paradigm. Rather than classification, the system provides hypothesis-generating pattern detection that surfaces anomalies without labeling them. Rather than concealing analytical methods, it assumes disclosure and designs for transparency. Rather than confident predictions, it systematically documents unknowns alongside observations.

The Canon—sixty repetitions of "interpret with restraint; prefer simpler explanations; record unknowns" embedded in every SQL investigation—makes epistemic humility structurally unavoidable. This design draws from research demonstrating that single warnings are psychologically distant while repeated environmental cues durably shift judgment patterns.

See [CANON.md](docs/CANON.md) for philosophical foundation.

## Investigation Catalog

The catalog contains 20,000 parametric SQL queries detecting patterns including (i) payment fragmentation indicating threshold evasion, (ii) entity clustering revealing shell company networks, (iii) temporal anomalies preceding sanctions implementation, (iv) cross-domain procurement suggesting proliferation activity, and (v) price outliers indicating transfer pricing or barter.

Each investigation includes Canon and Margin headers providing epistemic safeguards, metadata documenting domain scope and analytical intent, CTE-based SQL for reviewability, and limited result sets preventing analyst overwhelm.

See [INVESTIGATIONS.md](docs/INVESTIGATIONS.md) for complete pattern taxonomy.

## Polycentric Verification

| Implementation | Language | Function |
|----------------|----------|----------|
| Python | 3.10+ | Reference runtime and case orchestration |
| Rust | 1.70+ | Cryptographic attestation and schema validation |
| Go | 1.20+ | Independent SQL execution and result verification |

This architecture defends against implementation bugs, supply chain compromises, and single points of failure. Trust is distributed rather than concentrated.

## Security and Privacy

**Export Control Notice**: This software is publicly released and not subject to export controls under the Export Administration Regulations. It contains no controlled technical data. Included datasets are synthetic and non-identifiable.

**Privacy by Design**: Packets contain aggregates rather than individual transaction details. Export gates block credentials and secrets before artifacts leave secure environments. World-states for demonstration are synthetic; production deployments apply redaction protocols.

See [THREAT_MODEL.md](docs/THREAT_MODEL.md) and [SECURITY.md](SECURITY.md) for threat analysis and disclosure policy.

## Contributing

Contributions are welcome following guidelines in [CONTRIBUTING.md](CONTRIBUTING.md) and security protocols in [SECURITY.md](SECURITY.md).

Requirements: (i) all data must be synthetic and non-identifiable, (ii) SQL investigations must follow Canon and Margin conventions, (iii) code must pass verification, (iv) no credentials or classified material.

## License

CC0 1.0 Universal (Public Domain)

This work was produced by the United States Government and is not subject to copyright protection in the United States. Foreign copyrights may apply. To the extent possible under law, all copyright and related rights have been dedicated to the public domain worldwide.

See [LICENSE](LICENSE) for complete text.

## Citation

```bibtex
@software{omphalos2026,
  author = {{U.S. Government}},
  title = {omphalOS: A Polycentric Architecture for Epistemically Humble Intelligence Analysis},
  year = {2026},
  doi = {10.5281/zenodo.18344930},
  url = {https://github.com/your-org/omphalOS}
}
```

## Acknowledgments

Development influenced by Richards Heuer's *Psychology of Intelligence Analysis* (structured analytic techniques), Elinor Ostrom's polycentric governance theory, the CompCert verified software project, and the open-source intelligence community.

The system is designed to be transparent not because it has nothing to hide, but because transparency is what makes it defensible.

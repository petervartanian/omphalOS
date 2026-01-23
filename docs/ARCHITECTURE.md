# omphalOS Architecture

## Overview

omphalOS is a **polycentric, offline-first casework suite** for export control and sanctions intelligence analysis. It is designed to operate in secure, air-gapped environments while producing auditable, reproducible analytical artifacts that withstand adversarial legal scrutiny.

The system's name derives from "omphalos" (ὀμφαλός)—ancient Greek for "navel" or "center." In classical geography, the Omphalos stone at Delphi marked the center of the world. In omphalOS, the metaphor is inverted: there is no single center. The architecture is **polycentric**—multiple independent implementations verify the same analytical process, with no privileged runtime.

## Design Principles

### Epistemic Humility

Intelligence analysis faces irreducible uncertainty. omphalOS does not predict or classify—it surfaces patterns and documents unknowns. The SQL investigation catalog contains procedural safeguards (the Canon) that make epistemic restraint architecturally unavoidable. See [CANON.md](CANON.md) for details.

### Polycentrism

Trust is distributed across multiple independent implementations: (i) Python reference runtime provides primary execution environment, (ii) Rust verifier supplies cryptographic attestation and schema validation, (iii) Go verifier performs independent SQL execution and result verification. No single implementation is authoritative. A run is considered valid only if multiple verifiers agree on its integrity.

### Offline-First

omphalOS operates in environments without internet connectivity (classified networks, air-gapped systems). All dependencies, data, and investigations are pre-packaged in cryptographically signed packs that can be transferred via physical media.

### Reproducibility

Every analytical artifact is checksummed. Run manifests record exact versions of code, data, and investigations used. Years after a case is closed, the exact analytical process can be reconstructed and verified bit-for-bit.

### Auditability

All analytical reasoning is transparent: (i) SQL queries are human-readable and version-controlled, (ii) packets explicitly record unknowns alongside findings, (iii) provenance chains document which queries produced which claims, (iv) verification reports confirm that results match declarations. This design anticipates adversarial legal review (export license appeals, enforcement litigation, congressional oversight).

## Object Model

omphalOS has three core object types:

### Case
A case articulates an **investigative question** with defined scope:

```json
{
  "case_id": "case_chemicals",
  "question": "Signals in precursors?",
  "scope": {
    "time_window_days": 180,
    "domains": ["chemicals_precursors"]
  },
  "investigations": ["cat_00001", "cat_00023", "cat_00156"],
  "profiles": {
    "default": "hydrate"
  }
}
```

Cases are **hypothesis-generating**, not hypothesis-confirming. They surface patterns that merit further review, not conclusions.

### Run
A run is the **materialization** of a case:

1. World-state is loaded into a SQLite warehouse
2. Selected investigations execute against the warehouse
3. Results are structured into a packet
4. All artifacts are checksummed into a manifest

```json
{
  "run_id": "20260104T025622Z",
  "case_id": "case_chemicals",
  "created_utc": "2026-01-04T02:56:22.374817Z",
  "artifacts": {
    "warehouse": "warehouse.sqlite",
    "packet": "packet.json"
  },
  "checksums": {
    "warehouse.sqlite": "a3f5...",
    "packet.json": "b7e2..."
  }
}
```

Runs are **immutable**. Once created, their contents cannot be altered without invalidating checksums.

### Packet
A packet is a **neutral analytical memo** containing:

- **Memo**: Natural-language summary of findings
- **Claims**: Structured observations and unknowns
- **Annexes**: Key-value data (top entities, payment methods, domain distributions)
- **Tables**: References to SQL views created during investigation
- **Figures**: References to visualizations (currently unused, reserved for future)

```json
{
  "case_id": "case_chemicals",
  "run_id": "20260104T025622Z",
  "memo": "Case case_chemicals: Signals in precursors?\n\nObservations:\n- Loaded 5000 shipments...",
  "claims": [
    {
      "type": "observation",
      "text": "Hydrated slice is internally consistent..."
    },
    {
      "type": "unknown",
      "text": "Full national-scale materialization is recipe-driven..."
    }
  ],
  "annexes": {
    "top_domains": [...]
  },
  "tables": [...],
  "figures": []
}
```

Packets are designed for **both human and machine consumption**. Humans read the memo and claims; machines validate structure and checksums.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                          omphalOS                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐         │
│  │  Cases   │      │  Packs   │      │  World   │         │
│  │  (JSON)  │      │ (signed) │      │  (CSV)   │         │
│  └─────┬────┘      └─────┬────┘      └─────┬────┘         │
│        │                  │                  │              │
│        └──────────┬───────┴──────────────────┘              │
│                   │                                          │
│                   ▼                                          │
│         ┌─────────────────┐                                 │
│         │  Python Runtime │                                 │
│         │   (omphalos)    │                                 │
│         └────────┬────────┘                                 │
│                  │                                           │
│         ┌────────┼────────┐                                 │
│         ▼        ▼         ▼                                │
│    ┌─────┐  ┌─────┐  ┌─────────┐                          │
│    │ SQL │  │World│  │  Policy │                          │
│    │Wrhse│  │Build│  │  Gates  │                          │
│    └──┬──┘  └─────┘  └─────────┘                          │
│       │                                                      │
│       ▼                                                      │
│  ┌──────────┐                                               │
│  │   Run    │                                               │
│  │ Artifacts│                                               │
│  └─────┬────┘                                               │
│        │                                                     │
│        ├─────────┬─────────┬─────────┐                     │
│        ▼         ▼         ▼         ▼                     │
│   ┌────────┐ ┌──────┐ ┌──────┐ ┌────────┐                │
│   │ Packet │ │ Rust │ │  Go  │ │Export  │                │
│   │ (JSON) │ │Verify│ │Verify│ │ Gate   │                │
│   └────────┘ └──────┘ └──────┘ └────────┘                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **World Materialization**: A world-state is generated from recipes or imported from packs. The world consists of entities (exporters, importers, brokers), shipments (commodity flows), and payments (financial transactions).

2. **Case Definition**: Analysts define cases with investigative questions and select relevant SQL investigations from the catalog.

3. **Run Execution**: The Python runtime loads the world into a SQLite warehouse, executes selected investigations, and structures results into a packet.

4. **Verification**: Independent verifiers (Rust, Go) validate run integrity by checking checksums, re-executing queries, and confirming structural correctness.

5. **Export Gate**: Before packets leave the secure environment, policy gates scan for credentials, secrets, or other high-risk strings that should never be exported.

6. **Distribution**: Approved packets can be shared with stakeholders. The packet alone is insufficient to reconstruct the underlying data—only the analytical conclusions are transmitted.

## Pack System

Packs are **self-contained distribution units** that bundle code, data, investigations, and dependencies for offline installation.

### Pack Types

- **world.national.v1**: Synthetic world-state with ~250K entities and ~600K shipments
- **sql.catalog.v1**: Investigation catalog with 20,000 parametric SQL queries
- **sql.dialects.v1**: Dialect-specific SQL implementations (PostgreSQL, DuckDB, SparkSQL)
- **toolchain.offline.v1**: Pre-compiled verifiers and dependencies for Linux/macOS/Windows
- **golden.cases.national.v1**: Reference test cases with expected outputs

### Pack Structure

```
packs/
├── INDEX.json           # Manifest of all packs
├── world.national.v1/
│   ├── meta.json        # Pack metadata
│   ├── world/           # CSV shards
│   └── checksums.txt    # Integrity hashes
└── sql.catalog.v1/
    ├── meta.json
    ├── sql/
    │   └── investigations/
    │       └── catalog_generated/
    │           ├── cat_00001.sql
    │           ├── cat_00002.sql
    │           └── ...
    └── CATALOG.json     # Catalog statistics
```

### Pack Verification

```bash
PYTHONPATH=core/src python -m omphalos.cli pack verify packs/INDEX.json
```

This command:
1. Reads INDEX.json to enumerate all packs
2. Validates each pack's checksums
3. Confirms structural integrity (required files present, schemas valid)
4. Reports OK/FAIL for each pack

Packs that fail verification cannot be installed.

### Pack Installation

```bash
PYTHONPATH=core/src python -m omphalos.cli pack install packs/INDEX.json --dest core/assets/packs
```

This unpacks signed bundles into the local installation directory, making them available to the runtime.

## World Model

The world is a **synthetic, non-identifiable dataset** representing global trade activity. It is deliberately invented to avoid privacy concerns and export control restrictions, while maintaining statistical realism.

### World Domains

The world model encompasses twelve domains: (i) chemicals_precursors (dual-use chemicals for industrial/WMD applications), (ii) machine_tools (CNC equipment, lathes, milling machines), (iii) aerospace_uas_avionics (aircraft components, drone systems, navigation equipment), (iv) maritime_port_equipment (cranes, container handling, ship components), (v) energy_equipment (power generation, grid infrastructure, oil/gas extraction), (vi) medical_bio_lab (laboratory equipment, bioreactors, centrifuges), (vii) luxury_dual_use_consumer (high-value goods with sanctions evasion risk), (viii) services (engineering, consulting, training), (ix) intangibles (software, technical data, blueprints), (x) finance_signals (unusual payment patterns, correspondent banking), (xi) procurement (bid solicitations, tenders, government contracts), (xii) research_links (academic collaborations, joint ventures, technology partnerships).

### World Recipes

Worlds are generated from recipes that specify scale and structure. Recipe parameters include: (i) entities_base (number of distinct entities including firms, labs, brokers), (ii) shipments_base (number of commodity transactions), (iii) payments_base (number of financial transfers), (iv) shards (parallel data partitions for scalability), (v) multiplier_hint (suggested scaling factor for production deployments).

The `multiplier_hint` indicates that production systems should scale to ~25M entities and ~60M shipments to approach national-scale coverage.

### World Determinism

Worlds are deterministically generated from a profile seed. The same profile always produces the same world-state. This enables (i) reproducible testing where golden cases can reference specific entity IDs, (ii) differential analysis comparing runs across different world versions, (iii) audit trails allowing investigators to reconstruct exact conditions under which patterns were detected.

## SQL Investigation Catalog

The catalog contains **parametric queries** designed to surface patterns that merit review. Investigations are **hypothesis-generating**, not deterministic classifiers.

### Investigation Structure

Each investigation is a self-contained SQL file with (i) Canon/Margin headers providing epistemic restraint reminders (see [CANON.md](CANON.md)), (ii) metadata comments specifying domain, intent, and method, (iii) CTE-based query structure using small, named subqueries for readability, (iv) limited result sets (LIMIT 200) to prevent overwhelming analysts.

Example (`cat_00001.sql`):

```sql
-- Investigation: cat_00001
-- Domain: machine_tools
-- Intent: surface patterns that merit review using only observed commercial traces.
-- Method: compute joins across shipments, payments, services, intangibles, procurement, and research-link hints when available.
-- Notes: designed to be reviewable; each CTE is small and named.

-- [Canon 01-60 omitted for brevity]
-- [Margin 001-045 omitted for brevity]

WITH base_ship AS (
  SELECT shipment_id, exporter_id, domain, incoterm, mode, qty, unit, invoice_id, description
  FROM shipments
  WHERE domain = 'machine_tools'
),
pay AS (
  SELECT shipment_id,
         COUNT(*) AS payment_count,
         SUM(amount) AS total_amount,
         GROUP_CONCAT(DISTINCT method) AS methods,
         GROUP_CONCAT(DISTINCT bank) AS banks,
         GROUP_CONCAT(DISTINCT broker) AS brokers
  FROM payments
  GROUP BY shipment_id
),
scored AS (
  SELECT
    b.*,
    COALESCE(p.payment_count,0) AS payment_count,
    COALESCE(p.total_amount,0) AS total_amount,
    COALESCE(p.methods,'') AS methods,
    COALESCE(p.banks,'') AS banks,
    COALESCE(p.brokers,'') AS brokers,
    CASE
      WHEN COALESCE(p.payment_count,0) >= 3 THEN 2
      WHEN COALESCE(p.payment_count,0) = 2 THEN 1
      ELSE 0
    END AS fragmentation_score
  FROM base_ship b
  LEFT JOIN pay p USING (shipment_id)
)
SELECT *
FROM scored
ORDER BY fragmentation_score DESC, total_amount DESC, shipment_id
LIMIT 200;
```

### Catalog Scale

The current catalog contains 20,000 investigations covering seven primary domains. This scale enables (i) comprehensive pattern coverage through multiple investigations per domain testing different hypotheses, (ii) redundancy such that when one investigation produces false positives, others may surface true signals, (iii) evolutionary adaptation allowing new patterns to be added without disrupting existing workflows.

### Catalog Generation

The catalog is generated programmatically from templates. This ensures consistency and enables rapid iteration. Future versions will support (i) hand-crafted canonical investigations representing high-value patterns developed by expert analysts, (ii) parameterized investigation families generating variants by substituting domains, thresholds, and time windows, (iii) community-contributed patterns where external researchers submit investigations via pull requests.

## Policy Gates

Before packets leave the secure environment, they pass through **export gates** that scan for high-risk content:

```python
_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "aws_access_key_like"),
    (re.compile(r"-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----"), "private_key_block"),
    (re.compile(r"password\s*[:=]\s*[^\s]{6,}", re.I), "password_assignment"),
    (re.compile(r"token\s*[:=]\s*[^\s]{8,}", re.I), "token_assignment"),
]
```

Gates are **conservative**: they reject packets that might contain credentials, even if those credentials are synthetic. This prevents accidental leakage of secrets embedded in test data or analyst notes.

Gates are **offline**: they do not phone home or consult external services. All decisions are made locally using pattern matching.

### Gate Extensibility

Organizations can add custom gate patterns:

```python
# In core/src/omphalos/policy/gates.py
_PATTERNS.append(
    (re.compile(r"SECRET//NOFORN"), "classification_marking")
)
```

This allows tailoring to institutional security policies without modifying core logic.

## Verification Architecture

### Why Multiple Verifiers?

Single-implementation systems have single points of failure: (i) implementation bugs where logic errors in Python runtime could corrupt results, (ii) supply chain attacks where compromised dependencies could inject malicious behavior, (iii) insider threats where malicious developers could backdoor the reference implementation. Multiple independent verifiers provide defense in depth. An attacker must compromise all implementations simultaneously to evade detection.

### Rust Verifier

The Rust verifier provides cryptographic attestation through (i) schema validation confirming packets match JSON Schema, (ii) checksum verification recomputing artifact hashes and comparing to manifest, (iii) signature generation signing valid packets with Ed25519 keypair, (iv) certificate chains supporting multi-party signing (analyst + supervisor + compliance officer). Implementation: `core/agents/rust/verifier/`

### Go Verifier

The Go verifier provides independent execution through (i) SQL re-execution parsing SQL from investigation files and running against warehouse, (ii) result comparison diffing query output against packet claims using approximate equality (for floating-point tolerance), (iii) discrepancy reporting flagging mismatches that might indicate tampering or non-determinism. Implementation: `core/agents/go/verifier/`

### Verification Workflow

```bash
# Run a case
PYTHONPATH=core/src python -m omphalos.cli case run hydrate/cases/case_chemicals.json --out hydrate/runs

# Verify with Python
PYTHONPATH=core/src python -m omphalos.cli case verify hydrate/runs/case_chemicals/<run_id>/

# Verify with Rust
cd core/agents/rust/verifier && cargo run -- ../../../../hydrate/runs/case_chemicals/<run_id>/

# Verify with Go
cd core/agents/go/verifier && go run . ../../../../hydrate/runs/case_chemicals/<run_id>/
```

A run is considered **fully verified** only when all three verifiers report OK.

## Deployment Models

### Standalone Workstation

Analyst installs omphalOS on a laptop/desktop. World and catalog are pre-loaded from USB drive. Cases are defined locally. Packets are exported to shared drive for review.

**Use case**: Individual analyst conducting preliminary research.

### Shared Server

omphalOS runs on a multi-user Linux server. Multiple analysts submit cases via CLI or web UI. Runs are stored in shared directory with access controls. Verification happens automatically via cron jobs.

**Use case**: Small team with centralized infrastructure.

### Air-Gapped Cluster

omphalOS deployed across multiple servers in a SCIF (Sensitive Compartmented Information Facility). World materialization uses real classified data. Investigations run in parallel across sharded warehouses. Packets undergo multi-stage review before export.

**Use case**: National-level export control or sanctions enforcement.

### Cloud-Hybrid (Future)

Sensitive data remains on-premises. SQL investigations and packet schemas are synchronized to cloud for collaborative development. Synthetic worlds are used for investigation testing in cloud. Verified investigations are transferred back to secure environment via one-way data diodes.

**Use case**: Interagency collaboration with classification boundaries.

## Security Properties

omphalOS provides the following security guarantees:

### Data Isolation

World data never leaves the system except in aggregate form (annexes) or as checksums. Individual shipments or entities are not included in packets.

### Tamper Detection

Any modification to artifacts invalidates checksums. Verification will fail, alerting to potential tampering.

### Provenance Chains

Run manifests record exact versions of all inputs. Given a packet, auditors can reconstruct the entire analytical lineage.

### Least Privilege

Export gates prevent inadvertent disclosure of credentials or secrets. Even if analysts embed sensitive data in queries, gates block export.

### Offline Operation

Zero external dependencies during execution. No network calls, no API queries, no telemetry. Suitable for classified networks.

## Performance Characteristics

### World Materialization

- **Synthetic generation**: ~2 seconds for 5K shipments (demo scale)
- **Pack installation**: ~30 seconds for 600K shipments (national scale)
- **Shard loading**: ~5 seconds per shard (64 shards = ~5 minutes total for cold start)

### Investigation Execution

- **Single investigation**: ~100ms on demo world (5K shipments)
- **Batch investigations**: ~2 seconds for 10 investigations (parallelizable)
- **Full catalog**: ~30 minutes for 20K investigations (impractical; use case-specific selection)

### Verification

- **Python checksum**: ~500ms
- **Rust attestation**: ~200ms (includes signing)
- **Go re-execution**: ~2 seconds (includes SQL parsing and execution)

### Scaling Considerations

For national-scale deployments (~60M shipments):
- Use **sharded warehouses** with parallel query execution
- Employ **DuckDB or Parquet** for columnar storage (100x faster than SQLite on analytical queries)
- Pre-materialize frequently-used aggregates as indexed views

## Future Architectural Extensions

Future development may pursue (i) graph database integration where current relational schema is augmented with graph queries for entity networks, ownership chains, and transshipment routes, (ii) streaming ingestion transitioning from batch-oriented model to streaming updates where new shipments are incrementally added and investigations run continuously, (iii) federated analysis enabling multi-agency scenarios through secure multi-party computation or differential privacy for statistical aggregation without raw data sharing, (iv) LLM-augmented investigation design where natural-language questions generate proposed investigation strategies, (v) formal verification extending Rust verifier to generate machine-checked proofs that investigations satisfy security properties (no SQL injection, deterministic results, bounded disclosure).

## Conclusion

omphalOS is designed for adversarial environments where analytical integrity is paramount. By distributing trust across multiple implementations, making epistemic humility architectural, and enabling offline operation, the system provides a foundation for intelligence analysis that is transparent, reproducible, and defensible.

The architecture prioritizes **legitimacy over optimization**. It is not the fastest system, nor the most automated. It is, however, auditable—and in domains where analysts' conclusions face legal challenges, congressional oversight, and public scrutiny, auditability is the highest-value property.

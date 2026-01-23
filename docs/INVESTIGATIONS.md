# SQL Investigation Catalog

## Overview

The omphalOS investigation catalog is a library of **parametric SQL queries** designed to surface patterns in trade data that merit analytical review. Investigations are **hypothesis-generating tools**, not classification algorithms. They narrow large datasets down to manageable subsets exhibiting specific patterns, which analysts then interpret using contextual intelligence.

Current catalog size: **20,000 investigations** across 7 domains.

## Design Philosophy

### Investigations Are Not Predictions

An investigation that flags an entity is not concluding that the entity is evading sanctions, proliferating WMD technology, or violating export controls. It is identifying a statistical pattern that, in combination with other intelligence, might warrant further review.

This distinction is critical for three reasons: (i) base rates—true violations are extremely rare (<0.01% of transactions) such that any automated classifier will produce overwhelming false positives, (ii) adversarial adaptation—once detection logic is known, sophisticated actors will evade it requiring continuous investigation evolution, (iii) legal defensibility—in adversarial proceedings (license appeals, enforcement litigation), investigators must explain their reasoning where "the algorithm flagged it" is insufficient while "this pattern is consistent with known evasion techniques, and we corroborated it with X, Y, Z" is defensible.

### Investigations Are Transparent

Every investigation is human-readable SQL with (i) Canon/Margin headers providing epistemic restraint reminders (see [CANON.md](CANON.md)), (ii) metadata comments specifying domain, intent, method, and notes, (iii) CTE-based structure using small, named subqueries for understandability, (iv) explicit LIMIT clauses preventing result sets from overwhelming analysts.

This transparency enables (i) code review where supervisors can audit analytical logic, (ii) courtroom testimony where analysts can explain exactly what the query does, (iii) community improvement where researchers can propose refinements.

### Investigations Are Versioned

The catalog is version-controlled (Git). Every investigation has a creation date and modification history. When a run references `cat_00001`, the run manifest records which commit SHA of the catalog was used.

This enables (i) reproducibility where years later, auditors can re-run investigations with the exact logic used originally, (ii) evolution allowing investigations to be updated as evasion techniques change without invalidating prior runs, (iii) rollback when an investigation produces excessive false positives.

## Investigation Patterns

The catalog currently implements several pattern families. Below are canonical examples of each.

### Pattern A: Payment Fragmentation

**Theory**: Evaders split large transactions into multiple smaller payments to avoid triggering financial reporting thresholds (e.g., BSA/FinCEN's $10K threshold for CTRs, OFAC's transaction monitoring).

**Method**: Join shipments to payments, count payments per shipment, score based on payment count.

**Example**: `cat_00001.sql`

```sql
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

Indicators include (i) payment_count >= 3 suggesting high fragmentation, (ii) mixed payment methods (wire + cashlike), (iii) multiple brokers for single shipment.

False positives arise from (i) letters of credit naturally involving multiple payments, (ii) milestone-based payment schedules for large capital equipment, (iii) currency control regimes forcing payment splitting (China, India).

**Canonical Domains**: All (pattern is domain-agnostic)

---

### Pattern B: Entity Clustering (Planned)

**Theory**: Shell company networks obscure beneficial ownership by using multiple nominally independent entities that share infrastructure (addresses, phone numbers, invoice sequences, payment brokers).

**Method**: Build entity-to-entity similarity graph based on shared attributes. Cluster using connected components or community detection. Flag entities in dense clusters.

Indicators include (i) shared physical addresses, (ii) shared bank accounts or payment brokers, (iii) sequential invoice numbers across nominally unrelated entities, (iv) rapid formation dates (all registered within weeks).

False positives arise from (i) co-location in industrial parks or free trade zones, (ii) use of common trade finance providers (e.g., all exporters in a sector use the same letter-of-credit bank), (iii) corporate groups with multiple subsidiaries (legitimate vertical integration).

**Canonical Domains**: All

**Implementation Status**: Prototype in development. Requires graph database or recursive CTE support.

---

### Pattern C: Temporal Anomalies (Planned)

**Theory**: Sanctions announcements or regulatory changes trigger "just-in-time" stockpiling or fire-sale liquidations. Sudden spikes in previously dormant commodity flows indicate evasion attempts.

**Method**: Compute entity-level or commodity-level baselines using rolling averages. Flag deviations >3 standard deviations from baseline.

Indicators include (i) entity dormant for 6+ months suddenly shipping high volumes, (ii) commodity flow to destination country spiking 10x before sanctions effective date, (iii) rapid alternation between high/low activity (potential smuggling cycles).

False positives arise from (i) seasonal commodity flows (agricultural products, heating equipment), (ii) project-based procurement (e.g., infrastructure buildout), (iii) market entry/exit (legitimate business expansion or contraction).

**Canonical Domains**: All, but especially `energy_equipment`, `aerospace_uas_avionics`, `chemicals_precursors`

**Implementation Status**: Prototype in development. Requires time-series analysis (window functions).

---

### Pattern D: Cross-Domain Linkage (Planned)

**Theory**: Proliferation procurement networks diversify across unrelated commodity sectors to obscure end-use. A single entity importing chemicals, machine tools, aerospace components, and laboratory equipment may be assembling a covert capability.

**Method**: For each entity, count distinct domains. Flag entities operating in ≥4 unrelated domains within a time window.

Indicators include (i) entity has shipments in chemicals + aerospace + medical equipment, (ii) no plausible vertical integration rationale (e.g., not a general trading company or government procurement agency), (iii) domains map to a threat scenario (WMD program, missile development).

False positives arise from (i) general trading companies (legitimate multi-sector operations), (ii) government procurement agencies (buy everything), (iii) university research labs (diverse equipment needs), (iv) industrial conglomerates (Samsung, Siemens buy across domains).

**Canonical Domains**: Cross-domain (requires joining multiple domain filters)

**Implementation Status**: Prototype complete. Requires ground-truth validation.

---

### Pattern E: Price Outliers (Planned)

**Theory**: Transfer pricing manipulation or barter arrangements use non-market prices to obscure value. Flagging transactions with prices far from commodity benchmarks may surface evasion.

**Method**: For each domain, compute median unit price (amount / qty). Flag transactions >2x or <0.5x median.

Indicators include (i) machine tool sold at 10x market price (possible IP bundling or sanctions premium), (ii) luxury goods sold at 10% of market price (possible kickbacks or barter), (iii) inconsistent pricing across similar transactions (same commodity, different prices).

False positives arise from (i) bulk discounts (large purchases at lower unit price), (ii) distressed sales (liquidations, defective goods), (iii) custom/bespoke equipment (one-off pricing), (iv) currency fluctuations (exchange rate changes between order and payment).

**Canonical Domains**: `luxury_dual_use_consumer`, `machine_tools`, `aerospace_uas_avionics`

**Implementation Status**: Prototype in development. Requires domain-specific price benchmarks.

---

### Pattern F: Network Topology (Future)

**Theory**: Transshipment routes and layered intermediaries obscure origin/destination. Analyzing entity networks for unusual topologies (long chains, hub-and-spoke, circular flows) may surface evasion.

**Method**: Build directed graph of entity-to-entity shipments. Compute graph metrics (betweenness centrality, clustering coefficient, shortest paths). Flag anomalous topologies.

Indicators include (i) 5+ hop chains (exporter → broker₁ → broker₂ → broker₃ → importer), (ii) circular flows (goods shipped A → B → A within short timeframe), (iii) high-betweenness entities (many unrelated flows pass through single broker).

False positives arise from (i) legitimate supply chains (raw materials → manufacturer → distributor → customer), (ii) trade hubs (Singapore, Dubai, Hong Kong naturally have high centrality), (iii) re-export business models (import for value-add processing, then re-export).

**Canonical Domains**: All

**Implementation Status**: Research phase. Requires graph database.

---

## Catalog Organization

### Directory Structure

```
sql/
├── investigations/
│   ├── catalog_generated/    # 20,000 auto-generated investigations
│   │   ├── cat_00001.sql
│   │   ├── cat_00002.sql
│   │   └── ...
│   ├── canonical/             # Hand-crafted high-value patterns (future)
│   └── custom/                # Analyst-contributed patterns (future)
├── templates/                 # Investigation generators
│   └── generate.py
└── CATALOG.json               # Catalog metadata
```

### Naming Convention

- `cat_XXXXX.sql`: Auto-generated investigations (5-digit zero-padded ID)
- `canonical_<pattern_name>.sql`: Hand-crafted canonical patterns (future)
- `custom_<analyst>_<date>_<description>.sql`: Analyst contributions (future)

### Metadata

Each investigation includes header comments:

```sql
-- Investigation: cat_00001
-- Domain: machine_tools
-- Intent: surface patterns that merit review using only observed commercial traces.
-- Method: compute joins across shipments, payments, services, intangibles, procurement, and research-link hints when available.
-- Notes: designed to be reviewable; each CTE is small and named.
```

## Using the Catalog

### Selecting Investigations for a Case

When defining a case, specify investigation IDs:

```json
{
  "case_id": "case_chemicals",
  "investigations": [
    "cat_00001",
    "cat_00023",
    "cat_00156"
  ]
}
```

How to choose? (i) Start broad by running 5-10 investigations across different pattern families, (ii) review results to identify which patterns produce actionable leads, (iii) iterate by adding complementary investigations to corroborate findings.

### Running Individual Investigations

You can execute investigations directly against a warehouse:

```bash
sqlite3 runs/my_case/<run_id>/warehouse.sqlite < sql/investigations/catalog_generated/cat_00001.sql > results.csv
```

This is useful for:
- Testing new investigations before adding to catalog
- Ad-hoc queries during case development
- Debugging unexpected results

### Contributing Investigations

If you develop a high-value investigation, contribute it by (i) placing SQL file in `sql/investigations/custom/`, (ii) following naming convention: `custom_<your_initials>_<date>_<description>.sql`, (iii) including Canon/Margin headers, (iv) adding metadata comments (domain, intent, method), (v) submitting pull request with investigation file, test case (synthetic data + expected results), and documentation of false positive scenarios. The maintainers will review and potentially promote to `canonical/` for wider use.

## Investigation Development Best Practices

Best practices for investigation development include the following. (i) Start with a hypothesis—articulate "I believe that [behavior] is a signal of [threat] because [theory]" rather than data-mining blindly. (ii) Test against ground truth when possible by validating against known cases (closed enforcement actions if unclassified, academic literature on evasion techniques, law enforcement case studies). (iii) Document false positive scenarios by listing legitimate behaviors that trigger the pattern, which guides analysts during result review, informs investigation refinement, and defends against allegations of fishing expeditions. (iv) Use CTEs for readability by breaking complex queries into small, named subqueries, making logic auditable by non-SQL-experts (supervisors, lawyers, congressional staff). (v) Limit result sets by always including `LIMIT 200` or similar to produce tractable result sets rather than raw dumps. (vi) Avoid premature optimization by using simpler queries unless complex SQL features (window functions, recursive CTEs, JSON functions) are necessary—simpler queries are easier to review, more portable across SQL dialects, and less likely to have subtle bugs. (vii) Version and track changes by committing every modification to version control with descriptive messages, creating an audit trail of analytical reasoning.

## Catalog Maintenance

### Deprecating Investigations

If an investigation produces excessive false positives or becomes obsolete (evasion technique no longer used), deprecate rather than delete by (i) moving to `sql/investigations/deprecated/`, (ii) adding deprecation comment specifying date, reason, and replacement, (iii) updating CATALOG.json to mark as deprecated. This preserves reproducibility—old runs that reference deprecated investigations can still be verified.

### Catalog Releases

The catalog is versioned as a pack (`sql.catalog.v1`, `sql.catalog.v2`, etc.). Major version bumps indicate:
- Breaking changes (schema modifications)
- Large-scale addition/removal of investigations
- Methodological shifts

Minor version bumps indicate:
- Incremental investigation additions
- Bug fixes
- Performance optimizations

### Performance Tuning

For large-scale deployments, investigations may require optimization through (i) indexing on frequently-filtered columns (domain, date ranges), (ii) materialized views pre-computing common aggregates (entity payment totals, domain distributions), (iii) parallel execution sharding warehouses and running investigations in parallel, (iv) columnar storage replacing SQLite with DuckDB or Parquet for analytical workloads.

## Frequently Asked Questions

### Why 20,000 investigations?

The large catalog size serves several purposes: (i) comprehensive coverage through multiple investigations per domain testing different hypotheses, (ii) redundancy such that when one investigation's logic is flawed, others may still surface the signal, (iii) adversarial resilience where a single investigation is easy to evade but 20,000 is infeasible, (iv) demonstration scale showing that the system can handle enterprise-scale catalogs. In practice, analysts select small subsets (5-10 investigations) per case. The full catalog is not executed together.

### How are investigations generated?

Currently, most are auto-generated from templates (see `core/src/omphalos/catalog/generate.py`). Future versions will include (i) hand-crafted canonical patterns, (ii) analyst-contributed custom investigations, (iii) LLM-proposed investigations (experimental).

### Can I write investigations in other languages?

The current implementation requires SQL (SQLite dialect). Future versions may support (i) other SQL dialects (PostgreSQL, DuckDB, SparkSQL), (ii) DSLs for investigation specification (then compiled to SQL), (iii) Python/R for statistical analyses (with SQL for data extraction).

### How do I know which investigations to use?

Start with canonical pattern families (fragmentation, clustering, temporal, cross-domain, price outliers). Run a small batch, review results, iterate.

Over time, you'll develop institutional knowledge: "For precursor cases, start with cat_00001, cat_00023, and cat_00156. For aerospace, use cat_01234 and cat_02345."

Document these heuristics in your organization's runbooks.

### What if my hypothesis isn't in the catalog?

Write a custom investigation! Place it in `sql/investigations/custom/`, test it, and if it's high-value, contribute it back to the catalog.

## Conclusion

The investigation catalog is the **intellectual core** of omphalOS. It encodes decades of analytical tradecraft in executable, auditable, versionable form. As evasion techniques evolve, the catalog evolves. As analysts develop new hypotheses, the catalog expands.

The catalog is not a black box—it is a transparent, community-maintained library of analytical patterns. Every investigation can be reviewed, challenged, refined, and replaced. This transparency is what makes omphalOS defensible in adversarial settings.

Investigations don't make decisions—analysts do. The catalog simply ensures that no plausible signal goes unexamined.

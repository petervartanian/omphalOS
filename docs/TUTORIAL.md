# omphalOS Tutorial: First Case Analysis

This tutorial walks through defining, running, verifying, and interpreting a case using omphalOS. By the end, you'll understand the complete analytical workflow from hypothesis to packet.

## Prerequisites

- Python 3.10+ installed
- omphalOS repository cloned
- 10 minutes of focused time

No external dependencies, no internet required, no complex setup.

## Step 1: Understanding the Scenario

You're an export control analyst investigating potential sanctions evasion in chemical precursor shipments. Your question: **"Are there unusual payment patterns in recent precursor exports?"**

This is a **hypothesis-generating question**. You're not trying to prove evasion occurred—you're surfacing patterns that merit closer review.

## Step 2: Verify System Installation

First, confirm that omphalOS is properly installed:

```bash
cd /path/to/omphalOS
PYTHONPATH=core/src python -m omphalos.cli pack verify packs/INDEX.json
```

Expected output:
```
OK
```

If you see `FAIL`, check that packs are present in the `packs/` directory. If packs are missing, you'll need to build or install them (see DEPLOYMENT.md).

## Step 3: Build a World

Cases run against **world-states**—synthetic datasets representing trade activity. Build a demonstration world:

```bash
PYTHONPATH=core/src python -m omphalos.cli world build --profile hydrate --out hydrate/world
```

This generates:
- `hydrate/world/meta.json` - World metadata (entity counts, domains, recipe)
- `hydrate/world/shards/entities_000.csv` - ~2,000 synthetic entities (firms, labs, brokers)
- `hydrate/world/shards/shipments_000.csv` - ~5,000 commodity shipments
- `hydrate/world/shards/payments_000.csv` - ~4,000 financial transactions

Expected output:
```
world built
```

### Inspect the World

Let's look at the metadata:

```bash
cat hydrate/world/meta.json
```

You'll see:
```json
{
  "profile": "hydrate",
  "created_utc": "2026-01-23T...",
  "domains": [
    "chemicals_precursors",
    "machine_tools",
    "aerospace_uas_avionics",
    ...
  ],
  "recipe": {
    "entities_base": 250000,
    "shipments_base": 600000,
    "multiplier_hint": 100,
    "shards": 64
  },
  "note": "Invented, internally consistent world. Non-identifiable."
}
```

The world is **deterministic**: running the same command again produces identical data (same entity IDs, same shipment values). This enables reproducible analysis.

## Step 4: Define a Case

Create a case file that articulates your investigative question:

```bash
cat > my_first_case.json <<'EOF'
{
  "case_id": "my_first_case",
  "question": "Are there unusual payment patterns in recent precursor exports?",
  "scope": {
    "time_window_days": 180
  },
  "investigations": [
    "cat_00001"
  ],
  "profiles": {
    "default": "hydrate"
  }
}
EOF
```

Breaking down the structure:

- **case_id**: Unique identifier for this case (used in filenames)
- **question**: Natural-language articulation of what you're investigating
- **scope**: Temporal and domain boundaries
- **investigations**: List of SQL investigation IDs to execute (from catalog)
- **profiles**: Which world-state to analyze ("hydrate" = demonstration world)

Investigation `cat_00001` is a payment fragmentation detector—it flags shipments with multiple split payments, which *could* indicate attempts to evade transaction reporting thresholds.

## Step 5: Run the Case

Execute the case against the world:

```bash
PYTHONPATH=core/src python -m omphalos.cli case run my_first_case.json --out runs
```

This:
1. Loads the world into a SQLite warehouse (`runs/my_first_case/<timestamp>/warehouse.sqlite`)
2. Executes investigation `cat_00001.sql` against the warehouse
3. Structures results into a packet (`packet.json`)
4. Generates a run manifest with checksums (`run.json`)

Expected output:
```
runs/my_first_case/20260123T143052Z
```

The timestamp `20260123T143052Z` is the **run ID**—a unique identifier for this specific execution.

## Step 6: Examine the Packet

The packet contains your analytical findings. Read it:

```bash
cat runs/my_first_case/20260123T143052Z/packet.json
```

You'll see a JSON structure with:

### Memo
Natural-language summary of the case:

```json
"memo": "Case my_first_case: Are there unusual payment patterns in recent precursor exports?\n\nObservations:\n- Loaded 5000 shipments and 4000 payments from hydrated world slice.\n- Most frequent domains: maritime_port_equipment(739), machine_tools(732), ..."
```

### Claims
Structured observations and unknowns:

```json
"claims": [
  {
    "type": "observation",
    "text": "Hydrated slice is internally consistent and cross-referenced by IDs."
  },
  {
    "type": "unknown",
    "text": "Full national-scale materialization is recipe-driven and performed offline at install-time."
  }
]
```

Notice the explicit **unknown** claim—the packet documents what it *doesn't* know, not just what it found. This is epistemic humility in practice.

### Annexes
Key-value aggregates providing context:

```json
"annexes": {
  "top_domains": [
    {"domain": "maritime_port_equipment", "count": 739},
    {"domain": "machine_tools", "count": 732},
    ...
  ],
  "payment_methods": [
    {"method": "wire", "count": 1361},
    {"method": "letter_of_credit", "count": 1333},
    {"method": "cashlike", "count": 1306}
  ]
}
```

These summaries help contextualize findings. If you flag 10 entities with unusual patterns, knowing the total population size matters.

### Tables
References to SQL views created during investigation:

```json
"tables": [
  {
    "name": "v_shipment_payments",
    "note": "Joined shipments and payments (view)"
  }
]
```

To actually query these, open the warehouse:

```bash
sqlite3 runs/my_first_case/20260123T143052Z/warehouse.sqlite
```

Then:
```sql
SELECT * FROM v_shipment_payments LIMIT 10;
```

## Step 7: Verify the Run

omphalOS includes built-in verification to detect tampering or corruption:

```bash
PYTHONPATH=core/src python -m omphalos.cli case verify runs/my_first_case/20260123T143052Z/
```

This recomputes checksums and confirms they match the manifest. Expected output:
```
OK
```

If you modify `packet.json` manually and re-run verification, you'll get:
```
FAIL
```

This checksumming makes runs **tamper-evident**. Anyone reviewing your work can confirm the artifacts haven't been altered since creation.

## Step 8: Apply Export Gate

Before sharing packets outside the secure environment, apply policy gates:

```bash
PYTHONPATH=core/src python -m omphalos.cli export runs/my_first_case/20260123T143052Z/packet.json
```

The gate scans for credentials, API keys, private keys, and other high-risk strings. For our synthetic world, output should be:
```
OK
```

If the gate detects problems, it reports:
```
DENY
blocked: password_assignment, aws_access_key_like
```

This prevents accidental leakage of secrets embedded in test data or analyst notes.

## Step 9: Interpret the Results

Now comes the **human judgment** part. The packet surfaced patterns—what do they mean?

### What the System Did

1. Loaded 5,000 shipments and 4,000 payments
2. Joined shipments to payments via `shipment_id`
3. Computed payment fragmentation scores (0 = single payment, 1 = two payments, 2 = three or more)
4. Sorted by fragmentation score and total amount
5. Returned top 200 results

### What the System Did NOT Do

- It did **not** conclude that any entity is evading sanctions
- It did **not** predict which shipments are suspicious
- It did **not** classify transactions as legitimate vs. illicit

The investigation is a **hypothesis-generating filter**: it narrows 5,000 shipments down to 200 that exhibit a specific pattern (split payments). The analyst must now review those 200 and determine which merit further investigation.

### Analytical Questions to Ask

For each flagged shipment:

1. **Is the payment fragmentation explained by legitimate trade finance?**
   - Letters of credit often involve multiple payments (deposit, balance on delivery)
   - Cross-border transactions may split due to currency controls
   - Large purchases might have milestone-based payment schedules

2. **Is the entity on a sanctions list?**
   - Check OFAC SDN list, Entity List, Denied Persons List
   - Look for name variants, aliases, addresses

3. **Is there other intelligence indicating evasion?**
   - Tip from law enforcement, financial intelligence unit, foreign partner
   - Prior violations, debarments, enforcement actions
   - Unusual corporate structure (shell companies, rapid ownership changes)

4. **Does the commodity have proliferation concern?**
   - Precursor chemicals for CW/BW programs
   - Dual-use equipment with nuclear, missile, or military applications

Only by combining pattern detection (what omphalOS does) with contextual intelligence (what analysts do) can you reach meaningful conclusions.

### The Canon's Role

Recall that `cat_00001.sql` includes 60 repetitions of:

```sql
-- Canon: interpret with restraint; prefer simpler explanations; record unknowns.
```

This is not boilerplate—it's a **cognitive forcing function**. When you review the 200 flagged shipments, the Canon reminds you:

- Don't assume malice where legitimate explanations exist
- Document what you don't know, not just what you found
- Statistical anomalies are not proof of wrongdoing

## Step 10: Iterate and Refine

Based on your review of the first run, you might:

### Add More Investigations

Edit `my_first_case.json` to include additional patterns:

```json
"investigations": [
  "cat_00001",  // Payment fragmentation
  "cat_00023",  // Entity clustering (shared addresses)
  "cat_00156"   // Cross-domain linkage (chemicals + aerospace)
]
```

Re-run the case—it will get a new run ID with a fresh timestamp.

### Narrow the Scope

If 200 results are too many, tighten the case:

```json
"scope": {
  "time_window_days": 90,
  "domains": ["chemicals_precursors"]
}
```

### Develop Custom Investigations

If existing catalog doesn't address your hypothesis, write custom SQL. Place it in `core/sql/investigations/custom/` and reference it in your case.

## Advanced: Comparing Runs

Over time, you'll run the same case multiple times (as new data arrives, as investigations improve). Compare runs:

```bash
# Run 1 (January)
diff runs/my_first_case/20260115T100000Z/packet.json \
     runs/my_first_case/20260123T143052Z/packet.json
```

Look for:
- Entities that appear in both runs (persistent patterns)
- Entities that disappear (false positives?)
- New entities that emerge (recent evasion attempts?)

Temporal comparison is where batch-oriented analytical systems excel. You're not monitoring in real-time—you're identifying **durable patterns** that survive across multiple snapshots.

## Troubleshooting

### "No such table: shipments"

The world hasn't been loaded. Ensure `hydrate/world/shards/shipments_000.csv` exists and re-run the case.

### "Investigation cat_XXXXX not found"

The catalog pack isn't installed. Run `omphalos.cli pack verify` to check pack availability.

### Verification fails after manual editing

This is expected! Checksums prevent undetected modification. If you need to edit a packet, note that it's no longer verifiable against the original run. Consider re-running the case instead.

### World has no data in my domain of interest

The demo world is small and randomly generated. For domain-specific analysis, you need to:
1. Install a production pack (`world.national.v1`)
2. Import real data (see DEPLOYMENT.md)

## What You've Learned

- **Cases** articulate investigative questions and select relevant investigations
- **Runs** materialize cases against world-states, producing checksummed artifacts
- **Packets** structure findings with memos, claims, annexes, and table references
- **Verification** confirms integrity using checksums
- **Export gates** prevent accidental disclosure of credentials
- **Interpretation** is human judgment, not automated classification

omphalOS doesn't give you answers—it surfaces patterns and documents uncertainty. Your expertise, combined with the system's analytical scaffolding, produces defensible intelligence.

## Next Steps

- Read [INVESTIGATIONS.md](INVESTIGATIONS.md) to understand the investigation catalog
- Read [CANON.md](CANON.md) to understand the epistemic design philosophy
- Read [ARCHITECTURE.md](ARCHITECTURE.md) for system internals
- Read [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment guidance

Welcome to polycentric, epistemically humble intelligence analysis.

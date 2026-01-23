# omphalOS Deployment Guide

## Overview

This guide covers deploying omphalOS in production environments, from standalone analyst workstations to classified multi-user clusters. omphalOS is designed for offline, air-gapped operation and can be deployed without internet connectivity.

## Deployment Architectures

### Architecture 1: Standalone Workstation

**Use Case**: Individual analyst conducting preliminary research

**Requirements**:
- Python 3.10+
- 50GB disk space (for national-scale world)
- 8GB RAM minimum, 16GB recommended
- Linux, macOS, or Windows

**Installation**:

```bash
# 1. Clone repository (via USB if air-gapped)
git clone /path/to/omphalos-bundle
cd omphalos

# 2. Verify pack integrity
PYTHONPATH=core/src python -m omphalos.cli pack verify packs/INDEX.json

# 3. Install packs
PYTHONPATH=core/src python -m omphalos.cli pack install packs/INDEX.json

# 4. Build world (or install from pack)
PYTHONPATH=core/src python -m omphalos.cli world build --profile national --out hydrate/world

# 5. Run test case
PYTHONPATH=core/src python -m omphalos.cli case run hydrate/cases/case_chemicals.json
```

**Security Considerations**:
- Apply full-disk encryption
- Use locked screensaver (15-minute timeout)
- Disable network interfaces if classified data present
- Enable audit logging (`auditd` on Linux)

---

### Architecture 2: Shared Server

**Use Case**: Small team (5-20 analysts) with centralized infrastructure

**Requirements**:
- Linux server (Ubuntu 22.04 LTS or RHEL 8+)
- 200GB disk space
- 32GB RAM
- Multi-user file system with ACLs

**Installation**:

```bash
# 1. Create service account
sudo useradd -r -s /bin/bash -d /opt/omphalos omphalos

# 2. Install omphalOS
sudo git clone /path/to/omphalos-bundle /opt/omphalos
sudo chown -R omphalos:omphalos /opt/omphalos

# 3. Create shared workspace
sudo mkdir -p /data/omphalos/{cases,runs,worlds}
sudo chown -R omphalos:analysts /data/omphalos
sudo chmod 2775 /data/omphalos/*  # Setgid for shared ownership

# 4. Install system service
sudo tee /etc/systemd/system/omphalos-verify.service <<EOF
[Unit]
Description=omphalOS Verification Service
After=network.target

[Service]
Type=simple
User=omphalos
WorkingDirectory=/opt/omphalos
ExecStart=/usr/bin/python3 -m omphalos.cli case verify /data/omphalos/runs/*
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable omphalos-verify.service
```

**Multi-User Access**:

Analysts submit cases via CLI:

```bash
python -m omphalos.cli case run /data/omphalos/cases/my_case.json --out /data/omphalos/runs
```

Results are written to shared `/data/omphalos/runs` with group-writable permissions. Verification runs as cron job or systemd timer.

**Security Considerations**:
- Use LDAP/Active Directory for user authentication
- Configure sudo policies (analysts can run cases, only admins can install packs)
- Enable SELinux/AppArmor with omphalOS confined to `/opt/omphalos` and `/data/omphalos`
- Mount `/data/omphalos` with `noexec` to prevent code execution from data partition

---

### Architecture 3: Air-Gapped Classified Cluster

**Use Case**: National-level export control, classified data analysis

**Requirements**:
- Multiple servers in SCIF (Sensitive Compartmented Information Facility)
- 10TB+ shared storage (NFS, Lustre, or object store)
- 100GB+ RAM per node
- One-way data diodes for packet export

**Installation**:

```bash
# On bastion host (for pack preparation)
# 1. Build packs from source
cd omphalos
./scripts/build-packs.sh --profile production --scale 100x

# 2. Sign packs
gpg --detach-sign --armor -o packs/world.national.v1.sig packs/world.national.v1.tar.gz

# 3. Transfer via data diode (unidirectional network)
rsync -av packs/ /mnt/diode-outbound/

# On classified compute cluster
# 4. Verify transferred packs
gpg --verify /mnt/diode-inbound/packs/world.national.v1.sig
python -m omphalos.cli pack verify /mnt/diode-inbound/packs/INDEX.json

# 5. Install to shared storage
python -m omphalos.cli pack install /mnt/diode-inbound/packs/INDEX.json --dest /shared/omphalos/packs

# 6. Materialize world from real data (classified process—not in public repo)
python -m omphalos_ingest.classified import-ace /classified/ace-extracts --out /shared/omphalos/worlds/classified_20260123

# 7. Configure job scheduler (SLURM example)
sbatch scripts/run-case-batch.slurm /shared/omphalos/cases/*.json
```

**Sharded Execution**:

For national-scale data (60M+ shipments), shard warehouses:

```python
# In case definition
{
  "case_id": "national_chemicals",
  "scope": {
    "shards": [0, 1, 2, ..., 63]  # Run on 64 shards in parallel
  }
}
```

Each shard runs independently on separate compute nodes. Results are aggregated in a final reduction step.

**Security Considerations**:
- Deploy within SCIF (physical security, TEMPEST, etc.)
- All storage encrypted at rest (LUKS, hardware encryption)
- Enable mandatory access control (SELinux MLS policy)
- Implement two-person rule for pack installation (requires two authorized signatures)
- Export packets via one-way data diode (physically unidirectional network)
- Redact packet memos before export (automated sanitization or manual review)

---

## Pack Management

### Building Packs from Source

```bash
cd omphalos

# Build world pack
python scripts/build-pack.py world --profile national --out packs/world.national.v2.tar.gz

# Build investigation catalog
python scripts/build-pack.py sql-catalog --count 20000 --out packs/sql.catalog.v2.tar.gz

# Build verifiers (requires Rust + Go toolchains)
./scripts/build-verifiers.sh --platforms linux-x86_64,macos-arm64,windows-x86_64
```

### Signing Packs

```bash
# Generate signing key (one-time)
gpg --full-generate-key  # Use RSA 4096, no expiration

# Sign pack
gpg --detach-sign --armor -o packs/world.national.v2.sig packs/world.national.v2.tar.gz

# Verify signature
gpg --verify packs/world.national.v2.sig packs/world.national.v2.tar.gz
```

### Pack Versioning

Pack versions follow semantic versioning:

- **Major version** (v1 → v2): Breaking schema changes, incompatible with old runs
- **Minor version** (v2.0 → v2.1): Backward-compatible additions (new investigations, domains)
- **Patch version** (v2.1.0 → v2.1.1): Bug fixes, no functional changes

**Compatibility**: Runs specify pack versions in manifests. Old runs remain verifiable even after pack upgrades.

---

## Performance Tuning

### SQLite Optimization

For single-node deployments:

```python
# In core/src/omphalos/warehouse.py
def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")  # Write-ahead logging
    conn.execute("PRAGMA synchronous=NORMAL")  # Faster commits
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    conn.execute("PRAGMA temp_store=MEMORY")  # Temp tables in RAM
    return conn
```

### DuckDB Migration

For analytical workloads >10M rows:

```bash
pip install duckdb --break-system-packages

# Convert SQLite warehouse to DuckDB
python scripts/convert-warehouse.py runs/my_case/<run_id>/warehouse.sqlite --format duckdb
```

DuckDB provides 10-100x faster analytical queries on large datasets.

### Parallel Execution

For multi-investigation cases:

```python
# In case definition
{
  "case_id": "batch_analysis",
  "investigations": ["cat_00001", "cat_00002", ..., "cat_00100"],
  "execution": {
    "parallel": true,
    "max_workers": 16
  }
}
```

Investigations run concurrently, limited by `max_workers`.

---

## Monitoring and Maintenance

### Health Checks

```bash
# Verify pack integrity
python -m omphalos.cli pack verify packs/INDEX.json

# Verify recent runs
find /data/omphalos/runs -name run.json -mtime -7 | while read manifest; do
  python -m omphalos.cli case verify $(dirname $manifest)
done

# Check disk space
df -h /data/omphalos
```

### Audit Logging

Enable structured logging:

```python
# In core/src/omphalos/cli.py
import logging
logging.basicConfig(
    filename='/var/log/omphalos/audit.log',
    format='%(asctime)s %(user)s %(action)s %(case_id)s %(run_id)s',
    level=logging.INFO
)
```

Log all operations (case runs, verifications, exports) with operator ID and timestamp.

### Backup Strategy

**Critical artifacts**:
- Investigation catalog (`sql/investigations/`)
- Cases (`/data/omphalos/cases/`)
- Run manifests (`runs/**/run.json`, `runs/**/packet.json`)

**Backup schedule**:
- Hourly: Incremental backup of run manifests
- Daily: Full backup of cases and investigation catalog
- Weekly: Snapshot of worlds (if worlds are static; skip if regenerated on demand)

**Do NOT backup**:
- Warehouses (`warehouse.sqlite`) — large, regenerable from world + case
- Temporary artifacts

---

## Troubleshooting

### Issue: Pack verification fails

**Symptom**: `omphalos.cli pack verify` returns FAIL

**Causes**:
1. Pack corrupted during transfer (USB copy interrupted)
2. Pack signature invalid (wrong GPG key)
3. Pack modified after signing

**Resolution**:
```bash
# Check GPG signature
gpg --verify packs/world.national.v1.sig

# Recompute checksums
sha256sum packs/world.national.v1.tar.gz

# Compare to INDEX.json expected checksum
jq '.packs[] | select(.name=="world.national.v1") | .checksum' packs/INDEX.json
```

If checksums don't match, re-transfer pack.

---

### Issue: Investigation query times out

**Symptom**: Case run hangs, SQL query never completes

**Causes**:
1. Missing indexes on large tables
2. Cartesian product (forgot JOIN condition)
3. Warehouse too large for SQLite (>100M rows)

**Resolution**:
```sql
-- Identify slow queries
.timer on
.eqp on
SELECT ...  -- Run investigation SQL

-- Add indexes
CREATE INDEX idx_shipments_domain ON shipments(domain);
CREATE INDEX idx_payments_shipment ON payments(shipment_id);
```

For very large warehouses, migrate to DuckDB or PostgreSQL.

---

### Issue: Verification succeeds locally but fails on another system

**Symptom**: Run verifies OK on analyst's workstation but FAIL on supervisor's system

**Causes**:
1. Different omphalOS version (non-deterministic SQL execution)
2. Floating-point precision differences (x86 vs ARM)
3. Filesystem timestamp resolution issues

**Resolution**:
- Ensure all systems use same omphalOS commit SHA
- Use approximate equality for floating-point comparisons in verifiers
- Verify that run manifest was copied correctly (checksum manifest itself)

---

## Security Hardening

### Minimal Installation

Remove unnecessary components in production:

```bash
# Install only runtime, no development tools
rm -rf docs/ tests/ scripts/ .github/

# Remove unused verifiers
rm -rf core/agents/rust/ core/agents/go/  # If only using Python verification
```

### Filesystem Permissions

```bash
# Code is read-only
chmod -R a-w /opt/omphalos/core/

# Only omphalos service account can write to data
chown -R omphalos:omphalos /data/omphalos
chmod 700 /data/omphalos/runs  # Other users cannot read runs
```

### Network Isolation

```bash
# Disable network for omphalos processes (Linux)
sudo -u omphalos unshare --net python -m omphalos.cli case run ...

# Or use systemd service with PrivateNetwork=yes
[Service]
PrivateNetwork=yes
```

---

## Compliance and Certification

### FIPS 140-2

For government deployments requiring FIPS-compliant cryptography:

```python
# Use hashlib in FIPS mode
import hashlib
assert hashlib.md5 == hashlib.algorithms_available  # Verify FIPS mode
```

Requires Python compiled with `--with-openssl-fips`.

### Common Criteria

omphalOS has not undergone CC evaluation. For CC-certified deployments:
- Run omphalOS on CC-certified OS (e.g., RHEL 8 CC-certified)
- Use CC-certified Python interpreter
- Document omphalOS security functions in Security Target

### STIG Compliance

For DISA STIG compliance:
- Apply OS-level STIGs (e.g., RHEL 8 STIG)
- Configure audit logging per STIG requirements
- Implement two-factor authentication for system access
- Enable SELinux in enforcing mode

---

## Scaling to National Level

Scaling from demo (5K shipments) to national (60M+ shipments):

**Infrastructure**:
- 10+ compute nodes (64 cores, 256GB RAM each)
- 50TB shared storage (NFS or object store)
- Job scheduler (SLURM, Kubernetes)

**Data Sharding**:
```python
# Shard world by entity_id hash
num_shards = 64
for i in range(num_shards):
    entities_shard = entities[entities['entity_id'].apply(hash) % num_shards == i]
    entities_shard.to_csv(f'world/shards/entities_{i:03d}.csv')
```

**Parallel Execution**:
```bash
# SLURM job array
sbatch --array=0-63 scripts/run-shard.slurm case_chemicals
```

Each shard runs on a separate node. Results are merged in a reduction phase.

**Query Optimization**:
- Replace SQLite with PostgreSQL or DuckDB
- Pre-materialize aggregates as indexed views
- Use columnar storage (Parquet) for read-heavy workloads

---

## Roadmap

### Near-Term (Next 6 Months)
- Web UI for case management
- Real-time verification service
- Integration with commercial trade databases

### Medium-Term (6-12 Months)
- Graph database for entity network analysis
- Federated learning across classification boundaries
- LLM-assisted investigation design

### Long-Term (12+ Months)
- Formal verification of investigation correctness
- Differential privacy for packet export
- Integration with secure enclaves (SGX, TrustZone)

---

## Support

For deployment assistance:
- **Documentation**: See other files in `docs/`
- **Issues**: GitHub Issues (for public repo questions)
- **Security**: See SECURITY.md for vulnerability reporting

---

## Appendix: Environment Variables

```bash
# Override default paths
export OMPHALOS_PACK_DIR=/custom/path/to/packs
export OMPHALOS_DATA_DIR=/custom/path/to/data

# Enable debug logging
export OMPHALOS_LOG_LEVEL=DEBUG

# Set verification concurrency
export OMPHALOS_VERIFY_WORKERS=8
```

## Appendix: Systemd Service Example

```ini
[Unit]
Description=omphalOS Case Runner
After=network.target

[Service]
Type=oneshot
User=omphalos
Group=omphalos
WorkingDirectory=/opt/omphalos
ExecStart=/usr/bin/python3 -m omphalos.cli case run %i --out /data/omphalos/runs
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Usage:
```bash
sudo systemctl start omphalos-case@case_chemicals.service
```

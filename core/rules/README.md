# omphalOS Rules Engine

Machine-readable export control and sanctions regime scaffolds.

## Structure

```
rules/
├── ear/           # Export Administration Regulations (EAR) control lists
├── sanctions/     # OFAC and multilateral sanctions programs
└── tests/         # Test cases for rule application
```

## Purpose

The rules engine enables investigations to be **regime-aware**: flagging shipments that match control lists, citing applicable ECCNs, and identifying sanctioned entities.

## Implementation Status

**Current**: Foundation created, awaiting regime data population

**Planned**:
- EAR control list (ECCN codes, HS code mappings, de minimis rules)
- OFAC sanctions (SDN list, sectoral sanctions, geographic embargoes)
- Test suite validating rule application

## Usage Example (Future)

```python
from omphalos.rules import check_ear_control

# Check if commodity requires export license
result = check_ear_control(
    hs_code="8479.89",
    destination="CN",
    end_use="military"
)
# Returns: {"license_required": True, "eccn": "3B001", "reason": "catch-all §744.17"}
```

## Data Sources

Rules will be derived from:
- Commerce Control List (CCL) - publicly available
- OFAC SDN list - publicly available, updated weekly
- Multilateral regime lists (Wassenaar, AG, MTCR) - publicly available

All regime data is **unclassified and publicly releasable**.

## Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for how to propose rule additions or corrections.

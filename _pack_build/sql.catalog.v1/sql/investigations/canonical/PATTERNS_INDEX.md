# Canonical Investigation Pattern Index

This directory contains hand-crafted canonical investigation patterns representing the core analytical techniques for export control and sanctions enforcement.

## Pattern Families

### Family A: Payment Fragmentation (5 patterns)
Detecting split payments that may indicate reporting threshold evasion.

- **pattern_a01_payment_fragmentation_basic**: Basic fragmentation detection (≥3 payments)
- **pattern_a02_payment_method_mixing**: Multiple payment methods per shipment
- **pattern_a03_cashlike_fragmentation**: Multiple cashlike payments (higher risk)
- **pattern_a04_just_under_threshold**: Payments just under $10K BSA threshold
- **pattern_a05_round_number_splitting**: Identical round-number payment amounts

### Family B: Entity Clustering (1 pattern)
Identifying shell company networks through shared infrastructure.

- **pattern_b01_shared_addresses**: Entities sharing physical addresses

### Family C: Temporal Anomalies (1 pattern)
Detecting unusual timing patterns in shipment flows.

- **pattern_c01_sudden_volume_spike**: Entities with sudden shipment volume increases

### Family D: Cross-Domain Linkage (1 pattern)
Flagging entities operating across unrelated commodity sectors.

- **pattern_d01_multi_domain_exporter**: Entities in ≥4 distinct domains

### Family E: Price Outliers (1 pattern)
Identifying non-market pricing suggesting transfer pricing or barter.

- **pattern_e01_extreme_unit_prices**: Unit prices >5x or <0.2x domain median

### Family F: Network Topology (1 pattern)
Analyzing entity networks for unusual structural properties.

- **pattern_f01_broker_centrality**: Payment brokers with high betweenness centrality

### Family G: Entity Linkage (1 pattern)
Detecting hidden relationships between nominally independent entities.

- **pattern_g01_invoice_sequence_sharing**: Entities with overlapping invoice ranges

### Family H: Temporal Patterns (1 pattern)
Unusual timing behaviors beyond volume spikes.

- **pattern_h01_weekend_shipments**: Shipments occurring on weekends/holidays

## Total Canonical Patterns: 12

**Note**: The catalog also contains 20,000 auto-generated pattern variants in `catalog_generated/`.
Canonical patterns represent the core methodological contributions and serve as templates for variants.

## Usage

Reference canonical patterns in case definitions:

```json
{
  "case_id": "my_case",
  "investigations": [
    "pattern_a01_payment_fragmentation_basic",
    "pattern_b01_shared_addresses",
    "pattern_d01_multi_domain_exporter"
  ]
}
```

## Contributing New Patterns

See [CONTRIBUTING.md](../../../../../../CONTRIBUTING.md) for how to propose new canonical patterns.

Requirements:
- Novel analytical technique not covered by existing patterns
- Documented false positive scenarios
- Test case with synthetic data
- Canon/Margin headers included
- CTE-based SQL for readability

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, List, Sequence


@dataclass
class DemoTradeFeedConnector:
    """Deterministic synthetic "trade feed".

    This connector is intentionally parameterizable by an exporter pool so the
    reference pipeline can guarantee a high (but not perfect) match rate against
    the synthetic registry.
    """

    records: int
    exporter_pool: Sequence[str] | None = None
    ambiguous_exporters: Sequence[str] | None = None
    ambiguous_fraction: float = 0.05
    name: str = "trade_feed"

    def read(self, *, seed: int) -> List[dict[str, Any]]:
        rng = random.Random(seed)

        # If no pool is provided, fall back to a small fixed set.
        exporters = list(self.exporter_pool) if self.exporter_pool else [
            "ASTER BOREAL",
            "COBALT DORIAN",
            "ECHELON FATHOM",
            "GOSSAMER HALCYON",
            "IRIS JUNIPER",
        ]
        exporters = [" ".join(e.split()).upper() for e in exporters]
        exporters.sort()

        ambiguous = list(self.ambiguous_exporters) if self.ambiguous_exporters else []
        ambiguous = [" ".join(a.split()).upper() for a in ambiguous]
        ambiguous = sorted(set(ambiguous))

        # Ensure ambiguous exporters are only emitted through the dedicated
        # ambiguous slice (so review_fraction remains bounded and stable).
        non_ambiguous_exporters = [e for e in exporters if e not in ambiguous]
        if non_ambiguous_exporters:
            exporters = non_ambiguous_exporters

        importers = ["North", "South", "East", "West", "Harbor", "Ridge"]
        countries = ["US", "CA", "MX", "BR", "GB", "DE", "FR", "NL", "PL", "TR", "IN", "JP", "KR", "VN", "SG"]
        hs_codes = ["8504", "8542", "8471", "8703", "3004", "9013", "7601", "7403"]
        base = date(2024, 1, 1)

        suffixes = ["", " LLC", " INC", " CO", " LTD", " GROUP"]

        def vary_name(name: str) -> str:
            # Token-preserving variations (case handled later by canonicalization).
            out = name
            if rng.random() < 0.35:
                out = out.replace(" ", "-")
            if rng.random() < 0.25:
                out = out.replace("-", " ")
            if rng.random() < 0.25:
                out = out + rng.choice(suffixes)
            if rng.random() < 0.10:
                out = out.replace(" ", "  ")  # whitespace noise
            if rng.random() < 0.15:
                out = out + "."  # punctuation noise
            return out

        rows: List[dict[str, Any]] = []

        # Choose exactly k rows that will be ambiguous, to keep review_fraction
        # stable even for small record counts.
        ambiguous_idx = set()
        if ambiguous:
            k = int(round(float(self.ambiguous_fraction) * float(self.records)))
            k = max(0, min(self.records, k))
            if k:
                ambiguous_idx = set(rng.sample(range(self.records), k))

        for i in range(self.records):
            sid = f"S{i+1:06d}"

            # A small controlled slice of ambiguous exporter names exercises the review queue.
            use_ambiguous = bool(ambiguous) and (i in ambiguous_idx)
            if use_ambiguous:
                exporter = rng.choice(ambiguous)
            else:
                exporter = rng.choice(exporters)

            importer = rng.choice(importers) + " " + rng.choice(importers)
            country = rng.choice(countries)
            hs = rng.choice(hs_codes)
            value = round(rng.random() * 100000 + 500, 2)
            d = base + timedelta(days=int(rng.random() * 365))

            rows.append(
                {
                    "shipment_id": sid,
                    "exporter_name": vary_name(exporter),
                    "importer_name": importer,
                    "country": country,
                    "hs_code": hs,
                    "value_usd": float(value),
                    "ship_date": d.isoformat(),
                }
            )

        rows.sort(key=lambda r: r["shipment_id"])
        return rows

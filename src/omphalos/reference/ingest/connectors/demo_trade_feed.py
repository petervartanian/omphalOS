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

        non_ambiguous_exporters = [e for e in exporters if e not in ambiguous]
        if non_ambiguous_exporters:
            exporters = non_ambiguous_exporters

        stems = [
            "Aster",
            "Boreal",
            "Cobalt",
            "Dorian",
            "Echelon",
            "Fathom",
            "Gossamer",
            "Halcyon",
            "Iris",
            "Juniper",
            "Kestrel",
            "Lattice",
            "Mosaic",
            "Nimbus",
            "Orchid",
            "Pioneer",
        ]
        countries = ["US", "CA", "MX", "BR", "GB", "DE", "FR", "NL", "PL", "TR", "IN", "JP", "KR", "VN", "SG"]
        domains = [
            "chem_precursors",
            "machine_tools",
            "aerospace_uas_avionics",
            "maritime_shipbuilding_ports",
            "energy_equipment",
            "medical_bio_lab",
            "luxury_dual_use_consumer",
        ]
        hs_by_domain = {
            "chem_precursors": ["2933", "2905", "2918", "3811"],
            "machine_tools": ["8456", "8466", "8462"],
            "aerospace_uas_avionics": ["8807", "8526", "9031"],
            "maritime_shipbuilding_ports": ["8907", "8419", "8431"],
            "energy_equipment": ["8502", "8501", "8411"],
            "medical_bio_lab": ["9018", "9027", "3002"],
            "luxury_dual_use_consumer": ["9101", "4202", "7113"],
        }
        base = date(2024, 1, 1)

        suffixes = ["", " LLC", " INC", " CO", " LTD", " GROUP"]

        def vary_name(name: str) -> str:
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

        ambiguous_idx = set()
        if ambiguous:
            k = int(round(float(self.ambiguous_fraction) * float(self.records)))
            k = max(0, min(self.records, k))
            if k:
                ambiguous_idx = set(rng.sample(range(self.records), k))

        for i in range(self.records):
            sid = f"S{i+1:06d}"

            use_ambiguous = bool(ambiguous) and (i in ambiguous_idx)
            if use_ambiguous:
                exporter = rng.choice(ambiguous)
            else:
                exporter = rng.choice(exporters)

            importer = f"{rng.choice(stems)} {rng.choice(['TRADING','SUPPLY','IMPORTS','DISTRIBUTION','PROJECTS'])}"
            country = rng.choice(countries)
            domain = rng.choice(domains)
            hs = rng.choice(hs_by_domain[domain])
            description = f"INVENTED {domain.replace('_',' ').upper()} ITEM"
            value = round(rng.random() * 100000 + 500, 2)
            d = base + timedelta(days=int(rng.random() * 365))

            incoterm = rng.choice(["EXW", "FOB", "CIF", "DAP", "DDP"])
            transport_mode = rng.choice(["SEA", "AIR", "ROAD", "RAIL"])

            rows.append(
                {
                    "shipment_id": sid,
                    "exporter_name": vary_name(exporter),
                    "importer_name": importer,
                    "exporter_country": country,
                    "importer_country": rng.choice(countries),
                    "country": country,
                    "domain": domain,
                    "hs_code": hs,
                    "description": description,
                    "incoterm": incoterm,
                    "transport_mode": transport_mode,
                    "value_usd": float(value),
                    "ship_date": d.isoformat(),
                }
            )

        rows.sort(key=lambda r: r["shipment_id"])
        return rows

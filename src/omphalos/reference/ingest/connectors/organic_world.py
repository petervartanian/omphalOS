from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class OrganicWorld:
    """Deterministic fictional world generator.

    The output is invented yet operationally shaped:
    - corporate names are plausible but non-identifying
    - documents are incomplete in realistic ways
    - entity naming drifts (aliases, truncation, transliteration noise)

    This is designed to exercise analysis and review flows without encoding
    any real counterparties.
    """

    registry_entities: int
    trade_records: int

    def build(self, *, seed: int) -> Dict[str, List[Dict[str, Any]]]:
        rng = random.Random(seed)

        # A deliberately broad domain set aligned with the AOTA list.
        domains = [
            "chem_precursors",
            "machine_tools",
            "aerospace_uas_avionics",
            "maritime_shipbuilding_ports",
            "energy_equipment",
            "medical_bio_lab",
            "luxury_dual_use_consumer",
            "services",
            "intangibles",
            "finance_signals",
            "procurement",
            "research_links",
        ]

        countries = ["US", "CA", "MX", "BR", "GB", "DE", "FR", "NL", "PL", "TR", "IN", "JP", "KR", "VN", "SG"]

        # Invented ports (do not correspond to real places).
        ports = [
            "PORT ASTER",
            "PORT CORMORANT",
            "PORT HALCYON",
            "PORT IRONLEAF",
            "PORT JUNIPER",
            "PORT KESTREL",
            "PORT LANTERN",
            "PORT MARINER",
            "PORT NEBULA",
            "PORT ORCHID",
        ]

        # Invented carrier and financial institutions.
        carriers = ["NORTHWIND LINES", "BLUE QUAY SHIPPING", "HELIOS MARITIME", "GULLSTREAM CARRIERS"]
        banks = ["STONEBRIDGE BANK", "HARBORLIGHT TRUST", "SABLE CLEARING", "RIVERMARK FINANCE"]
        insurers = ["CIRRUS INSURANCE", "ANCHOR MUTUAL", "EMBER UNDERWRITERS"]

        incoterms = ["EXW", "FCA", "FOB", "CFR", "CIF", "DAP"]
        transport_modes = ["AIR", "SEA", "ROAD", "RAIL"]
        payment_methods = ["WIRE", "LC", "CARD", "NETTING"]

        # HS6-like codes used as compact domain signals.
        hs_by_domain = {
            "chem_precursors": ["293339", "290410", "291249", "292151"],
            "machine_tools": ["845811", "846693", "847989", "846090"],
            "aerospace_uas_avionics": ["880240", "880730", "852610", "901420"],
            "maritime_shipbuilding_ports": ["890120", "842641", "842620", "731449"],
            "energy_equipment": ["841011", "841199", "850231", "850164"],
            "medical_bio_lab": ["901890", "902780", "300212", "382219"],
            "luxury_dual_use_consumer": ["910211", "711319", "870324", "420221"],
            "services": ["999700", "999710", "999720", "999730"],
            "intangibles": ["998100", "998110", "998120", "998130"],
            "finance_signals": ["997000", "997010", "997020", "997030"],
            "procurement": ["996000", "996010", "996020", "996030"],
            "research_links": ["995000", "995010", "995020", "995030"],
        }

        def _choice(xs: List[str]) -> str:
            return xs[int(rng.random() * len(xs))]

        # --- registry ---
        stems = [
            "AURELINE",
            "BASALT",
            "CANTICLE",
            "DORIAN",
            "EQUINOX",
            "FATHOM",
            "GOSSAMER",
            "HALCYON",
            "IRONLEAF",
            "JUNIPER",
            "KESTREL",
            "LANTERN",
            "MARINER",
            "NEBULA",
            "ORCHID",
            "PENDULUM",
            "QUARRY",
            "RIDGELINE",
            "SABLE",
            "TIDEMARK",
        ]
        descriptors = [
            "LABORATORIES",
            "INSTRUMENTS",
            "INDUSTRIES",
            "SYSTEMS",
            "WORKS",
            "ENGINEERING",
            "MANUFACTURING",
            "LOGISTICS",
            "AEROSPACE",
            "MARITIME",
            "ENERGY",
            "BIOSCIENCE",
            "CHEMICALS",
            "PRECISION",
            "HOLDINGS",
        ]
        legal = ["INC", "LTD", "GMBH", "S.A.", "BV", "KK", "PTE", "LLC"]

        # Create clusters that intentionally share prefixes to generate ambiguity.
        cluster_roots = rng.sample(stems, k=max(4, min(8, len(stems))))
        clusters: List[Tuple[str, List[str]]] = []
        for root in cluster_roots:
            # Each cluster shares the same first two tokens.
            base = f"{root} {_choice(descriptors)}"
            variants = [
                f"{base} LABORATORIES",
                f"{base} SYSTEMS",
                f"{base} WORKS",
            ]
            clusters.append((base, variants))

        registry: List[Dict[str, Any]] = []
        for i in range(self.registry_entities):
            eid = f"E{i+1:04d}"
            country = _choice(countries)

            if rng.random() < 0.45:
                base, variants = _choice(clusters)
                name = _choice(variants)
            else:
                name = f"{_choice(stems)} {_choice(descriptors)}"
                if rng.random() < 0.55:
                    name = f"{name} {_choice(descriptors)}"

            if rng.random() < 0.60:
                name = f"{name} {_choice(legal)}"

            registry.append({"entity_id": eid, "entity_name": name, "country": country})

        registry.sort(key=lambda r: r["entity_id"])

        # --- trade feed ---
        base_date = date(2024, 1, 1)

        def _noisy_exporter_name(canonical: str) -> str:
            """Produce realistic naming drift.

            The resolver is token-based; the goal is to create a controlled mix
            of clean matches and review-worthy ambiguity.
            """

            toks = canonical.split()
            # Rare truncation to induce review cases in clustered names.
            if len(toks) >= 3 and rng.random() < 0.06:
                toks = toks[:2]

            out = " ".join(toks)

            if rng.random() < 0.20:
                out = out.replace(" ", "-")
            if rng.random() < 0.15:
                out = out.replace("-", " ")
            if rng.random() < 0.10:
                out = out + "."  # punctuation noise
            if rng.random() < 0.08:
                out = out.replace(" ", "  ")  # whitespace noise

            return out

        def _invent_importer() -> str:
            left = _choice(stems)
            right = _choice(["TRADING", "SUPPLY", "IMPORTS", "DISTRIBUTION", "HOLDING", "PROJECTS"])
            mid = _choice(["CO", "HOUSE", "PARTNERS", "VENTURES", "GLOBAL"])
            return f"{left} {mid} {right}"

        trade_feed: List[Dict[str, Any]] = []
        for i in range(self.trade_records):
            sid = f"S{i+1:06d}"

            # Most shipments select a registry exporter; a small fraction are truly unknown.
            if rng.random() < 0.03:
                exporter_name = f"{_choice(stems)} {_choice(['EXPORT', 'TRADING', 'SOURCES'])}"
                exporter_country = _choice(countries)
            else:
                ent = registry[int(rng.random() * len(registry))]
                exporter_country = ent["country"]
                exporter_name = _noisy_exporter_name(str(ent["entity_name"]))

            importer_name = _invent_importer()
            importer_country = _choice([c for c in countries if c != exporter_country])
            domain = _choice(domains)
            hs_code = _choice(hs_by_domain[domain])

            # Values are domain-shaped: some domains typically price higher per shipment.
            base = {
                "chem_precursors": 25000,
                "machine_tools": 120000,
                "aerospace_uas_avionics": 180000,
                "maritime_shipbuilding_ports": 140000,
                "energy_equipment": 160000,
                "medical_bio_lab": 90000,
                "luxury_dual_use_consumer": 45000,
                "services": 60000,
                "intangibles": 80000,
                "finance_signals": 30000,
                "procurement": 110000,
                "research_links": 20000,
            }[domain]
            value = round((0.35 + rng.random() * 1.65) * base, 2)

            ship_date = (base_date + timedelta(days=int(rng.random() * 365))).isoformat()

            trade_feed.append(
                {
                    "shipment_id": sid,
                    "exporter_name": exporter_name,
                    "importer_name": importer_name,
                    "exporter_country": exporter_country,
                    "importer_country": importer_country,
                    "country": exporter_country,
                    "domain": domain,
                    "hs_code": hs_code,
                    "description": f"{domain} consignment (invented)",
                    "incoterm": _choice(incoterms),
                    "transport_mode": _choice(transport_modes),
                    "value_usd": float(value),
                    "ship_date": ship_date,
                }
            )

        trade_feed.sort(key=lambda r: r["shipment_id"])

        # --- payments (finance-adjacent signals) ---
        payments: List[Dict[str, Any]] = []
        for i, tr in enumerate(trade_feed):
            pid = f"P{i+1:06d}"
            amount = round(float(tr["value_usd"]) * (0.7 + rng.random() * 0.6), 2)
            payments.append(
                {
                    "payment_id": pid,
                    "shipment_id": tr["shipment_id"],
                    "payer_name": tr["importer_name"],
                    "payee_name": tr["exporter_name"],
                    "amount_usd": amount,
                    "currency": "USD",
                    "method": _choice(payment_methods),
                    "intermediary_bank": _choice(banks),
                    "insurer": _choice(insurers) if rng.random() < 0.35 else "",
                    "payment_date": tr["ship_date"],
                }
            )

            # Occasional split payment.
            if rng.random() < 0.10:
                pid2 = f"P{i+1:06d}B"
                amount2 = round(float(tr["value_usd"]) * (0.15 + rng.random() * 0.25), 2)
                payments.append(
                    {
                        "payment_id": pid2,
                        "shipment_id": tr["shipment_id"],
                        "payer_name": tr["importer_name"],
                        "payee_name": tr["exporter_name"],
                        "amount_usd": amount2,
                        "currency": "USD",
                        "method": "NETTING",
                        "intermediary_bank": _choice(banks),
                        "insurer": "",
                        "payment_date": tr["ship_date"],
                    }
                )

        payments.sort(key=lambda r: (r["shipment_id"], r["payment_id"]))

        # --- maritime legs ---
        maritime_legs: List[Dict[str, Any]] = []
        for i, tr in enumerate(trade_feed):
            if tr["transport_mode"] != "SEA":
                continue
            leg_id = f"L{i+1:06d}"
            a = _choice(ports)
            b = _choice([p for p in ports if p != a])
            transship = rng.random() < 0.22
            maritime_legs.append(
                {
                    "leg_id": leg_id,
                    "shipment_id": tr["shipment_id"],
                    "from_port": a,
                    "to_port": b,
                    "carrier": _choice(carriers),
                    "vessel_type": _choice(["CONTAINER", "BULK", "RO-RO", "TANKER"]),
                    "transshipment": 1 if transship else 0,
                    "depart_date": tr["ship_date"],
                    "arrive_date": tr["ship_date"],
                }
            )
        maritime_legs.sort(key=lambda r: r["leg_id"])

        # --- procurement notices ---
        procurement: List[Dict[str, Any]] = []
        for i in range(max(12, self.registry_entities // 2)):
            tid = f"T{i+1:05d}"
            buyer = _invent_importer()
            supplier = str(registry[int(rng.random() * len(registry))]["entity_name"])
            domain = _choice(domains)
            value = round((0.6 + rng.random() * 2.2) * 75000, 2)
            notice = (base_date + timedelta(days=int(rng.random() * 365))).isoformat()
            award = (base_date + timedelta(days=int(rng.random() * 365))).isoformat()
            procurement.append(
                {
                    "tender_id": tid,
                    "buyer_name": buyer,
                    "supplier_name": supplier,
                    "domain": domain,
                    "description": f"{domain} procurement (invented)",
                    "value_usd": float(value),
                    "notice_date": notice,
                    "award_date": award,
                }
            )
        procurement.sort(key=lambda r: r["tender_id"])

        # --- services ---
        services: List[Dict[str, Any]] = []
        for i in range(max(20, self.registry_entities)):
            sid = f"SV{i+1:05d}"
            provider = str(registry[int(rng.random() * len(registry))]["entity_name"])
            counterparty = _invent_importer()
            stype = _choice(["MAINTENANCE", "ENGINEERING", "CALIBRATION", "CONTRACT_MFG", "TRAINING"])
            start = (base_date + timedelta(days=int(rng.random() * 365))).isoformat()
            end = (base_date + timedelta(days=int(rng.random() * 365))).isoformat()
            value = round((0.2 + rng.random() * 1.8) * 60000, 2)
            services.append(
                {
                    "service_id": sid,
                    "provider_name": provider,
                    "counterparty_name": counterparty,
                    "service_type": stype,
                    "description": f"{stype} service (invented)",
                    "start_date": start,
                    "end_date": end,
                    "value_usd": float(value),
                }
            )
        services.sort(key=lambda r: r["service_id"])

        # --- intangibles ---
        intangibles: List[Dict[str, Any]] = []
        for i in range(max(14, self.registry_entities // 2)):
            iid = f"I{i+1:05d}"
            owner = str(registry[int(rng.random() * len(registry))]["entity_name"])
            itype = _choice(["FIRMWARE", "DESIGN", "PROCESS_RECIPE", "SOFTWARE_MODULE", "TEST_SUITE"])
            mode = _choice(["EMAIL", "PORTAL", "REMOVABLE_MEDIA", "REMOTE_ACCESS"])
            when = (base_date + timedelta(days=int(rng.random() * 365))).isoformat()
            intangibles.append(
                {
                    "intangible_id": iid,
                    "owner_name": owner,
                    "intangible_type": itype,
                    "transfer_mode": mode,
                    "description": f"{itype} transfer (invented)",
                    "transfer_date": when,
                }
            )
        intangibles.sort(key=lambda r: r["intangible_id"])

        # --- research links ---
        research_links: List[Dict[str, Any]] = []
        for i in range(max(10, self.registry_entities // 3)):
            rid = f"R{i+1:05d}"
            ent = str(registry[int(rng.random() * len(registry))]["entity_name"])
            topic = _choice(["MATERIALS", "GUIDANCE", "SENSING", "CATALYSIS", "THERMALS"])
            title = f"INVENTED STUDY {i+1}: {topic}"
            lab = f"{_choice(stems)} LAB"
            when = (base_date + timedelta(days=int(rng.random() * 365))).isoformat()
            score = round(0.35 + rng.random() * 0.55, 3)
            research_links.append(
                {
                    "link_id": rid,
                    "entity_name": ent,
                    "publication_title": title,
                    "lab_name": lab,
                    "link_date": when,
                    "similarity": float(score),
                }
            )
        research_links.sort(key=lambda r: r["link_id"])

        return {
            "registry": registry,
            "trade_feed": trade_feed,
            "payments": payments,
            "procurement": procurement,
            "services": services,
            "intangibles": intangibles,
            "research_links": research_links,
            "maritime_legs": maritime_legs,
        }

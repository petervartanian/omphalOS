from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from omphalos.core.contracts import load_json_schema, validate_json_against_schema
from omphalos.core.fingerprint import sha256_json
from omphalos.core.time import deterministic_now_iso


def _index_by_shipment(trade_rows: List[dict[str, Any]]) -> Dict[str, dict[str, Any]]:
    return {r["shipment_id"]: r for r in trade_rows}


def _index_many(rows: List[dict[str, Any]], key: str) -> Dict[str, List[dict[str, Any]]]:
    out: Dict[str, List[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(str(r.get(key, "")), []).append(r)
    return out


def write_evidence_packets(
    run_dir: Path,
    entity_scores: List[dict[str, Any]],
    trade_rows: List[dict[str, Any]],
    matches: List[dict[str, Any]],
    review_queue: List[dict[str, Any]],
    payments: List[dict[str, Any]],
    procurement: List[dict[str, Any]],
    services: List[dict[str, Any]],
    intangibles: List[dict[str, Any]],
    research_links: List[dict[str, Any]],
    maritime_legs: List[dict[str, Any]],
    run_id: str,
    clock_seed: str,
) -> List[str]:
    schema = load_json_schema("evidence_packet_contract.schema.json")
    out_dir = run_dir / "exports" / "packets"
    out_dir.mkdir(parents=True, exist_ok=True)

    trade_by_id = _index_by_shipment(trade_rows)
    matches_by_entity: Dict[str, List[dict[str, Any]]] = {}
    for m in matches:
        matches_by_entity.setdefault(m["entity_id"], []).append(m)

    # Pre-index annex data for efficient per-entity selection.
    payments_by_ship = _index_many(payments, "shipment_id")
    legs_by_ship = _index_many(maritime_legs, "shipment_id")
    procurement_by_supplier = _index_many(procurement, "supplier_name")
    services_by_provider = _index_many(services, "provider_name")
    intangibles_by_owner = _index_many(intangibles, "owner_name")
    research_by_entity = _index_many(research_links, "entity_name")

    out_paths: List[str] = []
    for e in entity_scores[:20]:  # bounded for demo determinism and size
        eid = e["entity_id"]
        rel = f"exports/packets/packet_{eid}.json"
        path = run_dir / rel

        entity_matches = sorted(matches_by_entity.get(eid, []), key=lambda x: x["shipment_id"])[:5]
        evidence: List[dict[str, Any]] = []
        lineage_refs: List[str] = ["RESOLVE", "ANALYZE", "EXPORT"]
        review_status = "CLEAR"
        review_reason = "sufficient_confidence"

        ship_ids: List[str] = []
        for m in entity_matches:
            tr = trade_by_id.get(m["shipment_id"])
            if not tr:
                continue
            ship_ids.append(tr["shipment_id"])
            ev = {
                "shipment_id": tr["shipment_id"],
                "hs_code": tr["hs_code"],
                "domain": tr.get("domain", ""),
                "value_usd": tr["value_usd"],
                "ship_date": tr["ship_date"],
                "transport_mode": tr.get("transport_mode", ""),
                "incoterm": tr.get("incoterm", ""),
                "match_score": m["score"],
                "match_status": m["status"],
            }
            evidence.append(ev)
            if m["status"] == "REVIEW":
                review_status = "REVIEW"
                review_reason = "at_least_one_low_confidence_match"

        entity_name = str(e["entity_name"])

        annexes = {
            "payments": [p for sid in ship_ids for p in payments_by_ship.get(sid, [])][:10],
            "maritime_legs": [l for sid in ship_ids for l in legs_by_ship.get(sid, [])][:10],
            "procurement": procurement_by_supplier.get(entity_name, [])[:10],
            "services": services_by_provider.get(entity_name, [])[:10],
            "intangibles": intangibles_by_owner.get(entity_name, [])[:10],
            "research_links": research_by_entity.get(entity_name, [])[:10],
        }

        packet = {
            "schema_version": "1.0",
            "run_id": run_id,
            "packet_id": f"packet-{eid}",
            "created_at": deterministic_now_iso(clock_seed, salt=f"packet:{eid}"),
            "claim": "Entity exhibits elevated chokepoint exposure under the reference scoring model.",
            "entity": {
                "entity_id": eid,
                "entity_name": entity_name,
                "country": e["country"],
                "chokepoint_score": e["chokepoint_score"],
                "shipment_count": e["shipment_count"],
                "total_value_usd": e["total_value_usd"],
            },
            "evidence": evidence,
            "annexes": annexes,
            "lineage": lineage_refs,
            "review": {"status": review_status, "reason": review_reason},
            "hashes": {"packet": ""},
        }
        packet["hashes"]["packet"] = sha256_json(packet)

        validate_json_against_schema(packet, schema)

        path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        out_paths.append(rel)

    return out_paths

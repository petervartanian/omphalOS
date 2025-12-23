from __future__ import annotations

from typing import Any, List


def _norm_text(s: str) -> str:
    return " ".join(s.strip().split()).upper()


def canonicalize_registry(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    out: List[dict[str, Any]] = []
    for r in rows:
        out.append({
            "entity_id": str(r["entity_id"]),
            "entity_name": _norm_text(str(r["entity_name"])),
            "country": str(r["country"]).upper(),
        })
    out.sort(key=lambda x: x["entity_id"])
    return out


def canonicalize_trade_feed(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    out: List[dict[str, Any]] = []
    for r in rows:
        out.append({
            "shipment_id": str(r["shipment_id"]),
            "exporter_name": _norm_text(str(r["exporter_name"])),
            "importer_name": _norm_text(str(r["importer_name"])),
            "country": str(r["country"]).upper(),
            "hs_code": str(r["hs_code"]),
            "value_usd": float(r["value_usd"]),
            "ship_date": str(r["ship_date"]),
        })
    out.sort(key=lambda x: x["shipment_id"])
    return out

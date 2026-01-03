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
        exporter_country = str(r.get("exporter_country", r.get("country", ""))).upper()
        importer_country = str(r.get("importer_country", r.get("country", exporter_country))).upper()
        out.append({
            "shipment_id": str(r["shipment_id"]),
            "exporter_name": _norm_text(str(r["exporter_name"])),
            "importer_name": _norm_text(str(r["importer_name"])),
            "exporter_country": exporter_country,
            "importer_country": importer_country,
            "country": exporter_country,
            "domain": str(r.get("domain", "")),
            "hs_code": str(r["hs_code"]),
            "description": _norm_text(str(r.get("description", ""))) if r.get("description") is not None else "",
            "incoterm": str(r.get("incoterm", "")).upper(),
            "transport_mode": str(r.get("transport_mode", "")).upper(),
            "value_usd": float(r["value_usd"]),
            "ship_date": str(r["ship_date"]),
        })
    out.sort(key=lambda x: x["shipment_id"])
    return out


def canonicalize_payments(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    out: List[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "payment_id": str(r["payment_id"]),
                "shipment_id": str(r["shipment_id"]),
                "payer_name": _norm_text(str(r.get("payer_name", ""))),
                "payee_name": _norm_text(str(r.get("payee_name", ""))),
                "amount_usd": float(r.get("amount_usd", 0.0)),
                "currency": str(r.get("currency", "")).upper(),
                "method": str(r.get("method", "")).upper(),
                "intermediary_bank": _norm_text(str(r.get("intermediary_bank", ""))),
                "insurer": _norm_text(str(r.get("insurer", ""))),
                "payment_date": str(r.get("payment_date", "")),
            }
        )
    out.sort(key=lambda x: (x["shipment_id"], x["payment_id"]))
    return out


def canonicalize_procurement(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    out: List[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "tender_id": str(r["tender_id"]),
                "buyer_name": _norm_text(str(r.get("buyer_name", ""))),
                "supplier_name": _norm_text(str(r.get("supplier_name", ""))),
                "domain": str(r.get("domain", "")),
                "description": _norm_text(str(r.get("description", ""))) if r.get("description") is not None else "",
                "value_usd": float(r.get("value_usd", 0.0)),
                "notice_date": str(r.get("notice_date", "")),
                "award_date": str(r.get("award_date", "")),
            }
        )
    out.sort(key=lambda x: x["tender_id"])
    return out


def canonicalize_services(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    out: List[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "service_id": str(r["service_id"]),
                "provider_name": _norm_text(str(r.get("provider_name", ""))),
                "counterparty_name": _norm_text(str(r.get("counterparty_name", ""))),
                "service_type": str(r.get("service_type", "")).upper(),
                "description": _norm_text(str(r.get("description", ""))) if r.get("description") is not None else "",
                "start_date": str(r.get("start_date", "")),
                "end_date": str(r.get("end_date", "")),
                "value_usd": float(r.get("value_usd", 0.0)),
            }
        )
    out.sort(key=lambda x: x["service_id"])
    return out


def canonicalize_intangibles(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    out: List[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "intangible_id": str(r["intangible_id"]),
                "owner_name": _norm_text(str(r.get("owner_name", ""))),
                "intangible_type": str(r.get("intangible_type", "")).upper(),
                "transfer_mode": str(r.get("transfer_mode", "")).upper(),
                "description": _norm_text(str(r.get("description", ""))) if r.get("description") is not None else "",
                "transfer_date": str(r.get("transfer_date", "")),
            }
        )
    out.sort(key=lambda x: x["intangible_id"])
    return out


def canonicalize_research_links(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    out: List[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "link_id": str(r["link_id"]),
                "entity_name": _norm_text(str(r.get("entity_name", ""))),
                "publication_title": _norm_text(str(r.get("publication_title", ""))),
                "lab_name": _norm_text(str(r.get("lab_name", ""))),
                "link_date": str(r.get("link_date", "")),
                "similarity": float(r.get("similarity", 0.0)),
            }
        )
    out.sort(key=lambda x: x["link_id"])
    return out


def canonicalize_maritime_legs(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    out: List[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "leg_id": str(r["leg_id"]),
                "shipment_id": str(r["shipment_id"]),
                "from_port": _norm_text(str(r.get("from_port", ""))),
                "to_port": _norm_text(str(r.get("to_port", ""))),
                "carrier": _norm_text(str(r.get("carrier", ""))),
                "vessel_type": str(r.get("vessel_type", "")).upper(),
                "transshipment": int(r.get("transshipment", 0)),
                "depart_date": str(r.get("depart_date", "")),
                "arrive_date": str(r.get("arrive_date", "")),
            }
        )
    out.sort(key=lambda x: x["leg_id"])
    return out

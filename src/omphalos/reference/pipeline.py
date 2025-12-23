from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from omphalos.core.contracts import load_json_schema, validate_json_against_schema
from omphalos.core.fingerprint import sha256_file, sha256_json
from omphalos.core.io.db import connect_sqlite, create_table, insert_many
from omphalos.core.lineage import LineageEvent
from omphalos.core.time import deterministic_now_iso

from .ingest.connectors.demo_registry import DemoRegistryConnector
from .ingest.connectors.demo_trade_feed import DemoTradeFeedConnector
from .normalize.canonicalize import canonicalize_registry, canonicalize_trade_feed
from .resolve.match import resolve_entities
from .resolve.features import canonical_name
from .analytics.chokepoints.scoring import compute_chokepoint_scores
from .analytics.chokepoints.sensitivity import compute_sensitivity
from .products.exports.briefing_tables import write_briefing_table_entities
from .products.exports.packets import write_evidence_packets
from .products.narratives.deltas import write_narrative_deltas


def run_reference_pipeline(*, cfg, run_dir: Path, clock_seed: str, logger, run_id: str) -> Dict[str, Any]:
    lineage: List[LineageEvent] = []
    inputs_index: List[Dict[str, Any]] = []

    # INGEST
    # The registry is generated first so the synthetic trade feed can be drawn
    # from its entity universe, yielding a high (but not perfect) resolution
    # rate in a fully deterministic way.
    registry_rows = DemoRegistryConnector(entities=cfg.inputs.registry_entities).read(seed=cfg.run.seed)

    base_counts: Dict[str, int] = {}
    for r in registry_rows:
        base = canonical_name(str(r["entity_name"]))
        base_counts[base] = base_counts.get(base, 0) + 1

    exporter_pool = sorted(base_counts.keys())
    ambiguous_exporters = sorted([k for k, v in base_counts.items() if v > 1])

    trade_rows = DemoTradeFeedConnector(
        records=cfg.inputs.trade_feed_records,
        exporter_pool=exporter_pool,
        ambiguous_exporters=ambiguous_exporters,
        ambiguous_fraction=0.05,
    ).read(seed=cfg.run.seed)
    inputs_index.append({"name": "trade_feed", "fingerprint": sha256_json(trade_rows), "row_count": len(trade_rows)})
    inputs_index.append({"name": "registry", "fingerprint": sha256_json(registry_rows), "row_count": len(registry_rows)})
    lineage.append(LineageEvent.create(run_id, "INGEST", [], ["trade_feed", "registry"], {"counts": {"trade_feed": len(trade_rows), "registry": len(registry_rows)}}, clock_seed))
    logger.log("INFO", "ingest_complete", trade_feed=len(trade_rows), registry=len(registry_rows))

    # NORMALIZE
    trade_norm = canonicalize_trade_feed(trade_rows)
    registry_norm = canonicalize_registry(registry_rows)
    lineage.append(LineageEvent.create(run_id, "NORMALIZE", ["trade_feed", "registry"], ["trade_feed_norm", "registry_norm"], {}, clock_seed))
    logger.log("INFO", "normalize_complete")

    # RESOLVE
    matches, review_queue, match_stats = resolve_entities(trade_norm, registry_norm)
    lineage.append(LineageEvent.create(run_id, "RESOLVE", ["trade_feed_norm", "registry_norm"], ["entity_matches", "review_queue"], match_stats, clock_seed))
    logger.log("INFO", "resolve_complete", **match_stats)

    # ANALYZE
    entity_scores = compute_chokepoint_scores(trade_norm, matches, registry_norm)
    sensitivity = compute_sensitivity(entity_scores)
    lineage.append(LineageEvent.create(run_id, "ANALYZE", ["entity_matches"], ["entity_scores", "sensitivity"], {"entities": len(entity_scores)}, clock_seed))
    logger.log("INFO", "analyze_complete", entities=len(entity_scores))

    # WAREHOUSE (SQLite)
    warehouse_path = run_dir / "warehouse" / "warehouse.sqlite"
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_sqlite(warehouse_path)
    try:
        create_table(conn, "trade_feed", [
            "shipment_id TEXT PRIMARY KEY",
            "exporter_name TEXT",
            "importer_name TEXT",
            "country TEXT",
            "hs_code TEXT",
            "value_usd REAL",
            "ship_date TEXT"
        ])
        create_table(conn, "registry", [
            "entity_id TEXT PRIMARY KEY",
            "entity_name TEXT",
            "country TEXT"
        ])
        create_table(conn, "entity_matches", [
            "shipment_id TEXT",
            "entity_id TEXT",
            "score REAL",
            "status TEXT",
            "explanation TEXT"
        ])
        create_table(conn, "entity_scores", [
            "entity_id TEXT",
            "entity_name TEXT",
            "country TEXT",
            "shipment_count INTEGER",
            "total_value_usd REAL",
            "chokepoint_score REAL"
        ])
        insert_many(conn, "trade_feed", trade_norm)
        insert_many(conn, "registry", registry_norm)
        insert_many(conn, "entity_matches", matches)
        insert_many(conn, "entity_scores", entity_scores)
        conn.commit()
    finally:
        conn.close()
    lineage.append(LineageEvent.create(run_id, "WAREHOUSE", ["trade_feed_norm", "registry_norm", "entity_matches"], ["warehouse.sqlite"], {"path": "warehouse/warehouse.sqlite"}, clock_seed))
    logger.log("INFO", "warehouse_complete", path="warehouse/warehouse.sqlite")

    # EXPORT products
    exports_paths: Dict[str, List[str]] = {"briefing_tables": [], "packets": [], "narratives": []}
    exports_fps: Dict[str, str] = {}

    bt_paths = write_briefing_table_entities(run_dir, entity_scores)
    exports_paths["briefing_tables"].extend(bt_paths)
    for p in bt_paths:
        exports_fps[p] = sha256_file(run_dir / p)

    pkt_paths = write_evidence_packets(run_dir, entity_scores, trade_norm, matches, review_queue, run_id, clock_seed)
    exports_paths["packets"].extend(pkt_paths)
    for p in pkt_paths:
        exports_fps[p] = sha256_file(run_dir / p)

    nar_paths = write_narrative_deltas(run_dir, entity_scores, sensitivity, run_id, clock_seed)
    exports_paths["narratives"].extend(nar_paths)
    for p in nar_paths:
        exports_fps[p] = sha256_file(run_dir / p)

    lineage.append(LineageEvent.create(run_id, "EXPORT", ["entity_scores", "sensitivity"], bt_paths + pkt_paths + nar_paths, {"counts": {"briefing_tables": len(bt_paths), "packets": len(pkt_paths), "narratives": len(nar_paths)}}, clock_seed))
    logger.log("INFO", "export_complete", briefing_tables=len(bt_paths), packets=len(pkt_paths), narratives=len(nar_paths))

    # metrics for gates
    metrics = {
        "match_rate": float(match_stats["matched"]) / float(match_stats["total"]) if match_stats["total"] else 1.0,
        "review_fraction": float(match_stats["review"]) / float(match_stats["total"]) if match_stats["total"] else 0.0,
    }

    return {
        "inputs_index": inputs_index,
        "lineage_events": lineage,
        "warehouse_path": warehouse_path,
        "exports_paths": exports_paths,
        "exports_fingerprints": exports_fps,
        "metrics": metrics,
    }

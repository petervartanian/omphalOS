from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from omphalos.core.contracts import load_json_schema, validate_json_against_schema
from omphalos.core.fingerprint import sha256_file, sha256_json
from omphalos.core.io.db import connect_sqlite, execute_sql_file, insert_many
from omphalos.core.lineage import LineageEvent
from omphalos.core.time import deterministic_now_iso

from .ingest.connectors.organic_world import OrganicWorld
from .normalize.canonicalize import (
    canonicalize_registry,
    canonicalize_trade_feed,
    canonicalize_payments,
    canonicalize_procurement,
    canonicalize_services,
    canonicalize_intangibles,
    canonicalize_research_links,
    canonicalize_maritime_legs,
)
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

    world = OrganicWorld(registry_entities=cfg.inputs.registry_entities, trade_records=cfg.inputs.trade_feed_records).build(seed=cfg.run.seed)
    registry_rows = world["registry"]
    trade_rows = world["trade_feed"]
    payments_rows = world["payments"]
    procurement_rows = world["procurement"]
    services_rows = world["services"]
    intangibles_rows = world["intangibles"]
    research_rows = world["research_links"]
    maritime_rows = world["maritime_legs"]

    inputs_index.append({"name": "trade_feed", "fingerprint": sha256_json(trade_rows), "row_count": len(trade_rows)})
    inputs_index.append({"name": "registry", "fingerprint": sha256_json(registry_rows), "row_count": len(registry_rows)})
    inputs_index.append({"name": "payments", "fingerprint": sha256_json(payments_rows), "row_count": len(payments_rows)})
    inputs_index.append({"name": "procurement", "fingerprint": sha256_json(procurement_rows), "row_count": len(procurement_rows)})
    inputs_index.append({"name": "services", "fingerprint": sha256_json(services_rows), "row_count": len(services_rows)})
    inputs_index.append({"name": "intangibles", "fingerprint": sha256_json(intangibles_rows), "row_count": len(intangibles_rows)})
    inputs_index.append({"name": "research_links", "fingerprint": sha256_json(research_rows), "row_count": len(research_rows)})
    inputs_index.append({"name": "maritime_legs", "fingerprint": sha256_json(maritime_rows), "row_count": len(maritime_rows)})

    lineage.append(
        LineageEvent.create(
            run_id,
            "INGEST",
            [],
            ["trade_feed", "registry", "payments", "procurement", "services", "intangibles", "research_links", "maritime_legs"],
            {
                "counts": {
                    "trade_feed": len(trade_rows),
                    "registry": len(registry_rows),
                    "payments": len(payments_rows),
                    "procurement": len(procurement_rows),
                    "services": len(services_rows),
                    "intangibles": len(intangibles_rows),
                    "research_links": len(research_rows),
                    "maritime_legs": len(maritime_rows),
                }
            },
            clock_seed,
        )
    )
    logger.log(
        "INFO",
        "ingest_complete",
        trade_feed=len(trade_rows),
        registry=len(registry_rows),
        payments=len(payments_rows),
        procurement=len(procurement_rows),
        services=len(services_rows),
        intangibles=len(intangibles_rows),
        research_links=len(research_rows),
        maritime_legs=len(maritime_rows),
    )

    trade_norm = canonicalize_trade_feed(trade_rows)
    registry_norm = canonicalize_registry(registry_rows)
    payments_norm = canonicalize_payments(payments_rows)
    procurement_norm = canonicalize_procurement(procurement_rows)
    services_norm = canonicalize_services(services_rows)
    intangibles_norm = canonicalize_intangibles(intangibles_rows)
    research_norm = canonicalize_research_links(research_rows)
    maritime_norm = canonicalize_maritime_legs(maritime_rows)

    lineage.append(
        LineageEvent.create(
            run_id,
            "NORMALIZE",
            ["trade_feed", "registry", "payments", "procurement", "services", "intangibles", "research_links", "maritime_legs"],
            ["trade_feed_norm", "registry_norm", "payments_norm", "procurement_norm", "services_norm", "intangibles_norm", "research_links_norm", "maritime_legs_norm"],
            {},
            clock_seed,
        )
    )
    logger.log("INFO", "normalize_complete")

    matches, review_queue, match_stats = resolve_entities(trade_norm, registry_norm)
    lineage.append(LineageEvent.create(run_id, "RESOLVE", ["trade_feed_norm", "registry_norm"], ["entity_matches", "review_queue"], match_stats, clock_seed))
    logger.log("INFO", "resolve_complete", **match_stats)

    entity_scores = compute_chokepoint_scores(trade_norm, matches, registry_norm)
    sensitivity = compute_sensitivity(entity_scores)
    lineage.append(LineageEvent.create(run_id, "ANALYZE", ["entity_matches"], ["entity_scores", "sensitivity"], {"entities": len(entity_scores)}, clock_seed))
    logger.log("INFO", "analyze_complete", entities=len(entity_scores))

    warehouse_path = run_dir / "warehouse" / "warehouse.sqlite"
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_sqlite(warehouse_path)
    try:
        execute_sql_file(conn, Path(__file__).resolve().parents[3] / "warehouse" / "db" / "schema.sql")
        insert_many(conn, "trade_feed", trade_norm)
        insert_many(conn, "registry", registry_norm)
        insert_many(conn, "entity_matches", matches)
        insert_many(conn, "entity_scores", entity_scores)
        insert_many(conn, "payments", payments_norm)
        insert_many(conn, "procurement", procurement_norm)
        insert_many(conn, "services", services_norm)
        insert_many(conn, "intangibles", intangibles_norm)
        insert_many(conn, "research_links", research_norm)
        insert_many(conn, "maritime_legs", maritime_norm)
        conn.commit()
        execute_sql_file(conn, Path(__file__).resolve().parents[3] / "warehouse" / "db" / "derived_views.sql")
        conn.commit()
    finally:
        conn.close()
    lineage.append(LineageEvent.create(run_id, "WAREHOUSE", ["trade_feed_norm", "registry_norm", "entity_matches"], ["warehouse.sqlite"], {"path": "warehouse/warehouse.sqlite"}, clock_seed))
    logger.log("INFO", "warehouse_complete", path="warehouse/warehouse.sqlite")

    exports_paths: Dict[str, List[str]] = {"briefing_tables": [], "packets": [], "narratives": []}
    exports_fps: Dict[str, str] = {}

    bt_paths = write_briefing_table_entities(run_dir, entity_scores)
    exports_paths["briefing_tables"].extend(bt_paths)
    for p in bt_paths:
        exports_fps[p] = sha256_file(run_dir / p)

    pkt_paths = write_evidence_packets(
        run_dir,
        entity_scores,
        trade_norm,
        matches,
        review_queue,
        payments_norm,
        procurement_norm,
        services_norm,
        intangibles_norm,
        research_norm,
        maritime_norm,
        run_id,
        clock_seed,
    )
    exports_paths["packets"].extend(pkt_paths)
    for p in pkt_paths:
        exports_fps[p] = sha256_file(run_dir / p)

    nar_paths = write_narrative_deltas(run_dir, entity_scores, sensitivity, run_id, clock_seed)
    exports_paths["narratives"].extend(nar_paths)
    for p in nar_paths:
        exports_fps[p] = sha256_file(run_dir / p)

    lineage.append(LineageEvent.create(run_id, "EXPORT", ["entity_scores", "sensitivity"], bt_paths + pkt_paths + nar_paths, {"counts": {"briefing_tables": len(bt_paths), "packets": len(pkt_paths), "narratives": len(nar_paths)}}, clock_seed))
    logger.log("INFO", "export_complete", briefing_tables=len(bt_paths), packets=len(pkt_paths), narratives=len(nar_paths))

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

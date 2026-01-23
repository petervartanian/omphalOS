import csv
import json
import os
import tarfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from .standards import assess_sql_admissibility
from .warehouse import connect
from .util import sha256_file, write_json


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _find_repo_root(start: Path) -> Path:
    """Ascend until a directory containing 'packs' and 'core' is found."""
    p = start.resolve()
    for cand in [p] + list(p.parents):
        if (cand / "packs").is_dir() and (cand / "core").is_dir():
            return cand
    raise RuntimeError(f"could not find repo root from {start}")


def _import_csv(db, csv_path: Path, table: str) -> int:
    """Import a CSV into table. Returns number of imported rows."""
    with csv_path.open("r", encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r)
        rows = list(r)

    q = f"INSERT OR REPLACE INTO {table}({','.join(header)}) VALUES ({','.join(['?'] * len(header))})"
    db.executemany(q, rows)
    db.commit()
    return len(rows)


def _copy_case_and_packs(case_path: Path, run_dir: Path, packs_index_rel: str) -> Tuple[Path, Path]:
    """Copy the case file and all packs described by the index into the run directory."""
    case_dst = run_dir / "case.json"
    case_dst.write_text(case_path.read_text(encoding="utf-8"), encoding="utf-8")

    repo_root = _find_repo_root(case_path)
    packs_src_dir = (repo_root / "packs").resolve()
    index_src = (repo_root / packs_index_rel).resolve()

    packs_dst_dir = run_dir / "packs"
    packs_dst_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(index_src, packs_dst_dir / "INDEX.json")
    idx = json.loads(index_src.read_text(encoding="utf-8"))
    for pk in idx.get("packs", []):
        shutil.copy2(packs_src_dir / pk["file"], packs_dst_dir / pk["file"])

    return case_dst, packs_dst_dir / "INDEX.json"


def _is_within_directory(base: Path, target: Path) -> bool:
    base_r = base.resolve()
    try:
        target.resolve().relative_to(base_r)
        return True
    except Exception:
        return False


def _safe_extract_subset(tar_path: Path, dest: Path, members: List[str]) -> None:
    """Extract specific tar members defensively."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    wanted = set(members)
    with tarfile.open(tar_path, "r:gz") as tf:
        for m in tf.getmembers():
            if m.name not in wanted:
                continue

            name = m.name
            if os.path.isabs(name) or name.startswith("~"):
                raise ValueError(f"unsafe tar member path: {name}")
            p = Path(name)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError(f"unsafe tar traversal: {name}")
            if m.issym() or m.islnk() or m.isdev():
                raise ValueError(f"unsafe tar member type: {name}")

            out_path = dest / p
            if not _is_within_directory(dest, out_path):
                raise ValueError(f"unsafe tar escape: {name}")

            tf.extract(m, path=dest)

    missing = sorted(wanted - {m for m in members if (dest / m).exists() or (dest / Path(m)).exists()})
    # Missing is acceptable if the tar member is a directory entry omitted by tar; files must exist.
    for m in members:
        if m.endswith("/"):
            continue
        if not (dest / m).exists():
            raise FileNotFoundError(f"expected member not extracted: {m}")


def _write_csv(path: Path, header: List[str], rows: List[Tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _collect_checksums(run_dir: Path) -> Dict[str, str]:
    """Compute checksums for all files under run_dir, excluding run.json itself."""
    checksums: Dict[str, str] = {}
    for fp in sorted(run_dir.rglob("*")):
        if fp.is_file():
            rel = fp.relative_to(run_dir).as_posix()
            if rel == "run.json":
                continue
            checksums[rel] = sha256_file(fp)
    return checksums


def _load_pack_index(index_path: Path) -> Dict[str, Dict]:
    idx = json.loads(index_path.read_text(encoding="utf-8"))
    return {p["name"]: p for p in idx.get("packs", [])}


def run_case(case_path, out_root="hydrate/runs"):
    case_path = Path(case_path)
    case = json.loads(case_path.read_text(encoding="utf-8"))

    if "case_id" not in case:
        raise ValueError("case.case_id missing")
    if "question" not in case:
        raise ValueError("case.question missing")
    if not case.get("investigations"):
        raise ValueError("case.investigations must be non-empty")
    packs_index_rel = (case.get("packs") or {}).get("index")
    if not packs_index_rel:
        raise ValueError("case.packs.index missing (must point to packs/INDEX.json)")
    domains = (case.get("scope") or {}).get("domains")
    if not isinstance(domains, list) or len(domains) == 0:
        raise ValueError("case.scope.domains must be a non-empty list (use ['ALL'] to indicate no filter)")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(out_root) / case["case_id"] / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot the case and the exact packs used (portable run directory).
    _, run_packs_index = _copy_case_and_packs(case_path, run_dir, packs_index_rel)
    pack_map = _load_pack_index(run_packs_index)

    # Selective extraction: keep the run small while retaining provenance (tarballs remain).
    world_pack = run_dir / "packs" / pack_map["world.national.v1.tar"]["file"]
    sql_pack = run_dir / "packs" / pack_map["sql.catalog.v1.tar"]["file"]

    inputs = run_dir / "inputs"
    world_root = inputs / "world"
    sql_root = inputs / "sql"

    world_members = [
        "world.national.v1/world/shards/entities_000.csv",
        "world.national.v1/world/shards/shipments_000.csv",
        "world.national.v1/world/shards/payments_000.csv",
        "world.national.v1/world/shards/intangibles_000.csv",
        "world.national.v1/world/shards/procurement_000.csv",
        "world.national.v1/world/shards/research_000.csv",
        "world.national.v1/world/shards/services_000.csv",
    ]
    _safe_extract_subset(world_pack, world_root, world_members)

    sql_members = []
    for inv_id in case["investigations"]:
        sql_members.append(f"sql.catalog.v1/sql/investigations/catalog_generated/{inv_id}.sql")
    _safe_extract_subset(sql_pack, sql_root, sql_members)

    # Materialize warehouse.
    db_path = run_dir / "warehouse.sqlite"
    db = connect(db_path)

    shard_dir = world_root / "world.national.v1" / "world" / "shards"
    counts = {}
    counts["entities"] = _import_csv(db, shard_dir / "entities_000.csv", "entities")
    counts["shipments"] = _import_csv(db, shard_dir / "shipments_000.csv", "shipments")
    counts["payments"] = _import_csv(db, shard_dir / "payments_000.csv", "payments")
    counts["intangibles"] = _import_csv(db, shard_dir / "intangibles_000.csv", "intangibles")
    counts["procurement"] = _import_csv(db, shard_dir / "procurement_000.csv", "procurement")
    counts["research"] = _import_csv(db, shard_dir / "research_000.csv", "research")
    counts["services"] = _import_csv(db, shard_dir / "services_000.csv", "services")

    claims = []
    for inv_id in case["investigations"]:
        sql_path = sql_root / "sql.catalog.v1" / "sql" / "investigations" / "catalog_generated" / f"{inv_id}.sql"
        sql_text = sql_path.read_text(encoding="utf-8")

        rep = assess_sql_admissibility(sql_text)
        if not rep.ok:
            raise RuntimeError(f"investigation inadmissible: {inv_id} ({', '.join(rep.issues)})")

        inv_out = run_dir / "investigations" / f"{inv_id}.sql"
        inv_out.parent.mkdir(parents=True, exist_ok=True)
        inv_out.write_text(sql_text, encoding="utf-8")

        cur = db.execute(sql_text)
        rows = cur.fetchall()
        header = [d[0] for d in (cur.description or [])]
        res_out = run_dir / "results" / f"{inv_id}.csv"
        _write_csv(res_out, header, rows)

        claim = {
            "claim_id": inv_id,
            "kind": "observation",
            "text": f"{inv_id} produced {len(rows)} rows for review.",
            "domain": rep.domain,
            "intent": rep.intent,
            "evidence": [
                {
                    "artifact": res_out.relative_to(run_dir).as_posix(),
                    "sha256": sha256_file(res_out),
                    "sql": inv_out.relative_to(run_dir).as_posix(),
                    "sql_sha256": sha256_file(inv_out),
                }
            ],
            "unknowns": [
                "This output alone does not establish intent, destination, end-user, or legality.",
                "Unless separately proven, the world slice should be treated as illustrative.",
            ],
            "alternatives": [
                "Benign commercial clustering can mimic risk signatures (seasonality, batching, vendor consolidation).",
                "Data generation or ingestion artifacts can create spurious structure (missing joins, duplicated IDs).",
            ],
            "falsifiers": [
                "Re-run on an independently materialized world slice; verify whether the same rows recur.",
                "Inspect raw shard rows referenced by IDs to confirm the joins are not artifacts of missing keys.",
            ],
        }
        claims.append(claim)

    db.close()

    packet = {
        "schema_version": "1.0",
        "case_id": case["case_id"],
        "run_id": run_id,
        "created_utc": _utc_now_iso(),
        "question": case["question"],
        "scope": case.get("scope") or {},
        "memo": f"Run {run_id}: executed {len(case['investigations'])} investigation(s) over a materialized world slice.",
        "method": {
            "principle": "institutionalized doubt",
            "notes": [
                "Claims are limited to observable outputs; interpretation is deferred unless separately argued and evidenced.",
                "Each claim carries unknowns, alternatives, and falsifiers as mandatory structure.",
            ],
        },
        "annexes": {"row_counts": counts},
        "claims": claims,
    }
    write_json(run_dir / "packet.json", packet)

    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "case_id": case["case_id"],
        "created_utc": _utc_now_iso(),
        "checksums": _collect_checksums(run_dir),
    }
    write_json(run_dir / "run.json", manifest)

    return str(run_dir)


def verify_run(run_path):
    p = Path(run_path)
    m = json.loads((p / "run.json").read_text(encoding="utf-8"))
    ok = True
    for rel, exp in (m.get("checksums") or {}).items():
        fp = p / rel
        ok = ok and fp.exists() and sha256_file(fp) == exp
    return ok

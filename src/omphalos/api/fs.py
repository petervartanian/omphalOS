from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Mapping

from omphalos.core.fingerprint import sha256_file


@dataclass(frozen=True)
class RunIndexEntry:
    run_id: str
    created_at: str
    root_hash: str


def _read_json(path: Path) -> Mapping[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def list_runs(artifacts_root: Path) -> List[RunIndexEntry]:
    runs_dir = artifacts_root / "runs"
    if not runs_dir.exists():
        return []
    out: List[RunIndexEntry] = []
    for p in sorted(runs_dir.iterdir()):
        if not p.is_dir():
            continue
        manifest = p / "manifest.json"
        if not manifest.exists():
            continue
        m = _read_json(manifest)
        out.append(RunIndexEntry(
            run_id=str(m.get("run_id", p.name)),
            created_at=str(m.get("created_at", "")),
            root_hash=str(m.get("artifacts_root_hash", ""))
        ))
    return out


def read_manifest(run_dir: Path) -> Mapping[str, object]:
    path = run_dir / "manifest.json"
    return _read_json(path)


def read_text_file(run_dir: Path, rel_path: str) -> str:
    target = (run_dir / rel_path).resolve()
    if run_dir.resolve() not in target.parents and target != run_dir.resolve():
        raise ValueError("path escapes run_dir")
    return target.read_text(encoding="utf-8")


def fingerprint_file(run_dir: Path, rel_path: str) -> Mapping[str, object]:
    target = (run_dir / rel_path).resolve()
    if run_dir.resolve() not in target.parents and target != run_dir.resolve():
        raise ValueError("path escapes run_dir")
    return {"path": rel_path, "size": target.stat().st_size, "sha256": sha256_file(target)}

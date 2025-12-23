from __future__ import annotations

from pathlib import Path
from typing import Dict

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse

from .fs import list_runs, read_manifest, read_text_file


app = FastAPI(title="omphalOS API", version="0.1.0")

DEFAULT_ARTIFACTS_ROOT = Path("artifacts")


@app.get("/api/runs")
def api_list_runs(artifacts_root: str = Query(default=str(DEFAULT_ARTIFACTS_ROOT))) -> object:
    root = Path(artifacts_root)
    return [e.__dict__ for e in list_runs(root)]


@app.get("/api/runs/{run_id}/manifest")
def api_read_manifest(run_id: str, artifacts_root: str = Query(default=str(DEFAULT_ARTIFACTS_ROOT))) -> object:
    run_dir = Path(artifacts_root) / "runs" / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="run not found")
    return read_manifest(run_dir)


@app.get("/api/runs/{run_id}/file", response_class=PlainTextResponse)
def api_read_file(run_id: str, path: str, artifacts_root: str = Query(default=str(DEFAULT_ARTIFACTS_ROOT))) -> object:
    run_dir = Path(artifacts_root) / "runs" / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="run not found")
    try:
        return read_text_file(run_dir, path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

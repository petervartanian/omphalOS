"""omphalOS nightly example DAG

This DAG is intentionally small: it wraps the repo's canonical CLI entrypoint and
writes run directories into a configured artifact root.

Environment variables:
  OMPHALOS_REPO_ROOT: path to repo checkout in the Airflow worker
  OMPHALOS_OUTPUT_ROOT: directory where runs should be created

Example:
  export OMPHALOS_REPO_ROOT=/opt/omphalos
  export OMPHALOS_OUTPUT_ROOT=/var/lib/omphalos/runs
"""

from __future__ import annotations

import os
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

REPO = os.environ.get("OMPHALOS_REPO_ROOT", "/opt/omphalos")
OUT = os.environ.get("OMPHALOS_OUTPUT_ROOT", "/var/lib/omphalos/runs")

with DAG(
    dag_id="omphalos_nightly_example",
    start_date=datetime(2025, 1, 1),
    schedule="0 3 * * *",
    catchup=False,
    tags=["omphalos"],
) as dag:
    run = BashOperator(
        task_id="run_example",
        bash_command=(
            f"cd {REPO} && "
            f"python -m omphalos run --config config/runs/example_run.yaml --output-root {OUT}"
        ),
    )

    verify = BashOperator(
        task_id="verify_latest",
        bash_command=(
            f"cd {REPO} && "
            f"python -m omphalos verify --run-dir $(ls -dt {OUT}/run-* | head -n 1)"
        ),
    )

    run >> verify

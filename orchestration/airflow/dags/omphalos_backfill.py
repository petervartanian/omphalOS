"""omphalOS backfill DAG (parameterized)

Trigger with dagrun conf:
  {
    "config_path": "config/runs/example_run.yaml",
    "output_root": "/var/lib/omphalos/runs"
  }

You can also set defaults via environment variables:
  OMPHALOS_REPO_ROOT
  OMPHALOS_OUTPUT_ROOT
"""

from __future__ import annotations

import os
from datetime import datetime

from airflow import DAG
from airflow.models import Variable
from airflow.operators.bash import BashOperator

REPO = os.environ.get("OMPHALOS_REPO_ROOT", "/opt/omphalos")
DEFAULT_OUT = os.environ.get("OMPHALOS_OUTPUT_ROOT", "/var/lib/omphalos/runs")

with DAG(
    dag_id="omphalos_backfill",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    tags=["omphalos"],
) as dag:
    run = BashOperator(
        task_id="run_config",
        bash_command=(
            "set -euo pipefail; "
            f"cd {REPO}; "
            "CFG='{{ dag_run.conf.get(\"config_path\", \"config/runs/example_run.yaml\") }}'; "
            f"OUT='{{ dag_run.conf.get(\"output_root\", \"{DEFAULT_OUT}\") }}'; "
            "python -m omphalos run --config ${CFG} --output-root ${OUT}"
        ),
    )

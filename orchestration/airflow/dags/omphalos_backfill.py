from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="omphalos_backfill",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    params={
        "start_date": Param("2025-01-01", type="string"),
        "end_date": Param("2025-01-31", type="string"),
    },
    tags=["omphalos"],
) as dag:
    run = BashOperator(
        task_id="run_backfill",
        bash_command="python -m omphalos backfill --start {{ params.start_date }} --end {{ params.end_date }}",
    )

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="omphalos_release",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    tags=["omphalos"],
) as dag:
    build = BashOperator(
        task_id="build_release",
        bash_command="python -m omphalos release build --latest",
    )
    verify = BashOperator(
        task_id="verify_release",
        bash_command="python -m omphalos release verify --latest",
    )
    build >> verify

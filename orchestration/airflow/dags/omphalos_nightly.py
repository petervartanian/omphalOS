from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "omphalos",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

with DAG(
    dag_id="omphalos_nightly",
    start_date=datetime(2025, 1, 1),
    schedule="0 3 * * *",
    catchup=False,
    default_args=default_args,
    tags=["omphalos"],
) as dag:
    run = BashOperator(
        task_id="run",
        bash_command="python -m omphalos run --config /etc/omphalos/run.yaml",
    )

    verify = BashOperator(
        task_id="verify",
        bash_command="python -m omphalos verify --latest",
    )

    run >> verify

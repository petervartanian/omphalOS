"""Example Spark job: ingest synthetic inputs -> Parquet staging outputs.

This is a reference surface. It deliberately avoids external services and assumes the
inputs are local files.

Usage (local mode):

  spark-submit spark/jobs/ingest_synthetic.py \
      --trade-feed examples/synthetic/trade_feed.csv \
      --registry examples/synthetic/registry.csv \
      --out-run-dir artifacts/runs/run-demo

Outputs:

  <run_dir>/staging/trade_feed/  (Parquet)
  <run_dir>/staging/registry/    (Parquet)

"""

from __future__ import annotations

import argparse
from pathlib import Path

from pyspark.sql import SparkSession


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trade-feed", required=True)
    ap.add_argument("--registry", required=True)
    ap.add_argument("--out-run-dir", required=True)
    args = ap.parse_args()

    out = Path(args.out_run_dir)
    (out / "staging").mkdir(parents=True, exist_ok=True)

    spark = SparkSession.builder.appName("omphalos_ingest_synthetic").getOrCreate()

    tf = spark.read.option("header", True).csv(args.trade_feed)
    reg = spark.read.option("header", True).csv(args.registry)

    tf.write.mode("overwrite").parquet(str(out / "staging" / "trade_feed"))
    reg.write.mode("overwrite").parquet(str(out / "staging" / "registry"))

    spark.stop()


if __name__ == "__main__":
    main()

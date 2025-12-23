package omphalos.spark

import org.apache.spark.sql.{SparkSession, DataFrame}
import org.apache.spark.sql.functions._

object Jobs {
  def ingestTradeFeed(spark: SparkSession, cfg: Config): DataFrame = {
    val df = spark.read.schema(Schemas.tradeFeed).option("header", "true").csv(cfg.inputCsv)
    val staged = Transforms.coalesceCountries(Transforms.deriveTemporal(Transforms.deriveHsSlices(Transforms.normalizeNames(df))))
    staged
  }

  def writeParquet(df: DataFrame, out: String): Unit =
    df.write.mode("overwrite").parquet(out)

  def computeMonthlyAgg(df: DataFrame): DataFrame =
    df.groupBy(col("ship_month"), col("exporter_country"), col("importer_country"), col("hs2"))
      .agg(
        count(lit(1)).as("shipment_count"),
        sum(col("value_usd")).as("total_value_usd"),
        avg(col("value_usd")).as("mean_value_usd")
      )
}

package omphalos.spark

import org.apache.spark.sql.{DataFrame, Column}
import org.apache.spark.sql.functions._

object Transforms {
  def normalizeNames(df: DataFrame): DataFrame =
    df.withColumn("exporter_name", upper(trim(col("exporter_name"))))
      .withColumn("importer_name", upper(trim(col("importer_name"))))

  def deriveHsSlices(df: DataFrame): DataFrame =
    df.withColumn("hs2", substring(col("hs_code"), 1, 2))
      .withColumn("hs4", substring(col("hs_code"), 1, 4))
      .withColumn("hs6", substring(col("hs_code"), 1, 6))

  def deriveTemporal(df: DataFrame): DataFrame =
    df.withColumn("ship_month", substring(col("ship_date"), 1, 7))
      .withColumn("ship_year", substring(col("ship_date"), 1, 4))

  def coalesceCountries(df: DataFrame): DataFrame =
    df.withColumn("exporter_country", coalesce(col("exporter_country"), col("country")))
      .withColumn("importer_country", coalesce(col("importer_country"), col("country")))
}

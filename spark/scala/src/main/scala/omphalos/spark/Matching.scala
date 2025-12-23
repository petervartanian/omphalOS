package omphalos.spark

import org.apache.spark.sql.{DataFrame, Column}
import org.apache.spark.sql.functions._

object Matching {
  def exactNameMatch(trade: DataFrame, registry: DataFrame): DataFrame = {
    val t = trade.select(col("shipment_id"), col("exporter_name"), col("importer_name"), col("value_usd"), col("ship_date"))
    val r = registry.select(col("entity_id"), upper(trim(col("entity_name"))).as("entity_name"), upper(trim(col("country"))).as("country"))
    val exporterHits = t.join(r, t.col("exporter_name") === r.col("entity_name"))
      .select(t.col("shipment_id"), r.col("entity_id"), lit(1.0).as("score"), lit("MATCH").as("status"), lit("EXACT_NAME_EXPORTER").as("explanation"))
    val importerHits = t.join(r, t.col("importer_name") === r.col("entity_name"))
      .select(t.col("shipment_id"), r.col("entity_id"), lit(1.0).as("score"), lit("MATCH").as("status"), lit("EXACT_NAME_IMPORTER").as("explanation"))
    exporterHits.unionByName(importerHits).dropDuplicates("shipment_id", "entity_id")
  }

  def scoreToTier(score: Column): Column =
    when(score >= 0.95, lit("A"))
      .when(score >= 0.85, lit("B"))
      .when(score >= 0.70, lit("C"))
      .otherwise(lit("D"))
}

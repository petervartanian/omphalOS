package omphalos.spark

import org.apache.spark.sql.{DataFrame, Row}
import org.apache.spark.sql.functions._

final case class QualityReport(
  tradeRows: Long,
  nullExporterName: Long,
  nullImporterName: Long,
  nullHsCode: Long,
  nullShipDate: Long,
  nonPositiveValue: Long,
  distinctShipments: Long
)

object Quality {
  def report(df: DataFrame): QualityReport = {
    val tradeRows = df.count()
    val nullExporterName = df.filter(col("exporter_name").isNull || length(trim(col("exporter_name"))) === 0).count()
    val nullImporterName = df.filter(col("importer_name").isNull || length(trim(col("importer_name"))) === 0).count()
    val nullHsCode = df.filter(col("hs_code").isNull || length(trim(col("hs_code"))) < 6).count()
    val nullShipDate = df.filter(col("ship_date").isNull || length(trim(col("ship_date"))) < 10).count()
    val nonPositiveValue = df.filter(col("value_usd") <= 0.0).count()
    val distinctShipments = df.select(col("shipment_id")).distinct().count()
    QualityReport(
      tradeRows = tradeRows,
      nullExporterName = nullExporterName,
      nullImporterName = nullImporterName,
      nullHsCode = nullHsCode,
      nullShipDate = nullShipDate,
      nonPositiveValue = nonPositiveValue,
      distinctShipments = distinctShipments
    )
  }

  def render(report: QualityReport): String = {
    val rows = Seq(
      ("trade_rows", report.tradeRows.toString),
      ("distinct_shipments", report.distinctShipments.toString),
      ("null_exporter_name", report.nullExporterName.toString),
      ("null_importer_name", report.nullImporterName.toString),
      ("null_hs_code", report.nullHsCode.toString),
      ("null_ship_date", report.nullShipDate.toString),
      ("non_positive_value", report.nonPositiveValue.toString)
    )
    rows.map { case (k, v) => s"$k=$v" }.mkString("\n")
  }
}

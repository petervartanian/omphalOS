package omphalos.spark

import org.apache.spark.sql.types._

object Schemas {
  val tradeFeed: StructType = StructType(Seq(
    StructField("shipment_id", StringType, nullable = false),
    StructField("exporter_name", StringType, nullable = false),
    StructField("importer_name", StringType, nullable = false),
    StructField("exporter_country", StringType, nullable = true),
    StructField("importer_country", StringType, nullable = true),
    StructField("country", StringType, nullable = true),
    StructField("hs_code", StringType, nullable = false),
    StructField("value_usd", DoubleType, nullable = false),
    StructField("ship_date", StringType, nullable = false)
  ))
}

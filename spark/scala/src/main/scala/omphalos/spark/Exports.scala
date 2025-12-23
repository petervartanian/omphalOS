package omphalos.spark

import org.apache.spark.sql.{DataFrame, SaveMode}
import org.apache.spark.sql.functions._
import java.nio.file.{Files, Paths}

object Exports {
  def writeCsv(df: DataFrame, out: String): Unit =
    df.coalesce(1).write.mode(SaveMode.Overwrite).option("header", "true").csv(out)

  def writeJsonLines(df: DataFrame, out: String): Unit =
    df.write.mode(SaveMode.Overwrite).json(out)

  def writeEntitySlice(df: DataFrame, entityId: String, out: String): Unit = {
    val slice = df.filter(col("entity_id") === lit(entityId))
    writeParquet(slice, out)
  }

  def writeParquet(df: DataFrame, out: String): Unit =
    df.write.mode(SaveMode.Overwrite).parquet(out)

  def ensureDir(path: String): Unit = {
    val p = Paths.get(path)
    if (!Files.exists(p)) Files.createDirectories(p)
  }
}

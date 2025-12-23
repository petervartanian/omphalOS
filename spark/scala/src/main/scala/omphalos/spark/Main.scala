package omphalos.spark

import org.apache.spark.sql.SparkSession

object Main {
  def main(args: Array[String]): Unit = {
    val parser = new scopt.OptionParser[Config]("omphalos-spark") {
      opt[String]("input").required().action((v, c) => c.copy(inputCsv = v))
      opt[String]("out").required().action((v, c) => c.copy(outputDir = v))
      opt[String]("run-id").required().action((v, c) => c.copy(runId = v))
      opt[String]("mode").optional().action((v, c) => c.copy(mode = v))
    }
    parser.parse(args, Config()).foreach { cfg =>
      val spark = SparkSession.builder().appName("omphalos-spark").getOrCreate()
      try {
        val staged = Jobs.ingestTradeFeed(spark, cfg)
        Jobs.writeParquet(staged, s"${cfg.outputDir}/runs/${cfg.runId}/spark/staged_trade_feed")
        val monthly = Jobs.computeMonthlyAgg(staged)
        Jobs.writeParquet(monthly, s"${cfg.outputDir}/runs/${cfg.runId}/spark/monthly_agg")
      } finally {
        spark.stop()
      }
    }
  }
}

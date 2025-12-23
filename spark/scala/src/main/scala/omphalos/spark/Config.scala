package omphalos.spark

final case class Config(
  inputCsv: String = "",
  outputDir: String = "",
  runId: String = "",
  mode: String = "ingest"
)

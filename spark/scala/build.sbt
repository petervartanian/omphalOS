ThisBuild / scalaVersion := "2.13.14"

lazy val root = (project in file("."))
  .settings(
    name := "omphalos-spark",
    version := "0.1.0",
    libraryDependencies ++= Seq(
      "org.apache.spark" %% "spark-sql" % "3.5.2" % "provided",
      "com.github.scopt" %% "scopt" % "4.1.0"
    )
  )

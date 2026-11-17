from __future__ import annotations

import common
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F


def _daily_frame(df: DataFrame, windows: list[int]) -> DataFrame:
    dated = common.actions_with_date(df).filter(F.col("date").isNotNull())
    daily = (
        common.plays_only(dated)
        .groupBy("date")
        .agg(F.count("*").alias("plays"))
        .orderBy("date")
    )

    window = Window.orderBy("date")
    for lag in windows:
        daily = daily.withColumn(f"lag_{lag}", F.lag("plays", lag).over(window))
    for size in windows:
        daily = daily.withColumn(
            f"rolling_mean_{size}",
            # 只使用当日之前的 size 天，避免把目标值本身泄漏进特征
            F.avg("plays").over(window.rowsBetween(-size, -1)),
        )
    return (
        daily.withColumn("day_of_week", F.dayofweek("date"))
        .withColumn("month", F.month("date"))
        .orderBy("date")
    )


def _hourly_frame(df: DataFrame) -> DataFrame:
    stamped = df.withColumn(
        "ts", F.to_timestamp(F.from_unixtime(F.col("gmt_create")))
    )
    return (
        common.plays_only(stamped)
        .groupBy(F.to_date("ts").alias("date"), F.hour("ts").alias("hour"))
        .agg(F.count("*").alias("plays"))
        .orderBy("date", "hour")
    )


def _weekly_frame(df: DataFrame) -> DataFrame:
    dated = common.actions_with_date(df).filter(F.col("date").isNotNull())
    return (
        common.plays_only(dated)
        .withColumn("day_of_week", F.dayofweek("date"))
        .groupBy("day_of_week")
        .agg(
            F.count("*").alias("plays"),
            F.countDistinct("date").alias("days"),
        )
        .withColumn("plays_per_day", F.col("plays") / F.col("days"))
        .orderBy("day_of_week")
    )


def main() -> None:
    args, result_path = common.parse_args()
    spark = common.build_session("build_time_features")
    df = common.read_dataset(spark, args["path"], args["spec"])

    granularity = args["granularity"]
    windows = sorted({int(item) for item in args.get("windows", []) if int(item) > 0})

    if granularity == "day":
        frame = _daily_frame(df, windows)
    elif granularity == "hour":
        frame = _hourly_frame(df)
    elif granularity == "day_of_week":
        frame = _weekly_frame(df)
    else:
        raise ValueError(f"不支持的时间粒度: {granularity}")

    output_path = args.get("output_path")
    if granularity == "day" and output_path:
        frame.write.mode("overwrite").parquet(output_path)

    preview = common.rows_as_dicts(frame, limit=50)
    date_range = None
    if "date" in frame.columns:
        range_row = frame.agg(F.min("date").alias("start"), F.max("date").alias("end")).first()
        if range_row and range_row["start"] is not None:
            date_range = {"start": str(range_row["start"]), "end": str(range_row["end"])}

    payload = {
        "granularity": granularity,
        "columns": frame.columns,
        "windows": windows,
        "row_count": frame.count(),
        "date_range": date_range,
        "preview": preview,
        "output_path": output_path,
    }
    common.write_result(result_path, payload)
    spark.stop()


if __name__ == "__main__":
    main()

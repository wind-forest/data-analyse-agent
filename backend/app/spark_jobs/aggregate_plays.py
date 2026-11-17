from __future__ import annotations

import common
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

ACTION_BY_METRIC = {
    "plays": 1,
    "downloads": 2,
    "favorites": 3,
}

SONG_DIMENSIONS = {"artist_id", "Language", "Gender"}


def _prepare(
    df: DataFrame, group_by: list[str], songs_path: str | None, spark
) -> DataFrame:
    base = df
    if SONG_DIMENSIONS & set(group_by):
        if not songs_path:
            raise ValueError("按艺人/语言/性别聚合需要同时上传歌曲信息表")
        songs = (
            spark.read.csv(songs_path, schema=common.SONGS_SCHEMA, header=False)
            .select("song_id", "artist_id", "Language", "Gender")
            .dropDuplicates(["song_id"])
        )
        base = base.join(songs, on="song_id", how="left")
        base = base.withColumn(
            "artist_id", F.coalesce(F.col("artist_id"), F.lit("unknown_artist"))
        )

    if "date" in group_by:
        base = base.withColumn("date", F.to_date(F.col("Ds"), "yyyyMMdd"))
    if "hour" in group_by:
        base = base.withColumn(
            "hour", F.hour(F.to_timestamp(F.from_unixtime(F.col("gmt_create"))))
        )
    if "day_of_week" in group_by:
        base = base.withColumn(
            "day_of_week", F.dayofweek(F.to_date(F.col("Ds"), "yyyyMMdd"))
        )
    return base


def _apply_filters(df: DataFrame, filters: list[dict]) -> DataFrame:
    for item in filters:
        column = item["column"]
        op = item["op"]
        value = item.get("value")
        if op == "eq":
            df = df.filter(F.col(column) == value)
        elif op == "ne":
            df = df.filter(F.col(column) != value)
        elif op == "gte":
            df = df.filter(F.col(column) >= value)
        elif op == "lte":
            df = df.filter(F.col(column) <= value)
        elif op == "in":
            df = df.filter(F.col(column).isin(value))
        elif op == "between":
            df = df.filter(F.col(column).between(value[0], value[1]))
        else:
            raise ValueError(f"不支持的过滤操作符: {op}")
    return df


def main() -> None:
    args, result_path = common.parse_args()
    spark = common.build_session("aggregate_plays")
    df = common.read_dataset(spark, args["path"], args["spec"])

    if args["spec"]["kind"] != "actions" and "action_type" not in df.columns:
        raise ValueError("aggregate_plays 需要用户行为表")

    group_by = args["group_by"]
    metric = args["metric"]
    base = _prepare(df, group_by, args.get("songs_path"), spark)
    base = _apply_filters(base, args.get("filters", []))

    time_range = args.get("time_range")
    if time_range:
        base = base.filter(
            F.col("date").between(time_range["start"], time_range["end"])
        )

    if metric == "active_users":
        value_expr = F.countDistinct("user_id").alias("value")
    else:
        action = ACTION_BY_METRIC.get(metric)
        if action is None:
            raise ValueError(f"不支持的指标: {metric}")
        base = base.filter(F.col("action_type") == action)
        value_expr = F.count("*").alias("value")

    grouped = base.groupBy(*group_by).agg(value_expr).filter(F.col("value") > 0)

    chronological = any(item in group_by for item in ("date", "hour", "day_of_week"))
    if chronological:
        result = grouped.orderBy(*[F.col(name).asc() for name in group_by])
    else:
        result = grouped.orderBy(F.col("value").desc()).limit(int(args["top_n"]))

    rows = common.rows_as_dicts(result, limit=5000)
    payload = {
        "metric": metric,
        "group_by": group_by,
        "columns": [*group_by, "value"],
        "rows": rows,
        "row_count": len(rows),
        "chronological": chronological,
        "has_songs_join": bool(SONG_DIMENSIONS & set(group_by)),
    }
    common.write_result(result_path, payload)
    spark.stop()


if __name__ == "__main__":
    main()

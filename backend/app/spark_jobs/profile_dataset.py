from __future__ import annotations

import common
from pyspark.sql import functions as F


def main() -> None:
    args, result_path = common.parse_args()
    spark = common.build_session("profile_dataset")
    df = common.read_dataset(spark, args["path"], args["spec"])
    df.cache()

    total = df.count()
    fields = df.schema.fields

    null_exprs = [
        F.sum(F.when(F.col(field.name).isNull(), 1).otherwise(0)).alias(f"n_{index}")
        for index, field in enumerate(fields)
    ]
    null_row = df.agg(*null_exprs).first() if fields else None

    distinct_exprs = [
        F.approx_count_distinct(F.col(field.name)).alias(f"d_{index}")
        for index, field in enumerate(fields)
    ]
    distinct_row = df.agg(*distinct_exprs).first() if fields else None

    columns = []
    for index, field in enumerate(fields):
        null_count = int(null_row[f"n_{index}"] or 0) if null_row else 0
        columns.append(
            {
                "name": field.name,
                "dtype": field.dataType.simpleString(),
                "null_count": null_count,
                "null_rate": round(null_count / total, 6) if total else 0.0,
                "approx_distinct": int(distinct_row[f"d_{index}"])
                if distinct_row
                else 0,
            }
        )

    numeric_types = {"int", "bigint", "smallint", "double", "float", "decimal"}
    numeric_names = [
        field.name
        for field in fields
        if field.dataType.simpleString() in numeric_types
    ]
    numeric_stats: dict[str, dict[str, float | None]] = {}
    if numeric_names:
        exprs = []
        for name in numeric_names:
            exprs.extend(
                [
                    F.min(name).alias(f"{name}_min"),
                    F.max(name).alias(f"{name}_max"),
                    F.avg(name).alias(f"{name}_mean"),
                    F.stddev(name).alias(f"{name}_std"),
                ]
            )
        stats_row = df.agg(*exprs).first()
        for name in numeric_names:
            numeric_stats[name] = {
                "min": stats_row[f"{name}_min"],
                "max": stats_row[f"{name}_max"],
                "mean": stats_row[f"{name}_mean"],
                "std": stats_row[f"{name}_std"],
            }

    action_counts: dict[str, int] = {}
    if "action_type" in df.columns:
        for row in df.groupBy("action_type").count().orderBy("action_type").collect():
            action_counts[str(row["action_type"])] = int(row["count"])

    date_range = None
    invalid_date_rows = None
    if "Ds" in df.columns:
        dated = df.withColumn("date", F.to_date(F.col("Ds"), "yyyyMMdd"))
        range_row = dated.agg(
            F.min("date").alias("start"), F.max("date").alias("end")
        ).first()
        invalid_date_rows = int(
            dated.filter(F.col("date").isNull()).count()
        )
        if range_row and range_row["start"] is not None:
            date_range = {
                "start": str(range_row["start"]),
                "end": str(range_row["end"]),
            }

    sample_rows = common.rows_as_dicts(df, limit=20)

    payload = {
        "dataset_kind": args["spec"]["kind"],
        "row_count": total,
        "column_count": len(fields),
        "columns": columns,
        "numeric_stats": numeric_stats,
        "action_type_counts": action_counts,
        "date_range": date_range,
        "invalid_date_rows": invalid_date_rows,
        "sample_rows": sample_rows,
    }
    common.write_result(result_path, payload)
    spark.stop()


if __name__ == "__main__":
    main()

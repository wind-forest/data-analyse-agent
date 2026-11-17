from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import LongType, StringType, StructField, StructType

ACTIONS_SCHEMA = StructType(
    [
        StructField("user_id", StringType(), True),
        StructField("song_id", StringType(), True),
        StructField("gmt_create", LongType(), True),
        StructField("action_type", StringType(), True),
        StructField("Ds", StringType(), True),
    ]
)

SONGS_SCHEMA = StructType(
    [
        StructField("song_id", StringType(), True),
        StructField("artist_id", StringType(), True),
        StructField("publish_time", StringType(), True),
        StructField("song_init_plays", LongType(), True),
        StructField("Language", StringType(), True),
        StructField("Gender", StringType(), True),
    ]
)


def parse_args() -> tuple[dict[str, Any], Path]:
    if len(sys.argv) != 3:
        raise SystemExit("usage: job.py <args.json> <result.json>")
    args_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])
    payload = json.loads(args_path.read_text(encoding="utf-8"))
    return payload, result_path


def build_session(app_name: str) -> SparkSession:
    spark = SparkSession.builder.appName(app_name).getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def read_dataset(spark: SparkSession, path: str, spec: dict[str, Any]) -> DataFrame:
    kind = spec["kind"]
    if kind == "actions":
        df = spark.read.csv(path, schema=ACTIONS_SCHEMA, header=False)
        return df.withColumn("action_type", F.col("action_type").cast("int"))
    if kind == "songs":
        return spark.read.csv(path, schema=SONGS_SCHEMA, header=False)
    return spark.read.csv(
        path,
        header=bool(spec.get("has_header", True)),
        inferSchema=True,
    )


def write_result(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8"
    )


def has_columns(df: DataFrame, columns: list[str]) -> bool:
    available = set(df.columns)
    return all(column in available for column in columns)


def actions_with_date(df: DataFrame) -> DataFrame:
    return df.withColumn("date", F.to_date(F.col("Ds"), "yyyyMMdd"))


def plays_only(df: DataFrame) -> DataFrame:
    return df.filter(F.col("action_type") == 1)


def rows_as_dicts(df: DataFrame, limit: int = 200) -> list[dict[str, Any]]:
    return [row.asDict(recursive=True) for row in df.limit(limit).collect()]

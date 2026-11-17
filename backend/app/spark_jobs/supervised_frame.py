from __future__ import annotations

import common
from pyspark.sql import functions as F


def main() -> None:
    args, result_path = common.parse_args()
    spark = common.build_session("supervised_frame")
    df = common.read_dataset(spark, args["path"], args["spec"])

    target = args["target"]
    if target not in df.columns:
        raise ValueError(f"目标列不存在: {target}")

    limit = int(args.get("limit", 200_000))
    selected = df.filter(F.col(target).isNotNull()).limit(limit)

    output_path = args["output_path"]
    selected.write.mode("overwrite").parquet(output_path)

    payload = {
        "target": target,
        "columns": selected.columns,
        "row_count": selected.count(),
        "output_path": output_path,
    }
    common.write_result(result_path, payload)
    spark.stop()


if __name__ == "__main__":
    main()

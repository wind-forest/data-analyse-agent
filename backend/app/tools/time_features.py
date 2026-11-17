from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.errors import AppError
from app.services import artifact_service, dataset_service, run_service, storage
from app.services.spark_runner import run_job
from app.tools.base import ToolContext, ToolResult

TIME_FEATURE_TIMEOUT_SECONDS = 180
DEFAULT_WINDOWS = [1, 7, 14, 28]


class TimeFeatureArgs(BaseModel):
    file_id: uuid.UUID
    granularity: Literal["day", "hour", "day_of_week"] = "day"
    windows: list[int] = Field(default_factory=lambda: list(DEFAULT_WINDOWS))

    @field_validator("windows")
    @classmethod
    def _validate_windows(cls, value: list[int]) -> list[int]:
        cleaned = sorted({int(item) for item in value})
        if not cleaned:
            raise ValueError("windows 不能为空")
        if cleaned[0] <= 0 or cleaned[-1] > 60:
            raise ValueError("windows 必须在 1~60 之间")
        return cleaned


def _summary(payload: dict) -> str:
    text = f"{payload['granularity']} 粒度共 {payload['row_count']} 行"
    if payload.get("date_range"):
        rng = payload["date_range"]
        text += f"，日期范围 {rng['start']} ~ {rng['end']}"
    preview = payload.get("preview") or []
    if preview:
        last = preview[-1]
        text += f"；最新一行: {last}"
    return text


async def build_time_features(args: TimeFeatureArgs, ctx: ToolContext) -> ToolResult:
    dataset = await dataset_service.resolve_dataset(
        ctx.db, ctx.session_id, args.file_id
    )
    if dataset.spec.kind != "actions":
        raise AppError("INVALID_FILE", "时间特征需要用户行为表", 400)

    run = await run_service.start_run(
        ctx.db,
        ctx.session_id,
        "build_time_features",
        args.model_dump(mode="json"),
        file_id=args.file_id,
    )

    try:
        work = storage.work_dir(ctx.session_id, run.id)
        parquet_path = work / "time_features" if args.granularity == "day" else None
        payload = await run_job(
            "build_time_features",
            {
                "path": str(dataset.path),
                "spec": dataset.spec.to_dict(),
                "granularity": args.granularity,
                "windows": args.windows,
                "output_path": str(parquet_path) if parquet_path else None,
            },
            work,
            TIME_FEATURE_TIMEOUT_SECONDS,
        )
        artifact_payload = {
            **payload,
            "file_id": str(args.file_id),
            "parquet_path": str(parquet_path) if parquet_path else None,
        }
        artifact = await artifact_service.create_artifact(
            ctx.db, run.id, "table", artifact_payload
        )
        await run_service.finish_run(ctx.db, run, result_path=str(work))
    except AppError as exc:
        await run_service.finish_run(ctx.db, run, status="failed", error=exc.message)
        raise

    return ToolResult(
        run_id=run.id,
        summary=_summary(payload),
        artifact_ids=[artifact.id],
        data={
            "granularity": args.granularity,
            "row_count": payload["row_count"],
            "date_range": payload.get("date_range"),
        },
    )

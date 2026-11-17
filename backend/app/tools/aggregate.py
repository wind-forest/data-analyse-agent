from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.errors import AppError
from app.services import artifact_service, dataset_service, run_service, storage
from app.services.spark_runner import run_job
from app.tools.base import ToolContext, ToolResult

AGGREGATE_TIMEOUT_SECONDS = 120

GroupBy = Literal[
    "artist_id",
    "song_id",
    "user_id",
    "date",
    "hour",
    "day_of_week",
    "action_type",
    "Language",
    "Gender",
]
Metric = Literal["plays", "downloads", "favorites", "active_users"]
FilterOp = Literal["eq", "ne", "gte", "lte", "in", "between"]
SONG_DIMENSIONS = {"artist_id", "Language", "Gender"}


class FilterSpec(BaseModel):
    column: GroupBy
    op: FilterOp
    value: Any


class TimeRange(BaseModel):
    start: date
    end: date


class AggregateArgs(BaseModel):
    file_id: uuid.UUID
    group_by: list[GroupBy] = Field(min_length=1, max_length=3)
    metric: Metric = "plays"
    filters: list[FilterSpec] = Field(default_factory=list, max_length=10)
    time_range: TimeRange | None = None
    top_n: int = Field(default=10, ge=1, le=100)

    @field_validator("group_by")
    @classmethod
    def _unique_group_by(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("group_by 不允许重复字段")
        return value


def _summary(payload: dict, args: AggregateArgs) -> str:
    rows = payload["rows"]
    head = f"按 {'、'.join(args.group_by)} 统计 {args.metric}，共 {payload['row_count']} 组"
    if not rows:
        return head + "；没有匹配数据"
    top = rows[:3]
    preview = "、".join(
        f"{' / '.join(str(row.get(key)) for key in args.group_by)}={row['value']}"
        for row in top
    )
    return f"{head}；前 {len(top)} 项: {preview}"


async def aggregate_plays(args: AggregateArgs, ctx: ToolContext) -> ToolResult:
    dataset = await dataset_service.resolve_dataset(
        ctx.db, ctx.session_id, args.file_id
    )
    if dataset.spec.kind != "actions":
        raise AppError("INVALID_FILE", "aggregate_plays 需要用户行为表", 400)

    songs_path = None
    if SONG_DIMENSIONS & set(args.group_by):
        songs = await dataset_service.find_songs_dataset(ctx.db, ctx.session_id)
        if songs is None:
            raise AppError(
                "SONGS_FILE_REQUIRED",
                "按艺人/语言/性别聚合需要先上传歌曲信息表",
                400,
            )
        songs_path = str(songs.path)

    run = await run_service.start_run(
        ctx.db,
        ctx.session_id,
        "aggregate_plays",
        args.model_dump(mode="json"),
        file_id=args.file_id,
    )

    try:
        work = storage.work_dir(ctx.session_id, run.id)
        payload = await run_job(
            "aggregate_plays",
            {
                "path": str(dataset.path),
                "spec": dataset.spec.to_dict(),
                "group_by": list(args.group_by),
                "metric": args.metric,
                "filters": [item.model_dump() for item in args.filters],
                "time_range": args.time_range.model_dump(mode="json")
                if args.time_range
                else None,
                "top_n": args.top_n,
                "songs_path": songs_path,
            },
            work,
            AGGREGATE_TIMEOUT_SECONDS,
        )
        artifact = await artifact_service.create_artifact(
            ctx.db, run.id, "table", payload
        )
        await run_service.finish_run(ctx.db, run, result_path=str(work))
    except AppError as exc:
        await run_service.finish_run(ctx.db, run, status="failed", error=exc.message)
        raise

    return ToolResult(
        run_id=run.id,
        summary=_summary(payload, args),
        artifact_ids=[artifact.id],
        data={
            "metric": args.metric,
            "group_by": list(args.group_by),
            "row_count": payload["row_count"],
        },
    )

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.errors import AppError
from app.services import artifact_service, dataset_service, run_service, storage
from app.services.spark_runner import run_job
from app.tools.base import ToolContext, ToolResult

PROFILE_TIMEOUT_SECONDS = 120


class ProfileArgs(BaseModel):
    file_id: uuid.UUID


def _summary(payload: dict) -> str:
    parts = [
        f"共 {payload['row_count']:,} 行、{payload['column_count']} 列",
        f"字段: {', '.join(item['name'] for item in payload['columns'][:12])}",
    ]
    if payload.get("action_type_counts"):
        counts = payload["action_type_counts"]
        parts.append(
            "行为分布: " + "、".join(f"type={key} {value:,}" for key, value in counts.items())
        )
    if payload.get("date_range"):
        date_range = payload["date_range"]
        parts.append(f"日期范围: {date_range['start']} ~ {date_range['end']}")
    if payload.get("invalid_date_rows"):
        parts.append(f"非法日期行: {payload['invalid_date_rows']:,}")
    return "；".join(parts)


async def profile_dataset(args: ProfileArgs, ctx: ToolContext) -> ToolResult:
    dataset = await dataset_service.resolve_dataset(
        ctx.db, ctx.session_id, args.file_id
    )
    run = await run_service.start_run(
        ctx.db,
        ctx.session_id,
        "profile_dataset",
        args.model_dump(mode="json"),
        file_id=args.file_id,
    )

    try:
        work = storage.work_dir(ctx.session_id, run.id)
        payload = await run_job(
            "profile_dataset",
            {"path": str(dataset.path), "spec": dataset.spec.to_dict()},
            work,
            PROFILE_TIMEOUT_SECONDS,
        )
        artifact = await artifact_service.create_artifact(
            ctx.db, run.id, "table", payload
        )
        await run_service.finish_run(ctx.db, run, result_path=str(work))
    except AppError as exc:
        await run_service.finish_run(
            ctx.db, run, status="failed", error=exc.message
        )
        raise

    return ToolResult(
        run_id=run.id,
        summary=_summary(payload),
        artifact_ids=[artifact.id],
        data={
            "row_count": payload["row_count"],
            "column_count": payload["column_count"],
            "dataset_kind": payload["dataset_kind"],
            "date_range": payload.get("date_range"),
        },
    )

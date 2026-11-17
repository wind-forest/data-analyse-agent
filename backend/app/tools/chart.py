from __future__ import annotations

import uuid
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel

from app.errors import AppError
from app.services import artifact_service, run_service
from app.tools.base import ToolContext, ToolResult

MAX_CHART_POINTS = 5000


class ChartArgs(BaseModel):
    chart_type: Literal["bar", "line", "scatter"]
    source_ref: uuid.UUID
    x: str
    y: str
    series: str | None = None
    agg: Literal["none", "sum", "mean", "count"] = "none"


def _build_chart(
    frame: pd.DataFrame, args: ChartArgs
) -> tuple[dict[str, Any], dict[str, Any]]:
    agg_map = {"sum": "sum", "mean": "mean", "count": "count"}
    truncated = False

    if args.series:
        aggregator = agg_map[args.agg] if args.agg != "none" else "sum"
        pivot = frame.pivot_table(
            index=args.x,
            columns=args.series,
            values=args.y,
            aggfunc=aggregator,
        ).fillna(0)
        if args.chart_type != "bar":
            pivot = pivot.sort_index()
        if len(pivot.index) > MAX_CHART_POINTS:
            pivot = pivot.iloc[:MAX_CHART_POINTS]
            truncated = True
        labels = [str(value) for value in pivot.index]
        series_payload = [
            {
                "name": str(column),
                "data": [
                    round(float(value), 4) if pd.notna(value) else 0.0
                    for value in pivot[column]
                ],
            }
            for column in pivot.columns
        ]
    else:
        if args.agg != "none" and frame[args.x].duplicated().any():
            working = frame.groupby(args.x, as_index=False)[args.y].agg(
                agg_map[args.agg]
            )
        else:
            working = frame[[args.x, args.y]].copy()

        if args.chart_type in ("line", "scatter"):
            working = working.sort_values(args.x)
        if len(working) > MAX_CHART_POINTS:
            working = working.iloc[:MAX_CHART_POINTS]
            truncated = True

        values = pd.to_numeric(working[args.y], errors="coerce").fillna(0.0)
        labels = [str(value) for value in working[args.x]]
        series_payload = [
            {"name": args.y, "data": [round(float(value), 4) for value in values]}
        ]

    data = {"x": labels, "series": series_payload}
    meta = {
        "points": len(labels),
        "aggregated": args.agg != "none",
        "truncated": truncated,
        "source_ref": str(args.source_ref),
    }
    return data, meta


async def generate_chart_data(args: ChartArgs, ctx: ToolContext) -> ToolResult:
    source = await artifact_service.get_session_artifact(
        ctx.db, ctx.session_id, args.source_ref
    )
    if source.type != "table":
        raise AppError("INVALID_ARTIFACT", "图表数据来源必须是 table 类型产物", 400)

    payload = source.payload_json or {}
    rows = payload.get("rows") or []
    if not rows:
        raise AppError("EMPTY_DATASET", "来源产物没有可用数据", 400)

    frame = pd.DataFrame(rows)
    for field in (args.x, args.y, args.series):
        if field and field not in frame.columns:
            raise AppError(
                "INVALID_ARGUMENT",
                f"字段 {field} 不在来源数据中，可选字段: {', '.join(frame.columns)}",
                400,
            )

    data, meta = _build_chart(frame, args)

    run = await run_service.start_run(
        ctx.db,
        ctx.session_id,
        "generate_chart_data",
        args.model_dump(mode="json"),
    )
    chart_payload = {
        "chart_type": args.chart_type,
        "x": args.x,
        "y": args.y,
        "series": args.series,
        "data": data,
        "meta": meta,
    }
    artifact = await artifact_service.create_artifact(
        ctx.db, run.id, "chart", chart_payload
    )
    await run_service.finish_run(ctx.db, run)

    return ToolResult(
        run_id=run.id,
        summary=f"已生成 {args.chart_type} 图，共 {meta['points']} 个数据点",
        artifact_ids=[artifact.id],
        data={"chart_id": str(artifact.id), "points": meta["points"]},
    )

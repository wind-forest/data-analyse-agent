from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.errors import AppError
from app.services import artifact_service, run_service
from app.tools.base import ToolContext, ToolResult


class EvaluateArgs(BaseModel):
    model_id: uuid.UUID


async def evaluate_model(args: EvaluateArgs, ctx: ToolContext) -> ToolResult:
    artifact = await artifact_service.get_session_artifact(
        ctx.db, ctx.session_id, args.model_id
    )
    if artifact.type != "model":
        raise AppError("INVALID_ARTIFACT", "指定的产物不是模型", 400)

    payload = artifact.payload_json or {}
    metrics = payload.get("metrics") or {}

    run = await run_service.start_run(
        ctx.db,
        ctx.session_id,
        "evaluate_model",
        args.model_dump(mode="json"),
    )
    await run_service.finish_run(ctx.db, run)

    task = payload.get("task")
    if task == "regression":
        summary = (
            f"回归评估（{payload.get('model_family')}）：MAE={metrics.get('mae')}、"
            f"RMSE={metrics.get('rmse')}，验证样本 {payload.get('sample_size')}"
        )
    else:
        summary = (
            f"分类评估（{payload.get('model_family')}）：accuracy={metrics.get('accuracy')}、"
            f"macro_f1={metrics.get('macro_f1')}，验证样本 {payload.get('sample_size')}"
        )

    return ToolResult(
        run_id=run.id,
        summary=summary,
        artifact_ids=[artifact.id],
        data={
            "model_id": str(artifact.id),
            "task": task,
            "target": payload.get("target"),
            "metrics": metrics,
            "folds": payload.get("folds"),
            "sample_size": payload.get("sample_size"),
            "feature_importance": payload.get("feature_importance"),
            "confusion_matrix": payload.get("confusion_matrix"),
            "forecast": payload.get("forecast"),
        },
    )

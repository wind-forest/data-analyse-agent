from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.errors import AppError
from app.sandbox import manager as sandbox_manager
from app.sandbox.validator import validate_code
from app.services import (
    artifact_service,
    dataset_service,
    run_service,
    storage,
)
from app.services.dataset_schema import detect_dataset
from app.tools.base import ToolContext, ToolResult

MAX_OUTPUT_CHARS = 8000


class SnippetArgs(BaseModel):
    code: str = Field(min_length=1, max_length=8000)
    file_id: uuid.UUID | None = None
    purpose: str = Field(default="", max_length=200)


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_OUTPUT_CHARS else text[-MAX_OUTPUT_CHARS:]


async def execute_python_snippet(args: SnippetArgs, ctx: ToolContext) -> ToolResult:
    validate_code(args.code)
    if not sandbox_manager.is_available():
        raise AppError(
            "SANDBOX_UNAVAILABLE",
            f"安全沙箱不可用：{sandbox_manager.unavailable_reason()}",
            503,
        )

    if ctx.run_id is not None:
        run = await run_service.get_run(ctx.db, ctx.run_id)
        run.status = "running"
        run.started_at = run.started_at or datetime.now(UTC)
        await ctx.db.commit()
    else:
        run = await run_service.start_run(
            ctx.db,
            ctx.session_id,
            "execute_python_snippet",
            args.model_dump(mode="json"),
            file_id=args.file_id,
            message_id=ctx.message_id,
        )

    work = storage.work_dir(ctx.session_id, run.id) / "sandbox"
    artifacts_dir = storage.artifact_dir(ctx.session_id, run.id) / "sandbox"
    work.mkdir(parents=True, exist_ok=True)

    input_note = ""
    if args.file_id is not None:
        dataset = await dataset_service.resolve_dataset(
            ctx.db, ctx.session_id, args.file_id
        )
        target = work / "input.csv"
        shutil.copy2(dataset.path, target)
        target.chmod(0o644)
        input_note = f"；输入文件已复制为 input.csv（kind={detect_dataset(target).kind}）"

    try:
        result = await sandbox_manager.run_snippet(args.code, work, artifacts_dir)
    except Exception as exc:
        await run_service.finish_run(
            ctx.db, run, status="failed", error=f"沙箱执行异常: {type(exc).__name__}"
        )
        raise AppError("SANDBOX_ERROR", "沙箱执行失败", 500) from exc

    payload = {
        "status": result.status,
        "exit_code": result.exit_code,
        "stdout": _truncate(result.stdout),
        "stderr": _truncate(result.stderr),
        "duration_ms": result.duration_ms,
        "artifacts": result.artifacts,
        "purpose": args.purpose,
        "code": args.code,
    }
    artifact = await artifact_service.create_artifact(
        ctx.db, run.id, "table", payload
    )
    await run_service.finish_run(
        ctx.db,
        run,
        status="success" if result.status == "success" else "failed",
        error=None if result.status == "success" else f"沙箱状态: {result.status}",
    )

    if result.status == "timeout":
        summary = f"沙箱执行超时（{result.duration_ms} ms），已强制终止"
    elif result.status == "success":
        files = "、".join(str(item["name"]) for item in result.artifacts) or "无"
        summary = f"沙箱执行成功，用时 {result.duration_ms} ms，产出文件: {files}{input_note}"
    else:
        summary = f"沙箱执行失败（退出码 {result.exit_code}）"

    return ToolResult(
        run_id=run.id,
        summary=summary,
        artifact_ids=[artifact.id],
        data={
            "status": result.status,
            "exit_code": result.exit_code,
            "artifacts": result.artifacts,
            "duration_ms": result.duration_ms,
        },
    )

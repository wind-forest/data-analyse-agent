from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.models import Session
from app.services import memory_service, run_service
from app.tools.base import ToolContext, ToolResult


class MemoryArgs(BaseModel):
    query: str = Field(default="", max_length=200)
    top_k: int = Field(default=5, ge=1, le=20)


async def query_session_memory(args: MemoryArgs, ctx: ToolContext) -> ToolResult:
    run = await run_service.start_run(
        ctx.db,
        ctx.session_id,
        "query_session_memory",
        args.model_dump(mode="json"),
        message_id=ctx.message_id,
    )
    matches = await memory_service.query_steps(ctx.session_id, args.query, args.top_k)

    session = await ctx.db.get(Session, ctx.session_id)
    summary = session.summary if session else None

    await run_service.finish_run(ctx.db, run)

    if not matches:
        summary_text = "本会话还没有可复用的分析步骤。"
    else:
        summary_text = "找到 " + str(len(matches)) + " 条历史步骤：" + "；".join(
            item.get("summary", "") for item in matches[:3]
        )

    return ToolResult(
        run_id=run.id,
        summary=summary_text,
        data={"session_summary": summary, "matches": matches},
    )

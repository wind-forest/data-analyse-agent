from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalysisRun
from app.errors import AppError
from app.services.sse_bus import get_event_context, publish_event


async def start_run(
    db: AsyncSession,
    session_id: uuid.UUID,
    tool_name: str,
    params: dict[str, Any],
    *,
    file_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
) -> AnalysisRun:
    context = get_event_context()
    if message_id is None and context is not None:
        message_id = uuid.UUID(context.message_id)

    run = AnalysisRun(
        session_id=session_id,
        message_id=message_id,
        file_id=file_id,
        tool_name=tool_name,
        params_json=params,
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    if context is not None:
        await publish_event(
            context.message_id,
            "tool_call",
            {
                "call_id": context.call_id,
                "run_id": str(run.id),
                "tool": tool_name,
                "params": params,
                "started_at": run.started_at.isoformat() if run.started_at else None,
            },
        )
    return run


async def finish_run(
    db: AsyncSession,
    run: AnalysisRun,
    *,
    status: str = "success",
    result_path: str | None = None,
    error: str | None = None,
) -> None:
    run.status = status
    run.result_path = result_path
    run.error = error
    run.finished_at = datetime.now(UTC)
    await db.commit()


async def get_run(db: AsyncSession, run_id: uuid.UUID) -> AnalysisRun:
    run = await db.get(AnalysisRun, run_id)
    if run is None:
        raise AppError("RUN_NOT_FOUND", "运行记录不存在", 404)
    return run

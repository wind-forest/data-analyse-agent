from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AnalysisRun, Approval, Message
from app.db.session import SessionLocal
from app.errors import AppError
from app.services import sse_bus

logger = logging.getLogger("app.approvals")

Decision = Literal["approved", "rejected"]


async def create_pending(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    tool_name: str,
    params: dict[str, Any],
) -> tuple[Approval, bool]:
    existing = await db.scalar(
        select(Approval)
        .where(Approval.run_id == run_id, Approval.tool_name == tool_name)
        .order_by(Approval.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        return existing, False

    approval = Approval(
        session_id=session_id,
        run_id=run_id,
        tool_name=tool_name,
        params_json=params,
        status="pending",
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)
    return approval, True


async def find_by_call(
    db: AsyncSession, message_id: uuid.UUID, tool_name: str, call_id: str
) -> tuple[AnalysisRun, Approval] | None:
    """用 call_id 作为幂等键：节点被 LangGraph 重放时复用同一审批。"""
    run = await db.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.message_id == message_id,
            AnalysisRun.tool_name == tool_name,
            AnalysisRun.params_json["__call_id__"].astext == call_id,
        )
        .order_by(AnalysisRun.started_at.desc())
        .limit(1)
    )
    if run is None:
        return None
    approval = await db.scalar(
        select(Approval)
        .where(Approval.run_id == run.id)
        .order_by(Approval.created_at.desc())
        .limit(1)
    )
    if approval is None:
        return None
    return run, approval


async def get_approval(db: AsyncSession, approval_id: uuid.UUID) -> Approval:
    approval = await db.get(Approval, approval_id)
    if approval is None:
        raise AppError("APPROVAL_NOT_FOUND", "审批记录不存在", 404)
    return approval


async def decide(
    db: AsyncSession, approval_id: uuid.UUID, decision: Decision
) -> Approval:
    reason = "user_approved" if decision == "approved" else "user_rejected"
    result = await db.execute(
        update(Approval)
        .where(Approval.id == approval_id, Approval.status == "pending")
        .values(status=decision, resolution_reason=reason, resolved_at=datetime.now(UTC))
        .returning(Approval.id)
    )
    if result.first() is None:
        await db.rollback()
        existing = await db.get(Approval, approval_id)
        if existing is None:
            raise AppError("APPROVAL_NOT_FOUND", "审批记录不存在", 404)
        raise AppError("APPROVAL_NOT_PENDING", "审批已处理或已超时", 409)
    await db.commit()
    return await get_approval(db, approval_id)


async def apply_resume_decision(
    approval_id: uuid.UUID, decision: Decision
) -> None:
    """恢复执行时补齐状态；已被 API 处理过则保持原状。"""
    async with SessionLocal() as db:
        await db.execute(
            update(Approval)
            .where(Approval.id == approval_id, Approval.status == "pending")
            .values(
                status=decision,
                resolution_reason=(
                    "user_approved" if decision == "approved" else "user_rejected"
                ),
                resolved_at=datetime.now(UTC),
            )
        )
        await db.commit()


async def sweep_expired() -> int:
    """过期审批原子关闭；不依赖 Agent 进程仍在运行。"""
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.approval_timeout_seconds)
    async with SessionLocal() as db:
        result = await db.execute(
            update(Approval)
            .where(Approval.status == "pending", Approval.created_at < cutoff)
            .values(
                status="rejected",
                resolution_reason="timeout",
                resolved_at=datetime.now(UTC),
            )
            .returning(Approval.id, Approval.run_id)
        )
        expired = result.all()
        if not expired:
            await db.commit()
            return 0

        for approval_id, run_id in expired:
            run = await db.get(AnalysisRun, run_id)
            if run is None:
                continue
            run.status = "failed"
            run.error = "审批超时"
            run.finished_at = datetime.now(UTC)
            if run.message_id is None:
                continue
            message = await db.get(Message, run.message_id)
            if message is not None and message.finish_reason is None:
                message.content = "操作审批超时，未执行。你可以重新描述需求后再试。"
                message.finish_reason = "timeout"
            await sse_bus.set_status(
                run.message_id, stage="done", finish_reason="timeout"
            )
            await sse_bus.publish_event(
                run.message_id,
                "done",
                {
                    "finish_reason": "timeout",
                    "approval_id": str(approval_id),
                },
            )
        await db.commit()

    logger.info("expired approvals=%s", len(expired))
    return len(expired)

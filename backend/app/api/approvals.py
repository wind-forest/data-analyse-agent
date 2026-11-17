from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.models import AnalysisRun
from app.dependencies import SessionDep
from app.errors import AppError
from app.services import agent_service, approval_service

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]


class ApprovalResult(BaseModel):
    approval_id: uuid.UUID
    status: str
    message_id: uuid.UUID


@router.post("/{approval_id}", status_code=202, response_model=ApprovalResult)
async def decide_approval(
    approval_id: uuid.UUID, payload: ApprovalDecision, db: SessionDep
) -> ApprovalResult:
    approval = await approval_service.get_approval(db, approval_id)
    updated = await approval_service.decide(db, approval_id, payload.decision)

    run = await db.get(AnalysisRun, updated.run_id)
    if run is None or run.message_id is None:
        raise AppError("RUN_NOT_FOUND", "关联运行记录不存在", 404)

    agent_service.resume_message(
        message_id=run.message_id,
        session_id=approval.session_id,
        approval_id=approval_id,
        decision=payload.decision,
    )
    return ApprovalResult(
        approval_id=approval_id, status=updated.status, message_id=run.message_id
    )

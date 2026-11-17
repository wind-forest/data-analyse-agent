from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.db.models import AnalysisRun, Artifact, Message
from app.dependencies import CurrentUser, SessionDep
from app.errors import AppError
from app.schemas.artifacts import ArtifactRead
from app.schemas.messages import MessageAccepted, MessageCreate, MessageRead
from app.schemas.sessions import SessionCreate, SessionRead
from app.services import agent_service, session_service, stream_service

router = APIRouter(prefix="/sessions", tags=["sessions"])

# 限额检查从 auth router 导入，避免循环依赖
from app.api.auth import check_anon_message_quota, check_anon_session_quota


@router.post("", response_model=SessionRead, status_code=201)
async def create_session(
    payload: SessionCreate,
    db: SessionDep,
    user: CurrentUser,
) -> SessionRead:
    await check_anon_session_quota(db, user)
    session = await session_service.create_session(
        db, payload.title, user_id=user.id if user else None
    )
    return SessionRead.model_validate(session)


@router.get("", response_model=list[SessionRead])
async def list_sessions(
    db: SessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[SessionRead]:
    sessions = await session_service.list_sessions(db, limit=limit, offset=offset)
    if user is not None:
        # 已登录：只返回自己的和匿名会话（兼容旧匿名会话）
        sessions = [s for s in sessions if s.user_id is None or s.user_id == user.id]
    else:
        sessions = [s for s in sessions if s.user_id is None]
    return [SessionRead.model_validate(item) for item in sessions]


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(
    session_id: uuid.UUID,
    db: SessionDep,
    user: CurrentUser,
) -> SessionRead:
    session = await session_service.get_session(db, session_id)
    if user is not None and session.user_id is not None and session.user_id != user.id:
        raise AppError("SESSION_NOT_FOUND", "会话不存在", 404)
    if user is None and session.user_id is not None:
        raise AppError("SESSION_NOT_FOUND", "会话不存在", 404)
    return SessionRead.model_validate(session)


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    db: SessionDep,
    user: CurrentUser,
) -> None:
    session = await session_service.get_session(db, session_id)
    if user is not None and session.user_id is not None and session.user_id != user.id:
        raise AppError("SESSION_NOT_FOUND", "会话不存在", 404)
    if user is None and session.user_id is not None:
        raise AppError("SESSION_NOT_FOUND", "会话不存在", 404)
    await session_service.delete_session(db, session_id)


@router.get("/{session_id}/messages", response_model=list[MessageRead])
async def list_messages(
    session_id: uuid.UUID,
    db: SessionDep,
    user: CurrentUser,
) -> list[MessageRead]:
    await get_session(session_id, db, user)
    result = await db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    return [MessageRead.model_validate(item) for item in result]


@router.post("/{session_id}/messages", status_code=202)
async def submit_message(
    session_id: uuid.UUID,
    payload: MessageCreate,
    db: SessionDep,
    user: CurrentUser,
) -> MessageAccepted:
    await get_session(session_id, db, user)
    await check_anon_message_quota(db, user, session_id)
    message = await agent_service.submit_message(db, session_id, payload)
    return MessageAccepted(message_id=message.id)


@router.get("/{session_id}/stream")
async def stream_events(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    request: Request,
    db: SessionDep,
    last_event_id: int | None = Query(default=None, ge=0),
):
    await session_service.get_session(db, session_id)
    message = await db.get(Message, message_id)
    if message is None or message.session_id != session_id:
        raise AppError("MESSAGE_NOT_FOUND", "消息不存在", 404)

    header_value = request.headers.get("Last-Event-ID")
    if header_value and header_value.strip().isdigit():
        resume_id = int(header_value)
    else:
        resume_id = last_event_id or 0

    return EventSourceResponse(
        stream_service.event_stream(message_id, resume_id),
        ping=settings.sse_heartbeat_seconds,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{session_id}/artifacts", response_model=list[ArtifactRead])
async def list_artifacts(
    session_id: uuid.UUID,
    db: SessionDep,
    user: CurrentUser,
) -> list[ArtifactRead]:
    await get_session(session_id, db, user)
    result = await db.execute(
        select(Artifact, AnalysisRun.message_id)
        .join(AnalysisRun, Artifact.run_id == AnalysisRun.id)
        .where(AnalysisRun.session_id == session_id)
        .order_by(Artifact.created_at.desc())
    )
    return [
        ArtifactRead.model_validate(artifact).model_copy(
            update={"message_id": message_id}
        )
        for artifact, message_id in result.all()
    ]

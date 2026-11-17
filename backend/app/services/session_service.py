from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session
from app.errors import AppError
from app.services.storage import remove_tree, session_dir, sessions_root


async def create_session(
    db: AsyncSession,
    title: str | None = None,
    user_id: uuid.UUID | None = None,
) -> Session:
    session = Session(title=(title or "新分析").strip() or "新分析", user_id=user_id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(
    db: AsyncSession, limit: int = 50, offset: int = 0
) -> list[Session]:
    result = await db.scalars(
        select(Session)
        .order_by(Session.updated_at.desc(), Session.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result)


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> Session:
    session = await db.get(Session, session_id)
    if session is None:
        raise AppError("SESSION_NOT_FOUND", "会话不存在", 404)
    return session


async def touch_session(db: AsyncSession, session: Session) -> None:
    session.updated_at = datetime.now(UTC)
    await db.commit()


async def delete_session(db: AsyncSession, session_id: uuid.UUID) -> None:
    session = await get_session(db, session_id)

    directory = session_dir(session_id)
    trash_target = None
    if directory.exists():
        trash_root = sessions_root() / ".trash"
        trash_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        trash_target = trash_root / f"{session_id}-{stamp}"
        directory.rename(trash_target)

    try:
        await db.delete(session)
        await db.commit()
    except Exception:
        if trash_target is not None and trash_target.exists():
            trash_target.rename(directory)
        raise

    if trash_target is not None and trash_target.exists():
        remove_tree(trash_target)

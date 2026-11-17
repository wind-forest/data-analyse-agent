from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User
from app.db.session import get_session
from app.services import auth_service

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _resolve_current_user(
    request: Request,
    db: SessionDep,
) -> User | None:
    """从 cookie 解析当前登录用户，若不存在则返回 None。"""
    cookie_token = request.cookies.get(settings.auth_session_cookie)
    if not cookie_token:
        return None
    user_id = auth_service.decode_session_token(cookie_token)
    if user_id is None:
        return None
    user = await auth_service.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        return None
    return user


CurrentUser = Annotated[User | None, Depends(_resolve_current_user)]

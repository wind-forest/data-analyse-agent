from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response
from sqlalchemy import func, select

from app.config import settings
from app.db.models import Message, Session as DbSession
from app.dependencies import CurrentUser, SessionDep
from app.errors import AppError
from app.schemas.auth import (
    CaptchaRead,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
    UpdateProfileRequest,
    UserRead,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/captcha", response_model=CaptchaRead)
async def get_captcha() -> CaptchaRead:
    captcha_id, image_b64, _ = await auth_service.generate_captcha()
    return CaptchaRead(
        captcha_id=captcha_id,
        image=f"data:image/svg+xml;base64,{image_b64}",
        hint="请输入 4 位数字",
    )


@router.post("/register", response_model=UserRead, status_code=201)
async def register(payload: RegisterRequest, db: SessionDep) -> UserRead:
    if not settings.auth_enabled:
        raise AppError("AUTH_DISABLED", "注册已关闭", 403)

    if not await auth_service.verify_captcha(payload.captcha_id, payload.captcha_code):
        raise AppError("CAPTCHA_INVALID", "验证码错误或已过期", 400)

    existing = await auth_service.get_user_by_username(db, payload.username)
    if existing is not None:
        raise AppError("USERNAME_EXISTS", "该用户名已被占用", 409)

    user = await auth_service.create_user(
        db,
        username=payload.username,
        password=payload.password,
        display_name=payload.display_name,
    )
    return UserRead.model_validate(user)


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: SessionDep,
) -> LoginResponse:
    if not settings.auth_enabled:
        raise AppError("AUTH_DISABLED", "登录已关闭", 403)

    if not await auth_service.verify_captcha(payload.captcha_id, payload.captcha_code):
        raise AppError("CAPTCHA_INVALID", "验证码错误或已过期", 400)

    user = await auth_service.get_user_by_username(db, payload.username)
    if user is None or not auth_service.verify_password(payload.password, user.password_hash):
        raise AppError("CREDENTIALS_INVALID", "用户名或密码错误", 401)

    if not user.is_active:
        raise AppError("USER_INACTIVE", "账号已被禁用", 403)

    await auth_service.update_last_login(db, user)

    token = auth_service.generate_session_token(user.id)
    response.set_cookie(
        key=settings.auth_session_cookie,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.auth_session_ttl_seconds,
        path="/",
    )
    return LoginResponse(user=UserRead.model_validate(user))


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_session_cookie,
        path="/",
    )


@router.get("/me", response_model=MeResponse)
async def me(
    db: SessionDep,
    request: Request,
    user: CurrentUser,
) -> MeResponse:
    """返回当前登录用户及匿名限额信息。"""
    user_read = UserRead.model_validate(user) if user else None

    # 匿名会话计数（没有 user_id 的 sessions，使用 request.session cookie 或 fingerprint 会更严谨，
    # 这里简化为：未登录用户看到的限额是固定值，由前端在触发时再询问后端实际会话数）
    anon_sessions_count = 0
    anon_messages_count = 0

    if user is None:
        # 简单统计匿名会话（所有 user_id 为 NULL 的会话）
        result = await db.execute(
            select(func.count(DbSession.id)).where(DbSession.user_id.is_(None))
        )
        anon_sessions_count = result.scalar() or 0

    sessions_remaining = max(0, settings.anon_max_sessions - anon_sessions_count)
    return MeResponse(
        user=user_read,
        anon_sessions_remaining=sessions_remaining,
        anon_messages_remaining_per_session=settings.anon_max_messages_per_session,
    )


@router.patch("/me", response_model=UserRead)
async def update_profile(
    payload: UpdateProfileRequest,
    db: SessionDep,
    user: CurrentUser,
) -> UserRead:
    """修改当前用户资料（昵称等）。未登录返回 401。"""
    if user is None:
        raise AppError("UNAUTHORIZED", "请先登录", 401)
    if payload.display_name is not None:
        user.display_name = payload.display_name or None
    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user)


@router.post("/change-password", status_code=200)
async def change_password(
    payload: ChangePasswordRequest,
    db: SessionDep,
    user: CurrentUser,
) -> dict[str, str]:
    """修改密码，要求旧密码正确。"""
    if user is None:
        raise AppError("UNAUTHORIZED", "请先登录", 401)
    if not auth_service.verify_password(payload.old_password, user.password_hash):
        raise AppError("CREDENTIALS_INVALID", "旧密码错误", 400)
    user.password_hash = auth_service.hash_password(payload.new_password)
    await db.commit()
    return {"status": "ok"}


@router.delete("/me", status_code=204)
async def delete_account(
    response: Response,
    db: SessionDep,
    user: CurrentUser,
) -> None:
    """删除当前账号及其所有会话数据。需要用户已登录。"""
    if user is None:
        raise AppError("UNAUTHORIZED", "请先登录", 401)
    # 关联会话用 CASCADE 删除
    await db.delete(user)
    await db.commit()
    response.delete_cookie(key=settings.auth_session_cookie, path="/")


# --- 限额检查辅助（供 sessions API 调用） ---


async def check_anon_session_quota(db: SessionDep, user: CurrentUser) -> None:
    """未登录用户会话数量检查。"""
    if user is not None:
        return
    result = await db.execute(
        select(func.count(DbSession.id)).where(DbSession.user_id.is_(None))
    )
    count = result.scalar() or 0
    if count >= settings.anon_max_sessions:
        raise AppError(
            "ANON_SESSION_LIMIT",
            f"访客最多可创建 {settings.anon_max_sessions} 个会话，请登录后继续",
            403,
        )


async def check_anon_message_quota(db: SessionDep, user: CurrentUser, session_id: uuid.UUID) -> None:
    """未登录用户单会话消息数检查（只数 user 消息轮数）。"""
    if user is not None:
        return
    result = await db.execute(
        select(func.count(Message.id)).where(
            Message.session_id == session_id,
            Message.role == "user",
        )
    )
    count = result.scalar() or 0
    # count 是当前已经发送的 user 消息数；这次提交之后会变成 count+1
    if count >= settings.anon_max_messages_per_session:
        raise AppError(
            "ANON_MESSAGE_LIMIT",
            f"访客单会话最多 {settings.anon_max_messages_per_session} 轮对话，请登录后继续",
            403,
        )

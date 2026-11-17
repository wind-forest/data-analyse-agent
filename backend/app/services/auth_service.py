from __future__ import annotations

import base64
import io
import logging
import random
import string
import uuid
from datetime import datetime, timezone

import bcrypt as _bcrypt
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User
from app.db.redis import get_redis

logger = logging.getLogger("auth")

serializer = URLSafeTimedSerializer(settings.auth_secret_key, salt="auth-session")


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def generate_session_token(user_id: uuid.UUID) -> str:
    return serializer.dumps({"uid": str(user_id)})


def decode_session_token(token: str, max_age_seconds: int | None = None) -> uuid.UUID | None:
    try:
        data = serializer.loads(token, max_age=max_age_seconds or settings.auth_session_ttl_seconds)
        uid_str = data.get("uid")
        if not uid_str:
            return None
        return uuid.UUID(uid_str)
    except (BadSignature, ValueError, TypeError) as exc:
        logger.debug("decode session token failed: %s", exc)
        return None


def _generate_captcha_code() -> str:
    """生成 4 位数字验证码。"""
    return "".join(random.choices(string.digits, k=4))


def _render_captcha_image(code: str) -> str:
    """用纯 ASCII 风格渲染验证码，返回 base64 SVG。"""
    colors = ["#2563eb", "#059669", "#dc2626", "#7c3aed", "#ea580c"]
    parts: list[str] = []
    for i, ch in enumerate(code):
        x = 12 + i * 28 + random.randint(-2, 2)
        y = 30 + random.randint(-3, 3)
        color = random.choice(colors)
        rotate = random.randint(-25, 25)
        parts.append(
            f'<text x="{x}" y="{y}" font-family="monospace" font-size="30" '
            f'font-weight="bold" fill="{color}" transform="rotate({rotate} {x} {y})">{ch}</text>'
        )
    # 干扰线
    for _ in range(4):
        x1 = random.randint(0, 120)
        y1 = random.randint(0, 45)
        x2 = random.randint(0, 120)
        y2 = random.randint(0, 45)
        color = random.choice(colors)
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1" opacity="0.5"/>')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="140" height="50" viewBox="0 0 140 50">'
        f'<rect width="100%" height="100%" fill="#f8fafc"/>'
        f'{"".join(parts)}'
        f'</svg>'
    )
    return base64.b64encode(svg.encode("utf-8")).decode("ascii")


async def generate_captcha() -> tuple[str, str, str]:
    """生成新的验证码并存入 Redis，返回 (captcha_id, base64_image, code)。"""
    code = _generate_captcha_code()
    captcha_id = uuid.uuid4().hex
    redis = get_redis()
    await redis.setex(
        f"captcha:{captcha_id}",
        settings.auth_captcha_ttl_seconds,
        code,
    )
    image_b64 = _render_captcha_image(code)
    return captcha_id, image_b64, code


async def verify_captcha(captcha_id: str, captcha_code: str) -> bool:
    redis = get_redis()
    key = f"captcha:{captcha_id}"
    stored = await redis.get(key)
    if stored is None:
        return False
    # 不论对错都立即删除，防止重复使用
    await redis.delete(key)
    return stored == captcha_code


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.scalars(select(User).where(User.username == username).limit(1))
    return result.first()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def create_user(
    db: AsyncSession,
    username: str,
    password: str,
    display_name: str | None = None,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=display_name or username,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_last_login(db: AsyncSession, user: User) -> None:
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

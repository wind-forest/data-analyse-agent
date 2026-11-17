from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,64}$")


class CaptchaRead(BaseModel):
    """前端请求验证码后返回的包含 base64 图片与 captcha_id。"""

    captcha_id: str
    image: str
    hint: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str | None = Field(default=None, max_length=64)
    captcha_id: str
    captcha_code: str = Field(..., min_length=4, max_length=6)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        if not USERNAME_RE.match(value):
            raise ValueError("用户名只能包含字母、数字和下划线，长度 3-64")
        return value


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str
    captcha_id: str
    captcha_code: str = Field(..., min_length=4, max_length=6)


class UpdateProfileRequest(BaseModel):
    """修改昵称/展示名。全部字段可选。"""

    display_name: str | None = Field(default=None, max_length=64)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str | None
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class LoginResponse(BaseModel):
    user: UserRead


class MeResponse(BaseModel):
    user: UserRead | None
    anon_sessions_remaining: int
    anon_messages_remaining_per_session: int

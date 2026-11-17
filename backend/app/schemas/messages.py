from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    file_ids: list[uuid.UUID] = Field(default_factory=list)
    model: str | None = None
    allow_custom_code: bool = False


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    tool_calls_json: list[dict[str, Any]] | None
    finish_reason: str | None
    created_at: datetime


class MessageAccepted(BaseModel):
    message_id: uuid.UUID

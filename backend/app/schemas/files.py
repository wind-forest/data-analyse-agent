from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    original_name: str
    size: int
    sha256: str
    mime: str | None
    status: str
    error: str | None
    created_at: datetime

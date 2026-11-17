from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ToolContext:
    db: AsyncSession
    session_id: uuid.UUID
    message_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None


class ToolResult(BaseModel):
    run_id: uuid.UUID
    summary: str
    artifact_ids: list[uuid.UUID] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ToolDefinition:
    def __init__(
        self,
        *,
        name: str,
        description: str,
        args_model: type[BaseModel],
        handler: Any,
        risk: Literal["low", "high"] = "low",
        enabled: bool = True,
    ) -> None:
        self.name = name
        self.description = description
        self.args_model = args_model
        self.handler = handler
        self.risk = risk
        self.enabled = enabled

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }

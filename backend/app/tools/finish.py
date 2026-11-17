from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.tools.base import ToolDefinition


class FinishArgs(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)
    artifact_ids: list[uuid.UUID] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


async def _not_executable(*_args, **_kwargs):
    raise RuntimeError("finish 由 Agent 图处理，不能直接执行")


FINISH_TOOL = ToolDefinition(
    name="finish",
    description="提交最终答案并结束本次分析。必须调用一次。",
    args_model=FinishArgs,
    handler=_not_executable,
)

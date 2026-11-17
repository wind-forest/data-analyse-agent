from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.dependencies import SessionDep
from app.services import session_service
from app.tools.aggregate import AggregateArgs
from app.tools.base import ToolContext, ToolResult
from app.tools.chart import ChartArgs
from app.tools.memory import MemoryArgs
from app.tools.profile import ProfileArgs
from app.tools.registry import execute_tool

router = APIRouter(prefix="/tools", tags=["tools"])


class ProfileRequest(ProfileArgs):
    session_id: uuid.UUID


class AggregateRequest(AggregateArgs):
    session_id: uuid.UUID


class ChartRequest(ChartArgs):
    session_id: uuid.UUID


class MemoryRequest(MemoryArgs):
    session_id: uuid.UUID


async def _run(
    db: SessionDep, session_id: uuid.UUID, tool: str, args: BaseModel
) -> ToolResult:
    await session_service.get_session(db, session_id)
    payload: dict[str, Any] = args.model_dump(mode="json")
    payload.pop("session_id", None)
    context = ToolContext(db=db, session_id=session_id)
    return await execute_tool(tool, payload, context)


@router.post("/profile", response_model=ToolResult)
async def profile_tool(body: ProfileRequest, db: SessionDep) -> ToolResult:
    return await _run(db, body.session_id, "profile_dataset", body)


@router.post("/aggregate", response_model=ToolResult)
async def aggregate_tool(body: AggregateRequest, db: SessionDep) -> ToolResult:
    return await _run(db, body.session_id, "aggregate_plays", body)


@router.post("/chart", response_model=ToolResult)
async def chart_tool(body: ChartRequest, db: SessionDep) -> ToolResult:
    return await _run(db, body.session_id, "generate_chart_data", body)


@router.post("/memory", response_model=ToolResult)
async def memory_tool(body: MemoryRequest, db: SessionDep) -> ToolResult:
    return await _run(db, body.session_id, "query_session_memory", body)

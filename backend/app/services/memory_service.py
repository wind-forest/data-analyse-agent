from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session
from app.db.redis import get_redis

logger = logging.getLogger("app.memory")

STEPS_TTL_SECONDS = 7 * 24 * 3600
MAX_STEPS = 100
_TOKEN_PATTERN = re.compile(r"[0-9a-zA-Z_]+|[\u4e00-\u9fff]{1,2}")


def _steps_key(session_id: uuid.UUID | str) -> str:
    return f"session:{session_id}:steps"


def _tokens(text: str) -> set[str]:
    return {item.lower() for item in _TOKEN_PATTERN.findall(text)}


async def record_step(
    session_id: uuid.UUID | str,
    *,
    tool: str,
    params: dict[str, Any],
    summary: str,
    artifact_ids: list[str],
) -> None:
    entry = json.dumps(
        {
            "tool": tool,
            "params": params,
            "summary": summary,
            "artifact_ids": artifact_ids,
            "at": datetime.now(UTC).isoformat(),
        },
        ensure_ascii=False,
        default=str,
    )
    try:
        redis = get_redis()
        key = _steps_key(session_id)
        async with redis.pipeline(transaction=False) as pipe:
            pipe.rpush(key, entry)
            pipe.ltrim(key, -MAX_STEPS, -1)
            pipe.expire(key, STEPS_TTL_SECONDS)
            await pipe.execute()
    except Exception:
        logger.warning("record step failed", exc_info=True)


async def read_steps(
    session_id: uuid.UUID | str, limit: int = MAX_STEPS
) -> list[dict[str, Any]]:
    try:
        raw = await get_redis().lrange(_steps_key(session_id), -limit, -1)
        return [json.loads(item) for item in raw]
    except Exception:
        logger.warning("read steps failed", exc_info=True)
        return []


async def query_steps(
    session_id: uuid.UUID | str, query: str, top_k: int = 5
) -> list[dict[str, Any]]:
    steps = await read_steps(session_id)
    if not steps:
        return []

    query_tokens = _tokens(query)
    if not query_tokens:
        return steps[-top_k:]

    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, step in enumerate(steps):
        haystack = " ".join(
            [step.get("tool", ""), step.get("summary", "")]
        ) + json.dumps(step.get("params") or {}, ensure_ascii=False)
        overlap = len(query_tokens & _tokens(haystack))
        if overlap == 0:
            continue
        recency = index / max(len(steps) - 1, 1)
        scored.append((overlap + recency * 0.5, index, step))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [step for _, _, step in scored[:top_k]]


async def update_summary(
    db: AsyncSession,
    session_id: uuid.UUID,
    answer: str,
    tool_history: list[dict[str, Any]],
) -> None:
    session = await db.get(Session, session_id)
    if session is None:
        return
    steps = [
        item["summary"]
        for item in tool_history
        if item.get("summary")
    ]
    summary = answer.strip()[:600]
    if steps:
        summary = f"{summary}\n关键步骤：{'；'.join(steps[-5:])}"
    session.summary = summary[:1000]
    session.summary_updated_at = datetime.now(UTC)
    await db.commit()

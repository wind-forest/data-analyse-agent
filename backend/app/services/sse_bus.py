from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.db.redis import get_redis

logger = logging.getLogger("app.sse")

MAX_CACHED_EVENTS = 2000
TERMINAL_EVENTS = {"done", "error"}


@dataclass(frozen=True)
class EventContext:
    message_id: str
    call_id: str | None = None


_event_context: ContextVar[EventContext | None] = ContextVar(
    "event_context", default=None
)


def get_event_context() -> EventContext | None:
    return _event_context.get()


@contextmanager
def bind_event_context(
    message_id: uuid.UUID | str, call_id: str | None = None
) -> Iterator[None]:
    token = _event_context.set(EventContext(str(message_id), call_id))
    try:
        yield
    finally:
        _event_context.reset(token)


def _seq_key(message_id: uuid.UUID | str) -> str:
    return f"message:{message_id}:event_seq"


def _events_key(message_id: uuid.UUID | str) -> str:
    return f"message:{message_id}:events"


def _status_key(message_id: uuid.UUID | str) -> str:
    return f"message:{message_id}:status"


def channel(message_id: uuid.UUID | str) -> str:
    return f"message:{message_id}:notifications"


def _channel(message_id: uuid.UUID | str) -> str:
    return channel(message_id)


async def publish_event(
    message_id: uuid.UUID | str, event_type: str, data: dict[str, Any]
) -> None:
    """递增序号 → 写缓存并设置 TTL → Pub/Sub 发布。失败不影响主流程。"""
    try:
        redis = get_redis()
        sequence = int(await redis.incr(_seq_key(message_id)))
        payload = json.dumps(
            {
                "event_id": sequence,
                "message_id": str(message_id),
                "timestamp": datetime.now(UTC).isoformat(),
                "event": event_type,
                **data,
            },
            ensure_ascii=False,
            default=str,
        )
        ttl = settings.sse_event_ttl_seconds
        events_key = _events_key(message_id)
        async with redis.pipeline(transaction=False) as pipe:
            pipe.rpush(events_key, payload)
            pipe.ltrim(events_key, -MAX_CACHED_EVENTS, -1)
            pipe.expire(events_key, ttl)
            pipe.expire(_seq_key(message_id), ttl)
            await pipe.execute()
        await redis.publish(_channel(message_id), payload)
    except Exception:
        logger.warning("publish event failed type=%s", event_type, exc_info=True)


async def set_status(
    message_id: uuid.UUID | str,
    *,
    stage: str,
    iteration: int = 0,
    finish_reason: str | None = None,
) -> None:
    try:
        redis = get_redis()
        key = _status_key(message_id)
        mapping = {
            "stage": stage,
            "iteration": str(iteration),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if finish_reason:
            mapping["finish_reason"] = finish_reason
        async with redis.pipeline(transaction=False) as pipe:
            pipe.hset(key, mapping=mapping)
            pipe.expire(key, settings.sse_event_ttl_seconds)
            await pipe.execute()
    except Exception:
        logger.warning("set status failed stage=%s", stage, exc_info=True)


async def get_status(message_id: uuid.UUID | str) -> dict[str, str]:
    try:
        return dict(await get_redis().hgetall(_status_key(message_id)))
    except Exception:  # noqa: BLE001
        return {}


async def current_sequence(message_id: uuid.UUID | str) -> int:
    try:
        value = await get_redis().get(_seq_key(message_id))
        return int(value or 0)
    except Exception:  # noqa: BLE001
        return 0


async def replay_after(
    message_id: uuid.UUID | str, last_event_id: int
) -> tuple[list[dict[str, Any]], bool]:
    """返回 last_event_id 之后可连续重放的事件；无法连续时返回 gap 标记。"""
    try:
        redis = get_redis()
        sequence = await current_sequence(message_id)
        if last_event_id >= sequence:
            return [], False
        raw = await redis.lrange(_events_key(message_id), 0, -1)
        events = [json.loads(item) for item in raw]
        if last_event_id == 0:
            if not events and sequence > 0:
                return [], True
        elif not events or events[0]["event_id"] > last_event_id + 1:
            return [], True
        return [item for item in events if item["event_id"] > last_event_id], False
    except Exception:
        logger.warning("replay failed", exc_info=True)
        return [], True


async def publish_artifact(message_id: uuid.UUID | str, artifact: Any) -> None:
    await publish_event(
        message_id,
        "artifact",
        {
            "artifact_id": str(artifact.id),
            "type": artifact.type,
            "payload": artifact.payload_json,
        },
    )

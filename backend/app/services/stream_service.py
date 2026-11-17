from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sse_starlette.sse import ServerSentEvent

from app.db.redis import get_redis
from app.services import sse_bus

logger = logging.getLogger("app.sse.stream")

TERMINAL_EVENTS = {"done", "error"}
POLL_TIMEOUT_SECONDS = 1.0


def _to_sse(event: dict[str, Any]) -> ServerSentEvent:
    return ServerSentEvent(
        id=str(event["event_id"]),
        event=event["event"],
        data=json.dumps(event, ensure_ascii=False),
    )


def _gap_event(message_id: uuid.UUID, resume_id: int) -> ServerSentEvent:
    payload = {
        "event_id": resume_id,
        "message_id": str(message_id),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event": "error",
        "code": "EVENT_GAP",
        "message": "事件缓存已过期，请重新拉取历史消息",
        "retryable": False,
    }
    return ServerSentEvent(
        id=str(resume_id), event="error", data=json.dumps(payload, ensure_ascii=False)
    )


async def event_stream(
    message_id: uuid.UUID, resume_id: int
) -> AsyncIterator[ServerSentEvent]:
    """先订阅再回放，避免订阅与缓存读取之间丢事件。"""
    redis = get_redis()
    pubsub = redis.pubsub()
    channel = sse_bus.channel(message_id)
    await pubsub.subscribe(channel)

    try:
        sequence = await sse_bus.current_sequence(message_id)
        if resume_id >= sequence:
            status = await sse_bus.get_status(message_id)
            if status.get("stage") in {"done", "error"}:
                return

        buffered: list[dict[str, Any]] = []
        drain_deadline = time.monotonic() + 0.1
        while time.monotonic() < drain_deadline:
            raw = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=0.02
            )
            if raw is None:
                break
            if raw.get("type") == "message":
                buffered.append(json.loads(raw["data"]))

        history, gap = await sse_bus.replay_after(message_id, resume_id)
        if gap:
            yield _gap_event(message_id, resume_id)
            return

        merged: dict[int, dict[str, Any]] = {}
        for item in [*history, *buffered]:
            merged[int(item["event_id"])] = item

        sent = resume_id
        for event_id in sorted(merged):
            if event_id <= sent:
                continue
            event = merged[event_id]
            sent = event_id
            yield _to_sse(event)
            if event["event"] in TERMINAL_EVENTS:
                return

        while True:
            raw = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=POLL_TIMEOUT_SECONDS
            )
            if raw is None or raw.get("type") != "message":
                await asyncio.sleep(0)
                continue
            event = json.loads(raw["data"])
            event_id = int(event["event_id"])
            if event_id <= sent:
                continue
            sent = event_id
            yield _to_sse(event)
            if event["event"] in TERMINAL_EVENTS:
                return
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            logger.debug("unsubscribe failed", exc_info=True)
        try:
            await pubsub.aclose()
        except Exception:
            logger.debug("pubsub close failed", exc_info=True)

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import settings

logger = logging.getLogger("app.agent.checkpointer")

_saver: Any | None = None
_stack: AsyncExitStack | None = None


def _psycopg_url() -> str:
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


def get_saver() -> Any | None:
    return _saver


def set_saver(saver: Any | None) -> None:
    """测试或运行时替换检查点实现，同时使已编译图失效。"""
    global _saver
    _saver = saver
    from app.agent.graph import reset_graph

    reset_graph()


async def init_checkpointer() -> None:
    """检查点表的唯一创建方；失败时 Agent 不可用，但不阻塞进程启动。"""
    global _saver, _stack
    stack = AsyncExitStack()
    await stack.__aenter__()
    try:
        saver = await stack.enter_async_context(
            AsyncPostgresSaver.from_conn_string(_psycopg_url())
        )
        await saver.setup()
    except Exception:
        logger.exception("checkpointer init failed, agent disabled")
        await stack.aclose()
        _saver = None
        _stack = None
        return

    _saver = saver
    _stack = stack
    logger.info("langgraph checkpointer ready")


async def close_checkpointer() -> None:
    global _saver, _stack
    _saver = None
    if _stack is not None:
        await _stack.aclose()
        _stack = None

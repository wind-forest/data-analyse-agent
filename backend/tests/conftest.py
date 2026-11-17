from __future__ import annotations

import asyncio
import os
import tempfile

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

TEST_DB_NAME = "data_agent_test"

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="agent-test-data-")

_raw_database_url = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://data_agent:data_agent@postgres:5432/data_agent",
)
_admin_dsn, _ = _raw_database_url.rsplit("/", 1)
_TEST_URL = f"{_admin_dsn}/{TEST_DB_NAME}"
os.environ["DATABASE_URL"] = _TEST_URL

from app.db.base import Base
from app.db.session import engine
from app.main import app


async def _ensure_database() -> None:
    dsn = _TEST_URL.replace("postgresql+asyncpg://", "postgresql://")
    admin_dsn = dsn.rsplit("/", 1)[0] + "/postgres"
    connection = await asyncpg.connect(admin_dsn)
    try:
        exists = await connection.fetchval(
            "select 1 from pg_database where datname = $1", TEST_DB_NAME
        )
        if not exists:
            await connection.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await connection.close()


async def _create_schema() -> None:
    await _ensure_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def _drop_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    asyncio.run(_create_schema())
    yield
    asyncio.run(_drop_schema())


@pytest.fixture(autouse=True)
async def clean_tables() -> None:
    yield
    async with engine.begin() as conn:
        for table in (
            "approvals",
            "artifacts",
            "analysis_runs",
            "files",
            "messages",
            "sessions",
        ):
            await conn.execute(text(f"DELETE FROM {table}"))
    # 每个测试使用独立事件循环，必须释放跨循环的连接与客户端
    from app.db.redis import close_redis

    try:
        await close_redis()
    except Exception:  # noqa: BLE001 - 测试清理不因 Redis 异常中断
        print("redis close failed during teardown")
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def db_session():
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def agent_runtime(monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agent.checkpointer import set_saver
    from app.config import settings

    set_saver(InMemorySaver())
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "max_iterations", 10)
    monkeypatch.setattr(settings, "agent_token_budget", 100000)
    yield
    set_saver(None)

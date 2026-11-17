import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.db.session import engine

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/ready")
async def ready() -> JSONResponse:
    checks: dict[str, object] = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - 健康检查需要吞掉异常并报告类型
        checks["database"] = f"error: {type(exc).__name__}"

    client = None
    try:
        client = aioredis.from_url(settings.redis_url)
        await client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {type(exc).__name__}"
    finally:
        if client is not None:
            await client.aclose()

    checks["llm_configured"] = settings.llm_configured
    infra_ok = checks["database"] == "ok" and checks["redis"] == "ok"

    if not infra_ok:
        status = "error"
    elif not settings.llm_configured:
        status = "degraded"
    else:
        status = "ok"

    return JSONResponse(
        status_code=200 if infra_ok else 503,
        content={"status": status, "checks": checks, "model": settings.model_name},
    )

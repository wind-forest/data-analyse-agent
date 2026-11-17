import asyncio
import contextlib
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi_mcp import FastApiMCP
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agent.checkpointer import close_checkpointer, init_checkpointer
from app.api.router import api_router
from app.config import settings
from app.db.redis import close_redis
from app.errors import AppError
from app.sandbox.manager import init_sandbox
from app.services import approval_service

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app")

APPROVAL_SWEEP_INTERVAL_SECONDS = 30


async def _approval_sweeper() -> None:
    while True:
        await asyncio.sleep(APPROVAL_SWEEP_INTERVAL_SECONDS)
        try:
            await approval_service.sweep_expired()
        except Exception:
            logger.exception("approval sweeper failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_sandbox()
    await init_checkpointer()
    from app.services.agent_service import mark_stale_messages

    try:
        await mark_stale_messages()
    except Exception:
        logger.exception("failed to mark stale messages")

    sweeper = asyncio.create_task(_approval_sweeper())
    yield
    sweeper.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sweeper
    await close_checkpointer()
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api")

mcp = FastApiMCP(app, name=settings.app_name, include_tags=["tools"])
mcp.mount()


@app.middleware("http")
async def request_context(request: Request, call_next: Any) -> Any:
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request failed request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        raise
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


def _error_response(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return _error_response(
        422, "VALIDATION_ERROR", "请求参数校验失败", {"errors": jsonable_encoder(exc.errors())}
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_response(exc.status_code, "HTTP_ERROR", str(exc.detail))


@app.exception_handler(Exception)
async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error: %s", type(exc).__name__)
    return _error_response(500, "INTERNAL_ERROR", "服务内部错误")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "health": "/api/health/live",
    }

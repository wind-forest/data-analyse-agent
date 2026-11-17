from fastapi import APIRouter

from app.api import approvals, auth, config, files, health, sessions, tools

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(config.router)
api_router.include_router(auth.router)
api_router.include_router(sessions.router)
api_router.include_router(files.router)
api_router.include_router(approvals.router)
api_router.include_router(tools.router)

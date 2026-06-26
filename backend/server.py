"""Content Approval Agent — main FastAPI app. Wires together modular routers."""
import asyncio
import logging
import os

from fastapi import FastAPI, APIRouter, Request
from starlette.middleware.cors import CORSMiddleware

from core import client, logger
from storage import init_storage
from scheduler import sla_scheduler_loop

# Routers
import auth as auth_module
import scoring as scoring_module
import storage as storage_module
import notifications as notifications_module
import submissions as submissions_module
import analytics as analytics_module
import scheduler as scheduler_module
from stats import router as stats_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

app = FastAPI(title="Content Approval Agent")

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_module.router)
api_router.include_router(scoring_module.router)
api_router.include_router(storage_module.router)
api_router.include_router(notifications_module.router)
api_router.include_router(submissions_module.router)
api_router.include_router(analytics_module.router)
api_router.include_router(scheduler_module.router)
api_router.include_router(stats_router)  # ← stats routes under /api like everything else

@api_router.get("/")
async def root() -> dict[str, str]:
    return {"service": "Content Approval Agent", "status": "ok"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_api_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.on_event("startup")
async def on_startup() -> None:
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed at startup: {e}")
    asyncio.create_task(sla_scheduler_loop())
    logger.info("SLA scheduler task scheduled")


@app.on_event("shutdown")
async def shutdown_db_client() -> None:
    client.close()
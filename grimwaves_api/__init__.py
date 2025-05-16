import time
from collections.abc import Awaitable
from logging import Logger
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from grimwaves_api.common.utils import get_project_metadata

# Import Celery app for initialization (will register tasks)
from grimwaves_api.core.celery_app import celery_app  # noqa: F401 # pyright: ignore[reportUnusedImport]
from grimwaves_api.core.logger import RequestLoggingMiddleware, get_logger, setup_logging
from grimwaves_api.core.settings import settings
from grimwaves_api.modules.base.router import router as base_router
from grimwaves_api.modules.music.router import router as music_router
from grimwaves_api.modules.styler.router import router as styler_router

# Initialize module logger
logger: Logger = get_logger("init")

# Configure logging
setup_logging(settings.logging)

# Get project metadata
name, version, description = get_project_metadata()

# Create FastAPI instance with metadata
app: FastAPI = FastAPI(
    title=name,
    version=version,
    description=description,
)

# Add middlewares
app.add_middleware(RequestLoggingMiddleware)


# Add middleware for detailed logging
@app.middleware("http")
async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    logger.info("Request: %s %s", request.method, request.url)
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info("Response status: %s, time: %.4fs", response.status_code, process_time)
    return response


# Add CORS middleware with default values if not configured
app.add_middleware(
    middleware_class=CORSMiddleware,
    allow_origins=settings.cors.get("allow_origins", ["*"]),
    allow_methods=settings.cors.get("allow_methods", ["GET", "POST"]),
    allow_headers=settings.cors.get("allow_headers", ["*"]),
    allow_credentials=True,
)

# Include routers
app.include_router(base_router)
app.include_router(styler_router)
app.include_router(music_router)

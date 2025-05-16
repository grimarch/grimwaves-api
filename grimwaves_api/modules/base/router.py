from fastapi import APIRouter

from grimwaves_api.core.logger import get_logger

logger = get_logger("base.router")

router = APIRouter(tags=["base"])


@router.get("/")
def root() -> dict[str, str]:
    """Root endpoint for the API."""
    logger.debug("Root endpoint called")
    return {"message": "GrimWaves API is running!"}


@router.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint for the API."""
    logger.debug("Health check endpoint called")
    return {"status": "ok"}


@router.get("/error/{status}")
async def error_handler(status: int) -> dict[str, str | int]:
    """Handle error pages from Traefik."""
    logger.info("Error handler called for status: %s", status)
    return {"message": f"Error {status}", "status_code": status}

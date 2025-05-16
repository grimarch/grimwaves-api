from fastapi import APIRouter

from grimwaves_api.core.logger import get_logger
from grimwaves_api.modules.styler.models import TextRequest
from grimwaves_api.modules.styler.service import convert_text, get_available_styles

logger = get_logger("styler.router")

router = APIRouter(tags=["text-styler"])


@router.get("/styles")
def get_styles() -> dict[str, list[str]]:
    """Get all available text styles."""
    logger.debug("Styles endpoint called")
    return {"styles": get_available_styles()}


@router.post("/convert")
def convert_text_route(request: TextRequest) -> dict[str, str]:
    """Convert text to the specified style.

    Returns a dictionary with original text, converted text, and style.
    """
    logger.info("Convert request received - Text: '%s', Style: '%s'", request.text, request.style)

    converted = convert_text(request.text, request.style)

    return {
        "original_text": request.text,
        "converted_text": converted,
        "style": request.style,
    }

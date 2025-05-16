from fastapi import HTTPException

from grimwaves_api.common.utils import load_json
from grimwaves_api.core.logger import get_logger
from grimwaves_api.core.settings import settings

logger = get_logger("styler.service")

# Load style mappings
STYLE_MAPPINGS = {style: load_json(f"data/{style}_letters.json") for style in settings.available_styles}
logger.info("Loaded %s text style mappings: %s", len(settings.available_styles), ", ".join(settings.available_styles))


def get_available_styles() -> list[str]:
    """Return list of available text styles."""
    return settings.available_styles


def convert_text(text: str, style: str) -> str:
    """Convert text to the specified style.

    Args:
        text: Original text to convert
        style: Style name to apply

    Returns:
        Converted text in the specified style

    Raises:
        HTTPException: If the requested style is not supported
    """
    if style not in settings.available_styles:
        logger.warning("Unsupported style requested: %s", style)
        raise HTTPException(status_code=400, detail=f"Style '{style}' not supported")

    converted_text = "".join(STYLE_MAPPINGS[style].get(char, char) for char in text)
    logger.info(
        "Conversion result - Original: '%s', Converted: '%s', Style: '%s'",
        text,
        converted_text,
        style,
    )

    return converted_text

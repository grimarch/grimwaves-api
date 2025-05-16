import json
from pathlib import Path
from typing import Any

import tomli

from grimwaves_api.core.logger.logger import get_logger

# Initialize module logger
logger = get_logger("common.utils")


def load_json(filename: str) -> dict[str, Any]:
    with Path(filename).open(encoding="utf-8") as f:
        return json.load(f)


def load_toml(filename: str) -> dict[str, Any]:
    """Load and parse a TOML file.

    Args:
        filename: Path to the TOML file to load

    Returns:
        Parsed TOML data as a dictionary

    Raises:
        FileNotFoundError: If the file doesn't exist
        tomli.TOMLDecodeError: If the file contains invalid TOML
    """
    try:
        with Path(filename).open("rb") as f:
            message = f"Loading TOML file: {filename}"
            logger.debug(message)
            return tomli.load(f)
    except FileNotFoundError:
        message = f"TOML file not found: {filename}"
        logger.exception(message)
        raise
    except tomli.TOMLDecodeError as e:
        message = f"Invalid TOML format in {filename}: {e}"
        logger.exception(message)
        raise


def get_project_metadata() -> tuple[str, str, str]:
    """Get project metadata from pyproject.toml.

    Returns:
        tuple containing name, version, and description
    """
    try:
        pyproject_data = load_toml("pyproject.toml")
        poetry_data = pyproject_data["tool"]["poetry"]
        return (
            poetry_data["name"],
            poetry_data["version"],
            poetry_data["description"],
        )
    except (FileNotFoundError, KeyError):
        logger.exception("Error reading pyproject.toml")
        return "GrimWaves API", "0.1.0", "API service"

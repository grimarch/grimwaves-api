import logging
from pathlib import Path
from typing import Any

# Импортируем наш фильтр
from .filters import SecretFilter


def setup_logging(config: dict[str, Any]) -> None:
    """Configure logging for the application.

    Args:
        config: Logging configuration dictionary with level, format, file, etc.
    """
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Создаем обработчики
    console_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(
        filename=log_dir / config["file"],
        encoding="utf-8",
    )

    # Устанавливаем форматтер для обработчиков
    formatter = logging.Formatter(config["format"])
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # !!! Создаем и добавляем наш фильтр к КАЖДОМУ обработчику !!!
    secret_filter = SecretFilter()
    console_handler.addFilter(secret_filter)
    file_handler.addFilter(secret_filter)

    # Базовая конфигурация теперь использует созданные обработчики
    logging.basicConfig(
        level=config["level"].upper(),
        # format больше не нужен здесь, так как он задан в форматтере обработчиков
        handlers=[console_handler, file_handler],
    )

    # Configure module-specific log levels if specified
    if "module_levels" in config:
        for module, level in config["module_levels"].items():
            logging.getLogger(module).setLevel(level.upper())

    # Get application logger and log startup
    logger = logging.getLogger("grimwaves_api")
    logger.info("Application logging configured with secret masking")
    logger.debug("Log level set to %s", config["level"].upper())
    logger.debug("Log file: %s", log_dir / config["file"])

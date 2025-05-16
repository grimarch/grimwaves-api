import logging


def get_logger(module_name: str | None = None) -> logging.Logger:
    """Get a logger for the specified module.

    Args:
        module_name: The name of the module requesting a logger.
                     If None, returns the root application logger.

    Returns:
        A configured logger instance
    """
    if module_name:
        return logging.getLogger(f"grimwaves_api.{module_name}")
    return logging.getLogger("grimwaves_api")

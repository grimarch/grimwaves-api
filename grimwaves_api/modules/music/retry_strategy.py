"""Retry strategy management for Celery tasks.

This module provides utilities for managing retry strategies for Celery tasks,
with support for different error types and backoff algorithms.
"""

import random
from typing import Any, TypeVar, cast

from celery.app.task import Task  # Changed import

from grimwaves_api.core.logger import get_logger
from grimwaves_api.modules.music.constants import (
    DATA_RETRY_CONFIG,
    DEFAULT_RETRY_CONFIG,
    EVENT_LOOP_RETRY_CONFIG,
    NETWORK_RETRY_CONFIG,
)
from grimwaves_api.modules.music.schemas import RetryConfig

# Monkey patch Task for subscriptable type hints
Task.__class_getitem__ = classmethod(lambda cls, *args, **kwargs: cls)  # type: ignore[attr-defined] # pyright: ignore[reportAttributeAccessIssue]


# Initialize logger
logger = get_logger("modules.music.retry_strategy")

# Type variable for Task generic
TaskT = TypeVar("TaskT", bound=Task[Any, Any])


class RetryStrategy:
    """Strategy manager for Celery task retries.

    This class manages retry strategies for different types of exceptions
    in Celery tasks, providing configurable backoff and jitter.
    """

    @staticmethod
    def get_config_for_exception(exc: Exception) -> RetryConfig:
        """Get the appropriate retry config for an exception.

        Args:
            exc: The exception that caused the task to fail

        Returns:
            The retry configuration to use
        """
        from grimwaves_api.common.utils.asyncio_utils import classify_event_loop_error
        from grimwaves_api.modules.music.constants import (
            DATA_ERRORS,
            NETWORK_ERRORS,
        )

        # Check for event loop errors first using specialized classifier
        error_type = classify_event_loop_error(exc)
        if error_type:
            return EVENT_LOOP_RETRY_CONFIG

        # Check for network errors
        if isinstance(exc, NETWORK_ERRORS):
            return NETWORK_RETRY_CONFIG

        # Check for data errors
        if isinstance(exc, DATA_ERRORS):
            return DATA_RETRY_CONFIG

        # Default config for other errors
        return DEFAULT_RETRY_CONFIG

    @staticmethod
    def calculate_retry_delay(config: RetryConfig, retries: int) -> float:
        """Calculate the delay for the next retry.

        Args:
            config: The retry configuration to use
            retries: The current retry count (0-based)

        Returns:
            The delay in seconds for the next retry
        """
        # Base delay
        delay = config.base_delay

        # Apply exponential backoff if configured
        if config.use_exponential:
            # Use the formula: delay = base_delay * (backoff_factor ** retries)
            delay = config.base_delay * (config.backoff_factor**retries)
        else:
            # Linear backoff: delay = base_delay * backoff_factor * retries
            delay = config.base_delay + (config.backoff_factor * retries)

        # Add jitter if configured (up to 25% in either direction)
        if config.use_jitter:
            jitter_range = delay * 0.25  # 25% jitter
            delay = delay + random.uniform(-jitter_range, jitter_range)  # nosec B311

        # Cap at max_delay
        delay = min(delay, config.max_delay)

        # Ensure we never go below base_delay
        return max(delay, config.base_delay)

    @classmethod
    def retry_task(
        cls,
        task_instance: Task[Any, Any],  # type: ignore # Подавляем ошибку типизации для обратной совместимости
        exc: Exception,
        task_id: str | None = None,
        task_name: str | None = None,
    ) -> Any:
        """Retry a Celery task with the appropriate strategy.

        This method handles retrying a Celery task using the appropriate
        retry strategy for the exception that caused the failure.

        Args:
            task_instance: The Celery task instance
            exc: The exception that caused the task to fail
            task_id: Optional task ID for logging
            task_name: Optional task name for logging

        Returns:
            The result of task.retry() (never returns normally)

        Raises:
            The task.retry() call will raise an exception to trigger Celery's retry mechanism
        """
        # Get current retry count
        retries = task_instance.request.retries or 0

        # Get task identifying information for logs
        # Используем str() для обеспечения совместимости с различными типами task_instance.__class__.__name__
        task_name = task_name or str(getattr(task_instance.__class__, "__name__", "UnknownTask"))
        task_id = task_id or task_instance.request.id or "unknown"

        # Get appropriate config
        config = cls.get_config_for_exception(exc)

        # Check if max retries exceeded
        max_retries = getattr(task_instance, "max_retries", None) or config.max_retries
        if retries >= max_retries:
            logger.warning(
                "Task %s (%s) has reached maximum retries (%d/%d). Not retrying.",
                task_name,
                task_id,
                retries,
                max_retries,
            )
            # Re-raise the original exception to fail the task
            raise exc

        # Calculate delay
        delay = cls.calculate_retry_delay(config, retries)

        # Log the retry attempt
        logger.info(
            "Task %s (%s) failed with %s. Retry %d/%d with delay %.2fs",
            task_name,
            task_id,
            type(exc).__name__,
            retries + 1,
            max_retries,
            delay,
        )

        # Perform the retry
        # Cast to Any to satisfy mypy - Celery's retry() always raises an exception
        return cast(Any, task_instance.retry(exc=exc, countdown=delay))

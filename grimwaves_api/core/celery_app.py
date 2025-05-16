"""Celery application configuration for GrimWaves API.

This module provides the configuration for Celery tasks and worker
management in the GrimWaves API service.
"""

from typing import Any

from celery import Celery

from grimwaves_api.core.settings import settings

# Initialize Celery app
celery_app = Celery(
    "grimwaves_api",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_time_limit=settings.celery_task_time_limit,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_eager_propagates=settings.celery_task_eager_propagates,
    task_always_eager=settings.celery_task_always_eager,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    result_expires=3600,  # 1 hour
)

# Import all tasks so they're registered with the Celery app
# This will be filled in when we create the music module
# celery_app.autodiscover_tasks(["grimwaves_api.modules.music"])  # noqa: ERA001


def get_task_by_id(task_id: str) -> Any:
    """Get a Celery task by its ID.

    Args:
        task_id: The ID of the task to retrieve.

    Returns:
        The Celery task with the given ID, or None if not found.
    """
    return celery_app.AsyncResult(task_id)

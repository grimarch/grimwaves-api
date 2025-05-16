"""Router for music metadata endpoints."""

import json
from logging import Logger
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, status

from grimwaves_api.core.celery_app import get_task_by_id
from grimwaves_api.core.logger import get_logger
from grimwaves_api.modules.music.cache import cache
from grimwaves_api.modules.music.constants import ERROR_MESSAGES
from grimwaves_api.modules.music.helpers import (
    check_existing_result,
    map_celery_status_to_app_status,
    process_task_result,
)
from grimwaves_api.modules.music.schemas import (
    ErrorResponse,
    ReleaseMetadataRequest,
    ReleaseMetadataResponse,
    TaskResponse,
    TaskStatus,
    TaskStatusResponse,
)
from grimwaves_api.modules.music.tasks import fetch_release_metadata

if TYPE_CHECKING:
    from celery.result import AsyncResult

# Initialize module logger
logger: Logger = get_logger("modules.music.router")

# Create router
router: APIRouter = APIRouter(prefix="/music", tags=["Music Metadata"])


@router.post(
    path="/release_metadata",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Fetch music release metadata",
    description="Submit a task to fetch metadata for a music release by artist and release name",
    responses={
        status.HTTP_202_ACCEPTED: {
            "description": "Task accepted for processing",
            "model": TaskResponse,
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid request parameters",
            "model": ErrorResponse,
        },
    },
)
async def submit_release_metadata_task(request: ReleaseMetadataRequest) -> dict[str, Any]:
    """Submit task to fetch release metadata.

    This endpoint accepts a request with artist/band name and release name,
    and initiates an asynchronous task to gather metadata from various
    music services (Spotify, MusicBrainz, Deezer).

    Args:
        request: Validated request object containing band_name, release_name and optionally country_code

    Returns:
        Dictionary with task_id and status
    """
    # 📌 1. Проверяем: а вдруг итоговый объединённый результат уже в кеше?
    # Этот ключ генерируется Celery задачей tasks.py:fetch_metadata_complete_flow при сохранении полного результата
    merged_cache_key_name = (
        f"cache_{request.band_name}_{request.release_name}_{request.country_code or 'global'}".replace(" ", "_").lower()
    )

    # Используем merged_cache_key_name напрямую, т.к. cache.get_metadata_result добавит нужный префикс
    merged_result_payload = await cache.get_metadata_result(merged_cache_key_name)

    if merged_result_payload and merged_result_payload.get("status") == TaskStatus.SUCCESS:
        logger.info(
            "Found fully merged cached result for '%s' - '%s' under key '%s'",
            request.band_name,
            request.release_name,
            merged_cache_key_name,
        )
        return {
            "task_id": merged_cache_key_name,  # Возвращаем "чистое" имя ключа
            "status": TaskStatus.SUCCESS,
        }

    # 📌 2. Если полного объединённого кеша нет, проверяем, есть ли частичные данные.
    # check_existing_result теперь не кеширует сама, а только возвращает найденные частичные данные
    # из любого сконфигурированного источника (Spotify, MusicBrainz, Deezer).
    found_partial, prefetched_item = await check_existing_result(
        band_name=request.band_name,
        release_name=request.release_name,
        country_code=request.country_code,
    )

    task_init_data: dict[str, Any] = {
        "band_name": request.band_name,
        "release_name": request.release_name,
        "country_code": request.country_code,
        "prefetched_data_list": [],  # Initialize with an empty list
        "merged_cache_key_name": merged_cache_key_name,
    }

    if found_partial and prefetched_item:  # prefetched_item is a dict {"source": ..., "data": ...}
        logger.info(
            "Found prefetched data for '%s' - '%s' from source '%s'. Passing to Celery task. Summary: Artist: %s, Release: %s",
            request.band_name,
            request.release_name,
            prefetched_item.get("source"),
            prefetched_item.get("data", {}).get("artist"),  # Safely access nested data for logging
            prefetched_item.get("data", {}).get("release"),  # Safely access nested data for logging
        )
        task_init_data["prefetched_data_list"].append(prefetched_item)
    else:
        logger.info(
            "No usable prefetched data found for '%s' - '%s' after checking all sources. Submitting new Celery task.",
            request.band_name,
            request.release_name,
        )

    # 📌 3. Отправляем новую задачу Celery для сбора полных данных.
    # Celery-задача сама позаботится о кешировании полного результата под task_id (UUID)
    # и под предсказуемым ключом merged_cache_key_name.

    task_result: AsyncResult[Any] = fetch_release_metadata.delay(
        request_data=task_init_data,
    )

    logger.info(
        "Submitted new Celery task %s for band '%s', release '%s'",
        task_result.id,
        request.band_name,
        request.release_name,
    )

    return {
        "task_id": task_result.id,
        "status": TaskStatus.QUEUED,  # Всегда QUEUED, т.к. мы всегда создаем новую задачу если нет полного кеша
    }


@router.get(
    path="/release_metadata/{task_id}",
    summary="Get task status and results",
    description="Check the status of a metadata fetch task and retrieve the results if available",
    responses={
        status.HTTP_200_OK: {
            "description": "Task status and results",
            "model": TaskStatusResponse,
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Task not found",
            "model": ErrorResponse,
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid task ID",
            "model": ErrorResponse,
        },
    },
)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """Get the status and results of a metadata fetch task.

    This endpoint checks the status of an asynchronous task initiated
    by the POST /release_metadata endpoint and returns its current state.
    If the task is completed, the metadata results are included in the response.

    Args:
        task_id: The ID of the task to check

    Returns:
        TaskStatusResponse object with task status and results if available

    Raises:
        HTTPException: If the task ID is invalid or not found
    """
    # Check if task ID is valid
    if not task_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES["INVALID_TASK_ID"],
        )

    # Check if this is a cached result first (task_id starting with "cache_")
    if task_id.startswith("cache_"):
        # This is a cached result, try to retrieve it
        cached_data = await cache.get_metadata_result(task_id)
        if cached_data:
            # Return cached result with success status
            response = TaskStatusResponse(
                task_id=task_id,
                status=TaskStatus.SUCCESS,
                result=ReleaseMetadataResponse(**cached_data["result"]),
            )
            return response  # noqa: RET504

    # Before checking Celery, try to get the result from Redis cache
    try:
        cached_result: dict[str, Any] | None = await cache.get_metadata_result(task_id)
        if cached_result:
            logger.info("Found cached result for task %s", task_id)

            if cached_result.get("status") == "FAILURE":
                return TaskStatusResponse(
                    task_id=task_id,
                    status=TaskStatus.FAILURE,
                    result=None,
                    error=cached_result.get("error", "Metadata collection failed"),
                )

            try:
                # --- BEGIN ADDED LOGGING (raw dict) ---
                logger.debug(
                    "Task %s: Raw cached result dictionary before parsing: %s",
                    task_id,
                    json.dumps(cached_result.get("result"), indent=2, ensure_ascii=False),
                )
                # --- END ADDED LOGGING (raw dict) ---

                parsed: ReleaseMetadataResponse = ReleaseMetadataResponse(**cached_result["result"])
                logger.debug(
                    "Task %s: Parsed cached result into ReleaseMetadataResponse. Release field value: %s",
                    task_id,
                    parsed.release,
                )
            except Exception as e:
                logger.warning("Error parsing ReleaseMetadataResponse for task %s: %s", task_id, str(e))
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid cached response") from e

            return TaskStatusResponse(
                task_id=task_id,
                status=TaskStatus.SUCCESS,
                result=parsed,
                error=None,
            )
    except (ConnectionError, OSError, ValueError, KeyError, TypeError) as e:
        logger.warning("Error checking cache for task %s: %s", task_id, str(e))

    # Get the task by ID from Celery
    task_result = get_task_by_id(task_id)
    if task_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES["INVALID_TASK_ID"],
        )

    # Check task status
    _ = task_result.status.lower()

    # Map Celery task status to our status constants
    response_status: TaskStatus = map_celery_status_to_app_status(task_result.status)

    # Initialize response object
    response = TaskStatusResponse(
        task_id=task_id,
        status=response_status,
    )

    # Process task result
    await process_task_result(task_result, response)

    return response

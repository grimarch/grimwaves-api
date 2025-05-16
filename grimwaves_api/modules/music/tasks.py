"""Celery tasks for music metadata service.

This module contains Celery tasks for fetching and processing
music metadata from various external APIs.
"""

import json
from logging import Logger
from typing import Any, TypeVar, override

from celery import Task
from celery.utils.log import get_task_logger

from grimwaves_api.common.utils import run_async_safely
from grimwaves_api.common.utils.asyncio_utils import (
    classify_event_loop_error,
    diagnose_event_loop,
    handle_event_loop_error,
)
from grimwaves_api.core.celery_app import celery_app
from grimwaves_api.core.settings import settings
from grimwaves_api.modules.music.cache import cache
from grimwaves_api.modules.music.clients import DeezerClient, MusicBrainzClient, SpotifyClient
from grimwaves_api.modules.music.constants import (
    CACHE_ERRORS,
    DATA_ERRORS,
    RESOURCE_ERRORS,
    SYSTEM_ERRORS,
)
from grimwaves_api.modules.music.retry_strategy import RetryStrategy
from grimwaves_api.modules.music.schemas import (
    ArtistInfoSchema,
    ArtistSourceSpecificIds,
    ReleaseMetadataResponse,
    ReleaseMetadataTaskParameters,
    SocialLinks,
    TaskResult,
    TaskStatus,
    Track,
)
from grimwaves_api.modules.music.service import MusicMetadataService

# Setup logger
logger: Logger = get_task_logger(__name__)

# Type variable for async function return type
T = TypeVar("T")

# Define error type categories for better retry handling
TASK_NETWORK_ERRORS = (ConnectionError, TimeoutError)
API_ERRORS = (ValueError, KeyError)


# Disable type checking for missing type arguments
# pyright: reportMissingTypeArgument=false
class MetadataTask(Task):
    """Base class for metadata tasks."""

    track_started: bool = True
    track_finished: bool = True
    retry_backoff: bool = True
    retry_backoff_max: int = 600  # 10 minutes
    retry_jitter: bool = True
    max_retries: int | None = 3

    @override
    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Default run method to be overridden by the task implementation.

        This method must be implemented by task subclasses.

        Args:
            *args: Positional arguments passed to the task
            **kwargs: Keyword arguments passed to the task

        Returns:
            Result of the task execution

        Raises:
            NotImplementedError: If the subclass does not override this method
        """
        msg = "Task implementation missing"
        raise NotImplementedError(msg)

    @override
    def on_failure(self, exc: Exception, task_id: str, args: Any, kwargs: Any, einfo: Any) -> None:
        """Log the failure of the task with enhanced error context.

        Args:
            exc: Exception that caused the task to fail
            task_id: Celery task ID
            args: Task arguments
            kwargs: Task keyword arguments
            einfo: Exception information
        """
        # Determine error category for better context
        error_category = "UNKNOWN"
        if isinstance(exc, TASK_NETWORK_ERRORS):
            error_category = "NETWORK_ERROR"
        elif isinstance(exc, RESOURCE_ERRORS):
            error_category = "RESOURCE_ERROR"
        elif isinstance(exc, DATA_ERRORS):
            error_category = "DATA_ERROR"
        elif isinstance(exc, SYSTEM_ERRORS):
            error_category = "SYSTEM_ERROR"
        elif isinstance(exc, CACHE_ERRORS):
            error_category = "CACHE_ERROR"

        # Enhanced logging with error category
        logger.error(
            "Task %s failed: %s [%s]",
            task_id,
            exc,
            error_category,
            extra={
                "task_id": task_id,
                "task_args": args,
                "kwargs": kwargs,
                "exception": str(exc),
                "exception_type": exc.__class__.__name__,
                "error_category": error_category,
            },
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)

    @override
    def on_success(self, retval: Any, task_id: str, args: Any, kwargs: Any) -> None:
        """Log the success of the task."""
        logger.info(
            "Task %s succeeded",
            task_id,
            extra={
                "task_id": task_id,
                "task_args": args,
                "kwargs": kwargs,
            },
        )
        super().on_success(retval, task_id, args, kwargs)

    def process_metadata(self, metadata: dict[str, Any], request: ReleaseMetadataTaskParameters) -> TaskResult:
        """Process metadata retrieved from service into task result.

        Args:
            metadata: Raw metadata from service
            request: Original task parameters data

        Returns:
            Processed task result
        """
        print(f"[DEBUG_TASK_ARTIST_PRINT] Full metadata before processing: {json.dumps(metadata, indent=2)}")
        artist_data_from_metadata = metadata.get("artist")
        print(
            f"[DEBUG_TASK_ARTIST_PRINT] Type of artist_data_from_metadata: {type(artist_data_from_metadata)}, value: {json.dumps(artist_data_from_metadata, indent=2)}",
        )

        # Get metadata values with proper type handling and conversion
        tracks_data = metadata.get("tracks", [])
        # Create proper Track objects from dictionary data
        # tracks = [Track(title=track.get("title", ""), isrc=track.get("isrc")) for track in tracks_data]
        # Assuming tracks_data from service is already a list of dicts compatible with Track model
        processed_tracks: list[Track] = []
        if isinstance(tracks_data, list):
            for track_dict in tracks_data:
                if isinstance(track_dict, dict):
                    try:
                        processed_tracks.append(Track(**track_dict))
                    except Exception as e_track:
                        logger.warning("Failed to parse track data: %s. Error: %s", track_dict, e_track)
                else:
                    logger.warning("Skipping non-dictionary track item: %s", track_dict)
        else:
            logger.warning("Tracks data is not a list: %s", tracks_data)

        # Convert social links dictionary to SocialLinks model
        social_links_data = metadata.get("social_links", {})
        social_links = SocialLinks()
        if isinstance(social_links_data, dict):
            for key in ["instagram", "facebook", "twitter", "vk", "website", "youtube"]:
                if social_links_data.get(key):
                    setattr(social_links, key, social_links_data[key])
        else:
            logger.warning("Social links data is not a dict: %s", social_links_data)

        # Handle artist information
        artist_obj: ArtistInfoSchema

        if isinstance(artist_data_from_metadata, dict):
            try:
                # === START DIAGNOSTIC BLOCK ===
                print(
                    f"[DEBUG_TASK_ARTIST_PRINT] Raw artist_data_from_metadata: {json.dumps(artist_data_from_metadata, indent=2)}",
                )

                ids_data = artist_data_from_metadata.get("source_specific_ids")
                print(f"[DEBUG_TASK_ARTIST_PRINT] Extracted ids_data: {json.dumps(ids_data, indent=2)}")

                created_ids_obj = None
                if isinstance(ids_data, dict):
                    try:
                        created_ids_obj = ArtistSourceSpecificIds(**ids_data)
                        print(
                            f"[DEBUG_TASK_ARTIST_PRINT] Successfully created ArtistSourceSpecificIds: {created_ids_obj.model_dump_json(indent=2) if created_ids_obj else 'None'}",
                        )
                    except Exception as e_ids:
                        print(
                            f"[DEBUG_TASK_ARTIST_PRINT] Error creating ArtistSourceSpecificIds from {json.dumps(ids_data, indent=2)}: {e_ids}",
                        )

                artist_obj = ArtistInfoSchema(
                    name=artist_data_from_metadata.get("name", "Unknown Artist"),
                    source_specific_ids=created_ids_obj,
                )
                print(
                    f"[DEBUG_TASK_ARTIST_PRINT] Successfully created ArtistInfoSchema: {artist_obj.model_dump_json(indent=2)}",
                )
                # === END DIAGNOSTIC BLOCK ===
            except Exception as e:
                print(f"Error processing artist data: {e}. Data: {json.dumps(artist_data_from_metadata, indent=2)}")
                artist_obj = ArtistInfoSchema(name="Unknown Artist", source_specific_ids=None)
        elif isinstance(artist_data_from_metadata, str):
            print(f"Fallback: artist_data_from_metadata is a string: {artist_data_from_metadata}")
            artist_obj = ArtistInfoSchema(name=artist_data_from_metadata, source_specific_ids=None)
        else:
            print(
                f"Artist data is missing or in unexpected format: {artist_data_from_metadata}. Type: {type(artist_data_from_metadata)}",
            )
            artist_obj = ArtistInfoSchema(name="Unknown Artist", source_specific_ids=None)

        # Prepare success response
        return TaskResult(
            status=TaskStatus.SUCCESS,
            result=ReleaseMetadataResponse(
                artist=artist_obj,  # Use the processed ArtistInfoSchema object
                # Use ONLY 'release' from metadata. Assumes 'release' key exists.
                release=metadata["release"],  # Changed from .get("release")
                release_date=metadata.get("release_date"),
                label=metadata.get("label"),
                genre=metadata.get("genre", []),
                tracks=processed_tracks,
                social_links=social_links,
            ),
        )

    async def check_cache(self, task_id: str) -> dict[str, Any] | None:
        """Check if result exists in cache.

        Args:
            task_id: Task ID to check

        Returns:
            Cached result if found, None otherwise
        """
        try:
            return await cache.get_metadata_result(task_id)
        except Exception as e:
            logger.warning("Error checking cache: %s", str(e))
            return None

    def check_cache_sync(self, task_id: str) -> dict[str, Any] | None:
        """Synchronous wrapper for check_cache.

        Creates a new event loop for each call to ensure thread safety.

        Args:
            task_id: Task ID to check

        Returns:
            Cached result if found, None otherwise
        """
        # Преобразуем результат в Any и затем безопасно приводим к нужному типу
        result: Any = run_async_safely(self.check_cache, task_id)
        return result

    async def cache_result(
        self,
        task_id: str,
        result: dict[str, Any],
        is_error: bool = False,
    ) -> None:
        """Cache task result.

        Args:
            task_id: Task ID
            result: Result data to cache
            is_error: Whether this is an error result
        """
        try:
            await cache.cache_metadata_result(task_id, result, is_error)
        except Exception as e:
            logger.warning("Error caching result: %s", str(e))

    def cache_result_sync(self, task_id: str, result: dict[str, Any], is_error: bool = False) -> None:
        """Synchronous wrapper for cache_result.

        Creates a new event loop for each call to ensure thread safety.

        Args:
            task_id: Task ID
            result: Result data to cache
            is_error: Whether this is an error result
        """
        # Добавляем явное присваивание, чтобы успокоить линтер
        _ = run_async_safely(self.cache_result, task_id, result, is_error)

    async def fetch_metadata_complete_flow(
        self,
        task_id: str | None,
        request_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Complete flow for fetching, processing and caching metadata.

        This function combines all asynchronous operations:
        1. Cache checking
        2. API client creation
        3. Metadata retrieval
        4. Result processing and caching

        Args:
            task_id: Celery task ID
            request_data: Raw request data dictionary

        Returns:
            Processed and cached task result in dictionary format
        """
        if not task_id:  # Should ideally always be present when called from a task
            logger.warning("fetch_metadata_complete_flow called without a task_id.")

        try:
            task_params = ReleaseMetadataTaskParameters(**request_data)
        except Exception as e_val:
            logger.error(
                "Task data validation error for task %s: %s. Data: %s",
                task_id,
                e_val,
                request_data,
                exc_info=True,
            )
            error_result = TaskResult(
                status=TaskStatus.FAILURE,
                error=f"Invalid task parameters: {e_val}",
                error_type=e_val.__class__.__name__,
            )
            if task_id:
                await self.cache_result(task_id, error_result.model_dump(), is_error=True)
            return error_result.model_dump()

        if task_id:
            cached_task_status_result = await self.check_cache(task_id)
            if cached_task_status_result:
                logger.info("Task %s: Found result in cache.", task_id)
                try:
                    parsed_cached_result = TaskResult(**cached_task_status_result)
                    return parsed_cached_result.model_dump()
                except Exception as e_parse_cache:
                    logger.warning(
                        "Task %s: Error parsing cached result: %s. Cache content: %s. Will refetch.",
                        task_id,
                        e_parse_cache,
                        cached_task_status_result,
                    )

        logger.info("Task %s: No result in cache, proceeding with fetch", task_id or "N/A")

        service: MusicMetadataService | None = None
        spotify_client: SpotifyClient | None = None
        deezer_client: DeezerClient | None = None
        musicbrainz_client: MusicBrainzClient | None = None
        metadata_result: dict[str, Any] = {}
        task_status_result: TaskResult

        try:
            async with (
                SpotifyClient(  # type: ignore[var-annotated]
                    client_id=settings.spotify_client_id,
                    client_secret=settings.spotify_client_secret,
                ) as spotify_client,
                DeezerClient(  # type: ignore[var-annotated]
                    api_base_url=settings.deezer_api_base_url,
                ) as deezer_client,
                MusicBrainzClient(  # type: ignore[var-annotated]
                    app_name=settings.musicbrainz_app_name,
                    app_version=settings.musicbrainz_app_version,
                    contact=settings.musicbrainz_contact,
                ) as musicbrainz_client,
            ):
                if spotify_client is None:
                    msg = "Spotify client should be initialized by context manager"
                    raise AssertionError(msg)
                if deezer_client is None:
                    msg = "Deezer client should be initialized by context manager"
                    raise AssertionError(msg)
                if musicbrainz_client is None:
                    msg = "MusicBrainz client should be initialized by context manager"
                    raise AssertionError(msg)

                service = MusicMetadataService(
                    spotify_client=spotify_client,
                    deezer_client=deezer_client,
                    musicbrainz_client=musicbrainz_client,
                )

                country_code = task_params.country_code

                # --- ADDED DEBUG LOG ---
                logger.info(
                    "[TASK_DEBUG] Task %s: prefetched_data_list before service call: %s (Type: %s, IsEmptyList: %s, IsNone: %s)",
                    self.request.id,
                    task_params.prefetched_data_list,
                    type(task_params.prefetched_data_list),
                    task_params.prefetched_data_list == [],
                    task_params.prefetched_data_list is None,
                )
                # --- END ADDED DEBUG LOG ---

                logger.info(
                    "Calling service.fetch_release_metadata for task %s with band: '%s', release: '%s', country: '%s', prefetched_list_present: %s",
                    self.request.id,
                    task_params.band_name,
                    task_params.release_name,
                    country_code,
                    task_params.prefetched_data_list is not None,
                )
                metadata_result = await service.fetch_release_metadata(
                    band_name=task_params.band_name,
                    release_name=task_params.release_name,
                    country_code=country_code,
                    prefetched_data_list=task_params.prefetched_data_list,
                )
                # --- BEGIN ADDED CHECK FOR "NOT FOUND" ---
                tracks_found = bool(metadata_result.get("tracks"))
                release_ids_found = any(
                    [
                        metadata_result.get("source_spotify_id"),
                        metadata_result.get("source_musicbrainz_id"),
                        metadata_result.get("source_deezer_id"),
                    ],
                )
                artist_info = metadata_result.get("artist", {})
                artist_ids_found = False
                if isinstance(artist_info, dict):
                    artist_source_ids = artist_info.get("source_specific_ids", {})
                    if isinstance(artist_source_ids, dict):
                        artist_ids_found = any(
                            [
                                artist_source_ids.get("spotify_artist_id"),
                                artist_source_ids.get("musicbrainz_artist_id"),
                                artist_source_ids.get("deezer_artist_id"),
                            ],
                        )

                if not tracks_found and not release_ids_found and not artist_ids_found:
                    logger.warning(
                        "Task %s: No meaningful data found for '%s' - '%s'. Returning FAILURE.",
                        task_id or "N/A",
                        task_params.band_name,
                        task_params.release_name,
                    )
                    task_status_result = TaskResult(
                        status=TaskStatus.FAILURE,
                        error=f"No data found for artist '{task_params.band_name}' and release '{task_params.release_name}' from any source.",
                        error_type="NotFoundError",
                    )
                else:
                    task_status_result = self.process_metadata(metadata_result, task_params)
                # --- END ADDED CHECK FOR "NOT FOUND" ---

        except Exception as e:
            logger.error(
                "Error during metadata fetch or processing for task %s: %s",
                task_id or "N/A",
                str(e),
                exc_info=True,
            )
            task_status_result = TaskResult(
                status=TaskStatus.FAILURE,
                error=str(e),
                error_type=e.__class__.__name__,
            )
        finally:
            # Ensure clients are closed in all scenarios (success or error)
            if service and hasattr(service, "close") and callable(service.close):
                try:
                    await service.close()
                except Exception as e_service_close:
                    logger.warning(f"Error closing MusicMetadataService: {e_service_close}")

            if spotify_client:
                try:
                    await spotify_client.close()
                except Exception as e_spotify_close:
                    logger.warning(f"Error closing SpotifyClient: {e_spotify_close}")

            if deezer_client:
                try:
                    await deezer_client.close()
                except Exception as e_deezer_close:
                    logger.warning(f"Error closing DeezerClient: {e_deezer_close}")

            if musicbrainz_client:
                try:
                    await musicbrainz_client.close()
                except Exception as e_mb_close:
                    logger.warning(f"Error closing MusicBrainzClient: {e_mb_close}")

        if task_id:
            await self.cache_result(
                task_id,
                task_status_result.model_dump(),
                is_error=(task_status_result.status == TaskStatus.FAILURE),
            )

        # Cache by merged_cache_key_name if available and task was successful
        if task_params.merged_cache_key_name and task_status_result.status == TaskStatus.SUCCESS:
            logger.info(
                "Task %s: Attempting to cache result by merged_cache_key_name: %s",
                task_id or "N/A",
                task_params.merged_cache_key_name,
            )
            await self.cache_result(
                task_params.merged_cache_key_name,
                task_status_result.model_dump(),  # Save the same full TaskResult object
                is_error=False,  # Only cache successful results by this key
            )
            logger.info(
                "Task %s: Successfully cached result by merged_cache_key_name: %s",
                task_id or "N/A",
                task_params.merged_cache_key_name,
            )

        logger.info("Task %s %s", task_id or "N/A", task_status_result.status.value)
        return task_status_result.model_dump()


@celery_app.task(
    bind=True,
    base=MetadataTask,
    name="music.fetch_release_metadata",
    max_retries=3,
    default_retry_delay=5,
    retry_backoff=True,
    retry_jitter=True,
)
def fetch_release_metadata(
    self: MetadataTask,
    request_data: dict[str, Any],
) -> dict[str, Any]:
    """Fetch music metadata for a release.

    This task retrieves metadata for a music release from various external APIs,
    including Spotify, MusicBrainz, and optionally Deezer. The data is aggregated
    and processed into a standardized format.

    Args:
        self: Task instance
        request_data: Serialized ReleaseMetadataRequest data

    Returns:
        Processed release metadata in TaskResult format
    """
    task_id = self.request.id
    if not task_id:
        logger.warning("Task ID is missing, caching will be disabled")

    max_length = 200
    logger.info(
        "Starting fetch_release_metadata task %s with data: %s",
        task_id or "unknown",
        json.dumps(request_data)[:max_length] + "..."
        if len(json.dumps(request_data)) > max_length
        else json.dumps(request_data),
    )

    try:
        # Execute the complete metadata flow with a single run_async_safely call
        # This replaces the previous three separate calls to run_async_safely
        # Явно задаем тип возвращаемого значения для успокоения линтера
        result: dict[str, Any] = run_async_safely(self.fetch_metadata_complete_flow, task_id, request_data)
        return result

    except Exception as exc:
        # First, check if it's an event loop error
        error_type = classify_event_loop_error(exc)

        if error_type:
            # It's an event loop error, get diagnostics
            diagnostics = diagnose_event_loop()

            logger.exception(
                "Event loop error in fetch_release_metadata task: %s. Type: %s. Diagnostics: %s",
                str(exc),
                error_type,
                diagnostics,
            )

            # Create error result
            error_result = TaskResult(
                status=TaskStatus.FAILURE,
                error=str(exc),
                error_type=f"EVENT_LOOP_{error_type.upper()}",
            )

            # Try to recover from the error
            recovery_attempted = handle_event_loop_error(error_type, diagnostics)

            if task_id:
                self.cache_result_sync(task_id, error_result.model_dump(), is_error=True)

                # If recovery was attempted, try to run the function again immediately
                if recovery_attempted:
                    logger.info(
                        "Recovery attempted for event loop error. Retrying immediately for task %s",
                        task_id or "unknown",
                    )

                    try:
                        # Try again immediately after recovery
                        recovery_result: dict[str, Any] = run_async_safely(
                            self.fetch_metadata_complete_flow,
                            task_id,
                            request_data,
                        )
                        return recovery_result
                    except Exception as retry_exc:
                        # If recovery failed, log and proceed with advanced retry mechanism
                        logger.exception(
                            "Recovery failed for event loop error: %s. Using optimized retry strategy.",
                            str(retry_exc),
                        )
                        # Use the optimized retry strategy with the original exception
                        return RetryStrategy.retry_task(self, exc, task_id, "fetch_release_metadata")

            return error_result.model_dump()

        # Cache the error result first to ensure it's available
        error_result = TaskResult(
            status=TaskStatus.FAILURE,
            error=str(exc),
            error_type=type(exc).__name__,
        )

        if task_id:
            self.cache_result_sync(task_id, error_result.model_dump(), is_error=True)

        # Use the unified retry strategy
        return RetryStrategy.retry_task(self, exc, task_id, "fetch_release_metadata")

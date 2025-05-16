"""Helper functions for the music metadata module."""

import json
from typing import TYPE_CHECKING, Any, LiteralString

from grimwaves_api.core.logger import get_logger
from grimwaves_api.modules.music.cache import cache
from grimwaves_api.modules.music.constants import ERROR_MESSAGES
from grimwaves_api.modules.music.schemas import (
    ReleaseMetadataResponse,
    TaskStatus,
    TaskStatusResponse,
    Track,
)

if TYPE_CHECKING:
    from celery.result import AsyncResult

# Initialize logger for helpers
logger = get_logger("modules.music.helpers")

SOURCES_TO_PRECHECK: list[str] = ["musicbrainz", "spotify", "deezer"]


def map_celery_status_to_app_status(celery_status: str) -> TaskStatus:
    """Map Celery task status to application status.

    Args:
        celery_status: The status string from Celery

    Returns:
        The corresponding application TaskStatus enum value
    """
    match celery_status.lower():
        case "pending":
            return TaskStatus.PENDING
        case "started":
            return TaskStatus.STARTED
        case "retry":
            return TaskStatus.RETRY
        case "success":
            return TaskStatus.SUCCESS
        case "failure":
            return TaskStatus.FAILURE
        case _:  # Default to PENDING for unknown status
            logger.warning("Unknown Celery task status received: %s", celery_status)
            return TaskStatus.PENDING


def _transform_spotify_cached_data(release_details: dict[str, Any]) -> dict[str, Any] | None:
    """Transform raw Spotify cached data into a standardized partial data format."""
    try:
        artist_data = release_details.get("artists", [{}])[0]
        artist_name = artist_data.get("name", "Unknown Artist")
        spotify_artist_id = artist_data.get("id")

        release_name_transformed = release_details.get("name", "Unknown Release")
        spotify_album_id = release_details.get("id")
        spotify_url = release_details.get("external_urls", {}).get("spotify")
        album_type = release_details.get("album_type")

        cover_art_url = None
        images = release_details.get("images", [])
        if images:
            # Prefer larger images, but take the first one if specific sizes aren't found
            # Spotify typically provides images in decreasing order of size.
            cover_art_url = images[0].get("url")

        track_items = release_details.get("tracks", {}).get("items", [])
        tracks_list = [
            Track(
                title=track.get("name", "Unknown Track"),
                isrc=track.get("external_ids", {}).get("isrc"),
                position=track.get("track_number"),
                duration_ms=track.get("duration_ms"),
                # Store Spotify track ID in a source-specific way if needed later
                source_specific_ids={"spotify_track_id": track.get("id")},
            ).model_dump(exclude_none=True)  # Use exclude_none to keep payload clean
            for track in track_items
        ]

        # Basic validation
        if artist_name == "Unknown Artist" or release_name_transformed == "Unknown Release" or not spotify_album_id:
            logger.warning(
                "Essential Spotify data missing for transform: artist '%s', release '%s', id '%s'",
                artist_name,
                release_name_transformed,
                spotify_album_id,
            )
            return None

        return {
            "artist": {"name": artist_name},  # Store artist as an object
            "release_title": release_name_transformed,
            "release_date": release_details.get("release_date"),
            "label": release_details.get("label"),
            "genres": release_details.get("genres", []),  # Spotify genres are at album level
            "tracks": tracks_list,
            "album_type": album_type,
            # Spotify API for album doesn't directly provide release country easily, usually it's via artist
            # or market availability
            "country": None,
            "source_specific_ids": {
                "spotify_album_id": spotify_album_id,
                "spotify_artist_id": spotify_artist_id,
            },
            "urls": {"spotify_url": spotify_url},
            "cover_art_url": cover_art_url,
            "additional_details": {
                # If we want to store all artists:
                # "spotify_artists_full": release_details.get("artists", []),
                "raw_spotify_album_type": release_details.get("album_type"),  # Keep raw if needed
                "spotify_popularity": release_details.get("popularity"),  # Example of another detail
            },
            # social_links are generally not available at Spotify album level
            "social_links": {},
        }
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.error(
            "Error transforming cached Spotify release details: %s. Details: %s",
            e,
            release_details,
            exc_info=True,
        )
        return None


def _transform_musicbrainz_cached_data(raw_mb_data: dict[str, Any]) -> dict[str, Any] | None:
    """Transform raw MusicBrainz cached data into a standardized partial data format."""
    try:
        logger.debug(
            "[DEBUG_TRANSFORM_MB] Attempting to transform MusicBrainz data: %s",
            json.dumps(raw_mb_data, indent=2, ensure_ascii=False),
        )

        musicbrainz_release_id = raw_mb_data.get("id")
        release_group_info = raw_mb_data.get("release-group", {})
        musicbrainz_release_group_id = release_group_info.get("id")

        # Artist
        artist_name = "Unknown Artist"
        musicbrainz_artist_id = None
        artist_credit_list = raw_mb_data.get("artist-credit", [])
        if artist_credit_list and isinstance(artist_credit_list, list):
            first_artist_credit = artist_credit_list[0]
            if isinstance(first_artist_credit, dict):
                artist_info = first_artist_credit.get("artist")
                if isinstance(artist_info, dict):
                    artist_name = artist_info.get("name", "Unknown Artist")
                    musicbrainz_artist_id = artist_info.get("id")

        # Release Name
        release_name_transformed = raw_mb_data.get("title", "Unknown Release")
        release_disambiguation = raw_mb_data.get("disambiguation")

        # Release Date
        release_date_str = raw_mb_data.get("date")
        country = raw_mb_data.get("country")
        status = raw_mb_data.get("status")
        barcode = raw_mb_data.get("barcode")
        packaging = raw_mb_data.get("packaging")

        album_type = release_group_info.get("primary-type")
        if not album_type:
            album_type = release_group_info.get("type")  # Fallback, though primary-type is preferred

        secondary_types = release_group_info.get("secondary-types", [])

        # Label
        label_name = None
        label_info_list = raw_mb_data.get("label-info", [])
        if label_info_list and isinstance(label_info_list, list):
            first_label_info = label_info_list[0]
            if isinstance(first_label_info, dict):
                label_detail = first_label_info.get("label")
                if isinstance(label_detail, dict):
                    label_name = label_detail.get("name")

        # Genres from tags and release-group/genres
        genres_list_final = []
        tags = raw_mb_data.get("tags", [])
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, dict) and tag.get("name") and tag["name"] not in genres_list_final:
                    genres_list_final.append(tag["name"])

        rg_genres = release_group_info.get("genres", [])
        if isinstance(rg_genres, list):
            for genre_info in rg_genres:
                if (
                    isinstance(genre_info, dict)
                    and genre_info.get("name")
                    and genre_info["name"] not in genres_list_final
                ):
                    genres_list_final.append(genre_info["name"])

        # Tracks
        tracks_data_final = []
        media_list = raw_mb_data.get("media", [])
        if isinstance(media_list, list):
            for medium in media_list:
                if isinstance(medium, dict):
                    tracks_in_medium = medium.get("tracks", [])
                    if isinstance(tracks_in_medium, list):
                        for track_item_data in tracks_in_medium:
                            if isinstance(track_item_data, dict):
                                title = track_item_data.get("title", "Unknown Track")
                                position = track_item_data.get("position") or track_item_data.get("number")
                                length_ms = None
                                recording_info = track_item_data.get("recording", {})
                                length_str = recording_info.get("length") or track_item_data.get("length")
                                if length_str and isinstance(length_str, (int, float)):
                                    length_ms = int(
                                        length_str,
                                    )  # Assuming it's already in ms or needs conversion based on typical MB data
                                    # If MB provides length in other units, conversion logic is needed here.
                                    # For now, assuming direct ms or a numeric value that can be used.

                                musicbrainz_recording_id = recording_info.get("id")

                                isrc = None
                                isrcs_list = recording_info.get("isrcs")
                                if isinstance(isrcs_list, list) and isrcs_list:
                                    isrc = isrcs_list[0]

                                tracks_data_final.append(
                                    Track(
                                        title=title,
                                        isrc=isrc,
                                        position=position,
                                        duration_ms=length_ms,
                                        source_specific_ids={"musicbrainz_recording_id": musicbrainz_recording_id},
                                    ).model_dump(exclude_none=True),
                                )

        if (
            artist_name == "Unknown Artist"
            or release_name_transformed == "Unknown Release"
            or not musicbrainz_release_id
        ):
            logger.warning(
                "[DEBUG_TRANSFORM_MB] Essential MusicBrainz data missing for transform: artist '%s', release '%s', id '%s'.",  # noqa: E501
                artist_name,
                release_name_transformed,
                musicbrainz_release_id,
            )
            return None

        transformed_data = {
            "artist": {"name": artist_name},
            "release_title": release_name_transformed,
            "release_date": release_date_str,
            "label": label_name,
            "genres": genres_list_final,
            "tracks": tracks_data_final,
            "album_type": album_type,
            "country": country,
            "source_specific_ids": {
                "musicbrainz_release_id": musicbrainz_release_id,
                "musicbrainz_release_group_id": musicbrainz_release_group_id,
                "musicbrainz_artist_id": musicbrainz_artist_id,
            },
            "urls": {},  # MusicBrainz URLs are usually constructed from IDs by the service
            "cover_art_url": None,  # Usually fetched separately by service using MB release ID
            "additional_details": {
                "musicbrainz_status": status,
                "musicbrainz_barcode": barcode,
                "musicbrainz_packaging": packaging,
                "musicbrainz_disambiguation": release_disambiguation,
                "musicbrainz_secondary_types": secondary_types,
                "musicbrainz_artist_credits_full": artist_credit_list,  # Store full artist credits if needed
            },
            "social_links": {},  # MusicBrainz doesn't typically provide these directly for a release
        }
        logger.info(
            "[DEBUG_TRANSFORM_MB] Successfully transformed MusicBrainz data for release ID %s",
            musicbrainz_release_id,
        )
        return transformed_data

    except Exception as e:  # Broader exception catch for unexpected issues during transformation
        logger.error(
            "[DEBUG_TRANSFORM_MB] Unexpected error transforming MusicBrainz release details for ID %s: %s. Details: %s",
            raw_mb_data.get("id", "N/A"),
            e,
            json.dumps(raw_mb_data, indent=2, ensure_ascii=False),
            exc_info=True,
        )
        return None


async def _transform_deezer_cached_data(
    raw_deezer_data: dict[str, Any],
    country_code: str | None,
) -> dict[str, Any] | None:
    """Transform raw Deezer cached data into a standardized partial data format."""
    try:
        logger.debug(
            "[DEBUG_TRANSFORM_DEEZER] Attempting to transform Deezer data: %s",
            json.dumps(raw_deezer_data, indent=2, ensure_ascii=False),
        )

        deezer_album_id = raw_deezer_data.get("id")

        artist_info = raw_deezer_data.get("artist", {})
        artist_name = artist_info.get("name", "Unknown Artist")
        deezer_artist_id = artist_info.get("id")

        release_name_transformed = raw_deezer_data.get("title", "Unknown Release")
        release_date_str = raw_deezer_data.get("release_date")  # Expected format "YYYY-MM-DD"
        deezer_url = raw_deezer_data.get("link")
        record_type = raw_deezer_data.get("record_type")  # e.g., "album", "single", "ep"

        cover_art_url = raw_deezer_data.get("cover_xl")  # Prefer XL
        if not cover_art_url:
            cover_art_url = raw_deezer_data.get("cover_big")
        if not cover_art_url:
            cover_art_url = raw_deezer_data.get("cover_medium")
        if not cover_art_url:
            cover_art_url = raw_deezer_data.get("cover")  # Smallest

        label_name = raw_deezer_data.get("label")
        barcode_upc = raw_deezer_data.get("upc")
        explicit_lyrics = raw_deezer_data.get("explicit_lyrics")
        fans_count = raw_deezer_data.get("fans")

        genres_list_final = []
        raw_genres_field = raw_deezer_data.get("genres")
        if isinstance(raw_genres_field, dict):
            genres_data = raw_genres_field.get("data", [])
        else:
            genres_data = []
            if raw_genres_field is not None:
                logger.warning(
                    "[DEBUG_TRANSFORM_DEEZER] 'genres' field was not a dictionary for release ID %s. Got: %s",
                    deezer_album_id,
                    type(raw_genres_field),
                )

        if isinstance(genres_data, list):
            for genre_item in genres_data:
                if isinstance(genre_item, dict) and genre_item.get("name"):
                    genres_list_final.append(genre_item["name"])

        tracks_data_final = []
        raw_tracks_field = raw_deezer_data.get("tracks")
        if isinstance(raw_tracks_field, dict):
            tracks_list_raw = raw_tracks_field.get("data", [])
        else:
            tracks_list_raw = []
            if raw_tracks_field is not None:
                logger.warning(
                    "[DEBUG_TRANSFORM_DEEZER] 'tracks' field was not a dictionary for release ID %s. Got: %s",
                    deezer_album_id,
                    type(raw_tracks_field),
                )

        if isinstance(tracks_list_raw, list):
            for track_item_data in tracks_list_raw:
                if isinstance(track_item_data, dict):
                    if not track_item_data:  # If the dict is empty, skip it
                        continue
                    title = track_item_data.get("title_short", track_item_data.get("title", "Unknown Track"))
                    isrc = track_item_data.get("isrc")
                    position = track_item_data.get("track_position")
                    disk_number = track_item_data.get("disk_number")
                    # If disk_number is relevant, position might need to be combined or handled specially
                    # For now, taking track_position directly if available.

                    duration_seconds = track_item_data.get("duration")
                    duration_ms = int(duration_seconds * 1000) if duration_seconds is not None else None

                    deezer_track_id = track_item_data.get("id")
                    rank = track_item_data.get("rank")

                    tracks_data_final.append(
                        Track(
                            title=title,
                            isrc=isrc,
                            position=position,  # May need adjustment if using disk_number
                            duration_ms=duration_ms,
                            source_specific_ids={"deezer_track_id": deezer_track_id},
                            additional_details_track={"deezer_rank": rank, "deezer_disk_number": disk_number},
                        ).model_dump(exclude_none=True),
                    )

        if artist_name == "Unknown Artist" or release_name_transformed == "Unknown Release" or not deezer_album_id:
            logger.warning(
                "[DEBUG_TRANSFORM_DEEZER] Essential Deezer data missing for transform: artist '%s', release '%s', id '%s'.",
                artist_name,
                release_name_transformed,
                deezer_album_id,
            )
            return None

        return {
            "artist": {"name": artist_name},
            "release_title": release_name_transformed,
            "release_date": release_date_str,
            "label": label_name,
            "genres": genres_list_final,
            "tracks": tracks_data_final,
            "album_type": record_type,
            "country": None,  # Deezer API for album doesn't directly provide release country
            "source_specific_ids": {
                "deezer_album_id": deezer_album_id,
                "deezer_artist_id": deezer_artist_id,
            },
            "urls": {"deezer_url": deezer_url},
            "cover_art_url": cover_art_url,
            "additional_details": {
                "deezer_barcode": barcode_upc,
                "deezer_explicit_lyrics": explicit_lyrics,
                "deezer_fans": fans_count,
                # "deezer_contributors": raw_deezer_data.get("contributors", []) # Example if we need all contributors
            },
            "social_links": {},
        }
    except Exception as e:
        logger.error(
            "[DEBUG_TRANSFORM_DEEZER] Unexpected error transforming Deezer release details for ID %s: %s. Details: %s",
            raw_deezer_data.get("id", "N/A"),
            e,
            json.dumps(raw_deezer_data, indent=2, ensure_ascii=False),
            exc_info=True,
        )
        return None


async def process_task_result(task_result: "AsyncResult[Any]", response: TaskStatusResponse) -> None:
    """Process task result and update response object.

    Args:
        task_result: AsyncResult object from Celery
        response: TaskStatusResponse object to update
    """
    task_status: LiteralString = task_result.status.lower()

    # If task is successful, include result data
    if task_status == "success":
        result: Any | BaseException = task_result.result

        # Check if the result indicates an error (e.g., from within the task)
        if isinstance(result, dict) and "error" in result:
            response.status = TaskStatus.FAILURE
            response.error = str(result.get("error", "Unknown error during task execution"))
            logger.error("Task %s reported failure with error: %s", task_result.id, response.error)
        elif isinstance(result, dict):
            # If the result is a dictionary, try converting it to ReleaseMetadataResponse
            try:
                logger.debug(
                    "Task %s completed successfully. Raw result dictionary before parsing: %s",
                    task_result.id,
                    json.dumps(result, indent=2, ensure_ascii=False),  # Use ensure_ascii=False for non-latin chars
                )
                response.result = ReleaseMetadataResponse(**result)
                # Cache the successful result upon processing
                try:
                    await cache.cache_metadata_result(task_result.id, {"status": "SUCCESS", "result": result})
                except Exception as cache_err:
                    logger.warning("Failed to cache successful result for task %s: %s", task_result.id, str(cache_err))
            except (ValueError, TypeError) as e:
                response.status = TaskStatus.FAILURE
                response.error = (
                    f"Failed to parse successful result for task {task_result.id}: {e}. Raw result: {result}"
                )
                logger.error(
                    "Error parsing successful result for task %s: %s. Raw result: %s",
                    task_result.id,
                    e,
                    result,
                    exc_info=True,
                )
        else:
            # If the result is not a dictionary, this indicates an error or unexpected format
            response.status = TaskStatus.FAILURE
            response.error = f"Task completed but returned incompatible data format: {type(result)}"
            logger.warning(
                "Task %s result has unexpected type: %s. Raw result: %s",
                task_result.id,
                type(result),
                result,
            )

    # If task failed in Celery, include error message
    elif task_status == "failure":
        exception = task_result.result
        response.error = str(exception) if exception else ERROR_MESSAGES["TASK_FAILED"].format(error="Unknown error")
        logger.error("Task %s failed with exception: %s", task_result.id, response.error)
        # Cache the failure status
        try:
            await cache.cache_metadata_result(task_result.id, {"status": "FAILURE", "error": response.error})
        except Exception as cache_err:
            logger.warning("Failed to cache failure status for task %s: %s", task_result.id, str(cache_err))

    # Note: Other statuses like RETRY, STARTED, PENDING are handled by map_celery_status_to_app_status
    # and don't typically have a result to process here.


async def check_existing_result(
    band_name: str,
    release_name: str,
    country_code: str | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    """Check for existing result in cache for similar queries from multiple sources.

    Searches configured sources (Spotify, MusicBrainz, Deezer) cache for similar searches
    and checks if the full release metadata for those results is already cached.
    This function NO LONGER caches the transformed result itself. It only returns
    the potentially transformable data with its source.

    Args:
        band_name: Name of the artist/band
        release_name: Name of the release
        country_code: Optional country code

    Returns:
        Tuple containing:
        - Boolean indicating if a transformed result was found
        - Transformed metadata dictionary (including source) if found, None otherwise
          e.g. {"source": "spotify", "data": {...}}
    """
    try:
        for source in SOURCES_TO_PRECHECK:
            logger.debug(
                "[DEBUG_CHECK] Iterating SOURCES_TO_PRECHECK. Current source: %s for %s - %s",
                source,
                band_name,
                release_name,
            )
            logger.debug(
                "[DEBUG_CHECK] Checking pre-existing result for source: %s for %s - %s",
                source,
                band_name,
                release_name,
            )

            # Унифицированная логика для поиска в кеше результатов поиска
            # Используем country_code только если он предоставлен, cache.get_search_results должен это учитывать
            cache_search_params = {
                "source": source,
                "band_name": band_name,
                "release_name": release_name,
            }
            if country_code:  # Spotify (и, возможно, Deezer в будущем) может его использовать
                cache_search_params["country_code"] = country_code

            # Ожидаем, что get_search_results возвращает list[dict] или None
            # search_cache_hits: list[dict[str, Any]] | None = await cache.get_search_results(**cache_search_params)
            # Передаем аргументы позиционно, как ожидает метод
            search_cache_hits: list[dict[str, Any]] | None = await cache.get_search_results(
                source,
                band_name,
                release_name,
                country_code,  # Используем country_code напрямую из аргументов check_existing_result
            )

            if not search_cache_hits:
                logger.debug("No similar %s search results found in cache for %s - %s", source, band_name, release_name)
                continue  # Try next source

            logger.debug("Found %d similar %s search results in cache.", len(search_cache_hits), source)

            for item in search_cache_hits[:5]:  # Limit checks to first few hits
                release_id = item.get("id")
                if not release_id:
                    logger.warning("%s search item missing 'id': %s", source.capitalize(), json.dumps(item, indent=2))
                    continue

                logger.debug("[DEBUG_CHECK] Attempting to get %s release details for ID %s", source, release_id)

                # country_code is NOT passed here as get_release_details doesn't take it
                # Explicitly pass only known parameters to get_release_details
                release_details = await cache.get_release_details(source=source, release_id=release_id)

                if release_details:
                    logger.debug("Found cached %s release details for ID: %s", source, release_id)
                    transformed_data = None
                    if source == "spotify":
                        transformed_data = _transform_spotify_cached_data(release_details)
                    elif source == "musicbrainz":
                        transformed_data = _transform_musicbrainz_cached_data(release_details)
                    elif source == "deezer":
                        # Передаем country_code в _transform_deezer_cached_data, если он нужен для трансформации
                        # (например, для выбора специфичных для рынка данных, если они есть в кеше)
                        transformed_data = await _transform_deezer_cached_data(release_details, country_code)

                    if transformed_data:
                        logger.info(
                            "Successfully found and transformed pre-existing %s data for release ID %s.",
                            source.capitalize(),
                            release_id,
                        )
                        return True, {"source": source, "data": transformed_data}
                    logger.warning(
                        "Failed to transform cached %s data for ID %s, though details were found.",
                        source.capitalize(),
                        release_id,
                    )
                # else:
                #    logger.debug("No cached %s release details found for ID: %s", source.capitalize(), release_id)

    except (ConnectionError, OSError, ValueError, KeyError, TypeError) as e:
        logger.warning("Error during check_existing_result: %s", str(e), exc_info=True)

    logger.info(
        "No usable pre-existing data found in cache for '%s' - '%s' after checking all sources.",
        band_name,
        release_name,
    )
    return False, None

"""Redis cache utilities for music metadata module.

This module provides functions for caching music metadata in Redis to
reduce external API calls and improve performance.
"""

import hashlib
import json
import threading
from logging import Logger
from typing import Any, TypeVar, cast

import redis
from redis.asyncio.client import Redis

from grimwaves_api.core.logger import get_logger
from grimwaves_api.core.settings import settings

# Initialize logger
logger: Logger = get_logger(module_name="modules.music.cache")

# Type variable for generic cache functions
T = TypeVar("T")

# Cache key prefixes
KEY_PREFIXES = {
    "metadata_result": "grimwaves:metadata:result:",  # Final results by task_id
    "spotify_search": "grimwaves:metadata:spotify:search:",  # Spotify search results
    "spotify_release": "grimwaves:metadata:spotify:release:",  # Spotify release details
    "spotify_tracks": "grimwaves:metadata:spotify:tracks:",  # Spotify track lists
    "spotify_artist": "grimwaves:metadata:spotify:artist:",  # Spotify artist details
    "musicbrainz_search": "grimwaves:metadata:mb:search:",  # MusicBrainz search results
    "musicbrainz_release": "grimwaves:metadata:mb:release:",  # MusicBrainz release details
    "musicbrainz_artist": "grimwaves:metadata:mb:artist:",  # MusicBrainz artist details
    "deezer_search": "grimwaves:metadata:deezer:search:",  # Deezer search results
    "deezer_release": "grimwaves:metadata:deezer:release:",  # Deezer release details
    "deezer_tracks": "grimwaves:metadata:deezer:tracks:",  # Deezer track lists
}

# TTL settings (in seconds)
TTL = {
    "result": 86400,  # 24 hours for final results
    "search": 3600,  # 1 hour for search results
    "release": 43200,  # 12 hours for release metadata
    "tracks": 43200,  # 12 hours for track lists
    "artist": 86400,  # 24 hours for artist data
    "error": 600,  # 10 minutes for error responses
}


class RedisCache:
    """Redis cache handler for music metadata.

    This class provides methods for caching and retrieving music metadata
    from Redis to minimize external API calls and improve performance.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        """Initialize Redis cache with connection parameters.

        Args:
            redis_url: Redis connection URL (defaults to settings.redis_url)
        """
        self.redis_url: str = redis_url or settings.redis_url
        self._sync_client: redis.Redis | None = None
        self._async_client: Redis | None = None
        self._client_lock = threading.RLock()

    @property
    def sync_client(self) -> redis.Redis:
        """Get or create a synchronous Redis client.

        Returns:
            Configured Redis client
        """
        with self._client_lock:
            if self._sync_client is None:
                self._sync_client = redis.from_url(  # pyright: ignore[reportUnknownMemberType]
                    self.redis_url,
                    socket_timeout=5.0,
                    socket_connect_timeout=5.0,
                    retry_on_timeout=True,
                )
            return self._sync_client

    @property
    async def async_client(self) -> Redis:
        """Get or create an asynchronous Redis client.

        Creates a fresh client for each call to avoid closed event loop issues.

        Returns:
            Configured Redis client
        """
        # Create a new client for each request to avoid event loop issues
        return Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            self.redis_url,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
        )

    async def close(self) -> None:
        """Close Redis connections. Note: This should only be called during app shutdown."""
        with self._client_lock:
            if self._async_client is not None:
                try:
                    await self._async_client.close()
                except Exception as e:
                    logger.warning(f"Error closing async Redis client: {e}")
                finally:
                    self._async_client = None

            if self._sync_client is not None:
                try:
                    self._sync_client.close()
                except Exception as e:
                    logger.warning(f"Error closing sync Redis client: {e}")
                finally:
                    self._sync_client = None

    def generate_key(self, prefix: str, *args: Any) -> str:
        """Generate a cache key from prefix and arguments.

        Args:
            prefix: Key prefix from KEY_PREFIXES
            *args: Additional arguments to include in the key

        Returns:
            Cache key string
        """
        if prefix not in KEY_PREFIXES:
            msg = f"Invalid cache key prefix: {prefix}"
            raise ValueError(msg)

        # Normalize and hash arguments to prevent key length issues and special characters
        if args:
            key_parts: list[str] = []
            for arg in args:
                if arg is None:
                    continue

                # Convert non-string args to string
                if not isinstance(arg, str):
                    arg = str(arg)  # noqa: PLW2901

                # For very long arguments, use a hash instead
                max_length = 100
                if len(arg) > max_length:
                    arg = hashlib.sha256(arg.encode("utf-8")).hexdigest()  # noqa: PLW2901

                # Replace spaces with underscores
                arg = arg.replace(" ", "_")  # noqa: PLW2901

                key_parts.append(arg)

            key_suffix = "_".join(key_parts)
        else:
            key_suffix = "default"

        # Create a deterministic key using the prefix and normalized arguments
        return f"{KEY_PREFIXES[prefix]}{key_suffix}"

    async def get(self, key: str, default: T | None = None) -> T | None:
        """Retrieve a value from cache with safe deserialization.

        Args:
            key: Cache key
            default: Default value if key doesn't exist

        Returns:
            Cached value or default
        """
        client = await self.async_client

        try:
            value = await client.get(key)
            if value is None:
                return default

            # Only use JSON for deserialization as it's safer than pickle
            try:
                return cast(T, json.loads(value))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning("Failed to deserialize value for key %s: %s", key, str(e))
                return default

        except redis.RedisError as e:
            logger.warning("Redis error when getting key %s: %s", key, str(e))
            return default

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Store a value in cache with expiration.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None for default)

        Returns:
            True if successful, False otherwise
        """
        client = await self.async_client

        try:
            # Only use JSON for serialization
            try:
                logger.debug("Caching value for key '%s': %s", key, json.dumps(value, indent=4))
                serialized = json.dumps(value).encode("utf-8")
            except (TypeError, OverflowError) as e:
                logger.warning("Cannot serialize value for key %s: %s", key, str(e))
                return False

            # Set value with TTL
            if ttl is None:
                ttl = settings.redis_cache_ttl

            await client.set(key, serialized, ex=ttl)
            return True

        except redis.RedisError as e:
            logger.warning("Redis error when setting key %s: %s", key, str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False otherwise
        """
        client = await self.async_client

        try:
            return bool(await client.delete(key))
        except redis.RedisError as e:
            logger.warning("Redis error when deleting key %s: %s", key, str(e))
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        client = await self.async_client

        try:
            return bool(await client.exists(key))
        except redis.RedisError as e:
            logger.warning("Redis error when checking key %s: %s", key, str(e))
            return False

    # Higher-level caching functions for the music metadata module

    async def cache_metadata_result(
        self,
        task_id: str,
        metadata: dict[str, Any],
        is_error: bool = False,
    ) -> bool:
        """Cache final metadata result by task ID.

        Args:
            task_id: Celery task ID
            metadata: Metadata result to cache
            is_error: Whether this is an error response

        Returns:
            True if successful, False otherwise
        """
        key = self.generate_key("metadata_result", task_id)
        ttl = TTL["error"] if is_error else TTL["result"]

        # Диагностика того, что мы сохраняем в кеше
        logger.debug("Caching metadata for task_id %s with key %s", task_id, key)

        # Проверяем структуру данных перед кешированием
        if not is_error and "result" in metadata:
            result_data = metadata["result"]
            # Проверяем наличие ISRC кодов
            isrc_count = 0
            if "tracks" in result_data and isinstance(result_data["tracks"], list):
                for track in result_data["tracks"]:
                    if track.get("isrc") is not None:
                        isrc_count += 1

            # Проверяем жанры
            genre_count = 0
            if "genre" in result_data and isinstance(result_data["genre"], list):
                genre_count = len(result_data["genre"])

            # Проверяем социальные ссылки
            social_count = 0
            if "social_links" in result_data and isinstance(result_data["social_links"], dict):
                social_count = sum(1 for val in result_data["social_links"].values() if val is not None)

            logger.info(
                "Caching metadata with %d tracks (%d with ISRC), %d genres, %d social links",
                len(result_data.get("tracks", [])),
                isrc_count,
                genre_count,
                social_count,
            )

        return await self.set(key, metadata, ttl)

    async def get_metadata_result(self, task_id: str) -> dict[str, Any] | None:
        """Retrieve cached metadata result by task ID.

        Args:
            task_id: Celery task ID

        Returns:
            Cached metadata or None if not found
        """
        key = self.generate_key("metadata_result", task_id)
        return await self.get(key)

    async def cache_search_results(
        self,
        source: str,
        band_name: str,
        release_name: str,
        country_code: str | None,
        results: list[dict[str, Any]],
    ) -> bool:
        """Cache search results from external API.

        This method caches search results from external music metadata APIs.
        To retrieve the cached data later, use the paired method `get_search_results`
        with the same parameters.

        Args:
            source: API source ("spotify", "musicbrainz", "deezer")
            band_name: Artist/band name
            release_name: Release name
            country_code: Optional ISO country code
            results: Search results to cache

        Returns:
            True if successful, False otherwise
        """
        prefix = f"{source}_search"
        if prefix not in KEY_PREFIXES:
            logger.warning("Invalid source for cache_search_results: %s", source)
            return False

        key = self.generate_key(prefix, band_name, release_name, country_code)
        return await self.set(key, results, TTL["search"])

    async def get_search_results(
        self,
        source: str,
        band_name: str,
        release_name: str,
        country_code: str | None,
    ) -> list[dict[str, Any]] | None:
        """Retrieve cached search results.

        Args:
            source: API source ("spotify", "musicbrainz", "deezer")
            band_name: Artist/band name
            release_name: Release name
            country_code: Optional ISO country code

        Returns:
            Cached search results or None if not found
        """
        prefix = f"{source}_search"
        if prefix not in KEY_PREFIXES:
            logger.warning("Invalid source for get_search_results: %s", source)
            return None

        key = self.generate_key(prefix, band_name, release_name, country_code)
        return await self.get(key)

    async def cache_release_details(
        self,
        source: str,
        release_id: str,
        details: dict[str, Any],
    ) -> bool:
        """Cache release details from external API.

        Args:
            source: API source ("spotify", "musicbrainz", "deezer")
            release_id: Unique release ID from the source
            details: Release details to cache

        Returns:
            True if successful, False otherwise
        """
        prefix = f"{source}_release"
        if prefix not in KEY_PREFIXES:
            logger.warning("Invalid source for cache_release_details: %s", source)
            return False

        key = self.generate_key(prefix, release_id)
        return await self.set(key, details, TTL["release"])

    async def get_release_details(
        self,
        source: str,
        release_id: str,
    ) -> dict[str, Any] | None:
        """Retrieve cached release details.

        Args:
            source: API source ("spotify", "musicbrainz", "deezer")
            release_id: Unique release ID from the source

        Returns:
            Cached release details or None if not found
        """
        prefix = f"{source}_release"
        if prefix not in KEY_PREFIXES:
            logger.warning("Invalid source for get_release_details: %s", source)
            return None

        key = self.generate_key(prefix, release_id)
        return await self.get(key)

    async def cache_tracks_list(
        self,
        source: str,
        release_id: str,
        tracks: list[dict[str, Any]],
    ) -> bool:
        """Cache tracks list for a release.

        Args:
            source: API source ("spotify", "musicbrainz", "deezer")
            release_id: Unique release ID from the source
            tracks: List of tracks to cache

        Returns:
            True if successful, False otherwise
        """
        prefix = f"{source}_tracks"
        if prefix not in KEY_PREFIXES:
            logger.warning("Invalid source for cache_tracks_list: %s", source)
            return False

        key = self.generate_key(prefix, release_id)
        return await self.set(key, tracks, TTL["tracks"])

    async def get_tracks_list(
        self,
        source: str,
        release_id: str,
    ) -> list[dict[str, Any]] | None:
        """Retrieve cached tracks list.

        Args:
            source: API source ("spotify", "musicbrainz", "deezer")
            release_id: Unique release ID from the source

        Returns:
            Cached tracks list or None if not found
        """
        prefix = f"{source}_tracks"
        if prefix not in KEY_PREFIXES:
            logger.warning("Invalid source for get_tracks_list: %s", source)
            return None

        key = self.generate_key(prefix, release_id)
        return await self.get(key)

    async def cache_artist_data(
        self,
        source: str,
        artist_id: str,
        data: dict[str, Any],
    ) -> bool:
        """Cache artist data.

        Args:
            source: API source ("spotify", "musicbrainz", "deezer")
            artist_id: Unique artist ID from the source
            data: Artist data to cache

        Returns:
            True if successful, False otherwise
        """
        prefix = f"{source}_artist"
        if prefix not in KEY_PREFIXES:
            logger.warning("Invalid source for cache_artist_data: %s", source)
            return False

        key = self.generate_key(prefix, artist_id)
        return await self.set(key, data, TTL["artist"])

    async def get_artist_data(
        self,
        source: str,
        artist_id: str,
    ) -> dict[str, Any] | None:
        """Retrieve cached artist data.

        Args:
            source: API source ("spotify", "musicbrainz", "deezer")
            artist_id: Unique artist ID from the source

        Returns:
            Cached artist data or None if not found
        """
        prefix = f"{source}_artist"
        if prefix not in KEY_PREFIXES:
            logger.warning("Invalid source for get_artist_data: %s", source)
            return None

        key = self.generate_key(prefix, artist_id)
        return await self.get(key)


# Create a singleton instance for global use
cache = RedisCache(settings.redis_url)

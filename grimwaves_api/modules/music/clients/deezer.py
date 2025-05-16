"""Deezer API client for music metadata retrieval.

This module provides a client for the Deezer API to search for releases
and fetch detailed information about albums, tracks, and artists.
It is used as a fallback source to complement data from Spotify and MusicBrainz.
"""

import asyncio
from typing import Any, ClassVar

import httpx

from grimwaves_api.common.utils import BaseHttpxClient
from grimwaves_api.core.logger import get_logger
from grimwaves_api.core.settings import settings
from grimwaves_api.modules.music.constants import RETRY_CONFIG

# Initialize module logger
logger = get_logger("modules.music.clients.deezer")


class DeezerClient(BaseHttpxClient):
    """Client for interacting with Deezer API.

    This client provides methods to search for music releases and fetch metadata
    from Deezer API. It is designed as a fallback source when primary sources
    like Spotify or MusicBrainz don't return sufficient data.
    """

    # API endpoints
    API_BASE_URL: ClassVar[str] = "https://api.deezer.com"

    # Timeout settings (in seconds)
    DEFAULT_TIMEOUT: ClassVar[int] = 10

    def __init__(self, api_base_url: str = "") -> None:
        """Initialize the Deezer client.

        Args:
            api_base_url: Deezer API base URL (optional, defaults to settings.deezer_api_base_url)
        """
        self.api_base_url: str = api_base_url or settings.deezer_api_base_url

        # Initialize base client with appropriate configuration
        super().__init__(
            base_url=self.api_base_url,
            timeout=self.DEFAULT_TIMEOUT,
            headers={
                "User-Agent": "GrimWaves-API/1.0",
                "Accept": "application/json",
            },
        )

        # Configure retries
        self._retry_config: dict[str, Any] = RETRY_CONFIG["DEFAULT"]

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make a request to the Deezer API.

        Args:
            method: HTTP method (get, post, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments to pass to httpx

        Returns:
            Dict: JSON response from the API

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        url = f"{self.api_base_url}/{endpoint.lstrip('/')}"

        # Apply retry logic
        retries_value: Any | None = self._retry_config.get("retries")
        max_retries: int = 3 if not isinstance(retries_value, int) else retries_value

        backoff_value: Any | None = self._retry_config.get("backoff_factor")
        backoff_factor: float = 0.5 if not isinstance(backoff_value, float) else backoff_value

        status_value: Any | None = self._retry_config.get("status_forcelist")
        status_forcelist: list[int] = [429, 500, 502, 503, 504]
        if isinstance(status_value, list) and all(isinstance(x, int) for x in status_value):  # pyright: ignore[reportUnknownVariableType]
            status_forcelist = status_value  # pyright: ignore[reportUnknownVariableType]

        rate_limit_status_code: int = 429
        client = await self._get_client()

        for retry in range(max_retries + 1):
            try:
                request_method = getattr(client, method.lower())
                response = await request_method(url, **kwargs)

                # Handle rate limiting
                if response.status_code == rate_limit_status_code:
                    retry_after = int(response.headers.get("Retry-After", 1))
                    logger.warning(
                        "Rate limited by Deezer API, waiting %s seconds",
                        retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if retry < max_retries and e.response.status_code in status_forcelist:
                    # Calculate backoff time
                    backoff_time = backoff_factor * (2**retry)
                    logger.warning(
                        "Retrying Deezer API request after %s seconds (attempt %s/%s)",
                        backoff_time,
                        retry + 1,
                        max_retries,
                    )
                    await asyncio.sleep(backoff_time)
                    continue

                logger.exception(
                    "Deezer API request failed: %s %s",
                    method.upper(),
                    url,
                )
                raise

        # This code will only execute if all attempts failed with an error
        # and none of them raised an exception (which is theoretically impossible)
        msg = "Unexpected error in request handling"
        raise RuntimeError(msg)

    async def search_releases(
        self,
        artist: str,
        album: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search for releases (albums) by artist and album name.

        Args:
            artist: Name of the artist
            album: Name of the album
            limit: Maximum number of results to return

        Returns:
            Dict: Search results from Deezer API

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        logger.debug(
            "Searching for release in Deezer: artist=%s, album=%s",
            artist,
            album,
        )

        # Using parameters directly without prior encoding
        # The httpx library automatically encodes query parameters
        params = {
            "q": f'artist:"{artist}" album:"{album}"',  # Using quotes for exact match
            "limit": limit,
            "type": "album",
        }

        try:
            result = await self._request("GET", "search/album", params=params)
        except httpx.HTTPStatusError:
            logger.exception(
                "Failed to search Deezer for artist=%s, album=%s",
                artist,
                album,
            )
            raise
        else:
            logger.debug(
                "Found %s results for artist=%s, album=%s in Deezer",
                result.get("total", 0),
                artist,
                album,
            )
            return result

    async def get_album(self, album_id: str) -> dict[str, Any]:
        """Get detailed information about an album.

        Args:
            album_id: Deezer album ID

        Returns:
            Dict: Album details including tracks

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        logger.debug("Fetching album details from Deezer: album_id=%s", album_id)

        try:
            result = await self._request("GET", f"album/{album_id}")
        except httpx.HTTPStatusError:
            logger.exception(
                "Failed to fetch album details from Deezer: album_id=%s",
                album_id,
            )
            raise
        else:
            logger.debug("Successfully fetched album details from Deezer")
            return result

    async def get_artist(self, artist_id: str) -> dict[str, Any]:
        """Get detailed information about an artist.

        Args:
            artist_id: Deezer artist ID

        Returns:
            Dict: Artist details

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        logger.debug("Fetching artist details from Deezer: artist_id=%s", artist_id)

        try:
            result = await self._request("GET", f"artist/{artist_id}")
        except httpx.HTTPStatusError:
            logger.exception(
                "Failed to fetch artist details from Deezer: artist_id=%s",
                artist_id,
            )
            raise
        else:
            logger.debug("Successfully fetched artist details from Deezer")
            return result

    async def get_album_tracks(self, album_id: str) -> list[dict[str, Any]]:
        """Get tracks for an album.

        Args:
            album_id: Deezer album ID

        Returns:
            List[Dict]: List of tracks

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        logger.debug("Fetching album tracks from Deezer: album_id=%s", album_id)

        try:
            result = await self._request("GET", f"album/{album_id}/tracks")
        except httpx.HTTPStatusError:
            logger.exception(
                "Failed to fetch album tracks from Deezer: album_id=%s",
                album_id,
            )
            raise
        else:
            tracks = result.get("data", [])
            logger.debug(
                "Successfully fetched %s tracks for album_id=%s from Deezer",
                len(tracks),
                album_id,
            )
            return tracks

    async def get_track(self, track_id: str) -> dict[str, Any]:
        """Get detailed information about a track.

        Args:
            track_id: Deezer track ID

        Returns:
            Dict: Track details including ISRC if available

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        logger.debug("Fetching track details from Deezer: track_id=%s", track_id)

        try:
            result = await self._request("GET", f"track/{track_id}")
        except httpx.HTTPStatusError:
            logger.exception(
                "Failed to fetch track details from Deezer: track_id=%s",
                track_id,
            )
            raise
        else:
            logger.debug("Successfully fetched track details from Deezer")
            return result

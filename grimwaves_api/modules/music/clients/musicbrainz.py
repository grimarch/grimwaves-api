"""MusicBrainz API client for music metadata retrieval.

This module provides a client for the MusicBrainz API to search for releases,
fetch artist information, and retrieve links to social media profiles.
"""

import asyncio
import time
from typing import Any, ClassVar, Literal

import httpx

from grimwaves_api.common.utils import BaseHttpxClient
from grimwaves_api.core.logger import get_logger
from grimwaves_api.core.settings import settings
from grimwaves_api.modules.music.constants import ERROR_MESSAGES, LINK_TYPES, RETRY_CONFIG

# Initialize module logger
logger = get_logger("modules.music.clients.musicbrainz")


class MusicBrainzClient(BaseHttpxClient):
    """Client for interacting with MusicBrainz API."""

    # API endpoints
    API_BASE_URL: ClassVar[str] = "https://musicbrainz.org/ws/2"

    # Timeout settings (in seconds)
    DEFAULT_TIMEOUT: ClassVar[int] = 10

    # Request delay to comply with rate limiting (1 request per second)
    REQUEST_DELAY: ClassVar[float] = 1.1

    def __init__(
        self,
        app_name: str = "",
        app_version: str = "",
        contact: str = "",
    ) -> None:
        """Initialize the MusicBrainz client.

        Args:
            app_name: Application name for user agent (defaults to settings)
            app_version: Application version for user agent (defaults to settings)
            contact: Contact email for user agent (defaults to settings)
        """
        self.app_name: str = app_name or settings.musicbrainz_app_name
        self.app_version: str = app_version or settings.musicbrainz_app_version
        self.contact: str = contact or settings.musicbrainz_contact

        # Construct user agent string according to MB guidelines
        self._user_agent: str = f"{self.app_name}/{self.app_version} ( {self.contact} )"

        # Initialize the base client with appropriate configuration
        super().__init__(
            base_url=self.API_BASE_URL,
            timeout=self.DEFAULT_TIMEOUT,
            headers={"User-Agent": self._user_agent},
        )

        # Configure retries
        self._retry_config: dict[str, Any] = RETRY_CONFIG.get("MUSICBRAINZ", RETRY_CONFIG["DEFAULT"])

        # Track last request time for rate limiting
        self._last_request_time: float = 0

        logger.info(f"Initialized MusicBrainz client with User-Agent: {self._user_agent}")

    async def _respect_rate_limit(self) -> None:
        """Ensure we respect MusicBrainz's rate limiting (1 request per second)."""
        current_time = time.time()
        elapsed = current_time - self._last_request_time

        if elapsed < self.REQUEST_DELAY:
            delay = self.REQUEST_DELAY - elapsed
            logger.debug(f"Rate limiting: waiting {delay:.2f}s before next request")
            await asyncio.sleep(delay)

        self._last_request_time = time.time()

    async def _request(
        self,
        method: str,
        endpoint: str,
        fmt: Literal["json", "xml"] = "json",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make a request to the MusicBrainz API.

        Args:
            method: HTTP method (get, post, etc.)
            endpoint: API endpoint (without base URL)
            fmt: Response format ('json' or 'xml')
            **kwargs: Additional arguments to pass to httpx

        Returns:
            dict: JSON response from the API

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        await self._respect_rate_limit()

        if "params" not in kwargs:
            kwargs["params"] = {}

        kwargs["params"]["fmt"] = fmt

        url = f"{self.API_BASE_URL}/{endpoint.lstrip('/')}"

        # Apply retry logic
        retries_value = self._retry_config.get("retries")
        max_retries = 2 if not isinstance(retries_value, int) else retries_value

        backoff_value = self._retry_config.get("backoff_factor")
        backoff_factor = 1.0 if not isinstance(backoff_value, float) else backoff_value

        status_value = self._retry_config.get("status_forcelist")
        status_forcelist: list[int] = [429, 500, 502, 503, 504]
        if isinstance(status_value, list) and all(isinstance(x, int) for x in status_value):  # pyright: ignore[reportUnknownVariableType]
            status_forcelist = status_value  # pyright: ignore[reportUnknownVariableType]

        # Get the client using lazy initialization
        client = await self._get_client()

        for retry in range(max_retries + 1):
            try:
                request_method = getattr(client, method.lower())
                response = await request_method(url, **kwargs)

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 2))
                    logger.warning(
                        "Rate limited by MusicBrainz API, waiting %s seconds",
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
                        "Retrying MusicBrainz API request after %s seconds (attempt %s/%s)",
                        backoff_time,
                        retry + 1,
                        max_retries,
                    )
                    await asyncio.sleep(backoff_time)
                    continue

                logger.exception(
                    "MusicBrainz API request failed: %s %s",
                    method.upper(),
                    url,
                )
                raise
        # This unreachable code is added to satisfy the linter
        # If we reach this point, an error has occurred and an exception has already been raised
        msg: str = "Unexpected error in request handling"
        raise RuntimeError(msg)

    async def search_releases(
        self,
        artist: str,
        album: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search for releases by artist and album name.

        Args:
            artist: Artist name
            album: Album name
            limit: Maximum number of results (default: 10)

        Returns:
            dict: Search results from MusicBrainz API
        """
        logger.info("Searching for release: artist='%s', album='%s'", artist, album)

        # Using parameters directly without prior encoding
        # The httpx library automatically encodes query parameters
        params = {
            "query": f'artist:"{artist}" AND release:"{album}"',
            "limit": min(limit, 25),  # MusicBrainz default is 25
            "fmt": "json",  # Explicitly specify response format
        }

        try:
            result = await self._request("get", "release", params=params)
            logger.info(
                "Found %s releases for query artist='%s', album='%s'",
                len(result.get("releases", [])),
                artist,
                album,
            )
            return result
        except httpx.HTTPStatusError:
            logger.exception(ERROR_MESSAGES["MUSICBRAINZ_API_ERROR"].format(error="search_releases failed"))
            raise

    async def get_release(self, release_id: str, inc: list[str] | None = None) -> dict[str, Any]:
        """Get detailed information about a specific release.

        Args:
            release_id: MusicBrainz release ID (MBID)
            inc: List of additional information to include
                 (e.g., ["recordings", "artists", "labels"])

        Returns:
            dict: Release details from MusicBrainz API
        """
        logger.info("Fetching release details for MBID: %s", release_id)

        params: dict[str, Any] = {}

        if inc:
            params["inc"] = "+".join(inc)

        try:
            return await self._request("get", f"release/{release_id}", params=params)
        except httpx.HTTPStatusError:
            logger.exception(ERROR_MESSAGES["MUSICBRAINZ_API_ERROR"].format(error="get_release failed"))
            raise

    async def get_artist(self, artist_id: str, inc: list[str] | None = None) -> dict[str, Any]:
        """Get detailed information about a specific artist.

        Args:
            artist_id: MusicBrainz artist ID (MBID)
            inc: List of additional information to include
                 (e.g., ["url-rels", "genres"])

        Returns:
            dict: Artist details from MusicBrainz API
        """
        logger.info("Fetching artist details for MBID: %s", artist_id)

        params: dict[str, Any] = {}

        if inc:
            params["inc"] = "+".join(inc)

        try:
            return await self._request("get", f"artist/{artist_id}", params=params)
        except httpx.HTTPStatusError:
            logger.exception(ERROR_MESSAGES["MUSICBRAINZ_API_ERROR"].format(error="get_artist failed"))
            raise

    async def get_social_links(self, artist_id: str) -> dict[str, str | None]:
        """Get social media links for an artist.

        Args:
            artist_id: MusicBrainz artist ID (MBID)

        Returns:
            dict: Dictionary of social media links keyed by platform
        """
        logger.info("Fetching social links for artist MBID: %s", artist_id)

        try:
            result = await self.get_artist(artist_id, inc=["url-rels"])

            social_links: dict[str, str | None] = {
                "website": None,
                "facebook": None,
                "twitter": None,
                "instagram": None,
                "youtube": None,
                "vk": None,
            }

            if "relations" in result:
                for relation in result["relations"]:
                    if relation.get("type") == LINK_TYPES["OFFICIAL_HOMEPAGE"]:
                        website_url = relation.get("url", {}).get("resource")
                        # Assign None if the URL uses HTTP, otherwise assign the URL
                        social_links["website"] = (
                            None if website_url and website_url.startswith("http://") else website_url
                        )

                    elif relation.get("type") == LINK_TYPES["SOCIAL_NETWORK"]:
                        url = relation.get("url", {}).get("resource", "")

                        if "facebook.com" in url:
                            social_links["facebook"] = url
                        elif "twitter.com" in url or "x.com" in url:
                            social_links["twitter"] = url
                        elif "instagram.com" in url:
                            social_links["instagram"] = url
                        elif "youtube.com" in url:
                            social_links["youtube"] = url
                        elif "vk.com" in url:
                            social_links["vk"] = url

            logger.info(
                "Found %s social links for artist MBID: %s",
                sum(1 for v in social_links.values() if v is not None),
                artist_id,
            )

            return social_links

        except httpx.HTTPStatusError:
            logger.exception(ERROR_MESSAGES["MUSICBRAINZ_API_ERROR"].format(error="get_social_links failed"))
            raise

    async def get_genres(self, artist_id: str) -> list[str]:
        """Get genres associated with an artist.

        Args:
            artist_id: MusicBrainz artist ID (MBID)

        Returns:
            list: List of genre names
        """
        logger.info("Fetching genres for artist MBID: %s", artist_id)

        try:
            result = await self.get_artist(artist_id, inc=["genres"])

            genres = []
            if "genres" in result:
                genres = [genre.get("name") for genre in result["genres"] if genre.get("name")]

            logger.info("Found %s genres for artist MBID: %s", len(genres), artist_id)
            return genres

        except httpx.HTTPStatusError:
            logger.exception(ERROR_MESSAGES["MUSICBRAINZ_API_ERROR"].format(error="get_genres failed"))
            raise

    async def search_artists(
        self,
        artist: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search for artists by name.

        Args:
            artist: Artist name
            limit: Maximum number of results (default: 10)

        Returns:
            dict: Search results from MusicBrainz API
        """
        logger.info("Searching for artist: name='%s'", artist)

        # Using parameters directly without prior encoding
        # The httpx library automatically encodes query parameters
        params = {
            "query": f'artist:"{artist}"',
            "limit": min(limit, 25),  # MusicBrainz default is 25
            "fmt": "json",  # Explicitly specify response format
        }

        try:
            result = await self._request("get", "artist", params=params)
            logger.info(
                "Found %s artists for query name='%s'",
                len(result.get("artists", [])),
                artist,
            )
            return result
        except httpx.HTTPStatusError:
            logger.exception(ERROR_MESSAGES["MUSICBRAINZ_API_ERROR"].format(error="search_artists failed"))
            raise

    async def get_track_by_isrc(self, isrc: str) -> dict[str, Any]:
        """Get track information by ISRC.

        Args:
            isrc: ISRC code

        Returns:
            dict: Track details from MusicBrainz API
        """
        logger.info("Fetching track details for ISRC: %s", isrc)

        params = {
            "query": f"isrc:{isrc}",
            "limit": 1,
            "fmt": "json",  # Explicitly specify response format
        }

        try:
            result = await self._request("get", "recording", params=params)
            if result and "recordings" in result and result["recordings"]:
                return result["recordings"][0]
            return {}
        except httpx.HTTPStatusError:
            logger.exception(ERROR_MESSAGES["MUSICBRAINZ_API_ERROR"].format(error="get_track_by_isrc failed"))
            raise

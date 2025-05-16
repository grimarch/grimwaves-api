"""Spotify API client for music metadata retrieval.

This module provides a client for the Spotify Web API to search for releases
and fetch detailed information about albums, tracks, and artists.
"""

import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar, TypedDict

import httpx

from grimwaves_api.common.utils import BaseHttpxClient
from grimwaves_api.core.logger import get_logger
from grimwaves_api.modules.music.constants import ERROR_MESSAGES

# Initialize module logger
logger = get_logger("modules.music.clients.spotify")


class RetryOptions(TypedDict):
    """Type definition for retry options dictionary."""

    attempts: int
    start_timeout: int
    factor: int
    statuses: set[int]


class SpotifyAPIError(Exception):
    """Exception raised for Spotify API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Error message
            status_code: HTTP status code of the error
        """
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class SpotifyClient(BaseHttpxClient):
    """Client for interacting with Spotify Web API."""

    # API endpoints
    API_BASE_URL: ClassVar[str] = "https://api.spotify.com/v1"
    AUTH_URL: ClassVar[str] = "https://accounts.spotify.com/api/token"

    # Timeout settings (in seconds)
    DEFAULT_TIMEOUT: ClassVar[int] = 10

    def __init__(self, client_id: str, client_secret: str) -> None:
        """Initialize Spotify client.

        Args:
            client_id: Spotify API client ID
            client_secret: Spotify API client secret
        """
        if not client_id or not client_secret:
            logger.warning("Initializing SpotifyClient with MISSING credentials.")

        # Initialize the base client
        super().__init__(
            base_url=self.API_BASE_URL,
            timeout=self.DEFAULT_TIMEOUT,
            headers={
                "User-Agent": "GrimWaves-API/1.0",
                "Accept": "application/json",
            },
        )

        # Store client credentials
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expiry: datetime | None = None
        self._retry_options: RetryOptions = {
            "attempts": 3,
            "start_timeout": 1,
            "factor": 2,
            "statuses": {500, 502, 503, 504},
        }

    async def _ensure_token(self) -> None:
        """Ensure we have a valid access token."""
        if not self._token or (self._token_expiry and self._token_expiry <= datetime.now(timezone.utc)):
            await self._refresh_token()

    async def _refresh_token(self) -> None:
        """Refresh the Spotify access token."""
        logger.debug("Attempting to refresh Spotify token.")
        auth_str = f"{self._client_id}:{self._client_secret}"
        auth_bytes = auth_str.encode("utf-8")
        auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")

        headers = {
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials"}

        try:
            client = await self._get_client()
            response = await client.post(
                self.AUTH_URL,
                headers=headers,
                data=data,
            )

            if response.status_code != 200:
                logger.error(
                    f"Failed to refresh token, status: {response.status_code}. Response: {response.text}",
                )
                msg = f"Failed to refresh token: {response.status_code}"
                raise SpotifyAPIError(
                    msg,
                    status_code=response.status_code,
                )

            data = response.json()
            try:
                expires_in: int = int(data["expires_in"])
            except (KeyError, ValueError, TypeError):
                msg = f"Invalid expires_in value: {data.get('expires_in')}"
                raise SpotifyAPIError(
                    msg,
                    status_code=response.status_code,
                )
            self._token = data["access_token"]
            self._token_expiry = datetime.now(timezone.utc) + timedelta(
                seconds=expires_in - 60,
            )  # Refresh 1 minute before expiry
        except httpx.RequestError as e:
            logger.exception("HTTP client error during token refresh: {error}", extra={"error": e})
            msg = f"HTTP client error during token refresh: {e}"
            raise SpotifyAPIError(msg) from e

    async def _make_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        retries: int | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Make a request to Spotify API with retries.

        Args:
            method: HTTP method
            url: Request URL
            params: Optional query parameters
            retries: Number of retries, uses default if None

        Returns:
            Response data as dict or list

        Raises:
            SpotifyAPIError: If the request fails after all retries
        """
        await self._ensure_token()
        client = await self._get_client()

        attempts: int = retries if retries is not None else self._retry_options["attempts"]
        timeout: float = float(self._retry_options["start_timeout"])

        # Construct full URL if it's not already absolute
        if not url.startswith("http"):
            url = f"{self.API_BASE_URL}/{url.lstrip('/')}"

        last_error = None
        for attempt in range(attempts):
            try:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {self._token}"},
                )

                if response.status_code == 200:
                    return response.json()
                if response.status_code == 401:
                    # Token might be expired, refresh and retry
                    await self._refresh_token()
                    continue
                if response.status_code in self._retry_options["statuses"]:
                    if attempt < attempts - 1:  # Don't sleep on last attempt
                        await asyncio.sleep(timeout)
                        timeout *= self._retry_options["factor"]
                        continue

                error_data = response.text
                msg = f"Request failed with status {response.status_code}: {error_data}"
                raise SpotifyAPIError(
                    msg,
                )
            except (httpx.RequestError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < attempts - 1:
                    await asyncio.sleep(timeout)
                    timeout *= self._retry_options["factor"]
                    continue

        msg = f"Request failed after {attempts} attempts: {last_error!s}"
        raise SpotifyAPIError(
            msg,
        )

    async def _make_dict_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        retries: int | None = None,
    ) -> dict[str, Any]:
        """Make a request to Spotify API, ensuring the response is a dictionary."""
        response_data = await self._make_request(method, url, params=params, retries=retries)
        if not isinstance(response_data, dict):
            err_msg = (
                f"Unexpected response type from Spotify API endpoint {url}. Expected dict, got {type(response_data)}."
            )
            logger.error(err_msg, extra={"response_data": response_data})
            raise SpotifyAPIError(err_msg)
        return response_data

    async def search_releases(
        self,
        artist: str,
        album: str,
        limit: int = 10,
        market: str | None = None,
    ) -> dict[str, Any]:
        """Search for album releases by artist and album name.

        Args:
            artist: Artist name
            album: Album name
            limit: Maximum number of results (default: 10)
            market: ISO 3166-1 alpha-2 country code (e.g., 'US')

        Returns:
            dict: Search results from Spotify API
        """
        logger.info("Searching for release: artist='%s', album='%s'", artist, album)

        query = f"artist:{artist} album:{album}"
        params: dict[str, Any] = {
            "q": query,
            "type": "album",
            "limit": min(limit, 50),  # Spotify API limit is 50
        }

        if market:
            params["market"] = market

        try:
            logger.debug("DEBUG: Spotify search params: %s", json.dumps(params, indent=4))
            result = await self._make_dict_request("GET", "search", params=params)
            logger.debug("DEBUG: Spotify search result: %s", json.dumps(result, indent=4))
            logger.info(
                "Found %s albums for query artist='%s', album='%s'",
                len(result.get("albums", {}).get("items", [])),
                artist,
                album,
            )
            return result
        except SpotifyAPIError:
            logger.exception(
                ERROR_MESSAGES["SPOTIFY_API_ERROR"],
            )
            raise

    async def get_album(self, album_id: str, market: str | None = None) -> dict[str, Any]:
        """Get detailed information about an album by ID.

        Args:
            album_id: Spotify album ID
            market: ISO 3166-1 alpha-2 country code (e.g., 'US')

        Returns:
            dict: Album information from Spotify API
        """
        logger.info("Fetching album details for ID: %s", album_id)

        params: dict[str, Any] = {}
        if market:
            params["market"] = market

        try:
            return await self._make_dict_request("GET", f"albums/{album_id}", params=params)
        except SpotifyAPIError:
            logger.exception(
                ERROR_MESSAGES["SPOTIFY_API_ERROR"].format(error=""),
            )
            raise

    async def get_artist(self, artist_id: str) -> dict[str, Any]:
        """Get detailed information about an artist by ID.

        Args:
            artist_id: Spotify artist ID

        Returns:
            dict: Artist information from Spotify API
        """
        logger.info("Fetching artist details for ID: %s", artist_id)

        try:
            return await self._make_dict_request("GET", f"artists/{artist_id}")
        except SpotifyAPIError:
            logger.exception(
                ERROR_MESSAGES["SPOTIFY_API_ERROR"],
            )
            raise

    async def get_tracks_with_isrc(
        self,
        album_id: str,
        market: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all tracks for an album with their ISRC codes.

        Args:
            album_id: Spotify album ID
            market: Optional market code for filtering

        Returns:
            List of tracks with metadata
        """
        logger.debug("Fetching tracks for Spotify album %s", album_id)

        # Get all tracks from the album
        tracks_url = f"albums/{album_id}/tracks"
        params: dict[str, Any] = {"limit": 50}
        if market:
            params["market"] = market

        all_album_tracks_summary = []  # Store summary tracks from album endpoint
        current_tracks_url: str | None = tracks_url  # Ensure current_tracks_url is initialized

        while current_tracks_url:
            # Use a temporary dict for params for the first request
            current_params = params if current_tracks_url == tracks_url else None
            data = await self._make_dict_request("GET", current_tracks_url, params=current_params)
            all_album_tracks_summary.extend(data["items"])
            current_tracks_url = data.get("next")
            # For subsequent paginated requests, Spotify's "next" URL includes all necessary parameters

        # Extract track IDs
        track_ids = [track["id"] for track in all_album_tracks_summary if track and track.get("id")]

        if not track_ids:
            return []

        # Fetch full track details in batches to get ISRC
        enriched_tracks_map: dict[str, dict[str, Any]] = {}
        batch_size = 50  # Spotify API limit for /v1/tracks endpoint
        for i in range(0, len(track_ids), batch_size):
            batch_track_ids = track_ids[i : i + batch_size]
            try:
                tracks_details_data = await self.get_several_tracks(batch_track_ids, market=market)
                for track_detail in tracks_details_data:
                    if track_detail and track_detail.get("id"):
                        enriched_tracks_map[track_detail["id"]] = track_detail
            except SpotifyAPIError as e:
                logger.warning(
                    "Failed to fetch batch details for tracks (%s ...): %s",
                    ", ".join(batch_track_ids[:3]),
                    str(e),
                )

        # Combine summary data with enriched data (ISRC)
        final_tracks_list = []
        for track_summary in all_album_tracks_summary:
            track_id = track_summary.get("id")
            if not track_id:
                continue

            full_track_data = enriched_tracks_map.get(track_id)
            if full_track_data:
                # Prefer data from full track details, but fallback to summary if needed
                final_tracks_list.append(
                    {
                        "name": full_track_data.get("name", track_summary.get("name", "")),
                        "id": track_id,
                        "track_number": full_track_data.get("track_number", track_summary.get("track_number")),
                        "disc_number": full_track_data.get("disc_number", track_summary.get("disc_number")),
                        "duration_ms": full_track_data.get("duration_ms", track_summary.get("duration_ms")),
                        "explicit": full_track_data.get("explicit", track_summary.get("explicit")),
                        "external_ids": full_track_data.get("external_ids", {}),  # This should contain ISRC
                        "artists": full_track_data.get(
                            "artists",
                            track_summary.get("artists"),
                        ),  # Preserve artists array
                        # Add other fields from track_summary or full_track_data as needed
                    },
                )
            else:
                # Fallback if full details for a track couldn't be fetched
                final_tracks_list.append(track_summary)
        logger.debug("Final tracks list: %s", json.dumps(final_tracks_list, indent=2))
        return final_tracks_list

    async def get_several_tracks(self, track_ids: list[str], market: str | None = None) -> list[dict[str, Any]]:
        """Get detailed information for several tracks by their IDs.

        Args:
            track_ids: A list of Spotify track IDs (max 50).
            market: An ISO 3166-1 alpha-2 country code.

        Returns:
            A list of track objects.
        """
        if not track_ids:
            return []
        if len(track_ids) > 50:
            logger.warning("Requested more than 50 tracks in get_several_tracks, only first 50 will be fetched.")
            track_ids = track_ids[:50]

        logger.info("Fetching details for %s tracks, starting with: %s", len(track_ids), track_ids[0])
        params: dict[str, Any] = {"ids": ",".join(track_ids)}
        if market:
            params["market"] = market

        try:
            data = await self._make_dict_request("GET", "tracks", params=params)
            # The response is a dict with a "tracks" key, which is a list of track objects
            return data.get("tracks", [])
        except SpotifyAPIError as e:
            logger.exception(
                "Spotify API error fetching several tracks: %s. IDs: %s",
                str(e),
                ", ".join(track_ids),
            )
            # Depending on desired behavior, could raise, or return empty, or partial results.
            # For now, let's re-raise to be consistent with other methods.
            raise

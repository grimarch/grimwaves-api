"""Tests for the MusicBrainzClient.

This module contains tests for the MusicBrainzClient class.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from grimwaves_api.modules.music.clients.musicbrainz import MusicBrainzClient
from grimwaves_api.modules.music.constants import LINK_TYPES


class TestMusicBrainzClient:
    """Test suite for MusicBrainzClient."""

    @pytest.fixture
    def client(self):
        """Create a test instance of MusicBrainzClient."""
        return MusicBrainzClient(
            app_name="TestApp",
            app_version="1.0.0",
            contact="test@example.com",
        )

    @pytest.mark.asyncio
    async def test_initialization(self, client):
        """Test that the client is properly initialized."""
        # Verify that the client is not initially initialized
        assert client._client is None
        assert client._initialized is False

        # Verify credentials are stored
        assert client.app_name == "TestApp"
        assert client.app_version == "1.0.0"
        assert client.contact == "test@example.com"

        # Verify user agent is constructed correctly
        assert client._user_agent == "TestApp/1.0.0 ( test@example.com )"

    @pytest.mark.asyncio
    async def test_lazy_initialization(self, client):
        """Test lazy initialization of HTTP client."""
        # Directly access _get_client to initialize the client
        httpx_client = await client._get_client()

        # Verify client is now initialized
        assert client._initialized is True
        assert client._client is not None

        # Verify client configuration - compare just the base part of the URL without worrying about trailing slash
        client_base_url = str(httpx_client.base_url).rstrip("/")
        expected_base_url = str(httpx.URL(client.API_BASE_URL)).rstrip("/")
        assert client_base_url == expected_base_url
        assert httpx_client.timeout == httpx.Timeout(client.DEFAULT_TIMEOUT)
        assert httpx_client.headers["User-Agent"] == client._user_agent

        # Clean up
        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test client as a context manager."""
        client_instance = None

        async with MusicBrainzClient(app_name="TestApp") as client:
            client_instance = client
            # Verify the client is initialized when used as a context manager
            assert client._client is not None
            assert client._initialized is True

        # After exiting context, client should be closed
        assert client_instance._client is None
        assert client_instance._initialized is False

    @pytest.mark.asyncio
    async def test_respect_rate_limit(self, client):
        """Test the rate limit mechanism."""
        # Set last request time to simulate a recent request
        client._last_request_time = time.time()

        # Mock sleep to avoid actual delay
        with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
            await client._respect_rate_limit()

            # Verify sleep was called with appropriate delay
            mock_sleep.assert_called_once()
            args = mock_sleep.call_args[0]
            assert args[0] > 0  # Should sleep for some duration
            assert args[0] <= client.REQUEST_DELAY  # But not more than the delay

    @pytest.mark.asyncio
    async def test_request_method_success(self, client):
        """Test successful request handling."""
        # Create a mock HTTP client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}
        mock_client.get = AsyncMock(return_value=mock_response)

        # Mock the _get_client method and _respect_rate_limit
        with (
            patch.object(client, "_get_client", AsyncMock(return_value=mock_client)),
            patch.object(client, "_respect_rate_limit", AsyncMock()),
        ):
            # Call _request method
            result = await client._request("get", "test/endpoint", params={"q": "test"})

            # Verify correct result is returned
            assert result == {"test": "data"}

            # Verify the request was made correctly
            mock_client.get.assert_called_once()
            args, kwargs = mock_client.get.call_args
            assert args[0] == f"{client.API_BASE_URL}/test/endpoint"
            assert "params" in kwargs
            # Verify fmt param is set to json
            assert kwargs["params"]["fmt"] == "json"

    @pytest.mark.asyncio
    async def test_request_rate_limit_handling(self, client):
        """Test rate limit handling in request method."""
        # Create a mock HTTP client with rate limit response first, then success
        mock_client = MagicMock()

        # First response: rate limited (429)
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"Retry-After": "2"}

        # Second response: success (200)
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"test": "data"}

        # Configure the mock to return different responses on consecutive calls
        mock_client.get = AsyncMock(side_effect=[rate_limit_response, success_response])

        # Mock the _get_client method, _respect_rate_limit, and sleep to avoid actual delay
        with (
            patch.object(client, "_get_client", AsyncMock(return_value=mock_client)),
            patch.object(client, "_respect_rate_limit", AsyncMock()),
            patch("asyncio.sleep", AsyncMock()) as mock_sleep,
        ):
            # Call _request method
            result = await client._request("get", "test/endpoint")

            # Verify correct result is returned
            assert result == {"test": "data"}

            # Verify sleep was called for rate limiting with correct delay
            mock_sleep.assert_called_once_with(2)

            # Verify get was called twice
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_search_releases(self, client):
        """Test search_releases method."""
        # Mock _request method
        mock_result = {"releases": [{"id": "123", "title": "Test Album"}]}
        with patch.object(client, "_request", AsyncMock(return_value=mock_result)) as mock_request:
            # Call search_releases
            result = await client.search_releases("Test Artist", "Test Album")

            # Verify correct result is returned
            assert result == mock_result

            # Verify _request was called correctly
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "get"
            assert args[1] == "release"
            assert "params" in kwargs
            assert "query" in kwargs["params"]
            assert 'artist:"Test Artist"' in kwargs["params"]["query"]
            assert 'release:"Test Album"' in kwargs["params"]["query"]

    @pytest.mark.asyncio
    async def test_get_release(self, client):
        """Test get_release method."""
        # Mock _request method
        mock_result = {"id": "123", "title": "Test Album"}
        with patch.object(client, "_request", AsyncMock(return_value=mock_result)) as mock_request:
            # Call get_release with additional include parameters
            result = await client.get_release("123", inc=["recordings", "artists"])

            # Verify correct result is returned
            assert result == mock_result

            # Verify _request was called correctly
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "get"
            assert args[1] == "release/123"
            assert "params" in kwargs
            assert "inc" in kwargs["params"]
            assert kwargs["params"]["inc"] == "recordings+artists"

    @pytest.mark.asyncio
    async def test_get_artist(self, client):
        """Test get_artist method."""
        # Mock _request method
        mock_result = {"id": "456", "name": "Test Artist"}
        with patch.object(client, "_request", AsyncMock(return_value=mock_result)) as mock_request:
            # Call get_artist
            result = await client.get_artist("456")

            # Verify correct result is returned
            assert result == mock_result

            # Verify _request was called correctly
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "get"
            assert args[1] == "artist/456"

    @pytest.mark.asyncio
    async def test_get_social_links(self, client):
        """Test get_social_links method."""
        # Mock get_artist method to return artist with relations
        mock_artist_result = {
            "relations": [
                {
                    "type": LINK_TYPES["OFFICIAL_HOMEPAGE"],
                    "url": {"resource": "https://example.com"},
                },
                {
                    "type": LINK_TYPES["SOCIAL_NETWORK"],
                    "url": {"resource": "https://facebook.com/artist"},
                },
                {
                    "type": LINK_TYPES["SOCIAL_NETWORK"],
                    "url": {"resource": "https://twitter.com/artist"},
                },
            ],
        }
        with patch.object(client, "get_artist", AsyncMock(return_value=mock_artist_result)) as mock_get_artist:
            # Call get_social_links
            result = await client.get_social_links("456")

            # Verify correct result is returned
            assert result["website"] == "https://example.com"
            assert result["facebook"] == "https://facebook.com/artist"
            assert result["twitter"] == "https://twitter.com/artist"
            assert result["instagram"] is None  # Not provided in mock data

            # Verify get_artist was called correctly
            mock_get_artist.assert_called_once_with("456", inc=["url-rels"])

    @pytest.mark.asyncio
    async def test_get_genres(self, client):
        """Test get_genres method."""
        # Mock get_artist method to return artist with genres
        mock_artist_result = {
            "genres": [
                {"name": "rock"},
                {"name": "alternative"},
            ],
        }
        with patch.object(client, "get_artist", AsyncMock(return_value=mock_artist_result)) as mock_get_artist:
            # Call get_genres
            result = await client.get_genres("456")

            # Verify correct result is returned
            assert len(result) == 2
            assert "rock" in result
            assert "alternative" in result

            # Verify get_artist was called correctly
            mock_get_artist.assert_called_once_with("456", inc=["genres"])

    @pytest.mark.asyncio
    async def test_search_artists(self, client):
        """Test search_artists method."""
        # Mock _request method
        mock_result = {"artists": [{"id": "456", "name": "Test Artist"}]}
        with patch.object(client, "_request", AsyncMock(return_value=mock_result)) as mock_request:
            # Call search_artists
            result = await client.search_artists("Test Artist")

            # Verify correct result is returned
            assert result == mock_result

            # Verify _request was called correctly
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "get"
            assert args[1] == "artist"
            assert "params" in kwargs
            assert "query" in kwargs["params"]
            assert 'artist:"Test Artist"' in kwargs["params"]["query"]

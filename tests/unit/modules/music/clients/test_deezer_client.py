"""Tests for the DeezerClient.

This module contains tests for the DeezerClient class.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from grimwaves_api.modules.music.clients.deezer import DeezerClient


class TestDeezerClient:
    """Test suite for DeezerClient."""

    @pytest.fixture
    def client(self):
        """Create a test instance of DeezerClient."""
        return DeezerClient(api_base_url="https://api.test.deezer.com")

    @pytest.mark.asyncio
    async def test_initialization(self, client):
        """Test that the client is properly initialized."""
        # Verify that the client is not initially initialized
        assert client._client is None
        assert client._initialized is False

        # Verify base URL is set correctly
        assert client.api_base_url == "https://api.test.deezer.com"

    @pytest.mark.asyncio
    async def test_lazy_initialization(self, client):
        """Test lazy initialization of HTTP client."""
        # Directly access _get_client to initialize the client
        httpx_client = await client._get_client()

        # Verify client is now initialized
        assert client._initialized is True
        assert client._client is not None

        # Verify client configuration
        assert httpx_client.base_url == httpx.URL(client.api_base_url)
        assert httpx_client.timeout == httpx.Timeout(client.DEFAULT_TIMEOUT)

        # Clean up
        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test client as a context manager."""
        client_instance = None

        async with DeezerClient() as client:
            client_instance = client
            # Verify the client is initialized when used as a context manager
            assert client._client is not None
            assert client._initialized is True

        # After exiting context, client should be closed
        assert client_instance._client is None
        assert client_instance._initialized is False

    @pytest.mark.asyncio
    async def test_request_method_success(self, client):
        """Test successful request handling."""
        # Create a mock HTTP client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}
        mock_client.get = AsyncMock(return_value=mock_response)

        # Mock the _get_client method
        with patch.object(client, "_get_client", AsyncMock(return_value=mock_client)):
            # Call _request method
            result = await client._request("get", "test/endpoint", params={"q": "test"})

            # Verify correct result is returned
            assert result == {"test": "data"}

            # Verify the request was made correctly
            mock_client.get.assert_called_once()
            args, kwargs = mock_client.get.call_args
            assert args[0] == f"{client.api_base_url}/test/endpoint"
            assert "params" in kwargs

    @pytest.mark.asyncio
    async def test_request_rate_limit_handling(self, client):
        """Test rate limit handling in request method."""
        # Create a mock HTTP client with rate limit response first, then success
        mock_client = MagicMock()

        # First response: rate limited (429)
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"Retry-After": "1"}

        # Second response: success (200)
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"test": "data"}

        # Configure the mock to return different responses on consecutive calls
        mock_client.get = AsyncMock(side_effect=[rate_limit_response, success_response])

        # Mock the _get_client method and sleep to avoid actual delay
        with patch.object(client, "_get_client", AsyncMock(return_value=mock_client)):
            with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
                # Call _request method
                result = await client._request("get", "test/endpoint")

                # Verify correct result is returned
                assert result == {"test": "data"}

                # Verify sleep was called for rate limiting
                mock_sleep.assert_called_once_with(1)

                # Verify get was called twice
                assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_request_retry_on_error(self, client):
        """Test retry logic on HTTP errors."""
        # Create a mock HTTP client
        mock_client = MagicMock()

        # First response: server error (500)
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("Error", request=MagicMock(), response=error_response),
        )

        # Second response: success (200)
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"test": "data"}
        success_response.raise_for_status = MagicMock()

        # Configure the mock to return different responses on consecutive calls
        mock_client.get = AsyncMock(side_effect=[error_response, success_response])

        # Mock the _get_client method and sleep to avoid actual delay
        with patch.object(client, "_get_client", AsyncMock(return_value=mock_client)):
            with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
                # Call _request method
                result = await client._request("get", "test/endpoint")

                # Verify correct result is returned
                assert result == {"test": "data"}

                # Verify sleep was called for backoff
                mock_sleep.assert_called_once()

                # Verify get was called twice
                assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_search_releases(self, client):
        """Test search_releases method."""
        # Mock _request method
        mock_result = {
            "data": [{"id": "123", "title": "Test Album"}],
            "total": 1,
        }
        with patch.object(client, "_request", AsyncMock(return_value=mock_result)) as mock_request:
            # Call search_releases
            result = await client.search_releases("Test Artist", "Test Album")

            # Verify correct result is returned
            assert result == mock_result

            # Verify _request was called correctly
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "GET"
            assert args[1] == "search/album"
            assert "params" in kwargs
            assert "q" in kwargs["params"]
            assert 'artist:"Test Artist"' in kwargs["params"]["q"]
            assert 'album:"Test Album"' in kwargs["params"]["q"]

    @pytest.mark.asyncio
    async def test_get_album(self, client):
        """Test get_album method."""
        # Mock _request method
        mock_result = {"id": "123", "title": "Test Album"}
        with patch.object(client, "_request", AsyncMock(return_value=mock_result)) as mock_request:
            # Call get_album
            result = await client.get_album("123")

            # Verify correct result is returned
            assert result == mock_result

            # Verify _request was called correctly
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "GET"
            assert args[1] == "album/123"

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
            assert args[0] == "GET"
            assert args[1] == "artist/456"

    @pytest.mark.asyncio
    async def test_get_album_tracks(self, client):
        """Test get_album_tracks method."""
        # Mock _request method
        mock_result = {"data": [{"id": "789", "title": "Test Track"}]}
        with patch.object(client, "_request", AsyncMock(return_value=mock_result)) as mock_request:
            # Call get_album_tracks
            result = await client.get_album_tracks("123")

            # Verify correct result is returned
            assert result == mock_result["data"]

            # Verify _request was called correctly
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "GET"
            assert args[1] == "album/123/tracks"

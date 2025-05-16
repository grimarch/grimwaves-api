"""Tests for the SpotifyClient.

This module contains tests for the SpotifyClient class.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from grimwaves_api.modules.music.clients.spotify import SpotifyClient


class TestSpotifyClient:
    """Test suite for SpotifyClient."""

    @pytest.fixture
    def client(self):
        """Create a test instance of SpotifyClient."""
        return SpotifyClient(client_id="test_client_id", client_secret="test_client_secret")

    @pytest.mark.asyncio
    async def test_initialization(self, client):
        """Test that the client is properly initialized."""
        # Verify that the client is not initially initialized
        assert client._client is None
        assert client._initialized is False

        # Verify credentials are stored
        assert client._client_id == "test_client_id"
        assert client._client_secret == "test_client_secret"

    @pytest.mark.asyncio
    async def test_lazy_initialization(self, client):
        """Test lazy initialization of HTTP client."""
        # Mock _ensure_token to avoid actual token refresh
        with patch.object(client, "_ensure_token", AsyncMock()):
            # Directly access _get_client to initialize the client
            await client._get_client()

            # Verify client is now initialized
            assert client._initialized is True
            assert client._client is not None

            # Clean up
            await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test client as a context manager."""
        client_instance = None

        # Mock _ensure_token to avoid actual token refresh during initialization
        with patch.object(SpotifyClient, "_ensure_token", AsyncMock()):
            async with SpotifyClient(client_id="test_id", client_secret="test_secret") as client:
                client_instance = client
                # Force initialization of client
                await client._get_client()
                # Verify the client is initialized
                assert client._client is not None
                assert client._initialized is True

        # After exiting context, client should be closed
        assert client_instance._client is None
        assert client_instance._initialized is False

    @pytest.mark.asyncio
    async def test_token_refresh(self, client):
        """Test token refresh mechanism."""
        # Mock the HTTP client's post method
        with patch("httpx.AsyncClient.post") as mock_post:
            # Create a mock response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": "test_token",
                "expires_in": 3600,
            }
            mock_post.return_value = mock_response

            # Call refresh token
            await client._refresh_token()

            # Verify token was set
            assert client._token == "test_token"
            assert client._token_expiry > datetime.now(timezone.utc)

            # Verify the request was made correctly
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert args[0] == client.AUTH_URL
            assert "headers" in kwargs
            assert "data" in kwargs
            assert kwargs["data"] == {"grant_type": "client_credentials"}

        # Clean up
        await client.close()

    @pytest.mark.asyncio
    async def test_search_releases(self, client):
        """Test search_releases method."""
        # Mock _make_request method
        with patch.object(SpotifyClient, "_make_request") as mock_request:
            mock_request.return_value = {"albums": {"items": [{"name": "Test Album"}]}}

            # Call search_releases
            result = await client.search_releases("Test Artist", "Test Album")

            # Verify correct result is returned
            assert "albums" in result
            assert len(result["albums"]["items"]) == 1

            # Verify _make_request was called correctly
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "GET"
            assert args[1] == "search"
            assert "params" in kwargs
            assert "q" in kwargs["params"]
            assert kwargs["params"]["q"] == "artist:Test Artist album:Test Album"

        # Clean up
        await client.close()

    @pytest.mark.asyncio
    async def test_get_album(self, client):
        """Test get_album method."""
        # Mock _make_request method
        with patch.object(SpotifyClient, "_make_request") as mock_request:
            mock_request.return_value = {"id": "album_id", "name": "Test Album"}

            # Call get_album
            result = await client.get_album("album_id")

            # Verify correct result is returned
            assert result["id"] == "album_id"
            assert result["name"] == "Test Album"

            # Verify _make_request was called correctly
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "GET"
            assert args[1] == "albums/album_id"

        # Clean up
        await client.close()

    @pytest.mark.asyncio
    async def test_error_handling(self, client):
        """Test error handling in _make_request method."""
        # Mock _get_client to return a client that raises an exception
        with patch.object(client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.request = AsyncMock(side_effect=httpx.RequestError("Test error"))
            mock_get_client.return_value = mock_client

            # Also mock _ensure_token to avoid actual token refresh
            with patch.object(client, "_ensure_token", AsyncMock()):
                # Call _make_request and expect an exception
                with pytest.raises(Exception):
                    await client._make_request("GET", "test")

        # Clean up
        await client.close()

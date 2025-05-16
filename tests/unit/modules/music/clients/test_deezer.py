"""Tests for the Deezer API client."""

from unittest.mock import AsyncMock, patch

import pytest

from grimwaves_api.modules.music.clients.deezer import DeezerClient


@pytest.fixture
def deezer_client() -> DeezerClient:
    """Create a Deezer client for testing."""
    return DeezerClient(api_base_url="https://api.deezer.com")


@pytest.mark.asyncio
async def test_search_releases(deezer_client: DeezerClient) -> None:
    """Test searching for releases."""
    with patch.object(deezer_client, "_request", new_callable=AsyncMock) as mock_request:
        # Prepare fake data for the response
        mock_data = {
            "data": [
                {
                    "id": 123456,
                    "title": "Test Album",
                    "artist": {"name": "Test Artist"},
                },
            ],
            "total": 1,
        }
        mock_request.return_value = mock_data

        # Call the search_releases method
        result = await deezer_client.search_releases("Test Artist", "Test Album")

        # Assertions
        assert result == mock_data
        mock_request.assert_called_once_with(
            "GET",
            "search/album",
            params={
                "q": 'artist:"Test Artist" album:"Test Album"',
                "limit": 10,
                "type": "album",
            },
        )


@pytest.mark.asyncio
async def test_get_album(deezer_client: DeezerClient) -> None:
    """Test getting album details."""
    with patch.object(deezer_client, "_request", new_callable=AsyncMock) as mock_request:
        # Prepare fake data for the response
        mock_data = {
            "id": 123456,
            "title": "Test Album",
            "artist": {"name": "Test Artist"},
            "tracks": {"data": [{"id": 1, "title": "Track 1"}]},
        }
        mock_request.return_value = mock_data

        # Call the get_album method
        result = await deezer_client.get_album("123456")

        # Assertions
        assert result == mock_data
        mock_request.assert_called_once_with("GET", "album/123456")


@pytest.mark.asyncio
async def test_get_track(deezer_client: DeezerClient) -> None:
    """Test getting track details."""
    with patch.object(deezer_client, "_request", new_callable=AsyncMock) as mock_request:
        # Prepare fake data for the response
        mock_data = {
            "id": 1,
            "title": "Track 1",
            "isrc": "USISRC12345678",
        }
        mock_request.return_value = mock_data

        # Call the get_track method
        result = await deezer_client.get_track("1")

        # Assertions
        assert result == mock_data
        mock_request.assert_called_once_with("GET", "track/1")

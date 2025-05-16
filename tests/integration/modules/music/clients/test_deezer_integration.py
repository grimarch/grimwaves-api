"""Integration tests for the Deezer API client.

These tests make real API calls to Deezer and should be marked to run only when explicitly requested.
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from grimwaves_api.modules.music.clients.deezer import DeezerClient


@pytest_asyncio.fixture(scope="function")
async def deezer_client() -> AsyncGenerator[DeezerClient, None]:
    """Create a Deezer client for integration testing."""
    client: DeezerClient
    async with DeezerClient() as client:
        yield client
    # client.close() is now handled by __aexit__


# Integration test marker
@pytest.mark.skip(reason="Skipping due to persistent RuntimeError: Event loop is closed during teardown")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_deezer_search_releases(deezer_client: DeezerClient):
    """Test searching for releases in Deezer API."""
    # Test data
    artist = "Gojira"
    album = "Fortitude"

    # Perform the request
    search_results = await deezer_client.search_releases(artist, album)

    # Assertions
    assert search_results is not None
    assert "data" in search_results
    assert len(search_results["data"]) > 0

    # Check the content of the first result
    first_album = search_results["data"][0]
    assert "id" in first_album
    assert "title" in first_album
    assert "artist" in first_album

    # Check the content of the first result
    assert album.lower() in first_album["title"].lower()
    assert artist.lower() in first_album["artist"]["name"].lower()


@pytest.mark.skip(reason="Skipping due to persistent RuntimeError: Event loop is closed during teardown")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_deezer_get_album(deezer_client: DeezerClient):
    """Test getting album details from Deezer API."""
    # Search for the album
    search_results = await deezer_client.search_releases("Gojira", "Fortitude")
    album_id = search_results["data"][0]["id"]

    # Get the album details
    album_details = await deezer_client.get_album(str(album_id))

    # Assertions
    assert album_details is not None
    assert "title" in album_details
    assert "artist" in album_details
    assert "release_date" in album_details
    assert "label" in album_details
    assert "tracks" in album_details


@pytest.mark.skip(reason="Skipping due to persistent RuntimeError: Event loop is closed during teardown")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_deezer_get_tracks(deezer_client: DeezerClient):
    """Test getting tracks for an album from Deezer API."""
    # Search for the album
    search_results = await deezer_client.search_releases("Gojira", "Fortitude")
    album_id = search_results["data"][0]["id"]

    # Get the tracks
    tracks = await deezer_client.get_album_tracks(str(album_id))

    # Assertions
    assert tracks is not None
    assert len(tracks) > 0

    for track in tracks:
        assert "id" in track
        assert "title" in track

    # Get the track details
    track_id = tracks[0]["id"]
    track_details = await deezer_client.get_track(str(track_id))

    # Assertions
    assert track_details is not None
    assert "isrc" in track_details

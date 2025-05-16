#!/usr/bin/env python3
"""Test script to check the functionality of MusicMetadataService.

This script demonstrates the use of MusicMetadataService to retrieve
combined metadata about music releases from different sources.

Run:
    python -m grimwaves_api.scripts.test_music_metadata_service
"""

import asyncio
import logging
import sys
import types
from typing import Any
from unittest.mock import AsyncMock, patch

from grimwaves_api.modules.music.clients import DeezerClient, MusicBrainzClient, SpotifyClient
from grimwaves_api.modules.music.service import MusicMetadataService


# Patch SpotifyClient to work without credentials
def patch_spotify_client() -> list[Any]:
    """Replace SpotifyClient methods with mocks for testing."""
    print("Patching SpotifyClient for testing...")

    # Create mock objects for patching
    token_mock = types.SimpleNamespace(access_token="fake_token", expires_at=9999999999)  # noqa: S106

    # Mock for the authenticate method
    authenticate_mock = AsyncMock(return_value=token_mock)

    # Create mocks with predefined responses
    def search_result_factory(**kwargs: Any) -> dict[str, Any]:
        return {
            "albums": {
                "items": [
                    {
                        "id": "test_album_id_1",
                        "name": kwargs["params"]["q"].split("album:")[1],
                        "artists": [{"name": kwargs["params"]["q"].split("artist:")[1].split(" album:")[0]}],
                        "album_type": "album",
                    },
                ],
            },
        }

    # Mock for the _request method with type hinting
    def _request_side_effect(_method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        if endpoint == "search":
            return search_result_factory(**kwargs)
        return {}

    request_mock = AsyncMock()
    request_mock.side_effect = _request_side_effect

    album_mock = AsyncMock(
        return_value={
            "name": "Test Album",
            "release_date": "2023-01-01",
            "label": "Test Label",
            "id": "test_album_id",
        },
    )

    tracks_mock = AsyncMock(
        return_value=[
            {"title": "Test Track 1", "isrc": "USABC1234567"},
            {"title": "Test Track 2", "isrc": "USABC1234568"},
            {"title": "Test Track 3", "isrc": "USABC1234569"},
        ],
    )

    # Apply patches
    # Create a list of patchers
    patchers = [
        patch.object(SpotifyClient, "authenticate", authenticate_mock),
        patch.object(SpotifyClient, "_request", request_mock),
        patch.object(SpotifyClient, "get_album", album_mock),
        patch.object(SpotifyClient, "get_tracks_with_isrc", tracks_mock),
        # Add async context manager support
        patch.object(SpotifyClient, "__aenter__", AsyncMock(return_value=SpotifyClient("fake_id", "fake_secret"))),
        patch.object(SpotifyClient, "__aexit__", AsyncMock(return_value=None)),
    ]

    # Start all patchers
    for patcher in patchers:
        _ = patcher.start()

    print("SpotifyClient successfully patched!")
    return patchers


# Patch DeezerClient and MusicBrainzClient for testing
def patch_other_clients() -> list[Any]:
    """Replace DeezerClient and MusicBrainzClient methods with mocks for testing."""
    print("Patching DeezerClient and MusicBrainzClient for testing...")

    # Mock MusicBrainz search results
    mb_search_mock = AsyncMock(
        return_value={
            "releases": [
                {
                    "id": "test_release_id",
                    "title": "Test Release",
                    "artist-credit": [{"artist": {"id": "test_artist_id", "name": "Test Artist"}}],
                    "primary-type": "Album",
                },
            ],
        },
    )

    # Mock MusicBrainz artist data
    mb_artist_data_mock = AsyncMock(
        return_value={
            "url-relations": [
                {"type": "official homepage", "url": {"resource": "https://testartist.com"}},
                {"type": "social network", "url": {"resource": "https://facebook.com/testartist"}},
            ],
            "genres": [{"name": "Test Genre 1"}, {"name": "Test Genre 2"}],
        },
    )

    # Mock Deezer album tracks
    deezer_tracks_mock = AsyncMock(
        return_value=[
            {"title": "Deezer Track 1", "isrc": "USABC1234567"},
            {"title": "Deezer Track 2", "isrc": "USABC1234568"},
        ],
    )

    # Create patchers for MusicBrainzClient
    mb_patchers = [
        patch.object(MusicBrainzClient, "search_releases", mb_search_mock),
        patch.object(MusicBrainzClient, "get_artist_data", mb_artist_data_mock),
        patch.object(MusicBrainzClient, "__aenter__", AsyncMock(return_value=MusicBrainzClient("Test App"))),
        patch.object(MusicBrainzClient, "__aexit__", AsyncMock(return_value=None)),
    ]

    # Create patchers for DeezerClient
    deezer_patchers = [
        patch.object(DeezerClient, "get_album_tracks", deezer_tracks_mock),
        patch.object(DeezerClient, "__aenter__", AsyncMock(return_value=DeezerClient())),
        patch.object(DeezerClient, "__aexit__", AsyncMock(return_value=None)),
    ]

    # Start all patchers
    patchers = mb_patchers + deezer_patchers
    for patcher in patchers:
        _ = patcher.start()

    print("DeezerClient and MusicBrainzClient successfully patched!")
    return patchers


def print_main_info(result: dict[str, Any]) -> None:
    """Print main information about the release."""
    print("\nMain information:")
    print(f"Artist: {result.get('artist')}")
    print(f"Release: {result.get('release')}")
    print(f"Release date: {result.get('release_date')}")
    print(f"Label: {result.get('label')}")


def print_genres(result: dict[str, Any]) -> None:
    """Print genres information."""
    genres = result.get("genre", [])
    if genres:
        print(f"\nGenres ({len(genres)}):")
        for genre in genres:
            print(f"- {genre}")
    else:
        print("\nGenres: not found")


def print_social_links(result: dict[str, Any]) -> None:
    """Print social links information."""
    social_links = result.get("social_links", {})
    if any(social_links.values()):
        print("\nSocial links:")
        for platform, url in social_links.items():
            if url:
                print(f"- {platform}: {url}")
    else:
        print("\nSocial links: not found")


def print_tracks(result: dict[str, Any]) -> None:
    """Print tracks information."""
    tracks = result.get("tracks", [])
    if tracks:
        print(f"\nTracks ({len(tracks)}):")
        for i, track in enumerate(tracks[:5], 1):
            isrc = track.get("isrc", "No ISRC")
            print(f"{i}. {track.get('title')} [ISRC: {isrc}]")
        if len(tracks) > 5:
            print(f"... and {len(tracks) - 5} more tracks")
    else:
        print("\nTracks: not found")


async def test_fetch_release_metadata(
    band_name: str,
    release_name: str,
    country_code: str | None = None,
    use_context_manager: bool = True,
) -> dict[str, Any] | None:
    """Testing the retrieval of release metadata.

    Args:
        band_name: Name of the artist or band
        release_name: Name of the release
        country_code: Optional country code
        use_context_manager: Whether to use context manager pattern

    Returns:
        Release metadata or None if an error occurred
    """
    print(f"\n=== Getting metadata for release: {band_name} - {release_name} ===")
    if country_code:
        print(f"Country code: {country_code}")

    print(f"Using context manager: {'Yes' if use_context_manager else 'No'}")

    # Create client instances
    spotify_client = SpotifyClient("test_client_id", "test_client_secret")
    deezer_client = DeezerClient()
    mb_client = MusicBrainzClient("Test App")

    # Initialize service with mock clients
    service = MusicMetadataService(
        spotify_client=spotify_client,
        deezer_client=deezer_client,
        musicbrainz_client=mb_client,
    )

    try:
        if use_context_manager:
            # Using async context manager for proper resource management
            async with service as metadata_service:
                result = await metadata_service.fetch_release_metadata(
                    band_name=band_name,
                    release_name=release_name,
                    country_code=country_code,
                )
        else:
            # Old approach without context manager
            result = await service.fetch_release_metadata(
                band_name=band_name,
                release_name=release_name,
                country_code=country_code,
            )
            # Need to manually close resources
            await service.close()

        print_main_info(result)
        print_genres(result)
        print_social_links(result)
        print_tracks(result)

        return result

    except Exception as e:
        print(f"Error getting metadata: {e}")
        # If not using context manager, we need to ensure resources are closed
        if not use_context_manager:
            await service.close()
        return None


async def run_tests() -> None:
    """Run all tests."""
    # Patch clients
    spotify_patchers = patch_spotify_client()
    other_patchers = patch_other_clients()
    all_patchers = spotify_patchers + other_patchers

    try:
        # Test 1: Popular release with context manager
        _ = await test_fetch_release_metadata("Metallica", "Master of Puppets", use_context_manager=True)

        # Test 2: Less popular release without context manager
        _ = await test_fetch_release_metadata("Opeth", "Ghost Reveries", use_context_manager=False)

        # Test 3: Release with country specification with context manager
        _ = await test_fetch_release_metadata("The Beatles", "Abbey Road", "GB", use_context_manager=True)
    finally:
        # Stop all patchers
        for patcher in all_patchers:
            patcher.stop()


if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.INFO)

    try:
        asyncio.run(run_tests())
    except KeyboardInterrupt:
        print("\nTesting interrupted by user")
        sys.exit(0)

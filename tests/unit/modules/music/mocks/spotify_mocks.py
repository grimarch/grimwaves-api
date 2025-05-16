from typing import Any

# Default mock values
DEFAULT_SPOTIFY_ALBUM_ID = "spotify_album_id_mock"
DEFAULT_SPOTIFY_ARTIST_ID = "spotify_artist_id_mock"
DEFAULT_SPOTIFY_TRACK_ID_PREFIX = "spotify_track_id_mock_"


def mock_spotify_search_results_single_item(
    album_id: str = DEFAULT_SPOTIFY_ALBUM_ID,
    album_name: str = "Mock Spotify Album",
    artist_name: str = "Mock Spotify Artist",
    artist_id: str = DEFAULT_SPOTIFY_ARTIST_ID,
    release_date: str = "2023-01-01",
    total_tracks: int = 10,
    popularity: int = 50,
    market: str | list[str] | None = "US",
) -> dict[str, Any]:
    """Generate a mock Spotify search result with a single album item."""
    if market is None:
        market = ["US", "GB", "DE"]  # Default available markets
    elif isinstance(market, str):
        market = [market]

    return {
        "albums": {
            "href": f"https://api.spotify.com/v1/search?query=album%3A{album_name}+artist%3A{artist_name}&type=album&offset=0&limit=1",
            "items": [
                {
                    "album_type": "album",
                    "artists": [
                        {
                            "external_urls": {"spotify": f"https://open.spotify.com/artist/{artist_id}"},
                            "href": f"https://api.spotify.com/v1/artists/{artist_id}",
                            "id": artist_id,
                            "name": artist_name,
                            "type": "artist",
                            "uri": f"spotify:artist:{artist_id}",
                        },
                    ],
                    "available_markets": market,
                    "external_urls": {"spotify": f"https://open.spotify.com/album/{album_id}"},
                    "href": f"https://api.spotify.com/v1/albums/{album_id}",
                    "id": album_id,
                    "images": [
                        {"height": 640, "url": "https://i.scdn.co/image/ab67616d0000b273mockimage1", "width": 640},
                        {"height": 300, "url": "https://i.scdn.co/image/ab67616d00001e02mockimage2", "width": 300},
                        {"height": 64, "url": "https://i.scdn.co/image/ab67616d00004851mockimage3", "width": 64},
                    ],
                    "name": album_name,
                    "release_date": release_date,
                    "release_date_precision": "day",
                    "total_tracks": total_tracks,
                    "type": "album",
                    "uri": f"spotify:album:{album_id}",
                },
            ],
            "limit": 1,
            "next": None,
            "offset": 0,
            "previous": None,
            "total": 1,
        },
    }


def mock_spotify_album_details_complete(
    album_id: str = DEFAULT_SPOTIFY_ALBUM_ID,
    album_name: str = "Mock Spotify Album Details",
    artist_name: str = "Mock Spotify Artist Details",
    artist_id: str = DEFAULT_SPOTIFY_ARTIST_ID,
    label: str = "Mock Spotify Label",
    release_date: str = "2023-02-15",
    genres: list[str] | None = None,
    popularity: int = 75,
    total_tracks: int = 12,
    tracks_items_count: int = 12,  # Number of track items in the tracks paginator
) -> dict[str, Any]:
    """Generate a mock Spotify album details response."""
    if genres is None:
        genres = ["Mock Genre 1", "Mock Genre 2"]

    # Generate minimal track items for the album details
    track_items = []
    for i in range(tracks_items_count):
        track_items.append(
            {
                "artists": [
                    {
                        "external_urls": {"spotify": f"https://open.spotify.com/artist/{artist_id}"},
                        "href": f"https://api.spotify.com/v1/artists/{artist_id}",
                        "id": artist_id,
                        "name": artist_name,
                        "type": "artist",
                        "uri": f"spotify:artist:{artist_id}",
                    },
                ],
                "available_markets": ["US", "GB", "DE"],
                "disc_number": 1,
                "duration_ms": 240000 + i * 1000,  # 4 minutes + i seconds
                "explicit": False,
                "external_urls": {
                    "spotify": f"https://open.spotify.com/track/{DEFAULT_SPOTIFY_TRACK_ID_PREFIX}{i + 1}",
                },
                "href": f"https://api.spotify.com/v1/tracks/{DEFAULT_SPOTIFY_TRACK_ID_PREFIX}{i + 1}",
                "id": f"{DEFAULT_SPOTIFY_TRACK_ID_PREFIX}{i + 1}",
                "is_local": False,
                "name": f"Track {i + 1}",
                "preview_url": f"https://p.scdn.co/mp3-preview/mockpreview{i + 1}",
                "track_number": i + 1,
                "type": "track",
                "uri": f"spotify:track:{DEFAULT_SPOTIFY_TRACK_ID_PREFIX}{i + 1}",
            },
        )

    return {
        "album_type": "album",
        "artists": [
            {
                "external_urls": {"spotify": f"https://open.spotify.com/artist/{artist_id}"},
                "href": f"https://api.spotify.com/v1/artists/{artist_id}",
                "id": artist_id,
                "name": artist_name,
                "type": "artist",
                "uri": f"spotify:artist:{artist_id}",
            },
        ],
        "available_markets": ["US", "GB", "DE", "JP", "CA"],
        "copyrights": [{"text": "© 2023 Mock Copyright", "type": "C"}, {"text": "℗ 2023 Mock Copyright", "type": "P"}],
        "external_ids": {"upc": "123456789012"},
        "external_urls": {"spotify": f"https://open.spotify.com/album/{album_id}"},
        "genres": genres,
        "href": f"https://api.spotify.com/v1/albums/{album_id}",
        "id": album_id,
        "images": [
            {"height": 640, "url": "https://i.scdn.co/image/ab67616d0000b273mockdetails1", "width": 640},
            {"height": 300, "url": "https://i.scdn.co/image/ab67616d00001e02mockdetails2", "width": 300},
        ],
        "label": label,
        "name": album_name,
        "popularity": popularity,
        "release_date": release_date,
        "release_date_precision": "day",
        "total_tracks": total_tracks,
        "tracks": {
            "href": f"https://api.spotify.com/v1/albums/{album_id}/tracks?offset=0&limit={tracks_items_count}",
            "items": track_items,
            "limit": tracks_items_count,
            "next": None,
            "offset": 0,
            "previous": None,
            "total": total_tracks,  # Should match album's total_tracks
        },
        "type": "album",
        "uri": f"spotify:album:{album_id}",
    }


def mock_spotify_tracks_complete(
    album_id: str = DEFAULT_SPOTIFY_ALBUM_ID,
    artist_name: str = "Mock Spotify Artist For Tracks",
    artist_id: str = DEFAULT_SPOTIFY_ARTIST_ID,
    count: int = 1,
    start_isrc_int: int = 12345,  # Just for generating varied ISRCs
) -> list[dict[str, Any]]:
    """Generate a list of mock Spotify track items, typically from get_tracks_with_isrc."""
    tracks = []
    for i in range(count):
        isrc_country = "US"
        isrc_registrant = "M0K"  # Mock registrant
        isrc_year = "23"  # Year 2023
        isrc_designation = str(start_isrc_int + i).zfill(5)
        isrc = f"{isrc_country}{isrc_registrant}{isrc_year}{isrc_designation}"

        tracks.append(
            {
                "album": {  # Simplified album representation within track item
                    "album_type": "album",
                    "artists": [{"name": artist_name, "id": artist_id}],
                    "id": album_id,
                    "name": f"Album for Track {i + 1}",
                    "release_date": "2023-03-01",
                    "total_tracks": count,
                },
                "artists": [
                    {
                        "external_urls": {"spotify": f"https://open.spotify.com/artist/{artist_id}"},
                        "href": f"https://api.spotify.com/v1/artists/{artist_id}",
                        "id": artist_id,
                        "name": artist_name,
                        "type": "artist",
                        "uri": f"spotify:artist:{artist_id}",
                    },
                ],
                "disc_number": 1,
                "duration_ms": 200000 + i * 5000,  # 3:20 + i*5 seconds
                "explicit": i % 2 == 0,  # Alternate explicit
                "external_ids": {"isrc": isrc},
                "external_urls": {
                    "spotify": f"https://open.spotify.com/track/{DEFAULT_SPOTIFY_TRACK_ID_PREFIX}detail_{i + 1}",
                },
                "href": f"https://api.spotify.com/v1/tracks/{DEFAULT_SPOTIFY_TRACK_ID_PREFIX}detail_{i + 1}",
                "id": f"{DEFAULT_SPOTIFY_TRACK_ID_PREFIX}detail_{i + 1}",
                "is_playable": True,
                "name": f"Mock Track Title {i + 1}",
                "popularity": 60 + i,
                "preview_url": f"https://p.scdn.co/mp3-preview/mocktrackdetail{i + 1}",
                "track_number": i + 1,
                "type": "track",
                "uri": f"spotify:track:{DEFAULT_SPOTIFY_TRACK_ID_PREFIX}detail_{i + 1}",
            },
        )
    return tracks

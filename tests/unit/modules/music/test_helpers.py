"""Unit tests for music metadata helper functions."""

from unittest.mock import AsyncMock

import pytest

from grimwaves_api.modules.music.helpers import _transform_deezer_cached_data, check_existing_result
from grimwaves_api.modules.music.schemas import Track

# Sample data for mocking cache responses
SAMPLE_DEEZER_SEARCH_RESULT_ITEM = {"id": "dz123", "title": "Deezer Album"}
SAMPLE_DEEZER_RELEASE_DETAILS = {
    "id": "dz123",
    "title": "Deezer Album",
    "artist": {"name": "Deezer Artist"},
    "release_date": "2023-03-03",
    "label": "Deezer Label",
    "genres": {"data": [{"name": "Deezer Genre"}]},
    "tracks": {"data": [{"title_short": "Deezer Track 1", "isrc": "DZISRC001"}]},
}
SAMPLE_SPOTIFY_SEARCH_RESULT_ITEM = {"id": "sp456", "name": "Spotify Album"}
SAMPLE_SPOTIFY_RELEASE_DETAILS = {
    "id": "sp456",
    "name": "Spotify Album",
    "artists": [{"name": "Spotify Artist"}],
    "release_date": "2023-01-01",
    "label": "Spotify Label",
    "genres": ["Spotify Genre"],
    "tracks": {"items": [{"name": "Spotify Track 1", "external_ids": {"isrc": "SPISRC001"}}]},
}


@pytest.mark.asyncio
async def test_transform_deezer_valid_full_data():
    """Test with valid, complete Deezer API-like data."""
    raw_data = {
        "id": "302127",
        "title": "Discovery",
        "upc": "724384960650",
        "link": "https://www.deezer.com/album/302127",
        "share": "https://www.deezer.com/album/302127?utm_source=deezer&utm_content=album-302127&utm_term=0_1700000000&utm_medium=web",
        "cover": "https://api.deezer.com/album/302127/image",
        "cover_small": "https://e-cdns-images.dzcdn.net/images/cover/2e018122cb56986277102d2041a592c8/56x56-000000-80-0-0.jpg",
        "cover_medium": "https://e-cdns-images.dzcdn.net/images/cover/2e018122cb56986277102d2041a592c8/250x250-000000-80-0-0.jpg",
        "cover_big": "https://e-cdns-images.dzcdn.net/images/cover/2e018122cb56986277102d2041a592c8/500x500-000000-80-0-0.jpg",
        "cover_xl": "https://e-cdns-images.dzcdn.net/images/cover/2e018122cb56986277102d2041a592c8/1000x1000-000000-80-0-0.jpg",
        "md5_image": "2e018122cb56986277102d2041a592c8",
        "genre_id": 113,
        "genres": {
            "data": [
                {"id": 113, "name": "Dance", "picture": "https://api.deezer.com/genre/113/image"},
                {"id": 106, "name": "Electro", "picture": "https://api.deezer.com/genre/106/image"},
            ],
        },
        "label": "Parlophone (France)",
        "nb_tracks": 14,
        "duration": 3660,
        "fans": 123456,
        "release_date": "2001-03-07",
        "record_type": "album",
        "available": True,
        "tracklist": "https://api.deezer.com/album/302127/tracks",
        "explicit_lyrics": False,
        "explicit_content_lyrics": 0,
        "explicit_content_cover": 0,
        "contributors": [
            {
                "id": 27,
                "name": "Daft Punk",
                "link": "https://www.deezer.com/artist/27",
                "share": "https://www.deezer.com/artist/27?utm_source=deezer&utm_content=artist-27&utm_term=0_1700000000&utm_medium=web",
                "picture": "https://api.deezer.com/artist/27/image",
                "picture_small": "https://e-cdns-images.dzcdn.net/images/artist/f2bc007e9133c946ac3c3907ddc5d2ea/56x56-000000-80-0-0.jpg",
                "picture_medium": "https://e-cdns-images.dzcdn.net/images/artist/f2bc007e9133c946ac3c3907ddc5d2ea/250x250-000000-80-0-0.jpg",
                "picture_big": "https://e-cdns-images.dzcdn.net/images/artist/f2bc007e9133c946ac3c3907ddc5d2ea/500x500-000000-80-0-0.jpg",
                "picture_xl": "https://e-cdns-images.dzcdn.net/images/artist/f2bc007e9133c946ac3c3907ddc5d2ea/1000x1000-000000-80-0-0.jpg",
                "radio": True,
                "tracklist": "https://api.deezer.com/artist/27/top?limit=50",
                "type": "artist",
                "role": "Main",
            },
        ],
        "artist": {  # Main artist for the album
            "id": 27,
            "name": "Daft Punk",
            "picture": "https://api.deezer.com/artist/27/image",
            "type": "artist",
        },
        "type": "album",
        "tracks": {
            "data": [
                {
                    "id": 3135553,
                    "readable": True,
                    "title": "One More Time",
                    "title_short": "One More Time",
                    "title_version": "",
                    "link": "https://www.deezer.com/track/3135553",
                    "duration": 320,
                    "rank": 900000,
                    "explicit_lyrics": False,
                    "explicit_content_lyrics": 0,
                    "explicit_content_cover": 0,
                    "preview": "https://cdns-preview-d.dzcdn.net/stream/c-d8f6e0e8c5a0e3f29e45f1f99a543034-12.mp3",
                    "md5_image": "2e018122cb56986277102d2041a592c8",
                    "isrc": "GBDUW0000058",
                    "artist": {"name": "Daft Punk"},  # Track artist might differ from album artist
                    "type": "track",
                },
                {
                    "id": 3135554,
                    "readable": True,
                    "title": "Aerodynamic",
                    "title_short": "Aerodynamic",
                    "title_version": "",
                    "link": "https://www.deezer.com/track/3135554",
                    "duration": 212,
                    "rank": 780000,
                    "explicit_lyrics": False,
                    "explicit_content_lyrics": 0,
                    "explicit_content_cover": 0,
                    "preview": "https://cdns-preview-e.dzcdn.net/stream/c-e5d5f0e8c5a0e3f29e45f1f99a543034-12.mp3",
                    "md5_image": "2e018122cb56986277102d2041a592c8",
                    "isrc": "GBDUW0000059",
                    "artist": {"name": "Daft Punk"},
                    "type": "track",
                },
            ],
        },
    }
    transformed = await _transform_deezer_cached_data(raw_data, country_code="FR")
    assert transformed is not None
    assert transformed["artist"]["name"] == "Daft Punk"
    assert transformed["release_title"] == "Discovery"
    assert transformed["release_date"] == "2001-03-07"
    assert transformed["label"] == "Parlophone (France)"
    assert "Dance" in transformed["genres"]
    assert "Electro" in transformed["genres"]
    assert transformed["tracks"] is not None
    assert transformed["album_type"] == "album"
    assert len(transformed["tracks"]) == 2

    track1 = Track(**transformed["tracks"][0])
    assert track1.title == "One More Time"
    assert track1.isrc == "GBDUW0000058"

    track2 = Track(**transformed["tracks"][1])
    assert track2.title == "Aerodynamic"
    assert track2.isrc == "GBDUW0000059"
    assert transformed.get("social_links") == {}  # Explicitly check for empty social_links


@pytest.mark.asyncio
async def test_transform_deezer_missing_optional_fields():
    """Test with data missing optional fields (e.g., label, some track ISRCs, genres)."""
    raw_data = {
        "id": "12345",
        "title": "Test Album",
        "release_date": "2023-01-01",
        "artist": {"name": "Test Artist"},
        # No label
        # No genres
        "tracks": {
            "data": [
                {"title_short": "Track 1", "isrc": "US1234567890"},
                {"title_short": "Track 2"},  # No ISRC
            ],
        },
    }
    transformed = await _transform_deezer_cached_data(raw_data, country_code=None)
    assert transformed is not None
    assert transformed["artist"]["name"] == "Test Artist"
    assert transformed["release_title"] == "Test Album"
    assert transformed["release_date"] == "2023-01-01"
    assert transformed["label"] is None
    assert transformed["tracks"] is not None
    assert transformed["genres"] == []
    assert transformed["album_type"] is None
    assert len(transformed["tracks"]) == 2

    track1 = Track(**transformed["tracks"][0])
    assert track1.title == "Track 1"
    assert track1.isrc == "US1234567890"

    track2 = Track(**transformed["tracks"][1])
    assert track2.title == "Track 2"
    assert track2.isrc is None


@pytest.mark.asyncio
async def test_transform_deezer_minimal_data():
    """Test with minimal essential data (artist, title, tracks with title)."""
    raw_data = {
        "id": "dummy_minimal_id",
        "title": "Minimal Release",
        "artist": {"name": "Minimal Artist"},
        "tracks": {"data": [{"title_short": "Minimal Track 1"}]},
    }
    transformed = await _transform_deezer_cached_data(raw_data, country_code=None)
    assert transformed is not None
    assert transformed["artist"]["name"] == "Minimal Artist"
    assert transformed["release_title"] == "Minimal Release"
    assert transformed["release_date"] is None
    assert transformed["label"] is None
    assert transformed["tracks"] is not None
    assert transformed["genres"] == []
    assert transformed["album_type"] is None
    assert len(transformed["tracks"]) == 1
    track1 = Track(**transformed["tracks"][0])
    assert track1.title == "Minimal Track 1"
    assert track1.isrc is None


@pytest.mark.asyncio
async def test_transform_deezer_missing_artist_name():
    """Test when artist name is missing (should return None as it's essential)."""
    raw_data = {
        "title": "Artistless Album",
        "artist": {},  # Missing name
        "tracks": {"data": [{"title_short": "Track A"}]},
    }
    transformed = await _transform_deezer_cached_data(raw_data, country_code=None)
    assert transformed is None

    raw_data_no_artist_obj = {
        "title": "Artistless Album 2",
        # Missing artist object entirely
        "tracks": {"data": [{"title_short": "Track B"}]},
    }
    transformed2 = await _transform_deezer_cached_data(raw_data_no_artist_obj, country_code=None)
    assert transformed2 is None


@pytest.mark.asyncio
async def test_transform_deezer_missing_release_title():
    """Test when release title is missing (should return None as it's essential)."""
    raw_data = {
        # Missing title
        "artist": {"name": "Titleless Artist"},
        "tracks": {"data": [{"title_short": "Track C"}]},
    }
    transformed = await _transform_deezer_cached_data(raw_data, country_code=None)
    assert transformed is None


@pytest.mark.asyncio
async def test_transform_deezer_no_tracks():
    """Test when tracks.data is empty or missing."""
    # Case 1: tracks.data is empty
    raw_data_empty_tracks = {
        "id": "dummy_empty_tracks_id",
        "title": "No Tracks Release",
        "artist": {"name": "Trackless Wonder"},
        "tracks": {"data": []},
    }
    transformed = await _transform_deezer_cached_data(raw_data_empty_tracks, country_code=None)
    assert transformed is not None
    assert transformed["artist"]["name"] == "Trackless Wonder"
    assert transformed["release_title"] == "No Tracks Release"
    assert transformed["tracks"] == []

    # Case 2: tracks object is missing
    raw_data_no_tracks_obj = {
        "id": "dummy_no_tracks_obj_id",
        "title": "No Tracks At All",
        "artist": {"name": "The Silent Artist"},
        # Missing "tracks" key entirely
    }
    transformed2 = await _transform_deezer_cached_data(raw_data_no_tracks_obj, country_code=None)
    assert transformed2 is not None
    assert transformed2["artist"]["name"] == "The Silent Artist"
    assert transformed2["release_title"] == "No Tracks At All"
    assert transformed2["tracks"] == []

    # Case 3: tracks object is present but 'data' key is missing
    raw_data_tracks_no_data = {
        "id": "dummy_tracks_no_data_id",
        "title": "Tracks No Data",
        "artist": {"name": "Data Deficient"},
        "tracks": {},  # Missing "data" key
    }
    transformed3 = await _transform_deezer_cached_data(raw_data_tracks_no_data, country_code=None)
    assert transformed3 is not None
    assert transformed3["tracks"] == []


@pytest.mark.asyncio
async def test_transform_deezer_empty_input():
    """Test with an empty dictionary as input."""
    raw_data = {}
    transformed = await _transform_deezer_cached_data(raw_data, country_code=None)
    assert transformed is None  # Essential fields artist & title will be missing


@pytest.mark.asyncio
async def test_transform_deezer_malformed_genres():
    """Test with malformed genres (e.g., not in genres.data or wrong type)."""
    # Case 1: genres is a list of strings, not dicts
    raw_data_genres_list_str = {
        "id": "dummy_malformed_genre1_id",
        "title": "Malformed Genres Release",
        "artist": {"name": "Genre Benders"},
        "genres": ["Rock", "Pop"],  # Incorrect structure
        "tracks": {"data": [{"title_short": "Track X"}]},
    }
    transformed = await _transform_deezer_cached_data(raw_data_genres_list_str, country_code=None)
    assert transformed is not None  # Should still process, but genres will be empty
    assert transformed["genres"] == []

    # Case 2: genres.data contains items not dictionaries
    raw_data_genres_data_not_dict = {
        "id": "dummy_malformed_genre2_id",
        "title": "Malformed Genres Data",
        "artist": {"name": "Structure Breakers"},
        "genres": {"data": ["Metal", None, {}]},  # Items are not all dicts with "name"
        "tracks": {"data": [{"title_short": "Track Y"}]},
    }
    transformed2 = await _transform_deezer_cached_data(raw_data_genres_data_not_dict, country_code=None)
    assert transformed2 is not None
    assert transformed2["genres"] == []  # Expects dicts with "name"

    # Case 3: genres key exists but is not a dict (e.g., None or a list)
    raw_data_genres_not_dict = {
        "id": "dummy_malformed_genre3_id",
        "title": "Non Dict Genres",
        "artist": {"name": "Type Shifters"},
        "genres": None,
        "tracks": {"data": [{"title_short": "Track Z"}]},
    }
    transformed3 = await _transform_deezer_cached_data(raw_data_genres_not_dict, country_code=None)
    assert transformed3 is not None
    assert transformed3["genres"] == []


@pytest.mark.asyncio
async def test_transform_deezer_malformed_tracks():
    """Test with malformed tracks (e.g., not in tracks.data or wrong type)."""
    # Case 1: tracks is a list of strings, not dicts
    raw_data_tracks_list_str = {
        "id": "dummy_malformed_track1_id",
        "title": "Malformed Tracks Release",
        "artist": {"name": "Track Tamperers"},
        "tracks": ["Track A", "Track B"],  # Incorrect structure for tracks
    }
    transformed = await _transform_deezer_cached_data(raw_data_tracks_list_str, country_code=None)
    assert transformed is not None  # Should still process, but tracks will be empty
    assert transformed["tracks"] == []

    # Case 2: tracks.data contains items not dictionaries
    raw_data_tracks_data_not_dict = {
        "id": "dummy_malformed_track2_id",
        "title": "Malformed Tracks Data",
        "artist": {"name": "Format Fumblers"},
        "tracks": {"data": ["Song1", None, {}]},  # Items not all dicts with "title_short"
    }
    transformed2 = await _transform_deezer_cached_data(raw_data_tracks_data_not_dict, country_code=None)
    assert transformed2 is not None
    assert transformed2["tracks"] == []

    # Case 3: Track item is dict but missing title_short/title
    raw_data_track_no_title = {
        "id": "dummy_malformed_track3_id",
        "title": "Track No Title",
        "artist": {"name": "Nameless Notes"},
        "tracks": {"data": [{"isrc": "123"}]},  # No title_short or title
    }
    transformed3 = await _transform_deezer_cached_data(raw_data_track_no_title, country_code=None)
    assert transformed3 is not None
    assert len(transformed3["tracks"]) == 1
    # It should use "Unknown Track" if title is missing
    assert Track(**transformed3["tracks"][0]).title == "Unknown Track"


@pytest.mark.asyncio
async def test_transform_deezer_country_code_no_effect():
    """Test that country_code currently has no effect on the transformation logic itself."""
    raw_data = {
        "id": "dummy_country_code_id",
        "title": "International Album",
        "artist": {"name": "Global Artist"},
        "release_date": "2024-01-01",
        "tracks": {"data": [{"title_short": "Global Hit"}]},
    }
    transformed_us = await _transform_deezer_cached_data(raw_data, country_code="US")
    transformed_gb = await _transform_deezer_cached_data(raw_data, country_code="GB")
    transformed_none = await _transform_deezer_cached_data(raw_data, country_code=None)

    assert transformed_us is not None
    assert transformed_gb is not None
    assert transformed_none is not None
    # Expect all transformations to be identical as country_code is not used by the function
    assert transformed_us == transformed_gb == transformed_none


# --- Tests for check_existing_result --- #


@pytest.mark.asyncio
async def test_check_existing_deezer_full_match(mocker):
    """Test check_existing_result with a full match from Deezer cache."""
    mocker.patch(
        "grimwaves_api.modules.music.helpers.SOURCES_TO_PRECHECK",
        ["deezer"],
    )
    mock_get_search = mocker.patch(
        "grimwaves_api.modules.music.cache.cache.get_search_results",
        return_value=[SAMPLE_DEEZER_SEARCH_RESULT_ITEM],
    )
    mock_get_details = mocker.patch(
        "grimwaves_api.modules.music.cache.cache.get_release_details",
        return_value=SAMPLE_DEEZER_RELEASE_DETAILS,
    )

    found, result = await check_existing_result("Deezer Artist", "Deezer Album", "US")

    assert found is True
    assert result is not None
    assert result["source"] == "deezer"
    assert result["data"]["artist"]["name"] == "Deezer Artist"
    assert result["data"]["release_title"] == "Deezer Album"
    assert len(result["data"]["tracks"]) == 1
    assert Track(**result["data"]["tracks"][0]).title == "Deezer Track 1"

    mock_get_search.assert_awaited_once_with(
        "deezer",
        "Deezer Artist",
        "Deezer Album",
        "US",
    )
    mock_get_details.assert_awaited_once_with(
        source="deezer",
        release_id="dz123",
    )


@pytest.mark.asyncio
async def test_check_existing_deezer_search_hit_no_details(mocker):
    """Test check_existing_result with Deezer search hit but no details in cache."""
    mocker.patch(
        "grimwaves_api.modules.music.helpers.SOURCES_TO_PRECHECK",
        ["deezer"],
    )
    mocker.patch(
        "grimwaves_api.modules.music.cache.cache.get_search_results",
        return_value=[SAMPLE_DEEZER_SEARCH_RESULT_ITEM],
    )
    mocker.patch(
        "grimwaves_api.modules.music.cache.cache.get_release_details",
        return_value=None,  # No details
    )

    found, result = await check_existing_result("Deezer Artist", "Deezer Album", "US")

    assert found is False
    assert result is None


@pytest.mark.asyncio
async def test_check_existing_deezer_no_search_results(mocker):
    """Test check_existing_result with no Deezer search results in cache."""
    mocker.patch(
        "grimwaves_api.modules.music.helpers.SOURCES_TO_PRECHECK",
        ["deezer"],
    )
    mock_get_search = mocker.patch(
        "grimwaves_api.modules.music.cache.cache.get_search_results",
        return_value=None,  # No search results
    )
    mock_get_details = mocker.patch("grimwaves_api.modules.music.cache.cache.get_release_details")

    found, result = await check_existing_result("Deezer Artist", "Deezer Album", "US")

    assert found is False
    assert result is None
    mock_get_search.assert_awaited_once()
    mock_get_details.assert_not_awaited()  # Should not be called if no search results


@pytest.mark.asyncio
async def test_check_existing_deezer_details_transform_fails(mocker):
    """Test when Deezer details are found but transformation fails (e.g. missing essential fields)."""
    mocker.patch(
        "grimwaves_api.modules.music.helpers.SOURCES_TO_PRECHECK",
        ["deezer"],
    )
    mocker.patch(
        "grimwaves_api.modules.music.cache.cache.get_search_results",
        return_value=[SAMPLE_DEEZER_SEARCH_RESULT_ITEM],
    )
    # Data that will cause _transform_deezer_cached_data to return None
    malformed_details = {"id": "dz123", "title": "Deezer Album"}  # Missing artist
    mocker.patch(
        "grimwaves_api.modules.music.cache.cache.get_release_details",
        return_value=malformed_details,
    )

    found, result = await check_existing_result("Any Artist", "Deezer Album", "US")

    assert found is False
    assert result is None


@pytest.mark.asyncio
async def test_check_existing_deezer_search_item_missing_id(mocker):
    """Test when a Deezer search item is missing its 'id' field."""
    mocker.patch(
        "grimwaves_api.modules.music.helpers.SOURCES_TO_PRECHECK",
        ["deezer"],
    )
    search_results_missing_id = [{"title": "Album With No ID"}]  # No 'id' field
    mocker.patch(
        "grimwaves_api.modules.music.cache.cache.get_search_results",
        return_value=search_results_missing_id,
    )
    mock_get_details = mocker.patch("grimwaves_api.modules.music.cache.cache.get_release_details")

    found, result = await check_existing_result("Some Artist", "Album With No ID", "US")

    assert found is False
    assert result is None
    mock_get_details.assert_not_awaited()  # Should not attempt to get details if ID is missing


@pytest.mark.asyncio
async def test_check_existing_result_spotify_first_then_deezer_no_call(mocker):
    """Test when Spotify provides data first, Deezer should not be called."""
    mocker.patch(
        "grimwaves_api.modules.music.helpers.SOURCES_TO_PRECHECK",
        ["spotify", "deezer"],  # Spotify is first
    )
    # Используем AsyncMock для моков кеша, так как оригинальные функции асинхронные
    mock_get_search = mocker.patch(
        "grimwaves_api.modules.music.cache.cache.get_search_results",
        new_callable=AsyncMock,
    )
    mock_get_details = mocker.patch(
        "grimwaves_api.modules.music.cache.cache.get_release_details",
        new_callable=AsyncMock,
    )

    # Configure side effects for cache calls
    async def get_search_results_side_effect(*args, **kwargs):
        # source is args[0], band_name is args[1], release_name is args[2], country_code is args[3]
        if args and args[0] == "spotify":
            return [SAMPLE_SPOTIFY_SEARCH_RESULT_ITEM]
        return []

    async def get_release_details_side_effect(*args, **kwargs):
        # source is kwargs['source'], release_id is kwargs['release_id'] (potentially country_code in kwargs too)
        if kwargs.get("source") == "spotify" and kwargs.get("release_id") == "sp456":
            return SAMPLE_SPOTIFY_RELEASE_DETAILS
        return None

    mock_get_search.side_effect = get_search_results_side_effect
    mock_get_details.side_effect = get_release_details_side_effect

    found, result = await check_existing_result("Spotify Artist", "Spotify Album", "US")

    assert found is True
    assert result is not None
    assert result["source"] == "spotify"
    assert result["data"]["artist"]["name"] == "Spotify Artist"

    # Check that get_search_results was called for Spotify but NOT for Deezer
    # mock_get_search.assert_any_call(source="spotify", band_name="Spotify Artist", release_name="Spotify Album", country_code="US")

    # Проверяем, что mock_get_search вызывался с source='spotify'
    # и НЕ вызывался с source='deezer'
    spotify_called = False
    deezer_called = False
    for mock_call in mock_get_search.call_args_list:
        # Source is the first positional argument (args[0])
        if mock_call.args and mock_call.args[0] == "spotify":
            spotify_called = True
        if mock_call.args and mock_call.args[0] == "deezer":
            deezer_called = True

    assert spotify_called is True
    assert deezer_called is False

    # Аналогично для mock_get_details
    # mock_get_details.assert_any_call(source="spotify", release_id="sp456", country_code="US")
    spotify_details_called = False
    deezer_details_called = False
    for mock_call in mock_get_details.call_args_list:
        if mock_call.kwargs.get("source") == "spotify":
            spotify_details_called = True
        if mock_call.kwargs.get("source") == "deezer":
            deezer_details_called = True

    assert spotify_details_called is True
    assert deezer_details_called is False

    # Проверяем аргументы первого вызова (Spotify)
    call_args_spotify = mock_get_search.call_args_list[0]
    assert call_args_spotify.args[0] == "spotify"

    assert mock_get_details.call_count == 1  # Only called for Deezer as Spotify had no search hit


@pytest.mark.asyncio
async def test_check_existing_result_no_spotify_deezer_provides_data(mocker):
    """Test when Spotify has no data, Deezer provides the result."""
    mocker.patch(
        "grimwaves_api.modules.music.helpers.SOURCES_TO_PRECHECK",
        ["spotify", "deezer"],
    )
    mock_get_search = mocker.patch(
        "grimwaves_api.modules.music.cache.cache.get_search_results",
        new_callable=AsyncMock,
    )
    mock_get_details = mocker.patch(
        "grimwaves_api.modules.music.cache.cache.get_release_details",
        new_callable=AsyncMock,
    )

    async def get_search_results_side_effect(*args, **kwargs):
        # source is args[0], band_name is args[1], release_name is args[2], country_code is args[3]
        if args and args[0] == "deezer":
            return [SAMPLE_DEEZER_SEARCH_RESULT_ITEM]
        return []  # Spotify returns no search results

    async def get_release_details_side_effect(*args, **kwargs):
        # source is kwargs['source'], release_id is kwargs['release_id']
        if kwargs.get("source") == "deezer" and kwargs.get("release_id") == "dz123":
            return SAMPLE_DEEZER_RELEASE_DETAILS
        return None

    mock_get_search.side_effect = get_search_results_side_effect
    mock_get_details.side_effect = get_release_details_side_effect

    found, result = await check_existing_result("Deezer Artist", "Deezer Album", "US")

    assert found is True
    assert result is not None
    assert result["source"] == "deezer"
    assert result["data"]["artist"]["name"] == "Deezer Artist"

    # Verify calls for both Spotify (no results) and Deezer (results)
    assert mock_get_search.call_count == 2  # Called for spotify then deezer

    # Проверяем аргументы первого вызова (Spotify)
    call_args_spotify = mock_get_search.call_args_list[0]
    assert call_args_spotify.args[0] == "spotify"

    # Проверяем аргументы второго вызова (Deezer)
    call_args_deezer = mock_get_search.call_args_list[1]
    assert call_args_deezer.args[0] == "deezer"

    assert mock_get_details.call_count == 1  # Only called for Deezer as Spotify had no search hit
    call_args_details_deezer = mock_get_details.call_args_list[0]
    assert call_args_details_deezer.kwargs.get("source") == "deezer"
    assert call_args_details_deezer.kwargs.get("release_id") == "dz123"

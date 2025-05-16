from typing import Any

"""Mock data for MusicBrainz API responses and transformed data."""

# This data should represent the output of _transform_musicbrainz_cached_data
# in helpers.py, which is based on the full release details from MusicBrainz API
# (after a call to musicbrainz_client.get_release with relevant 'inc' parameters).

mock_prefetched_musicbrainz_release_id = "mbid-release-from-prefetched-data"
mock_prefetched_musicbrainz_artist_id = "mbid-artist-from-prefetched-data"
mock_prefetched_musicbrainz_recording_id = "mbid-recording-from-prefetched-data"

# This represents the 'data' field within prefetched_data_list for MusicBrainz
# It should be structured like a MusicbrainzReleaseSummary if possible,
# or at least contain all necessary fields that _combine_metadata_from_sources
# would try to extract from it.
mock_transformed_musicbrainz_data_complete: dict[str, Any] = {
    "id": mock_prefetched_musicbrainz_release_id,
    "title": "Prefetched MB Album Title",
    "artist-credit": [
        {
            "artist": {
                "id": mock_prefetched_musicbrainz_artist_id,
                "name": "Prefetched MB Artist Name",
                "sort-name": "Artist Name, Prefetched MB",
            },
            "name": "Prefetched MB Artist Name",  # Sometimes the 'name' is at this level too
            "joinphrase": "",
        },
    ],
    "date": "2023-03-03",
    "country": "XW",  # Fictional country for world-wide
    "release-events": [{"date": "2023-03-03", "area": {"iso-3166-1-codes": ["XW"]}}],
    "label-info": [
        {
            "label": {
                "id": "mbid-label-prefetched",
                "name": "Prefetched MB Label",
            },
        },
    ],
    "track-count": 2,  # from media.track-count summary
    "media": [
        {
            "format": "CD",
            "disc-count": 1,
            "track-count": 2,
            "tracks": [
                {
                    "id": "mbid-track1-prefetched",
                    "number": "1",
                    "title": "Prefetched MB Track 1",
                    "length": 180000,  # ms
                    "recording": {
                        "id": mock_prefetched_musicbrainz_recording_id + "-01",
                        "title": "Prefetched MB Track 1",
                        "isrcs": ["MBISRC001"],
                        "length": 180000,
                    },
                },
                {
                    "id": "mbid-track2-prefetched",
                    "number": "2",
                    "title": "Prefetched MB Track 2",
                    "length": 240000,  # ms
                    "recording": {
                        "id": mock_prefetched_musicbrainz_recording_id + "-02",
                        "title": "Prefetched MB Track 2",
                        "isrcs": ["MBISRC002"],
                        "length": 240000,
                    },
                },
            ],
        },
    ],
    "release-group": {  # For genres primarily
        "id": "mbid-rg-prefetched",
        "primary-type": "Album",
        "genres": [  # Older style, sometimes present
            {"name": "Prefetched Rock", "count": 5},
        ],
    },
    "genres": [  # More common for full release objects if 'inc=genres'
        {"name": "Prefetched Rock", "count": 10, "id": "genre-id-rock"},
        {"name": "Prefetched Experimental", "count": 5, "id": "genre-id-exp"},
    ],
    "tags": [  # For additional genre/style info
        {"name": "Progressive Prefetched", "count": 3},
        {"name": "Prefetched Rock", "count": 7},  # Duplicate with genre, good for testing deduplication
    ],
    # Add other fields if _transform_musicbrainz_cached_data extracts them
    # and _combine_metadata_from_sources uses them.
    # For example, if social links were part of the release object (they usually are not)
}

# A mock for when MusicBrainz returns a less complete search result
# (simulating output of _find_best_musicbrainz_release if it found something basic)
mock_musicbrainz_search_result_basic = {
    "id": "mbid-search-basic",
    "title": "MB Search Result Album",
    "artist-credit": [{"artist": {"name": "MB Search Artist"}}],
    "release-group": {"primary-type": "Album"},
    # Missing date, label, full tracks, detailed genres etc.
}


# Convert this from a dict to a function
def mock_raw_musicbrainz_api_release_details(
    release_id: str = "default_mb_release_id",
    title: str = "Default MB Title",
    artist_name: str = "Default MB Artist",
    artist_id: str = "default_artist_id",
    date: str = "2023-01-01",
    country: str = "XW",
    label: str | None = "Default MB Label",  # Label can be optional
    barcode: str | None = None,
    asin: str | None = None,
    release_group_id: str = "default_rg_id",
    primary_type: str = "Album",
    genres: list[str] | None = None,
    tags: list[str] | None = None,
    track_count: int = 1,
    status: str | None = "Official",
    disambiguation: str | None = None,
    packaging: str | None = None,
    quality: str | None = "normal",
) -> dict[str, Any]:
    """Generates a mock raw MusicBrainz API release details response."""
    data: dict[str, Any] = {
        "id": release_id,
        "title": title,
        "status": status,
        "disambiguation": disambiguation or "",
        "packaging": packaging,
        "quality": quality,
        "text-representation": {"language": "eng", "script": "Latn"},
        "artist-credit": [
            {
                "artist": {
                    "id": artist_id,
                    "name": artist_name,
                    "sort-name": artist_name,
                    "disambiguation": "artist_disambiguation",
                },
                "joinphrase": "",
            },
        ],
        "date": date,
        "country": country,
        "release-events": [{"date": date, "area": {"iso-3166-1-codes": [country]}}],
        "label-info": [],
        "track-count": track_count,  # This is total track count for all media
        "media": [],
        "release-group": {
            "id": release_group_id,
            "primary-type": primary_type,
            # If service expects genres here, they should be added:
            # "genres":  [{"name": g, "count": 1} for g in (YOUR_RG_GENRES_HERE or [])],
        },
        "barcode": barcode,
        "asin": asin,
        # Top-level genres and tags as service expects them now for raw data from get_release
        "genres": (
            [{"name": g, "count": 1, "id": f"genre-id-{g.lower().replace(' ', '-')}"} for g in genres] if genres else []
        ),
        "tags": ([{"name": t, "count": 1} for t in tags] if tags else []),
    }

    if label:
        data["label-info"].append(
            {
                "label": {"id": "label-id-placeholder", "name": label},
                "catalog-number": "CAT123",
            },
        )

    # Calculate tracks per medium if multiple media are needed, or put all on one.
    # For simplicity, one medium with all tracks.
    current_media_tracks = []
    for i in range(track_count):
        current_media_tracks.append(
            {
                "id": f"track-id-{release_id}-{i}",
                "number": str(i + 1),
                "title": f"MB Track Title {i + 1} for {release_id}",
                "length": 180000 + (i * 1000),  # ms
                "recording": {
                    "id": f"recording-id-{release_id}-{i}",
                    "title": f"MB Recording Title {i + 1} for {release_id}",
                    "length": 180000 + (i * 1000),
                    "isrcs": [f"MBISRC{i + 1:03}-{release_id[-3:]}"] if i % 2 == 0 else [],
                    "first-release-date": date,
                },
            },
        )

    data["media"].append(
        {
            "format": "CD",
            "disc-count": 1,
            "track-count": track_count,
            "tracks": current_media_tracks,
        },
    )

    return data


# Existing mock_transformed_musicbrainz_data_complete for prefetched data
# Ensure its structure is what `_transform_musicbrainz_cached_data` would produce

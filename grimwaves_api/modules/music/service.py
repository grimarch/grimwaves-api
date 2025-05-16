"""Service layer for music metadata module."""

import asyncio
import json
from contextlib import AsyncExitStack
from typing import Any, Self, TypeAlias

from grimwaves_api.core.logger import get_logger
from grimwaves_api.modules.music.cache import cache
from grimwaves_api.modules.music.clients import DeezerClient, MusicBrainzClient, SpotifyClient
from grimwaves_api.modules.music.helpers import _transform_deezer_cached_data
from grimwaves_api.modules.music.schemas import SocialLinks, Track
from grimwaves_api.modules.music.utils import normalize_text

# Initialize module logger
logger = get_logger("modules.music.service")

# Type aliases
ReleaseData: TypeAlias = dict[str, Any]

DEFAULT_MUSICBRAINZ_INC_PARAMS = [
    "recordings",  # for tracks, track lengths, ISRCs
    "artists",  # for artist details
    "artist-credits",  # for artist names and join phrases
    "labels",  # for label information, catalog numbers
    "release-groups",  # for primary type, release group genres
    "genres",  # for release-level genres
    "tags",  # for additional tags/genres
    "media",  # for format, tracklist structure
    # "url-rels", # if you need URLs related to the release (buy links, etc.)
    # "artist-rels", # if you need relationships of artists involved
]


class MusicMetadataService:
    """Service for retrieving and processing music metadata."""

    def __init__(
        self,
        spotify_client: SpotifyClient,
        deezer_client: DeezerClient,
        musicbrainz_client: MusicBrainzClient,
    ) -> None:
        """Initialize the service with API clients.

        Args:
            spotify_client: Spotify API client
            deezer_client: Deezer API client
            musicbrainz_client: MusicBrainz API client
        """
        self._spotify = spotify_client
        self._deezer = deezer_client
        self._musicbrainz = musicbrainz_client
        self._error_stats = {
            "spotify": {"errors": 0, "total": 0},
            "deezer": {"errors": 0, "total": 0},
            "musicbrainz": {"errors": 0, "total": 0},
        }
        self._exit_stack: AsyncExitStack | None = None

    async def __aenter__(self) -> Self:
        """Enter the async context manager.

        This method initializes the AsyncExitStack and enters contexts
        for all API clients to ensure proper resource management.

        Returns:
            Self reference for chaining
        """
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        # Enter context for all clients
        await self._exit_stack.enter_async_context(self._spotify)
        await self._exit_stack.enter_async_context(self._deezer)
        await self._exit_stack.enter_async_context(self._musicbrainz)

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the async context manager.

        This method ensures all resources are properly released even if
        an exception occurred. It uses the AsyncExitStack to manage
        the exit sequence of all contained context managers.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised
        """
        if self._exit_stack:
            await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
            self._exit_stack = None
        else:
            # Fallback to close() if not using context manager
            await self.close()

    def _update_error_stats(self, source: str, success: bool) -> None:
        """Update error statistics for a source.

        Args:
            source: Name of the source (spotify, deezer, musicbrainz)
            success: Whether the operation was successful
        """
        if source in self._error_stats:
            self._error_stats[source]["total"] += 1
            if not success:
                self._error_stats[source]["errors"] += 1

    def get_error_stats(self) -> dict[str, dict[str, int]]:
        """Get error statistics for all sources.

        Returns:
            Dictionary with error statistics per source
        """
        return self._error_stats

    async def _get_spotify_tracks(
        self,
        album_id: str,
        market: str | None = None,
    ) -> tuple[list[Track], bool]:
        """Get tracks from Spotify with error handling.

        Args:
            album_id: Spotify album ID
            market: Optional market code for filtering

        Returns:
            Tuple of (tracks list, success flag)
        """
        try:
            tracks_data: list[dict[str, Any]] = await self._spotify.get_tracks_with_isrc(album_id, market)
            logger.debug("Spotify tracks raw data: %s", json.dumps(tracks_data, indent=2))

            # Transform list[dict] to list[Track]
            transformed_tracks: list[Track] = []
            for i, track_dict in enumerate(tracks_data):
                # Assuming _transform_spotify_track expects position; Spotify API might provide track_number
                position = track_dict.get("track_number", i + 1)
                track_model = await self._transform_spotify_track(track_dict, position)
                transformed_tracks.append(track_model)

            self._update_error_stats("spotify", True)
            return transformed_tracks, True
        except Exception as e:
            logger.error(
                "Failed to get tracks from Spotify for album %s: %s",
                album_id,
                str(e),
                exc_info=True,
            )
            self._update_error_stats("spotify", False)
            return [], False

    async def _get_deezer_tracks(
        self,
        album_id: str,
    ) -> tuple[list[Track], bool]:
        """Get tracks from Deezer with error handling.

        Args:
            album_id: Deezer album ID

        Returns:
            Tuple of (tracks list, success flag)
        """
        try:
            logger.debug("DEBUG: Calling Deezer get_album_tracks with album_id: %s", album_id)
            tracks_data: list[dict[str, Any]] = await self._deezer.get_album_tracks(album_id)
            logger.debug("DEBUG: Deezer get_album_tracks raw data: %s", json.dumps(tracks_data, indent=4))

            # Transform list[dict] to list[Track]
            transformed_tracks: list[Track] = []
            for track_dict in tracks_data:
                # Deezer API provides 'track_position' and 'disk_number'
                # We'll use 'track_position' for now, assuming single disk or simple sequence.
                # If multiple disks, a more complex position calculation might be needed.
                position = track_dict.get("track_position", 0)  # Default to 0 if not present
                track_model = await self._transform_deezer_track(track_dict, position)
                transformed_tracks.append(track_model)

            self._update_error_stats("deezer", True)
            return transformed_tracks, True
        except Exception as e:
            logger.error(
                "Failed to get tracks from Deezer for album %s: %s",
                album_id,
                str(e),
                exc_info=True,
            )
            self._update_error_stats("deezer", False)
            return [], False

    async def _get_musicbrainz_data(
        self,
        isrc: str,
    ) -> tuple[dict[str, Any], bool]:
        """Get track data from MusicBrainz with error handling.

        Args:
            isrc: ISRC code

        Returns:
            Tuple of (track data, success flag)
        """
        try:
            logger.debug(f"DEBUG: Calling MusicBrainz get_track_by_isrc with isrc: {isrc}")
            data: dict[str, Any] = await self._musicbrainz.get_track_by_isrc(isrc)
            logger.debug(f"DEBUG: MusicBrainz get_track_by_isrc result: {json.dumps(data, indent=4)}")
            self._update_error_stats("musicbrainz", True)
            return data, True
        except Exception as e:
            logger.error(
                "Failed to get data from MusicBrainz for ISRC %s: %s",
                isrc,
                str(e),
                exc_info=True,
            )
            self._update_error_stats("musicbrainz", False)
            return {}, False

    def _is_musicbrainz_data_sufficiently_complete(self, data: dict[str, Any] | None) -> bool:
        """Checks if the provided MusicBrainz data dictionary appears to be
        sufficiently complete (i.e., not just a basic search summary).
        """
        if not data:
            return False
        # Full MusicBrainz data typically includes 'media' (for tracks) and 'label-info'.
        # Search summaries usually lack these.
        # 'track-count' might be present in summaries but 'media' is more definitive for full tracks.
        has_media = "media" in data and isinstance(data["media"], list) and bool(data["media"])
        # Check for label-info, but allow it to be an empty list for releases without labels.
        has_labels = "label-info" in data and isinstance(data["label-info"], list)
        has_release_group = "release-group" in data and isinstance(data["release-group"], dict)

        # Consider data complete if it has media information (implies tracks) and release group info.
        # The presence of 'label-info' key (even if list is empty) also suggests a more complete object.
        return has_media and has_release_group and has_labels

    async def _transform_spotify_track(self, track_data: dict[str, Any], position: int) -> Track:
        """Transform Spotify track data into Track model.

        Args:
            track_data: Spotify track data
            position: Track position in album

        Returns:
            Track model instance
        """
        # Extract ISRC if available
        isrc = None
        external_ids = track_data.get("external_ids", {})
        if external_ids and "isrc" in external_ids:
            isrc = external_ids["isrc"]
            logger.debug("Found ISRC %s for track %s", isrc, track_data.get("name"))
        else:
            logger.debug(
                "No ISRC found for track %s. external_ids: %s",
                track_data.get("name"),
                json.dumps(external_ids),
            )

        # Extract Spotify ID
        spotify_id = track_data.get("id")

        # Create source-specific IDs dictionary if Spotify ID is available
        source_specific_ids = None
        if spotify_id:
            source_specific_ids = {"spotify_track_id": spotify_id}

        return Track(
            title=track_data.get("name", "Unknown Track"),
            isrc=isrc,
            position=position,
            duration_ms=track_data.get("duration_ms"),
            source_specific_ids=source_specific_ids,
            additional_details_track=None,  # Could be populated with additional Spotify details if needed
        )

    async def _transform_deezer_track(self, track_data: dict[str, Any], position: int) -> Track:
        """Transform Deezer track data into Track model.

        Args:
            track_data: Deezer track data
            position: Track position in album

        Returns:
            Track model instance
        """
        # Extract ISRC if available
        isrc = track_data.get("isrc")
        if isrc:
            logger.debug("Found ISRC %s for Deezer track %s", isrc, track_data.get("title"))
        else:
            logger.debug(
                "No ISRC found for Deezer track %s.",
                track_data.get("title"),
            )

        # Extract Deezer ID
        deezer_id = track_data.get("id")

        # Create source-specific IDs dictionary if Deezer ID is available
        source_specific_ids = None
        if deezer_id:
            source_specific_ids = {"deezer_track_id": str(deezer_id)}  # Ensure it's a string

        # Duration in Deezer is in seconds, convert to milliseconds
        duration_ms = None
        duration_seconds = track_data.get("duration")
        if duration_seconds is not None:
            try:
                duration_ms = int(duration_seconds) * 1000
            except ValueError:
                logger.warning("Could not convert Deezer duration '%s' to int.", duration_seconds)

        return Track(
            title=track_data.get(
                "title_short",
                track_data.get("title", "Unknown Track"),
            ),  # Prefer short title if available
            isrc=isrc,
            position=position,
            duration_ms=duration_ms,
            source_specific_ids=source_specific_ids,
            additional_details_track=None,  # Could be populated with additional Deezer details
        )

    async def _combine_metadata_from_sources(
        self,
        band_name: str,
        release_name: str,
        spotify_release_summary: dict[str, Any] | None,
        musicbrainz_release_summary: dict[str, Any] | None,
        mb_artist_id: str | None,  # MusicBrainz Artist ID
        artist_social_links: SocialLinks,
        artist_mb_genres: list[str],  # Genres from MB artist, broader than release
        deezer_data: dict[str, Any] | None,  # Transformed Deezer data
        is_spotify_data_prefetched: bool,
        is_mb_data_prefetched: bool,
        country_code: str | None = None,
    ) -> dict[str, Any]:
        """Combines metadata from Spotify, MusicBrainz, and Deezer sources.

        Prioritizes Spotify for track list if available.
        Prioritizes MusicBrainz for release date and label if available.
        Uses all sources to build a comprehensive list of genres.
        Social links are primarily from MusicBrainz artist data.
        Deezer can supplement missing information.
        """
        logger.info(
            "Combining metadata for '%s' - '%s'. Spotify: %s, MB: %s, Deezer: %s, MB Artist ID: %s",
            band_name,
            release_name,
            spotify_release_summary is not None,
            musicbrainz_release_summary is not None,
            deezer_data is not None,
            mb_artist_id,
        )
        # --- BEGIN DETAILED INPUT LOGGING ---
        logger.debug(
            "[COMBINE_INPUTS] band_name: %s, release_name: %s, country_code: %s",
            band_name,
            release_name,
            country_code,
        )
        logger.debug(
            "[COMBINE_INPUTS] Spotify Data (is_prefetched: %s): %s",
            is_spotify_data_prefetched,
            json.dumps(spotify_release_summary, indent=2, ensure_ascii=False) if spotify_release_summary else "None",
        )
        logger.debug(
            "[COMBINE_INPUTS] MusicBrainz Data (is_prefetched: %s, artist_id_arg: %s): %s",
            is_mb_data_prefetched,
            mb_artist_id,
            json.dumps(musicbrainz_release_summary, indent=2, ensure_ascii=False)
            if musicbrainz_release_summary
            else "None",
        )
        logger.debug(
            "[COMBINE_INPUTS] MusicBrainz Artist Genres (from artist_id_arg): %s",
            artist_mb_genres,
        )
        logger.debug(
            "[COMBINE_INPUTS] Deezer Data: %s",
            json.dumps(deezer_data, indent=2, ensure_ascii=False) if deezer_data else "None",
        )
        logger.debug(
            "[COMBINE_INPUTS] Artist Social Links (from artist_id_arg): %s",
            artist_social_links.model_dump(exclude_none=True),
        )
        # --- END DETAILED INPUT LOGGING ---

        # --- BEGIN ADDED DEBUG LOGGING ---
        logger.debug(
            "[COMBINE_PROBE_SOCIAL_LINKS_MODEL] Instance: %s, Website: %s, Facebook: %s, Twitter: %s, Instagram: %s, YouTube: %s, VK: %s",
            type(artist_social_links),
            getattr(artist_social_links, "website", "ATTR_MISSING"),
            getattr(artist_social_links, "facebook", "ATTR_MISSING"),
            getattr(artist_social_links, "twitter", "ATTR_MISSING"),
            getattr(artist_social_links, "instagram", "ATTR_MISSING"),
            getattr(artist_social_links, "youtube", "ATTR_MISSING"),
            getattr(artist_social_links, "vk", "ATTR_MISSING"),
        )
        logger.debug(
            "[COMBINE_PROBE_SOCIAL_LINKS_MODEL_DUMP_NO_EXCLUDE] Dump (no exclude_none): %s",
            artist_social_links.model_dump(),
        )
        # --- END ADDED DEBUG LOGGING ---

        final_metadata: dict[str, Any] = {
            "artist": band_name,
            "release": release_name,
            "release_date": None,
            "label": None,
            "genre": [],
            "tracks": [],
            "album_cover_url": None,
            "social_links": artist_social_links.model_dump(exclude_none=True),
            "source_spotify_id": None,
            "source_musicbrainz_id": None,
            "source_deezer_id": None,
        }

        # --- Populate from Spotify (Primary for some fields) ---
        if spotify_release_summary:
            logger.debug("Processing Spotify data for combination: ID %s", spotify_release_summary.get("id"))
            final_metadata["artist"] = spotify_release_summary.get("artist") or final_metadata["artist"]
            final_metadata["release"] = spotify_release_summary.get("name") or final_metadata["release"]
            if not final_metadata["release_date"]:
                final_metadata["release_date"] = spotify_release_summary.get("release_date")
            if not final_metadata["label"]:
                final_metadata["label"] = spotify_release_summary.get("label")

            spotify_genres_list = spotify_release_summary.get("genres")
            if spotify_genres_list:
                logger.debug(
                    "DEBUG_COMBINE: Spotify genres found: %s. Current final_metadata_genres: %s",
                    spotify_genres_list,
                    final_metadata["genre"],
                )
                final_metadata["genre"] = list(set(final_metadata["genre"] + spotify_genres_list))
                logger.debug(
                    "DEBUG_COMBINE: After adding Spotify genres, final_metadata_genres: %s",
                    final_metadata["genre"],
                )
            else:
                logger.debug(
                    "DEBUG_COMBINE: No genres found in spotify_release_summary or it's empty. Key 'genres' value: %s",
                    spotify_genres_list,
                )

            # Extract and transform Spotify tracks (if available)
            if (
                spotify_release_summary
                and "tracks" in spotify_release_summary
                and "items" in spotify_release_summary["tracks"]
                and spotify_release_summary["tracks"]["items"]
            ):
                logger.debug(
                    "Using tracks from Spotify (extracted and transformed from 'tracks.items'). Count: %s",
                    len(spotify_release_summary["tracks"]["items"]),
                )
                # Initialize tracks list
                all_tracks = []

                # Transform each track asynchronously (because the method is now async)
                for i, track in enumerate(spotify_release_summary["tracks"]["items"]):
                    # Get correct position (spotify track_number or positional index + 1)
                    position = track.get("track_number", i + 1)
                    track_obj = await self._transform_spotify_track(track, position)
                    all_tracks.append(track_obj)

                # Assign to final_metadata['tracks']
                final_metadata["tracks"] = all_tracks
            else:
                logger.debug("No tracks found in Spotify data or tracks data is missing")
                final_metadata["tracks"] = []

            # Spotify usually has good quality cover art.
            # The transformed data from Spotify should have `album_cover_url`.
            if spotify_release_summary.get("album_cover_url"):
                final_metadata["album_cover_url"] = spotify_release_summary["album_cover_url"]
            final_metadata["source_spotify_id"] = spotify_release_summary.get("id")

        # --- Populate/Refine from MusicBrainz (Primary for some fields) ---
        if musicbrainz_release_summary:
            logger.debug("Processing MusicBrainz data for combination: ID %s", musicbrainz_release_summary.get("id"))

            # Extract artist name from MusicBrainz artist-credit
            mb_artist_name_extracted = None
            artist_credit_list = musicbrainz_release_summary.get("artist-credit", [])
            if artist_credit_list and isinstance(artist_credit_list, list):
                first_artist_credit = artist_credit_list[0]
                if isinstance(first_artist_credit, dict):
                    artist_info = first_artist_credit.get("artist")
                    if isinstance(artist_info, dict):
                        mb_artist_name_extracted = artist_info.get("name")

            if mb_artist_name_extracted and (
                not final_metadata.get("artist") or final_metadata.get("artist") == band_name
            ):
                final_metadata["artist"] = {
                    "name": mb_artist_name_extracted,
                }  # Store as dict consistent with transformers
                logger.debug(
                    "[COMBINE_MB_ARTIST] Set artist from MusicBrainz: %s",
                    final_metadata["artist"],
                )
            # Original logic for artist (can be removed or commented out if the above is sufficient)
            # if (
            #     not final_metadata.get("artist") or final_metadata["artist"] == band_name
            # ):  # If Spotify didn't set a good one
            #     final_metadata["artist"] = musicbrainz_release_summary.get("artist") or final_metadata["artist"]

            if not final_metadata.get("release") or final_metadata["release"] == release_name:
                final_metadata["release"] = musicbrainz_release_summary.get("title") or final_metadata["release"]

            mb_release_date = musicbrainz_release_summary.get("date")
            if mb_release_date and (len(mb_release_date) >= 10 or not final_metadata["release_date"]):
                final_metadata["release_date"] = mb_release_date

            mb_label_info_list = musicbrainz_release_summary.get("label-info", [])
            if isinstance(mb_label_info_list, list) and mb_label_info_list:
                first_label_info = mb_label_info_list[0]
                if isinstance(first_label_info, dict) and isinstance(first_label_info.get("label"), dict):
                    mb_label_name = first_label_info.get("label", {}).get("name")
                    if mb_label_name:  # MusicBrainz label is often more canonical
                        final_metadata["label"] = mb_label_name
            elif not final_metadata[
                "label"
            ]:  # Fallback if no label-info but we might have a simpler 'label' field (less likely for raw MB)
                simple_mb_label = musicbrainz_release_summary.get("label")
                if simple_mb_label:
                    final_metadata["label"] = simple_mb_label

            # Corrected genre extraction from MusicBrainz release data
            mb_release_genres_and_tags = []
            raw_mb_genres_list = musicbrainz_release_summary.get("genres", [])
            if isinstance(raw_mb_genres_list, list):
                for g_info in raw_mb_genres_list:
                    if isinstance(g_info, dict) and g_info.get("name"):
                        mb_release_genres_and_tags.append(g_info["name"])

            raw_mb_tags_list = musicbrainz_release_summary.get("tags", [])
            if isinstance(raw_mb_tags_list, list):
                for t_info in raw_mb_tags_list:
                    if isinstance(t_info, dict) and t_info.get("name"):
                        mb_release_genres_and_tags.append(t_info["name"])  # Add tags as genres

            if mb_release_genres_and_tags:
                final_metadata["genre"] = list(set(final_metadata["genre"] + mb_release_genres_and_tags))

            # Genres from MB artist (broader than release)
            if artist_mb_genres:
                final_metadata["genre"] = list(set(final_metadata["genre"] + artist_mb_genres))

            # MusicBrainz Tracks (if not already populated by Spotify/Deezer)
            if not final_metadata["tracks"] and musicbrainz_release_summary.get("media"):  # Check for 'media'
                mb_tracks_extracted = []
                media_list = musicbrainz_release_summary.get("media", [])
                if isinstance(media_list, list):
                    current_track_position = 1  # Global position counter for all tracks from MB
                    for medium_data in media_list:
                        if isinstance(medium_data, dict):
                            medium_tracks_list = medium_data.get("tracks", [])
                            if isinstance(medium_tracks_list, list):
                                for track_item_data in medium_tracks_list:
                                    if isinstance(track_item_data, dict):
                                        title = track_item_data.get("title", "Unknown Track")

                                        length_ms = None
                                        recording_info = track_item_data.get("recording", {})
                                        mb_length = recording_info.get("length")
                                        if mb_length is not None:
                                            try:
                                                length_ms = int(mb_length)
                                            except (ValueError, TypeError):
                                                logger.warning(
                                                    f"Could not convert MB track length '{mb_length}' to int.",
                                                )

                                        isrc = None
                                        isrcs_list = recording_info.get("isrcs")
                                        if isinstance(isrcs_list, list) and isrcs_list:
                                            isrc = isrcs_list[0]

                                        musicbrainz_recording_id = recording_info.get("id")
                                        position_to_assign = current_track_position

                                        mb_tracks_extracted.append(
                                            {
                                                "title": title,
                                                "isrc": isrc,
                                                "position": position_to_assign,
                                                "duration_ms": length_ms,
                                                "source_specific_ids": {
                                                    "musicbrainz_recording_id": musicbrainz_recording_id,
                                                    "spotify_track_id": None,
                                                    "deezer_track_id": None,
                                                },
                                                "additional_details_track": None,
                                            },
                                        )
                                        current_track_position += 1
                if mb_tracks_extracted:
                    final_metadata["tracks"] = mb_tracks_extracted
                    logger.debug("Using tracks from MusicBrainz. Count: %s", len(final_metadata["tracks"]))

            final_metadata["source_musicbrainz_id"] = musicbrainz_release_summary.get("id")

        # --- Populate/Refine from Deezer (Fallback/Supplement) ---
        if deezer_data:  # deezer_data is already transformed by _transform_deezer_cached_data
            logger.debug("Processing Deezer data for combination: ID %s", deezer_data.get("id"))
            if not final_metadata.get("artist") or final_metadata["artist"] == band_name:
                final_metadata["artist"] = deezer_data.get("artist") or final_metadata["artist"]
            if not final_metadata.get("release") or final_metadata["release"] == release_name:
                final_metadata["release"] = deezer_data.get("release") or final_metadata["release"]

            dz_release_date = deezer_data.get("release_date")
            if dz_release_date:
                current_date = final_metadata.get("release_date")
                if (
                    not current_date
                    or (len(dz_release_date) > len(current_date))
                    or (len(dz_release_date) == 10 and current_date.count("-") < 2)
                ):
                    final_metadata["release_date"] = dz_release_date

            if not final_metadata["label"]:
                final_metadata["label"] = deezer_data.get("label")

            if deezer_data.get("genre"):
                final_metadata["genre"] = list(set(final_metadata["genre"] + deezer_data["genre"]))

            if not final_metadata["tracks"] and deezer_data.get("tracks"):
                final_metadata["tracks"] = deezer_data["tracks"]
                logger.debug("Using tracks from Deezer. Count: %s", len(final_metadata["tracks"]))

            # The _transform_deezer_cached_data should ideally populate an 'album_cover_url' field.
            # If not, we might need to access raw Deezer keys if they were passed through (e.g. cover_big).
            # For now, assume _transform_deezer_cached_data produces a compatible 'album_cover_url'.
            if not final_metadata["album_cover_url"] and deezer_data.get("album_cover_url"):
                final_metadata["album_cover_url"] = deezer_data["album_cover_url"]
            # Fallback to common Deezer cover keys if the transformed one is missing
            elif not final_metadata["album_cover_url"]:
                if deezer_data.get("cover_big"):
                    final_metadata["album_cover_url"] = deezer_data["cover_big"]
                elif deezer_data.get("cover_medium"):
                    final_metadata["album_cover_url"] = deezer_data["cover_medium"]

            final_metadata["source_deezer_id"] = deezer_data.get("id")

        # Final cleanup for genres - remove duplicates and None/empty strings, then sort
        if final_metadata.get("genre"):
            cleaned_genres = sorted({g for g in final_metadata["genre"] if isinstance(g, str) and g.strip()})
            final_metadata["genre"] = cleaned_genres
        else:
            final_metadata["genre"] = []

        if not isinstance(final_metadata.get("tracks"), list):
            final_metadata["tracks"] = []

        # Ensure all track items are dictionaries (model_dump from Pydantic Track)
        final_metadata["tracks"] = [
            t.model_dump(exclude_none=True) if isinstance(t, Track) else t for t in final_metadata["tracks"]
        ]

        logger.info(
            "Successfully combined metadata for '%s' - '%s'. Final track count: %s, Genres: %s",
            final_metadata.get("artist"),
            final_metadata.get("release"),
            len(final_metadata.get("tracks", [])),
            len(final_metadata.get("genre", [])),
        )
        logger.debug("Final combined metadata: %s", json.dumps(final_metadata, indent=2, ensure_ascii=False))

        # Correctly structure artist information before returning
        final_artist_name_str = final_metadata.get("artist", band_name)  # Use the artist name already decided

        # Убедимся, что имя артиста - это строка, а не словарь
        if isinstance(final_artist_name_str, dict):
            if isinstance(final_artist_name_str.get("name"), str):
                final_artist_name_str = final_artist_name_str.get("name")
            else:
                final_artist_name_str = band_name  # Fallback к оригинальному имени, если все остальное не работает

        # Initialize artist IDs
        actual_spotify_artist_id = None
        actual_musicbrainz_artist_id = mb_artist_id  # Prioritize the mb_artist_id argument passed to this function
        actual_deezer_artist_id = None

        # Extract Spotify Artist ID
        if spotify_release_summary:
            # Check if it's transformed data (has source_specific_ids at top level)
            if isinstance(spotify_release_summary.get("source_specific_ids"), dict):
                actual_spotify_artist_id = spotify_release_summary["source_specific_ids"].get("spotify_artist_id")
            # Check if it's transformed data where artist is an object with source_specific_ids
            elif isinstance(spotify_release_summary.get("artist"), dict) and isinstance(
                spotify_release_summary["artist"].get("source_specific_ids"),
                dict,
            ):
                actual_spotify_artist_id = spotify_release_summary["artist"]["source_specific_ids"].get(
                    "spotify_artist_id",
                )
            # Fallback for raw Spotify data (list of artists)
            elif isinstance(spotify_release_summary.get("artists"), list) and spotify_release_summary["artists"]:
                actual_spotify_artist_id = spotify_release_summary["artists"][0].get("id")

        # Extract MusicBrainz Artist ID (if not already set by mb_artist_id argument)
        if not actual_musicbrainz_artist_id and musicbrainz_release_summary:
            # Check if it's transformed data
            if isinstance(musicbrainz_release_summary.get("source_specific_ids"), dict):
                actual_musicbrainz_artist_id = musicbrainz_release_summary["source_specific_ids"].get(
                    "musicbrainz_artist_id",
                )
            # Check if it's transformed data where artist is an object with source_specific_ids
            elif isinstance(musicbrainz_release_summary.get("artist"), dict) and isinstance(
                musicbrainz_release_summary["artist"].get("source_specific_ids"),
                dict,
            ):
                actual_musicbrainz_artist_id = musicbrainz_release_summary["artist"]["source_specific_ids"].get(
                    "musicbrainz_artist_id",
                )
            # Fallback for raw MusicBrainz data (artist-credit list)
            elif (
                isinstance(musicbrainz_release_summary.get("artist-credit"), list)
                and musicbrainz_release_summary["artist-credit"]
            ):
                artist_credit = musicbrainz_release_summary["artist-credit"][0]
                if isinstance(artist_credit.get("artist"), dict):
                    actual_musicbrainz_artist_id = artist_credit["artist"].get("id")

        # Extract Deezer Artist ID
        if deezer_data:  # deezer_data is expected to be transformed by _transform_deezer_cached_data
            if isinstance(deezer_data.get("source_specific_ids"), dict):
                actual_deezer_artist_id = deezer_data["source_specific_ids"].get("deezer_artist_id")
            # Fallback if transformed data structure is slightly different (artist object contains the ids)
            elif isinstance(deezer_data.get("artist"), dict) and isinstance(
                deezer_data["artist"].get("source_specific_ids"),
                dict,
            ):
                actual_deezer_artist_id = deezer_data["artist"]["source_specific_ids"].get("deezer_artist_id")
            # Fallback to basic artist.id if present in transformed deezer_data.artist object
            elif isinstance(deezer_data.get("artist"), dict) and not actual_deezer_artist_id:
                actual_deezer_artist_id = deezer_data["artist"].get("id")

        artist_payload = {
            "name": final_artist_name_str,
            "source_specific_ids": {
                "spotify_artist_id": actual_spotify_artist_id,
                "musicbrainz_artist_id": actual_musicbrainz_artist_id,
                "deezer_artist_id": str(actual_deezer_artist_id) if actual_deezer_artist_id is not None else None,
            },
            "social_links": artist_social_links.model_dump(exclude_none=True),
        }
        final_metadata["artist"] = artist_payload  # Update the 'artist' field in final_metadata

        logger.info(
            "Final combined metadata (with structured artist) for '%s' - '%s': %s",
            band_name,  # Using original band_name for logging clarity
            release_name,  # Using original release_name for logging clarity
            json.dumps(final_metadata, indent=2, ensure_ascii=False),
        )
        return final_metadata

    def _score_deezer_item(self, item: dict[str, Any], normalized_artist: str, normalized_album: str) -> int:
        """Score a Deezer release based on its relevance to the search terms.

        Args:
            item: Deezer release item
            normalized_artist: Normalized artist name for comparison
            normalized_album: Normalized album name for comparison

        Returns:
            Score value (higher is better match)
        """
        score = 0
        item_title = normalize_text(item.get("title", ""))
        item_artist = normalize_text(item.get("artist", {}).get("name", ""))

        # Exact matches
        if item_title == normalized_album:
            score += 10
        elif normalized_album in item_title:
            score += 5

        if item_artist == normalized_artist:
            score += 10
        elif normalized_artist in item_artist:
            score += 5

        return score

    async def _extract_deezer_tracks(self, album_id: str) -> list[dict[str, Any]]:
        """Extract track data from a Deezer album.

        Args:
            album_id: Deezer album ID

        Returns:
            List of track data dictionaries
        """
        # Check cache first
        cached_tracks = await cache.get_release_details("deezer", f"{album_id}_tracks")
        if cached_tracks:
            logger.debug("Using cached Deezer tracks for %s", album_id)
            if isinstance(cached_tracks, list):
                return cached_tracks
            logger.warning("Cached Deezer tracks for %s have invalid format", album_id)
            return []

        # Not in cache, fetch from API
        tracks: list[dict[str, Any]] = []
        try:
            logger.debug(f"DEBUG: Calling Deezer get_album_tracks (in _extract) with album_id: {album_id}")
            album_tracks: list[dict[str, Any]] = await self._deezer.get_album_tracks(album_id)
            logger.debug("DEBUG: Deezer get_album_tracks (in _extract) result: %s", json.dumps(album_tracks, indent=4))

            for track_item in album_tracks:
                track: dict[str, Any] = {
                    "position": track_item.get("track_position", 0),
                    "title": track_item.get("title", ""),
                    "duration_ms": track_item.get("duration", 0) * 1000,  # Convert to ms to match Spotify
                    "isrc": track_item.get("isrc", ""),
                }
                tracks.append(track)

                # Cache the result
                _ = await cache.cache_release_details("deezer", f"{album_id}_tracks", {"tracks": tracks})
        except Exception as e:
            logger.warning("Error extracting Deezer tracks: %s", str(e))

        return tracks

    async def _get_deezer_fallback_data(
        self,
        artist: str,
        album: str,
    ) -> dict[str, Any]:
        """Attempt to fetch release data from Deezer as a fallback.

        This method searches Deezer for the release and, if a suitable match is found,
        fetches its full details including tracks. The fetched raw details are cached.

        Args:
            artist: The artist's name.
            album: The album's name.

        Returns:
            A dictionary containing Deezer raw release data if found, otherwise an empty dict.
        """
        deezer_data_to_return: dict[str, Any] = {}
        normalized_artist = normalize_text(artist)
        normalized_album = normalize_text(album)

        try:
            logger.info("[DEEZER_FALLBACK] Searching Deezer for: '%s' - '%s'", artist, album)
            # Check cache for search results first - This step was missing in the previous iteration of this specific function
            # but is good practice. However, the main goal here is to fetch and cache *details* if search is successful.
            # For simplicity with current task, we proceed to search, then cache details if found.
            # A more robust implementation might cache search results too.

            search_response = await self._deezer.search_releases(
                artist,
                album,
                limit=5,
            )  # limit to 5 results for scoring
            self._update_error_stats("deezer", True)  # Mark search attempt

            if search_response and search_response.get("data"):
                best_match_item = None
                highest_score = -1

                for item in search_response["data"]:
                    score = self._score_deezer_item(item, normalized_artist, normalized_album)
                    logger.debug("[DEEZER_FALLBACK] Scoring Deezer item: %s, Score: %s", item.get("title"), score)
                    if score > highest_score:
                        highest_score = score
                        best_match_item = item

                # Set a threshold for a good match, e.g. score > 5 or based on your scoring logic
                if best_match_item and highest_score > 0:  # Adjust threshold as needed
                    deezer_album_id = str(best_match_item["id"])
                    logger.info(
                        "[DEEZER_FALLBACK] Found best Deezer match: ID %s, Title: '%s', Score: %s. Fetching details.",
                        deezer_album_id,
                        best_match_item.get("title"),
                        highest_score,
                    )

                    # Fetch full album details from Deezer API
                    deezer_album_raw_details = await self._deezer.get_album(deezer_album_id)
                    # self._update_error_stats("deezer", True) # Already updated for search, this is part of the same logical operation

                    if deezer_album_raw_details:  # Ensure details were actually fetched
                        # Cache the raw, full details from Deezer API
                        try:
                            _ = await cache.cache_release_details(
                                source="deezer",
                                release_id=deezer_album_id,
                                details=deezer_album_raw_details,
                                # country_code is not typically part of Deezer get_album or its caching key for details
                            )
                            logger.info(
                                "[DEEZER_FALLBACK] Successfully cached raw Deezer album details for ID %s",
                                deezer_album_id,
                            )
                        except Exception as e_cache:
                            logger.warning(
                                "[DEEZER_FALLBACK] Failed to cache Deezer album details for ID %s: %s",
                                deezer_album_id,
                                e_cache,
                                exc_info=True,
                            )
                        deezer_data_to_return = deezer_album_raw_details
                    else:
                        logger.warning(
                            "[DEEZER_FALLBACK] Got empty details for Deezer album ID %s after successful search match.",
                            deezer_album_id,
                        )
                else:  # This else corresponds to 'if best_match_item and highest_score > 0:'
                    logger.info(
                        "[DEEZER_FALLBACK] No suitable Deezer match found after scoring for: '%s' - '%s'",
                        artist,
                        album,
                    )
            else:  # This else corresponds to 'if search_response and search_response.get("data"):'
                logger.info("[DEEZER_FALLBACK] Deezer search returned no data for: '%s' - '%s'", artist, album)

        except Exception as e:
            logger.error(
                "[DEEZER_FALLBACK] Error during Deezer fallback data fetching for '%s' - '%s': %s",
                artist,
                album,
                e,
                exc_info=True,
            )
            self._update_error_stats("deezer", False)  # Mark error for the Deezer source

        return deezer_data_to_return

    async def _fetch_artist_additional_data(
        self,
        mb_artist_id: str | None,
    ) -> tuple[SocialLinks, list[str]]:
        """Fetch additional artist data from MusicBrainz.

        Args:
            mb_artist_id: MusicBrainz artist ID or None

        Returns:
            Tuple with SocialLinks instance and genre list
        """
        social_links_model = SocialLinks()  # Default empty model
        genres: list[str] = []

        if not mb_artist_id:
            logger.debug("No mb_artist_id provided, returning empty SocialLinks and genres.")
            return social_links_model, genres

        cache_key = f"artist_{mb_artist_id}"
        cached_data = await cache.get_release_details("musicbrainz", cache_key)

        parsed_social_links_from_cache_successfully = False
        if cached_data:
            logger.debug("Found cached data for MusicBrainz artist %s: %s", mb_artist_id, cached_data)
            cached_links_dict = cached_data.get("social_links")
            cached_genres_list = cached_data.get("genres")

            if cached_links_dict and isinstance(cached_links_dict, dict):
                try:
                    social_links_model = SocialLinks(**cached_links_dict)
                    logger.debug(
                        "Successfully parsed cached social_links_dict into SocialLinks model for %s: %s",
                        mb_artist_id,
                        social_links_model.model_dump(exclude_none=True),
                    )
                    parsed_social_links_from_cache_successfully = True
                except Exception as e_pydantic_cache:
                    logger.warning(
                        "Pydantic SocialLinks validation error from CACHED data for %s: %s, input: %s. Will attempt API fetch.",
                        mb_artist_id,
                        e_pydantic_cache,
                        cached_links_dict,
                    )
                    social_links_model = SocialLinks()  # Reset to empty on parsing error
            else:
                logger.debug(
                    "Cached social_links_dict for %s is missing or not a dict. Will attempt API fetch.",
                    mb_artist_id,
                )

            if cached_genres_list and isinstance(cached_genres_list, list):
                genres = cached_genres_list
                logger.debug("Successfully loaded genres from cache for %s: %s", mb_artist_id, genres)
            else:
                logger.debug("No genres found in cache for %s or format is invalid.", mb_artist_id)
                # genres remains []

            # If we successfully parsed social links from cache, we can return (genres are optional from cache)
            if parsed_social_links_from_cache_successfully:
                logger.debug(
                    "Returning artist data (social links parsed, genres may be from cache) for %s from cache.",
                    mb_artist_id,
                )
                return social_links_model, genres
            logger.debug(
                "Proceeding to API fetch for %s as cached social links were not successfully parsed.",
                mb_artist_id,
            )
        else:
            logger.debug("No cached data found for MusicBrainz artist %s. Fetching from API.", mb_artist_id)

        # Not in cache OR cached social_links data was not sufficient/parsed_successfully was False, fetch from API
        logger.info(
            "Fetching MusicBrainz artist data from API for %s (cache miss or incomplete/invalid social_links cache)",
            mb_artist_id,
        )
        try:
            logger.debug("DEBUG: Calling MusicBrainz get_social_links with mb_artist_id: %s", mb_artist_id)
            fetched_social_links_dict = await self._musicbrainz.get_social_links(mb_artist_id)
            logger.debug(
                "DEBUG: MusicBrainz get_social_links API result (dict) for %s: %s",
                mb_artist_id,
                json.dumps(fetched_social_links_dict, indent=4),
            )

            current_social_links_were_from_api = False
            if isinstance(fetched_social_links_dict, dict):
                try:
                    social_links_model = SocialLinks(**fetched_social_links_dict)
                    logger.debug(
                        "Successfully parsed FETCHED social_links_dict into SocialLinks model for %s: %s",
                        mb_artist_id,
                        social_links_model.model_dump(exclude_none=True),
                    )
                    current_social_links_were_from_api = True
                except Exception as e_pydantic_fetch:
                    logger.exception(
                        "Pydantic SocialLinks validation error from FETCHED API data for %s: %s, input: %s",
                        mb_artist_id,
                        e_pydantic_fetch,
                        fetched_social_links_dict,
                    )
                    social_links_model = SocialLinks()  # Fallback to empty model
            else:
                logger.warning(
                    "Fetched social links from MusicBrainz API was not a dictionary for artist_id %s. Received: %s",
                    mb_artist_id,
                    type(fetched_social_links_dict),
                )
                social_links_model = SocialLinks()  # Ensure it's an empty model if fetch failed

            # Fetch genres only if we are already fetching from API (or cache for genres was empty)
            # This avoids re-fetching genres if they were already successfully loaded from cache
            # and only social_links needed an API update.
            if not genres:  # Only fetch genres if they weren't in cache
                logger.debug("DEBUG: Calling MusicBrainz get_genres with mb_artist_id: %s", mb_artist_id)
                genre_data = await self._musicbrainz.get_genres(mb_artist_id)
                logger.debug(
                    "DEBUG: MusicBrainz genres API result for %s: %s",
                    mb_artist_id,
                    json.dumps(genre_data, indent=4),
                )
                if genre_data:
                    genres.extend(genre_data)
            else:
                logger.debug("Skipping API fetch for genres for %s, as they were loaded from cache.", mb_artist_id)

            # Cache the newly fetched/updated data
            # We cache social_links_model.model_dump() to ensure consistent dict structure in cache.
            # Genres are already a list[str].
            if current_social_links_were_from_api or not genres:  # Cache if links came from API or genres were fetched
                logger.info(
                    "Caching updated artist data (SocialLinks from API: %s, Genres fetched: %s) for %s",
                    current_social_links_were_from_api,
                    not bool(cached_data.get("genres") if cached_data else []),
                    mb_artist_id,
                )
                await cache.cache_release_details(
                    "musicbrainz",
                    cache_key,
                    {
                        "social_links": social_links_model.model_dump(exclude_none=True),
                        "genres": genres,
                    },
                )
            else:
                logger.debug(
                    "No new data fetched from API to update cache for artist %s (data likely from cache).",
                    mb_artist_id,
                )

        except Exception as e:
            logger.warning(
                "Error fetching artist additional data from API for %s: %s. Using default empty SocialLinks and genres.",
                mb_artist_id,
                str(e),
                exc_info=True,
            )
            social_links_model = SocialLinks()  # Fallback on any other error during API fetch
            genres = []  # Reset genres on API fetch error

        logger.debug(
            "Returning final artist_social_links: %s and genres: %s for %s",
            social_links_model.model_dump(exclude_none=True),
            genres,
            mb_artist_id,
        )
        return social_links_model, genres

    def _score_spotify_release(self, item: dict[str, Any], normalized_artist: str, normalized_album: str) -> int:
        """Score a Spotify release based on its relevance to search terms.

        Args:
            item: Spotify album item
            normalized_artist: Normalized artist name for comparison
            normalized_album: Normalized album name for comparison

        Returns:
            Score value (higher is better match)
        """
        score = 0
        album_name = normalize_text(item.get("name", ""))

        # Compare album name
        if album_name == normalized_album:
            score += 10
        elif normalized_album in album_name:
            score += 5

        # Compare artists
        artists = item.get("artists", [])
        has_artist_match = False

        for artist in artists:
            artist_name = normalize_text(artist.get("name", ""))
            if artist_name == normalized_artist:
                score += 10
                has_artist_match = True
                break
            if normalized_artist in artist_name or artist_name in normalized_artist:
                score += 5
                has_artist_match = True
                break

        # If no artist match, penalize heavily
        if not has_artist_match:
            score -= 10

        # Prefer albums over singles, EPs, compilations
        album_type = item.get("album_type", "")
        if album_type == "album":
            score += 3
        elif album_type == "single":
            score += 1

        # Prefer albums with more tracks (likely to be the full release)
        total_tracks = item.get("total_tracks", 0)
        if total_tracks > 5:
            score += 2
        elif total_tracks > 10:
            score += 3

        return score

    async def _find_best_spotify_release(
        self,
        artist: str,
        album: str,
        country_code: str | None = None,
    ) -> dict[str, Any] | None:
        """Find the best matching Spotify release.

        Args:
            artist: Artist name
            album: Album name
            country_code: Optional country code

        Returns:
            Best matching Spotify release data or None if not found
        """
        # Check cache first
        cached_results = await cache.get_search_results(
            source="spotify",
            band_name=artist,
            release_name=album,
            country_code=country_code,
        )
        logger.debug("DEBUG: Spotify cached_results: %s", cached_results)
        if cached_results is not None:
            logger.debug("Using cached Spotify search results for %s - %s", artist, album)
        else:
            # Not in cache, search on Spotify

            try:
                search_results = await self._spotify.search_releases(artist, album, market=country_code)
                logger.debug("DEBUG: Spotify search_results: %s", json.dumps(search_results, indent=4))

                if search_results and "albums" in search_results and "items" in search_results["albums"]:
                    cached_results = search_results["albums"]["items"]
                    # Cache the search results
                    _ = await cache.cache_search_results(
                        source="spotify",
                        band_name=artist,
                        release_name=album,
                        country_code=country_code,
                        results=cached_results,
                    )
                else:
                    cached_results = []
            except Exception as e:
                logger.warning("Spotify search failed: %s", str(e))
                return None

        if not cached_results:
            return None

        # Score the results to find the best match
        normalized_artist = normalize_text(artist)
        normalized_album = normalize_text(album)

        scored_items = [
            (item, self._score_spotify_release(item, normalized_artist, normalized_album)) for item in cached_results
        ]

        # Sort by score (descending)
        scored_items.sort(key=lambda x: x[1], reverse=True)

        # Return the highest-scoring item if it's a reasonable match
        if scored_items and scored_items[0][1] > 5:
            return scored_items[0][0]

        return None

    def _score_musicbrainz_release(
        self,
        release: dict[str, Any],
        normalized_artist: str,
        normalized_album: str,
    ) -> float:
        """Score a MusicBrainz release based on its relevance to search terms.

        Args:
            release: MusicBrainz release group data
            normalized_artist: Normalized artist name for comparison
            normalized_album: Normalized album name for comparison

        Returns:
            Score value (higher is better match)
        """
        score = 0.0

        # Compare release title
        title = normalize_text(release.get("title", ""))

        if title == normalized_album:
            score += 10.0
        elif normalized_album in title:
            score += 5.0
        elif title in normalized_album:
            score += 3.0

        # Check artist credit
        artist_credits = release.get("artist-credit", [])

        for credit in artist_credits:
            if "artist" in credit and "name" in credit["artist"]:
                artist_name = normalize_text(credit["artist"]["name"])

                if artist_name == normalized_artist:
                    score += 10.0
                    break
                if normalized_artist in artist_name:
                    score += 5.0
                    break
                if artist_name in normalized_artist:
                    score += 3.0
                    break

        # Consider release type
        if "primary-type" in release:
            if release["primary-type"] == "Album":
                score += 3.0
            elif release["primary-type"] in ["EP", "Single"]:
                score += 1.0

        return score

    async def _find_best_musicbrainz_release(
        self,
        artist: str,
        album: str,
    ) -> dict[str, Any] | None:
        """Find the best matching MusicBrainz release.

        Args:
            artist: Artist name
            album: Album name

        Returns:
            Best matching MusicBrainz release data or None if not found
        """
        # Check cache first
        cached_results = await cache.get_search_results("musicbrainz", artist, album, None)
        if cached_results is not None:
            logger.debug("Using cached MusicBrainz search results for %s - %s", artist, album)
        else:
            # Not in cache, search on MusicBrainz
            try:
                logger.debug(
                    "[DEBUG_SERVICE_MB_SEARCH_API] Calling MusicBrainz API: artist='%s', album='%s'",
                    artist,
                    album,
                )
                search_results = await self._musicbrainz.search_releases(artist, album)
                logger.debug(
                    "[DEBUG_SERVICE_MB_SEARCH_API_RESULT] MusicBrainz API search_releases raw result: %s",
                    json.dumps(search_results, indent=2, ensure_ascii=False),
                )

                # Fix: MusicBrainzClient.search_releases returns "releases", not "release-groups"
                if search_results and "releases" in search_results:
                    cached_results = search_results["releases"]
                    # Cache the search results
                    logger.debug(
                        "[DEBUG_SERVICE_MB_CACHE_SEARCH_WRITE] Caching MusicBrainz search results for key (artist='%s', album='%s'). Data: %s",
                        artist,
                        album,
                        json.dumps(cached_results, indent=2, ensure_ascii=False),
                    )
                    _ = await cache.cache_search_results("musicbrainz", artist, album, None, cached_results)
                else:
                    cached_results = []
            except Exception as e:
                logger.warning("MusicBrainz search failed: %s", str(e))
                return None

        if not cached_results:
            return None

        # Score the results to find the best match
        normalized_artist = normalize_text(artist)
        normalized_album = normalize_text(album)

        logger.debug(
            "DEBUG: MusicBrainz cached_results first item: %s",
            json.dumps(cached_results[0] if cached_results else {}, indent=2),
        )

        scored_items = [
            (item, self._score_musicbrainz_release(item, normalized_artist, normalized_album))
            for item in cached_results
        ]

        # Sort by score (descending)
        scored_items.sort(key=lambda x: x[1], reverse=True)

        # Return the highest-scoring item if it's a reasonable match
        if scored_items and scored_items[0][1] > 5.0:
            best_match = scored_items[0][0]  # Extract the best matching item
            logger.debug("DEBUG: MusicBrainz best match: %s", json.dumps(best_match, indent=2))
            return best_match

        return None

    async def fetch_release_metadata(
        self,
        band_name: str,
        release_name: str,
        country_code: str | None = None,
        prefetched_data_list: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Fetch metadata for a music release from various sources.

        Args:
            band_name: Name of the artist or band
            release_name: Name of the release (album, EP, single)
            country_code: Optional ISO 3166-1 alpha-2 country code
            prefetched_data_list: Optional list of prefetched data from various sources.
                                Each dict in list: {'source': str, 'data': dict[str, Any]}

        Returns:
            Dictionary with aggregated release metadata

        Raises:
            Exception: If an error occurs during fetch
        """
        logger.info(
            "Fetching metadata for band '%s', release '%s', country code '%s', prefetched_data_list is present: %s",
            band_name,
            release_name,
            country_code,
            prefetched_data_list is not None,
        )

        # This map will store the fully resolved data for each source,
        # whether it came from prefetch or was actively fetched.
        # The data stored here should be what _combine_metadata_from_sources expects.
        collected_data_for_sources: dict[str, Any | None] = {
            "spotify": None,
            "musicbrainz": None,
            "deezer": None,
        }

        # Flags to track if data for a source was prefetched and successfully processed
        is_spotify_data_prefetched = False
        is_musicbrainz_data_prefetched = False
        is_deezer_data_prefetched = False

        if prefetched_data_list:
            logger.info("Processing prefetched data list (%s items)...", len(prefetched_data_list))
            for item in prefetched_data_list:
                source = item.get("source")
                data = item.get("data")  # This is the transformed data from helpers.py
                if not source or not data:
                    logger.warning("Skipping invalid item in prefetched_data_list: %s", item)
                    continue

                logger.info("Found prefetched data for source: %s", source)
                if source == "spotify":
                    collected_data_for_sources["spotify"] = data
                    is_spotify_data_prefetched = True
                elif source == "musicbrainz":
                    collected_data_for_sources["musicbrainz"] = data
                    is_musicbrainz_data_prefetched = True
                elif source == "deezer":
                    collected_data_for_sources["deezer"] = data
                    is_deezer_data_prefetched = True
            logger.info("Finished processing prefetched data list.")

        # --- ADDED DEBUG LOG ---
        logger.debug(
            "[DEBUG_PREFETCH_FLAG_SPOTIFY] For task processing band '%s', release '%s': is_spotify_data_prefetched = %s",
            band_name,
            release_name,
            is_spotify_data_prefetched,
        )
        # --- END ADDED DEBUG LOG ---

        # --- Spotify Data Fetching (if not prefetched) ---
        if not is_spotify_data_prefetched:
            logger.info(
                "Spotify data not prefetched, calling _find_best_spotify_release for '%s' - '%s'",
                band_name,
                release_name,
            )
            spotify_search_summary = await self._find_best_spotify_release(
                artist=band_name,
                album=release_name,
                country_code=country_code,
            )
            if spotify_search_summary and spotify_search_summary.get("id"):
                spotify_album_id = spotify_search_summary["id"]
                logger.info(
                    "Found Spotify album ID from search: %s for '%s' - '%s'",
                    spotify_album_id,
                    band_name,
                    release_name,
                )

                # Try to get full album details from cache
                cached_spotify_album_details = await cache.get_release_details("spotify", spotify_album_id)
                if cached_spotify_album_details:
                    logger.info("Using cached full Spotify album details for ID %s", spotify_album_id)
                    collected_data_for_sources["spotify"] = cached_spotify_album_details
                    self._update_error_stats("spotify", True)  # Consider cache hit a success for this source
                else:
                    logger.info(
                        "Full Spotify album details for ID %s not in cache, fetching from API.",
                        spotify_album_id,
                    )
                    try:
                        full_spotify_album_details = await self._spotify.get_album(
                            spotify_album_id,
                            market=country_code,
                        )
                        if full_spotify_album_details:
                            logger.info("Successfully fetched full Spotify album details for ID %s", spotify_album_id)

                            # Enrich tracks with ISRC and other details if possible
                            if isinstance(full_spotify_album_details.get("tracks"), dict) and isinstance(
                                full_spotify_album_details["tracks"].get("items"),
                                list,
                            ):
                                summary_tracks = full_spotify_album_details["tracks"]["items"]
                                track_ids_to_fetch = [t["id"] for t in summary_tracks if t and t.get("id")]

                                if track_ids_to_fetch:
                                    logger.info("Fetching detailed track info for %d tracks", len(track_ids_to_fetch))
                                    try:
                                        detailed_tracks = await self._spotify.get_several_tracks(
                                            track_ids=track_ids_to_fetch,
                                            market=country_code,
                                        )

                                        if detailed_tracks:  # detailed_tracks это уже список треков
                                            # Логируем пример первого трека для отладки
                                            if detailed_tracks and len(detailed_tracks) > 0:
                                                first_track = detailed_tracks[0]
                                                logger.debug(
                                                    "Spotify track details example (first track): %s",
                                                    json.dumps(first_track, indent=2),
                                                )
                                                # Специально проверяем наличие ISRC
                                                if first_track and isinstance(first_track.get("external_ids"), dict):
                                                    isrc = first_track.get("external_ids", {}).get("isrc")
                                                    logger.debug("ISRC from first track: %s", isrc)

                                            # Получаем идентификаторы треков для быстрого поиска
                                            detailed_tracks_map = {
                                                t.get("id"): t
                                                for t in detailed_tracks  # Используем directamente detailed_tracks
                                                if t and t.get("id")
                                            }

                                            # Обогащаем данные о треках из полной информации
                                            enriched_tracks = []
                                            for track_summary in summary_tracks:
                                                track_id = track_summary.get("id")
                                                if track_id and track_id in detailed_tracks_map:
                                                    detailed_track = detailed_tracks_map[track_id]
                                                    # Объединяем информацию, приоритет - детализированным данным
                                                    enriched_track = track_summary.copy()
                                                    # Копируем external_ids для получения ISRC из ПОЛНОГО трека
                                                    if "external_ids" in detailed_track:
                                                        enriched_track["external_ids"] = detailed_track[
                                                            "external_ids"
                                                        ].copy()  # Копируем, чтобы не изменить оригинальный detailed_track

                                                        current_external_ids = enriched_track["external_ids"]
                                                        if current_external_ids and "isrc" in current_external_ids:
                                                            # Поле isrc уже должно быть в current_external_ids, если оно пришло от Spotify
                                                            logger.debug(
                                                                "Found ISRC %s in external_ids for track %s",
                                                                current_external_ids["isrc"],
                                                                track_summary.get("name"),
                                                            )
                                                        else:
                                                            logger.debug(
                                                                "No ISRC in external_ids for track %s. external_ids: %s",
                                                                track_summary.get("name"),
                                                                json.dumps(current_external_ids),
                                                            )
                                                    else:
                                                        enriched_track[
                                                            "external_ids"
                                                        ] = {}  # Устанавливаем пустой словарь, если в detailed_track нет external_ids
                                                        logger.debug(
                                                            "No external_ids field in detailed_track for track %s",
                                                            track_summary.get("name"),
                                                        )
                                                    enriched_tracks.append(enriched_track)
                                                else:
                                                    # Если трек не найден в детализированных данных, оставляем оригинал
                                                    enriched_tracks.append(track_summary)

                                            # Заменяем оригинальные треки обогащенными
                                            full_spotify_album_details["tracks"]["items"] = enriched_tracks
                                            logger.info(
                                                "Successfully enriched %d tracks with detailed information",
                                                len(enriched_tracks),
                                            )
                                        else:
                                            logger.warning(
                                                "Failed to get detailed track information: unexpected response format",
                                            )
                                    except Exception as e_tracks:
                                        logger.error(
                                            "Error fetching detailed track information: %s",
                                            e_tracks,
                                            exc_info=True,
                                        )
                                # else: no track IDs to fetch, do nothing

                            await cache.cache_release_details("spotify", spotify_album_id, full_spotify_album_details)
                            collected_data_for_sources["spotify"] = full_spotify_album_details
                            self._update_error_stats("spotify", True)
                        else:
                            logger.warning("Spotify get_album returned no data for ID %s", spotify_album_id)
                            # collected_data_for_sources["spotify"] remains None or previous value (None here)
                            self._update_error_stats("spotify", False)
                    except Exception as e_spotify_album:
                        logger.error(
                            "Error fetching full Spotify album details for ID %s: %s",
                            spotify_album_id,
                            e_spotify_album,
                            exc_info=True,
                        )
                        self._update_error_stats("spotify", False)
                        # collected_data_for_sources["spotify"] remains None
            else:  # Соответствует if spotify_search_summary and spotify_search_summary.get("id"):
                logger.warning("No data found from Spotify search for '%s' - '%s'.", band_name, release_name)
                # collected_data_for_sources["spotify"] remains None
                # self._update_error_stats("spotify", False) # No API call was made if search failed at client level or no match
        else:
            logger.info("Skipping Spotify API fetch, using prefetched data for '%s' - '%s'.", band_name, release_name)
            # If prefetched, collected_data_for_sources["spotify"] is already set

        # --- MusicBrainz Data Fetching (if not prefetched) ---
        mb_artist_id_for_social_links: str | None = None  # For _fetch_artist_additional_data
        if not is_musicbrainz_data_prefetched:
            logger.info(
                "MusicBrainz data not prefetched, calling _find_best_musicbrainz_release for '%s' - '%s'",
                band_name,
                release_name,
            )
            musicbrainz_summary_from_search = await self._find_best_musicbrainz_release(
                artist=band_name,
                album=release_name,
            )

            raw_mb_details_to_use = None  # This will hold the data we intend to use

            if musicbrainz_summary_from_search:
                mb_release_id_from_summary = musicbrainz_summary_from_search.get("id")

                if mb_release_id_from_summary:
                    # 1. Try to get from details cache
                    cached_mb_details = await cache.get_release_details("musicbrainz", mb_release_id_from_summary)
                    if cached_mb_details and self._is_musicbrainz_data_sufficiently_complete(cached_mb_details):
                        logger.info(
                            "Using cached complete MusicBrainz details for ID %s for '%s' - '%s'",
                            mb_release_id_from_summary,
                            band_name,
                            release_name,
                        )
                        raw_mb_details_to_use = cached_mb_details
                        # Since we used cache, no API call to get_release is made here.
                        # Update error stats for cache hit (optional, depends on definition of "total" calls)
                        # self._update_error_stats("musicbrainz", True) # Let's assume total counts API calls for now

                    if not raw_mb_details_to_use:  # Not in cache or cache was not complete
                        logger.info(
                            "MusicBrainz details for ID %s not in cache or incomplete, attempting API fetch.",
                            mb_release_id_from_summary,
                        )
                        try:
                            # 2. Fetch from MusicBrainz API if not found in cache or cache was incomplete
                            fetched_mb_details = await self._musicbrainz.get_release(
                                mb_release_id_from_summary,
                                inc=DEFAULT_MUSICBRAINZ_INC_PARAMS,
                            )
                            self._update_error_stats("musicbrainz", True)  # Record API call attempt

                            if fetched_mb_details:
                                # Cache the newly fetched details
                                await cache.cache_release_details(
                                    "musicbrainz",
                                    mb_release_id_from_summary,
                                    fetched_mb_details,
                                )
                                logger.info(
                                    "Successfully fetched and cached MusicBrainz details for ID %s",
                                    mb_release_id_from_summary,
                                )
                                raw_mb_details_to_use = fetched_mb_details
                            else:
                                logger.warning(
                                    "MusicBrainz get_release returned no data for ID %s",
                                    mb_release_id_from_summary,
                                )
                                # self._update_error_stats("musicbrainz", False) # Already True for attempt, or handle empty as success?
                        except Exception as e_get_release:
                            logger.error(
                                "Error fetching MusicBrainz details for ID %s: %s",
                                mb_release_id_from_summary,
                                e_get_release,
                                exc_info=True,
                            )
                            self._update_error_stats("musicbrainz", False)  # Record API call failure

                # 3. Now check and use the details (either from cache or API)
                if raw_mb_details_to_use and self._is_musicbrainz_data_sufficiently_complete(raw_mb_details_to_use):
                    collected_data_for_sources["musicbrainz"] = raw_mb_details_to_use
                    logger.info(
                        "Successfully processed full MusicBrainz data (fetched or cached) for '%s' - '%s'.",
                        band_name,
                        release_name,
                    )
                    artist_credits = raw_mb_details_to_use.get("artist-credit", [])
                    if artist_credits and isinstance(artist_credits, list) and len(artist_credits) > 0:
                        first_artist_credit = artist_credits[0]
                        if isinstance(first_artist_credit, dict) and isinstance(
                            first_artist_credit.get("artist"),
                            dict,
                        ):
                            mb_artist_id_for_social_links = first_artist_credit.get("artist", {}).get("id")
                # This 'else' covers cases where:
                # - musicbrainz_summary_from_search was found, but mb_release_id_from_summary was missing.
                # - API fetch for details failed or returned empty/incomplete.
                # - Details from cache were incomplete and API fetch also failed or was incomplete.
                elif musicbrainz_summary_from_search:  # musicbrainz_summary_from_search implies an ID was likely there
                    logger.warning(
                        "MusicBrainz data for '%s'-'%s' (ID: %s) was not used: full details could not be obtained or were incomplete.",
                        band_name,
                        release_name,
                        musicbrainz_summary_from_search.get("id", "N/A"),
                    )
            else:  # musicbrainz_summary_from_search was None (no search result)
                logger.warning("No data found from MusicBrainz search for '%s' - '%s'.", band_name, release_name)
        else:  # is_musicbrainz_data_prefetched is True
            logger.info(
                "Skipping MusicBrainz API fetch, using prefetched data for '%s' - '%s'.",
                band_name,
                release_name,
            )
            # If MusicBrainz data was prefetched, ensure mb_artist_id_for_social_links is extracted
            prefetched_mb_data = collected_data_for_sources.get("musicbrainz")
            if prefetched_mb_data:  # Ensure it's not None
                # Try to get from transformed structure first (from helpers.py)
                if isinstance(prefetched_mb_data.get("source_specific_ids"), dict):
                    mb_artist_id_for_social_links = prefetched_mb_data["source_specific_ids"].get(
                        "musicbrainz_artist_id",
                    )
                    logger.debug(
                        "[PREFETCH_MB_ARTIST_ID_EXTRACT] Extracted mb_artist_id %s from prefetched_mb_data.source_specific_ids",
                        mb_artist_id_for_social_links,
                    )
                # Fallback for raw-ish data that might have artist-credit (less likely if truly from helpers.py)
                elif isinstance(prefetched_mb_data.get("artist-credit"), list):
                    artist_credits = prefetched_mb_data.get("artist-credit", [])
                    if artist_credits and len(artist_credits) > 0 and isinstance(artist_credits[0].get("artist"), dict):
                        mb_artist_id_for_social_links = artist_credits[0]["artist"].get("id")
                        logger.debug(
                            "[PREFETCH_MB_ARTIST_ID_EXTRACT] Extracted mb_artist_id %s from prefetched_mb_data.artist-credit",
                            mb_artist_id_for_social_links,
                        )
                if not mb_artist_id_for_social_links:
                    logger.warning(
                        "[PREFETCH_MB_ARTIST_ID_EXTRACT] Could not extract musicbrainz_artist_id from prefetched MusicBrainz data. Prefetched data keys: %s",
                        list(prefetched_mb_data.keys()) if prefetched_mb_data else "None",  # Log keys for easier debug
                    )

        # --- Deezer Data Fetching (if not prefetched) ---
        if not is_deezer_data_prefetched:
            logger.info(
                "Deezer data not prefetched, calling _get_deezer_fallback_data for '%s' - '%s'",
                band_name,
                release_name,
            )
            # _get_deezer_fallback_data searches, fetches full raw details, and caches them.
            deezer_raw_album_details = await self._get_deezer_fallback_data(band_name, release_name)
            if (
                deezer_raw_album_details
                and isinstance(deezer_raw_album_details, dict)
                and deezer_raw_album_details.get("id")
            ):
                # We need to transform these raw details into the structure expected by _combine_metadata_from_sources
                # This is similar to what _transform_deezer_cached_data in helpers.py does.
                # Let's call it here directly for consistency.
                # Note: _transform_deezer_cached_data is async as of the last edit.
                transformed_deezer_data = await _transform_deezer_cached_data(deezer_raw_album_details, country_code)
                if transformed_deezer_data:
                    collected_data_for_sources["deezer"] = transformed_deezer_data
                    logger.info(
                        "Successfully fetched and transformed data from Deezer for '%s' - '%s'.",
                        band_name,
                        release_name,
                    )
                else:
                    logger.warning(
                        "Fetched Deezer data for '%s' - '%s', but failed to transform it.",
                        band_name,
                        release_name,
                    )
            else:
                logger.warning("No data found or incomplete data from Deezer for '%s' - '%s'.", band_name, release_name)
        else:
            logger.info("Skipping Deezer API fetch, using prefetched data for '%s' - '%s'.", band_name, release_name)

        # --- Fetch Artist Additional Data (Social Links, MB Artist Genres) ---
        # Uses mb_artist_id_for_social_links which should be populated if MB data (prefetched or fetched) is available.
        artist_social_links, artist_mb_genres = await self._fetch_artist_additional_data(mb_artist_id_for_social_links)

        # --- Combine all collected data ---
        logger.info("Combining metadata from available sources...")
        final_metadata = await self._combine_metadata_from_sources(
            band_name=band_name,
            release_name=release_name,
            spotify_release_summary=collected_data_for_sources["spotify"],
            musicbrainz_release_summary=collected_data_for_sources["musicbrainz"],
            mb_artist_id=mb_artist_id_for_social_links,  # Use the consistently derived MB artist ID
            is_mb_data_prefetched=is_musicbrainz_data_prefetched,  # Pass correct flag
            is_spotify_data_prefetched=is_spotify_data_prefetched,
            country_code=country_code,
            artist_social_links=artist_social_links,
            artist_mb_genres=artist_mb_genres,
            deezer_data=collected_data_for_sources["deezer"],
        )

        logger.info("Error stats for this request: %s", json.dumps(self.get_error_stats()))
        return final_metadata

    async def close(self) -> None:
        """Close all client connections."""
        tasks = []

        if hasattr(self._spotify, "close"):
            tasks.append(self._spotify.close())

        if hasattr(self._musicbrainz, "close"):
            tasks.append(self._musicbrainz.close())

        if hasattr(self._deezer, "close"):
            tasks.append(self._deezer.close())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Do not close the cache here as it's a global singleton
        # that should remain open for future requests

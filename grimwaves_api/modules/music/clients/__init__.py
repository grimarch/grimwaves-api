"""Clients package for external music metadata APIs.

This package contains client implementations for various external music
metadata APIs like Spotify, MusicBrainz, and Deezer.
"""

from grimwaves_api.modules.music.clients.deezer import DeezerClient
from grimwaves_api.modules.music.clients.musicbrainz import MusicBrainzClient
from grimwaves_api.modules.music.clients.spotify import SpotifyClient

__all__ = ["DeezerClient", "MusicBrainzClient", "SpotifyClient"]

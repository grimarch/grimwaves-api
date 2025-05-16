"""Constants and error codes for the music metadata module."""

import asyncio

from redis.exceptions import RedisError

from grimwaves_api.modules.music.schemas import RetryConfig

# Status codes for tasks
TASK_STATUS = {
    "PENDING": "PENDING",  # Task has been accepted but not yet started
    "QUEUED": "QUEUED",  # Task has been queued but not yet started
    "STARTED": "STARTED",  # Task has been started
    "SUCCESS": "SUCCESS",  # Task has completed successfully
    "FAILURE": "FAILURE",  # Task has failed
    "RETRY": "RETRY",  # Task is being retried
    "TIMEOUT": "TIMEOUT",  # Task has timed out
}

# Error codes for the music metadata module
ERROR_CODES = {
    "INVALID_REQUEST": "invalid_request",
    "TASK_NOT_FOUND": "task_not_found",
    "EXTERNAL_API_ERROR": "external_api_error",
    "SERVICE_UNAVAILABLE": "service_unavailable",
    "DATA_NOT_FOUND": "data_not_found",
    "RATE_LIMIT_EXCEEDED": "rate_limit_exceeded",
    "TIMEOUT": "timeout",
    "UNKNOWN_ERROR": "unknown_error",
}

# External API error message templates
ERROR_MESSAGES = {
    "SPOTIFY_AUTH_ERROR": "Failed to authenticate with Spotify API",
    "SPOTIFY_API_ERROR": "Error occurred while fetching data from Spotify API: {error}",
    "MUSICBRAINZ_API_ERROR": "Error occurred while fetching data from MusicBrainz API: {error}",
    "DEEZER_API_ERROR": "Error occurred while fetching data from Deezer API: {error}",
    "NO_RESULTS_FOUND": "No results found for the given search criteria",
    "INVALID_TASK_ID": "The provided task ID is invalid or does not exist",
    "TASK_FAILED": "The task failed with error: {error}",
    "RATE_LIMIT": "Rate limit exceeded for external API: {api_name}",
    "REQUEST_TIMEOUT": "Request to external API timed out: {api_name}",
}

# Cache keys and TTL
CACHE_TTL = {
    "DEFAULT": 3600,  # 1 hour
    "SPOTIFY_AUTH": 3000,  # 50 minutes (Spotify tokens last 1 hour)
    "RELEASE_METADATA": 86400,  # 24 hours
    "ARTIST_METADATA": 86400 * 7,  # 7 days
}

# API request retry configuration for HTTP clients
RETRY_CONFIG = {
    "DEFAULT": {
        "retries": 3,
        "backoff_factor": 0.5,
        "status_forcelist": [429, 500, 502, 503, 504],
    },
    "MUSICBRAINZ": {
        "retries": 2,
        "backoff_factor": 1.0,  # MusicBrainz prefers less frequent retries
        "status_forcelist": [429, 500, 502, 503, 504],
    },
}

# MusicBrainz relationship link types
LINK_TYPES = {
    "OFFICIAL_HOMEPAGE": "official homepage",
    "SOCIAL_NETWORK": "social network",
    "WIKIDATA": "wikidata",
    "BANDCAMP": "bandcamp",
    "SOUNDCLOUD": "soundcloud",
    "TWITTER": "twitter",
    "FACEBOOK": "facebook",
    "INSTAGRAM": "instagram",
    "YOUTUBE": "youtube",
    "VK": "vk",
}

# Social media URL patterns (for extraction and validation)
SOCIAL_MEDIA_PATTERNS = {
    "instagram": r"instagram\.com/([^/?]+)",
    "facebook": r"facebook\.com/([^/?]+)",
    "twitter": r"twitter\.com/([^/?]+)|x\.com/([^/?]+)",
    "youtube": r"youtube\.com/([^/?]+)",
    "vk": r"vk\.com/([^/?]+)",
}

# Exception categories for error handling
NETWORK_ERRORS = (ConnectionError, TimeoutError, asyncio.TimeoutError)
RESOURCE_ERRORS = (OSError, asyncio.CancelledError)
DATA_ERRORS = (ValueError, KeyError, TypeError, IndexError, AttributeError)
SYSTEM_ERRORS = (ImportError, RuntimeError, SystemError)
CACHE_ERRORS = (RedisError,)

# Event loop related errors for more specific handling
EVENT_LOOP_ERRORS = (RuntimeError,)
EVENT_LOOP_ERROR_MESSAGES = {
    "CLOSED_LOOP": "Event loop is closed",
    "WRONG_LOOP": "got Future attached to a different loop",
    "NO_LOOP": "No running event loop",
}

# Combined exception categories for convenience
ALL_HANDLED_ERRORS = NETWORK_ERRORS + RESOURCE_ERRORS + DATA_ERRORS + SYSTEM_ERRORS + CACHE_ERRORS

# Retry configurations for different error types
EVENT_LOOP_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=1.0,  # Quick 1-second retry for event loop errors
    use_exponential=False,
    use_jitter=False,
    max_delay=5.0,
    backoff_factor=1.0,  # Linear growth with no multiplier
)

NETWORK_RETRY_CONFIG = RetryConfig(
    max_retries=5,
    base_delay=2.0,
    use_exponential=True,
    use_jitter=True,
    max_delay=60.0,
    backoff_factor=2.0,  # Exponential backoff factor of 2
)

DATA_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=3.0,
    use_exponential=False,
    use_jitter=True,
    max_delay=15.0,
    backoff_factor=1.5,  # Moderate linear growth
)

DEFAULT_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=5.0,
    use_exponential=True,
    use_jitter=True,
    max_delay=30.0,
    backoff_factor=1.5,  # Moderate exponential growth
)

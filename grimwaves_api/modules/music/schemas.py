"""Pydantic models for music metadata module."""

import re
from enum import Enum
from typing import Any, override

from pydantic import BaseModel, Field, field_validator, model_validator


class TaskStatus(str, Enum):
    """Enum for task status values."""

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RETRY = "RETRY"
    TIMEOUT = "TIMEOUT"


class ReleaseMetadataRequest(BaseModel):
    """Request model for release metadata endpoint."""

    band_name: str = Field(..., min_length=1, max_length=200, description="Name of the artist or band")
    release_name: str = Field(..., min_length=1, max_length=200, description="Name of the release (album, EP, single)")
    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code (e.g. 'US', 'GB')",
    )
    prefetched_spotify_data: dict[str, Any] | None = Field(
        default=None,
        description="Optional prefetched Spotify data to avoid redundant API calls",
    )

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, v: str | None) -> str | None:
        """Validate and normalize country code to uppercase."""
        if v is None:
            return v
        return v.upper()


class ReleaseMetadataTaskParameters(BaseModel):
    """Parameters for the release metadata Celery task."""

    band_name: str = Field(..., min_length=1, max_length=200, description="Name of the artist or band")
    release_name: str = Field(..., min_length=1, max_length=200, description="Name of the release (album, EP, single)")
    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code (e.g. 'US', 'GB')",
    )
    prefetched_data_list: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional list of prefetched data from various sources, e.g., [{'source': 'spotify', 'data': {...}}]",
    )
    merged_cache_key_name: str | None = Field(
        default=None,
        description="The predictable cache key name for storing/retrieving the merged result.",
    )

    @field_validator("country_code")
    @classmethod
    def validate_country_code_task_params(cls, v: str | None) -> str | None:
        """Validate and normalize country code to uppercase."""
        if v is None:
            return v
        return v.upper()


class Track(BaseModel):
    """Model for track information."""

    title: str = Field(..., description="Track title")
    isrc: str | None = Field(default=None, description="International Standard Recording Code")
    position: int | None = Field(default=None, description="Track position in the release")
    duration_ms: int | None = Field(default=None, description="Track duration in milliseconds")
    source_specific_ids: dict[str, Any] | None = Field(
        default=None,
        description="Dictionary of source-specific IDs for the track (e.g., spotify_track_id)",
    )
    additional_details_track: dict[str, Any] | None = Field(
        default=None,
        description="Dictionary for any other source-specific track details (e.g., deezer_rank)",
    )


class ArtistSourceSpecificIds(BaseModel):
    """Source-specific IDs for an artist."""

    spotify_artist_id: str | None = Field(default=None, description="Spotify artist ID")
    musicbrainz_artist_id: str | None = Field(default=None, description="MusicBrainz artist ID")
    deezer_artist_id: str | None = Field(default=None, description="Deezer artist ID")


class ArtistInfoSchema(BaseModel):
    """Detailed information about an artist."""

    name: str = Field(..., description="Artist name")
    source_specific_ids: ArtistSourceSpecificIds | None = Field(
        default=None,
        description="Source-specific IDs for the artist",
    )
    # TODO: Consider adding other common artist fields if consistently available,
    # e.g., country, main_genre, disambiguation, sort_name.


class SocialLinks(BaseModel):
    """Social media links for an artist or band."""

    facebook: str | None = None
    twitter: str | None = None
    instagram: str | None = None
    vk: str | None = None
    website: str | None = None
    youtube: str | None = None

    @field_validator("facebook", "twitter", "instagram", "vk", "website", "youtube")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        """Validate that URLs are valid and use HTTPS protocol."""
        if v is None:
            return v

        if v.startswith("http://"):
            msg = "Only HTTPS URLs are allowed"
            raise ValueError(msg)

        # Simple regex to check URL format
        url_pattern = r"^https://[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)$"
        if not re.match(url_pattern, v):
            msg = f"Invalid URL format: {v}"
            raise ValueError(msg)

        return v

    @override
    def __str__(self) -> str:
        """Return a string representation of the social links."""
        return (
            f"SocialLinks(facebook={self.facebook}, twitter={self.twitter}, "
            f"instagram={self.instagram}, vk={self.vk}, website={self.website}, "
            f"youtube={self.youtube})"
        )


class ReleaseMetadataResponse(BaseModel):
    """Response model for release metadata."""

    artist: ArtistInfoSchema = Field(..., description="Detailed artist information")
    release: str = Field(..., description="Release name")
    release_date: str | None = Field(default=None, description="Release date in ISO format (YYYY-MM-DD)")
    label: str | None = Field(default=None, description="Record label")
    genre: list[str] = Field(default_factory=list, description="List of genres")
    tracks: list[Track] = Field(..., min_length=1, description="List of tracks")
    social_links: SocialLinks = Field(default_factory=SocialLinks, description="Artist's social media links")


class TaskResponse(BaseModel):
    """Response model for task submission."""

    task_id: str = Field(..., description="Unique identifier for the task")
    status: str = Field(..., description="Current status of the task")


class TaskStatusResponse(BaseModel):
    """Response model for task status check."""

    task_id: str = Field(..., description="Unique identifier for the task")
    status: TaskStatus = Field(..., description="Current status of the task")
    result: ReleaseMetadataResponse | None = Field(
        default=None,
        description="Task result data if available",
    )
    error: str | None = Field(default=None, description="Error message if task failed")


class TaskResult(BaseModel):
    """Model for task execution result."""

    status: TaskStatus = Field(..., description="Task execution status")
    result: ReleaseMetadataResponse | None = Field(
        default=None,
        description="Task result data if successful",
    )
    error: str | None = Field(default=None, description="Error message if task failed")
    error_type: str | None = Field(default=None, description="Type of exception if task failed")

    @model_validator(mode="after")
    def validate_status_and_fields(self) -> "TaskResult":
        """Validate that the appropriate fields are set based on status."""
        if self.status == TaskStatus.SUCCESS and not self.result:
            msg = "Result is required for successful tasks"
            raise ValueError(msg)
        if self.status == TaskStatus.FAILURE and not self.error:
            msg = "Error message is required for failed tasks"
            raise ValueError(msg)
        if self.status in (TaskStatus.PENDING, TaskStatus.STARTED) and (self.result or self.error):
            msg = "Pending or started tasks should not have result or error"
            raise ValueError(msg)
        return self


class ErrorResponse(BaseModel):
    """Response model for errors."""

    status: str = Field("error", description="Error status")
    error_code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")


class RetryConfig(BaseModel):
    """Configuration for retry strategies.

    This model defines the parameters for a retry strategy, including
    backoff behavior, jitter, and maximum retry attempts.
    """

    max_retries: int = Field(..., description="Maximum number of retries to attempt")
    base_delay: float = Field(..., description="Base delay in seconds")
    use_exponential: bool = Field(..., description="Whether to use exponential backoff")
    use_jitter: bool = Field(..., description="Whether to add jitter to delay")
    max_delay: float = Field(..., description="Maximum delay in seconds (to cap exponential growth)")
    backoff_factor: float = Field(..., description="Factor to multiply retry count by when calculating delay")

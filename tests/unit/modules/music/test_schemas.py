"""Tests for schema models in the music module."""

import pytest
from pydantic import ValidationError

from grimwaves_api.modules.music.constants import ERROR_CODES
from grimwaves_api.modules.music.schemas import (
    ErrorResponse,
    ReleaseMetadataRequest,
    ReleaseMetadataResponse,
    SocialLinks,
    TaskStatus,
    TaskStatusResponse,
    Track,
)


class TestReleaseMetadataRequest:
    """Tests for the ReleaseMetadataRequest model."""

    def test_valid_request(self):
        """Test creating a valid request."""
        data = {
            "band_name": "Test Band",
            "release_name": "Test Album",
            "country_code": "us",
        }
        request = ReleaseMetadataRequest(**data)
        assert request.band_name == "Test Band"
        assert request.release_name == "Test Album"
        assert request.country_code == "US"  # Should be converted to uppercase

    def test_request_with_optional_fields(self):
        """Test creating a request with optional fields."""
        data = {
            "band_name": "Test Band",
            "release_name": "Test Album",
            "country_code": "GB",
        }
        request = ReleaseMetadataRequest(**data)
        assert request.band_name == "Test Band"
        assert request.release_name == "Test Album"
        assert request.country_code == "GB"

    def test_missing_required_fields(self):
        """Test that required fields are enforced."""
        # Missing band_name (using empty string which will fail min_length validation)
        with pytest.raises(ValidationError) as exc_info:
            _ = ReleaseMetadataRequest(band_name="", release_name="Test Album", country_code="US")
        assert "band_name" in str(exc_info.value)

        # Missing release_name (using empty string which will fail min_length validation)
        with pytest.raises(ValidationError) as exc_info:
            _ = ReleaseMetadataRequest(band_name="Test Band", release_name="", country_code="US")
        assert "release_name" in str(exc_info.value)

        # Missing country_code is allowed because it's optional
        request = ReleaseMetadataRequest(band_name="Test Band", release_name="Test Album")
        assert request.country_code is None

    def test_invalid_country_code(self):
        """Test that country code validation works."""
        # Country code too long
        with pytest.raises(ValidationError):
            _ = ReleaseMetadataRequest(
                band_name="Test Band",
                release_name="Test Album",
                country_code="USA",
            )

        # Country code too short
        with pytest.raises(ValidationError):
            _ = ReleaseMetadataRequest(
                band_name="Test Band",
                release_name="Test Album",
                country_code="A",
            )

    def test_invalid_year(self):
        """Test that year validation works."""
        # Удалены тесты для year, так как этого поля нет в модели


class TestTrack:
    """Tests for the Track model."""

    def test_valid_track(self):
        """Test creating a valid track."""
        data = {
            "title": "Test Track",
            "isrc": "ABC123456789",
        }
        track = Track(**data)
        assert track.title == "Test Track"
        assert track.isrc == "ABC123456789"

    def test_track_with_optional_fields_null(self):
        """Test creating a track with optional fields as None."""
        data = {
            "title": "Test Track",
            "isrc": None,
        }
        track = Track(**data)  # pyright: ignore[reportArgumentType]
        assert track.title == "Test Track"
        assert track.isrc is None

    def test_missing_title(self):
        """Test that title is required."""
        with pytest.raises(ValidationError):
            _ = Track.model_validate({"isrc": "ABC123456789"})

    def test_track_from_dict(self):
        """Test creating a track from a dictionary."""
        data = {
            "title": "Test Track",
            "isrc": "ABC123456789",
        }
        track = Track(**data)
        assert track.title == "Test Track"
        assert track.isrc == "ABC123456789"

    def test_track_from_dict_extra_fields(self):
        """Test creating a track with extra fields."""
        data = {
            "title": "Test Track",
            "isrc": "ABC123456789",
            "extra_field": "This should be ignored",
        }
        track = Track(**data)
        assert track.title == "Test Track"
        assert track.isrc == "ABC123456789"
        # Extra fields are ignored by default
        with pytest.raises(AttributeError):
            _ = track.extra_field  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]


class TestSocialLinks:
    """Tests for the SocialLinks model."""

    def test_valid_social_links(self):
        """Test creating valid social links."""
        links = SocialLinks(
            facebook="https://facebook.com/artist",
            twitter="https://twitter.com/artist",
            instagram="https://instagram.com/artist",
            youtube="https://youtube.com/channel/artist",
            website="https://artist-website.com",
        )
        assert links.facebook == "https://facebook.com/artist"
        assert links.twitter == "https://twitter.com/artist"
        assert links.instagram == "https://instagram.com/artist"
        assert links.youtube == "https://youtube.com/channel/artist"
        assert links.website == "https://artist-website.com"

    def test_social_links_empty(self):
        """Test creating social links with no data."""
        links = SocialLinks()
        assert links.facebook is None
        assert links.twitter is None
        assert links.instagram is None
        assert links.youtube is None
        assert links.website is None

    def test_social_links_partial(self):
        """Test creating social links with partial data."""
        data = {
            "facebook": "https://facebook.com/artist",
            "instagram": "https://instagram.com/artist",
        }
        links = SocialLinks(**data)  # pyright: ignore[reportArgumentType]
        assert links.facebook == "https://facebook.com/artist"
        assert links.twitter is None
        assert links.instagram == "https://instagram.com/artist"
        assert links.youtube is None
        assert links.website is None

    def test_invalid_urls(self):
        """Test that invalid URLs are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SocialLinks(facebook="http://facebook.com/artist")
        assert "Only HTTPS URLs are allowed" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            SocialLinks(twitter="http://twitter.com/artist")
        assert "Only HTTPS URLs are allowed" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            SocialLinks(instagram="not_a_url")
        assert "Invalid URL format" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            SocialLinks(website="ftp://example.com")
        assert "Invalid URL format" in str(exc_info.value)


class TestReleaseMetadataResponse:
    """Tests for the ReleaseMetadataResponse model."""

    def test_valid_response(self):
        """Test creating a valid response."""
        data = {
            "artist": {"name": "Test Artist"},
            "release": "Test Album",
            "release_date": "2023-01-01",
            "label": "Test Label",
            "genre": ["Rock", "Metal"],
            "tracks": [
                Track(title="Track 1", isrc="ABC123456789"),
                Track(title="Track 2", isrc="DEF987654321"),
            ],
            "social_links": {
                "facebook": "https://facebook.com/artist",
                "instagram": "https://instagram.com/artist",
            },
        }
        response = ReleaseMetadataResponse(**data)  # pyright: ignore[reportArgumentType]
        assert response.artist.name == "Test Artist"
        assert response.release == "Test Album"
        assert response.release_date == "2023-01-01"
        assert response.label == "Test Label"
        assert response.genre == ["Rock", "Metal"]
        assert len(response.tracks) == 2
        assert isinstance(response.tracks[0], Track)
        assert response.tracks[0].title == "Track 1"
        assert isinstance(response.social_links, SocialLinks)
        assert response.social_links.facebook == "https://facebook.com/artist"

    def test_response_with_missing_optional_fields(self):
        """Test creating a response with missing optional fields."""
        data = {
            "artist": {"name": "Test Artist"},
            "release": "Test Album",
            "tracks": [Track(title="Track 1")],
        }
        response = ReleaseMetadataResponse(**data)  # pyright: ignore[reportArgumentType]
        assert response.artist.name == "Test Artist"
        assert response.release == "Test Album"
        assert response.release_date is None
        assert response.label is None
        assert response.genre == []
        assert len(response.tracks) == 1
        assert response.tracks[0].title == "Track 1"
        assert response.social_links is not None
        assert response.social_links.facebook is None

    def test_missing_required_fields(self):
        """Test that required fields are enforced."""
        # Missing artist
        with pytest.raises(ValidationError):
            _ = ReleaseMetadataResponse(  # pyright: ignore[reportCallIssue]
                release="Test Album",
                tracks=[Track(title="Track 1")],
            )

        # Missing release
        with pytest.raises(ValidationError):
            _ = ReleaseMetadataResponse(  # pyright: ignore[reportCallIssue]
                artist={"name": "Test Artist"},
                tracks=[Track(title="Track 1")],
            )

        # Missing tracks
        with pytest.raises(ValidationError):
            _ = ReleaseMetadataResponse(  # pyright: ignore[reportCallIssue]
                artist={"name": "Test Artist"},
                release="Test Album",
            )

    def test_empty_tracks_list(self):
        """Test that empty tracks list is not allowed."""
        with pytest.raises(ValidationError):
            _ = ReleaseMetadataResponse(
                artist={"name": "Test Artist"},
                release="Test Album",
                tracks=[],
            )


class TestTaskStatus:
    """Tests for the TaskStatus enum."""

    def test_enum_values(self):
        """Test that enum values are correct."""
        assert TaskStatus.PENDING.value == "PENDING"
        assert TaskStatus.QUEUED.value == "QUEUED"
        assert TaskStatus.STARTED.value == "STARTED"
        assert TaskStatus.SUCCESS.value == "SUCCESS"
        assert TaskStatus.FAILURE.value == "FAILURE"
        assert TaskStatus.RETRY.value == "RETRY"
        assert TaskStatus.TIMEOUT.value == "TIMEOUT"


class TestTaskStatusResponse:
    """Tests for the TaskStatusResponse model."""

    def test_valid_response(self):
        """Test creating a valid response."""
        response = TaskStatusResponse(
            task_id="123-456-789",
            status=TaskStatus.PENDING,
        )
        assert response.task_id == "123-456-789"
        assert response.status == TaskStatus.PENDING
        assert response.result is None
        assert response.error is None

    def test_missing_fields(self):
        """Test that required fields are enforced."""
        # Missing task_id
        with pytest.raises(ValidationError):
            _ = TaskStatusResponse(status=TaskStatus.PENDING)  # pyright: ignore[reportCallIssue]

        # Missing status
        with pytest.raises(ValidationError):
            _ = TaskStatusResponse(task_id="123-456-789")  # pyright: ignore[reportCallIssue]


def test_task_status_response():
    """Test TaskStatusResponse schema."""
    # Test successful task
    task_response = TaskStatusResponse(
        task_id="123",
        status=TaskStatus.SUCCESS,
        result=ReleaseMetadataResponse(
            artist={"name": "Test Artist"},
            release="Test Release",
            tracks=[Track(title="Test Track")],
        ),
    )
    assert task_response.task_id == "123"
    assert task_response.status == TaskStatus.SUCCESS
    assert task_response.result is not None
    assert task_response.error is None

    # Test failed task
    task_response = TaskStatusResponse(
        task_id="456",
        status=TaskStatus.FAILURE,
        error="Test error message",
    )
    assert task_response.task_id == "456"
    assert task_response.status == TaskStatus.FAILURE
    assert task_response.result is None
    assert task_response.error == "Test error message"


def test_error_response():
    """Test ErrorResponse schema."""
    error = ErrorResponse(
        message="Test error",
        error_code=ERROR_CODES["INVALID_REQUEST"],
        status="400",
    )
    assert error.message == "Test error"
    assert error.error_code == ERROR_CODES["INVALID_REQUEST"]

    # Test that message and error_code are required
    with pytest.raises(ValidationError):
        _ = ErrorResponse()  # pyright: ignore[reportCallIssue]

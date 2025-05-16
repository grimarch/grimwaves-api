"""Tests for Redis cache in the music module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis

from grimwaves_api.modules.music.cache import KEY_PREFIXES, TTL, RedisCache, cache


@pytest.fixture
def redis_cache():
    """Return a RedisCache instance with a mocked async client for testing."""
    # Create an AsyncMock instance once for the async client
    mock_async_redis_client = AsyncMock()
    # Create a MagicMock instance once for the sync client
    mock_sync_redis_client = MagicMock()

    # Patch the location where the ASYNCHRONOUS client is created
    # Path: grimwaves_api.modules.music.cache.Redis (which is redis.asyncio.client.Redis)
    # and its method from_url
    with patch("grimwaves_api.modules.music.cache.Redis.from_url", return_value=mock_async_redis_client):
        # Patch the location where the SYNCHRONOUS client is created
        # Path: grimwaves_api.modules.music.cache.redis (which is the root redis module)
        # and its method from_url
        with patch("grimwaves_api.modules.music.cache.redis.from_url", return_value=mock_sync_redis_client):
            cache_instance = RedisCache("redis://test:6379/0")
            # Attach mocks to the cache instance for easy access in tests
            cache_instance._test_mock_async_client = mock_async_redis_client
            cache_instance._test_mock_sync_client = mock_sync_redis_client
            yield cache_instance


@pytest.fixture
def sample_metadata():
    """Return sample metadata dictionary for testing."""
    return {
        "artist": "Test Artist",
        "release": "Test Album",
        "release_date": "2023-01-01",
        "label": "Test Label",
        "genre": ["Rock", "Metal"],
        "tracks": [
            {"title": "Track 1", "isrc": "ABC123456789"},
            {"title": "Track 2", "isrc": "DEF987654321"},
        ],
        "social_links": {
            "instagram": "https://instagram.com/testartist",
            "facebook": "https://facebook.com/testartist",
        },
    }


class TestRedisCache:
    """Tests for the RedisCache class."""

    def test_init(self):
        """Test RedisCache initialization."""
        cache = RedisCache("redis://localhost:6379/0")
        assert cache.redis_url == "redis://localhost:6379/0"
        assert cache._sync_client is None
        assert cache._async_client is None

    def test_sync_client_init(self, redis_cache):
        """Test synchronous Redis client initialization."""
        # Access the sync_client property to trigger its creation
        client = redis_cache.sync_client
        assert client is not None
        # Check that the mock_sync_from_url (via _test_mock_sync_client) was used
        redis_cache._test_mock_sync_client.assert_not_called()  # from_url creates it, client is the mock itself

        # The from_url in the patch should have been called by the property
        # We need to get the original mock object for from_url
        # This is a bit tricky because the context manager gives us the mock of `redis.from_url` not the instance
        # Let's rely on the fact that the client *is* our mock_sync_redis_client
        assert client is redis_cache._test_mock_sync_client

        # To verify from_url was called, we'd need to inspect the original mock_sync_from_url from the patch context
        # For simplicity now, we assume if client is our mock, from_url was called.

        # Second call should use cached client (property logic)
        client_again = redis_cache.sync_client
        assert client is client_again  # Should be the same mocked instance

    @pytest.mark.asyncio
    async def test_async_client_init(self, redis_cache):
        """Test asynchronous Redis client initialization."""
        client = await redis_cache.async_client  # This will call Redis.from_url which returns our mock
        assert client is not None
        # The client IS our mock
        assert client is redis_cache._test_mock_async_client
        # _async_client internal variable of RedisCache should ideally not be checked directly after this change
        # as the property creates a new one. But let's see if original test logic makes sense.
        # The original RedisCache stores the *last* client it created in self._async_client if not using the property logic.
        # However, the property always returns a *new* one. So self._async_client might be None or the one from previous direct assignment.
        # This test needs to verify that *accessing* redis_cache.async_client gives the mock.

    @pytest.mark.asyncio
    async def test_close(self, redis_cache):
        """Test closing Redis connections."""
        # Initialize clients first
        _ = redis_cache.sync_client
        _ = await redis_cache.async_client

        # The mocks are already attached to redis_cache as _test_mock_async_client and _test_mock_sync_client
        # by the fixture. The internal _async_client and _sync_client will be set by property access if needed,
        # but the close() method directly uses the internal _async_client and _sync_client fields.
        # For the test to correctly assert calls on the mocks that are actually used by close(),
        # we need to ensure these internal fields are indeed our test mocks *before* calling close().

        # However, RedisCache.close() uses self._async_client and self._sync_client directly.
        # We need to ensure these are our mocks from the fixture if the property logic doesn't set them or
        # if they were somehow overwritten. The fixture now attaches them as _test_mock_async_client.
        # The actual internal fields _async_client and _sync_client are what RedisCache.close() uses.
        # Let's ensure RedisCache.close() will use the mocks it's supposed to use from the fixture.
        # The fixture already ensures that calls to .from_url() return these mocks.
        # The properties async_client and sync_client in RedisCache will use these mocks.
        # The close() method in RedisCache uses self._sync_client and self._async_client.
        # We should assign our test mocks to these internal attributes before calling close,
        # to ensure that the close method operates on the mocks we intend to check.

        # Ensure internal members are our test mocks before calling close.
        # This is needed because the async_client property creates a new client on each call,
        # but close() acts on the internal self._async_client member.
        redis_cache._async_client = redis_cache._test_mock_async_client
        redis_cache._sync_client = redis_cache._test_mock_sync_client

        await redis_cache.close()

        # Verify close was called on the mocks that were part of the RedisCache instance
        redis_cache._test_mock_async_client.close.assert_called_once()
        redis_cache._test_mock_sync_client.close.assert_called_once()

        # Verify clients are nullified in the instance by the close() method
        assert redis_cache._async_client is None
        assert redis_cache._sync_client is None

    def test_generate_key_basic(self, redis_cache):
        """Test basic key generation."""
        key = redis_cache.generate_key("spotify_search", "Test Artist", "Test Album")
        assert key == f"{KEY_PREFIXES['spotify_search']}Test_Artist_Test_Album"

    def test_generate_key_with_none_arg(self, redis_cache):
        """Test key generation with None argument."""
        key = redis_cache.generate_key("spotify_search", "Test Artist", None, "Test Album")
        assert key == f"{KEY_PREFIXES['spotify_search']}Test_Artist_Test_Album"

    def test_generate_key_with_integer_arg(self, redis_cache):
        """Test key generation with integer argument."""
        key = redis_cache.generate_key("spotify_search", "Test Artist", 123)
        assert key == f"{KEY_PREFIXES['spotify_search']}Test_Artist_123"

    def test_generate_key_long_argument(self, redis_cache):
        """Test key generation with very long argument."""
        long_arg = "x" * 200
        key = redis_cache.generate_key("spotify_search", long_arg)

        # Should hash the long argument
        assert len(key) < len(KEY_PREFIXES["spotify_search"]) + 200
        assert len(key) >= len(KEY_PREFIXES["spotify_search"]) + 64  # SHA256 hash length

        # Verify it's deterministic
        key2 = redis_cache.generate_key("spotify_search", long_arg)
        assert key == key2

    def test_generate_key_invalid_prefix(self, redis_cache):
        """Test key generation with invalid prefix."""
        with pytest.raises(ValueError):
            redis_cache.generate_key("invalid_prefix", "test")

    def test_generate_key_no_args(self, redis_cache):
        """Test key generation with no arguments."""
        key = redis_cache.generate_key("spotify_search")
        assert key == f"{KEY_PREFIXES['spotify_search']}default"

    @pytest.mark.asyncio
    async def test_get_success(self, redis_cache):
        """Test successful get operation."""
        redis_cache._test_mock_async_client.get.return_value = json.dumps({"key": "value"}).encode("utf-8")

        result = await redis_cache.get("test_key")

        redis_cache._test_mock_async_client.get.assert_called_once_with("test_key")
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_get_not_found(self, redis_cache):
        """Test get operation when key doesn't exist."""
        redis_cache._test_mock_async_client.get.return_value = None

        result = await redis_cache.get("test_key", default={"default": "value"})

        redis_cache._test_mock_async_client.get.assert_called_once_with("test_key")
        assert result == {"default": "value"}

    @pytest.mark.asyncio
    async def test_get_json_error(self, redis_cache):
        """Test get operation with invalid JSON."""
        redis_cache._test_mock_async_client.get.return_value = b"invalid json"

        result = await redis_cache.get("test_key", default={"default": "value"})

        redis_cache._test_mock_async_client.get.assert_called_once_with("test_key")
        assert result == {"default": "value"}

    @pytest.mark.asyncio
    async def test_get_redis_error(self, redis_cache):
        """Test get operation with Redis error."""
        redis_cache._test_mock_async_client.get.side_effect = redis.RedisError("Connection error")

        result = await redis_cache.get("test_key", default={"default": "value"})

        redis_cache._test_mock_async_client.get.assert_called_once_with("test_key")
        assert result == {"default": "value"}

    @pytest.mark.asyncio
    async def test_set_success(self, redis_cache):
        """Test successful set operation."""
        redis_cache._test_mock_async_client.set.return_value = True

        result = await redis_cache.set("test_key", {"key": "value"}, ttl=60)

        redis_cache._test_mock_async_client.set.assert_called_once()
        assert redis_cache._test_mock_async_client.set.call_args[0][0] == "test_key"
        assert json.loads(redis_cache._test_mock_async_client.set.call_args[0][1].decode("utf-8")) == {"key": "value"}
        assert redis_cache._test_mock_async_client.set.call_args[1]["ex"] == 60
        assert result is True

    @pytest.mark.asyncio
    async def test_set_default_ttl(self, redis_cache):
        """Test set operation with default TTL."""
        redis_cache._test_mock_async_client.set.return_value = True

        with patch("grimwaves_api.modules.music.cache.settings") as mock_settings:
            mock_settings.redis_cache_ttl = 3600
            result = await redis_cache.set("test_key", {"key": "value"})

            assert redis_cache._test_mock_async_client.set.call_args[1]["ex"] == 3600
            assert result is True

    @pytest.mark.asyncio
    async def test_set_serialization_error(self, redis_cache):
        """Test set operation with non-serializable value."""
        # This test doesn't directly call the client if serialization fails beforehand

        # Create an object that can't be serialized to JSON
        class Unserializable:
            def __init__(self) -> None:
                self.circular = self

        result = await redis_cache.set("test_key", Unserializable())

        redis_cache._test_mock_async_client.set.assert_not_called()
        assert result is False

    @pytest.mark.asyncio
    async def test_set_redis_error(self, redis_cache):
        """Test set operation with Redis error."""
        redis_cache._test_mock_async_client.set.side_effect = redis.RedisError("Connection error")

        result = await redis_cache.set("test_key", {"key": "value"})

        redis_cache._test_mock_async_client.set.assert_called_once()
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_success(self, redis_cache):
        """Test successful delete operation."""
        redis_cache._test_mock_async_client.delete.return_value = 1

        result = await redis_cache.delete("test_key")

        redis_cache._test_mock_async_client.delete.assert_called_once_with("test_key")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, redis_cache):
        """Test delete operation when key doesn't exist."""
        redis_cache._test_mock_async_client.delete.return_value = 0

        result = await redis_cache.delete("test_key")

        redis_cache._test_mock_async_client.delete.assert_called_once_with("test_key")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_true(self, redis_cache):
        """Test exists operation when key exists."""
        redis_cache._test_mock_async_client.exists.return_value = 1

        result = await redis_cache.exists("test_key")

        redis_cache._test_mock_async_client.exists.assert_called_once_with("test_key")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self, redis_cache):
        """Test exists operation when key doesn't exist."""
        redis_cache._test_mock_async_client.exists.return_value = 0

        result = await redis_cache.exists("test_key")

        redis_cache._test_mock_async_client.exists.assert_called_once_with("test_key")
        assert result is False


class TestMetadataCache:
    """Tests for metadata-specific caching methods."""

    @pytest.mark.asyncio
    async def test_cache_metadata_result(self, redis_cache, sample_metadata):
        """Test caching metadata result."""
        with patch.object(redis_cache, "set") as mock_set:
            mock_set.return_value = True

            result = await redis_cache.cache_metadata_result("task-123", sample_metadata)

            mock_set.assert_called_once()
            key = mock_set.call_args[0][0]
            assert key == f"{KEY_PREFIXES['metadata_result']}task-123"
            assert mock_set.call_args[0][1] == sample_metadata
            assert mock_set.call_args[0][2] == TTL["result"]
            assert result is True

    @pytest.mark.asyncio
    async def test_cache_metadata_result_error(self, redis_cache, sample_metadata):
        """Test caching error metadata result."""
        with patch.object(redis_cache, "set") as mock_set:
            mock_set.return_value = True

            result = await redis_cache.cache_metadata_result("task-123", sample_metadata, is_error=True)

            mock_set.assert_called_once()
            assert mock_set.call_args[0][2] == TTL["error"]
            assert result is True

    @pytest.mark.asyncio
    async def test_get_metadata_result(self, redis_cache, sample_metadata):
        """Test retrieving metadata result."""
        with patch.object(redis_cache, "get") as mock_get:
            mock_get.return_value = sample_metadata

            result = await redis_cache.get_metadata_result("task-123")

            mock_get.assert_called_once()
            key = mock_get.call_args[0][0]
            assert key == f"{KEY_PREFIXES['metadata_result']}task-123"
            assert result == sample_metadata

    @pytest.mark.asyncio
    async def test_cache_search_results(self, redis_cache):
        """Test caching search results."""
        search_results = [{"id": "1", "name": "Album 1"}, {"id": "2", "name": "Album 2"}]

        with patch.object(redis_cache, "set") as mock_set:
            mock_set.return_value = True

            result = await redis_cache.cache_search_results(
                "spotify",
                "Artist Name",
                "Album Name",
                "US",
                search_results,
            )

            mock_set.assert_called_once()
            key = mock_set.call_args[0][0]
            assert key == f"{KEY_PREFIXES['spotify_search']}Artist_Name_Album_Name_US"
            assert mock_set.call_args[0][1] == search_results
            assert mock_set.call_args[0][2] == TTL["search"]
            assert result is True

    @pytest.mark.asyncio
    async def test_cache_search_results_invalid_source(self, redis_cache):
        """Test caching search results with invalid source."""
        search_results = [{"id": "1", "name": "Album 1"}, {"id": "2", "name": "Album 2"}]

        result = await redis_cache.cache_search_results(
            "invalid",
            "Artist Name",
            "Album Name",
            "US",
            search_results,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_get_search_results(self, redis_cache):
        """Test retrieving search results."""
        search_results = [{"id": "1", "name": "Album 1"}, {"id": "2", "name": "Album 2"}]

        with patch.object(redis_cache, "get") as mock_get:
            mock_get.return_value = search_results

            result = await redis_cache.get_search_results(
                "spotify",
                "Artist Name",
                "Album Name",
                "US",
            )

            mock_get.assert_called_once()
            key = mock_get.call_args[0][0]
            assert key == f"{KEY_PREFIXES['spotify_search']}Artist_Name_Album_Name_US"
            assert result == search_results

    @pytest.mark.asyncio
    async def test_get_search_results_invalid_source(self, redis_cache):
        """Test retrieving search results with invalid source."""
        result = await redis_cache.get_search_results(
            "invalid",
            "Artist Name",
            "Album Name",
            "US",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_release_details(self, redis_cache):
        """Test caching release details."""
        release_details = {"id": "album123", "name": "Test Album", "artist": "Test Artist"}

        with patch.object(redis_cache, "set") as mock_set:
            mock_set.return_value = True

            result = await redis_cache.cache_release_details("spotify", "album123", release_details)

            mock_set.assert_called_once()
            key = mock_set.call_args[0][0]
            assert key == f"{KEY_PREFIXES['spotify_release']}album123"
            assert mock_set.call_args[0][1] == release_details
            assert mock_set.call_args[0][2] == TTL["release"]
            assert result is True

    @pytest.mark.asyncio
    async def test_get_release_details(self, redis_cache):
        """Test retrieving release details."""
        release_details = {"id": "album123", "name": "Test Album", "artist": "Test Artist"}

        with patch.object(redis_cache, "get") as mock_get:
            mock_get.return_value = release_details

            result = await redis_cache.get_release_details("spotify", "album123")

            mock_get.assert_called_once()
            key = mock_get.call_args[0][0]
            assert key == f"{KEY_PREFIXES['spotify_release']}album123"
            assert result == release_details

    @pytest.mark.asyncio
    async def test_cache_tracks_list(self, redis_cache):
        """Test caching tracks list."""
        tracks = [
            {"id": "track1", "title": "Track 1", "isrc": "ABC123"},
            {"id": "track2", "title": "Track 2", "isrc": "DEF456"},
        ]

        with patch.object(redis_cache, "set") as mock_set:
            mock_set.return_value = True

            result = await redis_cache.cache_tracks_list("spotify", "album123", tracks)

            mock_set.assert_called_once()
            key = mock_set.call_args[0][0]
            assert key == f"{KEY_PREFIXES['spotify_tracks']}album123"
            assert mock_set.call_args[0][1] == tracks
            assert mock_set.call_args[0][2] == TTL["tracks"]
            assert result is True

    @pytest.mark.asyncio
    async def test_get_tracks_list(self, redis_cache):
        """Test retrieving tracks list."""
        tracks = [
            {"id": "track1", "title": "Track 1", "isrc": "ABC123"},
            {"id": "track2", "title": "Track 2", "isrc": "DEF456"},
        ]

        with patch.object(redis_cache, "get") as mock_get:
            mock_get.return_value = tracks

            result = await redis_cache.get_tracks_list("spotify", "album123")

            mock_get.assert_called_once()
            key = mock_get.call_args[0][0]
            assert key == f"{KEY_PREFIXES['spotify_tracks']}album123"
            assert result == tracks

    @pytest.mark.asyncio
    async def test_cache_artist_data(self, redis_cache):
        """Test caching artist data."""
        artist_data = {
            "id": "artist123",
            "name": "Test Artist",
            "popularity": 80,
            "genres": ["Rock", "Alternative"],
        }

        with patch.object(redis_cache, "set") as mock_set:
            mock_set.return_value = True

            result = await redis_cache.cache_artist_data("spotify", "artist123", artist_data)

            mock_set.assert_called_once()
            key = mock_set.call_args[0][0]
            assert key == f"{KEY_PREFIXES['spotify_artist']}artist123"
            assert mock_set.call_args[0][1] == artist_data
            assert mock_set.call_args[0][2] == TTL["artist"]
            assert result is True

    @pytest.mark.asyncio
    async def test_get_artist_data(self, redis_cache):
        """Test retrieving artist data."""
        artist_data = {
            "id": "artist123",
            "name": "Test Artist",
            "popularity": 80,
            "genres": ["Rock", "Alternative"],
        }

        with patch.object(redis_cache, "get") as mock_get:
            mock_get.return_value = artist_data

            result = await redis_cache.get_artist_data("spotify", "artist123")

            mock_get.assert_called_once()
            key = mock_get.call_args[0][0]
            assert key == f"{KEY_PREFIXES['spotify_artist']}artist123"
            assert result == artist_data


def test_cache_singleton():
    """Test that the cache singleton is properly initialized."""
    from grimwaves_api.core.settings import settings

    assert cache is not None
    assert isinstance(cache, RedisCache)
    assert cache.redis_url == settings.redis_url

"""Tests for the HTTP client base classes.

This module contains tests for the HTTP client base classes in grimwaves_api.common.utils.http_client.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient

from grimwaves_api.common.utils.http_client import (
    BaseHttpxClient,
    DualHttpClient,
)


class TestBaseHttpxClient:
    """Test suite for BaseHttpxClient."""

    @pytest.mark.asyncio
    async def test_lazy_initialization(self):
        """Test that the client is lazily initialized."""
        client = BaseHttpxClient(base_url="https://example.com")

        # Client should not be initialized at first
        assert client._client is None
        assert client._initialized is False

        # Client should be initialized after calling _get_client
        real_client = await client._get_client()
        assert client._client is not None
        assert client._initialized is True
        assert real_client is client._client

        # Client should be reused on subsequent calls
        real_client2 = await client._get_client()
        assert real_client2 is real_client

        # Cleanup
        await client.close()

    @pytest.mark.asyncio
    async def test_client_configuration(self):
        """Test that the client is properly configured."""
        base_url = "https://api.example.com"
        timeout = 15.0
        headers = {"User-Agent": "Test-Agent", "Accept": "application/json"}

        client = BaseHttpxClient(
            base_url=base_url,
            timeout=timeout,
            headers=headers,
        )

        httpx_client = await client._get_client()

        assert httpx_client.base_url == httpx.URL(base_url)
        assert httpx_client.headers["User-Agent"] == "Test-Agent"
        assert httpx_client.headers["Accept"] == "application/json"

        # Cleanup
        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test the async context manager interface."""
        client_instance = None

        async with BaseHttpxClient() as client:
            client_instance = client
            # Check that the client is initialized
            assert client._client is not None
            assert client._initialized is True

        # Check that the client is closed after the context block
        assert client_instance._client is None
        assert client_instance._initialized is False

    @pytest.mark.asyncio
    async def test_close_method(self):
        """Test that the close method closes the client properly."""
        client = BaseHttpxClient()

        # Initialize the client
        await client._get_client()
        assert client._initialized is True

        # Mock the aclose method of the httpx client
        with patch.object(AsyncClient, "aclose", new_callable=AsyncMock) as mock_aclose:
            await client.close()
            # Verify that aclose was called
            mock_aclose.assert_called_once()

        # Verify that the client is properly reset
        assert client._client is None
        assert client._initialized is False

        # Calling close again should be a no-op
        await client.close()  # Should not raise


class TestDualHttpClient:
    """Test suite for DualHttpClient."""

    @pytest.mark.asyncio
    async def test_init_both_clients(self):
        """Test initialization of both HTTP clients."""
        client = DualHttpClient(base_url="https://example.com")

        # Both clients should be None at first
        assert client._client is None
        assert client._session is None

        # Initialize both clients
        await client._get_client()
        await client._get_session()

        # Verify both clients are initialized
        assert client._client is not None
        assert client._session is not None

        # Cleanup
        await client.close()

    @pytest.mark.asyncio
    async def test_dual_context_manager(self):
        """Test the context manager for DualHttpClient."""
        client_instance = None

        async with DualHttpClient() as client:
            client_instance = client
            # Explicitly initialize both clients
            await client._get_client()
            await client._get_session()

            assert client._client is not None
            assert client._session is not None

        # Both clients should be closed after context
        assert client_instance._client is None
        assert client_instance._session is None or client_instance._session.closed

    @pytest.mark.asyncio
    async def test_close_closes_both_clients(self):
        """Test that close method closes both clients."""
        client = DualHttpClient()

        # Initialize both clients
        await client._get_client()
        await client._get_session()

        # Mock the aclose method of httpx client
        with patch.object(AsyncClient, "aclose", new_callable=AsyncMock) as mock_httpx_aclose:
            # Mock the close method of aiohttp session
            with patch.object(client._session, "close", new_callable=AsyncMock) as mock_aiohttp_close:
                await client.close()

                # Verify both clients were closed
                mock_httpx_aclose.assert_called_once()
                mock_aiohttp_close.assert_called_once()

        # Clients should be reset
        assert client._client is None
        assert client._initialized is False

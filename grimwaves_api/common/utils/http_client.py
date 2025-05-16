"""Base HTTP client classes with async context manager support.

This module provides base classes for HTTP clients with proper resource management,
async context manager support, and lazy initialization of client sessions.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Optional, TypeVar, cast

import aiohttp
import httpx

from grimwaves_api.core.logger import get_logger

# Initialize module logger
logger = get_logger("common.utils.http_client")

# Type variable for self reference in context managers
T = TypeVar("T", bound="BaseHttpClient")


class BaseHttpClient(ABC):
    """Base class for HTTP clients with async context manager support.

    This abstract class provides common functionality for HTTP clients:
    - Async context manager interface (__aenter__, __aexit__)
    - Lazy initialization of client sessions
    - Resource cleanup on exit

    Subclasses should implement the _init_client method.
    """

    def __init__(self) -> None:
        """Initialize the base HTTP client."""
        # Client instance will be lazily initialized
        self._client: Optional[httpx.AsyncClient] = None
        self._initialized: bool = False

    @abstractmethod
    async def _init_client(self) -> httpx.AsyncClient:
        """Initialize and return the HTTP client.

        This method should be implemented by subclasses to configure
        and return their specific HTTP client instance.

        Returns:
            Configured HTTP client instance
        """
        msg = "Subclasses must implement _init_client"
        raise NotImplementedError(msg)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client instance.

        This method implements lazy initialization of the client.

        Returns:
            Initialized HTTP client
        """
        if not self._client or not self._initialized:
            logger.debug("Initializing HTTP client")
            self._client = await self._init_client()
            self._initialized = True
        return self._client

    async def close(self) -> None:
        """Close the HTTP client and release resources.

        This method should be called when the client is no longer needed
        to ensure all resources are properly released.
        """
        if self._client and self._initialized:
            logger.debug("Closing HTTP client")
            await self._client.aclose()
            await asyncio.sleep(0)  # Allow loop to process any pending tasks from aclose
            self._client = None
            self._initialized = False

    async def __aenter__(self) -> T:
        """Enter the async context manager.

        This method is called when entering an async context manager block.
        It ensures the client is initialized.

        Returns:
            The client instance
        """
        await self._get_client()
        return cast(T, self)

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the async context manager.

        This method is called when exiting an async context manager block.
        It ensures resources are properly released even if an exception occurred.

        Args:
            exc_type: Exception type if an exception was raised, None otherwise
            exc_val: Exception instance if an exception was raised, None otherwise
            exc_tb: Exception traceback if an exception was raised, None otherwise
        """
        await self.close()


class BaseHttpxClient(BaseHttpClient):
    """Base class for HTTP clients using httpx.AsyncClient.

    This class extends BaseHttpClient with specific functionality for
    httpx.AsyncClient based implementations.
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 10.0,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        """Initialize the base httpx client.

        Args:
            base_url: Optional base URL for all requests
            timeout: Request timeout in seconds
            headers: Optional default headers for all requests
        """
        super().__init__()
        self.base_url = base_url
        self.timeout = timeout
        self.headers = headers or {}

    async def _init_client(self) -> httpx.AsyncClient:
        """Initialize and configure the httpx.AsyncClient.

        Returns:
            Configured httpx.AsyncClient instance
        """
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self.headers,
            follow_redirects=True,
        )


class BaseAiohttpClient(ABC):
    """Base class for HTTP clients using aiohttp.ClientSession.

    This class provides proper resource management for clients using
    aiohttp.ClientSession.
    """

    def __init__(self) -> None:
        """Initialize the base aiohttp client."""
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp ClientSession instance.

        This method implements lazy initialization of the session.

        Returns:
            Initialized aiohttp ClientSession
        """
        if self._session is None or self._session.closed:
            logger.debug("Creating new aiohttp ClientSession")
            self._session = aiohttp.ClientSession()
        return self._session

    async def close_session(self) -> None:
        """Close the aiohttp ClientSession and release resources."""
        if self._session and not self._session.closed:
            logger.debug("Closing aiohttp ClientSession")
            await self._session.close()
            # Give the event loop a chance to clean up
            await asyncio.sleep(0.1)
            self._session = None


class DualHttpClient(BaseHttpClient, BaseAiohttpClient):
    """Base class for clients using both httpx and aiohttp.

    This class is intended for clients like SpotifyClient that need to use
    both httpx.AsyncClient and aiohttp.ClientSession.
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 10.0,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        """Initialize the dual HTTP client.

        Args:
            base_url: Optional base URL for httpx client
            timeout: Request timeout in seconds
            headers: Optional default headers for all requests
        """
        BaseHttpClient.__init__(self)
        BaseAiohttpClient.__init__(self)
        self.base_url = base_url
        self.timeout = timeout
        self.headers = headers or {}

    async def _init_client(self) -> httpx.AsyncClient:
        """Initialize and configure the httpx.AsyncClient.

        Returns:
            Configured httpx.AsyncClient instance
        """
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self.headers,
            follow_redirects=True,
        )

    async def close(self) -> None:
        """Close both httpx and aiohttp clients."""
        # Close httpx client
        await BaseHttpClient.close(self)

        # Close aiohttp session
        await self.close_session()

    async def __aenter__(self) -> T:
        """Enter the async context manager.

        Ensures both httpx client and aiohttp session are initialized.

        Returns:
            The client instance
        """
        await BaseHttpClient.__aenter__(self)
        await self._get_session()
        return cast(T, self)

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the async context manager.

        Ensures resources for both clients are properly released.

        Args:
            exc_type: Exception type if an exception was raised, None otherwise
            exc_val: Exception instance if an exception was raised, None otherwise
            exc_tb: Exception traceback if an exception was raised, None otherwise
        """
        await self.close()

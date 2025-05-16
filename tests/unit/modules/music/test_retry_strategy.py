"""Tests for the retry strategy module."""

import asyncio
import random
from unittest.mock import MagicMock, patch

import pytest
from celery import Task

from grimwaves_api.modules.music.constants import (
    DATA_RETRY_CONFIG,
    EVENT_LOOP_RETRY_CONFIG,
    NETWORK_RETRY_CONFIG,
)
from grimwaves_api.modules.music.retry_strategy import RetryStrategy
from grimwaves_api.modules.music.schemas import RetryConfig


@pytest.fixture
def mock_task():
    """Create a mock Celery task for testing."""
    task = MagicMock(spec=Task)
    task.request = MagicMock()
    task.request.retries = 0
    task.request.id = "test_task_id"
    task.max_retries = 3
    return task


class TestRetryStrategy:
    """Tests for the RetryStrategy class."""

    def test_get_config_for_event_loop_error(self):
        """Test getting config for event loop errors."""
        # Create a RuntimeError that looks like an event loop error
        exc = RuntimeError("Event loop is closed")

        # Patch the classify_event_loop_error function to return a known value
        with patch("grimwaves_api.common.utils.asyncio_utils.classify_event_loop_error", return_value="closed_loop"):
            config = RetryStrategy.get_config_for_exception(exc)

        # Verify we got the event loop config
        assert config == EVENT_LOOP_RETRY_CONFIG

    def test_get_config_for_network_error(self):
        """Test getting config for network errors."""
        # Test with ConnectionError
        exc = ConnectionError("Failed to connect")
        config = RetryStrategy.get_config_for_exception(exc)
        assert config == NETWORK_RETRY_CONFIG

        # Test with TimeoutError
        exc = TimeoutError("Operation timed out")
        config = RetryStrategy.get_config_for_exception(exc)
        assert config == NETWORK_RETRY_CONFIG

        # Test with asyncio.TimeoutError
        exc = asyncio.TimeoutError("Async operation timed out")
        config = RetryStrategy.get_config_for_exception(exc)
        assert config == NETWORK_RETRY_CONFIG

    def test_get_config_for_data_error(self):
        """Test getting config for data errors."""
        # Test with ValueError
        exc = ValueError("Invalid value")
        config = RetryStrategy.get_config_for_exception(exc)
        assert config == DATA_RETRY_CONFIG

        # Test with KeyError
        exc = KeyError("Missing key")
        config = RetryStrategy.get_config_for_exception(exc)
        assert config == DATA_RETRY_CONFIG

    def test_calculate_retry_delay_linear(self):
        """Test calculating retry delay with linear backoff."""
        config = RetryConfig(
            max_retries=3,
            base_delay=1.0,
            use_exponential=False,  # Linear
            use_jitter=False,  # No jitter
            max_delay=10.0,
            backoff_factor=1.0,
        )

        # Test with different retry counts
        assert RetryStrategy.calculate_retry_delay(config, 0) == 1.0  # Base delay
        assert RetryStrategy.calculate_retry_delay(config, 1) == 2.0  # Base + factor
        assert RetryStrategy.calculate_retry_delay(config, 2) == 3.0  # Base + 2*factor

    def test_calculate_retry_delay_exponential(self):
        """Test calculating retry delay with exponential backoff."""
        config = RetryConfig(
            max_retries=3,
            base_delay=1.0,
            use_exponential=True,  # Exponential
            use_jitter=False,  # No jitter
            max_delay=10.0,
            backoff_factor=2.0,
        )

        # Test with different retry counts
        assert RetryStrategy.calculate_retry_delay(config, 0) == 1.0  # Base delay
        assert RetryStrategy.calculate_retry_delay(config, 1) == 2.0  # Base * factor^1
        assert RetryStrategy.calculate_retry_delay(config, 2) == 4.0  # Base * factor^2
        assert RetryStrategy.calculate_retry_delay(config, 3) == 8.0  # Base * factor^3

    def test_calculate_retry_delay_with_max(self):
        """Test that retry delay is capped at max_delay."""
        config = RetryConfig(
            max_retries=3,
            base_delay=1.0,
            use_exponential=True,
            use_jitter=False,
            max_delay=5.0,  # Max delay of 5 seconds
            backoff_factor=2.0,
        )

        # The calculated delay would be 8.0, but it should be capped at 5.0
        assert RetryStrategy.calculate_retry_delay(config, 3) == 5.0

    def test_calculate_retry_delay_with_jitter(self, monkeypatch):
        """Test that jitter is applied to retry delay."""
        # Mock random.uniform to return a fixed value for testing
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.5)

        config = RetryConfig(
            max_retries=3,
            base_delay=4.0,
            use_exponential=False,
            use_jitter=True,  # Add jitter
            max_delay=10.0,
            backoff_factor=1.0,
        )

        # For retry 1, base delay is 4.0 + 1*1.0 = 5.0
        # With jitter range of 25% (1.25), and mocked random.uniform returning 0.5
        # Expected delay is 5.0 + 0.5 = 5.5
        assert RetryStrategy.calculate_retry_delay(config, 1) == 5.5

    def test_retry_task_raises_exception_when_max_retries_reached(self, mock_task):
        """Test that retry_task raises the original exception when max retries is reached."""
        # Set retries to max
        mock_task.request.retries = mock_task.max_retries

        exc = ValueError("Test exception")

        # The function should raise the original exception
        with pytest.raises(ValueError, match="Test exception"):
            RetryStrategy.retry_task(mock_task, exc)

    def test_retry_task_calls_task_retry(self, mock_task):
        """Test that retry_task calls task.retry with the right parameters."""
        exc = ValueError("Test exception")

        # Mock the calculate_retry_delay method
        with patch.object(RetryStrategy, "calculate_retry_delay", return_value=2.5):
            # Call retry_task, which should eventually call task.retry
            RetryStrategy.retry_task(mock_task, exc)

            # Verify task.retry was called with the right parameters
            mock_task.retry.assert_called_once()
            # Extract the call arguments
            call_args = mock_task.retry.call_args[1]
            assert call_args.get("exc") == exc
            assert call_args.get("countdown") == 2.5

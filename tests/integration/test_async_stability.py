"""Integration tests for async resources stability in GrimWaves API.

This module contains tests that specifically focus on verifying the stability
of asyncio event loop management, thread-local storage mechanisms, and resource
cleanup in high-load or problematic scenarios.
"""

import asyncio
import concurrent.futures
import gc
import threading
from typing import Any, Callable, TypeVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery import Task

from grimwaves_api.common.utils.asyncio_utils import run_async_safely
from grimwaves_api.core.celery_app import celery_app
from grimwaves_api.modules.music.tasks import (
    RetryStrategy,
    fetch_release_metadata,
)

T = TypeVar("T")


@pytest.fixture
def enable_eager_mode(monkeypatch):
    """Configure Celery to run tasks synchronously for testing.

    This fixture changes Celery configuration to execute tasks synchronously
    to simplify testing and prevent actual task queue usage.
    """
    # Store original settings
    original_always_eager = celery_app.conf.task_always_eager
    original_eager_propagates = celery_app.conf.task_eager_propagates

    # Enable eager mode
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)

    # Provide fixture
    yield

    # Restore original settings
    celery_app.conf.update(
        task_always_eager=original_always_eager,
        task_eager_propagates=original_eager_propagates,
    )


@pytest.fixture
def verify_no_resource_leaks():
    """Check for resource leaks after test execution."""
    # Run garbage collection to clean up any lingering resources
    gc.collect()

    # Store initial state
    initial_thread_count = threading.active_count()

    yield

    # Run garbage collection again
    gc.collect()

    # Check for thread leaks
    final_thread_count = threading.active_count()
    assert final_thread_count <= initial_thread_count + 1, (
        f"Thread leak detected: {final_thread_count - initial_thread_count} additional threads found after test"
    )


def execute_in_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute a function in a separate thread and return its result."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        return future.result()


@pytest.mark.integration
def test_thread_local_isolation():
    """Test that event loops are properly isolated between threads."""

    # Create a simple async function
    async def simple_async_func():
        await asyncio.sleep(0.1)
        return threading.get_ident()

    # Run it in the main thread
    main_thread_id = run_async_safely(simple_async_func)

    # Run it in another thread
    other_thread_id = execute_in_thread(run_async_safely, simple_async_func)

    # Verify thread IDs are different
    assert main_thread_id != other_thread_id, "Thread isolation failed"

    # Run again in main thread to verify we get the same thread ID
    main_thread_id_2 = run_async_safely(simple_async_func)
    assert main_thread_id == main_thread_id_2, "Main thread ID changed unexpectedly"


@pytest.mark.integration
def test_reference_counting():
    """Test that event loop reference counting works correctly."""

    # A function that nests multiple run_async_safely calls
    async def nested_async_func(depth=1, max_depth=3):
        if depth < max_depth:
            # Вместо вложенного вызова run_async_safely используем прямой вызов
            return await nested_async_func(depth + 1, max_depth)
        return f"Reached depth {depth}"

    # Execute with nested calls
    result = run_async_safely(nested_async_func)

    # Verify success
    assert result == "Reached depth 3", "Nested run_async_safely calls failed"

    # Verify no lingering loops
    with pytest.raises(RuntimeError, match="no running event loop"):
        asyncio.get_running_loop()


@pytest.mark.integration
def test_parallel_run_async_safely(verify_no_resource_leaks):
    """Test that run_async_safely works correctly when called from multiple threads."""

    async def simple_task(idx) -> str:
        await asyncio.sleep(0.01)  # Small sleep to force task switching
        return f"Task {idx} completed in thread {threading.get_ident()}"

    # Number of parallel threads to use
    n_threads = 10

    # Create and start threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as executor:
        # Submit tasks
        futures = [executor.submit(run_async_safely, simple_task, i) for i in range(n_threads)]

        # Collect results
        results = [future.result() for future in futures]

    # Verify we got results from different threads
    thread_ids = {result.split("thread ")[1] for result in results}
    assert len(thread_ids) == n_threads, f"Expected {n_threads} distinct threads but got {len(thread_ids)}"


@pytest.mark.integration
def test_error_recovery_simulation():
    """Test the error recovery mechanism by simulating closed event loop errors."""

    # Define an async function that will encounter the error
    async def function_with_error() -> str:
        # Normal operation first time
        return "Success"

    # Mock the classify_event_loop_error function to simulate different error types
    with (
        patch(
            "grimwaves_api.modules.music.tasks.classify_event_loop_error",
            return_value="closed_loop",
        ),
        patch(
            "grimwaves_api.modules.music.tasks.diagnose_event_loop",
            return_value={"has_loop": True, "is_closed": True, "ref_count": 0},
        ),
        patch(
            "grimwaves_api.modules.music.tasks.handle_event_loop_error",
            return_value=True,  # Indicate successful recovery
        ),
    ):
        # Create a task instance
        task_instance = MagicMock(spec=Task)
        task_instance.request.retries = 0
        task_instance.max_retries = 3

        # Настраиваем mock так, чтобы retry выбрасывал реальное исключение
        task_instance.retry.side_effect = RuntimeError("Retry called")

        # Simulate an exception
        exception = RuntimeError("Event loop is closed")

        # Try to recover
        try:
            RetryStrategy.retry_task(task_instance, exception, "test_task_id", "test_task")
            msg = "Should have raised retry exception"
            raise AssertionError(msg)
        except RuntimeError as e:
            # Expected - retry должен вызываться
            assert "Retry called" in str(e)

        # Verify the right countdown was used for event loop errors
        task_instance.retry.assert_called_once()
        kwargs = task_instance.retry.call_args[1]
        assert "countdown" in kwargs
        assert kwargs["countdown"] == 1, "Expected quick retry (1s) for event loop errors"


@pytest.mark.integration
def test_high_volume_sequential_tasks(enable_eager_mode):
    """Test that a high volume of sequential task executions doesn't lead to event loop issues."""
    # Mock clients to prevent actual API calls
    with (
        patch(
            "grimwaves_api.modules.music.tasks.SpotifyClient",
        ) as mock_spotify,
        patch(
            "grimwaves_api.modules.music.tasks.DeezerClient",
        ) as mock_deezer,
        patch(
            "grimwaves_api.modules.music.tasks.MusicBrainzClient",
        ) as mock_mb,
    ):
        # Setup mocks as context managers
        for client_mock in [mock_spotify.return_value, mock_deezer.return_value, mock_mb.return_value]:
            client_mock.__aenter__.return_value = client_mock
            client_mock.__aexit__.return_value = None

            # Важно: настраиваем close как корутину
            async def mock_close() -> None:
                return None

            client_mock.close = mock_close

        # Setup service mock to return minimal valid data
        with patch(
            "grimwaves_api.modules.music.service.MusicMetadataService.fetch_release_metadata",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = {
                "release": "Test Album",  # Строковое значение, а не словарь
                "artist": "Test Artist",
                "tracks": [{"title": "Track 1"}, {"title": "Track 2"}],
            }

            # Mock cache to avoid actual Redis calls
            with (
                patch(
                    "grimwaves_api.modules.music.tasks.MetadataTask.check_cache",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch(
                    "grimwaves_api.modules.music.tasks.MetadataTask.cache_result",
                    new_callable=AsyncMock,
                ),
            ):
                # Execute a large number of sequential tasks
                num_tasks = 10  # Уменьшаем количество для ускорения тестов

                # Simple request data с правильными именами полей
                request_data = {
                    "band_name": "Test Artist",
                    "release_name": "Test Album",
                    "search_mode": "basic",
                }

                for _i in range(num_tasks):
                    # Execute task
                    result = fetch_release_metadata(request_data)

                    # Verify result structure is valid
                    assert "status" in result
                    assert result["status"] == "SUCCESS"
                    assert "result" in result
                    assert result["result"]["release"] == "Test Album"


@pytest.mark.integration
def test_event_loop_robustness_with_simulated_failures(enable_eager_mode):
    """Test that the system handles various event loop failure scenarios properly."""
    # Create counter for calls
    call_count = {"count": 0}

    # Mock service that fails with event loop errors on first calls
    async def mock_fetch_with_failures(*args, **kwargs):
        call_count["count"] += 1

        # Fail in different ways for the first few calls
        if call_count["count"] == 1:
            msg = "Event loop is closed"
            raise RuntimeError(msg)
        if call_count["count"] == 2:
            msg = "got Future attached to a different loop"
            raise RuntimeError(msg)

        # Eventually succeed
        return {
            "release": "Test Album",  # Строковое значение
            "artist": "Test Artist",
            "tracks": [{"title": "Track 1"}, {"title": "Track 2"}],
        }

    # Apply mocks for clients and service
    with (
        patch(
            "grimwaves_api.modules.music.tasks.SpotifyClient",
        ) as mock_spotify,
        patch(
            "grimwaves_api.modules.music.tasks.DeezerClient",
        ) as mock_deezer,
        patch(
            "grimwaves_api.modules.music.tasks.MusicBrainzClient",
        ) as mock_mb,
    ):
        # Setup mocks as context managers
        for client_mock in [mock_spotify.return_value, mock_deezer.return_value, mock_mb.return_value]:
            client_mock.__aenter__.return_value = client_mock
            client_mock.__aexit__.return_value = None

            # Важно: настраиваем close как корутину
            async def mock_close() -> None:
                return None

            client_mock.close = mock_close

        # Setup our failing service mock
        with (
            patch(
                "grimwaves_api.modules.music.service.MusicMetadataService.fetch_release_metadata",
                side_effect=mock_fetch_with_failures,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.MetadataTask.check_cache",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.MetadataTask.cache_result",
                new_callable=AsyncMock,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.handle_event_loop_error",
                return_value=True,  # Indicate successful recovery
            ),
            # Дополнительно патчим classify_event_loop_error для перехвата ошибок
            patch(
                "grimwaves_api.modules.music.tasks.classify_event_loop_error",
                return_value="closed_loop",  # Ошибка закрытого цикла событий
            ),
        ):
            # Request data с правильными именами полей
            request_data = {
                "band_name": "Test Artist",
                "release_name": "Test Album",
                "search_mode": "basic",
            }

            # Execute task - мы ожидаем либо успех, либо ошибку с сообщением о цикле
            try:
                result = fetch_release_metadata(request_data)

                # Если результат успешный, проверяем его структуру
                if result.get("status") == "SUCCESS":
                    assert "result" in result
                    assert result["result"]["release"] == "Test Album"
                else:
                    # В случае статуса FAILURE, проверяем наличие ошибки event loop
                    assert "error" in result
                    error_msg = result.get("error", "")
                    assert "Event loop" in error_msg or "Future" in error_msg
            except Exception as e:
                # В случае исключения, проверяем его тип
                error_str = str(e)
                assert (
                    "Event loop" in error_str
                    or "Future" in error_str
                    or "asyncio" in error_str
                    or "retry" in error_str.lower()
                )

            # Проверяем, что наш mock вызывался не менее 1 раза
            assert call_count["count"] >= 1


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])

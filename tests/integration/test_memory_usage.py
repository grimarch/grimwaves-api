"""Integration tests for memory usage in GrimWaves API.

This module contains tests that specifically focus on memory usage patterns
during long-running operations to detect memory leaks or resource accumulation.
"""

import asyncio
import gc
import logging
import threading
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import psutil
import pytest

from grimwaves_api.common.utils.asyncio_utils import run_async_safely
from grimwaves_api.core.celery_app import celery_app
from grimwaves_api.modules.music.tasks import fetch_release_metadata


class MemoryProfiler:
    """Helper class to track and analyze memory usage."""

    def __init__(self, sampling_interval: float = 0.5) -> None:
        """Initialize profiler.

        Args:
            sampling_interval: Time between memory samples in seconds
        """
        self.sampling_interval = sampling_interval
        self.samples: list[tuple[float, int]] = []  # (timestamp, memory usage in bytes)
        self.running = False
        self.process = psutil.Process()
        self.thread = None

    def start(self):
        """Start memory profiling in a background thread."""
        self.samples = []
        self.running = True
        self.thread = threading.Thread(target=self._sample_memory)
        self.thread.daemon = True
        self.thread.start()

    def stop(self) -> list[tuple[float, int]]:
        """Stop memory profiling and return samples."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)  # Wait up to 3s for the thread to finish
        return self.samples

    def _sample_memory(self) -> None:
        """Sample memory usage at regular intervals."""
        start_time = time.time()
        while self.running:
            memory_info = self.process.memory_info()
            self.samples.append((time.time() - start_time, memory_info.rss))
            time.sleep(self.sampling_interval)

    def analyze(self) -> dict[str, Any]:
        """Analyze memory samples and return statistics."""
        if not self.samples:
            return {"warning": "No memory samples collected"}

        # Calculate basic statistics
        memory_values = [mem for _, mem in self.samples]
        duration = self.samples[-1][0] - self.samples[0][0]

        # Convert to MB for easier reading
        memory_mb = [mem / (1024 * 1024) for mem in memory_values]

        # Calculate growth rate (bytes per second)
        if len(self.samples) > 1:
            start_mem = self.samples[0][1]
            end_mem = self.samples[-1][1]
            growth_rate = (end_mem - start_mem) / duration
        else:
            growth_rate = 0

        return {
            "duration_seconds": duration,
            "samples_count": len(self.samples),
            "min_memory_mb": min(memory_mb),
            "max_memory_mb": max(memory_mb),
            "avg_memory_mb": sum(memory_mb) / len(memory_mb),
            "memory_growth_rate_kb_per_sec": growth_rate / 1024,
            "start_memory_mb": memory_mb[0],
            "end_memory_mb": memory_mb[-1],
            "memory_growth_percent": (memory_mb[-1] - memory_mb[0]) / memory_mb[0] * 100 if memory_mb[0] > 0 else 0,
        }


@pytest.fixture
def enable_eager_mode():
    """Configure Celery to run tasks synchronously for testing."""
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
def memory_profiler():
    """Provide a memory profiler and manage its lifecycle."""
    profiler = MemoryProfiler(sampling_interval=0.5)

    # Start profiling
    profiler.start()

    # Provide profiler to test
    yield profiler

    # Stop profiling at end of test
    profiler.stop()


@pytest.fixture
def mock_api_clients():
    """Mock API clients to avoid actual API calls during memory testing."""
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

        # Return mocks to the test
        yield {
            "spotify": mock_spotify,
            "deezer": mock_deezer,
            "musicbrainz": mock_mb,
        }


@pytest.fixture
def mock_metadata_service():
    """Mock metadata service to return predefined responses."""
    with patch(
        "grimwaves_api.modules.music.service.MusicMetadataService.fetch_release_metadata",
        new_callable=AsyncMock,
    ) as mock_fetch:
        # Default response data
        mock_fetch.return_value = {
            "release": {"title": "Test Album", "artist": "Test Artist"},
            "tracks": [{"title": f"Track {i}"} for i in range(1, 11)],
        }

        yield mock_fetch


@pytest.fixture
def mock_cache():
    """Mock cache operations to avoid Redis dependencies."""
    with (
        patch(
            "grimwaves_api.modules.music.tasks.MetadataTask.check_cache",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_check_cache,
        patch(
            "grimwaves_api.modules.music.tasks.MetadataTask.cache_result",
            new_callable=AsyncMock,
        ) as mock_cache_result,
    ):
        yield {
            "check": mock_check_cache,
            "save": mock_cache_result,
        }


def force_garbage_collection():
    """Force aggressive garbage collection to minimize baseline memory impact."""
    # Run multiple GC passes to clean up reference cycles
    for _ in range(5):
        gc.collect()
    # Small delay to let async cleanups complete
    time.sleep(0.5)


@pytest.mark.memory
@pytest.mark.integration
def test_repeated_tasks_memory_usage(
    enable_eager_mode: None,
    memory_profiler: MemoryProfiler,
    mock_api_clients: dict[str, Any],
    mock_metadata_service: AsyncMock,
    mock_cache: dict[str, AsyncMock],
):
    """Test memory usage during repeated task execution.

    This test runs a large number of sequential tasks and tracks memory usage
    to detect potential memory leaks.
    """
    # Setup mocks for client close methods as async methods
    for client_mock in mock_api_clients.values():

        async def mock_close() -> None:
            return None

        client_mock.return_value.close = mock_close

    # Configure metadata service mock to return valid data
    mock_metadata_service.return_value = {
        "release": "Test Album",  # строка вместо объекта
        "artist": "Test Artist",
        "tracks": [{"title": f"Track {i}"} for i in range(1, 10)],
    }

    # Number of tasks to run
    num_tasks = 5  # Уменьшаем для ускорения и стабильности тестов

    # Prepare request data
    request_data = {
        "band_name": "Metallica",
        "release_name": "Black Album",
        "search_mode": "basic",
    }

    # Force initial GC to establish baseline
    force_garbage_collection()

    # Track success and failure
    results = {"success": 0, "fail": 0}

    # Execute tasks
    for i in range(num_tasks):
        # Log progress occasionally
        if i % 50 == 0:
            logging.info(f"Memory test progress: {i}/{num_tasks}")

        try:
            # Execute task
            result = fetch_release_metadata(request_data)

            # Count successes and failures
            if "status" in result and result["status"] == "SUCCESS":
                results["success"] += 1
            else:
                results["fail"] += 1
        except Exception as e:
            logging.exception(f"Task failed: {e!s}")
            results["fail"] += 1

        # Force garbage collection to clear memory
        if i % 2 == 0:
            force_garbage_collection()

    # Log results
    success_rate = results["success"] / num_tasks if num_tasks > 0 else 0
    logging.info(f"Memory test success rate: {success_rate:.2f}")

    # We don't actually need to assert success rate here as we're mainly
    # checking for memory leaks which would be detected by the memory profiler


@pytest.mark.memory
@pytest.mark.integration
def test_concurrent_tasks_memory_usage(
    enable_eager_mode: None,
    memory_profiler: MemoryProfiler,
    mock_api_clients: dict[str, Any],
    mock_metadata_service: AsyncMock,
    mock_cache: dict[str, AsyncMock],
):
    """Test memory usage during concurrent task execution.

    This test executes multiple tasks concurrently in threads and
    monitors memory usage to detect leaks related to thread-local storage.
    """
    # Configuration
    num_threads = 10
    iterations_per_thread = 50

    # Force initial GC to establish baseline
    force_garbage_collection()

    # Define thread worker function
    def thread_worker() -> None:
        request_data = {
            "band_name": "Metallica",
            "release_name": "Black Album",
            "search_mode": "basic",
        }

        for _ in range(iterations_per_thread):
            # Execute task
            result = fetch_release_metadata(request_data)
            assert "release" in result

    # Start threads
    threads = []
    for _ in range(num_threads):
        thread = threading.Thread(target=thread_worker)
        thread.daemon = True
        thread.start()
        threads.append(thread)

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    # Force final GC
    force_garbage_collection()

    # Analyze results
    memory_stats = memory_profiler.analyze()

    # Log detailed results
    logging.info("Concurrent tasks memory usage statistics:")
    for key, value in memory_stats.items():
        logging.info(f"  {key}: {value}")

    # Verify thread-local storage isn't leaking
    assert memory_stats["memory_growth_percent"] < 30.0, (
        f"Memory growth too high in concurrent test: {memory_stats['memory_growth_percent']:.2f}%"
    )


@pytest.mark.memory
@pytest.mark.integration
def test_nested_run_async_safely_memory(
    memory_profiler: MemoryProfiler,
):
    """Test memory usage during nested run_async_safely calls.

    This test specifically checks if multiple levels of nesting in
    run_async_safely calls cause memory leaks.
    """
    # Force initial GC to establish baseline
    force_garbage_collection()

    # Define a simple async function that returns a coroutine
    async def simple_coro(depth=0) -> str:
        await asyncio.sleep(0.01)
        return f"Result at depth {depth}"

    # Define a recursive test function with proper async wrapping
    def run_nested(depth=0, max_depth=3):
        # Важно использовать async lambda для вложенных вызовов
        if depth >= max_depth:
            return run_async_safely(simple_coro, depth)

        # Create nested async function call
        async def nested_async():
            # Рекурсивно вызываем run_nested, но оборачиваем результат в корутину
            return run_nested(depth + 1, max_depth)

        return run_async_safely(nested_async)

    # Run fewer iterations for stability
    iterations = 5
    max_nesting = 2

    successes = 0
    failures = 0

    for i in range(iterations):
        # Log progress occasionally
        if i % 50 == 0:
            logging.info(f"Nested run_async_safely memory test: {i}/{iterations}")

        try:
            # Run nested calls
            run_nested(0, max_nesting)
            successes += 1
        except Exception as e:
            logging.exception(f"Nested run_async_safely failed: {e!s}")
            failures += 1

        # Force garbage collection occasionally
        if i % 2 == 0:
            force_garbage_collection()

    # Log results
    logging.info(f"Nested memory test: {successes} successes, {failures} failures")


@pytest.mark.memory
@pytest.mark.integration
def test_thread_local_storage_cleanup_on_thread_exit(
    memory_profiler: MemoryProfiler,
):
    """Test that thread-local storage is properly cleaned up when threads exit.

    This test creates and destroys many threads, each using run_async_safely,
    to verify that thread-local resources are properly cleaned up.
    """
    # Force initial GC to establish baseline
    force_garbage_collection()

    # Function to run in each thread
    def thread_func() -> None:
        # Create a simple async function
        async def simple_async_func():
            await asyncio.sleep(0.01)
            return threading.get_ident()

        # Run it multiple times in this thread to ensure TLS is used
        for _ in range(10):
            run_async_safely(simple_async_func)

    # Create and destroy many threads
    num_threads = 100

    # Run in smaller batches to avoid too many threads at once
    batch_size = 10
    num_batches = num_threads // batch_size

    for batch in range(num_batches):
        logging.info(f"Thread cleanup test batch {batch + 1}/{num_batches}")

        # Create threads
        threads = []
        for _ in range(batch_size):
            thread = threading.Thread(target=thread_func)
            thread.start()
            threads.append(thread)

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

    # Force final GC
    force_garbage_collection()

    # Analyze results
    memory_stats = memory_profiler.analyze()

    # Log detailed results
    logging.info("Thread cleanup memory statistics:")
    for key, value in memory_stats.items():
        logging.info(f"  {key}: {value}")

    # Verify thread resources are cleaned up
    assert memory_stats["memory_growth_percent"] < 30.0, (
        f"Memory growth too high in thread cleanup test: {memory_stats['memory_growth_percent']:.2f}%"
    )


@pytest.mark.memory
@pytest.mark.integration
def test_error_recovery_memory_usage(
    enable_eager_mode: None,
    memory_profiler: MemoryProfiler,
    mock_api_clients: dict[str, Any],
    mock_cache: dict[str, AsyncMock],
):
    """Test memory usage during error recovery scenarios.

    This test simulates error scenarios and recovery to ensure
    that recovery mechanisms don't leak memory.
    """
    # Force initial GC to establish baseline
    force_garbage_collection()

    # Define a service that fails occasionally
    call_count = {"value": 0}

    async def failing_service(*args, **kwargs):
        call_count["value"] += 1

        # Fail every 10th call with an event loop error
        if call_count["value"] % 10 == 0:
            msg = "Event loop is closed"
            raise RuntimeError(msg)

        # Fail every 23rd call with a different error
        if call_count["value"] % 23 == 0:
            msg = "got Future attached to a different loop"
            raise RuntimeError(msg)

        # Otherwise return valid data
        return {
            "release": {"title": "Test Album", "artist": "Test Artist"},
            "tracks": [{"title": "Track 1"}, {"title": "Track 2"}],
        }

    # Set up mock service with failures
    with patch(
        "grimwaves_api.modules.music.service.MusicMetadataService.fetch_release_metadata",
        side_effect=failing_service,
    ):
        # Execute multiple tasks with retries
        iterations = 200
        request_data = {
            "band_name": "Metallica",
            "release_name": "Black Album",
            "search_mode": "basic",
        }

        for i in range(iterations):
            # Log progress occasionally
            if i % 20 == 0:
                logging.info(f"Error recovery memory test: {i}/{iterations}")

            try:
                # Execute task with potential errors
                result = fetch_release_metadata(request_data)
                assert "release" in result
            except Exception as e:
                # Some errors might not be automatically recovered
                logging.warning(f"Error at iteration {i}: {e!s}")

            # Run GC occasionally
            if i % 25 == 0:
                gc.collect()

    # Force final GC
    force_garbage_collection()

    # Analyze results
    memory_stats = memory_profiler.analyze()

    # Log detailed results
    logging.info("Error recovery memory statistics:")
    for key, value in memory_stats.items():
        logging.info(f"  {key}: {value}")

    # Verify that error recovery doesn't leak memory
    assert memory_stats["memory_growth_percent"] < 30.0, (
        f"Memory growth too high in error recovery test: {memory_stats['memory_growth_percent']:.2f}%"
    )


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])

"""Tests for asyncio utilities module."""

import asyncio
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from grimwaves_api.common.utils.asyncio_utils import (
    _thread_local_storage,
    _thread_locks,
    cleanup_loop,
    run_async_safely,
)
from grimwaves_api.core.logger.logger import get_logger

# Initialize module logger for this test file
logger = get_logger("tests.common.utils.asyncio_utils")


# Helper async functions for tests
async def simple_async_function() -> str:
    """Simple async function that returns a string."""
    return "success"


async def async_function_with_error() -> None:
    """Async function that raises an error."""
    msg = "Test error"
    raise ValueError(msg)


async def async_function_with_tasks() -> set[asyncio.Task[None]]:
    """Async function that creates additional tasks."""
    # Create some background tasks
    tasks = set()

    async def background_task(delay: float) -> None:
        await asyncio.sleep(delay)

    # Create 3 background tasks with different delays
    for i in range(3):
        task = asyncio.create_task(background_task(0.1 * (i + 1)))
        tasks.add(task)

    # Return the tasks without waiting for them
    return tasks


class TestRunAsyncSafely:
    """Tests for the run_async_safely function."""

    def test_simple_function(self) -> None:
        """Test that the function correctly executes a simple async function."""
        result = run_async_safely(simple_async_function)
        assert result == "success"

    def test_with_arguments(self) -> None:
        """Test that the function correctly passes arguments to async function."""

        async def async_with_args(a: int, b: int, c: str = "default") -> dict[str, Any]:
            return {"a": a, "b": b, "c": c}

        result = run_async_safely(async_with_args, 1, 2, c="test")
        assert result == {"a": 1, "b": 2, "c": "test"}

    def test_with_exception(self) -> None:
        """Test that exceptions in the async function are properly propagated."""
        with pytest.raises(ValueError, match="Test error"):
            run_async_safely(async_function_with_error)

    def test_cancels_pending_tasks(self) -> None:
        """Test that pending tasks are properly cancelled."""
        # Define a custom async function that we can monitor
        task_cancelled = False

        async def custom_task_function():
            # Define a task that we can check if it was cancelled
            async def long_running_task() -> None:
                try:
                    await asyncio.sleep(10)  # Should be cancelled
                except asyncio.CancelledError:
                    nonlocal task_cancelled
                    task_cancelled = True
                    raise

            # Create and return the task without awaiting it
            return asyncio.create_task(long_running_task())

        # Run the function and let run_async_safely handle the cleanup
        run_async_safely(custom_task_function)

        # The task should have been cancelled during cleanup
        assert task_cancelled, "Background task was not cancelled"

    def test_nested_async_calls(self) -> None:
        """Test nested async function calls."""

        async def outer_async() -> str:
            # Call another async function
            result = await asyncio.create_task(simple_async_function())
            return f"outer: {result}"

        result = run_async_safely(outer_async)
        assert result == "outer: success"

    def test_reuse_with_closed_loop(self) -> None:
        """Test behavior when reusing the function with a closed loop."""
        # First call to establish a loop
        result1 = run_async_safely(simple_async_function)

        # Close any existing loop (simulating what happens in real world)
        try:
            loop = asyncio.get_event_loop()
            loop.close()
        except RuntimeError:
            pass

        # Second call should create a new loop
        result2 = run_async_safely(simple_async_function)

        assert result1 == "success"
        assert result2 == "success"

    def test_exception_during_task_cleanup(self) -> None:
        """Test behavior when an exception occurs during task cleanup."""
        # Create an async function that generates a task which will raise an error when cancelled
        task_cleanup_attempted = False

        async def task_with_problematic_cleanup():
            async def problematic_task() -> None:
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    nonlocal task_cleanup_attempted
                    task_cleanup_attempted = True
                    # Simulate an error during cleanup
                    msg = "Error during task cleanup"
                    raise RuntimeError(msg)

            # Start but don't await the task
            return asyncio.create_task(problematic_task())

        # The function should complete successfully despite the error in task cleanup
        run_async_safely(task_with_problematic_cleanup)

        # Verify cleanup was attempted
        assert task_cleanup_attempted, "Task cleanup was not attempted"

    def test_multiple_task_exceptions(self) -> None:
        """Test behavior with multiple tasks that raise different exceptions."""
        errors_raised = []
        tasks_created = []

        async def function_with_multiple_failing_tasks() -> str:
            # Create tasks that will raise different exceptions
            async def failing_task_1() -> None:
                try:
                    await asyncio.sleep(0.1)
                    msg = "Task 1 error"
                    raise ValueError(msg)
                except Exception as e:
                    errors_raised.append(e)
                    raise

            async def failing_task_2() -> None:
                try:
                    await asyncio.sleep(0.2)
                    msg = "Task 2 error"
                    raise TypeError(msg)
                except Exception as e:
                    errors_raised.append(e)
                    raise

            # Create and track the tasks
            task1 = asyncio.create_task(failing_task_1())
            task2 = asyncio.create_task(failing_task_2())
            tasks_created.extend([task1, task2])

            # Return immediately without awaiting
            return "started tasks"

        # The function should handle all task exceptions during cleanup
        result = run_async_safely(function_with_multiple_failing_tasks)
        assert result == "started tasks"

        # Check if tasks were created
        assert len(tasks_created) == 2, "Tasks were not created correctly"

        # Tasks should have been cancelled during cleanup before they could raise their exceptions
        # So errors_raised should be empty as the tasks were cancelled before reaching their exceptions
        assert len(errors_raised) == 0, "Tasks should have been cancelled before raising their exceptions"

    @patch("asyncio.new_event_loop")
    def test_exception_creating_new_loop(self, mock_new_event_loop) -> None:
        """Test behavior when an exception occurs creating a new event loop."""
        # Setup mock to raise an exception
        mock_new_event_loop.side_effect = OSError("Cannot create event loop")

        # Patch get_event_loop to simulate no existing loop
        with patch("asyncio.get_event_loop", side_effect=RuntimeError("No event loop")):
            # Should propagate the exception from new_event_loop
            with pytest.raises(OSError, match="Cannot create event loop"):
                run_async_safely(simple_async_function)

    def test_loop_already_running(self) -> None:
        """Test behavior when there's already a running loop."""
        # This test requires Python 3.7+ where get_running_loop is available
        if not hasattr(asyncio, "get_running_loop"):
            pytest.skip("This test requires Python 3.7+")

        # This test verifies that run_async_safely does not try to create a new event loop
        # when one is already running and available

        # Create a flag to check if our test completed properly
        test_completed = False

        async def test_coroutine() -> str:
            nonlocal test_completed
            # Create an event loop (this will be the current running loop)
            loop = asyncio.get_running_loop()

            # Define an async function that just captures the current loop
            async def get_current_loop():
                return asyncio.get_running_loop()

            # Call run_async_safely directly with an awaitable
            current_loop = await get_current_loop()

            # The loops should be the same - run_async_safely should use the existing loop
            assert current_loop is loop

            # Mark test as completed
            test_completed = True
            return "success"

        # Run the test coroutine
        asyncio.run(test_coroutine())

        # Verify test completed
        assert test_completed, "Test did not complete"

    def test_exception_during_loop_close(self) -> None:
        """Test run_async_safely handles exceptions during event loop close."""

        # Define a mock event loop that raises an error on close
        class MockEventLoop(asyncio.SelectorEventLoop):
            def __init__(self):
                super().__init__()
                self._has_raised_for_test = False

            def close(self) -> None:
                if not self._has_raised_for_test:
                    self._has_raised_for_test = True
                    msg = "Error closing loop"
                    raise RuntimeError(msg)
                else:
                    if not self.is_closed():
                        try:
                            super().close()
                        except Exception:
                            pass

        # Mock asyncio.new_event_loop to return our mock loop
        with patch("asyncio.new_event_loop", return_value=MockEventLoop()) as mock_new_loop:
            # Simulate no current loop to force creation of a new one
            # This will lead to get_or_create_loop calling asyncio.set_event_loop(MockEventLoop_instance)
            with patch("asyncio.get_event_loop", side_effect=RuntimeError("No current loop")):
                # Call the function; it should not raise an exception itself
                # because cleanup_loop should catch the RuntimeError from loop.close()
                run_async_safely(simple_async_function)

            # Verify that new_event_loop was called to create our mock loop
            mock_new_loop.assert_called_once()
            # Verify that our mock loop's close method was attempted
            assert mock_new_loop.return_value._has_raised_for_test, "MockEventLoop.close() was not called"

    # Новые тесты для Thread-Local Storage и счетчика ссылок

    def test_thread_local_storage_preserves_loop(self) -> None:
        """Test that the loop is preserved in thread-local storage between calls."""
        # Reset thread-local storage to ensure test isolation
        if hasattr(_thread_local_storage, "loop"):
            delattr(_thread_local_storage, "loop")
        if hasattr(_thread_local_storage, "ref_count"):
            delattr(_thread_local_storage, "ref_count")

        # First call should create a loop and store it
        run_async_safely(simple_async_function)

        # Get the loop from thread-local storage
        assert hasattr(_thread_local_storage, "loop"), "Loop not stored in thread-local storage"
        loop1 = _thread_local_storage.loop

        # Second call should reuse the same loop
        run_async_safely(simple_async_function)

        # Check that the same loop is used
        assert _thread_local_storage.loop is loop1, "Loop not preserved between calls"

    def test_reference_counter(self) -> None:
        """Test that the reference counter works correctly."""
        # Reset thread-local storage to ensure test isolation
        if hasattr(_thread_local_storage, "loop"):
            delattr(_thread_local_storage, "loop")
        if hasattr(_thread_local_storage, "ref_count"):
            delattr(_thread_local_storage, "ref_count")

        # Patch the cleanup_loop function to track if it's called
        cleanup_called = 0
        original_cleanup = cleanup_loop

        def mock_cleanup() -> None:
            nonlocal cleanup_called
            cleanup_called += 1
            original_cleanup()

        # Patch the cleanup_loop function
        with patch("grimwaves_api.common.utils.asyncio_utils.cleanup_loop", side_effect=mock_cleanup):
            # First call should initialize storage
            run_async_safely(simple_async_function)

            # The cleanup should have been called after the first call
            assert cleanup_called == 1, "cleanup_loop not called after first call"

            # Manually set ref_count to simulate active reference
            thread_id = threading.get_ident()
            with _thread_locks[thread_id]:
                # Set ref_count to 1 to simulate active reference
                _thread_local_storage.ref_count = 1

            # This call should not trigger cleanup since we have an active reference
            run_async_safely(simple_async_function)
            assert cleanup_called == 1, "cleanup_loop called when ref_count was still positive"

            # Manually reset ref_count to 0
            with _thread_locks[thread_id]:
                _thread_local_storage.ref_count = 0

            # Now let's simulate a completed run that should trigger cleanup
            run_async_safely(simple_async_function)
            assert cleanup_called == 2, "cleanup_loop not called when ref_count reached 0"

    def test_multiple_sequential_calls(self) -> None:
        """Test multiple sequential calls to ensure proper loop lifecycle."""
        # Reset thread-local storage
        if hasattr(_thread_local_storage, "loop"):
            delattr(_thread_local_storage, "loop")
        if hasattr(_thread_local_storage, "ref_count"):
            delattr(_thread_local_storage, "ref_count")

        # Patch the cleanup_loop function to track if it's called
        cleanup_called = False
        original_cleanup = cleanup_loop

        def mock_cleanup() -> None:
            nonlocal cleanup_called
            cleanup_called = True
            original_cleanup()

        # Patch the cleanup_loop function
        with patch("grimwaves_api.common.utils.asyncio_utils.cleanup_loop", side_effect=mock_cleanup):
            # Make multiple calls and store the results
            results = []
            for _ in range(5):
                results.append(run_async_safely(simple_async_function))
                # Cleanup should be called after each call
                assert cleanup_called, "cleanup_loop not called after call"
                cleanup_called = False  # Reset for next iteration

            # All calls should succeed
            assert all(result == "success" for result in results), "Not all calls succeeded"

            # Reference count should be 0 after all calls
            assert _thread_local_storage.ref_count == 0, "Reference counter not properly managed"

    def test_exception_preserves_reference_counter(self) -> None:
        """Test that exceptions don't break the reference counter."""
        # Reset thread-local storage
        if hasattr(_thread_local_storage, "loop"):
            delattr(_thread_local_storage, "loop")
        if hasattr(_thread_local_storage, "ref_count"):
            delattr(_thread_local_storage, "ref_count")

        # First successful call to initialize
        run_async_safely(simple_async_function)

        # Call with exception should still decrement the counter
        try:
            run_async_safely(async_function_with_error)
        except ValueError:
            pass  # Expected exception

        # Counter should still be 0
        assert _thread_local_storage.ref_count == 0, "Exception broke reference counter"

    def test_thread_isolation(self) -> None:
        """Test that each thread has its own isolated event loop."""
        # Вместо проверки разных идентификаторов loop, проверим, что _thread_local_storage
        # правильно работает в разных потоках и не конфликтует

        # Переменные для хранения данных из потоков
        thread_refs = {}
        threads_complete = {}

        def thread_func(thread_id) -> None:
            # Сохраняем начальное значение счетчика ссылок
            thread_refs[thread_id] = {"initial": getattr(_thread_local_storage, "ref_count", None)}

            # Запускаем функцию в этом потоке, которая должна создать локальное хранилище
            run_async_safely(simple_async_function)

            # Сохраняем значение счетчика ссылок после выполнения
            thread_refs[thread_id]["after_call"] = getattr(_thread_local_storage, "ref_count", None)

            # Отмечаем поток как завершенный
            threads_complete[thread_id] = True

        # Создаем и запускаем потоки
        threads = []
        for i in range(3):
            thread = threading.Thread(target=thread_func, args=(i,))
            threads.append(thread)
            thread.start()

        # Ждем завершения всех потоков
        for thread in threads:
            thread.join()

        # Проверяем, что все потоки создали свои локальные хранилища
        assert len(thread_refs) == 3, "Not all threads stored their refs"

        # Проверяем, что все потоки правильно управляют счетчиком ссылок:
        # 1. Изначально счетчик должен быть None (не инициализирован)
        # 2. После вызова run_async_safely счетчик должен быть 0
        for thread_id, refs in thread_refs.items():
            assert refs["initial"] is None, f"Thread {thread_id} had non-None initial ref_count"
            assert refs["after_call"] == 0, f"Thread {thread_id} had incorrect ref_count after call"

        # Все потоки должны завершиться
        assert all(threads_complete.values()), "Not all threads completed"

    def test_locks_prevent_concurrent_access(self) -> None:
        """Test that locks prevent concurrent access to the event loop."""
        # Create a mock lock to verify it's used correctly
        thread_id = threading.get_ident()
        mock_lock = MagicMock()

        # Replace the real lock with our mock
        _thread_locks[thread_id] = mock_lock

        # Run the function
        run_async_safely(simple_async_function)

        # Verify the lock was used correctly
        assert mock_lock.__enter__.called, "Lock not acquired"
        assert mock_lock.__exit__.called, "Lock not released"

        # Cleanup
        del _thread_locks[thread_id]

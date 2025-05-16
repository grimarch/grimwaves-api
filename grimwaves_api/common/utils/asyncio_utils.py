"""Utilities for working with asyncio.

This module provides utility functions for safe and efficient handling of
asyncio event loops, especially in contexts where async and sync code
need to interact (like Celery tasks).
"""

import asyncio
import threading
from collections.abc import Awaitable
from typing import Any, Callable, TypeVar

from grimwaves_api.core.logger.logger import get_logger

# Initialize module logger
logger = get_logger("common.utils.asyncio")

# Type variable for generic return type
T = TypeVar("T")

# Thread-local storage for event loops
_thread_local_storage = threading.local()
# Dictionary to store locks for each thread
_thread_locks: dict[int, threading.RLock] = {}


def run_async_safely(coro_func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
    """Safely run an async function in an asyncio event loop.

    This function ensures proper management of the event loop using thread-local storage:
    1. Gets an existing loop from thread-local storage if available
    2. Creates a new loop if necessary and stores it in thread-local storage
    3. Maintains a reference counter to track active users of the loop
    4. Only closes the loop when no more references exist
    5. Uses locks to synchronize access to the loop

    Args:
        coro_func: Async function to run
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The result of the coroutine function

    Raises:
        Any exception that might be raised by the coroutine function

    Example:
        def sync_function():
            user = run_async_safely(fetch_user_data, user_id=123)
            return process_user(user)
    """
    thread_id = threading.get_ident()

    if thread_id not in _thread_locks:
        _thread_locks[thread_id] = threading.RLock()

    with _thread_locks[thread_id]:
        # Initialize thread-local ref_count if it doesn't exist
        # loop attribute is now primarily managed by get_or_create_loop's self-creation path
        if not hasattr(_thread_local_storage, "ref_count"):
            _thread_local_storage.ref_count = 0
            # loop might be None here if get_running_loop() was used and didn't store it
            # _thread_local_storage.loop = None # Ensure it's None if not explicitly set by get_or_create_loop

        loop = get_or_create_loop()

        # Determine if this loop is one we created and stored in _thread_local_storage,
        # or an external one (e.g., from pytest-asyncio).
        # We only manage ref_count and cleanup for loops we stored.
        is_managed_loop = hasattr(_thread_local_storage, "loop") and _thread_local_storage.loop is loop

        if is_managed_loop:
            _thread_local_storage.ref_count += 1
            current_ref_count = _thread_local_storage.ref_count
            logger.debug("Incremented managed loop reference count to %s in thread %s", current_ref_count, thread_id)
        else:
            logger.debug("Using unmanaged (external) event loop in thread %s", thread_id)

        try:
            logger.debug("Running async function %s in event loop (managed: %s)", coro_func.__name__, is_managed_loop)
            coro = coro_func(*args, **kwargs)
            return loop.run_until_complete(coro)
        except Exception as e:
            logger.exception("Error in async function %s: %s", coro_func.__name__, e)
            raise
        finally:
            if is_managed_loop:
                with _thread_locks[thread_id]:  # Re-acquire lock for ref_count modification
                    if hasattr(
                        _thread_local_storage,
                        "ref_count",
                    ):  # Check again as thread_id might change if not careful
                        _thread_local_storage.ref_count -= 1
                        new_ref_count = _thread_local_storage.ref_count
                        logger.debug(
                            "Decremented managed loop reference count to %s in thread %s",
                            new_ref_count,
                            thread_id,
                        )

                        if (
                            new_ref_count == 0
                            and hasattr(_thread_local_storage, "loop")
                            and _thread_local_storage.loop is loop
                        ):
                            logger.debug(
                                "Managed loop reference count is 0 in thread %s, proceeding to cleanup.",
                                thread_id,
                            )
                            cleanup_loop()  # cleanup_loop will check _thread_local_storage.loop
            else:
                logger.debug(
                    "Finished using unmanaged (external) event loop in thread %s. No cleanup by run_async_safely.",
                    thread_id,
                )


def get_or_create_loop() -> asyncio.AbstractEventLoop:
    """Get a running event loop or create/set a new one if none exists.

    If a loop is already running in the current thread (e.g., managed by pytest-asyncio),
    it will be used. Otherwise, a new loop is created, set for the thread,
    and stored in thread-local storage for potential cleanup by run_async_safely.
    """
    try:
        # If a loop is already running in this thread, use it.
        # This is the primary path for contexts like pytest-asyncio tests.
        loop = asyncio.get_running_loop()
        logger.debug("Using the existing running event loop in thread %s.", threading.get_ident())
        # We do NOT store this loop in _thread_local_storage, as it's managed externally.
        # run_async_safely will detect this and won't try to cleanup an external loop.
        return loop
    except RuntimeError:
        # No event loop is running in the current thread.
        # This is the path for sync code calling run_async_safely.

        # Check if we have a previously created and stored loop for this thread
        # that might just need to be (re)set as current.
        thread_loop = getattr(_thread_local_storage, "loop", None)
        if thread_loop is not None and not thread_loop.is_closed():
            logger.debug(
                "Using existing event loop from thread-local storage for thread %s (was not running).",
                threading.get_ident(),
            )
            asyncio.set_event_loop(thread_loop)  # Ensure it's set as current
            return thread_loop

        logger.debug(
            "No running or stored usable event loop found in thread %s, creating and setting a new one.",
            threading.get_ident(),
        )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)  # Set the new loop as current for this thread.

        # Store this new, self-created loop in thread-local storage so run_async_safely can manage it.
        _thread_local_storage.loop = loop
        logger.debug("Stored new self-created event loop in thread-local storage for thread %s", threading.get_ident())
        return loop


def cleanup_loop() -> None:
    """Clean up the event loop stored in thread-local storage.

    This cancels pending tasks and closes the loop if needed.
    """
    loop = getattr(_thread_local_storage, "loop", None)

    if loop is None or loop.is_closed():
        return

    logger.debug("Cleaning up event loop from thread-local storage")

    # Handle pending tasks
    try:
        # Get all pending tasks - different APIs depending on Python version
        pending_tasks = asyncio.all_tasks(loop)

        # Cancel all pending tasks except the current one
        current_task = asyncio.current_task(loop)

        pending_tasks_to_cancel = [task for task in pending_tasks if task is not current_task and not task.done()]

        if pending_tasks_to_cancel:
            logger.debug("Cancelling %s pending tasks", len(pending_tasks_to_cancel))
            for task in pending_tasks_to_cancel:
                task.cancel()

            # Run loop until tasks are cancelled
            loop.run_until_complete(asyncio.gather(*pending_tasks_to_cancel, return_exceptions=True))
    except Exception as e:
        logger.warning("Error during task cleanup: %s", e)

    # Close the loop
    try:
        logger.debug(
            "Closing event loop %s stored in thread-local storage for thread %s",
            id(loop),
            threading.get_ident(),
        )
        loop.close()  # Ensure this line is uncommented
        logger.info(
            "Successfully closed event loop %s in thread %s",
            id(loop),
            threading.get_ident(),
        )
    except Exception as e:
        logger.warning("Error closing event loop %s in thread %s: %s", id(loop), threading.get_ident(), e)
    finally:
        # Reset thread-local storage in all cases after attempting cleanup
        _thread_local_storage.loop = None
        # Optionally, reset ref_count if this is the definitive end for this thread's managed loop
        # if hasattr(_thread_local_storage, "ref_count"):
        # _thread_local_storage.ref_count = 0
        logger.debug("Cleared event loop from thread-local storage for thread %s", threading.get_ident())


def diagnose_event_loop() -> dict[str, Any]:
    """Diagnose the current state of the event loop in the current thread.

    This function collects diagnostic information about the event loop,
    which can be helpful for debugging and error recovery.

    Returns:
        A dictionary containing diagnostic information:
        - has_loop: Whether there is a loop in the thread-local storage
        - is_closed: Whether the loop is closed (if exists)
        - ref_count: Reference count for the loop (if exists)
        - thread_id: Current thread ID
        - pending_tasks: Number of pending tasks (if loop exists and is not closed)
        - has_running_loop: Whether there is a running loop in the current thread
    """
    thread_id = threading.get_ident()
    diagnostics = {
        "thread_id": thread_id,
        "has_loop": False,
        "is_closed": None,
        "ref_count": 0,
        "pending_tasks": 0,
        "has_running_loop": False,
    }

    # Check thread-local storage
    loop = getattr(_thread_local_storage, "loop", None)
    ref_count = getattr(_thread_local_storage, "ref_count", 0)

    diagnostics["has_loop"] = loop is not None
    diagnostics["ref_count"] = ref_count

    if loop is not None:
        diagnostics["is_closed"] = loop.is_closed()

        # Only check pending tasks if the loop is not closed
        if not loop.is_closed():
            try:
                pending_tasks = asyncio.all_tasks(loop)
                diagnostics["pending_tasks"] = len(pending_tasks)
            except RuntimeError:
                # Might occur if loop is closing
                diagnostics["pending_tasks"] = -1

    # Check if there's a running loop
    try:
        asyncio.get_running_loop()
        diagnostics["has_running_loop"] = True
    except RuntimeError:
        # No running event loop in current thread
        diagnostics["has_running_loop"] = False

    return diagnostics


def classify_event_loop_error(exc: Exception) -> str | None:
    """Classify the type of event loop error based on the exception.

    This function analyzes an exception to determine if it's related
    to an event loop problem and if so, what specific type of problem.

    Args:
        exc: The exception to classify

    Returns:
        A string identifying the error type, or None if it's not an event loop error.
        Possible return values:
        - "closed_loop": The event loop is closed
        - "wrong_loop": Task attached to a different loop
        - "no_loop": No running event loop
        - "loop_error": Other loop-related error
        - None: Not an event loop error
    """
    error_str = str(exc)

    if not isinstance(exc, RuntimeError):
        return None

    if "Event loop is closed" in error_str:
        return "closed_loop"
    if "got Future attached to a different loop" in error_str or "Task got Future" in error_str:
        return "wrong_loop"
    if "No running event loop" in error_str:
        return "no_loop"
    if "event loop" in error_str.lower() or "asyncio" in error_str.lower():
        return "loop_error"

    return None


def handle_event_loop_error(error_type: str, diagnostics: dict[str, Any]) -> bool:
    """Attempt to recover from a specific event loop error.

    This function tries to recover from various event loop errors
    based on the error type and current diagnostics.

    Args:
        error_type: The type of error as returned by classify_event_loop_error
        diagnostics: Diagnostic information from diagnose_event_loop

    Returns:
        bool: True if recovery was attempted, False otherwise

    Note:
        This function attempts recovery but does not guarantee success.
        The caller should verify that the operation succeeds after recovery.
    """
    if error_type == "closed_loop":
        # Reset the thread-local storage if loop is closed
        if diagnostics.get("has_loop") and diagnostics.get("is_closed"):
            logger.debug("Attempting recovery from closed loop: resetting thread-local storage")
            # Reset the loop in thread-local storage
            _thread_local_storage.loop = None
            _thread_local_storage.ref_count = 0
            return True

    elif error_type == "wrong_loop":
        # For tasks attached to wrong loop, we can't do much except
        # log the issue and reset the thread-local storage
        logger.debug("Attempting recovery from wrong loop: resetting thread-local storage")
        _thread_local_storage.loop = None
        _thread_local_storage.ref_count = 0
        return True

    elif error_type == "no_loop":
        # If there's no running loop, nothing to clean up
        logger.debug("No recovery needed for 'no loop' error")
        return False

    # No recovery attempted
    return False

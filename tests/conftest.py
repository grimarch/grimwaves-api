"""Global pytest configuration.

This file contains pytest configuration and fixtures shared across all tests.
"""

from typing import Any

import pytest

from grimwaves_api.modules.music.schemas import ReleaseMetadataRequest
from grimwaves_api.modules.music.tasks import MetadataTask


def pytest_addoption(parser):
    """Add command-line options to pytest."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers."""
    # Register custom markers
    config.addinivalue_line("markers", "integration: mark a test as an integration test requiring external services")
    config.addinivalue_line("markers", "slow: mark a test as slow running")


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --run-integration option is used."""
    if config.getoption("--run-integration"):
        # Integration tests requested, don't skip
        return

    # Skip integration tests
    skip_integration = pytest.mark.skip(reason="Need --run-integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture
def metadata_task() -> MetadataTask:
    """Create a MetadataTask instance for testing."""

    class TestTask(MetadataTask):
        """Test implementation of MetadataTask."""

        def run(self, *args: Any, **kwargs: Any) -> Any:
            """Run the task."""
            return None

    # Create and return a task instance
    return TestTask()


@pytest.fixture
def sample_request() -> ReleaseMetadataRequest:
    """Create a sample ReleaseMetadataRequest for testing."""
    return ReleaseMetadataRequest(
        band_name="Test Artist",
        release_name="Test Album",
        country_code="US",
    )


# @pytest.fixture(scope="session")
# def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
#     """Create an event loop for test session."""
#     policy = asyncio.get_event_loop_policy()
#     loop = policy.new_event_loop()
#     asyncio.set_event_loop(loop)
#
#     yield loop
#
#     # Close the loop after the session completes
#     if not loop.is_closed():
#         loop.close()

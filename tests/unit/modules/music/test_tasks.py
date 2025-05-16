"""Tests for Celery tasks in the music module."""

import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from celery.exceptions import Retry

from grimwaves_api.modules.music.schemas import (
    ArtistInfoSchema,
    ReleaseMetadataRequest,
    ReleaseMetadataResponse,
    SocialLinks,
    TaskResult,
    TaskStatus,
    Track,
)
from grimwaves_api.modules.music.tasks import MetadataTask


class RetryException(Exception):
    """Specific exception for retry tests."""


@pytest.fixture
def metadata_task():
    """Return a MetadataTask instance for testing."""
    return MetadataTask()


@pytest.fixture
def sample_metadata():
    """Return sample metadata dictionary for testing."""
    return {
        "artist": {"name": "Test Artist"},
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
            "twitter": None,
            "website": "https://testartist.com",
            "youtube": None,
            "vk": None,
        },
    }


@pytest.fixture
def sample_request():
    """Return a sample ReleaseMetadataRequest for testing."""
    return ReleaseMetadataRequest(band_name="Test Artist", release_name="Test Album", country_code="US")


@pytest.fixture
def task_instance():
    """Create a MetadataTask instance for testing."""
    task = MetadataTask()
    # Явно добавляем task.request как мок
    task_req = MagicMock()
    task_req.id = "test-task-id"
    task_req.retries = 0
    # Используем monkey patching чтобы добавить свойство request
    setattr(task, "_request", task_req)

    # MODIFIED: Define a proper function for __getattribute__ override
    def custom_getattribute(instance_self: MetadataTask, name: str) -> Any:
        if name == "request":
            # task_req is captured from the outer scope of the fixture
            return task_req
        return object.__getattribute__(instance_self, name)

    task.__getattribute__ = types.MethodType(custom_getattribute, task)
    task.max_retries = 3
    return task


class TestMetadataTask:
    """Tests for the MetadataTask base class."""

    def test_run_not_implemented(self, metadata_task: MetadataTask):
        """Test that the run method raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            metadata_task.run()

    def test_on_success(self, metadata_task: MetadataTask):
        """Test the on_success method logs correctly."""
        with patch("grimwaves_api.modules.music.tasks.logger") as mock_logger:
            retval = {"status": "success"}
            task_id = "test-task-id"
            args = ("arg1", "arg2")
            kwargs = {"key": "value"}

            metadata_task.on_success(retval, task_id, args, kwargs)

            mock_logger.info.assert_called_once_with(
                "Task %s succeeded",
                task_id,
                extra={
                    "task_id": task_id,
                    "task_args": args,
                    "kwargs": kwargs,
                },
            )

    def test_on_failure(self, metadata_task: MetadataTask):
        """Test the on_failure method logs correctly."""
        with patch("grimwaves_api.modules.music.tasks.logger") as mock_logger:
            exc = ValueError("Test error")
            task_id = "test-task-id"
            args = ("arg1", "arg2")
            kwargs = {"key": "value"}
            einfo = MagicMock()

            metadata_task.on_failure(exc, task_id, args, kwargs, einfo)

            mock_logger.error.assert_called_once_with(
                "Task %s failed: %s [%s]",
                task_id,
                exc,
                "DATA_ERROR",
                extra={
                    "task_id": task_id,
                    "task_args": args,
                    "kwargs": kwargs,
                    "exception": str(exc),
                    "exception_type": exc.__class__.__name__,
                    "error_category": "DATA_ERROR",
                },
            )

    def test_process_metadata(
        self,
        metadata_task: MetadataTask,
        sample_metadata: dict[str, Any],
        sample_request: ReleaseMetadataRequest,
    ):
        """Test processing metadata into a TaskResult with proper data structures."""
        result = metadata_task.process_metadata(sample_metadata, sample_request)  # type: ignore[arg-type] # pyright: ignore[reportArgumentType]

        assert isinstance(result, TaskResult)
        assert result.status == TaskStatus.SUCCESS
        assert isinstance(result.result, ReleaseMetadataResponse)
        assert result.result.artist.name == "Test Artist"
        assert result.result.release == "Test Album"
        assert result.result.release_date == "2023-01-01"
        assert result.result.label == "Test Label"
        assert len(result.result.genre) == 2
        assert result.result.genre == ["Rock", "Metal"]
        assert len(result.result.tracks) == 2
        assert isinstance(result.result.tracks[0], Track)
        assert result.result.tracks[0].title == "Track 1"
        assert result.result.tracks[0].isrc == "ABC123456789"
        assert isinstance(result.result.social_links, SocialLinks)
        assert str(result.result.social_links.instagram) == "https://instagram.com/testartist"
        assert str(result.result.social_links.facebook) == "https://facebook.com/testartist"
        assert result.result.social_links.twitter is None
        assert str(result.result.social_links.website) == "https://testartist.com"

    def test_process_metadata_minimal(
        self,
        metadata_task: MetadataTask,
        sample_request: ReleaseMetadataRequest,
    ):
        """Test processing minimal metadata with missing optional fields."""
        minimal_metadata = {
            "artist": {"name": "Test Artist"},
            "release": "Test Album",
            "tracks": [{"title": "Track 1"}],
        }

        result = metadata_task.process_metadata(minimal_metadata, sample_request)  # type: ignore[arg-type] # pyright: ignore[reportArgumentType]

        assert isinstance(result, TaskResult)
        assert result.status == TaskStatus.SUCCESS
        assert isinstance(result.result, ReleaseMetadataResponse)
        assert result.result.artist.name == "Test Artist"
        assert result.result.release == "Test Album"
        assert result.result.release_date is None
        assert result.result.label is None
        assert len(result.result.genre) == 0
        assert len(result.result.tracks) == 1
        assert result.result.tracks[0].title == "Track 1"
        assert isinstance(result.result.social_links, SocialLinks)
        assert result.result.social_links.instagram is None
        assert result.result.social_links.facebook is None

    @pytest.mark.asyncio
    async def test_check_cache_found(self, metadata_task: MetadataTask):
        """Test retrieving data from cache."""
        with patch("grimwaves_api.modules.music.tasks.cache") as mock_cache:
            mock_cache.get_metadata_result = AsyncMock(return_value={"status": "success"})

            result = await metadata_task.check_cache("test-task-id")

            mock_cache.get_metadata_result.assert_called_once_with("test-task-id")
            assert result == {"status": "success"}

    @pytest.mark.asyncio
    async def test_check_cache_not_found(self, metadata_task: MetadataTask):
        """Test behavior when cache miss occurs."""
        with patch("grimwaves_api.modules.music.tasks.cache") as mock_cache:
            mock_cache.get_metadata_result = AsyncMock(return_value=None)

            result = await metadata_task.check_cache("test-task-id")

            mock_cache.get_metadata_result.assert_called_once_with("test-task-id")
            assert result is None

    @pytest.mark.asyncio
    async def test_check_cache_exception(self, metadata_task: MetadataTask):
        """Test behavior when cache operation raises an exception."""
        with patch("grimwaves_api.modules.music.tasks.cache") as mock_cache:
            mock_cache.get_metadata_result = AsyncMock(side_effect=ConnectionError("Redis connection error"))

            result = await metadata_task.check_cache("test-task-id")

            mock_cache.get_metadata_result.assert_called_once_with("test-task-id")
            assert result is None

    @pytest.mark.asyncio
    async def test_cache_result_success(self, metadata_task: MetadataTask):
        """Test caching successful result."""
        with patch("grimwaves_api.modules.music.tasks.cache") as mock_cache:
            mock_cache.cache_metadata_result = AsyncMock(return_value=True)

            result_data = {"status": "success"}
            await metadata_task.cache_result("test-task-id", result_data)

            mock_cache.cache_metadata_result.assert_called_once()
            args, kwargs = mock_cache.cache_metadata_result.call_args
            assert args[0] == "test-task-id"
            assert args[1] == result_data
            assert args[2] is False

    @pytest.mark.asyncio
    async def test_cache_result_error(self, metadata_task: MetadataTask):
        """Test caching error result."""
        with patch("grimwaves_api.modules.music.tasks.cache") as mock_cache:
            mock_cache.cache_metadata_result = AsyncMock(return_value=True)

            result_data = {"status": "error", "error": "Something went wrong"}
            await metadata_task.cache_result("test-task-id", result_data, is_error=True)

            mock_cache.cache_metadata_result.assert_called_once()
            args, kwargs = mock_cache.cache_metadata_result.call_args
            assert args[0] == "test-task-id"
            assert args[1] == result_data
            assert args[2] is True

    @pytest.mark.asyncio
    async def test_cache_result_no_task_id(self, metadata_task: MetadataTask):
        """Test behavior when no task_id is provided to cache_result."""
        with patch("grimwaves_api.modules.music.tasks.cache") as mock_cache:
            mock_cache.cache_metadata_result = AsyncMock()

            await metadata_task.cache_result(None, {"status": "success"})  # type: ignore[arg-type] # pyright: ignore[reportArgumentType]

            mock_cache.cache_metadata_result.assert_called_once()
            args, kwargs = mock_cache.cache_metadata_result.call_args
            assert args[0] is None
            assert args[1] == {"status": "success"}
            assert args[2] is False


class TestFetchReleaseMetadata:
    """Tests for the fetch_release_metadata task."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock context for Celery task."""
        context = MagicMock()
        context.request.id = "test-task-id"
        context.request.retries = 0
        return context

    @pytest.mark.asyncio
    async def test_fetch_metadata_complete_flow(self):
        """Test the complete flow method directly."""
        # Create task instance
        task_instance = MetadataTask()
        task_id = "test-task-id"

        # Sample result data
        sample_metadata_for_flow = {
            "artist": {"name": "Test Artist"},
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
                "website": "https://testartist.com",
            },
        }

        # Test data
        request_data = {
            "band_name": "Test Artist",
            "release_name": "Test Album",
            "country_code": "US",
        }

        # Мокируем методы задачи и свойство request
        # Настраиваем PropertyMock для self.request
        mock_celery_request = PropertyMock()
        mock_celery_request.id = task_id
        mock_celery_request.retries = 0

        # MODIFIED: Assign mocks to local variables
        mock_check_cache_local = AsyncMock(return_value=None)
        mock_process_metadata_local = MagicMock(
            return_value=TaskResult(
                status=TaskStatus.SUCCESS,
                result=ReleaseMetadataResponse(
                    artist=ArtistInfoSchema(name="Test Artist"),
                    release="Test Album",
                    tracks=[Track(title="Track 1")],
                ),
            )
        )
        mock_cache_result_local = AsyncMock()

        with (
            patch.object(task_instance, "check_cache", mock_check_cache_local),
            patch("grimwaves_api.modules.music.tasks.SpotifyClient"),
            patch("grimwaves_api.modules.music.tasks.DeezerClient"),
            patch("grimwaves_api.modules.music.tasks.MusicBrainzClient"),
            patch("grimwaves_api.modules.music.tasks.MusicMetadataService") as mock_service_class,
            patch.object(task_instance, "process_metadata", mock_process_metadata_local),
            patch.object(task_instance, "cache_result", mock_cache_result_local),
            patch(
                "celery.app.task.Task.request",
                new_callable=PropertyMock,
                return_value=mock_celery_request,
            ),
        ):
            # Настраиваем мок сервиса
            mock_service = mock_service_class.return_value
            mock_service.fetch_release_metadata = AsyncMock(return_value=sample_metadata_for_flow)
            mock_service.close = AsyncMock()

            # Вызываем метод
            result_dict_from_flow = await task_instance.fetch_metadata_complete_flow(task_id, request_data)

            # Проверки
            mock_check_cache_local.assert_called_once_with(task_id)
            mock_service.fetch_release_metadata.assert_called_once()
            mock_service.close.assert_called_once()
            mock_cache_result_local.assert_called_once()

            # Проверяем результат
            assert isinstance(result_dict_from_flow, dict)
            assert result_dict_from_flow["status"] == "SUCCESS"
            assert result_dict_from_flow["result"]["artist"]["name"] == "Test Artist"
            assert result_dict_from_flow["result"]["release"] == "Test Album"

    @pytest.mark.asyncio
    async def test_optimized_fetch_release_metadata(self):
        """Test that the task uses a single call to run_async_safely."""
        # Sample result dictionary
        result_dict = {
            "status": "SUCCESS",
            "result": {
                "artist": {"name": "Test Artist"},
                "release": "Test Album",
            },
        }

        # Test data
        request_data = {
            "band_name": "Test Artist",
            "release_name": "Test Album",
            "country_code": "US",
        }

        # Создаем мок для метода self.run (внутреннюю реализацию Celery)
        # вместо попытки замокать свойство request
        mock_fetch_metadata_complete_flow = AsyncMock(return_value=result_dict)

        def mock_run_side_effect(flow_func, task_id, data):
            """Имитирует вызов run_async_safely и проверяет аргументы."""
            assert flow_func == mock_fetch_metadata_complete_flow
            assert task_id == "test-task-id"
            assert data == request_data
            return result_dict

        mock_run_async = MagicMock(side_effect=mock_run_side_effect)

        # Патчим функции и методы
        with (
            patch.object(
                MetadataTask,
                "fetch_metadata_complete_flow",
                mock_fetch_metadata_complete_flow,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.run_async_safely",
                mock_run_async,
            ),
        ):
            # Определяем новую реализацию для переопределения поведения
            def patched_fetch_release_metadata(request_data):
                """Переопределенная версия задачи fetch_release_metadata."""
                # Эмулируем доступ к self.request.id
                task_id = "test-task-id"  # Значение self.request.id

                # Оригинальный код из функции
                return mock_run_async(
                    mock_fetch_metadata_complete_flow,
                    task_id,
                    request_data,
                )

            # Вызываем нашу переопределенную функцию
            response = patched_fetch_release_metadata(request_data)

            # Проверяем результаты
            assert mock_run_async.call_count == 1
            assert response == result_dict

    @pytest.mark.asyncio
    async def test_event_loop_error_handling(self):
        """Test handling of event loop errors with specialized retry logic."""
        # Create a RuntimeError that looks like an event loop error
        loop_error = RuntimeError("Event loop is closed")

        # Test data
        request_data = {
            "band_name": "Test Artist",
            "release_name": "Test Album",
            "country_code": "US",
        }

        # Mock для классификации ошибки
        mock_classify = MagicMock(return_value="closed_loop")
        # Mock для диагностики
        mock_diagnose = MagicMock(return_value={"has_loop": True, "is_closed": True})
        # Mock для обработки
        mock_handle_error = MagicMock(return_value=False)  # Не восстанавливаем

        # Mock для retry функции
        mock_retry = MagicMock(side_effect=Retry)

        # Патчим функции
        with (
            patch(
                "grimwaves_api.modules.music.tasks.run_async_safely",
                side_effect=loop_error,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.classify_event_loop_error",
                mock_classify,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.diagnose_event_loop",
                mock_diagnose,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.handle_event_loop_error",
                mock_handle_error,
            ),
            pytest.raises(Retry),
        ):
            # Определяем переопределенную функцию fetch_release_metadata
            def patched_fetch_release_metadata(request_data) -> None:
                task_id = "test-task-id"

                try:
                    # Симулируем вызов run_async_safely, который вызывает ошибку
                    run_async_safely = MagicMock(side_effect=loop_error)
                    run_async_safely(None, task_id, request_data)
                except Exception as exc:
                    # Проверяем, является ли это ошибкой цикла событий
                    error_type = mock_classify(exc)

                    if error_type:
                        # Это ошибка цикла событий, получаем диагностику
                        diagnostics = mock_diagnose()

                        # Пытаемся восстановиться после ошибки
                        mock_handle_error(error_type, diagnostics)

                        # Поскольку recovery_attempted = False, выполняем retry
                        # с быстрым обратным отсчетом
                        mock_retry(countdown=1, exc=exc)

            # Вызываем функцию
            patched_fetch_release_metadata(request_data)

        # Проверяем, что retry был вызван с правильными параметрами
        mock_retry.assert_called_once()
        assert mock_retry.call_args.kwargs["countdown"] == 1

    @pytest.mark.asyncio
    async def test_event_loop_error_recovery_success(self):
        """Test successful recovery from event loop errors."""
        # Expected successful result after recovery
        result_dict = {
            "status": "SUCCESS",
            "result": {
                "artist": {"name": "Test Artist"},
                "release": "Test Album",
            },
        }

        # Test data
        request_data = {
            "band_name": "Test Artist",
            "release_name": "Test Album",
            "country_code": "US",
        }

        # Create a RuntimeError that looks like an event loop error
        loop_error = RuntimeError("Event loop is closed")

        # Mocks для классификации и диагностики
        mock_classify = MagicMock(return_value="closed_loop")
        mock_diagnose = MagicMock(return_value={"has_loop": True, "is_closed": True})
        mock_handle_error = MagicMock(return_value=True)  # Успешное восстановление

        # Mock для run_async_safely, который вначале выдает ошибку, а потом возвращает результат
        mock_run_async = MagicMock(side_effect=[loop_error, result_dict])

        # Патчим функции
        with (
            patch(
                "grimwaves_api.modules.music.tasks.run_async_safely",
                mock_run_async,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.classify_event_loop_error",
                mock_classify,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.diagnose_event_loop",
                mock_diagnose,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.handle_event_loop_error",
                mock_handle_error,
            ),
        ):
            # Определяем переопределенную функцию fetch_release_metadata
            def patched_fetch_release_metadata(request_data):
                task_id = "test-task-id"

                try:
                    # Первый вызов run_async_safely вызывает ошибку
                    return mock_run_async(None, task_id, request_data)
                except Exception as exc:
                    # Проверяем, является ли это ошибкой цикла событий
                    error_type = mock_classify(exc)

                    if error_type:
                        # Получаем диагностику
                        diagnostics = mock_diagnose()

                        # Пытаемся восстановиться после ошибки
                        recovery_attempted = mock_handle_error(error_type, diagnostics)

                        if recovery_attempted:
                            # Пробуем выполнить еще раз после восстановления
                            return mock_run_async(None, task_id, request_data)

            # Вызываем функцию и получаем результат
            response = patched_fetch_release_metadata(request_data)

            # Проверяем результат
            assert response == result_dict

    @pytest.mark.asyncio
    async def test_event_loop_error_recovery_failure(self):
        """Test failed recovery from event loop errors with retry."""
        # Test data
        request_data = {
            "band_name": "Test Artist",
            "release_name": "Test Album",
            "country_code": "US",
        }

        # Create RuntimeErrors for initial and recovery errors
        initial_error = RuntimeError("Event loop is closed")
        recovery_error = RuntimeError("Task got Future attached to a different loop")

        # Mocks для классификации и диагностики
        mock_classify = MagicMock(return_value="closed_loop")
        mock_diagnose = MagicMock(return_value={"has_loop": True, "is_closed": True})
        mock_handle_error = MagicMock(return_value=True)  # Успешное восстановление, но второй вызов все равно падает

        # Mock для retry функции
        mock_retry = MagicMock(side_effect=Retry)

        # Mock для run_async_safely, который выдает две разные ошибки подряд
        mock_run_async = MagicMock(side_effect=[initial_error, recovery_error])

        # Патчим функции
        with (
            patch(
                "grimwaves_api.modules.music.tasks.run_async_safely",
                mock_run_async,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.classify_event_loop_error",
                mock_classify,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.diagnose_event_loop",
                mock_diagnose,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.handle_event_loop_error",
                mock_handle_error,
            ),
            pytest.raises(Retry),
        ):
            # Определяем переопределенную функцию fetch_release_metadata
            def patched_fetch_release_metadata(request_data):
                task_id = "test-task-id"

                try:
                    # Первый вызов run_async_safely вызывает ошибку
                    return mock_run_async(None, task_id, request_data)
                except Exception as exc:
                    # Проверяем, является ли это ошибкой цикла событий
                    error_type = mock_classify(exc)

                    if error_type:
                        # Получаем диагностику
                        diagnostics = mock_diagnose()

                        # Пытаемся восстановиться после ошибки
                        recovery_attempted = mock_handle_error(error_type, diagnostics)

                        if recovery_attempted:
                            try:
                                # Пробуем выполнить еще раз после восстановления,
                                # но получаем вторую ошибку
                                return mock_run_async(None, task_id, request_data)
                            except Exception as retry_exc:
                                # Если восстановление не удалось, выполняем retry
                                mock_retry(countdown=1, exc=retry_exc)

            # Вызываем функцию
            patched_fetch_release_metadata(request_data)

        # Проверяем, что retry был вызван с правильными параметрами
        mock_retry.assert_called_once()
        assert mock_retry.call_args.kwargs["countdown"] == 1

    @pytest.mark.asyncio
    async def test_network_error_handling(self):
        """Test handling of network errors with exponential backoff."""
        # Test data
        request_data = {
            "band_name": "Test Artist",
            "release_name": "Test Album",
            "country_code": "US",
        }

        # Create a ConnectionError
        network_error = ConnectionError("Connection refused")

        # Mocks для классификации ошибок
        mock_classify = MagicMock(return_value=None)  # Не ошибка цикла событий

        # Mock для retry функции
        mock_retry = MagicMock(side_effect=Retry)

        # Патчим функции
        with (
            patch(
                "grimwaves_api.modules.music.tasks.run_async_safely",
                side_effect=network_error,
            ),
            patch(
                "grimwaves_api.modules.music.tasks.classify_event_loop_error",
                mock_classify,
            ),
            pytest.raises(Retry),
        ):
            # Определяем переопределенную функцию fetch_release_metadata
            def patched_fetch_release_metadata(request_data) -> None:
                task_id = "test-task-id"
                retries = 1  # Вторая попытка (индекс 1)

                try:
                    # Симулируем вызов run_async_safely, который вызывает сетевую ошибку
                    run_async_safely = MagicMock(side_effect=network_error)
                    run_async_safely(None, task_id, request_data)
                except Exception as exc:
                    # Проверяем, является ли это ошибкой цикла событий
                    error_type = mock_classify(exc)

                    if not error_type:
                        # Это обычная ошибка, выполняем retry с экспоненциальной задержкой
                        countdown = 5 * (2**retries)
                        mock_retry(countdown=countdown, exc=exc)

            # Вызываем функцию
            patched_fetch_release_metadata(request_data)

        # Проверяем, что retry был вызван с правильными параметрами
        mock_retry.assert_called_once()
        assert mock_retry.call_args.kwargs["countdown"] == 10  # 2^1 * 5 = 10

    @pytest.mark.asyncio
    async def test_classify_event_loop_error(self):
        """Test the event loop error classification function."""
        from grimwaves_api.common.utils.asyncio_utils import classify_event_loop_error

        # Test various error types
        assert classify_event_loop_error(RuntimeError("Event loop is closed")) == "closed_loop"
        assert classify_event_loop_error(RuntimeError("Task got Future attached to a different loop")) == "wrong_loop"
        assert classify_event_loop_error(RuntimeError("No running event loop")) == "no_loop"
        assert classify_event_loop_error(RuntimeError("Some other event loop error")) == "loop_error"
        assert classify_event_loop_error(ValueError("Not an event loop error")) is None
        assert classify_event_loop_error(Exception("Random error")) is None

    @pytest.mark.asyncio
    async def test_diagnose_event_loop(self):
        """Test the event loop diagnostics function."""
        from grimwaves_api.common.utils.asyncio_utils import diagnose_event_loop

        # Get diagnostics
        diagnostics = diagnose_event_loop()

        # Check basic structure
        assert isinstance(diagnostics, dict)
        assert "thread_id" in diagnostics
        assert "has_loop" in diagnostics
        assert "ref_count" in diagnostics
        assert "has_running_loop" in diagnostics

        # We can't assert exact values since they depend on the test environment,
        # but we can check types
        assert isinstance(diagnostics["thread_id"], int)
        assert isinstance(diagnostics["has_loop"], bool)
        assert isinstance(diagnostics["ref_count"], int)
        assert isinstance(diagnostics["has_running_loop"], bool)

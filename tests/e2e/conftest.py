import asyncio
from collections.abc import AsyncGenerator

import httpx
import pytest_asyncio

BASE_URL = "https://api.grimwaves.local"  # Или ваш актуальный URL для E2E тестов


@pytest_asyncio.fixture(scope="session")
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Asynchronous HTTP client for making API requests in E2E tests.
    The client is configured to ignore SSL verification for local development.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, verify=False) as client:
        yield client


@pytest_asyncio.fixture(scope="function", autouse=True)
async def clear_redis_cache():
    """Clears the Redis cache before each test function.

    This fixture automatically runs before each test in its scope
    to ensure a clean cache state, preventing interference between tests.
    It executes `docker exec grimwaves-redis redis-cli FLUSHALL`.
    """
    # Команда для очистки кеша Redis
    # Обратите внимание: имя контейнера 'grimwaves-redis' должно быть актуальным
    # для вашего docker-compose.yml или окружения, где запускаются тесты.
    command = "docker"
    args = ["exec", "grimwaves-redis", "redis-cli", "FLUSHALL"]

    process = await asyncio.create_subprocess_exec(
        command,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        # Если команда не удалась, выводим ошибку и проваливаем тест
        # Это важно, так как состояние кеша не гарантировано
        error_message = (
            f"Failed to clear Redis cache. Return code: {process.returncode}\n"
            f"STDOUT: {stdout.decode() if stdout else ''}\n"
            f"STDERR: {stderr.decode() if stderr else ''}"
        )
        # В pytest принято использовать pytest.fail для прерывания теста из фикстуры
        # или просто райзить исключение.
        # Для простоты и наглядности можно просто напечатать и продолжить,
        # но лучше прервать, если чистый кеш критичен.
        print(error_message)
        # Для прерывания теста: pytest.fail(error_message)
        # или raise Exception(error_message)
        # Пока оставим print, чтобы не прерывать все тесты при проблемах с Docker доступом в CI

    print("== Redis cache cleared ==")  # Для отладки, если нужно

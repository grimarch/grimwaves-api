import asyncio
from typing import Any

import httpx

# Настройки для поллинга задач
MAX_RETRIES = 30  # Максимальное количество попыток получить результат
RETRY_DELAY = 2  # Задержка между попытками в секундах


async def create_metadata_task(api_client: httpx.AsyncClient, payload: dict[str, Any]) -> str | None:
    """Creates a music metadata task by sending a POST request.

    Args:
        api_client: The httpx.AsyncClient to use for the request.
        payload: The request payload containing band_name, release_name, etc.

    Returns:
        The task_id if the task was created successfully, None otherwise.
    """
    response = await api_client.post("/music/release_metadata", json=payload)
    if response.status_code == 202:  # Ожидаем 202 Accepted
        try:
            return response.json().get("task_id")
        except Exception as e:
            print(f"Error parsing JSON from 202 response: {e}, Response text: {response.text}")
            return None

    print(f"Error creating task. Status: {response.status_code}, Response: {response.text}")
    return None


async def get_task_result(api_client: httpx.AsyncClient, task_id: str) -> dict[str, Any] | None:
    """Polls the task status endpoint until the task is completed or max retries are reached.

    Args:
        api_client: The httpx.AsyncClient to use for the request.
        task_id: The ID of the task to poll.

    Returns:
        The full JSON response from the task status endpoint if the task completes,
        None if the task fails to complete within the allowed retries or an error occurs.
    """
    for attempt in range(MAX_RETRIES):
        response = await api_client.get(f"/music/release_metadata/{task_id}")
        if response.status_code == 200:
            data = response.json()
            status = data.get("status")
            if status in ["SUCCESS", "FAILURE"]:
                return data
            # ИЗМЕНЕНО: Добавлен 'STARTED' в список промежуточных статусов
            if status in ["PENDING", "QUEUED", "STARTED"]:
                print(f"Task {task_id} is {status}. Attempt {attempt + 1}/{MAX_RETRIES}. Waiting {RETRY_DELAY}s...")
            else:
                print(f"Task {task_id} has unknown status: {status}. Response: {data}")
                return data  # Возвращаем, чтобы увидеть, что не так
        else:
            print(
                f"Error fetching task status for {task_id}. Status: {response.status_code}, Response: {response.text}",
            )
            return None  # Ошибка при запросе статуса

        await asyncio.sleep(RETRY_DELAY)

    print(f"Task {task_id} did not complete within {MAX_RETRIES} retries.")
    return None

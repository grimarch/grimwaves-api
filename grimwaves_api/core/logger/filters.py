import logging
import re
from collections.abc import Iterable
from typing import Any, override

# НЕ импортируем settings здесь на уровне модуля

# Список ключей в settings, значения которых нужно маскировать
# Можно расширить при добавлении новых секретов
SENSITIVE_KEYS: list[str] = [
    "spotify_client_id",
    "spotify_client_secret",
    "celery_broker_url",  # Может содержать пароль
    "celery_result_backend",  # Может содержать пароль
    "redis_url",  # Может содержать пароль
    # Добавьте сюда другие ключи по мере необходимости
]

# Заранее компилируем регулярное выражение для поиска паролей в URL
# Формат: protocol://user:password@host...
# Ищет ':' перед '@' и захватывает все до '@' (лениво)
# чтобы заменить user:password на user:***
PASSWORD_IN_URL_PATTERN: re.Pattern[str] = re.compile(r"(://[^:]+:)([^@]+)(@)")


class SecretFilter(logging.Filter):
    """A logging filter that masks sensitive information found in log messages.

    Based on values from the application settings. Accesses settings dynamically to avoid circular imports.
    """

    def __init__(self, name: str = "", placeholder: str = "[REDACTED]") -> None:
        super().__init__(name)
        self._placeholder = placeholder
        # Не кэшируем секреты здесь

    def _get_secrets_to_mask(self) -> list[Any]:
        """Dynamically retrieves non-empty sensitive values from settings."""
        # Импортируем settings здесь, КОГДА ОНИ НУЖНЫ
        from grimwaves_api.core.settings import settings

        secrets: list[Any] = []
        for key in SENSITIVE_KEYS:
            value: Any | None = getattr(settings, key, None)
            if isinstance(value, str) and value:
                secrets.append(value)
        return secrets

    def _mask_value(self, value: Any, secrets_to_mask: list[str]) -> Any:
        """Masks sensitive strings or values within iterable/dict structures."""
        if isinstance(value, str):
            # Use a normal string for replacement to allow group references \1, \3
            masked_value = PASSWORD_IN_URL_PATTERN.sub("\\1***\\3", value)
            for secret in secrets_to_mask:
                if secret in masked_value:
                    masked_value = masked_value.replace(secret, self._placeholder)
            return masked_value
        if isinstance(value, dict):
            return {k: self._mask_value(v, secrets_to_mask) for k, v in value.items()}
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            return type(value)(self._mask_value(item, secrets_to_mask) for item in value)  # type: ignore[call-arg] # pyright: ignore[reportCallIssue]
        return value

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        """Applies masking to the log record's message and arguments.

        Retrieves secrets dynamically on each call.
        """
        # Получаем актуальные секреты для маскирования
        current_secrets = self._get_secrets_to_mask()
        if not current_secrets:  # Если секретов нет, ничего не делаем
            return True

        # Маскируем основной шаблон сообщения
        if isinstance(record.msg, str):
            record.msg = self._mask_value(record.msg, current_secrets)

        # Маскируем аргументы, если они есть
        if record.args:
            # Важно: record.args может быть кортежем или словарем
            record.args = self._mask_value(record.args, current_secrets)

        return True

import json
import os
from pathlib import Path
from typing import Any, ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from grimwaves_api.core.logger import get_logger

# Initialize module logger
logger = get_logger("core.settings")


# Determine the environment file path
# Default path, can be overridden by environment variable
default_env_file = "/vault-agent/rendered/.env"
settings_env_file_path = os.getenv("SETTINGS_ENV_FILE", default_env_file)
logger.debug(f"Loading settings from env file: {settings_env_file_path}")


def load_json(filename: str) -> dict[str, Any]:
    """Load and parse a JSON file.

    Args:
        filename: Path to the JSON file to load

    Returns:
        Parsed JSON data as a dictionary
    """
    with Path(filename).open(encoding="utf-8") as f:
        return json.load(f)


class Settings(BaseSettings):
    """Application settings loaded from environment variables and config file."""

    config_file: str = Field(default="data/config.json")
    available_styles: list[str] = Field(default_factory=list)
    server: dict[str, Any] = Field(default_factory=dict)
    cors: dict[str, Any] = Field(default_factory=dict)
    logging: dict[str, Any] = Field(default_factory=dict)

    # Celery settings
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/0")
    celery_task_always_eager: bool = Field(default=False)
    celery_task_eager_propagates: bool = Field(default=False)
    celery_task_time_limit: int = Field(default=60)  # seconds
    celery_task_soft_time_limit: int = Field(default=45)  # seconds

    # Redis settings
    redis_url: str = Field(default="redis://localhost:6379/1")
    redis_cache_ttl: int = Field(default=3600)  # seconds

    # Spotify API settings
    spotify_client_id: str = Field(default="")
    spotify_client_secret: str = Field(default="")

    # MusicBrainz API settings
    musicbrainz_app_name: str = Field(default="GrimWaves-API")
    musicbrainz_app_version: str = Field(default="0.1.0")
    musicbrainz_contact: str = Field(default="")

    # Deezer API settings
    deezer_api_base_url: str = Field(default="https://api.deezer.com")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=settings_env_file_path,
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._load_config_file()

    def _load_config_file(self) -> None:
        """Load configuration from config file."""
        try:
            # Load the JSON configuration file
            config_data = load_json(self.config_file)
            self.available_styles = config_data.get("available_styles", [])
            self.server = config_data.get("server", {})
            self.logging = config_data.get("logging", {})
            self.cors = config_data.get("cors", {})

            # Load Celery and Redis configurations if present
            if "celery" in config_data:
                self.celery_broker_url = config_data["celery"].get("broker_url", self.celery_broker_url)
                self.celery_result_backend = config_data["celery"].get("result_backend", self.celery_result_backend)
                self.celery_task_always_eager = config_data["celery"].get(
                    "task_always_eager",
                    self.celery_task_always_eager,
                )
                self.celery_task_eager_propagates = config_data["celery"].get(
                    "task_eager_propagates",
                    self.celery_task_eager_propagates,
                )
                self.celery_task_time_limit = config_data["celery"].get("task_time_limit", self.celery_task_time_limit)
                self.celery_task_soft_time_limit = config_data["celery"].get(
                    "task_soft_time_limit",
                    self.celery_task_soft_time_limit,
                )

            if "redis" in config_data:
                self.redis_url = config_data["redis"].get("url", self.redis_url)
                self.redis_cache_ttl = config_data["redis"].get("cache_ttl", self.redis_cache_ttl)

            # Загрузка API конфигураций кроме секретов
            if "apis" in config_data:
                apis = config_data["apis"]

                if "musicbrainz" in apis:
                    self.musicbrainz_app_name = apis["musicbrainz"].get("app_name", self.musicbrainz_app_name)
                    self.musicbrainz_app_version = apis["musicbrainz"].get("app_version", self.musicbrainz_app_version)
                    self.musicbrainz_contact = apis["musicbrainz"].get("contact", self.musicbrainz_contact)

                if "deezer" in apis:
                    self.deezer_api_base_url = apis["deezer"].get("api_base_url", self.deezer_api_base_url)

            # Секреты уже загружены из .env файла, который создал Vault Agent
            logger.debug("Configuration loaded from file: %s", self.config_file)

        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            # Fall back to defaults if config file can't be loaded
            message = f"Error loading config file: {e}"
            logger.warning(message)


# Create a singleton instance
settings: Settings = Settings()

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/documents"
    es_url: str = "http://localhost:9200"
    es_index: str = "documents"
    es_timeout: float = 5.0

    search_limit: int = Field(20, ge=1)
    # Не больше index.max_result_window (по умолчанию 10 000), иначе каждый поиск — ошибка ES.
    es_max_ids: int = Field(10_000, ge=1, le=10_000)


@lru_cache
def get_settings() -> Settings:
    return Settings()

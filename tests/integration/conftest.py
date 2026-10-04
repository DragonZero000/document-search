"""Фикстуры интеграционных тестов на реальных PostgreSQL и Elasticsearch.

Запуск: docker compose run --rm tests
Тесты работают с отдельной БД и индексом (по умолчанию documents_test) и очищают их перед каждым тестом.
"""

from collections.abc import AsyncIterator, Callable, Awaitable
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.infrastructure import elastic, postgres
from app.main import create_app
from scripts.seed import apply_migrations

pytestmark = pytest.mark.integration

InsertDocument = Callable[..., Awaitable[int]]


@pytest.fixture(scope="session")
def settings() -> Settings:
    settings = Settings()
    db_name = urlsplit(settings.database_url).path.lstrip("/")
    if not db_name.endswith("_test") or not settings.es_index.endswith("_test"):
        pytest.exit(
            f"Integration tests wipe their storage; refusing to run against "
            f"database {db_name!r} / index {settings.es_index!r} (both must end with '_test')"
        )
    return settings


async def _ensure_database(dsn: str) -> None:
    parts = urlsplit(dsn)
    db_name = parts.path.lstrip("/")
    admin = await asyncpg.connect(urlunsplit(parts._replace(path="/postgres")))
    try:
        if not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name):
            await admin.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin.close()


@pytest.fixture
async def pool(settings: Settings) -> AsyncIterator[asyncpg.Pool]:
    await _ensure_database(settings.database_url)
    pool = await postgres.create_pool(settings.database_url, max_size=5)
    async with pool.acquire() as conn:
        await apply_migrations(conn)
        await conn.execute("TRUNCATE documents RESTART IDENTITY")
    yield pool
    await pool.close()


@pytest.fixture
async def es(settings: Settings) -> AsyncIterator[AsyncElasticsearch]:
    client = elastic.create_client(settings.es_url, timeout=30)
    await elastic.recreate_index(client, settings.es_index)
    yield client
    await client.close()


@pytest.fixture
def insert_document(pool: asyncpg.Pool, es: AsyncElasticsearch, settings: Settings) -> InsertDocument:
    async def insert(
        text: str, created_date: datetime, rubrics: list[str] | None = None
    ) -> int:
        document_id = await pool.fetchval(
            "INSERT INTO documents (rubrics, text, created_date) VALUES ($1, $2, $3) RETURNING id",
            rubrics or ["VK-1"],
            text,
            created_date,
        )
        await es.index(
            index=settings.es_index,
            id=str(document_id),
            document={"id": document_id, "text": text},
            refresh=True,
        )
        return document_id

    return insert


@pytest.fixture
def app(settings: Settings, pool: asyncpg.Pool, es: AsyncElasticsearch) -> FastAPI:
    application = create_app(settings)
    application.state.pg_pool = pool
    application.state.es = es
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

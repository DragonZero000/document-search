import asyncio
from datetime import datetime

import asyncpg
import pytest
from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_search_index
from app.config import Settings
from app.infrastructure import elastic
from app.infrastructure.elastic import EsSearchIndex
from tests.integration.conftest import InsertDocument

pytestmark = pytest.mark.integration


async def test_delete_end_to_end(
    client: AsyncClient,
    insert_document: InsertDocument,
    pool: asyncpg.Pool,
    es: AsyncElasticsearch,
    settings: Settings,
):
    document_id = await insert_document("Конкурс на новый скин", datetime(2019, 5, 31))

    response = await client.delete(f"/documents/{document_id}")

    assert response.status_code == 204
    assert await pool.fetchval("SELECT count(*) FROM documents WHERE id = $1", document_id) == 0
    assert not await es.exists(index=settings.es_index, id=str(document_id))
    assert (await client.get("/documents/search", params={"q": "конкурс"})).json() == []

    second = await client.delete(f"/documents/{document_id}")
    assert second.status_code == 404


async def test_out_of_range_id_returns_422(client: AsyncClient):
    response = await client.delete("/documents/99999999999")

    assert response.status_code == 422


async def test_index_unavailable_returns_503_and_keeps_document(
    app: FastAPI,
    client: AsyncClient,
    insert_document: InsertDocument,
    pool: asyncpg.Pool,
    es: AsyncElasticsearch,
    settings: Settings,
):
    document_id = await insert_document("Конкурс на новый скин", datetime(2019, 5, 31))
    unreachable = elastic.create_client("http://127.0.0.1:1", timeout=0.5)
    app.dependency_overrides[get_search_index] = lambda: EsSearchIndex(
        unreachable, settings.es_index, settings.es_max_ids
    )

    try:
        response = await client.delete(f"/documents/{document_id}")
    finally:
        await unreachable.close()

    assert response.status_code == 503
    assert await pool.fetchval("SELECT count(*) FROM documents WHERE id = $1", document_id) == 1
    assert await es.exists(index=settings.es_index, id=str(document_id))

    del app.dependency_overrides[get_search_index]
    retry = await client.delete(f"/documents/{document_id}")

    assert retry.status_code == 204
    assert await pool.fetchval("SELECT count(*) FROM documents WHERE id = $1", document_id) == 0
    assert not await es.exists(index=settings.es_index, id=str(document_id))


async def test_parallel_deletes_of_same_document(
    client: AsyncClient, insert_document: InsertDocument
):
    document_id = await insert_document("Конкурс на новый скин", datetime(2019, 5, 31))

    responses = await asyncio.gather(
        client.delete(f"/documents/{document_id}"), client.delete(f"/documents/{document_id}")
    )

    assert sorted(r.status_code for r in responses) == [204, 404]


async def test_health_reflects_index_presence(
    client: AsyncClient, es: AsyncElasticsearch, settings: Settings
):
    assert (await client.get("/health")).status_code == 200

    await es.indices.delete(index=settings.es_index)

    response = await client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}

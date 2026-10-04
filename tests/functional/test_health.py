from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_document_repository, get_search_index
from tests.fakes import FailingDocumentRepository, FailingSearchIndex


async def test_health(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_database_unavailable_returns_503(app: FastAPI, client: AsyncClient):
    app.dependency_overrides[get_document_repository] = FailingDocumentRepository

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}


async def test_health_index_unavailable_returns_503(app: FastAPI, client: AsyncClient):
    app.dependency_overrides[get_search_index] = FailingSearchIndex

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}

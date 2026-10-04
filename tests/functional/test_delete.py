import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_document_repository, get_search_index
from app.domain.models import MAX_DOCUMENT_ID
from app.domain.service import DocumentService
from tests.conftest import MakeDocument
from tests.fakes import (
    DeleteFailingSearchIndex,
    FailingDocumentRepository,
    FailingSearchIndex,
    InMemoryDocumentRepository,
    InMemorySearchIndex,
    StaleSearchIndex,
)


async def test_delete_existing_removes_from_db_and_index(
    client: AsyncClient,
    make_document: MakeDocument,
    repository: InMemoryDocumentRepository,
    index: InMemorySearchIndex,
):
    document = make_document("конкурс")

    response = await client.delete(f"/documents/{document.id}")

    assert response.status_code == 204
    assert response.content == b""
    assert document.id not in repository.documents
    assert document.id not in index.texts


async def test_delete_missing_returns_404_without_index_call(
    client: AsyncClient, index: InMemorySearchIndex
):
    response = await client.delete("/documents/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}
    assert index.deleted == []


async def test_delete_twice_returns_204_then_404(
    client: AsyncClient, make_document: MakeDocument
):
    document = make_document("конкурс")

    first = await client.delete(f"/documents/{document.id}")
    second = await client.delete(f"/documents/{document.id}")

    assert (first.status_code, second.status_code) == (204, 404)


async def test_delete_document_missing_in_index_returns_204(
    client: AsyncClient, make_document: MakeDocument, repository: InMemoryDocumentRepository
):
    document = make_document("конкурс", in_index=False)

    response = await client.delete(f"/documents/{document.id}")

    assert response.status_code == 204
    assert document.id not in repository.documents


async def test_delete_non_integer_id_returns_422(client: AsyncClient):
    response = await client.delete("/documents/abc")

    assert response.status_code == 422


@pytest.mark.parametrize("document_id", [MAX_DOCUMENT_ID + 1, 99999999999, 0, -1])
async def test_delete_out_of_range_id_returns_422_without_storage_calls(
    app: FastAPI, client: AsyncClient, document_id: int
):
    # Обращение к хранилищу дало бы 503.
    app.dependency_overrides[get_document_repository] = FailingDocumentRepository

    response = await client.delete(f"/documents/{document_id}")

    assert response.status_code == 422


async def test_delete_max_id_is_accepted(client: AsyncClient):
    response = await client.delete(f"/documents/{MAX_DOCUMENT_ID}")

    assert response.status_code == 404


async def test_deleted_document_disappears_from_search_immediately(
    app: FastAPI, client: AsyncClient, make_document: MakeDocument, index: InMemorySearchIndex
):
    deleted = make_document("конкурс", days=2)
    kept = make_document("конкурс", days=1)
    stale = StaleSearchIndex()
    stale.texts = index.texts
    app.dependency_overrides[get_search_index] = lambda: stale

    await client.delete(f"/documents/{deleted.id}")
    # Индекс ещё возвращает удалённый документ (refresh не прошёл), но выдача фильтруется через БД.
    assert deleted.id in stale.texts
    response = await client.get("/documents/search", params={"q": "конкурс"})

    assert [d["id"] for d in response.json()] == [kept.id]


async def test_delete_index_error_returns_503_and_keeps_document(
    app: FastAPI,
    client: AsyncClient,
    make_document: MakeDocument,
    repository: InMemoryDocumentRepository,
    index: InMemorySearchIndex,
):
    document = make_document("конкурс")
    failing = DeleteFailingSearchIndex()
    failing.texts = index.texts
    app.dependency_overrides[get_search_index] = lambda: failing

    response = await client.delete(f"/documents/{document.id}")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}
    assert failing.deleted == [document.id]
    assert document.id in repository.documents
    assert document.id in index.texts
    search = await client.get("/documents/search", params={"q": "конкурс"})
    assert [d["id"] for d in search.json()] == [document.id]

    # Индекс восстановился — повтор удаляет документ из обоих хранилищ.
    app.dependency_overrides[get_search_index] = lambda: index
    retry = await client.delete(f"/documents/{document.id}")

    assert retry.status_code == 204
    assert document.id not in repository.documents
    assert document.id not in index.texts


async def test_delete_unexpected_index_error_keeps_document(
    make_document: MakeDocument, repository: InMemoryDocumentRepository
):
    document = make_document("конкурс")
    service = DocumentService(repository, DeleteFailingSearchIndex(RuntimeError("boom")), 20)

    with pytest.raises(RuntimeError):
        await service.delete(document.id)

    assert document.id in repository.documents


async def test_delete_database_error_returns_503_without_index_call(
    app: FastAPI, client: AsyncClient
):
    index = FailingSearchIndex()
    app.dependency_overrides[get_document_repository] = FailingDocumentRepository
    app.dependency_overrides[get_search_index] = lambda: index

    response = await client.delete("/documents/1")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}
    assert index.calls == 0

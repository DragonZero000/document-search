from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_document_repository, get_search_index
from tests.conftest import MakeDocument
from tests.fakes import (
    FailingDocumentRepository,
    FailingSearchIndex,
    InMemoryDocumentRepository,
    InMemorySearchIndex,
)


async def test_search_returns_matching_documents(client: AsyncClient, make_document: MakeDocument):
    match = make_document("Конкурс на новый скин")
    make_document("Слив информации на пассивки")

    response = await client.get("/documents/search", params={"q": "конкурс"})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert [d["id"] for d in body] == [match.id]


async def test_search_nothing_found_returns_empty_list(
    client: AsyncClient, make_document: MakeDocument, repository: InMemoryDocumentRepository
):
    make_document("Конкурс на новый скин")

    response = await client.get("/documents/search", params={"q": "отсутствующееслово"})

    assert response.status_code == 200
    assert response.json() == []
    assert repository.get_many_calls == 0


async def test_search_without_q_returns_422(client: AsyncClient):
    response = await client.get("/documents/search")

    assert response.status_code == 422


@pytest.mark.parametrize("q", ["", "   ", "\t \n"])
async def test_search_blank_q_returns_422_without_index_call(
    client: AsyncClient, index: InMemorySearchIndex, q: str
):
    response = await client.get("/documents/search", params={"q": q})

    assert response.status_code == 422
    assert index.search_calls == []


async def test_search_too_long_q_returns_422(client: AsyncClient):
    response = await client.get("/documents/search", params={"q": "а" * 501})

    assert response.status_code == 422


async def test_search_max_length_q_is_accepted(client: AsyncClient):
    response = await client.get("/documents/search", params={"q": "а" * 500})

    assert response.status_code == 200


async def test_search_strips_whitespace(
    client: AsyncClient, make_document: MakeDocument, index: InMemorySearchIndex
):
    make_document("Конкурс на новый скин")

    response = await client.get("/documents/search", params={"q": "  конкурс  "})

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert index.search_calls == ["конкурс"]


async def test_search_more_than_20_returns_20_newest_desc(
    client: AsyncClient, make_document: MakeDocument
):
    documents = [make_document(f"конкурс номер {i}", days=i) for i in range(25)]
    newest_first = sorted(documents, key=lambda d: d.created_date, reverse=True)

    response = await client.get("/documents/search", params={"q": "конкурс"})

    assert response.status_code == 200
    assert [d["id"] for d in response.json()] == [d.id for d in newest_first[:20]]


async def test_search_fewer_than_20_returns_all_desc(
    client: AsyncClient, make_document: MakeDocument
):
    middle = make_document("конкурс", days=5)
    oldest = make_document("конкурс", days=1)
    newest = make_document("конкурс", days=10)

    response = await client.get("/documents/search", params={"q": "конкурс"})

    assert [d["id"] for d in response.json()] == [newest.id, middle.id, oldest.id]


async def test_search_selection_ignores_relevance(client: AsyncClient, make_document: MakeDocument):
    # Самый старый документ — «самый релевантный» (слово повторяется много раз),
    # но в выдачу из 21 совпадения он попасть не должен.
    oldest = make_document("конкурс " * 50, days=0)
    for i in range(1, 21):
        make_document(f"конкурс {i}", days=i)

    response = await client.get("/documents/search", params={"q": "конкурс"})

    ids = [d["id"] for d in response.json()]
    assert len(ids) == 20
    assert oldest.id not in ids


async def test_search_equal_dates_ordered_by_id_desc(
    client: AsyncClient, make_document: MakeDocument
):
    first = make_document("конкурс", days=1)
    second = make_document("конкурс", days=1)

    response = await client.get("/documents/search", params={"q": "конкурс"})

    assert [d["id"] for d in response.json()] == [second.id, first.id]


async def test_search_returns_all_document_fields(client: AsyncClient, make_document: MakeDocument):
    document = make_document("Конкурс на скин", days=3, rubrics=["VK-1603736028819866", "VK-2"])

    response = await client.get("/documents/search", params={"q": "скин"})

    [item] = response.json()
    assert item == {
        "id": document.id,
        "rubrics": ["VK-1603736028819866", "VK-2"],
        "text": "Конкурс на скин",
        "created_date": "2019-01-04T12:00:00",
    }
    assert datetime.fromisoformat(item["created_date"]) == document.created_date


async def test_search_requires_all_words(client: AsyncClient, make_document: MakeDocument):
    both = make_document("Конкурс на новый скин")
    make_document("Конкурс репостов")

    response = await client.get("/documents/search", params={"q": "конкурс скин"})

    assert [d["id"] for d in response.json()] == [both.id]


async def test_search_ghost_in_index_is_not_returned(
    client: AsyncClient, make_document: MakeDocument
):
    alive = make_document("конкурс", days=1)
    make_document("конкурс", days=2, in_db=False)  # удалён из БД, но ещё есть в индексе

    response = await client.get("/documents/search", params={"q": "конкурс"})

    assert [d["id"] for d in response.json()] == [alive.id]


async def test_search_index_unavailable_returns_503(app: FastAPI, client: AsyncClient):
    app.dependency_overrides[get_search_index] = FailingSearchIndex

    response = await client.get("/documents/search", params={"q": "конкурс"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}


async def test_search_database_unavailable_returns_503(
    app: FastAPI, client: AsyncClient, make_document: MakeDocument
):
    make_document("конкурс")
    app.dependency_overrides[get_document_repository] = FailingDocumentRepository

    response = await client.get("/documents/search", params={"q": "конкурс"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}

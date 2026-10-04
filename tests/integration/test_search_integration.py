from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.integration.conftest import InsertDocument

pytestmark = pytest.mark.integration

BASE = datetime(2019, 6, 1, 12, 0, 0)


async def test_morphology_plural_finds_singular(client: AsyncClient, insert_document: InsertDocument):
    document_id = await insert_document("Конкурс на НОВЫЙ СКИН", BASE)

    response = await client.get("/documents/search", params={"q": "конкурсы"})

    assert response.status_code == 200
    assert [d["id"] for d in response.json()] == [document_id]


async def test_all_words_are_required(client: AsyncClient, insert_document: InsertDocument):
    both = await insert_document("Конкурс на новый скин", BASE)
    await insert_document("Конкурс репостов", BASE + timedelta(days=1))

    response = await client.get("/documents/search", params={"q": "конкурс скин"})

    assert [d["id"] for d in response.json()] == [both]


async def test_returns_20_newest_of_all_matches(client: AsyncClient, insert_document: InsertDocument):
    ids = [await insert_document(f"конкурс номер {i}", BASE + timedelta(days=i)) for i in range(25)]

    response = await client.get("/documents/search", params={"q": "конкурс"})

    body = response.json()
    assert [d["id"] for d in body] == list(reversed(ids))[:20]
    assert body[0] == {
        "id": ids[-1],
        "rubrics": ["VK-1"],
        "text": "конкурс номер 24",
        "created_date": (BASE + timedelta(days=24)).isoformat(),
    }

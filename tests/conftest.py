from collections.abc import AsyncGenerator, Callable
from datetime import datetime, timedelta
from itertools import count

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_document_repository, get_search_index
from app.config import Settings
from app.domain.models import Document
from app.main import create_app
from tests.fakes import InMemoryDocumentRepository, InMemorySearchIndex

BASE_DATE = datetime(2019, 1, 1, 12, 0, 0)

MakeDocument = Callable[..., Document]


@pytest.fixture
def repository() -> InMemoryDocumentRepository:
    return InMemoryDocumentRepository()


@pytest.fixture
def index() -> InMemorySearchIndex:
    return InMemorySearchIndex()


@pytest.fixture
def make_document(
    repository: InMemoryDocumentRepository, index: InMemorySearchIndex
) -> MakeDocument:
    """Создаёт документ и кладёт его в фейковые БД и индекс.

    `days` — сдвиг created_date от BASE_DATE: чем больше, тем новее документ.
    """
    ids = count(1)

    def factory(
        text: str = "текст документа",
        *,
        days: float = 0,
        rubrics: list[str] | None = None,
        in_db: bool = True,
        in_index: bool = True,
    ) -> Document:
        document = Document(
            id=next(ids),
            rubrics=rubrics if rubrics is not None else ["VK-1"],
            text=text,
            created_date=BASE_DATE + timedelta(days=days),
        )
        if in_db:
            repository.add(document)
        if in_index:
            index.add(document.id, text)
        return document

    return factory


@pytest.fixture
def app(repository: InMemoryDocumentRepository, index: InMemorySearchIndex) -> FastAPI:
    application = create_app(Settings())
    application.dependency_overrides[get_document_repository] = lambda: repository
    application.dependency_overrides[get_search_index] = lambda: index
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

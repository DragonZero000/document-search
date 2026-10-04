"""In-memory реализации портов для функциональных тестов."""

import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from app.domain.errors import StorageUnavailable
from app.domain.models import Document


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self.documents: dict[int, Document] = {}
        self.get_many_calls = 0

    def add(self, document: Document) -> None:
        self.documents[document.id] = document

    async def get_many_sorted(self, ids: Sequence[int], limit: int) -> list[Document]:
        self.get_many_calls += 1
        found = [self.documents[i] for i in set(ids) if i in self.documents]
        found.sort(key=lambda d: (d.created_date, d.id), reverse=True)
        return found[:limit]

    @asynccontextmanager
    async def delete(self, document_id: int) -> AsyncIterator[bool]:
        document = self.documents.pop(document_id, None)
        try:
            yield document is not None
        except BaseException:
            # Откат транзакции.
            if document is not None:
                self.documents[document_id] = document
            raise

    async def ping(self) -> None:
        pass


class FailingDocumentRepository:
    async def get_many_sorted(self, ids: Sequence[int], limit: int) -> list[Document]:
        raise StorageUnavailable("PostgreSQL is down")

    @asynccontextmanager
    async def delete(self, document_id: int) -> AsyncIterator[bool]:
        raise StorageUnavailable("PostgreSQL is down")
        yield False  # pragma: no cover — делает функцию генератором

    async def ping(self) -> None:
        raise StorageUnavailable("PostgreSQL is down")


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


class InMemorySearchIndex:
    """Эмулирует match с operator=and по lowercase-токенам (без морфологии)."""

    def __init__(self) -> None:
        self.texts: dict[int, str] = {}
        self.search_calls: list[str] = []
        self.deleted: list[int] = []

    def add(self, document_id: int, text: str) -> None:
        self.texts[document_id] = text

    async def search_ids(self, query: str) -> list[int]:
        self.search_calls.append(query)
        wanted = _tokens(query)
        if not wanted:
            return []
        return [i for i, text in self.texts.items() if wanted <= _tokens(text)]

    async def delete(self, document_id: int) -> None:
        self.texts.pop(document_id, None)
        self.deleted.append(document_id)

    async def ping(self) -> None:
        pass


class FailingSearchIndex:
    def __init__(self) -> None:
        self.calls = 0

    async def search_ids(self, query: str) -> list[int]:
        self.calls += 1
        raise StorageUnavailable("Elasticsearch is down")

    async def delete(self, document_id: int) -> None:
        self.calls += 1
        raise StorageUnavailable("Elasticsearch is down")

    async def ping(self) -> None:
        self.calls += 1
        raise StorageUnavailable("Elasticsearch is down")


class DeleteFailingSearchIndex(InMemorySearchIndex):
    """Поиск работает, удаление падает с заданным исключением."""

    def __init__(self, error: Exception | None = None) -> None:
        super().__init__()
        self.error = error or StorageUnavailable("Elasticsearch is down")

    async def delete(self, document_id: int) -> None:
        self.deleted.append(document_id)
        raise self.error


class StaleSearchIndex(InMemorySearchIndex):
    """Удаление успешно, но документ ещё виден поиску — как до refresh индекса."""

    async def delete(self, document_id: int) -> None:
        self.deleted.append(document_id)

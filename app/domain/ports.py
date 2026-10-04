from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from app.domain.models import Document


class DocumentRepository(Protocol):
    async def get_many_sorted(self, ids: Sequence[int], limit: int) -> list[Document]:
        """Документы с указанными id, по убыванию created_date (тай-брейкер — id), не более limit."""
        ...

    def delete(self, document_id: int) -> AbstractAsyncContextManager[bool]:
        """Удаляет документ в транзакции; значение — была ли такая строка.

        Транзакция фиксируется при выходе из контекста; исключение в теле откатывает удаление.
        """
        ...

    async def ping(self) -> None:
        """Проверяет доступность хранилища; при недоступности — StorageUnavailable."""
        ...


class SearchIndex(Protocol):
    async def search_ids(self, query: str) -> list[int]:
        """Id всех документов, текст которых содержит все значимые слова запроса."""
        ...

    async def delete(self, document_id: int) -> None:
        """Удаляет документ из индекса; отсутствие документа ошибкой не считается."""
        ...

    async def ping(self) -> None:
        """Проверяет, что индекс существует; иначе — StorageUnavailable."""
        ...

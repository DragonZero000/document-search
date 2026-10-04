from app.domain.errors import DocumentNotFound
from app.domain.models import Document
from app.domain.ports import DocumentRepository, SearchIndex


class DocumentService:
    def __init__(self, repository: DocumentRepository, index: SearchIndex, limit: int) -> None:
        self._repository = repository
        self._index = index
        self._limit = limit

    async def search(self, query: str) -> list[Document]:
        # Из индекса — id всех совпадений, а сортировка по дате и лимит — в БД:
        # даты в индексе нет, а отбор не должен зависеть от релевантности.
        # БД заодно отсекает документы, которые удалены, но ещё есть в индексе.
        ids = await self._index.search_ids(query)
        if not ids:
            return []
        return await self._repository.get_many_sorted(ids, self._limit)

    async def delete(self, document_id: int) -> None:
        # Удаление из индекса — до фиксации транзакции БД: при ошибке индекса
        # удаление из БД откатывается, и документ остаётся в обоих хранилищах.
        async with self._repository.delete(document_id) as deleted:
            if not deleted:
                raise DocumentNotFound(document_id)
            await self._index.delete(document_id)

    async def check_health(self) -> None:
        await self._repository.ping()
        await self._index.ping()

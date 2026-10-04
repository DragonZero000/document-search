from collections.abc import Generator
from contextlib import contextmanager

from elasticsearch import ApiError, AsyncElasticsearch, NotFoundError, TransportError

from app.domain.errors import StorageUnavailable

# По условию индекс хранит только id и text, даты в нём нет, поэтому сортировка
# по дате выполняется в БД. Анализатор russian даёт стемминг и убирает стоп-слова.
INDEX_MAPPING = {
    "properties": {
        "id": {"type": "long"},
        "text": {"type": "text", "analyzer": "russian"},
    }
}


@contextmanager
def _translate_errors() -> Generator[None]:
    try:
        yield
    except (ApiError, TransportError) as exc:
        raise StorageUnavailable(f"Elasticsearch error: {type(exc).__name__}") from exc


def create_client(url: str, *, timeout: float = 5.0) -> AsyncElasticsearch:
    return AsyncElasticsearch(url, request_timeout=timeout)


async def recreate_index(es: AsyncElasticsearch, index: str) -> None:
    await es.indices.delete(index=index, ignore_unavailable=True)
    await es.indices.create(index=index, mappings=INDEX_MAPPING)


class EsSearchIndex:
    def __init__(self, es: AsyncElasticsearch, index: str, max_ids: int) -> None:
        self._es = es
        self._index = index
        self._max_ids = max_ids

    async def search_ids(self, query: str) -> list[int]:
        # operator=and: нужны все слова запроса. С or при сортировке по дате выдача
        # свелась бы к «последним постам, где есть хоть одно слово».
        # Если запрос состоит из одних стоп-слов, после анализа не остаётся термов,
        # и match ничего не находит (zero_terms_query=none по умолчанию).
        # Возвращаются id всех совпадений, лимит применяется в БД.
        with _translate_errors():
            response = await self._es.search(
                index=self._index,
                query={"match": {"text": {"query": query, "operator": "and"}}},
                size=self._max_ids,
                source=False,  # нужны только _id
                track_total_hits=False,  # общее число совпадений не используется
            )
        return [int(hit["_id"]) for hit in response["hits"]["hits"]]

    async def delete(self, document_id: int) -> None:
        try:
            await self._es.delete(index=self._index, id=str(document_id))
        except NotFoundError:
            return
        except (ApiError, TransportError) as exc:
            raise StorageUnavailable(f"Elasticsearch error: {type(exc).__name__}") from exc

    async def ping(self) -> None:
        with _translate_errors():
            exists = await self._es.indices.exists(index=self._index)
        if not exists:
            raise StorageUnavailable(f"Elasticsearch index {self._index!r} does not exist")

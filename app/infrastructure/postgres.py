import asyncio
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager

import asyncpg

from app.domain.errors import StorageUnavailable
from app.domain.models import Document

_STORAGE_ERRORS = (
    asyncpg.PostgresError,
    asyncpg.InterfaceError,
    OSError,
    asyncio.TimeoutError,
)


@contextmanager
def _translate_errors() -> Iterator[None]:
    try:
        yield
    except _STORAGE_ERRORS as exc:
        raise StorageUnavailable(f"PostgreSQL error: {type(exc).__name__}") from exc


async def create_pool(dsn: str, *, min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size, command_timeout=10)


class PgDocumentRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_many_sorted(self, ids: Sequence[int], limit: int) -> list[Document]:
        with _translate_errors():
            rows = await self._pool.fetch(
                """
                SELECT id, rubrics, text, created_date
                FROM documents
                WHERE id = ANY($1::int[])
                ORDER BY created_date DESC, id DESC
                LIMIT $2
                """,
                list(ids),
                limit,
            )
        return [Document(**dict(row)) for row in rows]

    @asynccontextmanager
    async def delete(self, document_id: int) -> AsyncIterator[bool]:
        # Строка остаётся заблокированной до конца транзакции: параллельный DELETE
        # того же id дождётся фиксации и получит 404.
        with _translate_errors():
            async with self._pool.acquire() as conn, conn.transaction():
                deleted_id = await conn.fetchval(
                    "DELETE FROM documents WHERE id = $1 RETURNING id", document_id
                )
                yield deleted_id is not None

    async def ping(self) -> None:
        with _translate_errors():
            await self._pool.fetchval("SELECT 1")

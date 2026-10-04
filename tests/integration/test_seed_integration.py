import asyncpg
import pytest
from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_scan

from app.config import Settings
from scripts.seed import DEFAULT_CSV, seed

pytestmark = pytest.mark.integration

EXPECTED_ROWS = 1500


async def _index_ids(es: AsyncElasticsearch, index: str) -> set[int]:
    await es.indices.refresh(index=index)
    return {int(hit["_id"]) async for hit in async_scan(es, index=index, _source=False)}


async def _db_ids(pool: asyncpg.Pool) -> set[int]:
    return {r["id"] for r in await pool.fetch("SELECT id FROM documents")}


async def test_seed_loads_csv_into_db_and_index(
    pool: asyncpg.Pool, es: AsyncElasticsearch, settings: Settings
):
    assert await seed(settings, DEFAULT_CSV, force=True) == "loaded"

    ids = [r["id"] for r in await pool.fetch("SELECT id FROM documents ORDER BY id")]
    assert ids == list(range(1, EXPECTED_ROWS + 1))
    assert await pool.fetchval(
        "SELECT count(*) FROM documents WHERE cardinality(rubrics) = 0"
    ) == 0

    first = await pool.fetchrow("SELECT rubrics, created_date FROM documents WHERE id = 1")
    assert first["rubrics"] == ["VK-1603736028819866", "VK-11879320040", "VK-63192684938"]
    assert first["created_date"].isoformat() == "2019-07-25T12:42:13"

    assert await _index_ids(es, settings.es_index) == set(ids)


async def test_seed_without_force_keeps_consistent_data(
    pool: asyncpg.Pool, es: AsyncElasticsearch, settings: Settings
):
    await seed(settings, DEFAULT_CSV, force=True)
    await pool.execute("DELETE FROM documents WHERE id = 1")
    await es.delete(index=settings.es_index, id="1", refresh=True)

    assert await seed(settings, DEFAULT_CSV, force=False) == "skipped"

    assert await pool.fetchval("SELECT count(*) FROM documents") == EXPECTED_ROWS - 1
    assert await pool.fetchval("SELECT max(id) FROM documents") == EXPECTED_ROWS


async def test_seed_restores_missing_index_from_db(
    pool: asyncpg.Pool, es: AsyncElasticsearch, settings: Settings
):
    await seed(settings, DEFAULT_CSV, force=True)
    await pool.execute("DELETE FROM documents WHERE id = 1")
    await es.indices.delete(index=settings.es_index)

    assert await seed(settings, DEFAULT_CSV, force=False) == "reindexed"

    assert await pool.fetchval("SELECT count(*) FROM documents") == EXPECTED_ROWS - 1
    assert await _index_ids(es, settings.es_index) == await _db_ids(pool)


async def test_seed_removes_ghosts_from_out_of_sync_index(
    pool: asyncpg.Pool, es: AsyncElasticsearch, settings: Settings
):
    await seed(settings, DEFAULT_CSV, force=True)
    # Документ удалён из БД, но остался в индексе.
    await pool.execute("DELETE FROM documents WHERE id = 1")

    assert await seed(settings, DEFAULT_CSV, force=False) == "reindexed"

    index_ids = await _index_ids(es, settings.es_index)
    assert 1 not in index_ids
    assert index_ids == await _db_ids(pool)

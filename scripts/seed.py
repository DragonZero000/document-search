"""Начальная загрузка тестового набора: CSV → PostgreSQL → Elasticsearch.

Запуск: python -m scripts.seed [--force] [--csv PATH]

Без --force загрузка CSV пропускается, если в таблице documents уже есть данные;
если при этом индекса нет или он не совпадает с БД по числу документов,
индекс пересоздаётся из БД (сама БД не меняется).
С --force данные и индекс пересоздаются полностью.
"""

import argparse
import ast
import asyncio
import csv
import logging
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Literal

import asyncpg
from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.config import Settings, get_settings
from app.infrastructure import elastic

logger = logging.getLogger("scripts.seed")

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "migrations"
DEFAULT_CSV = ROOT / "test-data" / "posts.csv"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

SeedResult = Literal["loaded", "reindexed", "skipped"]


async def apply_migrations(conn: asyncpg.Connection) -> None:
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        logger.info("Applying migration %s", path.name)
        await conn.execute(path.read_text(encoding="utf-8"))


def parse_rubrics(raw: str) -> list[str]:
    value = ast.literal_eval(raw)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"rubrics must be a list of strings, got {raw!r}")
    return value


def read_csv(path: Path) -> Iterator[tuple[list[str], str, datetime]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            try:
                yield (
                    parse_rubrics(row["rubrics"]),
                    row["text"],
                    datetime.strptime(row["created_date"], DATE_FORMAT),
                )
            except (KeyError, ValueError, SyntaxError) as exc:
                raise ValueError(f"{path.name}: invalid record at line {line_no}: {exc}") from exc


async def index_documents(conn: asyncpg.Connection, es: AsyncElasticsearch, index: str) -> int:
    rows = await conn.fetch("SELECT id, text FROM documents ORDER BY id")
    actions = (
        {"_index": index, "_id": row["id"], "_source": {"id": row["id"], "text": row["text"]}}
        for row in rows
    )
    indexed, _ = await async_bulk(es, actions, chunk_size=500, raise_on_error=True)
    await es.indices.refresh(index=index)
    return indexed


async def index_in_sync(conn: asyncpg.Connection, es: AsyncElasticsearch, index: str) -> bool:
    # Дешёвая проверка: сравниваются только количества. Если число совпадает, а наборы id
    # разные, расхождение не обнаружится; в этом случае поможет `seed --force`.
    if not await es.indices.exists(index=index):
        return False
    await es.indices.refresh(index=index)
    indexed = (await es.count(index=index))["count"]
    return indexed == await conn.fetchval("SELECT count(*) FROM documents")


async def seed(settings: Settings, csv_path: Path, *, force: bool) -> SeedResult:
    """Загружает данные или восстанавливает индекс; возвращает, что было сделано."""
    conn = await asyncpg.connect(settings.database_url)
    es = elastic.create_client(settings.es_url, timeout=30)
    try:
        await apply_migrations(conn)

        if not force and await conn.fetchval("SELECT EXISTS (SELECT 1 FROM documents)"):
            if await index_in_sync(conn, es, settings.es_index):
                logger.info("Documents already loaded, skipping (use --force to reload)")
                return "skipped"
            await elastic.recreate_index(es, settings.es_index)
            indexed = await index_documents(conn, es, settings.es_index)
            logger.info("Index %r was out of sync, reindexed %d documents", settings.es_index, indexed)
            return "reindexed"

        records = list(read_csv(csv_path))
        # Данные в БД фиксируются только после успешной индексации:
        # при сбое ES следующий запуск начнёт загрузку заново.
        async with conn.transaction():
            await conn.execute("TRUNCATE documents RESTART IDENTITY")
            await conn.copy_records_to_table(
                "documents", records=records, columns=["rubrics", "text", "created_date"]
            )
            logger.info("Inserted %d documents into PostgreSQL", len(records))

            await elastic.recreate_index(es, settings.es_index)
            indexed = await index_documents(conn, es, settings.es_index)
            logger.info("Indexed %d documents into %r", indexed, settings.es_index)
        return "loaded"
    finally:
        await es.close()
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="пересоздать данные и индекс")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="путь к CSV-файлу")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        asyncio.run(seed(get_settings(), args.csv, force=args.force))
    except Exception:
        logger.exception("Seeding failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

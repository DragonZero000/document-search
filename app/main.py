import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import Settings, get_settings
from app.domain.errors import DocumentNotFound, StorageUnavailable
from app.infrastructure import elastic, postgres

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings: Settings = app.state.settings
    app.state.pg_pool = await postgres.create_pool(settings.database_url)
    app.state.es = elastic.create_client(settings.es_url, timeout=settings.es_timeout)
    try:
        yield
    finally:
        await app.state.es.close()
        await app.state.pg_pool.close()


async def _document_not_found(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Document not found"})


async def _storage_unavailable(request: Request, exc: Exception) -> JSONResponse:
    # В лог — трейсбек исходной ошибки драйвера (__cause__), а не обёртки StorageUnavailable;
    # клиенту детали не раскрываются.
    logger.error("Storage unavailable: %s", exc, exc_info=exc.__cause__)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": "Service unavailable"}
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="Document Search",
        version="0.1.0",
        description="Полнотекстовый поиск по документам (PostgreSQL + Elasticsearch).",
        lifespan=lifespan,
    )
    app.state.settings = settings or get_settings()
    app.include_router(router)
    app.add_exception_handler(DocumentNotFound, _document_not_found)
    app.add_exception_handler(StorageUnavailable, _storage_unavailable)
    return app


app = create_app()

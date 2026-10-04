from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.domain.ports import DocumentRepository, SearchIndex
from app.domain.service import DocumentService
from app.infrastructure.elastic import EsSearchIndex
from app.infrastructure.postgres import PgDocumentRepository


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_document_repository(request: Request) -> DocumentRepository:
    return PgDocumentRepository(request.app.state.pg_pool)


def get_search_index(
    request: Request, settings: Annotated[Settings, Depends(get_app_settings)]
) -> SearchIndex:
    return EsSearchIndex(request.app.state.es, settings.es_index, settings.es_max_ids)


def get_document_service(
    repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    index: Annotated[SearchIndex, Depends(get_search_index)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> DocumentService:
    return DocumentService(repository, index, settings.search_limit)

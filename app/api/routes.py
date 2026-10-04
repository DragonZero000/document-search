from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from pydantic import BaseModel, StringConstraints

from app.api.deps import get_document_service
from app.domain.models import MAX_DOCUMENT_ID, Document
from app.domain.service import DocumentService

router = APIRouter()


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str


SERVICE_UNAVAILABLE = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "PostgreSQL или Elasticsearch недоступны",
    }
}

SearchQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    Query(
        description="Текст запроса: 1–500 символов после обрезки пробелов. "
        "Документ совпадает, если содержит все значимые слова запроса (с учётом морфологии).",
        examples=["конкурс"],
    ),
]

Service = Annotated[DocumentService, Depends(get_document_service)]


@router.get(
    "/documents/search",
    response_model=list[Document],
    summary="Полнотекстовый поиск документов",
    description="Ищет запрос по тексту документов и возвращает не более `SEARCH_LIMIT` "
    "(по умолчанию 20) совпавших документов, упорядоченных по дате создания по убыванию "
    "(сначала новые). Сортировка и лимит применяются ко всем совпадениям, а не к наиболее "
    "релевантным.",
    responses=SERVICE_UNAVAILABLE,
    tags=["documents"],
)
async def search_documents(q: SearchQuery, service: Service) -> list[Document]:
    return await service.search(q)


@router.delete(
    "/documents/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Удаление документа",
    description="Удаляет документ из БД и из поискового индекса в рамках одного запроса. "
    "Если PostgreSQL или Elasticsearch недоступны, сервис отвечает 503, и документ не удаляется "
    "ни из одного хранилища — запрос можно повторить.",
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "Документ удалён"},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Документ не найден"},
        **SERVICE_UNAVAILABLE,
    },
    tags=["documents"],
)
async def delete_document(
    id: Annotated[
        int,
        Path(ge=1, le=MAX_DOCUMENT_ID, description="Идентификатор документа (1–2147483647)"),
    ],
    service: Service,
) -> Response:
    await service.delete(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Проверка готовности",
    description="Проверяет доступность PostgreSQL и наличие поискового индекса в Elasticsearch.",
    responses=SERVICE_UNAVAILABLE,
    tags=["service"],
)
async def health(service: Service) -> HealthResponse:
    await service.check_health()
    return HealthResponse(status="ok")

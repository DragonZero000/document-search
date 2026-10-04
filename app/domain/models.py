from datetime import datetime

from pydantic import BaseModel, Field

# Максимальный id документа: столбец documents.id имеет тип SERIAL (int4).
MAX_DOCUMENT_ID = 2**31 - 1


class Document(BaseModel):
    id: int = Field(description="Идентификатор документа в БД")
    rubrics: list[str] = Field(description="Рубрики документа")
    text: str = Field(description="Текст документа")
    created_date: datetime = Field(description="Дата создания документа (ISO 8601)")

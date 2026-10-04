class DocumentNotFound(Exception):
    def __init__(self, document_id: int) -> None:
        super().__init__(f"Document {document_id} not found")
        self.document_id = document_id


class StorageUnavailable(Exception):
    """Хранилище (PostgreSQL или Elasticsearch) недоступно или вернуло ошибку."""

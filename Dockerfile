# Рабочий образ: api и seed.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Зависимости ставятся отдельным слоем, чтобы изменения кода не инвалидировали кэш.
# Точные версии — из lock-файла (перегенерация описана в README).
COPY requirements.lock ./
RUN pip install -r requirements.lock \
    && useradd --create-home --uid 1000 app

COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY test-data ./test-data

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# Образ для интеграционных тестов: docker compose run --rm tests
FROM runtime AS test

USER root

# pyproject.toml нужен только pytest (маркеры, asyncio_mode).
COPY pyproject.toml requirements-dev.lock ./
RUN pip install -r requirements-dev.lock

COPY tests ./tests
COPY docs.json ./

CMD ["python", "-m", "pytest", "-m", "integration", "-v"]

# Рабочий образ: api и seed.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Зависимости ставятся отдельным слоем, чтобы изменения кода не инвалидировали кэш.
COPY pyproject.toml ./
RUN python -c "import tomllib; p = tomllib.load(open('pyproject.toml', 'rb'))['project']; \
print('\n'.join(p['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt \
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

RUN python -c "import tomllib; p = tomllib.load(open('pyproject.toml', 'rb'))['project']; \
print('\n'.join(p['optional-dependencies']['dev']))" > /tmp/requirements-dev.txt \
    && pip install -r /tmp/requirements-dev.txt

COPY tests ./tests
COPY docs.json ./

CMD ["python", "-m", "pytest", "-m", "integration", "-v"]

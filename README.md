# Document Search

Простой поисковик по текстам документов: документы хранятся в PostgreSQL, полнотекстовый индекс — в Elasticsearch, API — FastAPI (асинхронно, `asyncpg` + `AsyncElasticsearch`).

## Требования

- Docker и Docker Compose v2
- Для запуска API или тестов без Docker — Python 3.11+

## Запуск

```bash
docker compose up --build
```

Поднимаются сервисы:

| Сервис          | Назначение                                                                 |
|-----------------|----------------------------------------------------------------------------|
| `postgres`      | PostgreSQL 16, таблица `documents`                                         |
| `elasticsearch` | Elasticsearch 8.19 (single-node, без security), индекс `documents`         |
| `seed`          | одноразовая загрузка `test-data/posts.csv` в БД и индекс, затем выходит    |
| `api`           | FastAPI на http://localhost:8000 (Swagger UI — http://localhost:8000/docs) |

`api` стартует только после успешного завершения `seed`, а `seed` — после healthcheck PostgreSQL и Elasticsearch. Если БД уже заполнена, `seed` не трогает данные, но пересоздаёт индекс из БД, когда индекса нет или число документов в нём расходится с БД.

Остановка с удалением данных: `docker compose down -v`.

### Запуск без Docker

PostgreSQL и Elasticsearch по-прежнему поднимаются в Docker, но с портами, открытыми на хост (`compose.local.yml`); API и загрузка данных запускаются локально:

```bash
docker compose -f docker-compose.yml -f compose.local.yml up -d postgres elasticsearch

python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.lock
pip install -e . --no-deps

cp .env.example .env            # Windows: copy .env.example .env
python -m scripts.seed
uvicorn app.main:app --reload
```

API — http://localhost:8000. Если порт 5432 или 9200 на хосте занят, поменяйте левую часть в `compose.local.yml` (например, `"15432:5432"`) и `DATABASE_URL`/`ES_URL` в `.env`.

## API

Полное описание — в [`docs.json`](docs.json) (OpenAPI 3).

### Поиск

```bash
curl -G "http://localhost:8000/documents/search" --data-urlencode "q=конкурс скин"
```

Ответ `200` — массив из не более чем 20 документов, отсортированных по `created_date` по убыванию:

```json
[
  {
    "id": 2,
    "rubrics": ["VK-1603736028819866", "VK-95883495386", "VK-55347043459"],
    "text": "🎁 Конкурс на НОВЫЙ СКИН ‼️ ...",
    "created_date": "2019-05-31T17:18:42"
  }
]
```

`q` обязателен, обрезается по краям и должен иметь длину 1–500 символов, иначе `422`.

### Удаление

```bash
curl -i -X DELETE "http://localhost:8000/documents/2"
```

`204` — удалён из БД и индекса, `404` — документа нет, `422` — `id` не целое число или вне диапазона `1–2147483647` (тип `SERIAL`), `503` — PostgreSQL или Elasticsearch недоступны: документ в этом случае не удаляется ни из одного хранилища, запрос можно повторить.

### Прочее

- `GET /health` → `200 {"status": "ok"}`, если PostgreSQL доступен и индекс в Elasticsearch существует, иначе `503`.
- При недоступности PostgreSQL или Elasticsearch эндпоинты отвечают `503 {"detail": "Service unavailable"}`.

## Тесты

### Функциональные (без Docker)

HTTP-уровень через `httpx.AsyncClient` + in-memory реализации портов (`tests/fakes.py`): поиск, валидация, удаление, healthcheck, настройки, сверка `docs.json`.

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.lock
pip install -e . --no-deps
pytest
```

### Интеграционные (реальные PostgreSQL и Elasticsearch)

Морфология, SQL-запросы, удаление при недоступном Elasticsearch и параллельные удаления, healthcheck, загрузка CSV и восстановление индекса. Используют отдельные БД `documents_test` и индекс `documents_test`, данные основного стека не трогают. Запускаются в отдельной стадии образа `test` (рабочий образ `runtime` не содержит тестов и dev-зависимостей):

```bash
docker compose run --rm --build tests
```

## Обслуживание

- **Зависимости.** В `pyproject.toml` — допустимые диапазоны, точные версии (включая транзитивные) — в `requirements.lock` и `requirements-dev.lock`; образы ставят зависимости только из них. После изменения зависимостей lock-файлы перегенерируются ([uv](https://docs.astral.sh/uv/) нужен только для этого):
  ```bash
  uv pip compile --universal pyproject.toml -o requirements.lock
  uv pip compile --universal --extra dev pyproject.toml -o requirements-dev.lock
  ```
  `--universal` сохраняет платформенные зависимости с маркерами (например, `uvloop` — только не на Windows), поэтому lock, собранный на любой ОС, годится для Linux-образа. Версия образа Elasticsearch в `docker-compose.yml` совпадает с клиентом `elasticsearch` по мажорной и минорной версии.
- **Перегенерация `docs.json`** после изменения API (тест `test_openapi` упадёт, если забыть):
  ```bash
  python -m scripts.export_openapi
  ```
- **Перезагрузка данных** (очищает `documents`, сбрасывает `id`, пересоздаёт индекс):
  ```bash
  docker compose run --rm seed python -m scripts.seed --force
  ```
  Без `--force` загрузка CSV пропускается, если в БД уже есть документы, — поэтому рестарт контейнеров не отменяет удаления.
- **Восстановление индекса из БД** (если индекс пропал или разошёлся с БД): `docker compose run --rm seed`.

Настройки задаются переменными окружения (см. [`.env.example`](.env.example)): `DATABASE_URL`, `ES_URL`, `ES_INDEX`, `ES_TIMEOUT`, `SEARCH_LIMIT` (≥ 1), `ES_MAX_IDS` (1–10000).

## Устройство

```
app/
  domain/          модели, порты (typing.Protocol), DocumentService — без зависимостей от БД/ES
  infrastructure/  адаптеры: postgres.py (asyncpg), elastic.py (AsyncElasticsearch)
  api/             маршруты FastAPI и сборка зависимостей (Depends)
scripts/           seed.py, export_openapi.py
migrations/        SQL-схема (применяется seed)
tests/             functional/ (фейки) и integration/ (реальный стек)
```

### Принятые решения

- **«Первые 20 по дате» — из всех совпадений.** Индекс по условию хранит только `id` и `text`, поэтому сортировать по дате в ES нельзя. Сервис берёт из ES `id` *всех* совпавших документов, а PostgreSQL выполняет `WHERE id = ANY($1) ORDER BY created_date DESC, id DESC LIMIT 20`. Так релевантность не влияет на отбор, а порядок — сначала новые (`id` — тай-брейкер). Побочный эффект: БД — источник истины, документы, удалённые из БД, но ещё не вычищенные из индекса, в выдачу не попадают. Рассмотренная альтернатива — взять 20 самых релевантных и уже их отсортировать по дате — отклонена: тогда «первые 20» определяются релевантностью, а не датой, что расходится с буквальным текстом задания. Направление «сначала новые» в задании не указано; выбрано как ожидаемое для ленты постов.
- **Все слова запроса обязательны** (`match` с `operator: and`, анализатор `russian` со стеммингом и стоп-словами). При сортировке по дате режим `or` превращал бы выдачу в «последние посты, где встретилось хоть одно слово». Обратная сторона — длинные запросы чаще дают пустой результат.
- **Удаление — одна транзакция БД вокруг вызова ES.** `DELETE ... RETURNING id` в транзакции (строка заблокирована), затем удаление из индекса (отсутствие документа в индексе — успех), затем `COMMIT`. Ошибка ES откатывает транзакцию → `503`, документ остаётся в обоих хранилищах, повтор запроса идемпотентен. Параллельные удаления одного `id` сериализуются блокировкой строки: один получает `204`, другой — `404`. Фоновых процессов и очередей нет.

### Ограничения

- ES отдаёт не более `ES_MAX_IDS` (по умолчанию 10 000, это же `max_result_window`) совпадений за запрос; при большем числе совпадений выдача может быть неполной. На тестовом наборе (1500 документов) не воспроизводится. Путь масштабирования — PIT + `search_after` или добавление `created_date` в индекс и сортировка в ES.
- Запрос только из стоп-слов (например, `q=и на`) возвращает `[]`: анализатор `russian` отбрасывает стоп-слова, и значимых слов для поиска не остаётся. Возвращать в этом случае «последние документы вообще» было бы хуже, чем пустой ответ.
- Пока Elasticsearch недоступен, удаление отвечает `503` (как и поиск).
- Если ES удалил документ, а `COMMIT` в PostgreSQL не прошёл (обрыв соединения), документ остаётся в БД, но не находится поиском. Повторный `DELETE` или запуск `seed` восстанавливает согласованность.
- Создание и редактирование документов через API не реализованы.

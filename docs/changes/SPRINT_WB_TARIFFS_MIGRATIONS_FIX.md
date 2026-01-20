### Причина проблемы

- В логах API при обращении к эндпоинтам WB Tariffs (`/api/v1/admin/marketplaces/wildberries/tariffs/ingest` и `/status`) возникала ошибка:

  ```text
  psycopg2.errors.UndefinedTable: relation "marketplace_api_snapshots" does not exist
  ```

- Это означало, что таблица `marketplace_api_snapshots` ещё не была создана в базе данных, к которой подключён API‑контейнер (миграция с её созданием не была выполнена).
- Дополнительно `scripts/check_alembic_heads.py` показывал наличие **двух HEAD‑ревизий** (ветвление в Alembic), из‑за чего `alembic upgrade head` не доходил до новой миграции `c3f4c5d6e7f8_add_marketplace_api_snapshots.py` и не создавал таблицу.

### Изменённые файлы

- **Миграции Alembic**:
  - `alembic/versions/c3f4c5d6e7f8_add_marketplace_api_snapshots.py` — миграция, создающая таблицу `marketplace_api_snapshots` с полями:
    - `id BIGINT PRIMARY KEY`,
    - `marketplace_code TEXT NOT NULL`,
    - `data_domain TEXT NOT NULL`,
    - `data_type TEXT NOT NULL`,
    - `as_of_date DATE NULL`,
    - `locale TEXT NULL`,
    - `request_params JSONB NOT NULL`,
    - `payload JSONB NOT NULL`,
    - `payload_hash TEXT NOT NULL`,
    - `fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()`,
    - `http_status INT NOT NULL`,
    - `error TEXT NULL`,
    - индексы: `uq_marketplace_api_snapshots_latest` и `ix_marketplace_api_snapshots_latest_lookup`.
  - **Новая merge‑миграция**: `alembic/versions/7f8e9a0b1c2d_merge_heads_c3f4c5d6e7f8_and_f1a2b3c4d5e6.py`:

    ```python
    """Merge heads: c3f4c5d6e7f8 and f1a2b3c4d5e6"""
    revision = "7f8e9a0b1c2d"
    down_revision = ("c3f4c5d6e7f8", "f1a2b3c4d5e6")
    ```

    Эта миграция не меняет схему, но объединяет две ветки в одну линейную историю, чтобы `alembic upgrade head` корректно доходил до всех миграций (включая создание `marketplace_api_snapshots`).

- **Слой доступа к данным**:
  - `src/app/db_marketplace_tariffs.py`:
    - Уточнена реализация `get_tariffs_status`, чтобы:
      - для каждого типа тарифов (`commission`, `acceptance_coefficients`, `box`, `pallet`, `return`) безопасно возвращать `{"latest_fetched_at": None, "latest_as_of_date": None, "locale": None}`, если в таблице нет строк для этого типа (без выброса исключений),
      - вычислять общий `latest_fetched_at` как максимум по полям `latest_fetched_at` всех типов; если данных нет вообще — `latest_fetched_at` будет `None`,
      - для `commission` при наличии данных и фильтре `locale='ru'` принудительно возвращать `locale="ru"`, а при отсутствии записей — `locale=None`.

- **Admin‑роутер**:
  - `src/app/routers/admin_marketplaces.py`:
    - В эндпоинте `POST /api/v1/admin/marketplaces/wildberries/tariffs/ingest` добавлена обработка `sqlalchemy.exc.ProgrammingError` вокруг вызова `ingest_wb_tariffs_all_task.delay(...)`:
      - при ошибке подключения/схемы (например, если таблица ещё не существует) возвращается `HTTP 503 Service Unavailable` с понятным `detail`:

        > "Database schema not migrated for WB tariffs. Required table 'marketplace_api_snapshots' may be missing. Please run Alembic migrations (e.g. 'alembic upgrade head')."

    - Аналогичная обработка добавлена в `GET /api/v1/admin/marketplaces/wildberries/tariffs/status` вокруг вызова `get_tariffs_status(...)`, чтобы вместо 500 возвращать 503 с понятным сообщением, если отсутствует схема.

- **Скрипт диагностики схемы**:
  - **Новый файл**: `scripts/check_db_schema.py`:
    - Проверяет наличие таблицы `marketplace_api_snapshots` через `SELECT to_regclass('public.marketplace_api_snapshots')`.
    - Выводит:
      - если таблица есть:

        ```text
        ✅ Table 'marketplace_api_snapshots' exists.
        ```

      - если таблицы нет:

        ```text
        ❌ Table 'marketplace_api_snapshots' is MISSING in the current database.
        Run Alembic migrations, for example:
          alembic upgrade head
        or via Docker:
          docker compose run --rm api alembic upgrade head
        ```

    - Exit‑коды:
      - `0` — таблица существует,
      - `1` — таблица отсутствует или не удалось подключиться к БД.

- **Тесты**:
  - `test_admin_wb_tariffs.py`:
    - `test_wb_tariffs_status_empty_table`:
      - очищает таблицу `marketplace_api_snapshots` через `DELETE FROM marketplace_api_snapshots`,
      - вызывает `GET /api/v1/admin/marketplaces/wildberries/tariffs/status`,
      - ожидает `200 OK` и структуру, где `latest_fetched_at` и все `latest_as_of_date`/`latest_fetched_at` по типам равны `null` (таблица пустая, но существует).

### Гарантии применения миграций в Docker / dev

- **API‑контейнер уже содержит встроенный запуск миграций**:
  - В `infra/docker/docker-compose.yml` для сервиса `api` используется entrypoint:

    ```yaml
    api:
      entrypoint: ["python", "/app/scripts/docker-entrypoint.py"]
      command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir /app/src
    ```

  - Скрипт `scripts/docker-entrypoint.py`:
    - ждёт готовности PostgreSQL (`wait_for_postgres()` с до 30 попыток),
    - берёт advisory‑lock в PostgreSQL (чтобы не запускать миграции параллельно),
    - выполняет `alembic upgrade head` в корне репозитория (`/app`), используя `DATABASE_URL`/`POSTGRES_*` окружения,
    - при неудаче выводит подробный лог и **завершает контейнер с ошибкой**, не запуская `uvicorn`.

- **Синхронизация настроек подключения**:
  - `infra/docker/docker-compose.yml` для `api` и `postgres` использует одни и те же переменные окружения `POSTNLGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` через общий `.env`.
  - В `src/app/settings.py` и `alembic/env.py` формируется `SQLALCHEMY_DATABASE_URL` из тех же переменных (`postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}`), поэтому и рантайм, и Alembic работают с одной и той же базой.

- **Исправление ветвления миграций**:
  - После добавления merge‑миграции `7f8e9a0b1c2d_merge_heads_c3f4c5d6e7f8_and_f1a2b3c4d5e6.py` команда:

    ```bash
    python scripts/check_alwaysc_heads.py
    ```

    показывает один HEAD:

    ```text
    HEADS:
      - 7f8e9a0b1c2d
    NO MERGE NEEDED - Single head
    ```

  - Это гарантирует, что `alembic upgrade head` применит как `f1a2b3c4d5e6_add_articles_base_indexes_and_vendor_code_norm.py`, так и `c3f4c5d6e7f8_add_marketplace_api_snapshots.py` в правильном порядке.

### Как накатить миграции и проверить таблицу

1. **Локально (без Docker)**:

   ```bash
   # Из корня репозитория
   alembic upgrade head

   # Проверка наличия таблицы
   python -m scripts.check_db_schema
   # Ожидаемый вывод:
   #   ✅ Table 'marketplace_api_snapshots' exists.
   ```

2. **Через Docker Compose**:

   - Накатить миграции на базу, к которой подключается `api`:

     ```bash
     # Выполнить миграции в том же окружении, что и api-контейнер
     docker compose run --rm api alembic upgrade head
     ```

   - Проверить наличие таблицы:

     ```bash
     docker compose run --rm api python -m scripts.check_db_schema
     ```

     Ожидаемый результат:

     ```text
     Checking for table: marketplace_api_snapshots
     ✅ Table 'marketplace_api_snapshots' exists.
     ```

3. **Проверка через psql / Adminer**:

   - Через `psql` внутри контейнера:

     ```bash
     docker compose exec postgres psql -U wb -d wb -c "\dt+ marketplace_api_snapshots"
     ```

   - Или через Adminer (контейнер `adminer`):
     - Зайти на `http://localhost/` (или соответствующий URL),
     - Подключиться к базе `wb`,
     - В списке таблиц увидеть `marketplace_api_snapshots`.

### Поведение эндпоинтов после исправлений

1. **Если таблица существует, но пуста**:
   - `GET /api/v1/admin/marketplaces/wildberries/tariffs/status`:
     - возвращает `200 OK`,
     - структура:

       ```json
       {
         "marketplace_code": "wildberries",
         "data_domain": "tariffs",
         "latest_fetched_at": null,
         "types": {
           "commission": { "latest_fetched_at": null, "latest_as_of_date": null, "locale": null },
           "acceptance_coefficients": { "latest_fetched_at": null, "latest_as_of_date": null, "locale": null },
           "box": { "latest_fetched_at": null, "latest_as_of_date": null, "locale": null },
           "pallet": { "latest_fetched_at": null, "latest_as_of_date": null, "locale": null },
           "return": { "latest_fetched_at": null, "latest_as_of_date": null, "locale": null }
         }
       }
       ```

   - `POST /api/v1/admin/marketplaces/wildberries/tariffs/ingest`:
     - при наличии работающего Celery‑воркера и схемы возвращает `202 Accepted` с телом:

       ```json
       {
         "status": "started",
         "days_ahead": 14,
         "task": "ingest_wb_tariffs_all",
         "task_id": "<uuid или id задачи>"
       }
       ```

2. **Если таблица отсутствует (миграции НЕ накатаны)**:
   - `GET /api/v1/admin/marketplaces/wildberries/tariffs/status`:
     - возвращает `503 Service Unavailable` с `detail`:

       ```json
       {
         "detail": "Database schema not migrated for WB tariffs. Required table 'marketplace_api_snapshots' may be missing. Please run Alembic migrations (e.g. 'alembic upgrade head')."
       }
       ```

   - `POST /api/v1/admin/marketplaces/wildberries/tariffs/ingest`:
     - при возникновении `ProgrammingError` в момент enqueue (маловероятно, но обработано защитно) возвращает тот же `503` с тем же `detail`, вместо 500/traceback.

### Как проверить UI после исправлений

1. **Проверка статуса без данных (после миграций)**:
   - Убедиться, что миграции накатаны (`python -m scripts.check_db_schema` → `✅`).
   - Запустить стек:

     ```bash
     docker compose up --build
     ```

   - Авторизоваться в UI под пользователем с `is_superuser=true`.
   - Открыть страницу:
     - через меню: кликнуть по пункту `Admin: WB Tariffs` в топбаре,
     - URL: `http://localhost/app/admin/marketsplaces/wildberries/tariffs`.
   - Нажать кнопку “Обновить статус”.
   - Убедиться, что UI показывает:
     - `Последний snapshot (любой тип): нет данных`,
     - в таблице по всем типам — `—` / `null` для `latest_fetched_at` и `latest_as_of_date`,
     - в Network‑вкладке DevTools запрос к `/api/v1/admin/marketplaces/wildberries/tariffs/status` вернул `200 OK`.

2. **Проверка поведения при отсутствии схемы (опционально, для отладки)**:
   - (НЕ делайте это в рабочей базе; только в отдельной тестовой БД!)
   - Вручную удалить таблицу `marketplace_api_snapshots` из тестовой БД.
   - Вызвать `GET /api/v1/admin/marketplaces/wildberries/tariffs/status`:
     - убедиться, что API возвращает `503` и `detail` с указанием на необходимость запуска миграций,
     - UI должен отобразить понятное сообщение об ошибке (через обработку `ApiError.detail`).
   - После проверки заново применить миграции `alembic upgrade head`, чтобы восстановить таблицу.


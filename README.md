# EcomCore

API для автоматизации работы с Wildberries: загрузка продуктов, синхронизация цен, получение актуальной информации.

## Project structure (transition state)

The repository is transitioning from a monolithic wb-automation layout to a modular EcomCore architecture. The current structure reflects this transitional state:

- **src/** — legacy backend core (FastAPI, ingestion, business logic), currently active
- **frontend/** — legacy frontend, currently active
- **apps/** — future application services (api, web, workers)
- **packages/** — shared and reusable modules
- **infra/** — infrastructure (Docker, nginx, environment)
- **alembic/** — database migrations

## Архитектура

Проект использует FastAPI, PostgreSQL, Redis и Celery для фоновых задач. Все сервисы запускаются через Docker Compose.

## Запуск через Docker Compose

Docker Compose файл находится в `infra/docker/docker-compose.yml`.

### Первый запуск / Создание администратора

После `docker compose down/up` таблица `users` может быть пустой, что приводит к ошибке 401 при попытке входа.

**⚠️ ВАЖНО: Расположение .env файла**

Файл `.env` **ОБЯЗАТЕЛЬНО** должен находиться в корне репозитория:
- Windows: `D:\Work\EcomCore\.env`
- Linux: `/root/apps/ecomcore/.env` (или путь к корню репозитория)

Docker Compose использует `env_file: ../../.env` (относительно `infra/docker/`), что указывает на корневой `.env` файл.

**Полный .env файл для локальной разработки:**

Создайте/откройте `.env` файл в корне репозитория (`D:\Work\EcomCore\.env`):

```env
# Database credentials (REQUIRED)
POSTGRES_DB=wb
POSTGRES_USER=wb
POSTGRES_PASSWORD=wbpassword

# Auto-apply migrations in dev mode (OPTIONAL, recommended)
# Если AUTO_MIGRATE=1, миграции применяются автоматически при старте API
AUTO_MIGRATE=1

# Bootstrap admin user (OPTIONAL, for automatic admin creation)
# Если BOOTSTRAP_ADMIN=1, admin создаётся автоматически если таблица users пуста
BOOTSTRAP_ADMIN=1
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=admin123
BOOTSTRAP_ADMIN_EMAIL=admin@local.dev
```

**Запуск с автоматическими миграциями (рекомендуется для dev):**

```powershell
# Перейти в директорию docker-compose (ОБЯЗАТЕЛЬНО из этой директории!)
cd D:\Work\EcomCore\infra\docker

# Остановить контейнеры
docker compose down

# Запустить контейнеры с пересборкой
docker compose up -d --build

# Подождать инициализации (15 секунд для PostgreSQL + миграций + API)
Start-Sleep -Seconds 15
```

**Что происходит автоматически:**
- Если `AUTO_MIGRATE=1` → миграции применяются автоматически (создаются таблицы `users`, `projects`, `project_members`, и другие)
- Если `BOOTSTRAP_ADMIN=1` → admin пользователь создаётся автоматически (если таблица `users` пуста)

**Запуск без автоматических миграций (если AUTO_MIGRATE=0):**

```powershell
cd D:\Work\EcomCore\infra\docker
docker compose down
docker compose up -d --build
Start-Sleep -Seconds 10
docker compose exec api alembic upgrade head
Start-Sleep -Seconds 5
```

Bootstrap создаст пользователя **только если таблица `users` пуста** (безопасно и идемпотентно).

**Проверка bootstrap в логах:**

```powershell
docker compose logs api | Select-String -Pattern "Bootstrap"
```

**Проверка входа (Windows PowerShell):**

```powershell
# Проверка API Docs
curl http://localhost:8000/docs
curl http://localhost/api/docs

# Проверка входа (одна строка)
curl -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{\"username\":\"admin\",\"password\":\"admin123\"}'
```

**Ручное создание (fallback):**

```powershell
# Из директории infra/docker (ОБЯЗАТЕЛЬНО!)
cd D:\Work\EcomCore\infra\docker

# Использовать существующий скрипт (создаст или обновит admin)
docker compose exec api python /app/scripts/create_admin_user.py admin123
```

**Troubleshooting:**

**Ошибка "relation 'projects' does not exist":**
- Миграции не применены. Решение:
  1. Добавьте `AUTO_MIGRATE=1` в `.env` и перезапустите: `docker compose restart api`
  2. Или примените вручную: `docker compose exec api alembic upgrade head`

**Ошибка "dockerDesktopLinuxEngine pipe missing":**
- Docker Desktop engine не запущен. Решение: перезапустите Docker Desktop (если WSL2: `wsl --shutdown`, затем перезапустите Docker Desktop).

**Ошибка 401 при входе:**
1. Проверьте логи: `docker compose logs api | Select-String -Pattern "Bootstrap"`
2. Создайте пользователя вручную: `docker compose exec api python /app/scripts/create_admin_user.py admin123`

**Проверка таблиц в БД:**
```powershell
docker compose exec postgres psql -U wb -d wb -c "\dt"
```

Должны быть таблицы: `users`, `projects`, `project_members`, и другие.

Подробнее см. `infra/docker/README.md`.

### Быстрый запуск (рекомендуется)

Используйте скрипт для автоматической обработки конфликтов портов:

```powershell
cd D:\Work\EcomCore
.\scripts\start-docker-compose.ps1 -Force
```

Скрипт автоматически:
- Останавливает конфликтующие контейнеры на порту 8000
- Останавливает старые контейнеры из предыдущих проектов
- Запускает все сервисы

### Ручной запуск

```powershell
cd D:\Work\EcomCore\infra\docker
docker compose down
docker compose up -d --build
docker compose exec api alembic upgrade head
```

### Порты и доступ

После запуска сервисы доступны по следующим адресам:

- **Frontend**: http://localhost (через nginx)
- **API**: http://localhost:8000 (прямой доступ)
- **API через nginx**: http://localhost/api/ (проксируется на api:8000)
- **API Docs**: http://localhost:8000/docs
- **Adminer**: http://localhost/adminer/ (требует basic auth)

### Решение конфликтов портов

Если порт 8000 занят другим контейнером:

1. **Автоматически** (рекомендуется):
   ```powershell
   .\scripts\start-docker-compose.ps1 -Force
   ```

2. **Вручную**:
   ```powershell
   # Найти контейнер, использующий порт 8000
   docker ps -a --filter "publish=8000"
   
   # Остановить конфликтующий контейнер
   docker stop <container-name>
   docker rm <container-name>
   ```

3. **Остановить старый проект docker**:
   ```powershell
   cd D:\Work\EcomCore\infra\docker
   docker compose -p docker down
   ```

### Docker filesystem/metadata corruption (I/O ошибки)

Если при запуске возникает ошибка:
```
Error response from daemon: ... input/output error
```

Используйте скрипт восстановления:

**Из корня репозитория:**
```powershell
cd D:\Work\EcomCore
.\scripts\docker_recover.ps1
```

**Из infra/docker:**
```powershell
cd D:\Work\EcomCore\infra\docker
..\..\scripts\docker_recover.ps1
```

Скрипт работает из любой директории и автоматически определяет пути. Подробные инструкции по восстановлению см. в `infra/docker/README.md`.

### Важно

- Файл `.env` должен находиться в корне репозитория (`D:\Work\EcomCore\.env`)
- Docker Compose автоматически использует этот файл для переменных окружения
- Проект использует стабильное имя `ecomcore` для предотвращения дублирования контейнеров
- Все сервисы подключены к сети `ecomcore-network` для корректной работы nginx upstream

## Последние цены (Latest Prices)

### SQL VIEW: v_products_latest_price

Для эффективного получения последней цены каждого продукта используется SQL VIEW `v_products_latest_price`. 

**Что это такое:**
VIEW автоматически выбирает самую свежую запись из таблицы `price_snapshots` для каждого `nm_id`, используя `DISTINCT ON` для оптимизации производительности.

**Зачем нужна:**
- Избегает необходимости хранить текущую цену в таблице `products` (нормализация данных)
- Обеспечивает актуальность данных без дополнительных обновлений
- Упрощает запросы для получения последних цен

**Как обновляется:**
VIEW создаётся и обновляется через Alembic миграции. При добавлении новых записей в `price_snapshots` VIEW автоматически отражает последние значения. Для изменения структуры VIEW необходимо создать новую миграцию.

**Структура VIEW:**
- `nm_id` - идентификатор товара
- `wb_price` - цена Wildberries
- `wb_discount` - скидка (%)
- `spp` - дополнительная скидка (%)
- `customer_price` - итоговая цена для покупателя
- `rrc` - рекомендованная розничная цена
- `price_at` - время создания снимка цены

## Последние остатки (Latest Stocks)

### SQL VIEW: v_products_latest_stock

Для эффективного получения последнего остатка каждого продукта используется SQL VIEW `v_products_latest_stock`.

**Что это такое:**
VIEW автоматически выбирает самую свежую запись из таблицы `stock_snapshots` для каждого `nm_id` и суммирует остатки по всем складам на момент последнего snapshot.

**Зачем нужна:**
- Избегает необходимости хранить текущий остаток в таблице `products`
- Автоматически агрегирует остатки по складам
- Обеспечивает актуальность данных без дополнительных обновлений

**Как обновляется:**
VIEW создаётся и обновляется через Alembic миграции. При добавлении новых записей в `stock_snapshots` VIEW автоматически отражает последние значения.

**Структура VIEW:**
- `nm_id` - идентификатор товара
- `total_quantity` - суммарный остаток по всем складам
- `stock_at` - время последнего snapshot остатков

## База артикулов (Article Base)

### SQL VIEW: v_article_base

Единая витрина со всеми артикулами, остатками и ценами из всех источников.

**Что это такое:**
VIEW объединяет данные из всех источников:
- **WB Supplier Stocks** (`supplier_stock_snapshots`): остатки на складах WB, nm_id, barcode, supplier_article
- **WB API Prices** (`price_snapshots`): наши цены и скидки, выставленные на WB
- **Frontend Catalog** (`frontend_catalog_price_snapshots`): цена на витрине WB и СПП (co-invest discount)
- **1C XML** (`rrp_snapshots`): РРЦ цена и остаток из 1С

**Нормализация артикула:**
- В WB `supplierArticle` хранится как `"560/ZKPY-1138"`
- В нашей базе нужен `"ZKPY-1138"` (часть после `/`, обрезаны пробелы)
- Функция нормализации: `src/app/utils/vendor_code.py::normalize_vendor_code()`
- В SQL: `SPLIT_PART(supplier_article, '/', 2)` с `TRIM()`

**Структура VIEW:**
- `Артикул` (vendor_code_norm) - нормализованный артикул
- `NMid` (nm_id) - артикул WB
- `ШК` (barcode) - штрихкод
- `Наша цена (РРЦ)` (rrp_price) - из 1С XML
- `Цена на витрине` (wb_showcase_price) - из фронта WB (`price_basic` из `frontend_catalog_price_snapshots`)
- `Скидка наша` (wb_our_discount) - из WB API (`wb_discount` из `price_snapshots`)
- `СПП` (wb_spp_discount) - из фронта WB (`sale_percent` из `frontend_catalog_price_snapshots`)
- `Остаток WB` (supplier_qty_total) - сумма остатков по всем складам WB
- `Остаток 1С` (rrp_stock) - остаток из 1С XML
- `Обновлено WB`, `Обновлено 1С`, `Обновлено фронт`, `Обновлено WB API` - даты последних обновлений

**Источники данных (источник правды):**
- `wb_showcase_price`: `frontend_catalog_price_snapshots.price_basic` (цена на витрине WB)
- `wb_our_discount`: `price_snapshots.wb_discount` (скидка, которую установили мы)
- `wb_spp_discount`: `frontend_catalog_price_snapshots.sale_percent` (СПП от WB)
- `rrp_price`: `rrp_snapshots.rrp_price` (РРЦ из 1С/XML)

**Ключи склейки:**
- Основной ключ: `nm_id + barcode`
- `vendor_code_norm` берётся приоритетно из `rrp_snapshots`, иначе из `supplier_stock_snapshots.supplier_article` (нормализованный)
- RRP матчится по `barcode` (лучше) или по `vendor_code_norm` (fallback)
- Frontend prices матчатся по `nm_id`
- WB API prices матчатся по `nm_id`

## API Endpoints

### Получение последних цен

```bash
# Получить последние цены (с пагинацией)
curl "http://localhost:8000/api/v1/prices/latest?limit=50&offset=0"
```

Возвращает список последних цен для всех продуктов, отсортированный по `nm_id`.

### Получение продуктов с последними ценами

```bash
# Получить продукты с их последними ценами
curl "http://localhost:8000/api/v1/products/with-latest-price?limit=50&offset=0"
```

Возвращает объединённые данные из таблиц `products` и `v_products_latest_price`, включая информацию о продукте и его последней цене.

### Получение продуктов с ценами и остатками

```bash
# Получить продукты с последними ценами и остатками
curl "http://localhost:8000/api/v1/products/with-latest-price-and-stock?limit=50&offset=0"
```

Возвращает объединённые данные из таблиц `products`, `v_products_latest_price` и `v_products_latest_stock`, включая информацию о продукте, его последней цене и остатках.

### Получение базы артикулов (Article Base)

```bash
# Получить витрину артикулов (с пагинацией)
curl "http://localhost:8000/api/v1/articles/base?limit=50&offset=0"

# Поиск по артикулу или NMid
curl "http://localhost:8000/api/v1/articles/base?limit=50&offset=0&search=ZKPY-1138"
```

Возвращает данные из VIEW `v_article_base` с объединёнными ценами и остатками из всех источников.

**Параметры:**
- `limit` (default: 50) - количество записей на странице
- `offset` (default: 0) - смещение для пагинации
- `search` (optional) - поиск по `vendor_code_norm` (ILIKE) или `nm_id::text` (ILIKE)

**Пример ответа:**
```json
{
  "data": [
    {
      "Артикул": "ZKPY-1138",
      "NMid": 12345678,
      "ШК": "2000123456789",
      "Наша цена (РРЦ)": 599.00,
      "Цена на витрине": 549.00,
      "Скидка наша": 5.0,
      "СПП": 10,
      "Остаток WB": 150,
      "Остаток 1С": 120,
      "Обновлено WB": "2026-01-14T10:00:00",
      "Обновлено 1С": "2026-01-14T09:00:00"
    }
  ],
  "limit": 50,
  "offset": 0,
  "count": 1,
  "total": 1000
}
```

## Ingestion

### Загрузка продуктов

```bash
# Проверить статус конфигурации
curl "http://localhost:8000/api/v1/ingest/products"

# Запустить загрузку продуктов
curl -X POST "http://localhost:8000/api/v1/ingest/products"
```

### Загрузка складов

```bash
# Проверить статус конфигурации
curl "http://localhost:8000/api/v1/ingest/warehouses"

# Запустить загрузку справочника складов
curl -X POST "http://localhost:8000/api/v1/ingest/warehouses"
```

### Загрузка остатков (Marketplace API)

```bash
# Проверить статус конфигурации (нужен токен категории «Маркетплейс»)
curl "http://localhost:8000/api/v1/ingest/stocks"

# Запустить загрузку остатков (использует POST /api/v3/stocks/{warehouseId} WB API)
curl -X POST "http://localhost:8000/api/v1/ingest/stocks"

# Проверить, что снимки остатков появились в БД
docker compose exec -T postgres psql -U wb -d wb -c "SELECT COUNT(*) FROM stock_snapshots;"

# Быстрый просмотр последних остатков
curl -s "http://localhost:8000/api/v1/stocks/latest?limit=5" | python3 -m json.tool
```

**Примечание:** В режиме MOCK (когда `WB_TOKEN=MOCK` или не установлен) ingestion будет пропущен с соответствующим сообщением.

### WB остатки на складах (Reports / Statistics API)

Загрузка остатков из раздела Reports (Statistics API), отчёт "Остатки на складах".

**Особенности:**
- Endpoint: `GET https://statistics-api.wildberries.ru/api/v1/supplier/stocks`
- Rate limit: 1 запрос в минуту (автоматический throttling)
- Пагинация: через параметр `dateFrom` (используется MAX(`lastChangeDate`) из страницы минус 1 секунда для overlap)
- Защита от зацикливания: максимум 200 страниц за запуск, проверка прогресса по датам
- Инкрементальная загрузка: overlap window 2 минуты от MAX(`last_change_date`) в БД
- Данные обновляются каждые ~30 минут
- Лимит ответа: ~60 000 строк на запрос

**Команды:**

```bash
# Проверить статус конфигурации
curl "http://localhost:8000/api/v1/ingest/supplier-stocks"

# Запустить загрузку остатков
curl -X POST "http://localhost:8000/api/v1/ingest/supplier-stocks"

# Проверить количество записей в БД
docker compose exec -T postgres psql -U wb -d wb -c "SELECT COUNT(*) FROM supplier_stock_snapshots;"

# Проверить диапазон дат (min/max last_change_date)
docker compose exec -T postgres psql -U wb -d wb -c "SELECT MIN(last_change_date) AS min_date, MAX(last_change_date) AS max_date, COUNT(*) AS total FROM supplier_stock_snapshots;"

# Посмотреть последние записи
curl -s "http://localhost:8000/api/v1/supplier-stocks/latest?limit=5" | python3 -m json.tool
```

**Настройка:**
- Начальная дата по умолчанию: `2019-06-20T00:00:00Z` (можно переопределить через `WB_STOCKS_DATE_FROM_DEFAULT`)
- Инкрементальная загрузка: если в БД уже есть данные, ingestion продолжит с `MAX(last_change_date) - 2 минуты` (overlap window для защиты от потери данных)
- Пагинация: на каждой странице вычисляется MAX(`lastChangeDate`), следующий `dateFrom = MAX - 1 секунда` (overlap для пограничных записей)
- Защита от зацикливания: максимум 200 страниц за запуск, проверка прогресса по датам
- Требуется токен с категорией "Статистика" (Statistics API)

### Загрузка RRP из 1С XML

Загрузка цен РРЦ и остатков из XML файла (выгрузка из 1С).

**Особенности:**
- Читает XML файл из `RRP_XML_PATH` (по умолчанию: `/app/test.xml`)
- Парсит `<item>` элементы с атрибутами: `article`, `stock`, `price`
- Нормализует артикул (извлекает часть после `/`)
- Upsert по `(snapshot_at::date, vendor_code_norm, barcode)`

**Команды:**

```bash
# Проверить статус конфигурации
curl "http://localhost:8000/api/v1/ingest/rrp-xml"

# Запустить загрузку RRP из XML
curl -X POST "http://localhost:8000/api/v1/ingest/rrp-xml"

# Проверить количество записей в БД
docker compose exec -T postgres psql -U wb -d wb -c "SELECT COUNT(*) FROM rrp_snapshots;"

# Посмотреть последние записи
curl -s "http://localhost:8000/api/v1/rrp/latest?limit=5" | python3 -m json.tool
```

**Настройка:**
- Путь к XML файлу: переменная окружения `RRP_XML_PATH` (по умолчанию: `/app/test.xml`)
- В будущем будет приходить по FTP, сейчас читаем локальный файл

## Доступ к Adminer

Adminer доступен через nginx по пути `/adminer/` и защищён basic authentication.

**Настройка пароля:**

1. Установить `apache2-utils` (если не установлен):
   ```bash
   apt-get update && apt-get install -y apache2-utils
   ```

2. Создать файл с паролем:
   ```bash
   htpasswd -c nginx/.htpasswd admin
   ```
   Команда запросит пароль для пользователя `admin`.

3. Перезапустить nginx:
   ```bash
   docker compose restart nginx
   ```

**Доступ:**
- URL: `http://<IP>/adminer/`
- Порт 8080 не публикуется наружу (доступ только через nginx)
- При первом запросе браузер попросит ввести логин и пароль

**Подключение к БД в Adminer:**
- System: `PostgreSQL`
- Server: `postgres`
- Username: `wb`
- Password: значение из `.env` (переменная `POSTGRES_PASSWORD`)
- Database: `wb`

## Запуск

```bash
docker compose up -d
docker compose exec api alembic upgrade head
```

## Миграции

Все изменения схемы БД выполняются через Alembic миграции:

```bash
docker compose exec api alembic upgrade head
```

### Sanity-check: multiple heads

Иногда при параллельной разработке Alembic может получить несколько heads, и тогда `alembic upgrade head` падает с ошибкой вида:
`Multiple head revisions are present for given argument 'head'`.

- **Проверка**:
  - `docker compose exec api alembic heads`
  - или локально: `python scripts/check_alembic_heads.py`
- **Фикс (без drop/reset)**: создать *пустую merge-миграцию*, которая объединяет оба head'а (down_revision = (HEAD_A, HEAD_B)).

### Новые миграции (Спринт #1)

1. **b1c2d3e4f5a6** - `add_rrp_snapshots_table`: таблица для данных из 1С XML
2. **c2d3e4f5a6b7** - `add_v_article_base_view`: VIEW для единой витрины артикулов

## Проверки и SQL запросы

### Проверка витрины v_article_base

```sql
-- Сколько строк в витрине
SELECT COUNT(*) FROM v_article_base;

-- Сколько уникальных nm_id
SELECT COUNT(DISTINCT "NMid") FROM v_article_base;

-- Пример по конкретному артикулу
SELECT * FROM v_article_base WHERE "Артикул" = 'ZKPY-1138';

-- Проверка нормализации артикула
SELECT 
    supplier_article,
    CASE 
        WHEN supplier_article LIKE '%/%' THEN TRIM(SPLIT_PART(supplier_article, '/', 2))
        ELSE TRIM(supplier_article)
    END AS normalized
FROM supplier_stock_snapshots
WHERE supplier_article IS NOT NULL
LIMIT 10;
```

## Порядок запуска ingestion

Для полной загрузки данных рекомендуется следующий порядок:

```bash
# 1. Загрузка остатков на складах WB (Statistics API)
curl -X POST "http://localhost:8000/api/v1/ingest/supplier-stocks"

# 2. Загрузка наших цен и скидок (WB Marketplace API)
curl -X POST "http://localhost:8000/api/v1/ingest/prices"

# 3. Загрузка цен с фронта WB (парсер catalog.wb.ru)
curl -X POST "http://localhost:8000/api/v1/ingest/frontend-prices/brand" \
  -H "Content-Type: application/json" \
  -d '{"brand_id": 41189, "max_pages": 0, "sleep_ms": 800}'

# 4. Загрузка RRP из 1С XML
curl -X POST "http://localhost:8000/api/v1/ingest/rrp-xml"
```

После выполнения всех ingestion'ов данные будут доступны в VIEW `v_article_base`.

## Деплой на сервер

**Важно:** Никаких правок кода напрямую на сервере, кроме аварийных хотфиксов с обязательным push.

### Процедура деплоя:

```bash
cd /home/deploy/wb-automation
git pull origin main
docker compose up -d --build
docker compose exec -T api alembic upgrade head
```

### Локальная разработка:

1. Клонировать репозиторий на локальный ПК:
   ```bash
   git clone git@github.com:<USER>/<REPO>.git
   ```

2. Открывать проект в Cursor из локальной папки

3. После изменений:
   ```bash
   git add .
   git commit -m "описание изменений"
   git push origin main
   ```

4. На сервере выполнить процедуру деплоя (см. выше)

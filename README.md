# WB Automation

API для автоматизации работы с Wildberries: загрузка продуктов, синхронизация цен, получение актуальной информации.

## Архитектура

Проект использует FastAPI, PostgreSQL, Redis и Celery для фоновых задач. Все сервисы запускаются через Docker Compose.

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
- Пагинация: через параметр `dateFrom` (используется `lastChangeDate` последней строки)
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

# Посмотреть последние записи
curl -s "http://localhost:8000/api/v1/supplier-stocks/latest?limit=5" | python3 -m json.tool
```

**Настройка:**
- Начальная дата по умолчанию: `2019-06-20T00:00:00Z` (можно переопределить через `WB_STOCKS_DATE_FROM_DEFAULT`)
- Инкрементальная загрузка: если в БД уже есть данные, ingestion продолжит с `MAX(last_change_date)`
- Требуется токен с категорией "Статистика" (Statistics API)

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


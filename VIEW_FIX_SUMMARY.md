# Исправление ошибки VIEW v_article_base

## Проблема

**Ошибка:** `sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedTable) relation "supplier_stock_snapshots" does not exist`

**Причина:** Миграции `0fd96b01e954` и `optimize_v_article_base_performance` создают VIEW `v_article_base`, который ссылается на таблицы:
- `supplier_stock_snapshots`
- `price_snapshots`
- `frontend_catalog_price_snapshots`
- `rrp_snapshots`

Но эти таблицы могут не существовать при применении миграций.

## Исправление

Добавлена проверка существования всех необходимых таблиц перед созданием VIEW в миграциях:
- `alembic/versions/0fd96b01e954_fix_v_article_base_full_outer_join.py`
- `alembic/versions/optimize_v_article_base_performance.py`

Если таблицы отсутствуют - миграция пропускает создание VIEW (как в `c2d3e4f5a6b7`).

## Проверка

```powershell
# 1. Применить миграции
docker compose exec api alembic upgrade head

# 2. Проверить что нет ошибок UndefinedTable
# (миграция должна завершиться без ошибок)

# 3. Проверить что health endpoint работает
Invoke-WebRequest -Uri "http://localhost/api/v1/health" -Method GET

# 4. Проверить что VIEW создан (если таблицы существуют)
docker compose exec postgres psql -U wb -d wb -c "SELECT COUNT(*) FROM information_schema.views WHERE table_name = 'v_article_base';"
```

**Ожидается:** 
- Миграции применяются без ошибок
- Health endpoint возвращает `200 OK`
- VIEW создается только если все необходимые таблицы существуют



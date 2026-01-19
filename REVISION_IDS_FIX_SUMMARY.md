# Исправление revision IDs: Итоговый отчет

## Исправленные миграции

### 1. add_unique_products_project_nm_id.py
- **Revision ID:** `add_unique_products_project_nm_id` → `946d21840243`
- **Файл:** `alembic/versions/add_unique_products_project_nm_id.py`

### 2. add_api_token_encrypted_to_project_marketplaces.py
- **Revision ID:** `add_api_token_encrypted` → `e373f63d276a`
- **Down revision:** `add_unique_products_project_nm_id` → `946d21840243`
- **Файл:** `alembic/versions/add_api_token_encrypted_to_project_marketplaces.py`

### 3. merge_heads_a2b730f4e786_and_add_api_token_encrypted.py
- **Revision ID:** `merge_heads_token_encryption` → `670ed0736bfa`
- **Down revision:** `('a2b730f4e786', 'add_api_token_encrypted')` → `('a2b730f4e786', 'e373f63d276a')`
- **Файл:** `alembic/versions/merge_heads_a2b730f4e786_and_add_api_token_encrypted.py`

## Результат

После исправлений:
- ✅ Один HEAD: `670ed0736bfa` (hex формат)
- ✅ Все revision IDs в hex формате
- ✅ Граф миграций корректен

## Стратегия для уже примененных миграций

Если миграции уже применены в БД со старыми revision IDs, используйте `alembic stamp`:

```bash
# 1. Проверить текущую версию
docker compose exec api alembic current

# 2. Определить какая версия применена и обновить на hex:
#    Если текущая версия = 'add_unique_products_project_nm_id':
docker compose exec api alembic stamp 946d21840243

#    Если текущая версия = 'add_api_token_encrypted':
docker compose exec api alembic stamp e373f63d276a

#    Если текущая версия = 'merge_heads_token_encryption':
docker compose exec api alembic stamp 670ed0736bfa

# 3. Проверить обновление
docker compose exec api alembic current
# Ожидается: hex revision ID

# 4. Применить оставшиеся миграции (если есть)
docker compose exec api alembic upgrade head
```

## Команды проверки

```bash
# 1. Проверить heads (один hex ID)
docker compose exec api alembic heads
# Ожидается: 670ed0736bfa (head)

# 2. Проверить текущую версию (hex формат)
docker compose exec api alembic current
# Ожидается: hex revision ID (не строковый)

# 3. Проверить историю (все в hex)
docker compose exec api alembic history
# Ожидается: все revision IDs в hex формате

# 4. Проверить на чистой БД
docker compose down -v
docker compose up -d postgres
sleep 5
docker compose exec api alembic upgrade head
# Ожидается: все миграции применяются, все revision IDs в hex формате
```

## Новые revision IDs

- `946d21840243` - add_unique_products_project_nm_id
- `e373f63d276a` - add_api_token_encrypted
- `670ed0736bfa` - merge_heads_token_encryption (HEAD)



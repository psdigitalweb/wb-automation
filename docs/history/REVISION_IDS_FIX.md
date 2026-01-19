# Исправление revision IDs на hex формат

## Проблема

Некоторые миграции используют строковые revision IDs вместо hex формата:
- `add_unique_products_project_nm_id` → `946d21840243`
- `add_api_token_encrypted` → `e373f63d276a`
- `merge_heads_token_encryption` → `670ed0736bfa`

## Исправления

### 1. add_unique_products_project_nm_id.py
- **Было:** `revision: str = 'add_unique_products_project_nm_id'`
- **Стало:** `revision: str = '946d21840243'`

### 2. add_api_token_encrypted_to_project_marketplaces.py
- **Было:** `revision: str = 'add_api_token_encrypted'`
- **Стало:** `revision: str = 'e373f63d276a'`
- **Было:** `down_revision = 'add_unique_products_project_nm_id'`
- **Стало:** `down_revision = '946d21840243'`

### 3. merge_heads_a2b730f4e786_and_add_api_token_encrypted.py
- **Было:** `revision: str = 'merge_heads_token_encryption'`
- **Стало:** `revision: str = '670ed0736bfa'`
- **Было:** `down_revision = ('a2b730f4e786', 'add_api_token_encrypted')`
- **Стало:** `down_revision = ('a2b730f4e786', 'e373f63d276a')`

## Стратегия для уже примененных миграций

Если миграции уже применены в БД, нужно использовать `alembic stamp` для обновления версии без повторного применения:

```bash
# 1. Проверить текущую версию
docker compose exec api alembic current

# 2. Если миграции применены со старыми revision IDs:
#    - Если текущая версия = 'add_api_token_encrypted':
docker compose exec api alembic stamp e373f63d276a

#    - Если текущая версия = 'merge_heads_token_encryption':
docker compose exec api alembic stamp 670ed0736bfa

#    - Если текущая версия = 'add_unique_products_project_nm_id':
docker compose exec api alembic stamp 946d21840243

# 3. Проверить что версия обновлена
docker compose exec api alembic current
# Ожидается: hex revision ID

# 4. Применить оставшиеся миграции (если есть)
docker compose exec api alembic upgrade head
```

## Команды проверки

```bash
# 1. Проверить heads (должен быть один hex ID)
docker compose exec api alembic heads
# Ожидается: 670ed0736bfa (head)

# 2. Проверить текущую версию
docker compose exec api alembic current
# Ожидается: hex revision ID (не строковый)

# 3. Проверить историю
docker compose exec api alembic history
# Ожидается: все revision IDs в hex формате

# 4. Проверить на чистой БД
docker compose down -v
docker compose up -d postgres
sleep 5
docker compose exec api alembic upgrade head
# Ожидается: все миграции применяются, revision IDs в hex формате
```

## Файлы изменены

1. `alembic/versions/add_unique_products_project_nm_id.py`
2. `alembic/versions/add_api_token_encrypted_to_project_marketplaces.py`
3. `alembic/versions/merge_heads_a2b730f4e786_and_add_api_token_encrypted.py`



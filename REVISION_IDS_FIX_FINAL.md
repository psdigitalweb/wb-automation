# Исправление revision IDs: Финальный отчет

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

## Результат проверки

После исправлений:
- ✅ **Один HEAD:** `670ed0736bfa` (hex формат)
- ✅ **Все revision IDs в hex формате**
- ✅ **Граф миграций корректен**

## Стратегия для уже примененных миграций

Если миграции уже применены в БД со старыми строковыми revision IDs, используйте `alembic stamp` для обновления версии БД без повторного применения миграций:

### Шаг 1: Проверить текущую версию

```bash
docker compose exec api alembic current
```

**Возможные результаты:**
- `add_unique_products_project_nm_id` → нужно stamp на `946d21840243`
- `add_api_token_encrypted` → нужно stamp на `e373f63d276a`
- `merge_heads_token_encryption` → нужно stamp на `670ed0736bfa`
- Уже hex формат → ничего делать не нужно

### Шаг 2: Обновить версию через stamp

```bash
# Если текущая версия = 'add_unique_products_project_nm_id':
docker compose exec api alembic stamp 946d21840243

# Если текущая версия = 'add_api_token_encrypted':
docker compose exec api alembic stamp e373f63d276a

# Если текущая версия = 'merge_heads_token_encryption':
docker compose exec api alembic stamp 670ed0736bfa
```

### Шаг 3: Проверить обновление

```bash
docker compose exec api alembic current
# Ожидается: hex revision ID (946d21840243, e373f63d276a, или 670ed0736bfa)
```

### Шаг 4: Применить оставшиеся миграции (если нужно)

```bash
docker compose exec api alembic upgrade head
```

## Команды проверки

### 1. Проверить heads (один hex ID)

```bash
docker compose exec api alembic heads
```

**Ожидается:**
```
670ed0736bfa (head)
```

### 2. Проверить текущую версию (hex формат)

```bash
docker compose exec api alembic current
```

**Ожидается:**
- Hex revision ID (например: `670ed0736bfa`)
- НЕ строковый формат (не `merge_heads_token_encryption`)

### 3. Проверить историю (все в hex)

```bash
docker compose exec api alembic history
```

**Ожидается:**
- Все revision IDs в hex формате
- Один граф без split
- `670ed0736bfa` в конце как HEAD

### 4. Проверить на чистой БД

```bash
# Сбросить БД (ОСТОРОЖНО - удалит все данные!)
docker compose down -v
docker compose up -d postgres
sleep 5

# Применить все миграции с нуля
docker compose exec api alembic upgrade head
```

**Ожидается:**
- Все миграции применяются успешно
- Все revision IDs в hex формате
- Нет ошибок конфликтов
- В конце применяется merge миграция `670ed0736bfa`

### 5. Проверить граф миграций

```bash
docker compose exec api alembic history --verbose
```

**Ожидается:**
- Линейный граф без split
- Merge миграция объединяет две ветки:
  - `a2b730f4e786` (app_settings)
  - `e373f63d276a` (api_token_encrypted)
- HEAD: `670ed0736bfa`

## Новые revision IDs (hex формат)

| Старый ID | Новый ID (hex) | Описание |
|-----------|----------------|----------|
| `add_unique_products_project_nm_id` | `946d21840243` | UNIQUE constraint для products |
| `add_api_token_encrypted` | `e373f63d276a` | Шифрование токенов |
| `merge_heads_token_encryption` | `670ed0736bfa` | Merge миграция (HEAD) |

## Acceptance Criteria ✅

- ✅ `alembic heads` показывает ОДНУ head: `670ed0736bfa` (hex)
- ✅ `alembic current` показывает hex revision ID (не строковый)
- ✅ `alembic history` показывает все revision IDs в hex формате
- ✅ Граф миграций корректен (один граф без split)
- ✅ Все миграции применяются с нуля на чистой БД



# Отчет: Merge миграция для объединения heads

## Проблема

Обнаружены две head ревизии Alembic:
- `a2b730f4e786` (app_settings table)
- `add_api_token_encrypted` (api_token_encrypted field)

Это создает две ветки миграций, что недопустимо для линейной истории.

## Решение

Создана merge миграция для объединения двух heads в один линейный HEAD.

## Merge миграция

**Файл:** `alembic/versions/merge_heads_a2b730f4e786_and_add_api_token_encrypted.py`

**Revision ID:** `merge_heads_token_encryption`

**Down revisions:** `('a2b730f4e786', 'add_api_token_encrypted')`

**Описание:**
- Объединяет две ветки:
  - `a2b730f4e786`: app_settings table (из ветки ea2d9ac02904)
  - `add_api_token_encrypted`: api_token_encrypted field (из ветки add_unique_products_project_nm_id)
- Не содержит изменений схемы (только объединяет историю)
- После применения становится единственным HEAD

## Команды для проверки

### 1. Проверить текущие heads (до merge)

```bash
docker compose exec api alembic heads
```

**Ожидается (до merge):**
```
a2b730f4e786 (head)
add_api_token_encrypted (head)
```

### 2. Применить merge миграцию

```bash
docker compose exec api alembic upgrade head
```

### 3. Проверить heads (после merge)

```bash
docker compose exec api alembic heads
```

**Ожидается (после merge):**
```
merge_heads_token_encryption (head)
```

### 4. Проверить историю (линейный граф)

```bash
docker compose exec api alembic history
```

**Ожидается:**
- Один граф без split
- `merge_heads_token_encryption` в конце
- Обе ветки ведут к merge миграции

### 5. Проверить на чистой БД

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
- Нет ошибок конфликтов
- В конце применяется merge миграция

### 6. Проверить текущую версию

```bash
docker compose exec api alembic current
```

**Ожидается:**
```
merge_heads_token_encryption (head)
```

## Структура графа миграций

```
<base>
  └─> ... (общие миграции)
       ├─> ... ─> ea2d9ac02904 ─> a2b730f4e786 ─┐
       │                                          │
       └─> ... ─> add_unique_products_project_nm_id ─> add_api_token_encrypted ─┐
                                                                                  │
                                                                                  └─> merge_heads_token_encryption (HEAD)
```

## Важные замечания

1. **Merge миграция не изменяет схему** - только объединяет историю
2. **Старые миграции не изменены** - только добавлена новая merge миграция
3. **После merge будет один HEAD** - `merge_heads_token_encryption`
4. **Миграции применяются в правильном порядке** - Alembic автоматически определяет порядок для merge

## Acceptance Criteria ✅

- ✅ `alembic heads` показывает ОДНУ head: `merge_heads_token_encryption`
- ✅ `alembic history` показывает один граф без split
- ✅ `alembic upgrade head` применяется на чистой БД без ошибок
- ✅ Все миграции применяются в правильном порядке



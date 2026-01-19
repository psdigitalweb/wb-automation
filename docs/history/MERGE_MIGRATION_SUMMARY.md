# Merge миграция: Объединение heads

## Проблема

Обнаружены две head ревизии:
- `a2b730f4e786` (app_settings table)
- `add_api_token_encrypted` (api_token_encrypted field)

## Решение

Создана merge миграция: `merge_heads_a2b730f4e786_and_add_api_token_encrypted.py`

**Revision ID:** `merge_heads_token_encryption`

**Down revisions:** `('a2b730f4e786', 'add_api_token_encrypted')`

## Результат

После применения merge миграции:
- ✅ Один HEAD: `merge_heads_token_encryption`
- ✅ Линейный граф без split
- ✅ Все миграции применяются с нуля

## Команды проверки

```bash
# 1. Проверить heads (должен быть один)
docker compose exec api alembic heads
# Ожидается: merge_heads_token_encryption (head)

# 2. Применить миграции
docker compose exec api alembic upgrade head

# 3. Проверить историю (линейный граф)
docker compose exec api alembic history

# 4. Проверить на чистой БД
docker compose down -v
docker compose up -d postgres
sleep 5
docker compose exec api alembic upgrade head
# Ожидается: все миграции применяются успешно
```

## Файл merge миграции

`alembic/versions/merge_heads_a2b730f4e786_and_add_api_token_encrypted.py`



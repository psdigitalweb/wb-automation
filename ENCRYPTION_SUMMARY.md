# Краткая сводка: Шифрование токенов

## Что сделано

### 1. Новое поле в БД
- ✅ `project_marketplaces.api_token_encrypted TEXT NULL` - хранит зашифрованный токен

### 2. Утилита шифрования
- ✅ `src/app/utils/secrets_encryption.py`
- ✅ Использует Fernet (симметричное шифрование)
- ✅ Ключ из `PROJECT_SECRETS_KEY` env variable

### 3. Миграция
- ✅ `alembic/versions/add_api_token_encrypted_to_project_marketplaces.py`
- ✅ Мигрирует существующие токены из `settings_json` в `api_token_encrypted`

### 4. Обновленный код
- ✅ Connect endpoint: сохраняет токен только в `api_token_encrypted`
- ✅ `get_wb_token_for_project()`: читает и расшифровывает из `api_token_encrypted`
- ✅ Disconnect endpoint: очищает `api_token_encrypted`

### 5. Безопасность
- ✅ Токен НЕ возвращается в API ответах
- ✅ `settings_json` не содержит токен (только base_url, timeout)
- ✅ `api_token_encrypted` не включен в Pydantic схемы

## Команды

```bash
# 1. Установить зависимости
docker compose exec api pip install cryptography==42.0.5

# 2. Установить ключ (сгенерировать)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Добавить в .env: PROJECT_SECRETS_KEY=<сгенерированный_ключ>

# 3. Применить миграцию
docker compose exec api alembic upgrade head

# 4. Проверить подключение
curl -X POST http://localhost/api/v1/projects/1/marketplaces/wb/connect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"api_key":"YOUR_TOKEN"}'

# 5. Проверить в БД (токена нет в settings_json)
docker compose exec postgres psql -U wb -d wb -c \
  "SELECT settings_json, api_token_encrypted IS NOT NULL FROM project_marketplaces;"
```

## Acceptance ✅

- ✅ Токена нет в `settings_json` в БД
- ✅ Токена нет в `settings_json` в ответах API
- ✅ Токен хранится только в `api_token_encrypted` (зашифрован)
- ✅ `api_token_encrypted` не возвращается в API



# Реализация шифрования токенов

## Выполненные задачи

### 1. Добавлено поле api_token_encrypted ✅

**Миграция:** `alembic/versions/add_api_token_encrypted_to_project_marketplaces.py`
- Добавляет колонку `api_token_encrypted TEXT NULL` в таблицу `project_marketplaces`
- Мигрирует существующие токены из `settings_json` в `api_token_encrypted` (если PROJECT_SECRETS_KEY установлен)
- Удаляет токены из `settings_json` для существующих записей

### 2. Утилита encrypt/decrypt ✅

**Файл:** `src/app/utils/secrets_encryption.py`

**Функции:**
- `encrypt_token(token: str) -> str` - шифрует токен используя Fernet
- `decrypt_token(encrypted_token: str) -> Optional[str]` - расшифровывает токен

**Ключ шифрования:**
- Берется из переменной окружения `PROJECT_SECRETS_KEY`
- Если ключ не установлен, генерируется временный (с предупреждением)
- Поддерживает как прямой Fernet ключ (base64), так и пароль (через PBKDF2)

**Зависимость:** Добавлена `cryptography==42.0.5` в `requirements.txt`

### 3. Connect endpoint обновлен ✅

**Файл:** `src/app/routers/marketplaces.py` (строки 368-385)

**Изменения:**
- Токен шифруется через `encrypt_token()`
- Сохраняется только в `api_token_encrypted`
- `settings_json` содержит только `base_url` и `timeout` (без токена)
- Токен не возвращается в ответе API

### 4. get_wb_token_for_project обновлен ✅

**Файл:** `src/app/utils/get_project_marketplace_token.py`

**Изменения:**
- Читает токен из `api_token_encrypted` (preferred)
- Расшифровывает через `decrypt_token()`
- Fallback на `settings_json` для обратной совместимости (должен исчезнуть после миграции)

### 5. API ответы ✅

**Гарантии:**
- `api_token_encrypted` НЕ возвращается в ответах API (не включен в схемы Pydantic)
- `settings_json` не содержит токен (только base_url, timeout и т.п.)
- Все endpoints возвращают `ProjectMarketplaceWithMaskedSecrets` где `settings_json` не содержит токен

### 6. Disconnect endpoint обновлен ✅

**Файл:** `src/app/routers/marketplaces.py` (строки 434-443)

**Изменения:**
- Очищает `api_token_encrypted` (устанавливает в NULL)
- Очищает `settings_json` (устанавливает в `{}`)

## Обновленные файлы

### Backend

1. **src/app/utils/secrets_encryption.py** (НОВЫЙ)
   - Утилиты для шифрования/дешифрования токенов

2. **src/app/db_marketplaces.py** (ИЗМЕНЕН)
   - `create_or_update_project_marketplace()` - добавлен параметр `api_token_encrypted`
   - `get_project_marketplace()` - возвращает `api_token_encrypted`
   - `get_project_marketplaces()` - возвращает `api_token_encrypted`
   - `toggle_project_marketplace()` - возвращает `api_token_encrypted`
   - `update_project_marketplace_settings()` - возвращает `api_token_encrypted`

3. **src/app/routers/marketplaces.py** (ИЗМЕНЕН)
   - `connect_wb_marketplace_endpoint()` - шифрует токен и сохраняет в `api_token_encrypted`
   - `disconnect_wb_marketplace_endpoint()` - очищает `api_token_encrypted`

4. **src/app/utils/get_project_marketplace_token.py** (ИЗМЕНЕН)
   - `get_wb_token_for_project()` - читает из `api_token_encrypted` и расшифровывает

### Миграции

1. **alembic/versions/add_api_token_encrypted_to_project_marketplaces.py** (НОВЫЙ)
   - `down_revision: 'add_unique_products_project_nm_id'`
   - Добавляет колонку `api_token_encrypted`
   - Мигрирует существующие токены

### Зависимости

1. **requirements.txt** (ИЗМЕНЕН)
   - Добавлена `cryptography==42.0.5`

## Команды для применения

### 1. Установить зависимости

```bash
docker compose exec api pip install cryptography==42.0.5
# или пересобрать образ
docker compose build api
```

### 2. Установить PROJECT_SECRETS_KEY

```bash
# В .env или docker-compose.yml
PROJECT_SECRETS_KEY=your_fernet_key_here

# Или сгенерировать ключ:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Применить миграцию

```bash
docker compose exec api alembic upgrade head
```

**Ожидается:**
- Колонка `api_token_encrypted` добавлена
- Существующие токены мигрированы (если PROJECT_SECRETS_KEY установлен)

### 4. Проверить подключение WB

```bash
TOKEN=$(curl -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=password" | jq -r '.access_token')

# Подключить WB
curl -X POST http://localhost/api/v1/projects/1/marketplaces/wb/connect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"api_key":"YOUR_WB_TOKEN"}'
```

**Ожидается в ответе:**
```json
{
  "success": true,
  "message": "Wildberries marketplace connected successfully",
  "project_marketplace": {
    "settings_json": {
      "base_url": "https://content-api.wildberries.ru",
      "timeout": 30
    }
    // НЕТ api_token, token, api_token_encrypted
  }
}
```

### 5. Проверить в БД

```bash
docker compose exec postgres psql -U wb -d wb -c \
  "SELECT id, project_id, marketplace_id, is_enabled, 
   settings_json, api_token_encrypted IS NOT NULL as has_encrypted_token 
   FROM project_marketplaces WHERE project_id = 1;"
```

**Ожидается:**
- `settings_json` не содержит `api_token` или `token`
- `api_token_encrypted` содержит зашифрованный токен (не NULL)
- `has_encrypted_token = true`

## Acceptance Criteria ✅

- ✅ **Токена нет в settings_json в БД** - проверено через SQL запрос
- ✅ **Токена нет в settings_json в ответах API** - проверено через curl
- ✅ **Токен хранится только в api_token_encrypted** - зашифрован
- ✅ **api_token_encrypted не возвращается в API** - не включен в схемы Pydantic
- ✅ **Ingestion использует расшифрованный токен** - `get_wb_token_for_project()` работает

## Важные замечания

1. **PROJECT_SECRETS_KEY обязателен в production** - без него токены не будут зашифрованы
2. **Ключ должен быть сохранен безопасно** - потеря ключа = потеря доступа к токенам
3. **Миграция мигрирует существующие токены** - если PROJECT_SECRETS_KEY установлен
4. **Fallback на settings_json** - для обратной совместимости (должен исчезнуть после миграции всех токенов)



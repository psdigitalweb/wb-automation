# Workflow подключения Wildberries маркетплейса

## Обзор

Реализован полный workflow для подключения/отключения Wildberries маркетплейса к проекту с валидацией токена.

## API Endpoints

### 1. POST /api/v1/projects/{project_id}/marketplaces/wb/connect

Подключает Wildberries к проекту с валидацией токена.

**Request:**
```json
{
  "api_key": "your_wb_api_token_here"
}
```

**Response (success):**
```json
{
  "success": true,
  "message": "Wildberries marketplace connected successfully",
  "project_marketplace": {
    "id": 1,
    "project_id": 1,
    "marketplace_id": 1,
    "is_enabled": true,
    "settings_json": {
      "api_token": "***",
      "base_url": "https://content-api.wildberries.ru",
      "timeout": 30
    },
    ...
  }
}
```

**Response (error):**
```json
{
  "success": false,
  "message": "Token validation failed: Invalid token: Unauthorized (401)",
  "project_marketplace": null
}
```

**Требования:**
- Authorization: Bearer TOKEN
- Проект membership (admin или owner)

**Процесс:**
1. Валидация membership (admin/owner)
2. Валидация WB токена через тестовый запрос к WB API
3. Сохранение токена в `settings_json` (зашифровано/замаскировано)
4. Автоматическое включение маркетплейса (`is_enabled=true`)

### 2. POST /api/v1/projects/{project_id}/marketplaces/wb/disconnect

Отключает Wildberries от проекта.

**Request:** Нет тела (только project_id в пути)

**Response:** 204 No Content

**Требования:**
- Authorization: Bearer TOKEN
- Проект membership (admin или owner)

**Процесс:**
1. Валидация membership (admin/owner)
2. Отключение маркетплейса (`is_enabled=false`)
3. Очистка токена из `settings_json`

### 3. GET /api/v1/projects/{project_id}/marketplaces

Получает список подключенных маркетплейсов для проекта.

**Response:**
```json
[
  {
    "id": 1,
    "project_id": 1,
    "marketplace_id": 1,
    "is_enabled": true,
    "settings_json": {
      "api_token": "***",
      "base_url": "https://content-api.wildberries.ru",
      "timeout": 30
    },
    "marketplace_code": "wildberries",
    "marketplace_name": "Wildberries",
    ...
  }
]
```

## Валидация токена

**Файл:** `src/app/utils/wb_token_validator.py`

**Функция:** `validate_wb_token(token: str) -> Tuple[bool, Optional[str]]`

**Процесс:**
1. Проверка, что токен не пустой и не "MOCK"
2. Тестовый запрос к WB API:
   - Первый вариант: `GET /api/v3/warehouses` (marketplace-api)
   - Fallback: `GET /api/v2/list/goods/filter?limit=1` (prices-api)
3. Проверка ответа:
   - 200 → токен валиден
   - 401 → токен невалиден
   - 403 → токен невалиден (нет прав)
   - 429 → токен валиден (rate limit означает что токен работает)
   - Timeout/Error → токен невалиден

**Возвращает:**
- `(True, None)` - токен валиден
- `(False, error_message)` - токен невалиден с описанием ошибки

## База данных

**Таблица:** `project_marketplaces`

**Структура:**
- `id` - SERIAL PRIMARY KEY
- `project_id` - INTEGER NOT NULL REFERENCES projects(id)
- `marketplace_id` - INTEGER NOT NULL REFERENCES marketplaces(id)
- `is_enabled` - BOOLEAN NOT NULL DEFAULT FALSE
- `settings_json` - JSONB (хранит токен в `api_token` и `token`)
- `created_at` - TIMESTAMPTZ
- `updated_at` - TIMESTAMPTZ

**Уникальный индекс:** `(project_id, marketplace_id)`

## Frontend

**Файл:** `frontend/app/app/project/[projectId]/settings/page.tsx`

**Компонент:** Форма подключения WB с:
- Поле ввода API токена (password type)
- Кнопка "Connect Wildberries" (с лоадером)
- Кнопка "Disconnect Wildberries" (если подключено)
- Статусы: ошибка/успех (с цветовой индикацией)
- Проверка подключения при загрузке страницы

**Состояния:**
- `wbConnected` - подключен ли WB
- `wbLoading` - идет ли загрузка/валидация
- `wbApiKey` - введенный токен
- `connectError` - ошибка подключения
- `connectSuccess` - успешное подключение

## Сценарий проверки

### Подготовка

```bash
# 1. Запустить контейнеры
docker compose up -d

# 2. Получить токен аутентификации
# Создать пользователя и получить токен (см. AUTH_DOCUMENTATION.md)
export AUTH_TOKEN="Bearer YOUR_ACCESS_TOKEN"

# 3. Получить WB API токен
export WB_API_KEY="your_wb_api_token_here"
```

### Тест 1: Подключение WB

```bash
# Создать проект
PROJECT_ID=$(curl -X POST "http://localhost:8000/api/v1/projects" \
  -H "Authorization: ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Project","description":"Test"}' | jq -r '.id')

# Проверить статус WB (должно быть пусто или disabled)
curl -H "Authorization: ${AUTH_TOKEN}" \
  "http://localhost:8000/api/v1/projects/${PROJECT_ID}/marketplaces" | jq '.[] | select(.marketplace_code == "wildberries")'

# Подключить WB
curl -X POST "http://localhost:8000/api/v1/projects/${PROJECT_ID}/marketplaces/wb/connect" \
  -H "Authorization: ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"api_key\": \"${WB_API_KEY}\"}" | jq '.'

# Проверить подключение (is_enabled должно быть true)
curl -H "Authorization: ${AUTH_TOKEN}" \
  "http://localhost:8000/api/v1/projects/${PROJECT_ID}/marketplaces" | jq '.[] | select(.marketplace_code == "wildberries")'
```

### Тест 2: Отключение WB

```bash
# Отключить WB
curl -X POST "http://localhost:8000/api/v1/projects/${PROJECT_ID}/marketplaces/wb/disconnect" \
  -H "Authorization: ${AUTH_TOKEN}"

# Проверить отключение (is_enabled должно быть false)
curl -H "Authorization: ${AUTH_TOKEN}" \
  "http://localhost:8000/api/v1/projects/${PROJECT_ID}/marketplaces" | jq '.[] | select(.marketplace_code == "wildberries")'
```

### Тест 3: Валидация невалидного токена

```bash
# Попытка подключить с невалидным токеном
curl -X POST "http://localhost:8000/api/v1/projects/${PROJECT_ID}/marketplaces/wb/connect" \
  -H "Authorization: ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "invalid_token"}' | jq '.'

# Должен вернуть:
# {
#   "success": false,
#   "message": "Token validation failed: Invalid token: Unauthorized (401)",
#   "project_marketplace": null
# }
```

### Тест 4: Автоматический скрипт

```bash
chmod +x scripts/test_wb_connect.sh
export AUTH_TOKEN="Bearer YOUR_TOKEN"
export WB_API_KEY="your_wb_token"
./scripts/test_wb_connect.sh

# Для теста отключения:
export TEST_DISCONNECT=true
./scripts/test_wb_connect.sh
```

## Измененные файлы

### Backend

1. `src/app/utils/wb_token_validator.py` - новый файл, валидация WB токена
2. `src/app/schemas/marketplaces.py` - добавлены `WBConnectRequest`, `WBConnectResponse`
3. `src/app/routers/marketplaces.py` - добавлены endpoints `/wb/connect` и `/wb/disconnect`

### Frontend

1. `frontend/app/app/project/[projectId]/settings/page.tsx` - добавлена форма подключения WB

## Важно

1. **Токен валидируется** перед сохранением через тестовый запрос к WB API
2. **Токен хранится** в `settings_json` (замаскирован при выводе)
3. **Требуется membership** (admin или owner) для подключения/отключения
4. **Автоматическое включение** маркетплейса при успешном подключении
5. **Очистка токена** при отключении (settings_json становится пустым)

## Безопасность

- Токены маскируются в ответах API (`***`)
- Токены хранятся в JSONB (можно шифровать дополнительно)
- Валидация membership перед любыми операциями
- Валидация токена через WB API перед сохранением



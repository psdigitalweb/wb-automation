# Документация по системе маркетплейсов

## Обзор

Реализована система управления маркетплейсами для проектов с поддержкой:
- Справочника маркетплейсов (seed-данные)
- Подключения маркетплейсов к проектам (enable/disable)
- Хранения настроек в `settings_json` с автоматическим маскированием секретов

## Компоненты системы

### 1. Модели

#### Marketplace (`app/db_marketplaces.py`)
- Таблица `marketplaces` (справочник) с полями:
  - `id` - уникальный идентификатор
  - `code` - код маркетплейса (уникальный, например: "wildberries", "ozon")
  - `name` - название маркетплейса
  - `description` - описание
  - `is_active` - активен ли маркетплейс
  - `created_at`, `updated_at` - временные метки

#### ProjectMarketplace (`app/db_marketplaces.py`)
- Таблица `project_marketplaces` (связь проекта с маркетплейсом) с полями:
  - `id` - уникальный идентификатор
  - `project_id` - ID проекта
  - `marketplace_id` - ID маркетплейса
  - `is_enabled` - включен ли маркетплейс для проекта
  - `settings_json` - JSONB с настройками (токены, API ключи и т.д.)
  - `created_at`, `updated_at` - временные метки
  - Уникальное ограничение на пару (project_id, marketplace_id)

### 2. Seed-данные

При создании таблиц автоматически заполняются следующие маркетплейсы:
- **Wildberries** (code: `wildberries`)
- **Ozon** (code: `ozon`)
- **Яндекс.Маркет** (code: `yandex_market`)
- **СберМегаМаркет** (code: `sbermegamarket`)

### 3. Маскирование секретов

Функция `mask_secrets()` автоматически маскирует следующие поля в `settings_json`:
- `token`, `api_key`, `api_secret`, `secret_key`, `password`
- `access_token`, `refresh_token`, `private_key`, `client_secret`

Любое поле, содержащее эти слова (регистронезависимо), будет заменено на `"***"` при выводе.

### 4. Эндпоинты (`app/routers/marketplaces.py`)

Все эндпоинты требуют аутентификации и проверяют membership проекта.

#### Справочник маркетплейсов

- `GET /api/v1/marketplaces` - список всех маркетплейсов
- `GET /api/v1/marketplaces/{marketplace_id}` - детали маркетплейса

#### Управление маркетплейсами в проекте

- `GET /api/v1/projects/{project_id}/marketplaces` - список маркетплейсов проекта (с маскированными секретами)
- `GET /api/v1/projects/{project_id}/marketplaces/{marketplace_id}` - детали подключения (с маскированными секретами)
- `POST /api/v1/projects/{project_id}/marketplaces` - подключить маркетплейс к проекту (требует admin/owner)
- `PUT /api/v1/projects/{project_id}/marketplaces/{marketplace_id}` - обновить настройки (merge с существующими, требует admin/owner)
- `PATCH /api/v1/projects/{project_id}/marketplaces/{marketplace_id}/toggle` - включить/выключить маркетплейс (требует admin/owner)
- `DELETE /api/v1/projects/{project_id}/marketplaces/{marketplace_id}` - отключить маркетплейс (требует admin/owner)

## Использование

### 1. Получение списка доступных маркетплейсов

```bash
curl -X GET "http://localhost:8000/api/v1/marketplaces" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Ответ:
```json
[
  {
    "id": 1,
    "code": "wildberries",
    "name": "Wildberries",
    "description": "Крупнейший маркетплейс в России",
    "is_active": true,
    "created_at": "2026-01-16T12:00:00Z",
    "updated_at": "2026-01-16T12:00:00Z"
  }
]
```

### 2. Подключение маркетплейса к проекту

```bash
curl -X POST "http://localhost:8000/api/v1/projects/1/marketplaces" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "marketplace_id": 1,
    "is_enabled": true,
    "settings_json": {
      "api_token": "secret_token_12345",
      "api_key": "key_abc123",
      "base_url": "https://api.wildberries.ru",
      "timeout": 30
    }
  }'
```

Ответ (секреты замаскированы):
```json
{
  "id": 1,
  "project_id": 1,
  "marketplace_id": 1,
  "is_enabled": true,
  "settings_json": {
    "api_token": "***",
    "api_key": "***",
    "base_url": "https://api.wildberries.ru",
    "timeout": 30
  },
  "created_at": "2026-01-16T12:00:00Z",
  "updated_at": "2026-01-16T12:00:00Z",
  "marketplace_code": "wildberries",
  "marketplace_name": "Wildberries"
}
```

### 3. Получение маркетплейсов проекта

```bash
curl -X GET "http://localhost:8000/api/v1/projects/1/marketplaces" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 4. Обновление настроек (merge с существующими)

```bash
curl -X PUT "http://localhost:8000/api/v1/projects/1/marketplaces/1" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "settings_json": {
      "timeout": 60,
      "new_setting": "value"
    }
  }'
```

Существующие настройки будут объединены с новыми (merge).

### 5. Включение/выключение маркетплейса

```bash
curl -X PATCH "http://localhost:8000/api/v1/projects/1/marketplaces/1/toggle" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "is_enabled": true
  }'
```

### 6. Отключение маркетплейса от проекта

```bash
curl -X DELETE "http://localhost:8000/api/v1/projects/1/marketplaces/1" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Маскирование секретов

### Автоматическое маскирование

При выводе `settings_json` все поля, содержащие следующие слова, автоматически маскируются:
- `token`, `api_key`, `api_secret`, `secret_key`, `password`
- `access_token`, `refresh_token`, `private_key`, `client_secret`

### Пример

**Входные данные:**
```json
{
  "api_token": "secret123",
  "api_key": "key456",
  "base_url": "https://api.example.com",
  "timeout": 30
}
```

**Выходные данные (маскированные):**
```json
{
  "api_token": "***",
  "api_key": "***",
  "base_url": "https://api.example.com",
  "timeout": 30
}
```

### Вложенные объекты

Маскирование работает рекурсивно для вложенных объектов:

**Входные данные:**
```json
{
  "auth": {
    "access_token": "token123",
    "refresh_token": "refresh456"
  },
  "api_key": "key789"
}
```

**Выходные данные:**
```json
{
  "auth": {
    "access_token": "***",
    "refresh_token": "***"
  },
  "api_key": "***"
}
```

## Правила доступа

1. **Просмотр справочника маркетплейсов**: любой аутентифицированный пользователь
2. **Просмотр маркетплейсов проекта**: только участники проекта (любая роль)
3. **Подключение/обновление/отключение маркетплейса**: только admin или owner проекта

## Миграции

Таблицы создаются через Alembic миграцию:
- `alembic/versions/add_marketplaces_tables.py`

Применить миграции:
```bash
docker compose exec api alembic upgrade head
```

Seed-данные заполняются автоматически при применении миграции.

## Схемы Pydantic

Схемы определены в `app/schemas/marketplaces.py`:
- `MarketplaceResponse` - информация о маркетплейсе
- `ProjectMarketplaceCreate` - для подключения маркетплейса
- `ProjectMarketplaceUpdate` - для обновления настроек
- `ProjectMarketplaceWithMaskedSecrets` - ответ с замаскированными секретами
- `ToggleRequest` - для включения/выключения

## Примеры использования

### Подключение Wildberries к проекту

```python
# 1. Получить ID маркетплейса Wildberries
marketplaces = get_all_marketplaces()
wb = next(m for m in marketplaces if m["code"] == "wildberries")

# 2. Подключить к проекту
create_or_update_project_marketplace(
    project_id=1,
    marketplace_id=wb["id"],
    is_enabled=True,
    settings_json={
        "api_token": "your_wb_token_here",
        "base_url": "https://content-api.wildberries.ru",
        "timeout": 30
    }
)
```

### Получение настроек с маскированием

```python
pm = get_project_marketplace(project_id=1, marketplace_id=1)
settings = pm["settings_json"]
masked_settings = mask_secrets(settings)
# masked_settings содержит замаскированные секреты
```





# Системные настройки маркетплейсов (System Marketplace Settings)

## Обзор

Добавлен системный слой управления маркетплейсами на уровне superadmin. Позволяет глобально отключать маркетплейсы, скрывать их из UI, задавать дефолтные настройки и порядок сортировки.

## Компоненты

### 1. База данных

**Таблица:** `system_marketplace_settings`
- `marketplace_code` (TEXT PRIMARY KEY) - код маркетплейса
- `is_globally_enabled` (BOOLEAN, default TRUE) - глобально включен
- `is_visible` (BOOLEAN, default TRUE) - видим в UI
- `sort_order` (INTEGER, default 100) - порядок сортировки
- `settings_json` (JSONB, default '{}') - системные настройки
- `created_at`, `updated_at` (TIMESTAMPTZ)

**Миграция:** `alembic/versions/add_system_marketplace_settings_table.py`

### 2. Backend API

#### Admin Endpoints (требуют superadmin)

**GET /api/v1/admin/system-marketplaces**
- Возвращает список всех маркетплейсов с системными настройками
- Если записи нет - возвращает дефолты (enabled=true, visible=true, sort_order=100)
- Response: `List[SystemMarketplaceSettingsResponse]`

**PUT /api/v1/admin/system-marketplaces/{marketplace_code}**
- UPSERT системных настроек для маркетплейса
- Валидирует, что marketplace_code существует в таблице marketplaces
- Body: `SystemMarketplaceSettingsUpdate` (partial update)

#### Public Endpoint (read-only, без auth)

**GET /api/v1/system/marketplaces**
- Возвращает только минимальные поля: `code`, `is_globally_enabled`, `is_visible`, `sort_order`
- Без `settings_json` (безопасно)
- Fail-safe: при ошибке возвращает дефолты
- Response: `List[SystemMarketplacePublicStatus]`

### 3. Frontend

#### Admin UI

**Route:** `/admin/system-marketplaces`
- Таблица всех маркетплейсов
- Toggle "Globally enabled"
- Toggle "Visible"
- Input "Sort order"
- Кнопка "Edit JSON" (modal с textarea)
- Автосохранение при изменении
- Показывается только для superadmin

#### Project UI Integration

**Route:** `/project/{projectId}/marketplaces`
- Загружает глобальные статусы через GET /system/marketplaces
- Если marketplace globally disabled → toggle disabled + подсказка "Отключено администратором системы"
- Если globally hidden → скрывается из списка (если не подключен в проекте)
- Если globally hidden но уже подключен → показывается с пометкой "Скрыт администратором системы (но подключен в проекте)"
- Fail-safe: при ошибке загрузки глобальных статусов - работает как раньше (backward compatible)

## Backward Compatibility

- Если таблица `system_marketplace_settings` пустая → всё работает как раньше (дефолты: enabled=true, visible=true)
- Если endpoint `/system/marketplaces` недоступен → фронтенд игнорирует ошибку и показывает маркетплейсы как раньше
- Существующие endpoints `/projects/{project_id}/marketplaces/*` не изменены
- Существующие WB endpoints не изменены

## Использование

### Пример: Отключить маркетплейс глобально

```bash
curl -X PUT "http://localhost:8000/api/v1/admin/system-marketplaces/wildberries" \
  -H "Authorization: Bearer SUPERADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "is_globally_enabled": false,
    "is_visible": false
  }'
```

### Пример: Получить глобальные статусы (public)

```bash
curl "http://localhost:8000/api/v1/system/marketplaces"
```

## Файлы

### Backend
- `alembic/versions/add_system_marketplace_settings_table.py` - миграция
- `src/app/db_marketplaces.py` - функции для работы с системными настройками
- `src/app/schemas/marketplaces.py` - Pydantic схемы
- `src/app/routers/admin_marketplaces.py` - admin endpoints
- `src/app/routers/marketplaces.py` - public endpoint

### Frontend
- `frontend/app/app/admin/system-marketplaces/page.tsx` - админ UI
- `frontend/app/app/project/[projectId]/marketplaces/page.tsx` - интеграция в проектный UI

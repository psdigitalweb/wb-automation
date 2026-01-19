# Инструкция по запуску проекта с нуля

## Предварительные требования

1. **Docker** и **Docker Compose** установлены и запущены
2. **Git** (опционально, для клонирования репозитория)

## Шаг 1: Подготовка окружения

### 1.1. Клонирование репозитория (если нужно)

```bash
git clone <repository-url>
cd wb-automation
```

### 1.2. Создание файла `.env`

Создайте файл `.env` в корне проекта:

```bash
# PostgreSQL
POSTGRES_DB=wb
POSTGRES_USER=wb
POSTGRES_PASSWORD=wbpass
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Wildberries API (укажите реальный токен или оставьте MOCK для тестирования)
WB_TOKEN=MOCK

# JWT Secret (ОБЯЗАТЕЛЬНО измените в продакшене!)
JWT_SECRET=your-secret-key-change-in-production

# Timezone
TZ=Europe/Moscow

# Access Token Expire (опционально)
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Refresh Token Expire (опционально)
REFRESH_TOKEN_EXPIRE_DAYS=7
```

**Важно:**
- Измените `JWT_SECRET` на случайную строку в продакшене
- Укажите реальный `WB_TOKEN` для работы с API Wildberries
- Пароль PostgreSQL должен быть достаточно сложным в продакшене

### 1.3. Создание `.htpasswd` для Adminer (опционально)

Для защиты Adminer паролем:

```bash
# Linux/Mac
htpasswd -c nginx/.htpasswd admin

# Windows (используйте WSL или Git Bash)
# Или создайте файл вручную с содержимым:
# admin:$apr1$...
```

Если файл не создан, Adminer будет доступен без пароля.

## Шаг 2: Запуск Docker контейнеров

### 2.1. Сборка и запуск

```bash
# Сборка образов и запуск контейнеров
docker compose up -d --build
```

Эта команда:
- Соберет Docker образы для всех сервисов
- Создаст и запустит контейнеры в фоновом режиме
- Подождет готовности зависимостей (PostgreSQL, Redis)

### 2.2. Проверка статуса

```bash
# Проверка статуса всех контейнеров
docker compose ps

# Просмотр логов
docker compose logs -f
```

Все контейнеры должны быть в статусе `Up`:
- `postgres` - база данных
- `redis` - кэш и очереди
- `api` - FastAPI приложение
- `frontend` - Next.js приложение
- `nginx` - reverse proxy
- `adminer` - веб-интерфейс для БД (опционально)
- `worker` - Celery worker (опционально)
- `beat` - Celery beat (опционально)

## Шаг 3: Применение миграций базы данных

### 3.1. Проверка текущего состояния

```bash
# Проверка текущей ревизии
docker compose exec api alembic current

# Просмотр истории миграций
docker compose exec api alembic history
```

### 3.2. Применение всех миграций

```bash
# Применить все миграции до последней версии
docker compose exec api alembic upgrade head
```

**Что происходит:**
1. Создаются все таблицы базы данных
2. Создаются индексы и ограничения
3. Создаются SQL VIEWs
4. Заполняются seed-данные (маркетплейсы)

### 3.3. Проверка результата

```bash
# Подключение к PostgreSQL
docker compose exec postgres psql -U wb -d wb

# В psql выполните:
\dt  # Список таблиц
\d users  # Структура таблицы users
\d projects  # Структура таблицы projects
\d marketplaces  # Структура таблицы marketplaces
SELECT * FROM marketplaces;  # Проверка seed-данных
\q  # Выход
```

**Ожидаемые таблицы:**
- `users` - пользователи
- `projects` - проекты
- `project_members` - участники проектов
- `marketplaces` - справочник маркетплейсов
- `project_marketplaces` - подключения маркетплейсов к проектам
- `products` - товары
- `price_snapshots` - снимки цен
- `stock_snapshots` - снимки остатков
- `supplier_stock_snapshots` - остатки поставщика
- `frontend_catalog_price_snapshots` - цены с фронта WB
- `rrp_snapshots` - данные из 1С XML
- `wb_warehouses` - склады WB
- `app_settings` - настройки приложения
- `refresh_tokens` - refresh токены для JWT

**Ожидаемые VIEWs:**
- `v_products_latest_price` - последние цены
- `v_products_latest_stock` - последние остатки
- `v_article_base` - единая витрина артикулов

**Seed-данные:**
- 4 маркетплейса: Wildberries, Ozon, Яндекс.Маркет, СберМегаМаркет

## Шаг 4: Создание первого пользователя

### 4.1. Регистрация через API

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "secure_password_123"
  }'
```

### 4.2. Вход и получение токенов

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "secure_password_123"
  }'
```

Ответ:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Сохраните `access_token` для дальнейших запросов.

## Шаг 5: Создание первого проекта

```bash
# Замените YOUR_ACCESS_TOKEN на токен из шага 4.2
curl -X POST "http://localhost:8000/api/v1/projects" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Мой первый проект",
    "description": "Описание проекта"
  }'
```

Ответ:
```json
{
  "id": 1,
  "name": "Мой первый проект",
  "description": "Описание проекта",
  "created_by": 1,
  "created_at": "2026-01-16T12:00:00Z",
  "updated_at": "2026-01-16T12:00:00Z"
}
```

## Шаг 6: Подключение маркетплейса к проекту

```bash
# Подключить Wildberries к проекту
curl -X POST "http://localhost:8000/api/v1/projects/1/marketplaces" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "marketplace_id": 1,
    "is_enabled": true,
    "settings_json": {
      "api_token": "your_wb_token_here",
      "base_url": "https://content-api.wildberries.ru",
      "timeout": 30
    }
  }'
```

**Примечание:** Секреты в `settings_json` автоматически маскируются при выводе (заменяются на `"***"`).

## Шаг 7: Проверка работы

### 7.1. Проверка API

```bash
# Health check
curl "http://localhost:8000/api/v1/health"

# Список маркетплейсов
curl -X GET "http://localhost:8000/api/v1/marketplaces" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# Список проектов
curl -X GET "http://localhost:8000/api/v1/projects" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 7.2. Проверка Frontend

Откройте в браузере:
- **Dashboard**: http://localhost:3000
- **Через Nginx**: http://localhost

### 7.3. Проверка базы данных

Откройте Adminer:
- **URL**: http://localhost/adminer
- **Система**: PostgreSQL
- **Сервер**: postgres
- **Пользователь**: wb
- **Пароль**: wbpass (или из `.env`)
- **База данных**: wb

## Шаг 8: Первоначальная загрузка данных (опционально)

Если у вас есть реальный `WB_TOKEN`, можно запустить ingestion:

```bash
# Загрузка продуктов
curl -X POST "http://localhost:8000/api/v1/ingest/products" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# Загрузка складов
curl -X POST "http://localhost:8000/api/v1/ingest/warehouses" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# Загрузка остатков
curl -X POST "http://localhost:8000/api/v1/ingest/supplier-stocks" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# Загрузка цен
curl -X POST "http://localhost:8000/api/v1/ingest/prices" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Порядок миграций Alembic

Миграции применяются в следующем порядке:

1. `a77217f699d1` - Initial migration (products, price_snapshots)
2. `e1dcde5e611e` - Add brand to products
3. `0f69aa9a434f` - Add v_products_latest_price view
4. `a0afa471d2a0` - Add v_products_latest_stock view
5. `2a8757976d5a` - Add frontend_catalog_price_snapshots table
6. `213c70612608` - Add raw jsonb column to price_snapshots
7. `ea2d9ac02904` - Add app_settings table
8. `a2b730f4e786` - Add app_settings table (fix)
9. `b1c2d3e4f5a6` - Add rrp_snapshots table
10. `c2d3e4f5a6b7` - Add v_article_base view
11. `0fd96b01e954` - Fix v_article_base full outer join
12. `optimize_v_article_base` - Optimize v_article_base performance
13. `add_product_details` - Add product details fields
14. `add_users_table` - Add users table for authentication
15. `add_refresh_tokens` - Add refresh_tokens table
16. `add_projects_tables` - Add projects and project_members tables
17. `add_marketplaces_tables` - Add marketplaces and project_marketplaces tables (HEAD)

## Полезные команды

### Управление контейнерами

```bash
# Остановить все контейнеры
docker compose down

# Остановить и удалить volumes (ОСТОРОЖНО: удалит данные!)
docker compose down -v

# Перезапустить контейнер
docker compose restart api

# Просмотр логов
docker compose logs -f api
docker compose logs -f frontend
```

### Работа с миграциями

```bash
# Текущая версия
docker compose exec api alembic current

# История миграций
docker compose exec api alembic history

# Применить все миграции
docker compose exec api alembic upgrade head

# Откатить последнюю миграцию
docker compose exec api alembic downgrade -1

# Создать новую миграцию
docker compose exec api alembic revision -m "description"
```

### Работа с базой данных

```bash
# Подключение к PostgreSQL
docker compose exec postgres psql -U wb -d wb

# Резервное копирование
docker compose exec postgres pg_dump -U wb wb > backup.sql

# Восстановление из backup
docker compose exec -T postgres psql -U wb -d wb < backup.sql
```

## Устранение проблем

### Проблема: Миграции не применяются

```bash
# Проверьте логи
docker compose logs api | grep -i migration

# Проверьте подключение к БД
docker compose exec api python -c "from app.db import engine; engine.connect()"

# Принудительно установите версию (ОСТОРОЖНО!)
docker compose exec api alembic stamp head
```

### Проблема: Контейнеры не запускаются

```bash
# Проверьте логи
docker compose logs

# Проверьте порты
netstat -an | grep -E "3000|8000|5432"

# Пересоберите образы
docker compose build --no-cache
```

### Проблема: Frontend не подключается к API

```bash
# Проверьте переменные окружения
docker compose exec frontend env | grep API

# Проверьте сеть Docker
docker network ls
docker network inspect wb-automation_default
```

## Следующие шаги

После успешного запуска:

1. **Настройте маркетплейсы** для ваших проектов
2. **Создайте пользователей** и назначьте их в проекты
3. **Настройте ingestion** для автоматической загрузки данных
4. **Изучите API документацию**: http://localhost:8000/docs
5. **Настройте мониторинг** и логирование

## Дополнительная документация

- `AUTH_DOCUMENTATION.md` - Система авторизации JWT
- `PROJECTS_DOCUMENTATION.md` - Мультипроектная модель
- `MARKETPLACES_DOCUMENTATION.md` - Управление маркетплейсами
- `SETUP_LOCAL.md` - Детальная инструкция по настройке





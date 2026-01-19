# Инструкция по запуску проекта в локальном Docker

## Предварительные требования

1. **Docker** и **Docker Compose** установлены
2. **Git** для клонирования репозитория (если нужно)

## Шаг 1: Подготовка файлов

### 1.1. Создайте файл `.env`

Скопируйте пример и настройте под себя:

```bash
cp .env.example .env
```

Отредактируйте `.env` и укажите:
- `POSTGRES_PASSWORD` - пароль для PostgreSQL (по умолчанию: `wbpass`)
- `WB_TOKEN` - токен Wildberries API (если есть, иначе оставьте `MOCK`)

**Важно:** Если `WB_TOKEN=MOCK` или не указан, ingestion будет пропущен с соответствующим сообщением.

### 1.2. Создайте файл `.htpasswd` для Adminer (рекомендуется)

Для защиты Adminer паролем создайте файл `.htpasswd`:

**Вариант 1: Использовать скрипт (рекомендуется)**

```bash
# Сделайте скрипт исполняемым (Linux/Mac)
chmod +x scripts/create_htpasswd.sh

# Запустите скрипт
./scripts/create_htpasswd.sh
```

**Вариант 2: Создать вручную**

```bash
# Установите apache2-utils (если не установлен)
# Linux/Debian:
sudo apt-get install apache2-utils

# Mac:
brew install httpd

# Windows: используйте WSL или Git Bash

# Создайте файл с паролем
htpasswd -c nginx/.htpasswd admin
```

**Важно:** Файл `.htpasswd` должен быть создан с валидным форматом (не пустой). Если файл не создан или пустой, nginx не запустится. Используйте скрипт или команду `htpasswd` для создания файла.

### 1.3. Убедитесь, что `test.xml` находится в корне проекта

Файл `test.xml` должен быть в корне проекта (`wb-automation/test.xml`). Он будет автоматически смонтирован в контейнер по пути `/app/test.xml`.

## Шаг 2: Запуск проекта

### 2.1. Соберите и запустите контейнеры

```bash
# Перейдите в директорию проекта
cd wb-automation

# Соберите и запустите все сервисы
docker compose up -d --build
```

Это запустит:
- **PostgreSQL** (БД)
- **Redis** (для Celery)
- **API** (FastAPI backend)
- **Worker** (Celery worker)
- **Beat** (Celery beat scheduler)
- **Frontend** (Next.js)
- **Nginx** (reverse proxy)
- **Adminer** (веб-интерфейс для БД)

### 2.2. Примените миграции базы данных

```bash
# Применить все миграции
docker compose exec api alembic upgrade head
```

### 2.3. Проверьте статус сервисов

```bash
# Посмотреть статус всех контейнеров
docker compose ps

# Посмотреть логи API
docker compose logs api

# Посмотреть логи frontend
docker compose logs frontend
```

## Шаг 3: Доступ к приложению

После запуска приложение будет доступно по адресам:

- **Frontend (Dashboard)**: http://localhost
- **API документация**: http://localhost/api/docs (Swagger UI)
- **Adminer (БД)**: http://localhost/adminer/ (требует пароль, если настроен)

## Шаг 4: Первоначальная загрузка данных

После запуска рекомендуется выполнить ingestion'ы для загрузки данных:

```bash
# 1. Загрузка остатков на складах WB (Statistics API)
curl -X POST "http://localhost/api/v1/ingest/supplier-stocks"

# 2. Загрузка наших цен и скидок (WB Marketplace API)
curl -X POST "http://localhost/api/v1/ingest/prices"

# 3. Загрузка цен с фронта WB (парсер catalog.wb.ru)
curl -X POST "http://localhost/api/v1/ingest/frontend-prices/brand" \
  -H "Content-Type: application/json" \
  -d '{"brand_id": 41189, "max_pages": 0, "sleep_ms": 800}'

# 4. Загрузка RRP из 1С XML
curl -X POST "http://localhost/api/v1/ingest/rrp-xml"
```

**Примечание:** Если `WB_TOKEN=MOCK`, ingestion'ы будут пропущены. Укажите реальный токен в `.env` для работы с WB API.

## Шаг 5: Проверка работы

### 5.1. Проверка API

```bash
# Health check
curl "http://localhost/api/v1/health"

# Проверка витрины артикулов
curl "http://localhost/api/v1/articles/base?limit=10&offset=0"
```

### 5.2. Проверка базы данных

```bash
# Подключиться к PostgreSQL
docker compose exec postgres psql -U wb -d wb

# В psql выполнить:
SELECT COUNT(*) FROM v_article_base;
SELECT COUNT(*) FROM rrp_snapshots;
SELECT COUNT(*) FROM supplier_stock_snapshots;
```

### 5.3. Проверка Frontend

Откройте в браузере: http://localhost

Должна открыться главная страница Dashboard с метриками и навигацией.

## Полезные команды

### Остановка сервисов

```bash
# Остановить все сервисы
docker compose down

# Остановить и удалить volumes (БД будет очищена!)
docker compose down -v
```

### Перезапуск сервисов

```bash
# Перезапустить конкретный сервис
docker compose restart api

# Перезапустить все сервисы
docker compose restart
```

### Просмотр логов

```bash
# Логи всех сервисов
docker compose logs

# Логи конкретного сервиса
docker compose logs api
docker compose logs frontend

# Логи в реальном времени
docker compose logs -f api
```

### Выполнение команд в контейнере

```bash
# Выполнить команду в контейнере API
docker compose exec api bash

# Выполнить Python команду
docker compose exec api python -c "from app.utils.vendor_code import normalize_vendor_code; print(normalize_vendor_code('560/ZKPY-1138'))"

# Выполнить миграцию
docker compose exec api alembic upgrade head
```

### Обновление кода

При изменении кода:
- **Backend (Python)**: автоматически перезагружается благодаря `--reload` в uvicorn
- **Frontend (Next.js)**: нужно пересобрать контейнер

```bash
# Пересобрать frontend
docker compose up -d --build frontend
```

## Решение проблем

### Проблема: Контейнеры не запускаются

```bash
# Проверьте логи
docker compose logs

# Проверьте, не заняты ли порты
# Windows: netstat -ano | findstr :80
# Linux/Mac: lsof -i :80
```

### Проблема: База данных не подключается

```bash
# Проверьте, что PostgreSQL запущен
docker compose ps postgres

# Проверьте логи PostgreSQL
docker compose logs postgres

# Проверьте переменные окружения
docker compose exec api env | grep POSTGRES
```

### Проблема: Миграции не применяются

```bash
# Проверьте текущую версию миграций
docker compose exec api alembic current

# Примените миграции вручную
docker compose exec api alembic upgrade head

# Если нужно откатить
docker compose exec api alembic downgrade -1
```

### Проблема: Frontend не открывается

```bash
# Проверьте логи frontend
docker compose logs frontend

# Пересоберите frontend
docker compose up -d --build frontend

# Проверьте nginx
docker compose logs nginx
```

### Проблема: test.xml не найден

Убедитесь, что файл `test.xml` находится в корне проекта:

```bash
# Проверьте наличие файла
ls -la test.xml

# Проверьте, что файл смонтирован в контейнер
docker compose exec api ls -la /app/test.xml
```

## Структура проекта

```
wb-automation/
├── .env                    # Переменные окружения (создайте из .env.example)
├── docker-compose.yml      # Конфигурация Docker Compose
├── Dockerfile              # Dockerfile для API
├── requirements.txt        # Python зависимости
├── test.xml               # XML файл для RRP ingestion
├── alembic.ini            # Конфигурация Alembic
├── nginx/
│   ├── nginx.conf         # Конфигурация Nginx
│   └── .htpasswd          # Пароли для Adminer (создайте)
├── src/
│   └── app/               # Python код приложения
├── frontend/               # Next.js frontend
└── alembic/                # Миграции базы данных
```

## Дополнительная информация

- **Документация API**: http://localhost/api/docs
- **README**: см. `README.md` для подробной документации
- **Миграции**: все изменения БД через Alembic (см. `alembic/versions/`)


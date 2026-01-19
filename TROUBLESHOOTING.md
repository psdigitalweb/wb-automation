# Решение проблем со сборкой Docker

## Проблема: pip install падает с ошибкой

### Причины

1. **Проблемы с сетью/DNS в Docker Desktop на Windows**
2. **Таймауты при загрузке пакетов с PyPI**
3. **Проблемы с конкретными версиями пакетов**

### Решения

#### Решение 1: Проверьте DNS в Docker Desktop

1. Откройте Docker Desktop
2. Settings → Docker Engine
3. Убедитесь, что есть:
```json
{
  "dns": ["1.1.1.1", "8.8.8.8", "8.8.4.4"]
}
```
4. Apply & Restart

#### Решение 2: Используйте альтернативный источник PyPI

Создайте `Dockerfile.alternative`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .

# Используем альтернативный индекс PyPI (если основной недоступен)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
    --index-url https://pypi.org/simple \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -r requirements.txt

COPY . .
EXPOSE 8000
```

#### Решение 3: Установка пакетов по одному

Если проблема с конкретным пакетом, установите по одному:

```dockerfile
RUN pip install fastapi==0.115.0 && \
    pip install "uvicorn[standard]==0.30.6" && \
    pip install pydantic==2.9.2 && \
    pip install SQLAlchemy==2.0.36 && \
    pip install psycopg2-binary==2.9.9 && \
    pip install httpx==0.27.2 && \
    pip install alembic==1.13.2 && \
    pip install celery==5.4.0 && \
    pip install redis==5.0.8 && \
    pip install python-dotenv==1.0.1
```

#### Решение 4: Используйте готовый образ с зависимостями

Создайте базовый образ с зависимостями отдельно:

```dockerfile
# Dockerfile.base
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

Затем используйте его:
```dockerfile
FROM your-registry/wb-automation-base:latest
COPY . .
```

#### Решение 5: Проверьте конкретную ошибку

```powershell
# Соберите с подробным выводом
docker compose build api --progress=plain 2>&1 | Tee-Object -FilePath build.log

# Найдите конкретную ошибку
Select-String -Path build.log -Pattern "ERROR|error|failed" | Select-Object -Last 20
```

#### Решение 6: Используйте локальный кеш pip

Если у вас есть локальный кеш pip:

```dockerfile
# Копируем локальный кеш pip (если есть)
COPY pip-cache /root/.cache/pip

RUN pip install --no-cache-dir -r requirements.txt
```

#### Решение 7: Временное решение - без worker/beat

Если нужно срочно запустить проект:

```powershell
# Соберите только API (без worker/beat)
docker compose build api --no-cache

# Запустите только необходимые сервисы
docker compose up -d postgres redis api frontend adminer nginx
```

Worker и beat можно добавить позже, когда решите проблему с pip.

## Проверка работы pip в контейнере

```powershell
# Запустите контейнер интерактивно
docker run -it --rm python:3.12-slim bash

# Внутри контейнера:
pip install --upgrade pip
pip install fastapi
# Если работает - проблема в requirements.txt или версиях
```

## Альтернатива: Используйте готовые образы

Если сборка постоянно падает, можно использовать готовые образы из Docker Hub или собрать на другой машине и загрузить образ.







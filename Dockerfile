FROM python:3.12-slim

WORKDIR /app
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Tools for debugging/health checks (curl requested for in-container smoke tests)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
  && rm -rf /var/lib/apt/lists/*

# build-essential НЕ нужен! Все зависимости используют бинарные пакеты:
# - psycopg2-binary (бинарная версия, не требует компиляции)
# - остальные пакеты - чистый Python
# Это ускоряет сборку и устраняет проблемы с apt-get на Windows

COPY requirements.txt .

# Установка зависимостей с оптимизацией для Windows/Docker
# Обновляем pip сначала
RUN pip install --upgrade pip setuptools wheel

# Устанавливаем зависимости с таймаутами и подробным выводом
RUN pip install --no-cache-dir \
    --timeout=300 \
    --retries=3 \
    --default-timeout=300 \
    -r requirements.txt || \
    (echo "=== PIP INSTALL FAILED, trying with verbose output ===" && \
     pip install --no-cache-dir --verbose -r requirements.txt)

COPY . .

EXPOSE 8000

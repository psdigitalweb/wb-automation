FROM python:3.12-slim

ARG TORCH_VERSION=2.13.0

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

# Production runs semantic models on CPU. Installing torch from the CPU index
# first prevents sentence-transformers from pulling multi-gigabyte CUDA wheels.
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    "torch==${TORCH_VERSION}+cpu"

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

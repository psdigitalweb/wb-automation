# Советы по ускорению сборки Docker

## Первая сборка

Первая сборка может занять **10-15 минут**, так как нужно:
- Скачать базовые образы (node, python, postgres, redis)
- Установить все зависимости (npm packages, Python packages)
- Собрать все сервисы

**Это нормально!** Последующие сборки будут намного быстрее благодаря кешу Docker.

## Ускорение сборки

### 1. Собирайте только нужные сервисы

Если нужно быстро запустить только API:

```powershell
# Соберите только backend сервисы
docker compose build postgres redis api

# Запустите их
docker compose up -d postgres redis api
```

### 2. Используйте BuildKit (уже включен в новых версиях Docker)

```powershell
$env:DOCKER_BUILDKIT=1
$env:COMPOSE_DOCKER_CLI_BUILD=1
docker compose build
```

### 3. Параллельная сборка

Docker Compose автоматически собирает сервисы параллельно, если они не зависят друг от друга.

### 4. Используйте кеш слоев

Docker автоматически кеширует слои. Если изменили только код (не зависимости), пересборка будет быстрой.

### 5. Оптимизация Dockerfile

- Копируйте `package.json` и `requirements.txt` ПЕРЕД копированием всего кода
- Это позволяет Docker кешировать установку зависимостей

## Мониторинг сборки

Смотрите прогресс в реальном времени:

```powershell
# В отдельном терминале
docker compose build --progress=plain 2>&1 | Tee-Object -FilePath build.log
```

## Если сборка зависает

### Frontend (npm install)

Если `npm install` зависает более 10 минут:

1. Отмените сборку (Ctrl+C)
2. Попробуйте собрать только frontend отдельно:
```powershell
docker compose build frontend --no-cache --progress=plain
```

3. Или используйте dev режим (уже настроен в Dockerfile.dev)

### Backend (apt-get)

Если `apt-get update` зависает:

1. Проверьте DNS в Docker Desktop (Settings → Docker Engine)
2. Убедитесь, что DNS серверы указаны: `["1.1.1.1", "8.8.8.8"]`
3. Перезапустите Docker Desktop

## Время сборки (примерное)

- **Первая сборка**: 10-15 минут
- **Пересборка после изменения кода**: 1-2 минуты
- **Пересборка после изменения зависимостей**: 5-10 минут

## Проверка прогресса

```powershell
# Смотрите логи сборки
docker compose build --progress=plain

# Или в отдельном окне смотрите использование ресурсов
docker stats
```

## Оптимизация для production

Для production используйте multi-stage builds и минимизируйте размер образов (уже настроено в Dockerfile).







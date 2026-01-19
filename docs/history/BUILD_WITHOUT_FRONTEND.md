# Сборка проекта БЕЗ frontend (временное решение)

Если frontend зависает при сборке, можно собрать и запустить проект без него.

## Быстрый старт без frontend

### 1. Создайте override файл

```powershell
cd wb-automation

# Создайте файл docker-compose.override.yml
@"
version: '3.8'
services:
  frontend:
    profiles: ['skip']
  nginx:
    depends_on:
      - api
      - adminer
"@ | Out-File -Encoding utf8 docker-compose.override.yml
```

### 2. Соберите и запустите

```powershell
# Соберите все кроме frontend
docker compose build postgres redis api worker beat adminer nginx

# Запустите
docker compose up -d
```

### 3. Примените миграции

```powershell
docker compose exec api alembic upgrade head
```

### 4. Проверьте работу

- **API**: http://localhost/api/docs
- **Adminer**: http://localhost/adminer/
- **API Health**: http://localhost/api/v1/health

## Добавление frontend позже

Когда будете готовы добавить frontend:

1. Удалите override файл:
```powershell
Remove-Item docker-compose.override.yml
```

2. Соберите frontend отдельно (можно попробовать в другой раз или на другой машине):
```powershell
docker compose build frontend
```

3. Или используйте готовый образ/соберите локально через Node.js

## Альтернатива: Frontend в dev режиме

Можно запустить frontend локально в dev режиме (если установлен Node.js):

```powershell
cd frontend
npm install
npm run dev
```

Frontend будет доступен на http://localhost:3000







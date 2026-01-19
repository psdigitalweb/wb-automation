# Быстрый старт для локальной разработки

## 🚀 За 3 шага

### 1. Подготовка (один раз)

```powershell
cd wb-automation

# Создайте .env
cp .env.example .env
# Отредактируйте .env: укажите POSTGRES_PASSWORD

# Создайте .htpasswd (если нужно)
# Windows: используйте онлайн генератор https://hostingcanada.org/htpasswd-generator/
# Или через Docker:
docker run --rm httpd:2.4-alpine htpasswd -nbB admin "YourPassword" | Out-File -Encoding ascii nginx/.htpasswd
```

### 2. Запуск

```powershell
# Соберите и запустите все
docker compose up -d --build

# Примените миграции
docker compose exec api alembic upgrade head
```

### 3. Откройте в браузере

- **Frontend**: http://localhost:3000 (Next.js dev с hot reload)
- **API**: http://localhost:8000/docs (Swagger UI)
- **API через Nginx**: http://localhost/api/docs
- **Adminer**: http://localhost/adminer/

## ✅ Готово!

Теперь у вас:
- ✅ Backend в Docker (postgres, redis, api, worker, beat)
- ✅ Frontend в Docker dev режиме (hot reload, быстрый старт)
- ✅ Полная функциональность проекта

## 🔧 Полезные команды

```powershell
# Логи frontend
docker compose logs -f frontend

# Логи API
docker compose logs -f api

# Перезапуск frontend
docker compose restart frontend

# Остановить все
docker compose down
```

## 📝 Изменения в коде

- **Frontend**: Изменения в `frontend/` автоматически применяются (hot reload)
- **Backend**: Изменения в `src/app/` автоматически применяются (FastAPI --reload)

## 🐛 Решение проблем

**Frontend не запускается?**
```powershell
docker compose logs frontend
docker compose build frontend --no-cache
docker compose up -d frontend
```

**API не отвечает?**
```powershell
docker compose logs api
docker compose restart api
```

**Подробная документация**: см. `LOCAL_DEVELOPMENT.md`







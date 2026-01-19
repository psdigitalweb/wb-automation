# Фикс импорта ingest_rrp_xml

## Проблема
FastAPI падал при импорте из-за отсутствующего модуля:
```
ModuleNotFoundError: No module named 'app.ingest_rrp_xml'
```

## Root Cause
В `src/app/main.py` был импорт несуществующего модуля:
```python
from app.ingest_rrp_xml import router as ingest_rrp_xml_router, rrp_router
```

Модуль `ingest_rrp_xml.py` не существует в `src/app/`.

## Решение
Закомментированы импорт и использование роутеров:

**Файл:** `src/app/main.py`

1. Закомментирован импорт (строка 15):
```python
# from app.ingest_rrp_xml import router as ingest_rrp_xml_router, rrp_router  # Module not found - commented out
```

2. Закомментированы include_router (строки 61-62):
```python
# app.include_router(ingest_rrp_xml_router)  # Module not found - commented out
# app.include_router(rrp_router)  # Module not found - commented out
```

## Проверка после фикса

### 1. Перезапустить API контейнер
```powershell
cd wb-automation
docker compose restart api
```

### 2. Проверить логи (не должно быть ошибок импорта)
```powershell
docker compose logs -n 50 api
```

### 3. Проверить health endpoint
```powershell
curl http://localhost:8000/api/v1/health
# Ожидаемый ответ: {"status": "ok"}
```

### 4. Проверить docs
```powershell
curl http://localhost:8000/docs
# Ожидаемый ответ: HTML страница Swagger UI (HTTP 200)
```

### 5. Проверить статус контейнера
```powershell
docker compose ps api
# Должен быть "Up" (не "Restarting" или "Exited")
```

## Ожидаемый результат
- ✅ API контейнер запускается без ошибок
- ✅ `/api/v1/health` возвращает `{"status": "ok"}`
- ✅ `/docs` открывается (Swagger UI)
- ✅ Нет ошибок "ModuleNotFoundError" в логах
- ✅ "Empty reply from server" исчезает

## Если проблема сохраняется

1. Проверить все импорты в `main.py`:
```powershell
docker compose exec api python -c "from app import main; print('OK')"
```

2. Проверить логи на другие ошибки:
```powershell
docker compose logs -n 100 api | Select-String -Pattern "Error|Exception|Traceback"
```

3. Проверить, что все зависимости установлены:
```powershell
docker compose exec api pip list | Select-String -Pattern "fastapi|uvicorn"
```



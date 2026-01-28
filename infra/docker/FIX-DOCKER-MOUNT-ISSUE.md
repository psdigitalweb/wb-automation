# Критическое исправление: Docker Desktop Windows Mount Issue

## Проблема
```
Error response from daemon: error while creating mount source path '/run/desktop/mnt/host/d/Work/EcomCore': mkdir /run/desktop/mnt/host/d: file exists
```

## Диагностика
Проблема возникает даже когда:
- ✅ Диск D:\ добавлен в File Sharing (Settings → Resources → File Sharing)
- ✅ Используются относительные пути в docker-compose.yml
- ✅ Docker Desktop запущен и работает

**Причина:** Docker Desktop кэширует неправильное внутреннее состояние монтирования томов, где `/run/desktop/mnt/host/d` существует как файл вместо директории.

## Решение (пошагово)

### Шаг 1: Полная очистка состояния Docker
```powershell
cd d:\Work\EcomCore\infra\docker

# Остановить все контейнеры
docker compose down -v

# Очистить систему Docker
docker system prune -f --volumes

# Удалить все неиспользуемые сети
docker network prune -f
```

### Шаг 2: Полный перезапуск Docker Desktop
1. **Полностью закройте Docker Desktop:**
   - Правый клик на иконке Docker Desktop в системном трее
   - Выберите "Quit Docker Desktop"
   - Откройте Task Manager (Ctrl+Shift+Esc)
   - Найдите процессы `Docker Desktop` и `com.docker.backend`
   - Завершите их, если они все еще запущены

2. **Подождите 10-15 секунд**

3. **Запустите Docker Desktop снова**
   - Подождите, пока Docker Desktop полностью запустится
   - Индикатор в трее должен стать зеленым
   - Проверьте, что Docker работает: `docker info`

### Шаг 3: Переконфигурировать File Sharing (если проблема сохраняется)
1. Откройте Docker Desktop → Settings → Resources → File Sharing
2. **Временно удалите D:\ из списка** (кнопка "-")
3. Нажмите "Apply & Restart"
4. После перезапуска Docker Desktop **добавьте D:\ обратно**
5. Нажмите "Apply & Restart" снова

### Шаг 4: Запустить сервисы
```powershell
cd d:\Work\EcomCore\infra\docker

# Попробовать запустить все сервисы
docker compose up -d --build

# Если ошибка сохраняется, запустить без nginx
docker compose up -d --build postgres redis api worker beat frontend

# Затем попробовать запустить nginx отдельно
docker compose up -d nginx
```

## Альтернативное решение: Использовать скрипты

### Скрипт fix-docker-mount.ps1 (рекомендуется)
Более продвинутый скрипт, который пытается запустить сервисы по одному и показывает детальную диагностику:
```powershell
cd d:\Work\EcomCore\infra\docker
.\fix-docker-mount.ps1
```

### Скрипт start.ps1
Базовый скрипт для быстрого запуска:
```powershell
cd d:\Work\EcomCore\infra\docker
.\start.ps1
```

Оба скрипта автоматически:
1. Проверяют, что Docker запущен
2. Запускают основные сервисы по одному
3. Пытаются запустить nginx отдельно
4. Показывают статус всех сервисов

## Проверка после исправления
```powershell
# Проверить статус контейнеров
docker compose ps

# Проверить логи API
docker logs ecomcore-api-1 --tail 50

# Проверить, что все сервисы работают
docker compose logs --tail 20
```

## Если проблема все еще сохраняется

**КРИТИЧЕСКОЕ РЕШЕНИЕ:** Если проблема сохраняется даже после полного перезапуска Docker Desktop, это указывает на поврежденное внутреннее состояние виртуальной машины Docker Desktop.

### Вариант A: Сброс Docker Desktop к заводским настройкам
1. **Полностью закройте Docker Desktop** (через Task Manager)
2. **Удалите данные Docker Desktop:**
   ```powershell
   # ОСТОРОЖНО: Это удалит все контейнеры, образы и volumes!
   # Сначала экспортируйте важные данные, если нужно
   
   # Остановить Docker Desktop
   # Затем удалить данные (путь может отличаться)
   Remove-Item -Recurse -Force "$env:LOCALAPPDATA\Docker"
   Remove-Item -Recurse -Force "$env:APPDATA\Docker"
   ```
3. **Запустите Docker Desktop снова** (он создаст новую виртуальную машину)
4. **Настройте File Sharing заново:**
   - Settings → Resources → File Sharing
   - Добавьте D:\
   - Apply & Restart
5. **Попробуйте запустить снова:**
   ```powershell
   cd d:\Work\EcomCore\infra\docker
   docker compose up -d --build
   ```

### Вариант B: Использовать WSL2 backend
1. Docker Desktop → Settings → General
2. Включите "Use the WSL 2 based engine"
3. Перезапустите Docker Desktop

### Вариант C: Переместить проект на диск C:
Если возможно, переместите проект на диск C: (где обычно нет таких проблем):
```powershell
# Создать новую директорию
mkdir C:\Work\EcomCore

# Скопировать проект (или использовать git clone)
# Затем обновить пути в docker-compose.yml
```

### Вариант D: Использовать Docker без Docker Desktop
Рассмотрите использование Docker Engine напрямую через WSL2 или другой способ.

## Технические детали

**Почему это происходит:**
- Docker Desktop на Windows использует виртуальную машину для запуска Docker Engine
- Пути Windows (D:\Work\EcomCore) маппятся в Linux пути (/run/desktop/mnt/host/d/Work/EcomCore)
- При создании промежуточных директорий Docker Desktop иногда создает файл вместо директории
- Это состояние кэшируется и сохраняется между перезапусками

**Почему перезапуск помогает:**
- Полный перезапуск Docker Desktop очищает внутреннее состояние виртуальной машины
- Это позволяет Docker Desktop заново создать правильную структуру путей монтирования

**Почему проблема может сохраняться:**
- Если `/run/desktop/mnt/host/d` уже существует как файл (а не директория), Docker Desktop не может его перезаписать
- Это состояние сохраняется в виртуальной машине Docker Desktop даже после перезапуска
- Единственное решение - полный сброс Docker Desktop к заводским настройкам (удаление данных виртуальной машины)

## Ссылки
- [Docker Desktop Windows File Sharing](https://docs.docker.com/desktop/settings/windows/#file-sharing)
- [Docker Desktop Troubleshooting](https://docs.docker.com/desktop/troubleshoot/)

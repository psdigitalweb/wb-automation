# Windows Docker Desktop Fix

## Проблема
При запуске `docker compose up -d --build` на Windows возникает ошибка:
```
Error response from daemon: error while creating mount source path '/run/desktop/mnt/host/d/Work/EcomCore': mkdir /run/desktop/mnt/host/d: file exists
```

## Причина
Docker Desktop на Windows пытается создать путь `/run/desktop/mnt/host/d`, но не может, потому что файл уже существует. Это известная проблема Docker Desktop при работе с диском D:.

**Важно:** Даже если диск D:\ уже добавлен в File Sharing (как видно на скриншоте), проблема может сохраняться из-за внутреннего состояния Docker Desktop, которое кэширует неправильные пути монтирования.

## Решение

### Вариант 1: Полный перезапуск Docker Desktop (рекомендуется)
1. **Полностью закройте Docker Desktop:**
   - Правый клик на иконке Docker Desktop в системном трее
   - Выберите "Quit Docker Desktop"
   - Убедитесь, что процесс полностью завершился (через Task Manager)

2. **Очистите состояние Docker (опционально, но рекомендуется):**
   ```powershell
   cd d:\Work\EcomCore\infra\docker
   docker compose down -v
   docker system prune -f
   ```

3. **Запустите Docker Desktop снова**
   - Подождите, пока Docker Desktop полностью запустится (зеленый индикатор в трее)

4. **Попробуйте запустить снова:**
   ```powershell
   cd d:\Work\EcomCore\infra\docker
   docker compose up -d --build
   ```

### Вариант 2: Проверить и переконфигурировать File Sharing в Docker Desktop
**Примечание:** Даже если D:\ уже в списке (как на скриншоте), проблема может сохраняться.

1. Откройте Docker Desktop → Settings → Resources → File Sharing
2. **Временно удалите D:\ из списка** (кнопка "-")
3. Нажмите "Apply & Restart"
4. После перезапуска Docker Desktop **добавьте D:\ обратно** (кнопка "+" или "Browse")
5. Нажмите "Apply & Restart" снова
6. Попробуйте запустить: `docker compose up -d --build`

### Вариант 3: Использовать WSL2 backend (если доступен)
1. Settings → General → Use the WSL 2 based engine
2. Перезапустите Docker Desktop

### Вариант 4: Временно исключить nginx из запуска
Если нужно запустить приложение без nginx (nginx часто вызывает проблему с монтированием):
```powershell
cd d:\Work\EcomCore\infra\docker
docker compose up -d --build postgres redis api worker beat frontend
```

После успешного запуска основных сервисов попробуйте запустить nginx отдельно:
```powershell
docker compose up -d nginx
```

### Вариант 5: Использовать скрипт start.ps1
Скрипт автоматически пытается запустить сервисы без nginx, затем запускает nginx отдельно:
```powershell
cd d:\Work\EcomCore\infra\docker
.\start.ps1
```

## Проверка после исправления
```powershell
cd d:\Work\EcomCore\infra\docker
docker compose down -v
docker compose up -d --build
docker compose ps
docker logs ecomcore-api-1 --tail 50
```

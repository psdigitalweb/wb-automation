# Security Hardening: Отчет

## Проблема
Ранее миграция создавала admin user с дефолтным паролем "password", что небезопасно для production. Bootstrap был включен по умолчанию.

## Что изменено

### 1. Убрано создание admin/password из миграции

**Файл:** `alembic/versions/b3d4e5f6a7b8_ensure_project_id_constraints.py`

**Изменения:**
- Admin user создается в миграции **ТОЛЬКО** если `ADMIN_PASSWORD` установлен
- Если `ADMIN_PASSWORD` не установлен - admin user не создается (выводится NOTE)
- Legacy проект больше не создается в миграции (перенесено в bootstrap)

**Безопасность:**
- Нет дефолтного пароля "password" в миграции
- Admin user создается только при явном указании `ADMIN_PASSWORD`

### 2. Bootstrap отключен по умолчанию

**Файл:** `src/app/bootstrap.py`

**Изменения:**
- `BOOTSTRAP_ENABLED` по умолчанию `false` (было `true`)
- Admin user создается только если `ADMIN_PASSWORD` установлен
- Legacy проект создается только если bootstrap включен и admin user создан

**Новое поведение:**
```python
# По умолчанию bootstrap отключен
BOOTSTRAP_ENABLED=false  # НЕ создает admin/Legacy

# Для включения в dev/test
BOOTSTRAP_ENABLED=true
ADMIN_PASSWORD=secure_password  # ОБЯЗАТЕЛЬНО должен быть установлен
```

### 3. Docker Compose override для dev

**Файл:** `docker-compose.override.yml.example` (НОВЫЙ)

**Содержимое:**
```yaml
services:
  api:
    environment:
      BOOTSTRAP_ENABLED: "true"
      ADMIN_PASSWORD: "dev_password_change_me"
      PROJECT_SECRETS_KEY: "fb4603fc1d831699133c2a68..."
```

**Использование:**
```bash
# Скопировать пример
cp docker-compose.override.yml.example docker-compose.override.yml

# Отредактировать docker-compose.override.yml (изменить пароли/ключи)
# docker-compose автоматически загрузит override файл
```

**Важно:**
- `docker-compose.override.yml` автоматически игнорируется git (если добавлен в .gitignore)
- Используется только для локальной разработки
- НЕ коммитится в репозиторий (содержит пароли)

### 4. Проверка PROJECT_SECRETS_KEY при старте

**Файл:** `src/app/main.py`

**Добавлено:**
- Проверка при startup: если в `project_marketplaces` есть `api_token_encrypted`, но `PROJECT_SECRETS_KEY` не установлен - логируется **ERROR**

**Пример вывода:**
```
================================================================================
SECURITY ERROR: Encrypted tokens found but PROJECT_SECRETS_KEY is not set!
Found 2 encrypted token(s) in project_marketplaces
PROJECT_SECRETS_KEY must be set to decrypt tokens
================================================================================
```

**Безопасность:**
- Невозможно пропустить проблему - ERROR логируется при старте
- Явно указывает на проблему с encrypted tokens

## Переменные окружения

### Обязательные (для работы с токенами)
- `PROJECT_SECRETS_KEY` - ключ для шифрования токенов (Fernet key)

### Опциональные (для bootstrap)
- `BOOTSTRAP_ENABLED` - включить bootstrap (по умолчанию `false`)
- `ADMIN_PASSWORD` - пароль для admin user (требуется если `BOOTSTRAP_ENABLED=true`)
- `ADMIN_USERNAME` - имя admin user (по умолчанию `admin`)
- `ADMIN_EMAIL` - email admin user (по умолчанию `admin@example.com`)

## Порядок применения

### 1. Для разработки (dev)

```bash
# 1. Создать override файл
cp docker-compose.override.yml.example docker-compose.override.yml

# 2. Отредактировать docker-compose.override.yml:
#    - Изменить ADMIN_PASSWORD на безопасный пароль
#    - Использовать PROJECT_SECRETS_KEY (можно оставить из примера для dev)

# 3. Запустить
docker compose up -d
```

### 2. Для production

```bash
# 1. НЕ использовать docker-compose.override.yml

# 2. Установить переменные окружения через env_file или secrets:
PROJECT_SECRETS_KEY=<генерация_безопасного_ключа>
BOOTSTRAP_ENABLED=false  # Или true если нужен bootstrap
ADMIN_PASSWORD=<безопасный_пароль>  # Если BOOTSTRAP_ENABLED=true

# 3. Проверить что PROJECT_SECRETS_KEY установлен
#    (ERROR будет в логах при старте если не установлен)
```

## Проверки безопасности

### 1. Проверка PROJECT_SECRETS_KEY

```powershell
# Перезапустить API и проверить логи
docker compose restart api
docker compose logs api | Select-String -Pattern "SECURITY ERROR|PROJECT_SECRETS_KEY" -Context 3
```

**Ожидается:**
- ✅ Нет ERROR если `PROJECT_SECRETS_KEY` установлен
- ❌ ERROR если есть encrypted tokens но `PROJECT_SECRETS_KEY` не установлен

### 2. Проверка bootstrap

```powershell
# Проверить что admin user создан (если BOOTSTRAP_ENABLED=true)
docker compose exec postgres psql -U wb -d wb -c "SELECT id, username, is_superuser FROM users WHERE username = 'admin';"

# Проверить что Legacy проект создан (если BOOTSTRAP_ENABLED=true)
docker compose exec postgres psql -U wb -d wb -c "SELECT id, name FROM projects WHERE name = 'Legacy';"
```

**Ожидается:**
- ✅ Admin user существует если `BOOTSTRAP_ENABLED=true` и `ADMIN_PASSWORD` установлен
- ✅ Legacy проект существует если `BOOTSTRAP_ENABLED=true` и admin user создан
- ❌ Нет admin/Legacy если `BOOTSTRAP_ENABLED=false` (безопасно для production)

### 3. Проверка миграций

```powershell
# Применить миграции на чистой БД
docker compose down -v
docker compose up -d postgres
Start-Sleep -Seconds 5
docker compose exec api alembic upgrade head
```

**Ожидается:**
- ✅ Миграция проходит без ошибок
- ✅ Нет создания admin user с дефолтным паролем
- ✅ NOTE о том что `ADMIN_PASSWORD` не установлен (но не ERROR)

## Acceptance Criteria ✅

- ✅ Нет создания admin/password в миграции без `ADMIN_PASSWORD`
- ✅ Bootstrap отключен по умолчанию (`BOOTSTRAP_ENABLED=false`)
- ✅ Admin user создается только если `ADMIN_PASSWORD` установлен
- ✅ Legacy проект создается только через bootstrap (не в миграции)
- ✅ `docker-compose.override.yml.example` создан с примером конфигурации
- ✅ Проверка `PROJECT_SECRETS_KEY` при старте - ERROR если tokens есть но ключ нет
- ✅ Миграции работают на чистой БД без дефолтных паролей
- ✅ Production-ready: bootstrap выключен по умолчанию, пароли не хардкодятся

## Рекомендации

1. **Для production:**
   - НЕ используйте `docker-compose.override.yml` с паролями
   - Используйте secrets management (Docker secrets, Kubernetes secrets, etc.)
   - Генерируйте `PROJECT_SECRETS_KEY` через `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

2. **Для dev:**
   - Используйте `docker-compose.override.yml` для локальных паролей
   - Добавьте `docker-compose.override.yml` в `.gitignore` если еще не добавлен
   - Меняйте `ADMIN_PASSWORD` на что-то более безопасное чем "dev_password_change_me"

3. **Мониторинг:**
   - Проверяйте логи при старте на наличие ERROR о `PROJECT_SECRETS_KEY`
   - Убедитесь что `BOOTSTRAP_ENABLED=false` в production (если bootstrap не нужен)



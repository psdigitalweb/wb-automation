# Быстрый старт

## Минимальные шаги для запуска проекта

### 1. Создайте `.env` файл

```bash
cp .env.example .env
```

Отредактируйте `.env` и укажите хотя бы `POSTGRES_PASSWORD`.

### 2. Создайте `.htpasswd` для Adminer

**Windows (PowerShell):**
```powershell
# Если у вас установлен WSL или Git Bash:
wsl htpasswd -c nginx/.htpasswd admin

# Или создайте файл вручную (без пароля, небезопасно):
# Создайте файл nginx/.htpasswd с содержимым: admin:$apr1$...
# Лучше использовать онлайн генератор: https://hostingcanada.org/htpasswd-generator/
```

**Linux/Mac:**
```bash
# Установите apache2-utils (если нужно)
sudo apt-get install apache2-utils  # Debian/Ubuntu
brew install httpd                   # Mac

# Создайте файл
htpasswd -c nginx/.htpasswd admin
```

**Или используйте скрипт:**
```bash
chmod +x scripts/create_htpasswd.sh
./scripts/create_htpasswd.sh
```

### 3. Запустите проект

```bash
# Соберите и запустите
docker compose up -d --build

# Примените миграции
docker compose exec api alembic upgrade head
```

### 4. Откройте в браузере

- **Frontend**: http://localhost
- **API Docs**: http://localhost/api/docs
- **Adminer**: http://localhost/adminer/

Готово! 🎉

---

**Подробная инструкция:** см. `SETUP_LOCAL.md`







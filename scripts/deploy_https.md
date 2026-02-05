# HTTPS rollout для ecomcore.ru (Let's Encrypt)

Всё выполняется из репозитория; ручные правки на сервере вне git не требуются.

## Требования

- Домен ecomcore.ru и www.ecomcore.ru указывают на IP сервера (31.130.135.65).
- В корне репозитория в `.env` задано: `LETSENCRYPT_EMAIL=your@email.com`.
- На сервере открыты порты **80** и **443** (TCP) в firewall провайдера/хоста.

## Firewall

**Обязательно откройте на сервере (или у провайдера):**

- **TCP 80** — HTTP (нужен для выдачи и продления сертификатов).
- **TCP 443** — HTTPS.

Пример (ufw на сервере):

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

## Первый запуск (получение сертификата)

Nginx не может стартовать с конфигом HTTPS, пока нет сертификатов. Поэтому первый раз используем конфиг только с HTTP (bootstrap), получаем сертификат, затем переключаемся на полный конфиг с HTTPS.

### Шаг 1: Переменная для Certbot

В корне репозитория в `.env` добавьте (или проверьте):

```env
LETSENCRYPT_EMAIL=admin@ecomcore.ru
```

### Шаг 2: Bootstrap — nginx только на 80

Временно подменить конфиг nginx так, чтобы не подключался блок с 443 (нет сертификатов). В `infra/docker/docker-compose.prod.yml` в секции `nginx` замените монтирование `conf.d` на `conf.d-bootstrap`:

```yaml
# Было:
- ./nginx/conf.d:/etc/nginx/conf.d:ro
# Временно для первого запуска:
- ./nginx/conf.d-bootstrap:/etc/nginx/conf.d:ro
```

Сохраните файл (можно закоммитить как временный шаг или сделать локально только на сервере и откатить после).

### Шаг 3: Запуск стека с prod overlay

На сервере из корня репозитория:

```bash
cd /path/to/wb-automation/infra/docker
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Убедитесь, что nginx слушает 80 и сервисы подняты:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl -I http://localhost
```

### Шаг 4: Выпуск сертификата Let's Encrypt

Один раз запустить certbot (профиль `init-certs`):

```bash
cd /path/to/wb-automation/infra/docker
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile init-certs run --rm certbot
```

Команда внутри контейнера по сути:

- `certbot certonly --webroot -w /var/www/certbot -d ecomcore.ru -d www.ecomcore.ru --email $LETSENCRYPT_EMAIL --agree-tos --no-eff-email --non-interactive`

При успехе сертификаты попадут в volume `certbot_letsencrypt`.

### Шаг 5: Включить HTTPS и редирект

1. Вернуть в `docker-compose.prod.yml` монтирование обычного `conf.d` (убрать bootstrap):

   ```yaml
   - ./nginx/conf.d:/etc/nginx/conf.d:ro
   ```

2. Перезапустить nginx:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate nginx
   ```

После этого:
- HTTP (80) отдаёт `/.well-known/acme-challenge/` и редиректит остальное на HTTPS.
- HTTPS (443) обслуживает сайт с валидным сертификатом.

### Шаг 6: Проверка

```bash
# Редирект HTTP -> HTTPS
curl -I http://localhost
# Ожидается: 301 и Location: https://...

# HTTPS (на сервере можно localhost)
curl -Ik https://localhost
# Ожидается: 200 (или 301 при редиректе с www)
```

Извне:

```bash
curl -I http://ecomcore.ru
curl -Ik https://ecomcore.ru
```

## Продление сертификатов (renewal)

В `docker-compose.prod.yml` сервис **certbot-renew** каждые 12 часов выполняет:

```bash
certbot renew --webroot -w /var/www/certbot
```

После обновления сертификатов nginx нужно перезагрузить, чтобы подхватить новые файлы.

**Вариант A — перезапуск nginx (простой, краткий простой):**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart nginx
```

Можно повесить на cron (например, раз в день после возможного renew):

```bash
0 4 * * * cd /path/to/wb-automation/infra/docker && docker compose -f docker-compose.yml -f docker-compose.prod.yml restart nginx
```

**Вариант B — reload без даунтайма (рекомендуется):**

По крону на хосте раз в день вызывать reload контейнера nginx:

```bash
0 4 * * * docker exec ecomcore-nginx-1 nginx -s reload
```

(Имя контейнера может быть другим — проверьте `docker compose -f docker-compose.yml -f docker-compose.prod.yml ps`.)

Рекомендация: использовать вариант B (cron с `nginx -s reload`) после того, как certbot-renew хотя бы раз обновил сертификаты.

## Обычный запуск на проде

После однократной настройки выше на сервере всегда поднимайте стек так:

```bash
cd /path/to/wb-automation/infra/docker
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Локально (без HTTPS) по-прежнему:

```bash
docker compose up -d
```

## Резюме команд на сервере

| Действие | Команды |
|----------|--------|
| Открыть порты | `ufw allow 80/tcp; ufw allow 443/tcp; ufw reload` (или аналог у провайдера) |
| Первый раз (bootstrap) | Подменить в prod compose `conf.d` → `conf.d-bootstrap`, затем `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` |
| Выпуск сертификата | `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile init-certs run --rm certbot` |
| Включить HTTPS | Вернуть `conf.d`, затем `docker compose -f ... -f docker-compose.prod.yml up -d --force-recreate nginx` |
| Рестарт nginx после renew | `docker compose -f ... -f docker-compose.prod.yml restart nginx` или cron: `docker exec ecomcore-nginx-1 nginx -s reload` |

## Файлы в репозитории

- `infra/docker/docker-compose.prod.yml` — overlay с nginx 80+443, certbot, certbot-renew, volumes.
- `infra/docker/nginx/nginx.prod.conf` — основной конфиг nginx для prod (подключает `conf.d/*.conf`).
- `infra/docker/nginx/conf.d/00-http.conf` — порт 80: ACME challenge + редирект на HTTPS.
- `infra/docker/nginx/conf.d/10-https.conf` — порт 443: SSL и proxy на frontend/api/adminer.
- `infra/docker/nginx/conf.d-bootstrap/00-http-only.conf` — только HTTP для первого запуска до получения сертификата.

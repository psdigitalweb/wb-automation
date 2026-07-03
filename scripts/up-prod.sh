#!/bin/bash
# Поднять стек для продакшена (ecomcore.ru + reports.zakka.ru по HTTPS).
# После любого "docker compose up --build" без -f prod nginx получает dev-конфиг без SSL — сайт по HTTPS перестаёт открываться.
# Использование: из корня репо — bash scripts/up-prod.sh
set -e
cd "$(dirname "$0")/.."
COMPOSE_FILE="infra/docker/docker-compose.prod.yml"
echo "Starting/updating with prod compose: $COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" up -d
echo "Done. Check: curl -sI -k https://127.0.0.1:443/ -H 'Host: ecomcore.ru' | head -1"

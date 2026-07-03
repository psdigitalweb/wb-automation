#!/bin/bash
# Диагностика доступности https://ecomcore.ru/
# Запуск из корня репо: bash scripts/diagnose-ecomcore.sh
set -e
COMPOSE_DIR="${1:-infra/docker}"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.prod.yml"
echo "=== Docker Compose (prod) status ==="
docker compose -f "$COMPOSE_FILE" ps 2>&1 || true
echo ""
echo "=== Nginx logs (last 40 lines) ==="
docker compose -f "$COMPOSE_FILE" logs nginx --tail 40 2>&1 || true
echo ""
echo "=== Frontend logs (last 60 lines) ==="
docker compose -f "$COMPOSE_FILE" logs frontend --tail 60 2>&1 || true
echo ""
echo "=== API logs (last 20 lines) ==="
docker compose -f "$COMPOSE_FILE" logs api --tail 20 2>&1 || true

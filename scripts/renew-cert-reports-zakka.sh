#!/bin/bash
# Renew reports.zakka.ru SSL cert (run via cron weekly)
set -e
cd "$(dirname "$0")/.."
certbot renew --config-dir nginx/letsencrypt-reports-zakka \
  --work-dir nginx/letsencrypt-reports-zakka/work \
  --logs-dir nginx/letsencrypt-reports-zakka/logs \
  --quiet
docker compose -f infra/docker/docker-compose.yml exec -T nginx nginx -s reload 2>/dev/null || true

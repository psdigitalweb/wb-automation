#!/bin/bash
# Renew ecomcore.ru SSL cert (run via cron weekly, e.g. 0 3 * * 0)
# Certbot renews only when <30 days to expiry.
set -e
cd "$(dirname "$0")/.."
certbot renew --config-dir nginx/letsencrypt-ecomcore \
  --work-dir nginx/letsencrypt-ecomcore/work \
  --logs-dir nginx/letsencrypt-ecomcore/logs \
  --quiet
# Reload nginx to pick up new certs (only if renewed)
docker compose -f infra/docker/docker-compose.yml exec -T nginx nginx -s reload 2>/dev/null || true

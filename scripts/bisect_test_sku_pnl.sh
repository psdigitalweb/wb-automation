#!/usr/bin/env bash
# Bisect test: trigger SKU PnL build, wait, check DB for rows.
# Exit 0 = PASS (snapshot has rows), 1 = FAIL.
# Usage: from repo root, with API_BASE, PROJECT_ID, AUTH_TOKEN or LOGIN/PASSWORD set.
#   bash scripts/bisect_test_sku_pnl.sh

set -e
API_BASE="${API_BASE:-http://localhost:8000}"
API_URL="${API_BASE}/api"
PROJECT_ID="${PROJECT_ID:-1}"
# Period: use last 14 days by default; override PERIOD_FROM/PERIOD_TO if needed
FROM="${PERIOD_FROM:-$(date -d '14 days ago' +%Y-%m-%d 2>/dev/null || date -v-14d +%Y-%m-%d 2>/dev/null || $(python3 -c "from datetime import date, timedelta; print((date.today()-timedelta(days=14)).isoformat())"))}"
TO="${PERIOD_TO:-$(date +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d 2>/dev/null || $(python3 -c "from datetime import date; print(date.today().isoformat())"))}"

if [ -z "$AUTH_TOKEN" ]; then
  if [ -n "$LOGIN" ] && [ -n "$PASSWORD" ]; then
    RESP=$(curl -s -X POST "${API_URL}/v1/auth/login" -H "Content-Type: application/json" -d "{\"username\":\"${LOGIN}\",\"password\":\"${PASSWORD}\"}")
    AUTH_TOKEN="Bearer $(echo "$RESP" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')"
    [ -z "$AUTH_TOKEN" ] || [ "$AUTH_TOKEN" = "Bearer " ] && { echo "Login failed"; exit 2; }
  else
    echo "Set AUTH_TOKEN or LOGIN+PASSWORD"; exit 2
  fi
fi

curl -s -o /dev/null -w "%{http_code}" -X POST "${API_URL}/v1/projects/${PROJECT_ID}/marketplaces/wildberries/finances/sku-pnl/build" \
  -H "Authorization: $AUTH_TOKEN" -H "Content-Type: application/json" \
  -d "{\"period_from\":\"$FROM\",\"period_to\":\"$TO\",\"version\":1,\"rebuild\":true,\"ensure_events\":true}" | grep -q 202 || { echo "Build returned non-202"; exit 1; }

# Wait up to 90s for task to complete
for i in $(seq 1 18); do
  sleep 5
  # Check DB: wb_sku_pnl_snapshots row count for project/period (docker or local psql)
  if command -v docker >/dev/null 2>&1; then
    COUNT=$(docker compose -f infra/docker/docker-compose.yml exec -T postgres psql -U wb -d wb -t -A -c "SELECT COUNT(*) FROM wb_sku_pnl_snapshots WHERE project_id=$PROJECT_ID AND period_from='$FROM' AND period_to='$TO' AND version=1" 2>/dev/null || echo "0")
  else
    COUNT="${SKU_PNL_COUNT:-0}"
  fi
  COUNT=$(echo "$COUNT" | tr -d '\r\n ')
  if [ -n "$COUNT" ] && [ "$COUNT" -gt 0 ] 2>/dev/null; then
    echo "PASS: rows=$COUNT"; exit 0
  fi
done
echo "FAIL: no rows after 90s"; exit 1

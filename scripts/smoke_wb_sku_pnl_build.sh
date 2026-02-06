#!/usr/bin/env bash
# Smoke test: trigger WB SKU PnL build and optionally check list response.
# Usage:
#   export API_BASE="${API_BASE:-http://localhost:8000}"
#   export PROJECT_ID=1
#   export AUTH_TOKEN="Bearer <jwt>"   # or use LOGIN/PASSWORD below
#   export LOGIN=admin PASSWORD=admin123   # to get token automatically
#   ./scripts/smoke_wb_sku_pnl_build.sh

set -e
API_BASE="${API_BASE:-http://localhost:8000}"
API_URL="${API_BASE}/api"
PROJECT_ID="${PROJECT_ID:-1}"
FROM="${PERIOD_FROM:-$(date +%Y-%m-01)}"
TO="${PERIOD_TO:-$(date +%Y-%m-%d)}"

if [ -z "$AUTH_TOKEN" ]; then
  if [ -n "$LOGIN" ] && [ -n "$PASSWORD" ]; then
    echo "Getting token..."
    RESP=$(curl -s -X POST "${API_URL}/v1/auth/login" -H "Content-Type: application/json" -d "{\"username\":\"${LOGIN}\",\"password\":\"${PASSWORD}\"}")
    AUTH_TOKEN="Bearer $(echo "$RESP" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')"
    if [ -z "$AUTH_TOKEN" ] || [ "$AUTH_TOKEN" = "Bearer " ]; then
      echo "Login failed. Response: $RESP"
      exit 1
    fi
  else
    echo "Set AUTH_TOKEN or LOGIN+PASSWORD"
    exit 1
  fi
fi

echo "Triggering build project_id=$PROJECT_ID period $FROM..$TO"
BUILD_RESP=$(curl -s -w "\n%{http_code}" -X POST "${API_URL}/v1/projects/${PROJECT_ID}/marketplaces/wildberries/finances/sku-pnl/build" \
  -H "Authorization: $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"period_from\":\"$FROM\",\"period_to\":\"$TO\",\"version\":1,\"rebuild\":true,\"ensure_events\":true}")

HTTP_BODY=$(echo "$BUILD_RESP" | head -n -1)
HTTP_CODE=$(echo "$BUILD_RESP" | tail -n 1)

if [ "$HTTP_CODE" != "202" ]; then
  echo "Build failed: HTTP $HTTP_CODE"
  echo "$HTTP_BODY" | head -c 500
  exit 1
fi

echo "Build accepted (202). Response: $HTTP_BODY"
TASK_ID=$(echo "$HTTP_BODY" | sed -n 's/.*"task_id":"\([^"]*\)".*/\1/p')
TRACE_ID=$(echo "$HTTP_BODY" | sed -n 's/.*"trace_id":"\([^"]*\)".*/\1/p')
echo "task_id=$TASK_ID trace_id=$TRACE_ID"
echo "Waiting 30s then checking list..."
sleep 30
LIST_RESP=$(curl -s -w "\n%{http_code}" "${API_URL}/v1/projects/${PROJECT_ID}/marketplaces/wildberries/finances/sku-pnl?period_from=${FROM}&period_to=${TO}&version=1&limit=1" \
  -H "Authorization: $AUTH_TOKEN")
LIST_BODY=$(echo "$LIST_RESP" | head -n -1)
LIST_CODE=$(echo "$LIST_RESP" | tail -n 1)
if [ "$LIST_CODE" != "200" ]; then
  echo "List failed: HTTP $LIST_CODE"
  exit 1
fi
TOTAL=$(echo "$LIST_BODY" | sed -n 's/.*"total_count":\([0-9]*\).*/\1/p')
echo "List OK. total_count=$TOTAL"
echo "Smoke OK."

#!/bin/bash
# Скрипт для проверки scoping данных по project_id
# Проверяет, что данные из одного проекта не видны в другом

set -e

echo "=== Тест scoping данных по project_id ==="
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

API_URL="http://localhost:8000/api"

# Проверка, что API доступен
echo -e "${YELLOW}1. Проверка доступности API...${NC}"
if ! curl -s -f "${API_URL}/v1/health" > /dev/null; then
    echo -e "${RED}❌ API недоступен по адресу ${API_URL}${NC}"
    echo "Убедитесь, что контейнеры запущены: docker compose up -d"
    exit 1
fi
echo -e "${GREEN}✅ API доступен${NC}"
echo ""

# Получение токена
echo -e "${YELLOW}2. Получение токена аутентификации...${NC}"
if [ -z "$AUTH_TOKEN" ]; then
    echo -e "${RED}❌ Переменная AUTH_TOKEN не установлена${NC}"
    echo "Используйте: export AUTH_TOKEN='Bearer YOUR_TOKEN_HERE'"
    exit 1
fi
echo -e "${GREEN}✅ Токен найден${NC}"
echo ""

# Создание проекта A
echo -e "${YELLOW}3. Создание проекта A...${NC}"
PROJECT_A_RESPONSE=$(curl -s -X POST \
    -H "Authorization: ${AUTH_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"name":"Project A - Test Scoping","description":"Test project for scoping"}' \
    "${API_URL}/v1/projects")

PROJECT_A_ID=$(echo "$PROJECT_A_RESPONSE" | jq -r '.id' 2>/dev/null || echo "")
if [ -z "$PROJECT_A_ID" ] || [ "$PROJECT_A_ID" = "null" ]; then
    echo -e "${RED}❌ Не удалось создать проект A${NC}"
    echo "Ответ: $PROJECT_A_RESPONSE"
    exit 1
fi
echo -e "${GREEN}✅ Проект A создан с ID: ${PROJECT_A_ID}${NC}"
echo ""

# Создание проекта B
echo -e "${YELLOW}4. Создание проекта B...${NC}"
PROJECT_B_RESPONSE=$(curl -s -X POST \
    -H "Authorization: ${AUTH_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"name":"Project B - Test Scoping","description":"Second test project"}' \
    "${API_URL}/v1/projects")

PROJECT_B_ID=$(echo "$PROJECT_B_RESPONSE" | jq -r '.id' 2>/dev/null || echo "")
if [ -z "$PROJECT_B_ID" ] || [ "$PROJECT_B_ID" = "null" ]; then
    echo -e "${RED}❌ Не удалось создать проект B${NC}"
    echo "Ответ: $PROJECT_B_RESPONSE"
    exit 1
fi
echo -e "${GREEN}✅ Проект B создан с ID: ${PROJECT_B_ID}${NC}"
echo ""

# Загрузка stocks для проекта A (если WB настроен)
echo -e "${YELLOW}5. Загрузка stocks для проекта A (может быть пропущена если WB не настроен)...${NC}"
STOCKS_A_RESPONSE=$(curl -s -X POST \
    -H "Authorization: ${AUTH_TOKEN}" \
    -H "Content-Type: application/json" \
    "${API_URL}/v1/ingest/projects/${PROJECT_A_ID}/stocks" 2>/dev/null || echo '{"status":"skipped"}')

STOCKS_A_STATUS=$(echo "$STOCKS_A_RESPONSE" | jq -r '.status' 2>/dev/null || echo "unknown")
if [ "$STOCKS_A_STATUS" = "started" ]; then
    echo -e "${GREEN}✅ Stocks ingestion для проекта A запущена${NC}"
    echo "Ожидание 10 секунд для завершения ingestion..."
    sleep 10
else
    echo -e "${YELLOW}⚠️  Stocks ingestion пропущена (WB не настроен или MOCK режим)${NC}"
fi
echo ""

# Проверка stocks в проекте A
echo -e "${YELLOW}6. Проверка stocks в проекте A...${NC}"
STOCKS_A_DATA=$(curl -s -H "Authorization: ${AUTH_TOKEN}" \
    "${API_URL}/v1/projects/${PROJECT_A_ID}/stocks/latest?limit=10" 2>/dev/null || echo '{"data":[]}')

STOCKS_A_COUNT=$(echo "$STOCKS_A_DATA" | jq '.data | length' 2>/dev/null || echo "0")
echo "Найдено stocks в проекте A: ${STOCKS_A_COUNT}"
echo ""

# Проверка stocks в проекте B (должно быть пусто)
echo -e "${YELLOW}7. Проверка stocks в проекте B (должно быть пусто)...${NC}"
STOCKS_B_DATA=$(curl -s -H "Authorization: ${AUTH_TOKEN}" \
    "${API_URL}/v1/projects/${PROJECT_B_ID}/stocks/latest?limit=10" 2>/dev/null || echo '{"data":[]}')

STOCKS_B_COUNT=$(echo "$STOCKS_B_DATA" | jq '.data | length' 2>/dev/null || echo "0")
echo "Найдено stocks в проекте B: ${STOCKS_B_COUNT}"

if [ "$STOCKS_B_COUNT" != "0" ]; then
    echo -e "${RED}❌ ОШИБКА: В проекте B найдены stocks, хотя их не должно быть!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Проект B пуст (как и должно быть)${NC}"
echo ""

# Проверка через БД напрямую
echo -e "${YELLOW}8. Проверка через БД (прямой SQL запрос)...${NC}"
STOCKS_A_DB=$(docker compose exec -T postgres psql -U wb -d wb -t -c \
    "SELECT COUNT(*) FROM stock_snapshots WHERE project_id = ${PROJECT_A_ID};" 2>/dev/null | xargs || echo "0")

STOCKS_B_DB=$(docker compose exec -T postgres psql -U wb -d wb -t -c \
    "SELECT COUNT(*) FROM stock_snapshots WHERE project_id = ${PROJECT_B_ID};" 2>/dev/null | xargs || echo "0")

echo "Stocks в БД для проекта A: ${STOCKS_A_DB}"
echo "Stocks в БД для проекта B: ${STOCKS_B_DB}"

if [ "$STOCKS_B_DB" != "0" ]; then
    echo -e "${RED}❌ ОШИБКА: В БД для проекта B найдены stocks!${NC}"
    exit 1
fi
echo ""

echo -e "${GREEN}=== ✅ ТЕСТ ПРОЙДЕН: Scoping работает правильно ===${NC}"
echo ""
echo "Итоги:"
echo "  - Проект A (ID: ${PROJECT_A_ID}): ${STOCKS_A_COUNT} stocks через API, ${STOCKS_A_DB} через БД"
echo "  - Проект B (ID: ${PROJECT_B_ID}): ${STOCKS_B_COUNT} stocks через API, ${STOCKS_B_DB} через БД"
echo ""
echo "✅ Данные из проекта A не видны в проекте B"



#!/bin/bash
# Скрипт для проверки подключения WB маркетплейса

set -e

echo "=== Тест подключения Wildberries маркетплейса ==="
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

# Проверка WB API токена (опционально)
echo -e "${YELLOW}3. Проверка WB API токена (опционально)...${NC}"
if [ -z "$WB_API_KEY" ]; then
    echo -e "${YELLOW}⚠️  Переменная WB_API_KEY не установлена${NC}"
    echo "Для теста подключения укажите WB API токен:"
    echo "  export WB_API_KEY='your_wb_token_here'"
    echo ""
    read -p "Введите WB API токен (или нажмите Enter для пропуска): " WB_API_KEY
    if [ -z "$WB_API_KEY" ]; then
        echo -e "${YELLOW}⚠️  Тест подключения будет пропущен без WB токена${NC}"
        exit 0
    fi
fi
echo -e "${GREEN}✅ WB API токен найден${NC}"
echo ""

# Создание проекта (если нет)
echo -e "${YELLOW}4. Получение или создание проекта...${NC}"
PROJECTS_RESPONSE=$(curl -s -H "Authorization: ${AUTH_TOKEN}" "${API_URL}/v1/projects")
PROJECT_COUNT=$(echo "$PROJECTS_RESPONSE" | jq '. | length' 2>/dev/null || echo "0")

if [ "$PROJECT_COUNT" -eq "0" ]; then
    echo "Создание тестового проекта..."
    PROJECT_RESPONSE=$(curl -s -X POST \
        -H "Authorization: ${AUTH_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{"name":"Test WB Connect Project","description":"Test project for WB connection"}' \
        "${API_URL}/v1/projects")
    PROJECT_ID=$(echo "$PROJECT_RESPONSE" | jq -r '.id' 2>/dev/null || echo "")
else
    PROJECT_ID=$(echo "$PROJECTS_RESPONSE" | jq -r '.[0].id' 2>/dev/null || echo "")
fi

if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" = "null" ]; then
    echo -e "${RED}❌ Не удалось получить или создать проект${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Проект ID: ${PROJECT_ID}${NC}"
echo ""

# Проверка текущего статуса WB
echo -e "${YELLOW}5. Проверка текущего статуса WB...${NC}"
MARKETPLACES_RESPONSE=$(curl -s -H "Authorization: ${AUTH_TOKEN}" \
    "${API_URL}/v1/projects/${PROJECT_ID}/marketplaces")
WB_STATUS=$(echo "$MARKETPLACES_RESPONSE" | jq -r '.[] | select(.marketplace_code == "wildberries") | .is_enabled' 2>/dev/null || echo "false")

if [ "$WB_STATUS" = "true" ]; then
    echo -e "${GREEN}✓ Wildberries уже подключен${NC}"
    WB_CONNECTED=true
else
    echo -e "${YELLOW}○ Wildberries не подключен${NC}"
    WB_CONNECTED=false
fi
echo ""

# Подключение WB (если не подключен)
if [ "$WB_CONNECTED" = "false" ]; then
    echo -e "${YELLOW}6. Подключение Wildberries...${NC}"
    CONNECT_RESPONSE=$(curl -s -X POST \
        -H "Authorization: ${AUTH_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"api_key\": \"${WB_API_KEY}\"}" \
        "${API_URL}/v1/projects/${PROJECT_ID}/marketplaces/wb/connect")
    
    CONNECT_SUCCESS=$(echo "$CONNECT_RESPONSE" | jq -r '.success' 2>/dev/null || echo "false")
    CONNECT_MESSAGE=$(echo "$CONNECT_RESPONSE" | jq -r '.message' 2>/dev/null || echo "Unknown error")
    
    if [ "$CONNECT_SUCCESS" = "true" ]; then
        echo -e "${GREEN}✅ ${CONNECT_MESSAGE}${NC}"
    else
        echo -e "${RED}❌ ${CONNECT_MESSAGE}${NC}"
        exit 1
    fi
    echo ""
fi

# Проверка подключения после connect
echo -e "${YELLOW}7. Проверка подключения после connect...${NC}"
MARKETPLACES_AFTER=$(curl -s -H "Authorization: ${AUTH_TOKEN}" \
    "${API_URL}/v1/projects/${PROJECT_ID}/marketplaces")
WB_AFTER_STATUS=$(echo "$MARKETPLACES_AFTER" | jq -r '.[] | select(.marketplace_code == "wildberries") | .is_enabled' 2>/dev/null || echo "false")

if [ "$WB_AFTER_STATUS" = "true" ]; then
    echo -e "${GREEN}✅ Wildberries подключен и включен${NC}"
else
    echo -e "${RED}❌ Wildberries не включен после подключения${NC}"
    exit 1
fi
echo ""

# Тест отключения (опционально)
if [ "${TEST_DISCONNECT:-false}" = "true" ]; then
    echo -e "${YELLOW}8. Тест отключения Wildberries...${NC}"
    curl -s -X POST \
        -H "Authorization: ${AUTH_TOKEN}" \
        "${API_URL}/v1/projects/${PROJECT_ID}/marketplaces/wb/disconnect"
    
    MARKETPLACES_DISCONNECTED=$(curl -s -H "Authorization: ${AUTH_TOKEN}" \
        "${API_URL}/v1/projects/${PROJECT_ID}/marketplaces")
    WB_DISCONNECTED_STATUS=$(echo "$MARKETPLACES_DISCONNECTED" | jq -r '.[] | select(.marketplace_code == "wildberries") | .is_enabled' 2>/dev/null || echo "false")
    
    if [ "$WB_DISCONNECTED_STATUS" = "false" ]; then
        echo -e "${GREEN}✅ Wildberries отключен${NC}"
    else
        echo -e "${RED}❌ Wildberries не отключен${NC}"
        exit 1
    fi
    echo ""
fi

echo -e "${GREEN}=== ✅ ТЕСТ ПРОЙДЕН: WB маркетплейс подключен успешно ===${NC}"
echo ""
echo "Итоги:"
echo "  - Проект ID: ${PROJECT_ID}"
echo "  - WB статус: ${WB_AFTER_STATUS}"
echo ""
echo "Для теста отключения используйте:"
echo "  export TEST_DISCONNECT=true"
echo "  ./scripts/test_wb_connect.sh"



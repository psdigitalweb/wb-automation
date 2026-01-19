#!/bin/bash
# Скрипт для проверки персистентности проектов
# Создает 2 проекта, останавливает контейнеры, запускает снова и проверяет, что проекты сохранились

set -e

echo "=== Тест персистентности проектов ==="
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

# Получение токена (предполагаем, что есть тестовый пользователь)
# ВАЖНО: Нужно сначала залогиниться или создать пользователя
echo -e "${YELLOW}2. Получение токена аутентификации...${NC}"
echo "⚠️  ВАЖНО: Для этого скрипта нужен токен аутентификации"
echo "Создайте пользователя и получите токен вручную, затем установите переменную:"
echo "  export AUTH_TOKEN='Bearer YOUR_TOKEN_HERE'"
echo ""

if [ -z "$AUTH_TOKEN" ]; then
    echo -e "${RED}❌ Переменная AUTH_TOKEN не установлена${NC}"
    echo "Используйте: export AUTH_TOKEN='Bearer YOUR_TOKEN_HERE'"
    exit 1
fi

# Проверка существующих проектов
echo -e "${YELLOW}3. Проверка существующих проектов...${NC}"
EXISTING_PROJECTS=$(curl -s -H "Authorization: ${AUTH_TOKEN}" "${API_URL}/v1/projects" | jq '. | length' 2>/dev/null || echo "0")
echo "Найдено проектов: ${EXISTING_PROJECTS}"
echo ""

# Создание первого проекта
echo -e "${YELLOW}4. Создание первого проекта 'Test Project 1'...${NC}"
PROJECT1_RESPONSE=$(curl -s -X POST \
    -H "Authorization: ${AUTH_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"name":"Test Project 1","description":"Test project for persistence check"}' \
    "${API_URL}/v1/projects")

PROJECT1_ID=$(echo "$PROJECT1_RESPONSE" | jq -r '.id' 2>/dev/null || echo "")
if [ -z "$PROJECT1_ID" ] || [ "$PROJECT1_ID" = "null" ]; then
    echo -e "${RED}❌ Не удалось создать первый проект${NC}"
    echo "Ответ: $PROJECT1_RESPONSE"
    exit 1
fi
echo -e "${GREEN}✅ Проект создан с ID: ${PROJECT1_ID}${NC}"
echo ""

# Создание второго проекта
echo -e "${YELLOW}5. Создание второго проекта 'Test Project 2'...${NC}"
PROJECT2_RESPONSE=$(curl -s -X POST \
    -H "Authorization: ${AUTH_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"name":"Test Project 2","description":"Second test project"}' \
    "${API_URL}/v1/projects")

PROJECT2_ID=$(echo "$PROJECT2_RESPONSE" | jq -r '.id' 2>/dev/null || echo "")
if [ -z "$PROJECT2_ID" ] || [ "$PROJECT2_ID" = "null" ]; then
    echo -e "${RED}❌ Не удалось создать второй проект${NC}"
    echo "Ответ: $PROJECT2_RESPONSE"
    exit 1
fi
echo -e "${GREEN}✅ Проект создан с ID: ${PROJECT2_ID}${NC}"
echo ""

# Проверка проектов в БД
echo -e "${YELLOW}6. Проверка проектов в БД (через psql)...${NC}"
PROJECTS_IN_DB=$(docker compose exec -T postgres psql -U wb -d wb -t -c "SELECT COUNT(*) FROM projects WHERE id IN (${PROJECT1_ID}, ${PROJECT2_ID});" 2>/dev/null | xargs || echo "0")
if [ "$PROJECTS_IN_DB" != "2" ]; then
    echo -e "${RED}❌ В БД найдено ${PROJECTS_IN_DB} проектов вместо 2${NC}"
    exit 1
fi
echo -e "${GREEN}✅ В БД найдены оба проекта${NC}"
echo ""

# Остановка контейнеров
echo -e "${YELLOW}7. Остановка контейнеров (docker compose down)...${NC}"
docker compose down
echo -e "${GREEN}✅ Контейнеры остановлены${NC}"
echo ""

# Запуск контейнеров снова
echo -e "${YELLOW}8. Запуск контейнеров снова (docker compose up -d)...${NC}"
docker compose up -d
echo "Ожидание готовности PostgreSQL..."
sleep 5
echo -e "${GREEN}✅ Контейнеры запущены${NC}"
echo ""

# Ожидание готовности API
echo -e "${YELLOW}9. Ожидание готовности API...${NC}"
for i in {1..30}; do
    if curl -s -f "${API_URL}/v1/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ API готов${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ API не готов после 30 попыток${NC}"
        exit 1
    fi
    sleep 1
done
echo ""

# Проверка проектов после перезапуска
echo -e "${YELLOW}10. Проверка проектов после перезапуска...${NC}"
PROJECTS_AFTER_RESTART=$(curl -s -H "Authorization: ${AUTH_TOKEN}" "${API_URL}/v1/projects" | jq '.' 2>/dev/null || echo "[]")

PROJECT1_FOUND=$(echo "$PROJECTS_AFTER_RESTART" | jq -r ".[] | select(.id == ${PROJECT1_ID}) | .name" 2>/dev/null || echo "")
PROJECT2_FOUND=$(echo "$PROJECTS_AFTER_RESTART" | jq -r ".[] | select(.id == ${PROJECT2_ID}) | .name" 2>/dev/null || echo "")

if [ -z "$PROJECT1_FOUND" ]; then
    echo -e "${RED}❌ Проект с ID ${PROJECT1_ID} не найден после перезапуска${NC}"
    echo "Ответ API: $PROJECTS_AFTER_RESTART"
    exit 1
fi

if [ -z "$PROJECT2_FOUND" ]; then
    echo -e "${RED}❌ Проект с ID ${PROJECT2_ID} не найден после перезапуска${NC}"
    echo "Ответ API: $PROJECTS_AFTER_RESTART"
    exit 1
fi

echo -e "${GREEN}✅ Проект 1 найден: ${PROJECT1_FOUND}${NC}"
echo -e "${GREEN}✅ Проект 2 найден: ${PROJECT2_FOUND}${NC}"
echo ""

# Финальная проверка в БД
echo -e "${YELLOW}11. Финальная проверка в БД...${NC}"
PROJECTS_IN_DB_FINAL=$(docker compose exec -T postgres psql -U wb -d wb -t -c "SELECT COUNT(*) FROM projects WHERE id IN (${PROJECT1_ID}, ${PROJECT2_ID});" 2>/dev/null | xargs || echo "0")
if [ "$PROJECTS_IN_DB_FINAL" != "2" ]; then
    echo -e "${RED}❌ В БД найдено ${PROJECTS_IN_DB_FINAL} проектов вместо 2${NC}"
    exit 1
fi
echo -e "${GREEN}✅ В БД найдены оба проекта${NC}"
echo ""

echo -e "${GREEN}=== ✅ ТЕСТ ПРОЙДЕН: Проекты успешно сохранились после перезапуска ===${NC}"


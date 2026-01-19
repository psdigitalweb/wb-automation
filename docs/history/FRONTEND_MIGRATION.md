# Миграция фронтенда на мультипроектную систему

## Измененные файлы

### Новые файлы

1. **lib/auth.ts** - Управление токенами и пользователем в localStorage
2. **lib/apiClient.ts** - API клиент с автоматической обработкой токенов и refresh
3. **components/Topbar.tsx** - Верхняя панель с селектором проектов
4. **components/Topbar.css** - Стили для Topbar
5. **app/page.tsx** - Страница логина (публичная)
6. **app/app/layout.tsx** - Layout для авторизованной части приложения
7. **app/app/projects/page.tsx** - Список проектов пользователя
8. **app/app/project/[projectId]/dashboard/page.tsx** - Dashboard проекта (обновленный)
9. **app/app/project/[projectId]/marketplaces/page.tsx** - Список маркетплейсов проекта
10. **app/app/project/[projectId]/marketplaces/[slug]/settings/page.tsx** - Настройки маркетплейса
11. **app/app/project/[projectId]/members/page.tsx** - Участники проекта
12. **app/app/project/[projectId]/stocks/page.tsx** - Остатки (обновлено)
13. **app/app/project/[projectId]/supplier-stocks/page.tsx** - Остатки поставщика (обновлено)
14. **app/app/project/[projectId]/prices/page.tsx** - Цены (обновлено)
15. **app/app/project/[projectId]/frontend-prices/page.tsx** - Цены фронта (обновлено)
16. **app/app/project/[projectId]/articles-base/page.tsx** - База артикулов (обновлено)
17. **app/app/project/[projectId]/rrp-snapshots/page.tsx** - RRP снимки (обновлено)

### Измененные файлы

1. **app/globals.css** - Добавлены стили для login страницы и app layout

## Структура роутов

### Публичные роуты
- `/` - Страница логина

### Авторизованные роуты (требуют токен)
- `/app/projects` - Список проектов
- `/app/project/[projectId]/dashboard` - Dashboard проекта
- `/app/project/[projectId]/marketplaces` - Маркетплейсы проекта
- `/app/project/[projectId]/marketplaces/[slug]/settings` - Настройки маркетплейса
- `/app/project/[projectId]/members` - Участники проекта
- `/app/project/[projectId]/stocks` - Остатки
- `/app/project/[projectId]/supplier-stocks` - Остатки поставщика
- `/app/project/[projectId]/prices` - Цены
- `/app/project/[projectId]/frontend-prices` - Цены фронта
- `/app/project/[projectId]/articles-base` - База артикулов
- `/app/project/[projectId]/rrp-snapshots` - RRP снимки

## Особенности реализации

### Авторизация
- Токены хранятся в localStorage
- Автоматический refresh при 401 ошибке
- Redirect на `/` при отсутствии токена

### Topbar
- Отображается на всех страницах `/app/*`
- Селектор проектов с автоматической навигацией
- Кнопка создания нового проекта
- Email пользователя и кнопка Logout

### Dashboard
- Проверка enabled статуса WB маркетплейса
- Кнопки ingestion отключены если WB не enabled
- Сообщение с ссылкой на настройки маркетплейсов

### Настройки маркетплейсов
- Для WB: форма с полями (token, base_url, timeout)
- Для остальных: JSON editor
- Маскирование секретов: если backend возвращает "***", показываем пустое поле с placeholder
- При сохранении "***" не перезатирает значение

### API Client
- Автоматическое добавление Authorization header
- Обработка 401 с попыткой refresh
- Redirect на `/` при неудачном refresh

## Запуск в Docker

Изменения не требуют изменений в `docker-compose.yml`. Просто перезапустите frontend контейнер:

```bash
docker compose restart frontend
```

Или пересоберите если нужно:

```bash
docker compose up -d --build frontend
```

## Миграция данных

Старые страницы (`/stocks`, `/prices`, и т.д.) остаются на месте, но не используются в новой структуре. Их можно удалить после проверки работоспособности новой системы.

## Тестирование

1. Откройте http://localhost:3000
2. Войдите с существующими учетными данными
3. Создайте проект или выберите существующий
4. Проверьте работу всех страниц
5. Проверьте настройки маркетплейсов
6. Проверьте управление участниками проекта





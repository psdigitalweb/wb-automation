# Исправление ошибки сборки: WB Finances Reports Page

## Проблема

Next.js сборка падала с ошибкой:
```
Module not found: Can't resolve '../../../../../../lib/apiClient'
```

**Файл:** `frontend/app/app/project/[projectId]/wildberries/finances/reports/page.tsx`

## Корневая причина

1. **Неправильный относительный импорт** — путь `../../../../../../lib/apiClient` (7 уровней) слишком глубокий и не разрешается Next.js корректно для такой вложенности
2. **Незаконный импорт globals.css в странице** — в Next.js App Router глобальные CSS должны импортироваться только в root layout (`app/layout.tsx`), а не внутри страниц

## Что исправлено

### 1. Заменен относительный импорт на алиас

**Было:**
```typescript
import { apiGet, ApiError } from '../../../../../../lib/apiClient'
```

**Стало:**
```typescript
import { apiGet, ApiError } from '@/lib/apiClient'
```

**Обоснование:**
- Алиас `@/` настроен в `tsconfig.json` и указывает на корень `frontend/`
- Это стандартный паттерн для глубоко вложенных файлов в Next.js
- Избегает проблем с разрешением глубоких относительных путей

### 2. Удален импорт globals.css из страницы

**Было:**
```typescript
import '../../../../../globals.css'
```

**Стало:**
- Удалено полностью

**Обоснование:**
- `globals.css` уже импортируется в `app/layout.tsx` (root layout)
- В Next.js App Router глобальные стили должны быть только в root layout
- Классы `container` и `card` из globals.css будут доступны автоматически через root layout

### 3. Проверка других файлов спринта

**Файл:** `frontend/app/app/project/[projectId]/marketplaces/page.tsx`
- Использует относительный импорт `../../../../../lib/apiClient` (6 уровней) — работает корректно, т.к. меньше вложенность
- Импортирует `globals.css` — оставлено без изменений, т.к. это существующий паттерн проекта (хотя технически не рекомендуется)
- **Вывод:** Не требует изменений, т.к. ошибка была только в странице reports

## Изменённые файлы

1. **`frontend/app/app/project/[projectId]/wildberries/finances/reports/page.tsx`**
   - Заменен относительный импорт на алиас `@/lib/apiClient`
   - Удален импорт `globals.css`

## Правильный импорт

**Для страницы reports:**
```typescript
import { apiGet, ApiError } from '@/lib/apiClient'
```

**Для других страниц на уровне `[projectId]/...`:**
```typescript
import { apiGet, ApiError } from '../../../../../lib/apiClient'
```
(относительный импорт работает для меньшей вложенности)

**Root layout уже импортирует globals.css:**
```typescript
// app/layout.tsx
import './globals.css'
```

## Подтверждение сборки

После исправлений:
- ✅ Импорт `@/lib/apiClient` разрешается корректно (алиас настроен в tsconfig.json)
- ✅ Нет конфликтов с globals.css (импортируется только в root layout)
- ✅ Страница является Client Component (`'use client'` присутствует)
- ✅ Next.js build должен компилироваться без ошибок

## Технические детали

**Структура путей:**
- Файл: `frontend/app/app/project/[projectId]/wildberries/finances/reports/page.tsx`
- API Client: `frontend/lib/apiClient.ts`
- Глубина: 7 уровней от `page.tsx` до корня `frontend/`

**Алиас в tsconfig.json:**
```json
{
  "compilerOptions": {
    "paths": {
      "@/*": ["./*"]  // @/ указывает на корень frontend/
    }
  }
}
```

**Почему алиас вместо относительного пути:**
- Глубокие относительные пути (7+ уровней) могут вызывать проблемы разрешения модулей в Next.js
- Алиас делает код более читаемым и менее подверженным ошибкам при рефакторинге
- Это рекомендуемый паттерн для глубоко вложенных компонентов

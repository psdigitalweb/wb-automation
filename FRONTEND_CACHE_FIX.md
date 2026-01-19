# Исправление фронтенд-кеширования для project scoping

## Проблема

Проекты показывали одинаковые данные из-за проблем с кешированием на фронтенде:

1. **Next.js автоматически кеширует fetch** в App Router (по умолчанию `fetch` использует кеш)
2. **useEffect не зависел от projectId** - компоненты не перезагружали данные при смене проекта
3. **Состояние не сбрасывалось** при смене projectId - данные из предыдущего проекта оставались

## Почему это давало одинаковые данные

### Проблема 1: Next.js fetch caching

Next.js App Router кеширует все `fetch` запросы по умолчанию. Это означает, что:
- При переходе из проекта A в проект B, Next.js возвращал кешированный ответ для URL `/v1/stocks/latest`
- Даже если URL теперь включает `projectId`, кеш мог быть общим для разных путей

**Решение:** Отключить кеширование для data endpoints через `cache: 'no-store'`

### Проблема 2: useEffect зависимости

В `stocks/page.tsx` и `prices/page.tsx`:

```typescript
useEffect(() => {
  loadData()
}, [offset]) // ❌ projectId не в зависимостях!
```

Когда пользователь переходит из проекта A в проект B:
- `projectId` меняется, но `useEffect` не перезапускается
- `loadData()` все еще использует старый `projectId` из замыкания или показывает кешированные данные

**Решение:** Добавить `projectId` в зависимости `useEffect`

### Проблема 3: Состояние не сбрасывается

При смене `projectId`:
- `data`, `total`, `offset` оставались от предыдущего проекта
- Пока новые данные загружаются, пользователь видит старые данные

**Решение:** Сбрасывать состояние при смене `projectId`

## Исправления

### 1. Отключение кеширования в apiClient.ts

**Файл:** `frontend/lib/apiClient.ts`

**Изменение:** Добавлен `cache: 'no-store'` для GET запросов к data endpoints:

```typescript
// Disable Next.js caching for data endpoints
const isDataEndpoint = url.match(/\/v1\/(projects\/\d+\/)?(stocks|prices|dashboard)/)
if (options.method === 'GET' || !options.method) {
  if (isDataEndpoint) {
    fetchOptions.cache = 'no-store' as RequestCache
  }
}
```

**Почему:** Next.js по умолчанию кеширует все `fetch` запросы. Для data endpoints нужно отключить кеш, чтобы получать свежие данные для каждого проекта.

### 2. Добавление projectId в зависимости useEffect

**Файлы:**
- `frontend/app/app/project/[projectId]/stocks/page.tsx`
- `frontend/app/app/project/[projectId]/prices/page.tsx`

**Изменение:**
```typescript
useEffect(() => {
  loadData()
}, [offset, projectId]) // ✅ Добавлен projectId
```

**Почему:** `useEffect` должен перезапускаться при смене `projectId`, чтобы загружать данные для нового проекта.

### 3. Сброс состояния при смене projectId

**Файлы:**
- `frontend/app/app/project/[projectId]/stocks/page.tsx`
- `frontend/app/app/project/[projectId]/prices/page.tsx`
- `frontend/app/app/project/[projectId]/dashboard/page.tsx`

**Изменение:**
```typescript
// Reset state when projectId changes to prevent showing data from previous project
useEffect(() => {
  setData([])
  setOffset(0)
  setTotal(0)
  setLoading(true)
}, [projectId])
```

**Почему:** При смене проекта нужно сразу очистить данные, чтобы пользователь не видел данные из предыдущего проекта во время загрузки.

## Тестирование

### Тест 1: Проверка отсутствия кеширования

1. Откройте DevTools → Network
2. Откройте проект A → Stocks
3. Перейдите в проект B → Stocks
4. Проверьте, что запросы не из кеша (Status 200, не from cache)

### Тест 2: Проверка сброса состояния

1. Откройте проект A → Stocks (должны быть данные)
2. Перейдите в проект B → Stocks
3. Проверьте, что:
   - Таблица сразу пустая (не показывает данные из проекта A)
   - Загружаются данные проекта B

### Тест 3: Проверка зависимостей useEffect

1. Откройте проект A → Stocks
2. Проверьте DevTools → Console на наличие запросов к `/v1/projects/{projectA_id}/stocks/latest`
3. Перейдите в проект B → Stocks
4. Проверьте, что есть новый запрос к `/v1/projects/{projectB_id}/stocks/latest`

## Измененные файлы

1. `frontend/lib/apiClient.ts` - добавлен `cache: 'no-store'` для data endpoints
2. `frontend/app/app/project/[projectId]/stocks/page.tsx` - добавлен сброс состояния и `projectId` в зависимости
3. `frontend/app/app/project/[projectId]/prices/page.tsx` - добавлен сброс состояния и `projectId` в зависимости
4. `frontend/app/app/project/[projectId]/dashboard/page.tsx` - добавлен сброс состояния

## Важно

1. **Next.js fetch caching** работает только в Server Components, но мы используем Client Components (`'use client'`). Однако Next.js все равно может кешировать запросы через HTTP cache headers.
2. **Cache: 'no-store'** отключает все уровни кеширования для fetch запроса
3. **Сброс состояния** критичен для хорошего UX - пользователь сразу видит, что данные загружаются для нового проекта
4. **useEffect зависимости** должны включать все переменные, которые используются внутри эффекта

## Альтернативное решение (если нужно)

Если нужно сохранить кеширование, но по projectId:

```typescript
// В apiClient.ts можно использовать revalidation вместо no-store
fetchOptions.next = { revalidate: 0 } // Для Server Components
```

Но для Client Components с динамическими данными лучше использовать `cache: 'no-store'`.



# Порядок применения миграций Alembic

## Полная цепочка миграций

Миграции применяются в следующем порядке (от базовых к более сложным):

```
<base>
  └─> a77217f699d1 (Initial migration)
       └─> e1dcde5e611e (Add brand to products)
            └─> 0f69aa9a434f (Add v_products_latest_price view)
                 └─> 6089711fc16b (Add warehouses and stock snapshots)
                      └─> a0afa471d2a0 (Add v_products_latest_stock view)
                           └─> fc62982c8480 (Add supplier_stock_snapshots)
                                └─> 213c70612608 (Add raw jsonb to price_snapshots)
                                     └─> 2a8757976d5a (Add frontend_catalog_price_snapshots)
                                          └─> ea2d9ac02904 (Add app_settings table)
                                               └─> a2b730f4e786 (Fix app_settings table)
                                                    └─> b1c2d3e4f5a6 (Add rrp_snapshots)
                                                         └─> c2d3e4f5a6b7 (Add v_article_base view)
                                                              └─> 0fd96b01e954 (Fix v_article_base)
                                                                   └─> optimize_v_article_base (Optimize view)
                                                                        └─> add_product_details (Add product details)
                                                                             └─> add_users_table (Add users)
                                                                                  └─> add_refresh_tokens (Add refresh tokens)
                                                                                       └─> add_projects_tables (Add projects)
                                                                                            └─> add_marketplaces_tables
                                                                                                 └─> add_project_id_to_data (Add project_id to data tables)
                                                                                                      └─> backfill_project_id_not_null (Backfill and make NOT NULL)
                                                                                                           └─> 946d21840243 (add_unique_products_project_nm_id)
                                                                                                                └─> e373f63d276a (add_api_token_encrypted) ─┐
                                                                                                 └─> ea2d9ac02904 (Add app_settings table)                  │
                                                                                                      └─> a2b730f4e786 (Fix app_settings) ─────────────────┘
                                                                                                           └─> 670ed0736bfa (merge_heads) (HEAD)
```

## Описание миграций

### Базовые таблицы

1. **a77217f699d1** - Initial migration
   - Создает таблицы: `products`, `price_snapshots`
   - Базовые индексы

2. **e1dcde5e611e** - Add brand to products
   - Добавляет поля в `products`: title, brand, subject_name, prices, ratings, sizes, colors, pics, raw
   - Индексы для brand и subject_name

3. **0f69aa9a434f** - Add v_products_latest_price view
   - SQL VIEW для получения последних цен товаров

4. **6089711fc16b** - Add warehouses and stock snapshots
   - Таблицы: `wb_warehouses`, `stock_snapshots`

5. **a0afa471d2a0** - Add v_products_latest_stock view
   - SQL VIEW для получения последних остатков товаров

6. **fc62982c8480** - Add supplier_stock_snapshots
   - Таблица для остатков поставщика из WB Statistics API

7. **213c70612608** - Add raw jsonb to price_snapshots
   - Добавляет поле `raw` (JSONB) в `price_snapshots`

8. **2a8757976d5a** - Add frontend_catalog_price_snapshots
   - Таблица для хранения цен с фронта WB

### Настройки и данные 1С

9. **ea2d9ac02904** - Add app_settings table
   - Таблица для хранения настроек приложения

10. **a2b730f4e786** - Fix app_settings table
    - Исправление дублирования таблицы app_settings

11. **b1c2d3e4f5a6** - Add rrp_snapshots table
    - Таблица для хранения данных из 1С XML (РРЦ и остатки)

### Витрина артикулов

12. **c2d3e4f5a6b7** - Add v_article_base view
    - SQL VIEW для единой витрины артикулов

13. **0fd96b01e954** - Fix v_article_base full outer join
    - Исправление VIEW с использованием UNION

14. **optimize_v_article_base** - Optimize v_article_base performance
    - Оптимизация производительности VIEW

### Детали продуктов

15. **add_product_details** - Add product details fields
    - Добавляет поля: subject_id, description, dimensions, characteristics, created_at_api, need_kiz

### Авторизация

16. **add_users_table** - Add users table for authentication
    - Таблица пользователей для JWT авторизации

17. **add_refresh_tokens** - Add refresh_tokens table
    - Таблица для хранения refresh токенов (опционально, для отзыва)

### Мультипроектная модель

18. **add_projects_tables** - Add projects and project_members tables
    - Таблицы для проектов и участников проектов
    - Роли: owner, admin, member, viewer

### Маркетплейсы

19. **add_marketplaces_tables** - Add marketplaces and project_marketplaces tables
    - Справочник маркетплейсов
    - Связь проектов с маркетплейсами
    - Seed-данные: Wildberries, Ozon, Яндекс.Маркет, СберМегаМаркет

### Project Scoping

20. **add_project_id_to_data** - Add project_id to data tables
    - Добавляет project_id (nullable) в products, stock_snapshots, price_snapshots
    - Создает foreign keys и индексы

21. **backfill_project_id_not_null** - Backfill project_id and make NOT NULL
    - Заполняет project_id для существующих данных
    - Создает "Legacy" проект если нужно
    - Делает project_id NOT NULL

22. **946d21840243** (add_unique_products_project_nm_id) - Add unique constraint (project_id, nm_id) to products
    - Удаляет старый UNIQUE(nm_id)
    - Добавляет UNIQUE(project_id, nm_id) для поддержки одинаковых nm_id в разных проектах

23. **e373f63d276a** (add_api_token_encrypted) - Add api_token_encrypted field to project_marketplaces
    - Добавляет колонку для хранения зашифрованных токенов
    - Мигрирует существующие токены из settings_json

24. **670ed0736bfa** (merge_heads) - Merge heads: a2b730f4e786 and e373f63d276a (HEAD)
    - Объединяет две ветки миграций в один линейный HEAD
    - Не содержит изменений схемы (только объединяет историю)

## Применение миграций

### С нуля

```bash
# Применить все миграции
docker compose exec api alembic upgrade head
```

### Проверка состояния

```bash
# Текущая версия
docker compose exec api alembic current

# История
docker compose exec api alembic history

# Показать SQL для миграции
docker compose exec api alembic upgrade head --sql
```

### Откат миграций

```bash
# Откатить последнюю миграцию
docker compose exec api alembic downgrade -1

# Откатить до конкретной версии
docker compose exec api alembic downgrade <revision_id>

# Откатить все миграции (ОСТОРОЖНО!)
docker compose exec api alembic downgrade base
```

## Создание новой миграции

```bash
# Автоматическое определение изменений
docker compose exec api alembic revision --autogenerate -m "description"

# Ручное создание
docker compose exec api alembic revision -m "description"
```

## Важные замечания

1. **Не изменяйте существующие миграции** после применения в продакшене
2. **Всегда проверяйте миграции** перед применением в продакшене
3. **Делайте резервные копии** перед применением миграций в продакшене
4. **Тестируйте откат** миграций перед применением
5. **Используйте транзакции** для критичных миграций

## Зависимости между миграциями

- `add_projects_tables` зависит от `add_users_table` (foreign key на users.id)
- `add_marketplaces_tables` зависит от `add_projects_tables` (foreign key на projects.id)
- `add_refresh_tokens` зависит от `add_users_table` (foreign key на users.id)
- Все VIEWs зависят от соответствующих таблиц

## Seed-данные

Автоматически заполняются при применении миграций:
- **add_marketplaces_tables**: 4 маркетплейса (Wildberries, Ozon, Яндекс.Маркет, СберМегаМаркет)

Другие seed-данные можно добавить через:
- API эндпоинты (регистрация пользователей, создание проектов)
- SQL скрипты в миграциях
- Отдельные скрипты инициализации


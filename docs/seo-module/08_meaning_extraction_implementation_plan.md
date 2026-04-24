# Meaning Extraction MVP — Implementation Plan (WB SEO Module)

Дата: 2026-04-20

Цель этого документа: зафиксировать **контролируемый, поэтапный** план реализации Meaning Extraction MVP в существующем SEO runtime **без изменения архитектуры**, **без matcher/scoring redesign**, **без generation**, **без LLM/embeddings**, и с тестами/чекпоинтами на каждом шаге.

---

## A. Scope итерации

### Входит в Meaning Extraction MVP

1) **Явные сущности (structured canonical objects):**
   - `CategoryMeaning` (per project × category)
   - `ProductProjection` (per project × SKU)
   - `QueryMeaning` (per project × category × query/cluster)

2) **Детерминированные builder’ы** (rule-based, без LLM/embeddings):
   - `build_category_meaning(...)` из product-side evidence категории.
   - `build_product_projection(...)` из SKU evidence + `CategoryMeaning` (включая cold-start expressive baseline).
   - `formalize_query_meaning(...)` как слой поверх уже существующего query pipeline (profiles/hybrid).

3) **Минимальная runtime-видимость** (debug exposure):
   - debug endpoint или debug-tab, который позволяет получить payload этих 3 сущностей и увидеть explainable decisions.

4) **Тесты и регрессия:**
   - unit-тесты на result types + builders.
   - регрессионная проверка, что существующий query pipeline / scoring preparation не сломан.

### Не входит (явные границы)

- Matcher (любая реализация сравнения `ProductProjection` ↔ `QueryMeaning`).
- Переписывание / редизайн scoring или scoring preparation (только additive changes вокруг, если потребуется для debug/типов).
- Generation (и любые интеграции provider’ов, включая OpenRouter).
- Reviews-first логика; интеграция текстов reviews как обязательного источника meaning.
- Manual overrides как feature (можно оставить только как **явно отложенное** расширение).
- Embeddings/semantic retrieval/LLM (включая sentence-transformers semantic clustering experiment).
- UI.
- “Research / spike” как основной путь: только production-ориентированная реализация с тестами.

---

## B. Source of truth

### Docs (использованы как source of truth)

- `docs/seo-module/01_architecture.md`
- `docs/seo-module/03_category_meaning_spec.md`
- `docs/seo-module/04_product_projection_spec.md`
- `docs/seo-module/05_query_meaning_spec.md`
- `docs/seo-module/06_meaning_extraction_basis.md`
- `docs/seo-module/07_meaning_extraction_plan.md`

### Runtime code / modules (просмотрено для привязки к текущей системе)

Query pipeline / debug / scoring preparation:
- `src/app/services/seo/query_pipeline/__init__.py`
- `src/app/services/seo/query_pipeline/profiles.py`
- `src/app/services/seo/query_pipeline/diagnostics.py`
- `src/app/services/seo/query_pipeline/semantic.py` (только как факт существования embedding-based эксперимента; **не использовать** в MVP)
- `src/app/services/seo/scoring/preparation.py`
- `src/app/routers/seo_query_pipeline_debug.py`
- `src/app/schemas/seo_query_pipeline_debug.py`

Products / evidence:
- `src/app/db_products.py` (schema intent)
- `src/app/services/seo/scoring/preparation.py` (реальный SQL чтения из `products`)

DB models (SEO tables):
- `src/app/models.py` (seo_query_* / seo_score_* / seo_sku_cluster_* skeleton)

Existing tests (паттерны и regression surface):
- `tests/seo_query_pipeline_test_helpers.py`
- `tests/test_seo_query_scoring_preparation.py`
- `tests/test_seo_query_pipeline_debug_api.py`
- (и другие `tests/test_seo_query_*.py` по query pipeline)

---

## C. Decomposition (подзадачи)

Ниже — разбиение на минимальные логические шаги. **Каждый шаг выполняется отдельно** с тестами и фиксируемым runtime/debug эффектом.

1) **Task 01 — Meaning result types / schemas / canonical objects**
2) **Task 02 — Category Meaning builder (product-side aggregation)**
3) **Task 03 — Product Projection builder (SKU → category space)**
4) **Task 04 — Query Meaning formalization (поверх query pipeline)**
5) **Task 05 — Debug/runtime exposure (meaning payloads)**
6) **Task 06 — Tests / regression checks / cleanup**

---

## D. Детализация подзадач (цель, файлы, output, тесты, done criteria)

### Task 01 — Meaning result types / schemas / canonical objects

**Цель**
- Ввести 3 сущности как явные canonical объекты, совместимые с архитектурой docs:
  - Functional + Expressive components
  - стабильная сериализация (`to_dict()`), versioning hooks (строка/число версии), explainability-friendly shape

**Файлы (планируется)**
- Create: `src/app/services/seo/meaning_extraction/__init__.py`
- Create: `src/app/services/seo/meaning_extraction/types.py`
- (опционально) Create: `src/app/schemas/seo_meaning_extraction_debug.py` (если debug payload будет отдельным endpoint’ом)
- Create: `tests/test_seo_meaning_types.py`

**Expected runtime output**
- Импортируемые типы/структуры (`CategoryMeaning`, `ProductProjection`, `QueryMeaning`) и стабильный JSON-like payload.

**Test / checkpoint**
- `pytest -q tests/test_seo_meaning_types.py`

**Критерий завершения**
- Типы существуют, сериализуются, и shape соответствует docs (functional/expressive, vibes/use_cases/attributes).

---

### Task 02 — Category Meaning builder (product-side aggregation)

**Цель**
- Детерминированно собрать `CategoryMeaning` из product evidence в `products`:
  - входы строго из подтверждённых runtime полей: `title`, `description`, `characteristics`, `sizes`, `colors`, `dimensions` (+ `subject_id` как category scope)
  - без reviews зависимости (degradation rule)
  - агрегирование “по множеству SKU” с фильтрацией выбросов

**MVP thresholds (минимальные deterministic пороги “повторяющихся паттернов”)**
- Определение “pattern support”:
  - `support_sku_count` = количество SKU в категории, где паттерн встречается хотя бы 1 раз (presence-based).
  - `support_share` = `support_sku_count / total_sku_count`.
- Базовый порог (по умолчанию):
  - `support_sku_count >= 3` **и** `support_share >= 0.15`.
- Малые категории (если `total_sku_count < 20`):
  - `support_sku_count >= 2` **и** `support_share >= 0.25`.
- Ограничение на вывод (чтобы MVP был контролируемым):
  - максимум `top_k = 20` значений на слот (product_types, use_cases, vibes),
  - максимум `top_k = 40` значений на attributes (если потребуется).
- Одинокие/редкие паттерны считаются выбросами и **не попадают** в `CategoryMeaning`.

**Файлы (планируется)**
- Create: `src/app/services/seo/meaning_extraction/category_meaning.py`
- Update: `src/app/services/seo/meaning_extraction/__init__.py` (экспорт builder)
- Create: `tests/test_seo_category_meaning_builder.py`
- (если понадобится) Create/Update: `tests/seo_query_pipeline_test_helpers.py` (добавить helper для seed products в категории; только additive)

**Expected runtime output**
- `build_category_meaning(session, project_id, category_id, ...) -> CategoryMeaning`
- В output явно присутствуют:
  - `functional.product_types/use_cases/attributes` (минимально непустой или explainably empty)
  - `expressive.vibes` как “категорийный prior” (может быть пустым, но слой должен существовать)

**Test / checkpoint**
- `pytest -q tests/test_seo_category_meaning_builder.py`

**Критерий завершения**
- Builder выдаёт стабильный `CategoryMeaning` на синтетических данных и **не читает** неподтверждённые поля.

---

### Task 03 — Product Projection builder (SKU → category space)

**Цель**
- Детерминированно построить `ProductProjection` для конкретного SKU:
  - functional: извлечение из SKU evidence и нормализация относительно осей `CategoryMeaning`
  - expressive: baseline = `CategoryMeaning.expressive` prior + (опционально) SKU signals из `title/description`
  - cold-start: если SKU expressive слабый → оставить prior

**MVP rule: weak vs strong SKU expressive signal**
- Expressive candidates извлекаются только из `title` и `description` (description = weak source).
- `strong_expressive_signal = True`, если выполняется хотя бы одно:
  1) найдены ≥ 2 expressive candidates в `title`, или
  2) найден ≥ 1 candidate в `title`, который пересекается с `CategoryMeaning.expressive.vibes` (category prior axis), или
  3) найдены ≥ 3 candidates суммарно (title+description) и хотя бы 1 из них из `title`.
- Иначе сигнал считается `weak_expressive_signal` и применяется cold-start fallback:
  - `ProductProjection.expressive.vibes = CategoryMeaning.expressive.vibes` (baseline),
  - SKU candidates (если есть) могут быть сохранены только как diagnostics/flags (не как override).

**Файлы (планируется)**
- Create: `src/app/services/seo/meaning_extraction/product_projection.py`
- Update: `src/app/services/seo/meaning_extraction/__init__.py`
- Create: `tests/test_seo_product_projection_builder.py`

**Expected runtime output**
- `build_product_projection(session, project_id, category_id, nm_id, category_meaning=...) -> ProductProjection`
- output содержит `functional` и `expressive`, и expresssive baseline реально применяется.

**Test / checkpoint**
- `pytest -q tests/test_seo_product_projection_builder.py`

**Критерий завершения**
- На тестовых SKU (с/без description/characteristics) видно:
  - functional извлекается детерминированно
  - expressive не ломается при пустых полях и корректно использует category prior

---

### Task 04 — Query Meaning formalization (поверх query pipeline)

**Цель**
- Ввести `QueryMeaning` как формализованный слой поверх существующего query pipeline:
  - не переписывать pipeline
  - не использовать product-side данные
  - маппинг из `ExtractedClusterProfile` / hybrid annotation outputs в canonical `QueryMeaning`
  - expressive intent ← (MVP) `language_markers` **как proxy для vibes**, без “semantic” embeddings

**Важно (MVP boundary)**
- `language_markers -> vibes` помечается как **MVP proxy mapping**, а не final expressive truth.
- Это временный слой формализации для того, чтобы `QueryMeaning` имел явную expressive часть без LLM/embeddings.

**Файлы (планируется)**
- Create: `src/app/services/seo/meaning_extraction/query_meaning.py`
- Update: `src/app/services/seo/meaning_extraction/__init__.py`
- Create: `tests/test_seo_query_meaning_formalization.py`

**Expected runtime output**
- `formalize_query_meaning(profile: ExtractedClusterProfile, ...) -> QueryMeaning`
- В output появляется явная структура `{functional{product_type,use_cases,attributes}, expressive{vibes}}`.

**Test / checkpoint**
- `pytest -q tests/test_seo_query_meaning_formalization.py`
- Regression: `pytest -q tests/test_seo_query_*`

**Критерий завершения**
- `QueryMeaning` создаётся из существующих профилей без изменения их extraction логики, и existing pipeline тесты не регрессируют.

---

### Task 05 — Debug/runtime exposure (meaning payloads)

**Цель**
- Добавить минимальный способ получить значения 3 сущностей для конкретного scope:
  - project_id, category_id, nm_id
  - cluster_key (или иной явный идентификатор query/profile) для получения **одного** `QueryMeaning`

**Файлы (планируется)**
- Create: `src/app/routers/seo_meaning_extraction_debug.py`
- Create: `src/app/schemas/seo_meaning_extraction_debug.py`
- Update: `src/app/main.py` или место регистрации роутеров (если требуется)
- Create: `tests/test_seo_meaning_extraction_debug_api.py`

**Expected runtime output (не раздувать endpoint)**
- Новый debug endpoint возвращает только:
  - `category_meaning`
  - `product_projection`
  - `query_meaning` (ровно один, по `cluster_key`/target)
  - минимальные flags (например: `weak_expressive_signal`, `used_category_prior`)

**Test / checkpoint**
- `pytest -q tests/test_seo_meaning_extraction_debug_api.py`

**Критерий завершения**
- Endpoint детерминированно возвращает payload; не требует новых data sources; не трогает scoring/matcher.

---

### Task 06 — Tests / regression checks / cleanup

**Цель**
- Убедиться, что meaning extraction не ломает существующий runtime и что MVP “закрывается” по тестам.

**Файлы (планируется)**
- Update: новые/существующие тесты (по необходимости).
- Update: `docs/seo-module/tasks/*` (если нужен фикс “что сделано”)

**Expected runtime output**
- Никаких изменений поведения существующих API, кроме добавления debug exposure.

**Test / checkpoint**
- Минимум:
  - `pytest -q tests/test_seo_meaning_types.py`
  - `pytest -q tests/test_seo_category_meaning_builder.py`
  - `pytest -q tests/test_seo_product_projection_builder.py`
  - `pytest -q tests/test_seo_query_meaning_formalization.py`
  - Regression: `pytest -q tests/test_seo_query_import_api.py tests/test_seo_query_pipeline_debug_api.py tests/test_seo_query_scoring_preparation.py`

**Критерий завершения**
- Все новые тесты проходят, и выбранный regression набор проходит без изменений expected behavior.

---

## E. Execution order (порядок выполнения и зависимости)

1) Task 01 (типы) — база для всех последующих шагов.
2) Task 02 (CategoryMeaning) — нужен как prior/baseline для ProductProjection.
3) Task 03 (ProductProjection) — использует Task 02.
4) Task 04 (QueryMeaning) — независим от product-side, но зависит от Task 01 типов.
5) Task 05 (debug exposure) — подключает результаты Tasks 02–04.
6) Task 06 (regression/cleanup) — финальная фиксация стабильности.

Зависимости:
- `ProductProjection` зависит от `CategoryMeaning`.
- `QueryMeaning` не зависит от product-side.
- Debug endpoint зависит от наличия builder’ов и их сериализации.

---

## F. Risks / boundaries

### Куда нельзя лезть (жёсткие границы)
- Не менять существующий query pipeline extraction (normalization/pruning/clustering/hybrid/profiles) как часть этого MVP.
- Не менять matcher/scoring и их контракт (включая `app/services/seo/scoring/*`) — только использовать как regression surface.
- Не включать `sentence_transformers` / embeddings / semantic clustering experiment в MVP meaning extraction.
- Не расширять активные product inputs за пределы подтверждённых call sites (см. `scoring/preparation.py` SQL).

### Сознательно откладывается
- Persist/cache meaning objects в БД (если понадобится — отдельная итерация с миграциями и жизненным циклом версий).
- Reviews enrichment (как усиление expressive) — только после того, как MVP стабилен без reviews.
- SKU clustering как downstream слой (placeholder уже существует; не трогаем).
- Manual overrides.

### Риски реализации
- **Производительность**: category aggregation по всем SKU может быть дорогой → MVP должен начинать с “безопасных лимитов/сэмплов” или с явной конфигурации (но не ломать корректность).
- **Стабильность shape**: важно не “расплываться” по структурам — всё через canonical types.
- **Expressive слой**: без reviews будет слабее; MVP должен корректно деградировать, но слой не должен пропасть.

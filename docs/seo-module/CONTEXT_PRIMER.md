# Context Primer — Entry point for AI agents

> Статус: **первая точка чтения для любого AI-агента**.
> Версия: v1 (2026-04-24). Этот документ отражает состояние репозитория на момент написания. Обновляется после закрытия каждой Phase.

---

## 0. Что это за репозиторий

**EcomCore** — внутренний инструмент для управления SEO-оптимизацией карточек товаров на Wildberries.

Основная бизнес-задача: для каждого SKU (товара) подобрать набор поисковых запросов, по которым карточка должна быть оптимизирована, чтобы эта карточка находила свою целевую аудиторию.

Ключевой тезис продукта (**homogenization-trap safeguard**): мы ищем не «самые денежные запросы категории», а **самые смысловые и вайбово-релевантные запросы для конкретного SKU**. Это то, что отличает нас от простых SEO-скраперов. См. `ROADMAP.md §10.4`.

---

## 1. Роль читающего агента

Если ты AI-агент (Codex / Claude / другой), и тебя подключили к этому репо — скорее всего ты пришёл реализовывать одну из фаз из `ROADMAP.md`. Дальнейшие действия:

1. Прочитать этот документ целиком.
2. Прочитать `AGENTS.md` (в корне репо) — правила работы.
3. Прочитать `ROADMAP.md` — понять, какая фаза активна.
4. Прочитать `phase<N>/PHASE_<N>_EXECUTION_PLAN.md` активной фазы.
5. Если задача про матчер / профили / guards — прочитать `CATEGORY_PROFILE_SPEC.md`.
6. Если задача про UI — прочитать `OPERATOR_WORKFLOW.md`.

Все эти документы лежат в `docs/seo-module/`.

После этого ты знаешь столько же, сколько автор документа. Не додумывай — спрашивай оператора.

---

## 2. Репо на высоком уровне

```
D:/Work/EcomCore/
├─ AGENTS.md                                       # ← правила работы агента
├─ docs/seo-module/
│  ├─ CONTEXT_PRIMER.md                           # ← этот файл
│  ├─ ROADMAP.md                                  # 5 фаз, текущий план
│  ├─ CATEGORY_PROFILE_SPEC.md                    # контракт профиля категории
│  ├─ OPERATOR_WORKFLOW.md                        # целевой operator UX
│  ├─ phase0/
│  │  ├─ PHASE_0_EXECUTION_PLAN.md                # 11 атомарных шагов backend-унификации
│  │  └─ TEST_PLAN.md                             # тестовый контракт Phase 0
│  ├─ 00_master_context.md ... 24_*.md            # ИСТОРИЯ (не source of truth, архив)
│  └─ implementation-plan/                        # отчёты об итерациях 1–2
├─ src/app/                                       # backend (FastAPI + SQLAlchemy)
│  ├─ main.py                                     # entry point
│  ├─ models.py                                   # ORM моделей ≈800 строк
│  ├─ routers/                                    # HTTP-эндпоинты
│  │  ├─ seo_*.py
│  │  └─ ...
│  ├─ schemas/                                    # Pydantic-схемы
│  ├─ services/seo/                               # ⭐ ЯДРО SEO-модуля
│  │  ├─ category_profile.py                      # loader CategoryProfile (см. SPEC)
│  │  ├─ category_bootstrap.py                    # сборка корпуса из CSV
│  │  ├─ query_meaning_matcher/                   # легаси матчер (matcher_v1)
│  │  │  ├─ matcher.py                            # ← literal-free facade, active path reads CategoryProfile
│  │  │  ├─ profile_matcher.py                    # ← profile-driven query matcher implementation
│  │  │  └─ _legacy/matcher.py                    # ← deprecated legacy matcher, isolated
│  │  ├─ matcher_v2/                              # ⭐ новый матчер
│  │  │  ├─ api.py                                # entry point
│  │  │  └─ stages/
│  │  │     ├─ eligibility.py                     # ← consumes active CategoryProfile
│  │  │     ├─ soft_score.py                      # ← consumes active CategoryProfile
│  │  │     └─ bucket_cap.py                      # ← consumes active CategoryProfile
│  │  ├─ atoms/v1/
│  │  │  ├─ guards.py                             # ← profile-driven guards
│  │  │  └─ schemas.py
│  │  ├─ meaning_atoms/                           # producer атомов
│  │  ├─ expressive_llm/                          # LLM-обогащение (отзывы, vibes)
│  │  └─ ...
│  └─ ...
├─ frontend/app/                                  # Next.js 15 (app router)
│  └─ app/project/[projectId]/seo/                # ⭐ SEO UI
│     ├─ page.tsx                                 # landing
│     ├─ _components/                             # Shell, HowToUsePanel, badges
│     ├─ categories/                              # список и страница категории
│     ├─ products/                                # SKU workbench + queries/generation/compare
│     ├─ matcher-runs/                            # debug viewer
│     └─ ...
├─ tests/seo/                                     # существующие тесты
│  ├─ test_matcher_v2_no_category_literals.py     # ← уже есть, anti-literal assertion
│  ├─ test_seo_eval_harness.py
│  └─ ...
├─ alembic/                                       # миграции
│  └─ versions/
├─ infra/docker/docker-compose.yml                # postgres + api + frontend
├─ scripts/                                       # CLI
│  ├─ run_matcher_v2_for_labeled_812.py           # прогнать matcher_v2 для labeled SKU
│  ├─ import_seo_eval_labels_812.py               # импорт 191 seed-label
│  └─ ...
└─ config/
   └─ seo/                                        # (Phase 0 создаёт структуру)
      ├─ global_vocabulary.json                   # (Phase 0 Step 2)
      └─ category_profiles/<project>/<cat>/<ver>.json  # (Phase 0 Step 3+)
```

---

## 3. Текущее состояние системы (2026-04-25, после Phase 1 / перед Phase 1Q)

### 3.1. Что есть в БД

- **Проект**: 1 проект (`project_id = 1`, имя — EcomCore).
- **Категория 812 (кружки)**:
  - 31 921 `seo_queries_normalized` с enriched-метриками (см. §3.1.1 ниже про реальные ключи `sample_source_payload`).
  - 183 `seo_query_clusters`.
  - `seo_category_meaning_axes` активная (source: LLM+deterministic).
  - 191 `seo_eval_labels` (ground truth).
  - свежий Step 10 matcher/eval прогон для 8 labeled SKU: run ids `63..70`, eval run id `75`.
  - ~8 SKU с `seo_sku_meaning_annotations` + meaning atoms.
  - активный `SeoCategoryProfile`: `id=1`, `version=v1.812.skeleton.243953b2`, `is_active=true`, `schema_version=category_profile_v1`, `self_check.status=passed`.
- **Категория 2841 (ланчбоксы)**:
  - Phase 1 Step 6 dry-run принят: `subject.primary="ланчбокс"`, aliases `["ланчбокс", "ланч", "бокс"]`, `self_check.status=passed`.
  - Phase 1 Step 7 сохранён candidate `SeoCategoryProfile`: `id=2`, `version=v1.2841.generic.46889ee8`, `schema_version=category_profile_v1`, `self_check.status=passed`.
  - Phase 1 Step 8 activation выполнен: `id=2`, `version=v1.2841.generic.46889ee8`, `is_active=true`, `self_check.status=passed`, `subject.primary="ланчбокс"`, `hard_conflicts_count=0`.
  - Phase 1 Step 9 matcher smoke прошёл как runtime/backend feasibility: active profile loaded, no `ProfileMissingError`, no legacy fallback, replayable traces exist.
  - Phase 1 Step 9D зафиксировал product-quality blocked: SKU `10533814` и `893327503` дали pathological bucket distributions `915 primary / 24 secondary / 2 broad / 0 rejected`.
  - Category 2841 is NOT production-proven. См. `docs/seo-module/phase1/STEP_9D_2841_MATCHER_QUALITY_FAILURE.md`.
  - Следующий шаг: Phase 1Q Step 2 — SKU Evidence Audit for `535441190`.
- **Категория 821 (тарелки, бегло упоминалась в транскрипте)**: был пример axes с полным набором экономических метрик, но не активно работали. В Phase 0 **не трогаем**.
- **Таблица `seo_category_profiles`**: существует; для `(project_id=1, category_id=812)` и `(project_id=1, category_id=2841)` есть активные профили.
- **Таблица `seo_category_profile_derive_runs`**: существует; используется для observability derive/activation tooling.

#### 3.1.1. Реальные ключи `sample_source_payload` (категория 812, проверено в БД 2026-04-24)

`seo_queries_normalized.sample_source_payload` — это **дамп строки исходного CSV в JSON**, без семантической трансформации (см. `services/seo/query_pipeline/ingestion.py:236-239`). Имена ключей = заголовки колонок WB-экспорта **as-is**, по-русски, с пробелами. Никакого «нормализованного» слоя имён (вида `top_subject`, `orders`, `conversion`) **в БД нет** и не появится без отдельной работы.

Полный список ключей в 812 (24 поля, заполнены для всех 31 921 строк):

**Сервисные (добавлены ingestion'ом):**
- `raw_query`, `__normalized_query`, `__raw_row_count`, `__trace_first_row_number`
- `__resolved_query_column`, `__resolved_frequency_column`

**Из enriched WB Analytics CSV (русские заголовки as-is):**
- `Поисковый запрос` — текст запроса
- `Количество запросов`, `Количество запросов (предыдущий период)` — спрос в поиске; при импорте агрегируется в **`SeoQueryNormalized.frequency_total`** (популярность нормализованного запроса в корпусе)
- `Запросов в среднем за день`, `Запросов в среднем за день (предыдущий период)`
- `Перешли в карточку товара`, `Перешли в карточку товара (предыдущий период)`
- `Добавили в корзину`, `Добавили в корзину (предыдущий период)`
- `Заказали товаров`, `Заказали товаров (предыдущий период)` — заказы по выгрузке (агрегат по категории, не per-SKU)
- `Конверсия в корзину`, `Конверсия в корзину (предыдущий период)`
- `Конверсия в заказ`, `Конверсия в заказ (предыдущий период)`
- `Больше всего заказов в предмете` — для какого WB-«предмета» этот запрос приносит больше всего заказов
- `Предметов с заказами по запросу`, `Предметов с заказами по запросу (предыдущий период)`

**Продуктовый контракт:** колонки с заказами и конверсиями в `sample_source_payload` — **не вход** в scoring матчера, в генерацию eval-labels и в derive-профиль как «сигнал качества запроса». Они максимум для справки оператора или отчётов импорта; причина — homogenization-trap и отсутствие per-SKU смысла, см. `ROADMAP.md` §8.1.

#### 3.1.2. Поле `Больше всего заказов в предмете` — это sanity check, не источник правил

Оператор грузит CSV **в конкретную категорию** (выбирает её в UI). WB-выгрузка ожидаемо принадлежит этому subject'у. Поэтому в 812 `Больше всего заказов в предмете = "Кружки"` для **100% строк (31 921/31 921)** — это **корректное и ожидаемое** состояние, а не дефект данных и не «pre-filter, который что-то отрезал».

Из этого следует:
- Поле **не источник** для `subject.related_but_different`, `negative_token_prefixes`, subject-trap rules. В правильно загруженном CSV там разнообразия не будет и быть не должно.
- Поле — **диагностический sanity check**: если в импортированном CSV `Больше всего заказов в предмете` отличается от primary subject категории в значимой доле строк (>5%), это сигнал, что оператор загрузил выгрузку из чужой категории. Phase 0 добавит это как warning в импорт-отчёт.
- Источник `subject.related_but_different` в profile derive — `SeoCategoryMeaningAxes.axes_payload.product_type_axes[1..]` (там в bootstrap LLM уже выделил конкурирующие subject'ы по семантике корпуса) + LLM-уточнение по списку токенов запросов. См. `CATEGORY_PROFILE_SPEC.md §3.2.3`.

### 3.2. Что работает (happy-path on 812)

- Импорт CSV через UI (`/app/project/1/seo/categories/{cid}` → Обновить).
- Bootstrap pipeline: normalize → cluster → meaning → axes → atoms → embeddings.
- `POST /api/seo/matcher/v2/run` для 812 SKU — создаёт `SeoMatcherRun` с `bucket` per query и пишет `category_profile_version` / `category_profile_active` в `metrics`.
- `matcher_v2` требует активный `SeoCategoryProfile`; нет активного профиля → понятная ошибка `ProfileMissingError`, а не hidden legacy fallback.
- Категория 2841 доказала backend portability passed: derive/persist/activate/matcher runtime path работает на второй категории без legacy fallback.
- `POST /api/seo/eval/matcher/run` для 812 — accuracy считается по 191 labels.
- Active guards и `query_meaning_matcher/matcher.py` profile-driven/literal-free; legacy matcher изолирован в `query_meaning_matcher/_legacy/matcher.py`.
- Phase 0 Step 10 regression gate passed for 812: baseline accuracy `0.1678`, current accuracy `0.2349`, drift `+0.0671`, minimum acceptable `0.1378`.
- UI iter2: QualityBadge, ApprovalStateBadge, CategoryTierBadge, HowToUsePanel, compare-page с фильтрами и поиском.
- Generation preview (research-preview), human-review, promote (все behind eligibility-gate).

### 3.3. Что НЕ работает (и почему)

| Что | Почему |
|---|---|
| `matcher_v2` для категории без активного профиля | После Phase 0 это ожидаемый fail-fast: нужно сначала derive/self-check/activate профиль |
| `eval` без ручного перечисления `nm_ids` | Эндпоинт требует явные `nm_ids`; без них возвращает 0 labels |
| Strict eval labels для категорий кроме 812 | Пока нет ground-truth labels; Phase 1 использует qualitative validation |
| Product-quality validation после Phase 1 | Product-quality blocked: missing/weak buyer-perception evidence, missing/failed vision, missing SKU atoms on some 2841 SKU, matcher over-primary failure |
| Phase 2 | Phase 2 blocked до прохождения Phase 1Q или явного operator waiver |
| Operator happy-path UI | Текущие экраны — микс iter1/iter2 + отладка, нет чистого пути «от CSV до брифа» |
| Экспорт брифа | Phase 4, не реализовано |
| Optional full SEO test suite | Известный unrelated failure: `tests/seo/test_matcher_retention.py::test_keeps_referenced_runs` |

### 3.4. Docker / environment

- Docker Compose: `infra/docker/docker-compose.yml`.
- Контейнеры: `ecomcore-postgres-1`, `ecomcore-api-1`, `ecomcore-frontend-1`.
- Docker Desktop на Windows **периодически падает** (см. транскрипт 2026-04-24, problem 9). Если `docker ps` зависает или отвечает 500 — первое действие: подождать, не крутить в цикле.
- Frontend ждёт rebuild при правке `frontend/**`: `docker compose -f infra/docker/docker-compose.yml up -d --build frontend`.

### 3.5. Ключевые конфигурационные факты

- Postgres: `jsonb_pretty(X)` требует явный каст `X::jsonb`, не `X::json`.
- Таблица `seo_meaning_atoms` использует колонки `entity_type`, `atoms_payload` (не `atom_type`).
- Таблица `seo_matcher_runs` использует `metrics`, не `run_meta`.

---

## 4. Ключевые концепции SEO-модуля

### 4.1. Subject vs category vs product_type

- **Category** = WB category_id (например, 812).
- **Subject** = каноническая товарная сущность в категории (например, «кружка»). **Одна категория = один primary subject**, но может содержать «родственные, но разные» subjects (`термокружка`, `стакан`).
- **Product_type** = тип товара на уровне SKU (это часто совпадает с subject, но может быть специфичнее: «кружка походная» vs «кружка»).

### 4.2. Query meaning

Каждый поисковый запрос (после нормализации и кластеризации) получает `SeoQueryMeaning` — JSONB с полями `functional`, `expressive`, `audience`, `occasion`, `constraints`. LLM-заполнено, хранится в `seo_query_meanings`.

### 4.3. SKU meaning

Для каждого SKU: `SeoSkuMeaningAnnotation` (LLM-обогащённое meaning на основе карточки и отзывов) + `SkuAtoms` (структурированные атомы).

### 4.4. Meaning atoms

`SeoMeaningAtom` — элементарные факты о запросе или SKU:
- `required_atoms` (запрос требует, SKU должен иметь),
- `preferred_atoms` (нравится иметь),
- `excluded_atoms` (запрос требует отсутствия),
- `conflict_atoms` / `negative_fit_atoms`.

Используются в `atoms_gate` стадии матчера.

### 4.5. Buckets

Результат матчинга (query, SKU) → один из 4 бакетов:
- `primary` — высокая релевантность, первый приоритет.
- `secondary` — релевантно, но слабее.
- `broad` — слишком общий запрос, использовать с осторожностью.
- `rejected` — не подходит.

### 4.6. Eligibility tier

На уровне категории (`SeoCategoryMatchingReadiness.eligibility_tier`):
- `preview_only` — можно только preview генерации.
- `evaluated` — eval пройден, можно approve запросы.
- `approved` — категория полностью подтверждена, можно экспортировать бриф.

### 4.7. Quality mode и Approval state

- `quality_mode`: `research_preview | evaluated_preview | production` — на уровне `SeoMatcherRun`.
- `approval_state`: `draft | under_review | approved` — на уровне `SeoSkuQuerySet`.

### 4.8. Category Meaning Axes

`SeoCategoryMeaningAxes` — выход анализа корпуса категории. Содержит `product_type_axes`, `use_case_axes`, `audience_axes`, и т. д. Производится `category_bootstrap` pipeline. Используется как **сырой материал** для derive'а профиля.

### 4.9. Category Profile (Phase 0 core)

См. `CATEGORY_PROFILE_SPEC.md`. Это JSON-документ с категорийными правилами, который в Phase 0 становится единственным источником категорийной логики для матчера и guards.

---

## 5. Product decisions уже сделаны (не пересматривать в одиночку)

Эти решения **зафиксированы после долгих обсуждений**. Если агент считает, что их надо пересмотреть — пишет оператору с развёрнутой аргументацией, не меняет в коде.

### 5.1. Homogenization trap

Экономические сигналы категории (`orders`, `conversion rate`) **не** используются для калибровки матчера. Причина: это убьёт вайбовую релевантность для уникальных товаров (пример: «милая жёлтая кружка с капибарой» нельзя оптимизировать под «кружка для кофе» только потому, что последний запрос конверсионнее на категории). Per-SKU сигналы (WB feedback loop) — отдельная тема, Phase 5, deferred.

### 5.2. Matcher — shortlist generator, не классификатор

Матчер не решает «relevant/irrelevant» бинарно. Он сортирует все запросы категории и разбивает на 4 бакета. Оператор затем approve'ит или отклоняет. Это **human-in-the-loop**, не полный автопилот.

### 5.3. Profile over hardcoded

Phase 0 переводит всю категорийную логику в `SeoCategoryProfile`. **Запрещено** добавлять новые hardcoded-ветки «под кружки / термокружки / стаканы» в руст / питон код. Если нужно новое правило — поле в профиле.

### 5.4. Manual review не масштабируется

Для 31 921 запроса категории ручная модерация невозможна. Профили строятся **автоматически** (эвристика + LLM + self-check), оператор только утверждает или откатывает. См. `CATEGORY_PROFILE_SPEC.md §9`.

### 5.5. Meaning atoms остаются

В ходе обсуждения 2026-04-24 было предложено выпилить meaning_atoms. **Решение: оставляем.** Генерация атомов уже автоматизирована через bootstrap и SKU-analysis. Проблема только в том, что producer читает hardcoded правила вместо профиля — это Phase 0 Step 5.

### 5.6. Категории-агностика — Phase 0/1 backend state

После Phase 0 backend-путь стал category-agnostic для категорий с активным `SeoCategoryProfile`: `matcher_v2` читает профиль, active guards/matcher literal-free, legacy изолирован. Phase 1 доказала backend portability passed на категории 2841: профиль был derived/persisted/activated, matcher smoke исполнился на активном профиле, legacy fallback не появился.

Но Phase 1 не доказала product-quality. Category 2841 is not production-proven: Step 9D показал matcher over-primary failure на двух SKU без SKU atoms (`915/941 primary`, `0 rejected`), а Phase 1Q дополнительно фиксирует риски missing/weak buyer-perception evidence, missing/failed vision и пустые/слабые expressive signals. Поэтому Phase 2 blocked до прохождения Phase 1Q или явного operator waiver.

### 5.7. Reviews уже участвуют в axes

Отзывы товаров (`wb_feedback_snapshots`) → `services/seo/expressive_llm/reviews_source.py` → `_fetch_review_evidence` в `category_bootstrap.py` → попадают в LLM-промпт для `SeoCategoryMeaningAxes`. Ничего дополнительно с отзывами делать не нужно (кроме возможных будущих оптимизаций).

---

## 6. Что уже пробовалось и не сработало

Чтобы агент не повторял неудачные попытки:

### 6.1. `parity_matcher_v2_812.py` — повис на 13+ минут

Скрипт, параллельно гонявший legacy + candidate матчер для сравнения. Слишком медленный. Заменён на `scripts/run_matcher_v2_for_labeled_812.py` (только matcher_v2). См. транскрипт 2026-04-24 problem 3.

### 6.2. `eval` без `nm_ids`

`POST /api/seo/eval/matcher/run` без списка `nm_ids` → 0 labels. Контракт эндпоинта (`routers/seo_eval.py`) требует явные id. Workaround: передавать все labeled nm_ids списком.

### 6.3. Включение `orders` в scoring

Было предложено, отвергнуто из-за homogenization trap (§5.1). В Phase 0 запрещено.

### 6.4. Manual labeling для других категорий

Предлагалось помечать 20-30 запросов руками на каждую категорию. Отвергнуто из-за нон-скейла (у оператора 5–7 категорий × десятки тысяч запросов). Решение: derive_category_profile + self_check.

### 6.5. Выпиливание meaning_atoms

Предлагалось. Отвергнуто (§5.5). Оставлены как runtime слой, только producer адаптируется под профиль.

---

## 7. Глоссарий

| Термин | Расшифровка |
|---|---|
| **SKU** | Stock-Keeping Unit. Идентификатор товара на WB (`nm_id`). |
| **nm_id** | WB-specific id SKU, celé число. |
| **WB** | Wildberries. |
| **Subject** | Каноническая товарная сущность. См. `CATEGORY_PROFILE_SPEC §3.2`. |
| **Bucket** | `primary` / `secondary` / `broad` / `rejected`. См. §4.5. |
| **Matcher** | Сервис, решающий «насколько запрос релевантен SKU». |
| **matcher_v1** | Легаси (`query_meaning_matcher/matcher.py`). Phase 0 изолирует в `_legacy/`. |
| **matcher_v2** | Candidate (новый). `services/seo/matcher_v2/`. Core работы Phase 0. |
| **Atoms** | Структурированные факты о query/SKU. |
| **Axes** | Семантические оси категории из LLM-анализа корпуса. |
| **Profile** | `SeoCategoryProfile`, категорийные правила. См. `CATEGORY_PROFILE_SPEC.md`. |
| **Derive** | Автогенерация профиля из корпуса. Phase 0 Step 3/8. |
| **Self-check** | Валидация профиля перед активацией. SPEC §9. |
| **Eligibility tier** | Статус готовности категории к production. §4.6. |
| **Research preview** | Маркер «не production-текст». `OPERATOR_WORKFLOW §1.1`. |
| **Homogenization trap** | См. §5.1. |
| **Eval** | Прогон матчера против ground-truth labels → accuracy / F1. |
| **Baseline** | Зафиксированное поведение системы ДО изменений. `TEST_PLAN §1.3`. |
| **Iter1 / Iter2** | Предыдущие итерации разработки. Отчёты в `docs/seo-module/implementation-plan/`. |

---

## 8. Quick command reference

### 8.1. Тесты

```bash
# все SEO тесты
pytest -x tests/seo/

# фаза-специфичные
pytest -x tests/seo/phase0/

# с verbose
pytest -x -vv tests/seo/phase0/test_<name>.py

# frontend type-check
cd frontend && npx tsc --noEmit
```

### 8.2. Docker

```powershell
# поднять стек
docker compose -f infra/docker/docker-compose.yml up -d

# пересобрать фронт
docker compose -f infra/docker/docker-compose.yml up -d --build frontend

# логи API
docker logs -f ecomcore-api-1
```

### 8.3. Alembic

```bash
# из src/
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "phase0: seo_category_profile_derive_runs"
```

### 8.4. CLI скрипты (Phase 0)

```bash
# baseline snapshot
python scripts/phase0/capture_baseline.py --project 1 --category 812 --out tests/seo/phase0/baselines/812_pre_phase0/

# derive/profile lifecycle
python scripts/derive_category_profile.py --project 1 --category 812 --dry-run
python scripts/derive_category_profile.py --project 1 --category 812 --persist
python scripts/activate_category_profile.py --profile-id 1

# run matcher_v2 for all labeled 812 SKU
python scripts/run_matcher_v2_for_labeled_812.py --project-id 1

# regression reports
tests/seo/phase0/baselines/812_pre_phase0/
tests/seo/phase0/activation_reports/812_step10/eval_comparison.json
tests/seo/phase0/activation_reports/812_step10/eval_current.json
```

### 8.5. База данных (Postgres)

```bash
# подключиться
docker exec -it ecomcore-postgres-1 psql -U ecomcore -d ecomcore

# размер таблицы
SELECT pg_size_pretty(pg_total_relation_size('seo_queries_normalized'));

# активный профиль
SELECT id, version, is_active FROM seo_category_profiles WHERE category_id = 812 AND is_active = true;
```

---

## 9. Key external systems

| Система | Зачем нужна | Как работаем |
|---|---|---|
| **WB API** | Карточки, отзывы, keyword-отчёты | Через отдельный сервис, не в Phase 0 scope |
| **LLM (OpenAI / compatible)** | Meaning extraction, expressive-анализ, derive-refinement | Через `services/seo/llm/client.py` |
| **Postgres** | Все данные | Через SQLAlchemy + Alembic |
| **Docker Desktop (Windows)** | Локальный dev-стек | Периодически падает; см. §3.4 |

---

## 10. Куда смотреть за специфичными вопросами

| Вопрос | Документ / файл |
|---|---|
| Как устроен CategoryProfile? | `CATEGORY_PROFILE_SPEC.md` |
| Что я должен сделать сейчас? | `ROADMAP.md` + `phase<N>/PHASE_<N>_EXECUTION_PLAN.md` |
| Как тестировать? | `phase<N>/TEST_PLAN.md` |
| Как должен выглядеть UI? | `OPERATOR_WORKFLOW.md` |
| Правила работы агента? | `AGENTS.md` (в корне репо) |
| История (как сюда пришли)? | `docs/seo-module/implementation-plan/` — отчёты iter1/2 |
| Как работает expressive LLM? | `docs/seo-module/SEO Module - Expressive LLM Integration Spec.md` |
| Как работают meaning atoms? | `docs/seo-module/23_atoms_v1_design_and_implementation_plan.md` |
| Как работает generation? | `docs/seo-module/24_wb_seo_generation_adaptation.md` |

---

## 11. Ловушки и принятые решения

### 11.1. Кажется, что в коде логика привязана к 812 (слова «кружка», «термокружка»)

В active runtime path после Phase 0 таких литералов быть не должно. Они допустимы в профиле 812, тестах, baseline/reports и isolated legacy. Если найдены в active `src/app/services/seo/**` вне `_legacy`, это regression.

### 11.2. Кажется, что `del category_profile` — ошибка

После Phase 0 это regression. Step 10 зафиксировал `del category_profile = 0`.

### 11.3. Кажется, что legacy-matcher надо просто удалить

Legacy matcher не удалён полностью: он изолирован под `query_meaning_matcher/_legacy/` и помечен deprecated. Не использовать его как hidden fallback для `matcher_v2`.

### 11.4. Кажется, что `SeoCategoryProfile` должен иметь больше полей

Спецификация `v1` — минимум, достаточный для Phase 0. Расширение — через `v1.1` (backward-compat) или `v2` (breaking). См. `CATEGORY_PROFILE_SPEC §8`.

### 11.5. Кажется, что можно начинать Phase 1 до docs/acceptance

Нельзя. Phase 1 стартует только от completed Phase 0: Step 10 acceptance gate + Step 11 docs/retro.

### 11.6. Кажется, что self_check слишком строгий

Он **намеренно** строгий. Если blocking — значит derive надо улучшить, а не проверку ослабить. Открытые вопросы по чувствительности порогов — в `CATEGORY_PROFILE_SPEC §13`.

### 11.7. Кажется, что `derive_category_profile` должен быть проще

«Просто взять топ-N токенов» — это эвристика. Она есть. LLM дополняет для сложных решений (разведение родственных subject'ов, hard_conflicts). Мини-модель работает; пытаться выкинуть LLM сломает качество.

---

## 12. Contact

Оператор: пользователь чата. Единственный финальный авторитет по продуктовым решениям. В случае сомнений — спрашивать его, не «спрашивать код».

---

## 13. Changelog

- **2026-04-24 v1** — initial. Первичный primer перед стартом Phase 0.
- **2026-04-24 v1.1** — Phase 0 closed: active profile 812, profile-driven matcher/guards, Step 10 regression gate, Phase 1 starting state.
- **2026-04-25 v1.2** — Phase 1 Step 8 activation reflected: category 2841 active profile `v1.2841.generic.46889ee8`; next Step 9 matcher smoke.
- **2026-04-25 v1.3** — Phase 1 reclassified: backend portability passed, product-quality blocked; Phase 1Q is required before Phase 2 unless operator waiver is explicit.
- **2026-04-28 v1.4** — Phase 1Q first production query-selection path added on `/queries`: preview input, LLM run through provider interface, and persisted run artifacts without separate operator brief entity or auto-approval.
- **2026-04-28 v1.5** — Production query-selection candidate retrieval corrected: backend run input now sends the wide deduped cluster-representative set (~2200 candidates when corpus is sufficient), while preview displays only the first N and persists total vs sent candidate counts separately.

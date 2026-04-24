# Category Profile — Specification (v1)

> Статус: **нормативный документ**. Любой код, читающий или пишущий `SeoCategoryProfile`, обязан соответствовать этому контракту. При расхождении — обновляем документ до кода, не наоборот.

> Версия: `v1` (Phase 0). Все последующие расширения — либо `v1.1` (обратно-совместимое поле), либо `v2` (breaking). См. раздел «Versioning».

---

## 0. TL;DR для агента

`SeoCategoryProfile` — это **единственный источник категорийных правил** для `matcher_v2` и для генерации `meaning_atoms`. Всё, что сейчас зашито литералами в `atoms/v1/guards.py` и `query_meaning_matcher/matcher.py` (строки «термокруж», «круж», «пивн», «кофемаш» и т. п.), должно переехать в этот профиль.

Профиль:
- **хранится** в таблице `seo_category_profiles` (JSONB payload);
- **читается** через `app.services.seo.category_profile.load_active_profile(...)`;
- **пишется** генератором `derive_category_profile(category_id)` (см. `PHASE_0_EXECUTION_PLAN.md`, Step 3) — руками не правится в обычном режиме;
- **активируется** только после прохождения self-check (раздел 9).

Границы:
- Профиль описывает **семантику категории** (что продаётся, какие конфликты, какие подкатегории).
- Профиль **не описывает кросс-категорийную лексику** (цвета, получатели, материалы, объёмы, числа) — это живёт в `config/seo/global_vocabulary.json`, один на всю систему.
- Профиль **не хранит экономические сигналы** (orders, conversion) — эти живут в `seo_queries_normalized.sample_source_payload`.

---

## 1. Зачем этот профиль существует

### 1.1. Текущая проблема

В коде на момент написания документа (см. транскрипт аудита за 2026-04-24):

- `matcher_v2` **декларативно** принимает `category_profile` в каждую стадию (`eligibility.py`, `soft_score.py`, `bucket_cap.py`), но **фактически** в каждой стадии есть строка `del category_profile`, после чего исполняется ветка из `services/seo/query_meaning_matcher/matcher.py`.
- Эта «легаси»-ветка содержит литералы, применимые только к кружкам: `"термокруж"`, `"круж"`, `"пив"`, `"кофемаш"`, `"в машину"`, `"рюкзак"`, и т. п.
- `atoms/v1/guards.py` делает то же самое при построении `QueryAtoms`/`SkuAtoms`.
- `seo_category_profiles` пустая; версия профиля у всех ранов = `default_iter1` (sentinel, означающий «профиль не применён»).

Итог: система формально «category-agnostic», фактически — работает только на категории 812 (кружки). На любой другой категории eligibility/scoring/bucketing выдадут мусор или ровно то же самое «кружечное» поведение.

### 1.2. Целевое состояние

После Phase 0:

- Профиль — **обязательное условие** запуска `matcher_v2` на категории. Нет активного профиля → `matcher_v2` отказывается стартовать с понятной ошибкой (никакого скрытого fallback на легаси).
- Все категорийные литералы удалены из `guards.py` и `matcher.py` и заменены на чтение полей профиля.
- Добавление новой категории == прогнать `derive_category_profile(category_id)` + пройти self-check + активировать. Без правки кода.

### 1.3. Что профиль **не** решает

- ❌ Не решает проблему качества ранжирования (за это отвечают `SeoQueryMeaning`, `SeoCategoryMeaningAxes`, атомы, эмбеддинги).
- ❌ Не решает задачу «какой запрос **конвертит лучше для конкретного SKU**». Это **вне** `SeoCategoryProfile`: профиль задаёт семантические правила и конфликты, а не экономическую оптимизацию карточки.
  - **Категорийные** колонки заказов/конверсии в `seo_queries_normalized.sample_source_payload` (`Заказали товаров`, `Конверсия в заказ` и т. п.) **не используются** как вход в матчер, в генерацию eval-labels и в `derive_category_profile` (осознанный отказ: homogenization-trap, см. `ROADMAP.md` §8.1 и `CONTEXT_PRIMER.md` §5.1). Они остаются в БД как **сырые данные выгрузки**; максимум — справка оператора или диагностика импорта, не правила.
  - **Отложено отдельно** (не Phase 0): возможный **per-SKU** сигнал из кэша отчётов WB (`wb_search_report_keywords_cache` и т. п.) как мягкий корректор после инфраструктуры — см. `ROADMAP.md` §8.2. Это **не** «подмешать тот же CSV по категории в scoring».
- ❌ Не является классификатором «товар→категория» (категория приходит извне, из импорта).
- ❌ Не хранит данные по конкретному SKU.

Профиль — это **словарь категорийных правил матчинга**, не больше.

---

## 2. Где он живёт

### 2.1. База

Таблица: `seo_category_profiles` (ORM: `app.models.SeoCategoryProfile`).

```
id              BIGSERIAL PK
project_id      INT NOT NULL  -- scope: проект
category_id     INT NOT NULL  -- scope: WB category
version         VARCHAR(64)   -- напр. "v1.812.2026-04-24-auto"
is_active       BOOL          -- ровно одна активная на (project_id, category_id)
payload         JSONB         -- см. раздел 3
source_note     TEXT          -- как построен профиль (человекочитаемо)
created_at      TIMESTAMPTZ
updated_at      TIMESTAMPTZ
UNIQUE (project_id, category_id, version)
```

Инвариант: **ровно одна** строка с `is_active = true` на `(project_id, category_id)` (enforce'ится в коде активации, не в БД — чтобы можно было атомарно подменять).

### 2.2. Код

| Компонент | Роль | Файл |
|---|---|---|
| ORM | схема таблицы | `src/app/models.py` (`class SeoCategoryProfile`) |
| Loader (read-only) | единственная точка чтения в рантайме | `src/app/services/seo/category_profile.py::load_active_profile` |
| Writer | генерация + активация | `src/app/services/seo/category_profile_derive.py` (создаётся в Phase 0, Step 3) |
| Admin API | ручной просмотр/откат | `src/app/routers/seo_category_profile.py` (создаётся в Phase 0, Step 7) |
| CLI | smoke-тест | `scripts/derive_category_profile.py` (создаётся в Phase 0, Step 3) |

### 2.3. Конфиг-файлы

Для воспроизводимости генерации профиля каждая активация **дополнительно** пишет снимок в git:

```
config/seo/category_profiles/<project_id>/<category_id>/<version>.json
```

Снимок — копия `payload` + `source_note`. Это даёт code-review diff при автоматическом обновлении профиля и возможность откатиться, если derive-скрипт выдаст мусор.

---

## 3. Схема payload

Ниже — **полный контракт** JSON. Все примеры — валидные. Порядок ключей в JSON не важен, но в снимке он фиксированный (для чистых diff'ов): сверху — subject, затем conflicts, затем constraints, затем weights, затем labels.

```json
{
  "schema_version": "category_profile_v1",

  "subject": {
    "primary": "кружка",
    "primary_aliases": ["кружка", "кружки", "кружку", "кружке", "кружкой", "mug"],
    "related_but_different": [
      {"subject": "термокружка", "aliases": ["термокруж", "термостакан"]},
      {"subject": "стакан",       "aliases": ["стакан"]},
      {"subject": "бокал",        "aliases": ["бокал", "пивн"]}
    ],
    "detection_hints": {
      "token_prefixes": ["круж"],
      "negative_token_prefixes": ["термокруж", "стакан", "бокал", "поильник"]
    }
  },

  "product_type_aliases": {
    "кружка":      {"match_any_prefix": ["круж"], "score_bonus": 0.16},
    "термокружка": {"match_any_prefix": ["термокруж"], "score_bonus": 0.22}
  },

  "constraints": {
    "derive_from_query_tokens": [
      {"constraint": "thermal",         "when_query_contains_any": ["термокруж", "термос"]},
      {"constraint": "beer_use_case",   "when_query_contains_any": ["пивн", "пиво"]},
      {"constraint": "coffee_machine",  "when_query_contains_any": ["кофемаш"]},
      {"constraint": "car_use_case",    "when_query_contains_any": ["в машину", "для машины", "авто"]},
      {"constraint": "set",             "when_query_contains_any": ["набор", "комплект"]}
    ],
    "derive_from_sku_meaning": [
      {"constraint": "thermal",         "when_functional_attribute_contains": ["термокруж"]},
      {"constraint": "set",             "when_functional_attribute_contains": ["набор"]}
    ]
  },

  "hard_conflicts": [
    {
      "name": "thermal_required",
      "when_query_has": {"constraint": "thermal"},
      "requires_sku_any": [
        {"constraint": "thermal"},
        {"product_type_contains": "термокруж"}
      ],
      "message": "requires thermal/термокружка, SKU meaning does not"
    },
    {
      "name": "product_type_termo_mismatch",
      "when_query_has": {"product_type": "термокружка"},
      "requires_sku_any": [{"product_type": "термокружка"}],
      "message": "product_type conflict: термокружка vs SKU product type"
    },
    {
      "name": "beer_use_case_required",
      "when_query_has": {"constraint": "beer_use_case"},
      "requires_sku_any": [
        {"constraint": "beer_use_case"},
        {"token_prefix": "пив"}
      ],
      "message": "requires beer mug use case"
    },
    {
      "name": "set_quantity_required",
      "when_query_has": {"constraint_prefix": "set"},
      "requires_sku_any": [{"constraint_prefix": "set"}],
      "message": "requires set/quantity"
    }
  ],

  "scoring": {
    "weights": {
      "product_type_match":   0.22,
      "product_type_compat":  0.16,
      "product_type_weak":   -0.18,
      "use_case_overlap":     0.10,
      "attribute_overlap":    0.08,
      "expressive_overlap":   0.08,
      "audience_overlap":     0.06,
      "occasion_overlap":     0.04,
      "material_mismatch":   -0.25,
      "negative_audience":   -1.00
    },
    "bucket_cutoffs": {
      "primary":   0.60,
      "secondary": 0.35,
      "broad":     0.15
    },
    "bucket_caps": {
      "primary":   100,
      "secondary": 300,
      "broad":     500
    }
  },

  "user_bucket_labels": {
    "primary":   "Лучшие",
    "secondary": "Подходящие",
    "broad":     "Слишком общие",
    "rejected":  "Не подходят"
  },

  "sku_guards": {
    "characteristic_mappings": [
      {"name_contains": "объем",       "target": {"type": "numeric",       "field": "volume_ml",     "parser": "int_first"}},
      {"name_contains": "цвет",        "target": {"type": "attribute",     "field": "color"}},
      {"name_contains": "материал",    "target": {"type": "attribute",     "field": "material"}},
      {"name_contains": "количество",  "target": {"type": "numeric",       "field": "quantity",      "parser": "int_first"}},
      {"name_contains": "рисунок",     "target": {"type": "visual",        "field": "design",        "value_if_any": "print"}},
      {"name_contains": "декоратив",   "target": {"type": "visual",        "field": "design",        "value_if_any": "print"}},
      {"name_contains": "особенности", "target_keywords": [
         {"when_value_contains": "свч",       "target": {"type": "compatibility", "field": "compatibility", "value": "microwave"}},
         {"when_value_contains": "посудом",   "target": {"type": "compatibility", "field": "compatibility", "value": "dishwasher"}}
      ]}
    ],
    "functional_token_mappings": [
      {"when_contains": "термокруж", "target": {"type": "compatibility", "field": "thermal",       "value": true}},
      {"when_contains": "посудом",   "target": {"type": "compatibility", "field": "compatibility", "value": "dishwasher"}},
      {"when_contains": "свч",       "target": {"type": "compatibility", "field": "compatibility", "value": "microwave"}}
    ]
  },

  "query_guards": {
    "product_type_detection": [
      {"when_contains": "термокруж", "set_product_type": "термокружка", "add_required": [{"type": "compatibility", "field": "thermal", "value": true}]},
      {"when_contains": "круж",      "set_product_type": "кружка", "unless_set": true}
    ],
    "required_atoms": [
      {"when_contains": "прозрач", "atom": {"type": "visual", "field": "transparency", "value": "transparent"}},
      {"when_contains": "кофемаш", "atom": {"type": "compatibility", "field": "compatibility", "value": "coffee_machine"}},
      {"when_contains": "пивн",    "atom": {"type": "use_case", "field": "use_case", "value": "beer"}}
    ],
    "excluded_atoms": [
      {"when_contains": "без рисун", "exclude": {"field": "design",  "value": "print"}},
      {"when_contains": "без принт", "exclude": {"field": "design",  "value": "print"}},
      {"when_contains": "без крыш",  "exclude": {"field": "feature", "value": "lid"}}
    ]
  },

  "generated_by": {
    "method": "derive_heuristic_plus_llm_v1",
    "llm_model": "gpt-4o-mini",
    "prompt_version": "derive_v1",
    "evidence_hash": "sha256:...",
    "generated_at": "2026-04-24T18:30:00Z",
    "corpus_signals": {
      "queries_sampled": 31921,
      "product_type_axes_count": 4,
      "csv_subject_match_share": 1.0
    }
  },

  "self_check": {
    "status": "passed",
    "checks": [
      {"name": "csv_subject_sanity",      "result": "pass", "detail": "100% rows have 'Больше всего заказов в предмете' = 'Кружки' (matches primary)"},
      {"name": "subject_coverage",        "result": "pass", "detail": "98.4% queries match primary_aliases by detection_hints"},
      {"name": "hard_conflicts_applied",  "result": "pass", "detail": "4 rules, no syntax errors"},
      {"name": "eval_smoke",              "result": "pass", "detail": "accuracy=0.78 on 191 labels"}
    ]
  }
}
```

Ниже — поле за полем.

---

### 3.1. `schema_version`

- **Тип**: `string`, обязательное, строго `"category_profile_v1"` в Phase 0.
- **Назначение**: миграционный discriminator. Любой `v2` ломает совместимость и должен читаться отдельной веткой loader'а.
- **Потребитель**: `load_active_profile` отклоняет payload с неизвестной `schema_version`.

---

### 3.2. `subject` — чем является товар категории

#### 3.2.1. `subject.primary` (string, required)

Канонический базовый subject категории в именительном падеже, нижний регистр, без ё (всегда нормализовано: `заменяем ё → е`).

Примеры: `"кружка"`, `"рюкзак"`, `"чайник"`, `"тарелка"`.

**Потребитель**:
- `query_meaning_matcher/matcher.py::_sku_features` — если у SKU не извлёкся `product_type` из LLM-meaning, `primary` используется как дефолт при совпадении по `detection_hints.token_prefixes`.
- `matcher_v2/stages/eligibility.py::_is_in_primary_subject` — проверка, что запрос вообще про эту категорию.

#### 3.2.2. `subject.primary_aliases` (list[string], required, ≥1 элемент)

Все лексические варианты `primary`, включая склонения и транслитерации. Нормализованы (lowercase, ё→е).

**Автовывод** (из `derive_category_profile`): берётся топ-N нормализованных токенов из `seo_queries_normalized.primary_query_text` категории, отфильтрованный по частоте + LLM-фильтр «это действительно базовый subject, а не атрибут».

#### 3.2.3. `subject.related_but_different` (list[object], required, может быть пустым)

Subject'ы, **похожие** на primary лексически или семантически, но **отдельные продукты**. Ключевой источник «hard conflict» правил.

Каждый элемент:
```json
{"subject": "<canonical>", "aliases": ["<alias1>", ...]}
```

Примеры:
- Для `кружка`: `термокружка`, `стакан`, `бокал`, `чашка чайная` (если по корпусу разведены).
- Для `рюкзак`: `сумка`, `портфель`, `шопер`, `кошелёк`.
- Для `тарелка`: `миска`, `салатник`, `блюдо`, `поднос`.

**Почему это важно**: без этого поля «термокружка» и «кружка» матчатся как синонимы — именно это сейчас и ломает категорию 812 при запросах `термокружка с трубочкой`.

**Автовывод** (источник для derive-pipeline, в порядке приоритета):
1. **Первичный**: `SeoCategoryMeaningAxes.axes_payload.product_type_axes[1..]` — bootstrap-LLM уже разложил корпус на subject-оси и выделил соседей; берём всё кроме `[0]` (это primary) как кандидатов в `related_but_different`.
2. **Дополнение**: список токенов запросов категории, имеющих общий префикс с `primary` или семантически близких (например, для `кружка` это `термокружка`, `стакан`, `бокал` — токены, которые часто встречаются в корпусе как «не совсем то же самое»).
3. **LLM-уточнение**: модель получает (а) кандидатов из шагов 1–2, (б) семплы запросов с этими токенами, (в) `primary`, и решает, какие — действительно «родственные, но отдельные subject'ы», а какие — лексические варианты того же primary (тогда они уходят в `primary_aliases`).

**Что НЕ источник**: `seo_queries_normalized.sample_source_payload['Больше всего заказов в предмете']`. В правильно загруженном CSV категории 812 это поле = `"Кружки"` для всех строк (см. `CONTEXT_PRIMER.md §3.1.2`) — оно отражает subject-предмет самого CSV, а не разнообразие соседних subject'ов в нём. Использовать его как источник `related_but_different` нельзя, оно даст пустой список.

#### 3.2.4. `subject.detection_hints`

```json
{
  "token_prefixes":          ["круж"],
  "negative_token_prefixes": ["термокруж", "стакан", "поильник"]
}
```

Используется как **быстрый синтаксический фильтр** перед более дорогой семантикой:

- `token_prefixes` — если хоть один токен запроса начинается с этого префикса → считать запрос потенциально про `primary`.
- `negative_token_prefixes` — отменяет match по `token_prefixes`. Пример: `"термокруж"` начинается на `"круж"` → без negative-префикса попадёт в primary, что неправильно.

**Потребитель**: `matcher_v2/stages/eligibility.py` (fast-path фильтр до вызова LLM/эмбеддинг-скора).

---

### 3.3. `product_type_aliases`

Карта «какое каноническое `product_type` считать совпадающим с какими SKU-формулировками».

```json
"product_type_aliases": {
  "кружка":      {"match_any_prefix": ["круж"], "score_bonus": 0.16},
  "термокружка": {"match_any_prefix": ["термокруж"], "score_bonus": 0.22}
}
```

- **Ключ**: каноническое значение `product_type` (приходит от запроса или SKU-meaning).
- **`match_any_prefix`**: если `sku.product_type` или `query.product_type` содержит любой из этих префиксов — считаем product_type совместимым.
- **`score_bonus`**: вклад в soft-score. Обычно `0.22` (точный match) / `0.16` (alias-match) / `-0.18` (слабый конфликт). Эти числа мигрированы 1:1 из `_product_type_score` и могут быть калиброваны позже.

**Потребитель**: заменяет нынешний `_product_type_score` (`query_meaning_matcher/matcher.py:289-298`).

---

### 3.4. `constraints`

Декларативная замена «если в тексте запроса/SKU встречается X — поставь constraint Y».

```json
"constraints": {
  "derive_from_query_tokens": [
    {"constraint": "thermal",        "when_query_contains_any": ["термокруж", "термос"]},
    {"constraint": "beer_use_case",  "when_query_contains_any": ["пивн", "пиво"]}
  ],
  "derive_from_sku_meaning": [
    {"constraint": "thermal",        "when_functional_attribute_contains": ["термокруж"]}
  ]
}
```

**Потребитель**: replaces `_sku_features`, `_query_features` (внутри `query_meaning_matcher/matcher.py`).

**Инвариант**: `constraint` значение — произвольная строка-слот, но она должна использоваться хотя бы в одном `hard_conflicts[].when_query_has.constraint` ИЛИ в одном `sku_guards`. Иначе self-check бракует профиль.

---

### 3.5. `hard_conflicts` — декларативные правила блокировки

Заменяют `_hard_conflicts(sku, query)`.

Каждое правило имеет форму:

```json
{
  "name": "string, уникальное в пределах профиля",
  "when_query_has": { ... условие на запрос ... },
  "requires_sku_any": [ ... список альтернативных требований на SKU ... ],
  "message": "человекочитаемое объяснение для trace"
}
```

Правило срабатывает, если `when_query_has` истинно, а ни одно из `requires_sku_any` НЕ истинно — тогда запрос в bucket `rejected` с этим `message`.

#### Поддерживаемые предикаты в `when_query_has` / элементах `requires_sku_any`:

| Предикат | Значение | Пример |
|---|---|---|
| `constraint` | `string` | `{"constraint": "thermal"}` |
| `constraint_prefix` | `string` | `{"constraint_prefix": "set"}` — matches `set`, `set_quantity:2`, etc. |
| `product_type` | `string` | `{"product_type": "термокружка"}` |
| `product_type_contains` | `string` | `{"product_type_contains": "термокруж"}` |
| `token_prefix` | `string` | `{"token_prefix": "пив"}` |
| `materials_overlap` | `bool` | `{"materials_overlap": false}` — особый, см. ниже |

#### Специальные системные правила

Два правила логически одинаковы для всех категорий, но их параметры зависят от категории:

1. **`materials_overlap`**: если `query.materials` и `sku.materials` оба непустые и пересечение пустое → reject. Для профиля — флаг `scoring.enforce_material_overlap: bool` (по умолчанию `true`).
2. **`negative_audience`**: если `sku.negative_audience ∩ query.audience ∩ <whitelist>` непусто → reject. `<whitelist>` — из глобальной `audience_taxonomy`, не из профиля.

Эти два правила описываются не в `hard_conflicts`, а отдельными флагами в `scoring` — они универсальны.

#### Обязательные правила

Self-check требует, чтобы для каждого элемента `subject.related_but_different` было **хотя бы одно** `hard_conflicts` правило вида:
```json
{"when_query_has": {"product_type": "<related.subject>"}, "requires_sku_any": [{"product_type": "<related.subject>"}]}
```

Это гарантирует: похожие, но разные subject'ы не смешиваются.

---

### 3.6. `scoring`

Числовые параметры soft-score и границ бакетов.

```json
"scoring": {
  "weights": { ... },
  "bucket_cutoffs": {"primary": 0.60, "secondary": 0.35, "broad": 0.15},
  "bucket_caps":    {"primary": 100, "secondary": 300, "broad": 500},
  "enforce_material_overlap": true
}
```

- **`weights`**: коэффициенты перед компонентами skore (product_type, overlap, mismatch, negative_audience). Дефолты = текущие hardcoded значения из `_product_type_score` и друзей.
- **`bucket_cutoffs`**: пороги отсечения `primary/secondary/broad`. Запрос со `score < broad` → `rejected`.
- **`bucket_caps`**: максимальное число элементов в бакете (после сортировки по score). Защита от раздувания.
- **`enforce_material_overlap`**: см. 3.5.

**Инвариант**: `primary > secondary > broad > 0`. Self-check проверяет.

---

### 3.7. `user_bucket_labels`

Локализованные имена бакетов для UI. Не влияет на логику, только на отображение.

Дефолт (mugs-style): `{"primary": "Лучшие", "secondary": "Подходящие", "broad": "Слишком общие", "rejected": "Не подходят"}`.

Для категорий B2B/специализированных можно переопределить: `"primary": "Целевые"`, и т. п.

---

### 3.8. `sku_guards` — детерминированные извлечения атомов из SKU

Декларативная замена `atoms/v1/guards.py::apply_sku_guards`.

Покрывает два источника:

1. **`characteristic_mappings`** — WB-характеристики товара (`product.characteristics`):
   ```json
   {"name_contains": "объем", "target": {"type": "numeric", "field": "volume_ml", "parser": "int_first"}}
   ```
   `parser` — один из:
   - `"int_first"` — первое целое число в строке;
   - `"as_is"` — строковое значение;
   - `"boolean_keyword"` — true если значение в whitelist'е.

2. **`functional_token_mappings`** — токены из `meaning_payload.functional.attributes/use_cases`:
   ```json
   {"when_contains": "термокруж", "target": {"type": "compatibility", "field": "thermal", "value": true}}
   ```

**Потребитель**: `atoms/v1/guards.py::apply_sku_guards` переписывается как интерпретатор этого списка.

**Важно**: названия характеристик (`"объем"`, `"цвет"`) зависят от категории — WB показывает разный набор полей для разных subject'ов. Derive-скрипт вычитывает реальные имена характеристик из `wb_product_snapshots` для SKU категории и матчит их через LLM с каноническими слотами (`volume_ml`, `color`, `material`, ...).

---

### 3.9. `query_guards` — детерминированные извлечения атомов из запросов

Декларативная замена `atoms/v1/guards.py::apply_query_guards` в части категорийных веток (не глобальных).

```json
"query_guards": {
  "product_type_detection": [
    {"when_contains": "термокруж", "set_product_type": "термокружка", "add_required": [...]},
    {"when_contains": "круж",      "set_product_type": "кружка", "unless_set": true}
  ],
  "required_atoms":  [...],
  "excluded_atoms":  [...]
}
```

**Потребитель**: `atoms/v1/guards.py::apply_query_guards`.

**Глобальное остаётся глобальным**: regex'ы `_VOLUME_RE`, `_QUANTITY_RE`, рецепиенты, цвета, выразительность — в `global_vocabulary.json`, не дублируются в профилях.

---

### 3.10. `generated_by` — метаданные генерации

Для аудита и воспроизводимости. Заполняется автоматически `derive_category_profile`.

```json
"generated_by": {
  "method":          "derive_heuristic_plus_llm_v1",
  "llm_model":       "gpt-4o-mini",
  "prompt_version":  "derive_v1",
  "evidence_hash":   "sha256:<hash корпуса на момент генерации>",
  "generated_at":    "2026-04-24T18:30:00Z",
  "corpus_signals":  { ... сводные метрики корпуса ... }
}
```

`evidence_hash` должен делаться стабильным (sorted keys, round-to-3 для float'ов), чтобы можно было понять «корпус не изменился → профиль пересчитывать не нужно».

---

### 3.11. `self_check` — последний шаг перед активацией

Результаты прохождения валидатора. Профиль **не может** быть записан с `is_active=true`, если `self_check.status != "passed"`.

```json
"self_check": {
  "status": "passed|failed",
  "checks": [
    {"name": "subject_coverage",       "result": "pass|fail", "detail": "..."},
    {"name": "hard_conflicts_applied", "result": "pass|fail", "detail": "..."},
    {"name": "eval_smoke",             "result": "pass|fail", "detail": "..."}
  ]
}
```

Список обязательных проверок — в разделе 9.

---

## 4. Глобальный словарь (вне профиля)

Файл: `config/seo/global_vocabulary.json` (создаётся в Phase 0, Step 2).

Ответственность: кросс-категорийная лексика, которая одинакова для кружки, рюкзака, тарелки, и т. д.

Содержит:

- **`audience_taxonomy`**: `["женская", "мужская", "школьники", "подростки", "детская", ...]` — используется в negative-audience-блокировке.
- **`audience_synonyms`**: мапа `"женщине" → "женская"`, `"девушка" → "женская"`, и т. п. (то, что сейчас в `_AUDIENCE_GROUPS`).
- **`expressive_taxonomy`**: `["милая", "уют", "эстетика", "смешная", ...]` — канонические группы.
- **`expressive_synonyms`**: мапа вариантов (сейчас `_EXPRESSIVE_GROUPS` и `_EXPRESSIVE`).
- **`recipient_synonyms`**: сейчас `_RECIPIENTS`.
- **`color_taxonomy`** + **`color_synonyms`**: сейчас `_COLORS`.
- **`material_taxonomy`**: `["glass", "ceramic", "porcelain", "metal", "plastic", "textile", "leather", ...]` + синонимы.
- **`numeric_parsers`**: regex'ы (`_VOLUME_RE`, `_QUANTITY_RE`) — можно либо вынести сюда, либо оставить в коде (они реально универсальны, в профиль не нужны).

**Важно**: профиль **ссылается** на этот словарь неявно — например, материалы в `material_taxonomy` доступны всем. Профиль категории при этом может указать `materials_relevant: ["glass", "ceramic", "porcelain"]`, чтобы для этой категории использовалось подмножество.

Это поле — `scoring.materials_relevant` (опциональное):

```json
"scoring": {
  ...
  "materials_relevant": ["glass", "ceramic", "porcelain", "metal"]
}
```

Если опущено — используются все материалы из `material_taxonomy` (совместимость).

---

## 5. Связь с `SeoCategoryMeaningAxes`

`SeoCategoryMeaningAxes` (таблица `seo_category_meaning_axes`) — это **выход** LLM-анализа корпуса категории (запросы + товары + отзывы). Она **уже существует** и используется в `category_bootstrap.py`.

Её `axes_payload` содержит:
- `product_type_axes`, `use_case_axes`, `attribute_axes`, `audience_axes`, `expressive_axes`, `occasion_axes`, `constraint_axes`, `negative_constraint_axes`;
- `conflict_rules`, `synonym_groups`, `generic_query_patterns`.

Эти оси — **сырой эмпирический материал**. Профиль — **калиброванные правила** поверх этих осей.

### 5.1. Маппинг

| Поле профиля | Источник из `CategoryMeaningAxes` | Дополнительно |
|---|---|---|
| `subject.primary` | `product_type_axes[0]` (топ-1 по частоте) | LLM-фильтр «базовый subject vs атрибут» |
| `subject.primary_aliases` | токены кластера вокруг primary из `synonym_groups` | + склонения через морфологию |
| `subject.related_but_different` | `product_type_axes[1..]` (остальные product_type'ы) | LLM-разводка «родственные, но разные» |
| `subject.detection_hints.token_prefixes` | эвристика: общий префикс ≥ 3 символа среди aliases | чистая детерминистика |
| `constraints.derive_from_query_tokens` | `constraint_axes` + `generic_query_patterns` | LLM выбирает triggers |
| `hard_conflicts` | `conflict_rules` | основной входной сигнал |
| `query_guards.product_type_detection` | `product_type_axes` + `synonym_groups` | derive-скрипт |
| `query_guards.required_atoms` | `constraint_axes` + category-specific use_cases | LLM финализирует |

### 5.2. Обратная связь

Профиль **не изменяет** `CategoryMeaningAxes`. Axes — источник истины о корпусе. Профиль — интерпретация.

Если кол-во/качество запросов изменилось (перезалили CSV) → пересобрать axes → перегенерить профиль. Рукопашных правок нет.

---

## 6. Связь с meaning_atoms

`SeoMeaningAtom` (таблица `seo_meaning_atoms`) хранит извлечённые атомы (required/preferred/excluded) для запросов и SKU.

Профиль влияет на генерацию атомов через раздел `query_guards` и `sku_guards` (разделы 3.8, 3.9). То есть:

- `atoms/v1/guards.py::apply_query_guards(query)` должен читать `profile.query_guards` и итерироваться по декларативному списку, а не жестко-кодить ветки.
- `atoms/v1/guards.py::apply_sku_guards(sku, ...)` должен читать `profile.sku_guards`.

Loader для этого:
```python
profile = load_active_profile(session, project_id=..., category_id=...)
if profile is None:
    raise ProfileMissingError(category_id)
apply_query_guards(query, query_texts, profile=profile)
```

Сигнатура `apply_query_guards` расширяется на обязательный `profile: CategoryProfile` (см. PHASE_0_EXECUTION_PLAN, Step 5).

---

## 7. Lifecycle

### 7.1. Создание

```
1. derive_category_profile(project_id, category_id) читает корпус:
   - seo_queries_normalized (с sample_source_payload)
   - seo_category_meaning_axes (активная v0)
   - wb_product_snapshots (для sku_guards.characteristic_mappings)
2. Эвристики + LLM-промпт → payload JSON.
3. Валидация (schema + self-check, раздел 9).
4. INSERT в seo_category_profiles с is_active=false, version="v1.<cat>.<date>-auto".
5. Снимок в config/seo/category_profiles/<project>/<cat>/<version>.json.
```

### 7.2. Активация

```
1. Прогоняем eval (matcher_v2 на всех labeled SKU) с новым профилем.
2. Сравниваем accuracy/bucket-drift с текущим активным (если есть).
3. Если не хуже порога (см. TEST_PLAN) → активируем:
   - UPDATE seo_category_profiles SET is_active=false WHERE category_id=X AND is_active=true;
   - UPDATE seo_category_profiles SET is_active=true WHERE id=<new>;
   - одна транзакция.
4. Git commit снимка.
```

### 7.3. Деактивация / откат

```
UPDATE seo_category_profiles SET is_active=true WHERE id=<previous>;
UPDATE seo_category_profiles SET is_active=false WHERE id=<current>;
-- одна транзакция
```

Все прошлые версии хранятся (не удаляются) для аудита.

### 7.4. Обновление корпуса

Когда пользователь заливает новый CSV для категории:
```
category_bootstrap → обновление CategoryMeaningAxes
  ↓
derive_category_profile(...) → новая версия (is_active=false)
  ↓
smoke-eval → если ok → активация
  ↓
snapshot → git diff для review
```

Это — автоматический pipeline. Руками только в случае, если smoke-eval провалился и оператор решает, что делать.

---

## 8. Versioning

### 8.1. Нумерация версий профиля

Формат `version`: `"v1.<category_id>.<YYYY-MM-DD>-<suffix>"`.

Примеры:
- `"v1.812.2026-04-24-auto"` — автогенерация
- `"v1.812.2026-04-25-manual-fix"` — ручная правка (исключительный случай)
- `"v1.812.2026-04-26-corpus-refresh"` — после обновления CSV

### 8.2. Нумерация схемы

`schema_version` в payload — отдельное значение, не связано с `version` записи:
- `"category_profile_v1"` — текущая.
- При breaking-изменении схемы (`v2`) loader должен читать обе и либо мигрировать `v1→v2` на лету, либо считать `v1` невалидной после явной миграции БД.

### 8.3. Мигрирование

Phase 0 — только `v1`. Любые последующие `v1.x` добавляют опциональные поля с дефолтами, чтобы старые снимки работали.

---

## 9. Self-check

Перед активацией `derive_category_profile` обязан прогнать валидатор. Активация с `self_check.status != "passed"` запрещена на уровне loader'а.

### 9.1. Обязательные проверки

| Название | Что проверяет | Fail-условие |
|---|---|---|
| `schema_version_is_v1` | строгий лит `"category_profile_v1"` | отличается |
| `subject_non_empty` | `primary` и хотя бы один alias | пусто |
| `subject_coverage` | ≥70% запросов категории матчатся через `primary_aliases` OR `related_but_different` | <70% |
| `hard_conflicts_cover_related` | для каждого `related_but_different.subject` есть hard-конфликт | отсутствует |
| `hard_conflicts_syntax` | все predicates резолвятся loader'ом | неизвестный predicate |
| `bucket_cutoffs_monotonic` | `primary > secondary > broad > 0` | нарушено |
| `constraint_references` | каждый `constraint` из `constraints` используется минимум в одном `hard_conflict` ИЛИ в `guards` | «мёртвый» constraint |
| `guards_target_known_fields` | `target.field` принадлежит whitelist'у (`volume_ml`, `color`, `material`, `quantity`, `design`, `feature`, `compatibility`, `thermal`, `transparency`, ...) | неизвестный field |
| `eval_smoke` | если есть ≥20 labels — прогнать `matcher_v2 + eval`, accuracy ≥ `eval_smoke_min_accuracy` (дефолт 0.60 относительно baseline) | ниже порога |
| `no_cross_category_duplication` | нет полей, дублирующих `global_vocabulary` (цвета, получатели, материалы) | найдены |

### 9.2. Observability

Каждый прогон `derive_category_profile` пишет:
- строку в `seo_category_profile_derive_runs` (новая таблица, Phase 0 Step 3): `run_id, project_id, category_id, started_at, finished_at, status, self_check_json, eval_baseline_accuracy, eval_new_accuracy, diff_summary`.
- снимок `before.json` / `after.json` / `diff.json` в `config/seo/category_profiles/<cat>/_runs/<run_id>/`.

Это нужно, чтобы оператор мог ответить на вопрос «почему профиль перегенерился и что изменилось».

---

## 10. Три примера

### 10.1. Пример: категория 812 (кружки) — реальный, от корпуса

Полный payload — см. раздел 3 (основной пример в начале). Ниже — ключевые поля для быстрой сверки:

```json
{
  "subject": {
    "primary": "кружка",
    "primary_aliases": ["кружка", "кружки", "mug"],
    "related_but_different": [
      {"subject": "термокружка", "aliases": ["термокруж", "термостакан"]},
      {"subject": "стакан",       "aliases": ["стакан"]},
      {"subject": "бокал",        "aliases": ["бокал"]}
    ],
    "detection_hints": {
      "token_prefixes": ["круж"],
      "negative_token_prefixes": ["термокруж", "стакан", "бокал", "поильник"]
    }
  },
  "scoring": {
    "materials_relevant": ["glass", "ceramic", "porcelain", "metal"]
  }
}
```

Ожидаемые self-check значения для 812:
- `csv_subject_sanity` ≈ **1.0** — поле `Больше всего заказов в предмете` = `"Кружки"` для всех 31 921 строк (выгрузка по своей категории, см. `CONTEXT_PRIMER.md §3.1.2`).
- `subject_coverage` (доля `seo_queries_normalized`, у которых хотя бы один токен совпадает с `subject.detection_hints.token_prefixes` и не отрицается `negative_token_prefixes`) — ожидается **≥ 95%**, точная цифра калибруется на baseline.

### 10.2. Пример: категория «тарелки» (гипотетический)

```json
{
  "schema_version": "category_profile_v1",
  "subject": {
    "primary": "тарелка",
    "primary_aliases": ["тарелка", "тарелки", "тарелку", "plate"],
    "related_but_different": [
      {"subject": "миска",   "aliases": ["миска", "миски", "bowl"]},
      {"subject": "салатник","aliases": ["салатник"]},
      {"subject": "блюдо",   "aliases": ["блюдо", "блюдце"]},
      {"subject": "поднос",  "aliases": ["поднос", "tray"]}
    ],
    "detection_hints": {
      "token_prefixes": ["тарел"],
      "negative_token_prefixes": ["мис", "салат", "блюд", "подн"]
    }
  },
  "product_type_aliases": {
    "тарелка":     {"match_any_prefix": ["тарел"], "score_bonus": 0.22},
    "десертная":   {"match_any_prefix": ["десерт"], "score_bonus": 0.16},
    "суповая":     {"match_any_prefix": ["суп"],    "score_bonus": 0.16}
  },
  "constraints": {
    "derive_from_query_tokens": [
      {"constraint": "deep_use_case",   "when_query_contains_any": ["глубок", "суповая", "для супа"]},
      {"constraint": "flat_use_case",   "when_query_contains_any": ["плоская", "сервировоч"]},
      {"constraint": "set",             "when_query_contains_any": ["набор", "комплект", "6 шт", "4 шт"]}
    ],
    "derive_from_sku_meaning": [
      {"constraint": "deep_use_case",  "when_functional_attribute_contains": ["глубок"]},
      {"constraint": "flat_use_case",  "when_functional_attribute_contains": ["плоск"]}
    ]
  },
  "hard_conflicts": [
    {
      "name": "miska_not_tarelka",
      "when_query_has": {"product_type": "миска"},
      "requires_sku_any": [{"product_type": "миска"}, {"token_prefix": "мис"}],
      "message": "query about bowls, SKU is flat plate"
    },
    {
      "name": "set_quantity_required",
      "when_query_has": {"constraint_prefix": "set"},
      "requires_sku_any": [{"constraint_prefix": "set"}],
      "message": "query requires a set, SKU is single item"
    }
  ],
  "scoring": {
    "weights": { ... как у 812 ... },
    "bucket_cutoffs": {"primary": 0.60, "secondary": 0.35, "broad": 0.15},
    "bucket_caps":    {"primary": 100, "secondary": 300, "broad": 500},
    "enforce_material_overlap": true,
    "materials_relevant": ["porcelain", "ceramic", "glass", "wood", "plastic"]
  }
}
```

**Чем отличается от 812**: другая primary, другие «родственные, но разные» (миска/салатник, а не термокружка/стакан), другие relevant-материалы (добавилось дерево).

### 10.3. Пример: категория «рюкзаки» (гипотетический, семантически далёкий)

```json
{
  "schema_version": "category_profile_v1",
  "subject": {
    "primary": "рюкзак",
    "primary_aliases": ["рюкзак", "рюкзаки", "backpack", "ранец"],
    "related_but_different": [
      {"subject": "сумка",      "aliases": ["сумка", "сумки", "bag", "шопер"]},
      {"subject": "портфель",   "aliases": ["портфель"]},
      {"subject": "чемодан",    "aliases": ["чемодан", "suitcase"]},
      {"subject": "тубус",      "aliases": ["тубус"]}
    ],
    "detection_hints": {
      "token_prefixes": ["рюкз", "ранц"],
      "negative_token_prefixes": ["сум", "шопер", "порт", "чемо"]
    }
  },
  "product_type_aliases": {
    "рюкзак":         {"match_any_prefix": ["рюкз", "ранц"], "score_bonus": 0.22},
    "рюкзак школьный":{"match_any_prefix": ["школьн"],       "score_bonus": 0.18}
  },
  "constraints": {
    "derive_from_query_tokens": [
      {"constraint": "laptop_compartment", "when_query_contains_any": ["для ноутбука", "с отделением под ноут", "15.6", "17 дюйм"]},
      {"constraint": "waterproof",         "when_query_contains_any": ["водонепроницаем", "непромокаем", "водозащит"]},
      {"constraint": "school_use_case",    "when_query_contains_any": ["школьн", "для школы", "для первоклассн"]},
      {"constraint": "hiking_use_case",    "when_query_contains_any": ["туристич", "походн", "трекинг"]}
    ],
    "derive_from_sku_meaning": [
      {"constraint": "laptop_compartment", "when_functional_attribute_contains": ["отдел под ноут"]},
      {"constraint": "waterproof",         "when_functional_attribute_contains": ["водоотталкив", "водозащит"]}
    ]
  },
  "hard_conflicts": [
    {
      "name": "sumka_not_ryukzak",
      "when_query_has": {"product_type": "сумка"},
      "requires_sku_any": [{"product_type": "сумка"}, {"token_prefix": "сум"}],
      "message": "query about handbag, SKU is backpack"
    },
    {
      "name": "laptop_required",
      "when_query_has": {"constraint": "laptop_compartment"},
      "requires_sku_any": [{"constraint": "laptop_compartment"}],
      "message": "query requires laptop compartment, SKU has no laptop sleeve"
    },
    {
      "name": "waterproof_required",
      "when_query_has": {"constraint": "waterproof"},
      "requires_sku_any": [{"constraint": "waterproof"}],
      "message": "query requires waterproof material, SKU is not"
    }
  ],
  "scoring": {
    "weights": { ... },
    "bucket_cutoffs": {"primary": 0.60, "secondary": 0.35, "broad": 0.15},
    "bucket_caps":    {"primary": 80, "secondary": 200, "broad": 400},
    "enforce_material_overlap": false,
    "materials_relevant": ["textile", "leather", "polyester", "nylon"]
  },
  "user_bucket_labels": {
    "primary":   "Целевые",
    "secondary": "Близкие",
    "broad":     "Слишком общие",
    "rejected":  "Не подходят"
  },
  "sku_guards": {
    "characteristic_mappings": [
      {"name_contains": "объем",       "target": {"type": "numeric",   "field": "volume_l",    "parser": "int_first"}},
      {"name_contains": "цвет",        "target": {"type": "attribute", "field": "color"}},
      {"name_contains": "материал",    "target": {"type": "attribute", "field": "material"}},
      {"name_contains": "размер ноутб","target": {"type": "numeric",   "field": "laptop_inch", "parser": "int_first"}}
    ],
    "functional_token_mappings": [
      {"when_contains": "водонепроница", "target": {"type": "compatibility", "field": "waterproof", "value": true}},
      {"when_contains": "ортопедич",     "target": {"type": "compatibility", "field": "orthopedic", "value": true}}
    ]
  }
}
```

**Чем отличается от 812**:
- совсем другая subject-онтология (сумка vs рюкзак — ключевой конфликт);
- `volume_ml` стал `volume_l`;
- `materials_relevant` — текстиль, кожа, полиэстер (а не керамика);
- `enforce_material_overlap: false` — для сумок материал часто не важен покупателю так, как для посуды;
- появился категорийный атрибут `laptop_inch` (без аналога у кружек);
- бакеты переименованы (`"Целевые"` вместо `"Лучшие"`) — категория более B2C-нишевая.

**Эти три примера — не выдумка ради примеров.** Каждое различие — это конкретная строка кода, которую нельзя захардкодить в общем месте: `_sku_features` не должен содержать ни «круж», ни «рюкз», ни «мис». Только читать профиль.

---

## 11. Что профиль **не** содержит

Список того, что выглядит категорийным, но категорийным не является и живёт в другом месте:

| Штука | Где лежит | Почему не в профиле |
|---|---|---|
| Цвета и их синонимы | `global_vocabulary.json::color_taxonomy` | универсальны для всех категорий |
| Получатели (подарок кому) | `global_vocabulary.json::recipient_synonyms` | универсальны |
| Выразительность (милая, уютная) | `global_vocabulary.json::expressive_synonyms` | универсальны |
| Аудитория (женская, мужская, детская) | `global_vocabulary.json::audience_taxonomy` | универсальны |
| Regex объёма/количества | код (`_VOLUME_RE`, `_QUANTITY_RE`) или `global_vocabulary.json::numeric_parsers` | универсальны |
| Экономические метрики | `seo_queries_normalized.sample_source_payload` | это сырые данные, не правила |
| Ярлыки для конкретных SKU | `seo_sku_query_sets`, `seo_matcher_results` | это результаты, не конфиг |
| Промпты LLM-генерации | `services/seo/.../prompts/` в коде | это инструменты, не конфиг |

---

## 12. Agent contract (как агент должен работать с этим документом)

### 12.1. Читать перед любым изменением

Агент, прежде чем писать код, касающийся `matcher_v2`, `atoms/v1/guards.py` или `query_meaning_matcher/matcher.py`, обязан:
1. прочитать этот документ целиком;
2. при несовпадении кода и спецификации — считать источником истины **спецификацию** и привести код к ней;
3. любые отклонения от контракта обсуждаются с оператором **до** написания кода, не после.

### 12.2. Запрещённые действия

- ❌ Добавлять категорийные литералы (названия subject'ов, токены категории) в `atoms/v1/guards.py` или `query_meaning_matcher/matcher.py`.
- ❌ Читать `SeoCategoryProfile` в обход `load_active_profile`.
- ❌ Мутировать `CategoryProfile`-объект (он `frozen=True`; попытка должна быть TypeError'ом).
- ❌ Создавать профиль вручную SQL'ом в проде (только через `derive_category_profile` + self-check).
- ❌ Включать `is_active=true` без прошедшего `self_check.status = passed`.

### 12.3. Обязательные действия

- ✅ Любая новая логика с категорийной семантикой → новое поле профиля + декларативный интерпретатор в коде.
- ✅ Любое расширение схемы → обновление этого документа в том же PR.
- ✅ Любое изменение `schema_version` → явный migration-плейбук в `PHASE_0_EXECUTION_PLAN.md` или аналогичном документе следующей фазы.

---

## 13. Open questions (на обсуждение с оператором)

Эти вопросы намеренно оставлены без ответа и должны быть закрыты до окончания Phase 0:

1. **Material enforcement threshold.** Для некоторых категорий (сумки, одежда) материал менее критичен, чем для посуды. Хардкод `enforce_material_overlap: true/false` — достаточно, или нужен мягкий вариант (penalty, не reject)? — Предложение: начать с булева, расширить до `material_mismatch_penalty: float` в `v1.1` если понадобится.

2. **LLM vs эвристика в derive.** Какая доля полей должна приходить от LLM, а какая — от эвристики? — Текущее предложение: `subject.primary_aliases`, `related_but_different`, `hard_conflicts` — LLM + валидация; `detection_hints`, `product_type_aliases.match_any_prefix` — чистая эвристика на токенах; `scoring.weights/cutoffs` — константы из 812-профиля (калибруются в Phase 1+).

3. **Review signal в профиле.** Отзывы уже участвуют в `CategoryMeaningAxes` (через `expressive_llm`). Нужно ли дублировать какие-то извлечённые из отзывов паттерны в профиль, или достаточно «axes → profile» цепочки? — Предложение: не дублировать; если `axes` говорит «частый жалобы-кейс `X`», это идёт в `negative_constraint_axes`, оттуда в `constraints.derive_from_query_tokens` с constraint «negative_<X>» и в `hard_conflicts`.

4. **Versioning границы.** Считаем ли мы изменение `scoring.weights[*]` breaking-изменением (т. е. нужен новый `version` с A/B?) или micro-tune? — Предложение: любое изменение `weights` или `bucket_cutoffs` → новая `version`, обязательный eval-прогон до активации. Изменение только `user_bucket_labels` → не требует eval.

---

## 14. Changelog этого документа

- **2026-04-24** — v1.0 (initial). Зафиксирован контракт для Phase 0.

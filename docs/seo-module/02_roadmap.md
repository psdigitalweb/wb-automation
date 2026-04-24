# SEO Module — Product Roadmap

Date: 2026-04-21

## 0. Product Goal

SEO module должен:

- понимать смысловой контекст поисковых запросов WB;
- понимать смысловой контекст товара;
- выбирать запросы, наиболее близкие к товару по смыслу и ожидаемой конверсии;
- отсеивать частотные, но слишком широкие или нерелевантные запросы;
- генерировать SEO-оптимизированные title/description на основе выбранных запросов;
- объяснять, почему запрос выбран или отклонен.

Ключевой пример:

- `кружка для чая` может быть частотным, но слишком generic;
- `милая кружка`, `кружка как в пинтерест` могут быть более конверсионными для товара с эстетикой, мемами и милотой.

---

## 1. Current State

Текущая стадия: **pre-MVP / R&D prototype**.

Уже есть:

- WB query CSV import;
- query normalization;
- deterministic query clustering;
- hybrid annotation;
- query profile extraction;
- debug scoring по query clusters;
- canonical meaning objects:
  - `CategoryMeaning`;
  - `ProductProjection`;
  - `QueryMeaning`;
- offline LLM-backed category expressive extraction через reviews + titles;
- debug endpoints/pages for query import and query pipeline.

Главный разрыв:

> новые meaning-сущности пока не собраны в end-to-end контур
> `SKU/Product Meaning -> Query Meaning -> Matcher -> Scoring -> Generation`.

---

## 2. Phase 1 — SKU Meaning Preview / Annotation Tool

Цель:

создать инструмент, который позволяет получить и проверить смысл товара до построения eval и matcher.

Важно:

- это не production SKU meaning extractor;
- это инструмент для human-verified эталона и быстрой проверки LLM draft;
- он нужен до eval-набора, потому что без SKU meaning нельзя системно оценивать релевантность запросов.

### In Scope

- показать raw SKU data:
  - title;
  - description;
  - attributes / characteristics;
  - reviews;
  - photos later;
- показать текущий `ProductProjection`;
- сформировать LLM draft SKU meaning;
- дать возможность вручную подтвердить/исправить meaning;
- сохранить human-verified SKU meaning как эталон для eval.

### Minimal SKU Meaning Shape

```json
{
  "functional": {
    "product_type": "кружка",
    "material": ["керамика"],
    "volume": ["450 мл"],
    "use_cases": ["для чая", "для кофе", "подарок"],
    "hard_attributes": ["большая", "с принтом"]
  },
  "expressive": {
    "vibes": ["милая", "эстетичная", "мемная"],
    "style": ["pinterest", "cute"],
    "emotional_context": ["подарок подруге", "радость", "уют"]
  },
  "negative_constraints": [
    "не классическая строгая кружка",
    "не термокружка"
  ]
}
```

### Done Criteria

- можно открыть один SKU и увидеть его draft meaning;
- можно вручную поправить functional/expressive/negative constraints;
- есть сохраненный эталон meaning хотя бы для 20-50 SKU в одной категории.

---

## 3. Phase 2 — Eval Dataset

Цель:

создать маленький эталон, на котором можно проверять, выбирает ли система правильные запросы.

### Initial Categories

- `Кружки`;
- `Тарелки` optional second category.

### Dataset Shape

Для каждого SKU:

- human-verified SKU meaning;
- список query clusters;
- ручная разметка релевантности:
  - `highly_relevant`;
  - `maybe_relevant`;
  - `too_broad`;
  - `irrelevant`;
  - `conflict`;
  - `dangerous_claim`.

### Done Criteria

- есть минимум 20 SKU и 100-300 query cluster judgments;
- есть примеры широких, но частотных запросов;
- есть примеры expressive-relevant запросов;
- можно сравнивать ранжирование системы с эталоном.

---

## 4. Phase 3 — LLM Query Meaning

Цель:

заменить слабый proxy `language_markers -> expressive.vibes` на полноценное query meaning для query clusters.

### Query Meaning Must Include

- product-type intent;
- use-case intent;
- attribute intent;
- expressive intent;
- broadness / genericness;
- commercial relevance;
- conflict-prone promises.

### Execution Mode

- offline / precompute;
- per project x category x query cluster;
- cache by model + prompt version + input hash;
- no hot-path LLM dependency.

### Done Criteria

- для query clusters есть structured `QueryMeaning`;
- система отличает generic `кружка для чая` от expressive `милая кружка`;
- результаты проверены на Phase 2 eval dataset.

---

## 5. Phase 4 — Matcher MVP

Цель:

создать явный слой:

> `SKU/Product Meaning <-> Query Meaning`

Matcher не считает финальный score. Он возвращает объяснимые match signals.

### Matcher Signals

- product type match / miss;
- use-case match / miss;
- attribute match / conflict;
- expressive alignment;
- broad/generic penalty signal;
- missing critical proof;
- query promises not supported by SKU.

### Done Criteria

- matcher умеет объяснить, почему `милая кружка` выше, чем `кружка для чая`;
- matcher умеет объяснить hard conflict, например `термокружка` для обычной керамической кружки;
- matcher output пригоден для scoring без raw text matching.

---

## 6. Phase 5 — Meaning-Based Scoring

Цель:

перевести ranking с raw marker matching на explainable meaning-based scoring.

### Principle

Scoring должен быть additive:

```text
score =
  functional_score
  + expressive_score
  + demand_score
  + penalties
```

### Required Components

- functional alignment;
- expressive alignment;
- demand/frequency signal;
- genericness penalty;
- conflict penalty;
- confidence penalty;
- competition signal later, but architecture must leave slot for it.

### Done Criteria

- top queries for SKU are ranked through matcher signals;
- score breakdown explains every decision;
- quality is measured against Phase 2 eval dataset.

---

## 7. Phase 6 — SEO Generation MVP

Цель:

генерировать title/description only after query selection is reliable.

### Inputs

- selected query clusters;
- SKU/Product Meaning;
- matcher/scoring explanation;
- current title/description;
- marketplace constraints;
- forbidden claims / conflicts.

### Outputs

- generated title;
- generated description;
- query coverage snapshot;
- safety/claim validation notes.

### Done Criteria

- generation uses only selected relevant queries;
- text does not promise unsupported attributes;
- output stores query snapshot and score breakdown;
- human review flow exists before publishing.

---

## 8. Phase 7 — Productionization & Feedback Loop

Цель:

перевести MVP в устойчивый продуктовый workflow.

### In Scope

- batch execution;
- versioning and rollback;
- monitoring;
- cost controls;
- feedback from real performance;
- weight tuning;
- category expansion.

### Done Criteria

- можно запускать pipeline по проекту/категории;
- результаты воспроизводимы;
- есть история версий;
- можно сравнивать старый и новый SEO content;
- система получает обратную связь по performance.

---

## 9. Product Sequencing Rule

Не начинать масштабную generation, UI polish или batch по всем категориям до того, как:

1. SKU meaning можно проверить вручную;
2. есть маленький eval dataset;
3. matcher/scoring показывает качество на eval.

Главный риск сейчас:

> красиво сгенерировать SEO-текст на основе неправильно выбранных запросов.

---

## 10. Current R&D Decision — Atoms v1

Дата фиксации: 2026-04-22.

По итогам shadow experiment на категории `812` / Кружки и 191 manual label текущий direction меняется:

```text
SKU evidence + reviews + vision -> SKU Atoms
Query clusters + LLM -> Query Atoms
SKU Atoms x Query Atoms -> eligibility-first matcher -> buckets
```

Ключевые результаты:

- current matcher: `15.8%` accuracy, `21.4%` primary precision, `88` bad primary;
- atoms v0.2b: `58.1%` accuracy, `58.8%` primary precision, `28` bad primary;
- atoms + Vision Audience v1: `60.7%` accuracy, `59.4%` primary precision, `28` bad primary.

Решение:

- продолжать через `Atoms v1`;
- embeddings оставить для candidate retrieval, но не для финального bucket decision;
- vision использовать как слой SKU understanding, где visual facts могут быть сильным evidence, а audience/occasion только soft boost;
- production SEO generation не начинать до прохождения eval gates.

Подробный план: [23_atoms_v1_design_and_implementation_plan.md](23_atoms_v1_design_and_implementation_plan.md).

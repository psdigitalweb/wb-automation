# SEO Module Production Readiness Plan

> Статус: рабочий план перехода от Phase 0 к production-ready продукту.  
> Дата: 2026-04-25.  
> Аудитория: CEO / product owner / engineering lead.  
> Главная цель: превратить SEO-модуль из работающего прототипа на категории 812 в воспроизводимый продуктовый pipeline для нескольких категорий без правки кода.

---

## 1. Executive Summary

Сейчас модуль уже имеет хорошую основу: есть matcher v2, replayable trace, meaning atoms, category profile, eval artifacts и UI-черновики. Но продукт еще нельзя считать production-ready, потому что ключевая гипотеза не доказана: система должна работать на новой категории без ручной правки Python-кода.

Главный блокер: `derive_category_profile` пока фактически работает как skeleton под категорию 812. Phase 1 preflight на категории 2841 показал, что данные и axes есть, но профиль не создается: dry-run падает с `NotImplementedError: skeleton only supports 812`.

Поэтому правильный путь:

1. Сначала закрыть generic profile derive.
2. Потом доказать вторую категорию end-to-end.
3. Потом онбордить 5-7 категорий.
4. Только после этого перестраивать UI в production-flow.
5. Затем добавить export brief.

Нельзя начинать с красивого UI или brief export: это создаст видимость продукта поверх backend, который еще не доказал переносимость.

---

## 2. Что Считаем Production-Ready

SEO-модуль production-ready, когда оператор может пройти путь:

```text
CSV категории -> bootstrap -> derive profile -> activate profile -> выбрать SKU
-> matcher v2 -> approve queries -> preview generation -> export brief
```

без:

- правки Python-кода;
- ручного SQL;
- ручного редактирования JSON профиля;
- чтения внутренних спецификаций;
- помощи разработчика;
- скрытого fallback на 812/legacy-логику.

Минимальный production gate:

1. Не менее 2 разных категорий прошли полный backend-flow без правки кода.
2. Не менее 5-7 категорий имеют active `SeoCategoryProfile`.
3. Для каждой категории есть 2-3 SKU с осмысленными matcher buckets.
4. Каждый matcher result связан с `SeoMatcherRun`, profile version и quality mode.
5. Generated text не выглядит production-ready до явного approval/export.
6. В runtime-коде не появляются новые category literals.

---

## 3. Принцип Управления Риском

Мы не строим "большой продукт" сразу. Мы двигаемся через доказательства.

Каждый следующий слой строится только после того, как предыдущий доказан:

```text
Generic backend -> second category -> 5-7 categories -> operator UI -> brief export
```

Если слой не доказан, следующий слой не начинаем. Это снижает риск дорогой переделки UI, данных и операторских процессов.

---

## 4. Phase 1A: Generic Category Profile Derive

### Цель

Сделать `derive_category_profile(project_id, category_id)` реально category-agnostic.

Это значит: профиль категории должен строиться из уже существующих данных категории, а не из committed template под 812.

### Что Уже Есть

- `SeoCategoryMeaningAxes` содержит category axes.
- `SeoQueryNormalized` содержит корпус запросов.
- `SeoCategoryProfile` уже есть как таблица и runtime wrapper.
- `SeoCategoryProfileDeriveRun` уже есть для observability.
- `matcher_v2` уже умеет читать active profile.

### Что Нужно Изменить В Логике

Текущий skeleton path заменить на generic pipeline:

```text
corpus evidence
-> deterministic heuristic
-> optional LLM refinement
-> profile payload
-> self-check
-> snapshot
-> inactive DB profile
```

Минимальные правила derive:

1. `subject.primary` берется из `SeoCategoryMeaningAxes.axes_payload.product_type_axes`.
2. `primary_aliases` строятся из частотных query tokens и axes.
3. `related_but_different` берется из соседних product_type axes + LLM refinement.
4. `detection_hints` строятся из token prefixes.
5. `constraints` строятся из `constraint_axes`, query tokens и SKU/product evidence.
6. `hard_conflicts` создаются для related subjects и hard constraints.
7. `scoring.weights`, `bucket_cutoffs`, `bucket_caps` берутся из default profile config, не из category economics.
8. `sku_guards` строятся из product characteristics.
9. `query_guards` строятся из query tokens и constraints.

### Документация

Обновить:

- `CATEGORY_PROFILE_SPEC.md`: уточнить, какие поля generic derive обязан заполнить в v1.
- `ROADMAP.md`: Phase 1 теперь включает generic derive, а не только validation.
- `CONTEXT_PRIMER.md`: зафиксировать, что 812 runtime работает, но generic derive является текущим переходным блокером до закрытия Phase 1A.

### Архитектура

Новые функции должны быть небольшими и проверяемыми:

```text
category_profile_derive.py
  - orchestrates derive flow

category_profile_derive/
  - corpus_reader.py
  - heuristic.py
  - llm_refine.py
  - constraint_builder.py
  - guard_builder.py
```

Если не хотим сразу заводить подпакет, можно начать с одного файла, но с четкими внутренними функциями. Важнее не форма, а отсутствие category literals.

### Код

Работы:

1. Убрать `category_id != 812 -> NotImplementedError`.
2. Оставить 812 template только как fixture/test artifact, не как runtime path.
3. Реализовать generic derive по axes/corpus.
4. Добавить dry-run для категории 2841.
5. Добавить persist inactive profile.
6. Не активировать автоматически.

### БД

Новых таблиц на Phase 1A не требуется.

Используем существующие:

- `seo_category_profiles`
- `seo_category_profile_derive_runs`
- `seo_category_meaning_axes`
- `seo_queries_normalized`
- `seo_category_matching_readiness`

### Миграции

Миграции не нужны, если текущих колонок хватает.

Миграция нужна только если выяснится, что для production критичен один из инвариантов:

- partial unique index на active profile per `(project_id, category_id)`;
- отдельный статус candidate profile;
- отдельное поле для profile activation audit.

Рекомендация: не делать миграцию в Phase 1A, если можно закрыть задачу без нее.

### Тесты

Минимум:

1. Unit tests для heuristic на synthetic axes.
2. Test: derive dry-run работает для не-812 категории.
3. Test: generated payload проходит `CategoryProfilePayloadV1`.
4. Test: no new category literals in active derive/matcher/guards.
5. Regression: 812 derive не ломается.

### Definition of Done

Phase 1A закрыта, когда:

- dry-run для 2841 возвращает `category_profile_v1`;
- `self_check.status = passed` или failed только по понятной data-quality причине;
- профиль не содержит economic scoring inputs;
- код не содержит новых category literals;
- snapshot можно прочитать и review'ить;
- профиль еще не активируется автоматически.

---

## 5. Phase 1B: Валидация На Второй Категории

### Цель

Доказать, что Phase 0 была не "812 переименовали", а настоящий переносимый backend.

Рекомендуемая категория: 2841, потому что уже есть данные, axes и preflight artifacts.

### Шаги

1. Прогнать dry-run derive для 2841.
2. Review self-check.
3. Persist inactive profile.
4. Review diff/snapshot.
5. Activate profile через API/CLI.
6. Прогнать matcher_v2 для 3-5 SKU категории.
7. Оператор смотрит buckets в compare/matcher-run UI.
8. Написать `phase1/CATEGORY_2841_REPORT.md`.

### Логика Принятия

Успех не означает идеальную accuracy. Для второй категории пока нет labels.

Успех означает:

- профиль создается автоматически;
- matcher не падает;
- buckets выглядят продуктово осмысленно;
- не потребовалась правка Python-кода под 2841.

### Документация

Создать:

- `docs/seo-module/phase1/CATEGORY_2841_REPORT.md`

В отчете:

- profile summary;
- top related subjects;
- hard conflicts;
- 3-5 SKU smoke results;
- проблемы derive;
- решение: proceed / fix derive / stop.

### БД

Записи, которые должны появиться:

- inactive then active `SeoCategoryProfile` for 2841;
- `SeoCategoryProfileDeriveRun`;
- `SeoMatcherRun` for selected SKU;
- `SeoMatcherResult` rows.

### Миграции

Не требуются.

### Definition of Done

Phase 1B закрыта, когда:

- категория 2841 имеет ровно один active profile;
- matcher_v2 работает для выбранных SKU;
- оператор подтверждает, что buckets осмысленны;
- все проблемы записаны в report;
- ни одна проблема не замаскирована UI-слоем.

---

## 6. Phase 2: Онбординг 5-7 Категорий

### Цель

Проверить не один удачный перенос, а повторяемость процесса.

### Шаги На Каждую Категорию

```text
CSV import
-> bootstrap
-> axes
-> derive dry-run
-> self-check
-> persist inactive profile
-> activate
-> matcher smoke on 2-3 SKU
-> operator review
```

### Что Исправляем В Этой Фазе

Только generic derive heuristics и profile interpretation.

Не делаем:

- новый UI;
- brief export;
- WB feedback loop;
- scoring по orders/conversion;
- ручные профили под каждую категорию.

### Архитектурный Контроль

Если категория требует правки Python-кода, это blocker.

Допустимые причины:

- нужно улучшить generic derive;
- нужно добавить optional поле в profile v1.1;
- данные CSV плохие.

Недопустимые причины:

- добавить `if category_id == X`;
- добавить новый category literal в matcher;
- вручную переписать profile JSON без фиксации причины.

### БД

После Phase 2 должны быть видны:

- 5-7 active profiles;
- derive-run history по каждой категории;
- latest matcher runs по smoke SKU;
- readiness status по каждой категории.

### Миграции

Возможная миграция после Phase 2:

1. Partial unique index:
   ```sql
   UNIQUE (project_id, category_id) WHERE is_active = true
   ```
2. Profile activation audit, если rollback/activation начали использоваться часто.
3. Query-set revisioning, если operator approval уже активно используется.

Рекомендация: не делать эти миграции до того, как появятся реальные паттерны на 5-7 категориях.

### Definition of Done

Phase 2 закрыта, когда:

- 5-7 категорий активированы без category-specific code changes;
- для каждой категории есть smoke matcher results;
- оператор видит ценность шортлистов;
- список повторяющихся проблем derive собран и приоритизирован.

---

## 7. Phase 3: Production UI

### Цель

Сделать не набор debug-страниц, а понятный операторский workflow.

### Главный Принцип

UI должен показывать один следующий шаг, а не всю внутреннюю систему.

Целевой flow:

```text
Categories -> Category readiness -> SKU list -> SKU workbench
-> query approval -> generation preview -> brief export
```

### Что Переносим В Debug

- eval pages;
- matcher-run raw viewer;
- compare pages;
- raw profile JSON;
- derive-runs history;
- retention cleanup.

### Что Должно Быть В Основном UI

1. Категория готова или нет.
2. Почему не готова.
3. Какое действие нужно оператору.
4. Какие SKU готовы к работе.
5. Какие queries система предлагает.
6. Почему query попал в bucket.
7. Что approved.
8. Что можно экспортировать.

### Код

Работы:

1. Создать новые routes под target workflow.
2. Старые `/seo/*` routes пометить deprecated или убрать из основной навигации.
3. Использовать существующие badges:
   - `QualityBadge`
   - `ApprovalStateBadge`
   - `CategoryTierBadge`
4. Добавить breadcrumbs.
5. Добавить explicit empty/error states.

### БД

Новых таблиц для Phase 3 не требуется.

UI должен читать существующие:

- readiness;
- profiles;
- derive runs;
- matcher runs;
- query sets;
- generation previews.

### Миграции

Не требуются, если не добавляем export.

### Definition of Done

Phase 3 закрыта, когда оператор может пройти happy path без CLI и без debug screens.

---

## 8. Phase 4: Brief Export

### Цель

Сделать конечный бизнес-артефакт: brief для копирайтера.

### Что Экспортируем

Markdown brief:

- SKU;
- product snapshot;
- approved queries by bucket;
- draft title/description/features;
- must-cover atoms;
- must-not-cover conflicts;
- audit section:
  - matcher_run_id;
  - profile version;
  - quality mode;
  - generated_at.

### БД

Нужна новая таблица:

```text
seo_brief_exports
```

Минимальные поля:

- id
- project_id
- category_id
- nm_id
- query_set_id
- matcher_run_id
- profile_version
- quality_mode
- brief_markdown_snapshot
- exported_by
- exported_at

### Миграция

Добавить Alembic migration для `seo_brief_exports`.

### Код

1. Backend service: build brief markdown.
2. Endpoint: create/download/copy brief.
3. UI page: `/sku/{nm_id}/brief`.
4. Export history page.

### Definition of Done

Phase 4 закрыта, когда минимум один SKU из каждой onboarded категории проходит:

```text
approved query set -> generation preview -> exported brief
```

---

## 9. Что Не Делаем До Production-Ready

Не делаем:

1. WB feedback loop.
2. AI Vision как обязательный слой.
3. Active learning.
4. Batch generation.
5. Auto-publish в WB.
6. Scoring по категорийным orders/conversion.
7. Ручную разметку каждой категории как условие запуска.
8. Новый большой UI до generic derive.

Причина простая: это увеличит сложность раньше, чем доказана базовая переносимость продукта.

---

## 10. Главные Риски

### Риск 1: Generic derive дает плохие профили

Митигация:

- dry-run first;
- self-check;
- inactive profile review;
- second category report;
- улучшать heuristic, не добавлять category-specific branches.

### Риск 2: UI начнут делать раньше backend

Митигация:

- Phase 3 начинается только после Phase 1B.
- До этого UI changes только bugfix/debug.

### Риск 3: Команда начнет оптимизировать по orders/conversion

Митигация:

- запрет оставить в AGENTS/spec/test plan;
- добавить negative tests;
- использовать frequency только как demand/corpus ordering, не как SKU relevance truth.

### Риск 4: JSON-поля станут непрозрачными

Митигация:

- snapshots;
- derive-run reports;
- matcher trace;
- brief audit section.

---

## 11. Управленческий План По Неделям

### Неделя 1

Фокус: generic derive.

Выход:

- derive dry-run для 2841;
- self-check report;
- no new category literals;
- updated docs.

### Неделя 2

Фокус: вторая категория end-to-end.

Выход:

- active profile 2841;
- matcher smoke на 3-5 SKU;
- `CATEGORY_2841_REPORT.md`;
- решение: Phase 2 go/no-go.

### Недели 3-4

Фокус: 5-7 категорий.

Выход:

- active profiles;
- smoke matcher runs;
- onboarding report;
- список recurring derive problems.

### Недели 5-6

Фокус: production UI.

Выход:

- operator happy path;
- debug screens separated;
- no CLI needed for normal operation.

### Неделя 7

Фокус: brief export.

Выход:

- `seo_brief_exports`;
- markdown export;
- audit trail.

---

## 12. CEO-Level Go / No-Go Criteria

### Go To Production UI

Можно начинать Phase 3, если:

- generic derive работает;
- 2841 прошла end-to-end;
- нет Python changes под конкретную категорию;
- оператор подтвердил смысл buckets.

### Go To Brief Export

Можно начинать Phase 4, если:

- есть 5-7 категорий;
- approved query set flow понятен;
- generation preview явно не production;
- matcher/profile audit сохраняется.

### Go To Production Use

Можно давать оператору production-flow, если:

- happy path проходит без разработчика;
- export содержит audit;
- fallback/debug состояния видны;
- ошибки объясняют следующий шаг.

---

## 13. Финальный Вердикт

Самый высокий ROI сейчас не в новом UI и не в генерации текста. Самый высокий ROI - закрыть generic `derive_category_profile`.

Это узкое горло всего продукта. Пока оно не закрыто, production-ready статус будет декларацией. Когда оно закрыто и доказано на второй категории, все остальные части становятся последовательной сборкой продукта: onboarding, UI, approval, export.

Правильный следующий engineering step:

```text
Phase 1A: implement generic derive_category_profile and prove dry-run on category 2841.
```


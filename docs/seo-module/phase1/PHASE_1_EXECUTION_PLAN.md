# Phase 1 — Generic derive и validation на категории 2841

> Статус: **execution plan для реализации Phase 1**.  
> Дата: 2026-04-25.  
> Язык документа: русский.  
> Scope: только backend profile derive/validation и артефакты проверки категории 2841. UI, миграции и архитектурные перестройки вне scope.

Парные документы:

- `docs/seo-module/CONTEXT_PRIMER.md`
- `docs/seo-module/ROADMAP.md`
- `docs/seo-module/CATEGORY_PROFILE_SPEC.md`
- `docs/seo-module/phase1/PRODUCTION_READINESS_PLAN.md`
- `docs/seo-module/phase1/TEST_PLAN.md`
- `docs/seo-module/phase1/CATEGORY_B_REPORT_TEMPLATE.md`

Примечание на момент подготовки плана: `docs/seo-module/phase1/category_2841/preflight_report.md` отсутствует.

---

## 1. Цель Phase 1

Цель Phase 1 — закрыть переход от 812-specific skeleton derive к generic category profile derive и доказать переносимость backend на категории `2841`.

Phase 1 считается успешной, если:

- `derive_category_profile(project_id=1, category_id=2841)` строит валидный `category_profile_v1` без category-specific Python literals;
- profile payload проходит self-check со статусом `passed`;
- профиль 2841 сохраняется сначала inactive;
- activation выполняется только отдельным явным шагом и только после `self_check.status == "passed"`;
- `matcher_v2` запускается минимум на 3 SKU категории 2841 и пишет правильные `category_profile_active` / `category_profile_version`;
- операторский отчёт фиксирует качество бакетов и решение `proceed | fix derive | block Phase 2`.

Phase 1 не доказывает production-quality accuracy, потому что для 2841 нет подтверждённых strict eval labels. Это фаза доказательства переносимости backend и качества generic derive на второй категории.

---

## 2. Реальное текущее состояние

Фактическое состояние после Phase 0:

- категория 812 имеет активный профиль `v1.812.skeleton.243953b2`;
- `self_check.status=passed` для активного профиля 812;
- `matcher_v2` требует active `SeoCategoryProfile` и fail-fast'ит без него;
- active matcher/guards/query paths profile-driven и literal-free;
- legacy matcher изолирован под `_legacy`;
- таблицы `seo_category_profiles` и `seo_category_profile_derive_runs` существуют;
- admin/CLI tooling для derive, persist и activation существует;
- Phase 0 regression gate для 812 пройден: baseline accuracy `0.1678`, current accuracy `0.2349`, drift `+0.0671`.

Критический текущий блокер по `PRODUCTION_READINESS_PLAN.md`:

- `derive_category_profile` пока фактически работает как skeleton под 812;
- preflight для 2841 в readiness plan описан как падение dry-run с `NotImplementedError: skeleton only supports 812`;
- поэтому Phase 1 должна включать generic derive implementation steps, а не только validation второй категории.

Текущее состояние по категории 2841 должно быть перепроверено в Step 6 перед persist/activation:

- наличие корпуса `SeoQueryNormalized`;
- наличие `SeoCategoryMeaningAxes`;
- наличие SKU evidence для matcher smoke;
- отсутствие уже активного профиля, либо явное решение оператора, что делать с существующим.

---

## 3. Out of scope

В Phase 1 не делаем:

- UI и UX-реорганизацию;
- миграции БД;
- изменение архитектуры `SeoCategoryProfile` / `category_profile_v1`;
- расширение schema_version до `v1.1` или `v2` без отдельной escalation;
- auto-activation;
- ручной SQL для мутации `SeoCategoryProfile`;
- ручное редактирование profile JSON как штатный путь;
- strict ground-truth labeling для 2841;
- scoring или label-generation на основе `orders`, `conversion`, `Заказали товаров`, `Конверсия`;
- category-specific Python literals в `src/app/services/seo/**`;
- правки runtime matcher/guards под 2841 как отдельную категорию;
- новый generic CLI для matcher, если можно использовать существующий API;
- WB API calls из Phase 1 кода без отдельного явного разрешения оператора.

До successful category 2841 backend validation не начинать UI.

---

## 4. Step 1 — Generic derive evidence reader

Цель: сделать слой чтения evidence для derive category-agnostic и воспроизводимым.

Входы:

- `project_id`;
- `category_id`;
- `SeoQueryNormalized` corpus;
- latest ready `SeoCategoryMeaningAxes`;
- доступные corpus diagnostics из import/bootstrap;
- optional `primary_subject_hint`, если 2841 окажется широкой или неоднозначной.

Работы:

- убрать runtime-зависимость derive от `category_id == 812`;
- собрать evidence pack из существующих таблиц, без внешних WB API-вызовов;
- читать `axes_payload.product_type_axes`, constraint/use-case/audience axes и частотные query tokens;
- зафиксировать, какие поля CSV используются только как диагностика, а не scoring truth;
- не читать `orders`/`conversion` как сигнал качества запроса;
- добавить понятную ошибку, если для 2841 нет корпуса или ready axes.

Выход:

- generic evidence object для builder'ов;
- диагностика покрытия corpus и axes;
- dry-run-friendly error messages.

Tests-to-pass:

- unit test на synthetic category evidence без 812 literals;
- test: missing axes даёт controlled failure;
- test: evidence reader не требует category-specific branch;
- anti-test: economic fields не попадают в scoring/label evidence.

Artifacts:

- `tests/seo/phase1/category_2841/corpus_health.json`;
- `tests/seo/phase1/category_2841/category_axes_snapshot.json`;
- notes в derive-run/self-check diagnostics.

Stop/escalation:

- нет `SeoCategoryMeaningAxes` для 2841;
- axes явно не соответствуют категории;
- для чтения evidence требуется новая таблица или миграция;
- нужен нестандартный LLM prompt или внешний API-вызов.

---

## 5. Step 2 — Generic heuristic profile builder

Цель: построить минимальный `category_profile_v1` из evidence без шаблона 812.

Работы:

- вывести `subject.primary` из `product_type_axes` и/или approved hint;
- построить `subject.primary_aliases` из axes и частотных query tokens;
- построить `subject.related_but_different` из соседних product type axes и корпусных токенов;
- построить `subject.detection_hints.token_prefixes` и `negative_token_prefixes`;
- построить `product_type_aliases`;
- взять `scoring.weights`, `bucket_cutoffs`, `bucket_caps` из default profile config/существующего profile contract, а не из category economics;
- заполнить `generated_by` с evidence hash, category id, corpus counts и method version.

Правила:

- в Python не добавлять слова категории 2841;
- не копировать 812 subject/aliases/conflicts;
- если primary subject неоднозначен, использовать hint только как входной параметр derive, а не hardcoded branch;
- любые defaults должны быть общими для всех категорий.

Выход:

- profile draft со `schema_version="category_profile_v1"`;
- draft может быть self-check failed на этом шаге, но должен быть синтаксически валиден.

Tests-to-pass:

- unit test на synthetic axes: builder создаёт subject из axes;
- unit test: 812 не является default subject для новой категории;
- unit test: scoring defaults не содержат orders/conversion;
- regression: derive для 812 всё ещё строит валидный профиль.

Artifacts:

- `tests/seo/phase1/category_2841/derive_draft_step2.json`;
- diff summary против 812 profile, только как review artifact.

Stop/escalation:

- `category_profile_v1` не может выразить нужные поля 2841;
- нужно поменять scoring contract;
- builder требует category-specific literal в коде.

---

## 6. Step 3 — Constraint and hard-conflict builder

Цель: generic builder для `constraints` и `hard_conflicts`, чтобы related subjects и жёсткие несовместимости возникали из профиля, а не из Python-кода.

Работы:

- построить `constraints.derive_from_query_tokens` из constraint/use-case axes и query token evidence;
- построить `constraints.derive_from_sku_meaning` из тех же generic patterns, где это возможно без SKU-specific assumptions;
- для каждого `related_but_different.subject` создать hard conflict или объяснимое исключение;
- построить hard conflicts для сильных constraints: product type mismatch, required use-case, set/quantity-like constraints, compatibility-like constraints;
- проверить, что every constraint referenced либо в hard conflict, либо в guards.

Правила:

- hard conflict builder не знает слов 2841;
- related subjects берутся из profile draft/evidence;
- economic columns не участвуют;
- если LLM refinement используется, он идёт только через существующий `services/seo/llm/client.py`, с таймаутом и budget guard.

Выход:

- profile draft с constraints и hard conflicts;
- diagnostics: conflict count, uncovered related subjects, dead constraints.

Tests-to-pass:

- unit test: every related subject gets hard conflict;
- unit test: dead constraints detected;
- unit test: hard conflict syntax валидируется loader/validator;
- test: no category literals in builder code.

Artifacts:

- `tests/seo/phase1/category_2841/constraints_summary.json`;
- `tests/seo/phase1/category_2841/hard_conflicts_summary.json`.

Stop/escalation:

- hard conflicts невыразимы через текущий predicate set;
- нужен новый predicate в `category_profile_v1`;
- LLM даёт непроверяемые related subjects.

---

## 7. Step 4 — Guard builder

Цель: generic builder для `query_guards` и `sku_guards` на основе profile evidence.

Работы:

- построить `query_guards.product_type_detection` из product type aliases и detection hints;
- построить `query_guards.required_atoms` из constraints, где query token явно требует атрибут/compatibility/use-case;
- построить `query_guards.excluded_atoms` только из generic negative patterns и evidence, не из 2841 literals;
- построить `sku_guards.characteristic_mappings` из известных характеристик SKU/category evidence, если они доступны;
- построить `sku_guards.functional_token_mappings` из constraints и known target field whitelist;
- проверить `guards_target_known_fields`.

Правила:

- guards builder не меняет runtime `atoms/v1/guards.py` под 2841;
- если характеристик SKU нет, builder должен дать минимальный валидный guard set, а не падать без причины;
- неизвестные fields должны попадать в warning/fail self-check, а не silently в profile.

Выход:

- profile draft с query/sku guards;
- diagnostics по guard coverage и unknown fields.

Tests-to-pass:

- unit test: product type detection строится из aliases;
- unit test: unknown target fields rejected;
- unit test: empty SKU characteristics не ломают profile draft;
- targeted profile-driven guard tests из Phase 0 остаются зелёными.

Artifacts:

- `tests/seo/phase1/category_2841/guards_summary.json`.

Stop/escalation:

- для 2841 критично поле, которого нет в whitelist;
- нужно менять atoms schema;
- guard builder может работать только с ручным literal list.

---

## 8. Step 5 — Validator hardening

Цель: сделать validator достаточно строгим для generic profiles, не ослабляя safety ради прохождения 2841.

Работы:

- проверить обязательные checks из `CATEGORY_PROFILE_SPEC.md §9`;
- добавить/уточнить checks, если generic derive выявил дыру:
  - `schema_version_is_v1`;
  - `subject_non_empty`;
  - `subject_coverage`;
  - `hard_conflicts_cover_related`;
  - `hard_conflicts_syntax`;
  - `bucket_cutoffs_monotonic`;
  - `constraint_references`;
  - `guards_target_known_fields`;
  - `no_cross_category_duplication`;
  - `eval_smoke`, только если для категории есть labels;
- self-check для 2841 без labels не должен требовать accuracy, но должен требовать semantic/profile integrity;
- activation must remain impossible when `self_check.status != "passed"`.

Правила:

- не ослаблять validator, чтобы “пропихнуть” плохой 2841 profile;
- validator не должен содержать category literals;
- failures должны быть actionable.

Выход:

- hardened validator behaviour;
- self-check JSON, пригодный для review.

Tests-to-pass:

- unit tests на каждый новый/уточнённый check;
- regression: active 812 profile проходит validator;
- test: activation rejects `self_check.status != "passed"`;
- test: category with no labels skips strict eval but records reason.

Artifacts:

- `tests/seo/phase1/category_2841/profile_self_check.json`;
- validator failure examples, если были исправления.

Stop/escalation:

- self-check требует schema extension;
- validator противоречит `CATEGORY_PROFILE_SPEC.md`;
- для прохождения нужен bypass activation safety.

---

## 9. Step 6 — Dry-run category 2841

Цель: главный gate Phase 1 — доказать, что generic derive строит profile payload для 2841 без DB profile writes.

Команда:

```powershell
python scripts/derive_category_profile.py --project 1 --category 2841 --dry-run --out tests/seo/phase1/category_2841/derive_dry_run.json
```

API alternative:

- `POST /api/v1/projects/1/seo/category-profiles/derive`
- body: `{"category_id": 2841, "dry_run": true, "activate": false}`

Pass conditions:

- нет `NotImplementedError`;
- нет skeleton-only / 812-only path;
- payload имеет `schema_version="category_profile_v1"`;
- `subject`, aliases, related subjects, constraints и guards описывают 2841, а не 812;
- `self_check.status == "passed"`;
- profile не содержит scoring по orders/conversion;
- derive-run diagnostics сохранены.

Required artifacts:

- `tests/seo/phase1/category_2841/derive_dry_run.json`;
- `tests/seo/phase1/category_2841/profile_self_check.json`;
- `tests/seo/phase1/category_2841/profile_diff_vs_812.json` или markdown summary;
- `tests/seo/phase1/category_2841/corpus_health.json`;
- `tests/seo/phase1/category_2841/category_axes_snapshot.json`.

Stop conditions:

- dry-run падает с `skeleton only supports 812`;
- `self_check.status != "passed"`;
- профиль выглядит как 812 leakage;
- для успешного dry-run нужна migration/schema change;
- generic derive пытается auto-activate.

---

## 10. Step 7 — Persist inactive profile

Цель: сохранить профиль 2841 в БД как inactive candidate после успешного dry-run.

Команда:

```powershell
python scripts/derive_category_profile.py --project 1 --category 2841 --persist --out tests/seo/phase1/category_2841/
```

API alternative:

- `POST /api/v1/projects/1/seo/category-profiles/derive`
- body: `{"category_id": 2841, "dry_run": false, "activate": false}`

Preconditions:

- Step 6 passed;
- `self_check.status == "passed"`;
- оператор согласовал DB-changing operation;
- если есть existing profile 2841, выбран путь: create new version, do not overwrite/delete old rows.

Pass conditions:

- создана строка `SeoCategoryProfile` для `(project_id=1, category_id=2841)`;
- `is_active=false`;
- `payload.self_check.status="passed"`;
- создана строка `SeoCategoryProfileDeriveRun`;
- snapshot записан в `config/seo/category_profiles/1/2841/<profile_version>.json`.

Required artifacts:

- `tests/seo/phase1/category_2841/post_persist_profile.json`;
- `config/seo/category_profiles/1/2841/<profile_version>.json`;
- `tests/seo/phase1/category_2841/derive_run_summary.json`.

Stop conditions:

- persist пытается активировать профиль;
- профиль сохраняется с failed self-check;
- duplicate/version conflict не объяснён;
- требуется ручной SQL.

---

## 11. Step 8 — Activate category 2841

Цель: активировать профиль 2841 отдельным safe action после review inactive profile.

Команда:

```powershell
python scripts/activate_category_profile.py --profile-id <profile_id>
```

API alternative:

- `POST /api/v1/projects/1/seo/category-profiles/<profile_id>/activate`

Preconditions:

- Step 7 passed;
- profile belongs to `project_id=1`, `category_id=2841`;
- `payload.self_check.status == "passed"`;
- operator approved activation;
- no pending escalation on profile semantics.

Pass conditions:

- ровно один active profile для `(project_id=1, category_id=2841)`;
- active profile version equals reviewed persisted profile version;
- previous active profile, если был, deactivated through admin service;
- no deleted rows from `seo_category_profiles`.

Required artifacts:

- `tests/seo/phase1/category_2841/post_activation_profile.json`;
- `tests/seo/phase1/category_2841/active_profile_check.json`.

Stop conditions:

- `self_check.status != "passed"`;
- activation endpoint/CLI bypasses safety;
- profile id/category mismatch;
- activation conflict requires manual SQL.

---

## 12. Step 9 — Matcher smoke on 2841

Цель: проверить active profile 2841 в runtime `matcher_v2`.

Preconditions:

- Step 8 passed;
- выбраны минимум 3 SKU категории 2841;
- SKU имеют existing product evidence/meaning/atoms или могут быть обработаны существующим analysis flow без внешних WB API-вызовов.

API:

- `POST /api/v1/projects/1/seo/matcher/v2/run`
- body:

```json
{
  "category_id": 2841,
  "nm_id": "<nm_id>",
  "limit": 400,
  "include_rejected": true
}
```

Pass conditions:

- минимум 3 successful `SeoMatcherRun`;
- у каждого run есть `SeoMatcherResult`;
- `metrics.category_profile_active == true`;
- `metrics.category_profile_version` equals active 2841 profile version;
- bucket distribution не пустая;
- top primary/secondary examples смыслово относятся к SKU;
- rejected reasons explainable через profile conflicts/guards.

Required artifacts:

- `tests/seo/phase1/category_2841/sku_meaning_status.json`;
- `tests/seo/phase1/category_2841/matcher_runs_summary.json`;
- optional `tests/seo/phase1/category_2841/matcher_run_<run_id>.json`;
- `tests/seo/phase1/category_2841/operator_review_notes.md`.

Stop conditions:

- `ProfileMissingError`;
- wrong profile version in metrics;
- matcher silently falls back to 812/legacy;
- all useful queries rejected due to profile defects;
- SKU meaning requires WB API sync not approved by operator.

---

## 13. Step 10 — Category 2841 report

Цель: зафиксировать результат Phase 1 и решение для Phase 2.

Документ:

- `docs/seo-module/phase1/CATEGORY_2841_REPORT.md`

Основа:

- `docs/seo-module/phase1/CATEGORY_B_REPORT_TEMPLATE.md`, адаптированный под 2841.

Report должен включать:

- category summary;
- CSV/corpus summary;
- axes summary;
- profile summary;
- self-check summary;
- persist/activation summary;
- 3+ matcher smoke summaries;
- operator qualitative review;
- список derive/profile/matcher проблем;
- evidence, что не было 812 leakage;
- evidence, что orders/conversion не использовались в scoring;
- финальное решение: `proceed | fix derive | block Phase 2`.

Pass conditions:

- report exists;
- report references all required artifacts;
- decision is explicit;
- open questions listed.

Stop conditions:

- нет matcher smoke summary;
- нет profile activation evidence;
- операторский review не выполнен;
- Phase 2 decision cannot be made from available evidence.

---

## 14. Required tests per step

Step 1:

- evidence reader unit tests on synthetic category;
- missing axes controlled failure;
- no economic fields in derive scoring evidence.

Step 2:

- heuristic builder unit tests on synthetic axes;
- generated profile has `category_profile_v1`;
- scoring defaults are profile/default based, not economics;
- 812 regression derive remains valid.

Step 3:

- every related subject covered by hard conflict;
- constraint references are not dead;
- hard conflict predicates validate;
- no category literal regression.

Step 4:

- query guards built from aliases/constraints;
- SKU guard unknown fields rejected;
- empty SKU characteristics handled;
- Phase 0 profile-driven guards tests still pass.

Step 5:

- validator checks from spec;
- activation rejects failed self-check;
- no-label category skips strict eval with recorded reason;
- 812 active profile still passes.

Step 6:

- dry-run command for 2841 succeeds;
- payload self-check passed;
- anti-literal check over active Python runtime;
- no orders/conversion scoring check.

Step 7:

- persisted profile inactive;
- derive-run row exists;
- snapshot exists;
- no auto-activation.

Step 8:

- activation only after passed self-check;
- exactly one active profile for 2841;
- no profile rows deleted.

Step 9:

- 3+ matcher runs;
- run metrics reference active 2841 profile version;
- result rows non-empty;
- qualitative bucket sanity recorded.

Step 10:

- report references artifacts;
- decision recorded;
- unresolved risks listed.

Recommended targeted test commands:

```powershell
pytest -x tests/seo/phase0/
pytest -x tests/seo/phase1/
pytest -x tests/seo/test_matcher_v2_no_category_literals.py
```

If `tests/seo/phase1/` does not exist yet, create focused tests with the implementation PR that changes derive/validator logic.

---

## 15. Required artifacts per step

Artifact root:

```text
tests/seo/phase1/category_2841/
```

Required artifacts:

| Step | Artifact |
|---|---|
| 1 | `corpus_health.json`, `category_axes_snapshot.json` |
| 2 | `derive_draft_step2.json`, `profile_diff_vs_812.json` or markdown summary |
| 3 | `constraints_summary.json`, `hard_conflicts_summary.json` |
| 4 | `guards_summary.json` |
| 5 | `profile_self_check.json` |
| 6 | `derive_dry_run.json`, `profile_self_check.json`, `corpus_health.json`, `category_axes_snapshot.json` |
| 7 | `post_persist_profile.json`, `derive_run_summary.json`, `config/seo/category_profiles/1/2841/<profile_version>.json` |
| 8 | `post_activation_profile.json`, `active_profile_check.json` |
| 9 | `sku_meaning_status.json`, `matcher_runs_summary.json`, `operator_review_notes.md` |
| 10 | `docs/seo-module/phase1/CATEGORY_2841_REPORT.md` |

Do not commit raw enriched CSV unless operator explicitly approves. Prefer manifest/hash/counts.

---

## 16. Stop/escalation conditions

Немедленно остановиться и эскалировать оператору, если:

- спецификация противоречит коду и нельзя выполнить spec без изменения schema/runtime contract;
- `category_profile_v1` не выражает нужный профиль 2841;
- требуется миграция;
- требуется UI;
- требуется WB API call;
- требуется нестандартный LLM prompt/model;
- self-check не проходит, а причина не data-quality и не очевидная derive heuristic bug;
- activation возможна только через bypass;
- matcher smoke показывает wrong profile version или legacy fallback;
- качество бакетов системно плохое и исправление требует schema/runtime change;
- для решения хочется добавить category-specific Python literal;
- возникает соблазн использовать orders/conversion для scoring или label-generation.

Формат escalation:

```text
ESCALATION
Phase: 1
Step: <N>
Issue: <что обнаружено>
Evidence: <файлы:строки, артефакты, логи>
Options I see:
  A) <вариант с рисками>
  B) <вариант с рисками>
Recommendation: <мнение + почему>
Waiting for your decision.
```

---

## 17. Definition of Done for Phase 1

Phase 1 closed, когда выполнено всё:

- generic derive работает для 2841 без `NotImplementedError` и без 812-only path;
- active Python runtime не содержит новых category-specific literals;
- профиль 2841 имеет `schema_version="category_profile_v1"`;
- `payload.self_check.status == "passed"`;
- scoring weights/cutoffs/caps берутся из profile/default config, не из category economics;
- orders/conversion не используются в scoring или label-generation;
- профиль 2841 сохранён inactive перед activation;
- activation выполнена отдельным явным шагом;
- auto-activation отсутствует;
- для `(project_id=1, category_id=2841)` ровно один active profile;
- профиль 2841 snapshot сохранён в `config/seo/category_profiles/1/2841/<profile_version>.json`;
- `matcher_v2` успешно прогнан минимум на 3 SKU 2841;
- каждый matcher run пишет `category_profile_active=true`;
- каждый matcher run пишет correct `category_profile_version`;
- операторский qualitative review говорит, что buckets достаточно осмысленны для Phase 1, либо report фиксирует `fix derive`/`block Phase 2`;
- создан `docs/seo-module/phase1/CATEGORY_2841_REPORT.md`;
- все required artifacts из §15 существуют;
- targeted tests из §14 зелёные или failure documented as unrelated/known;
- Phase 2 go/no-go decision явно записан в report.

---

## 18. Коммуникация результата

После выполнения каждого Step отчёт агентом должен быть в формате:

```text
Статус: closed | blocked | needs-review
Изменённые файлы:
- ...
Тесты: pass | fail | skipped
Кратко что сделано:
- ...
Риски / вопросы:
- ...
Следующий рекомендуемый шаг:
- ...
```

Коммиты не делать без явного запроса оператора. Рекомендуемый префикс commit message для будущих code/docs changes: `[phase1-step<N>] <краткая суть>`.

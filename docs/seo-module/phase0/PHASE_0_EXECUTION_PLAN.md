# Phase 0 — Execution Plan

> Статус: **пошаговая инструкция для агента-исполнителя**.
> Версия: v1 (2026-04-24).
> Опорные документы: `CATEGORY_PROFILE_SPEC.md`, `ROADMAP.md`, `TEST_PLAN.md`, `AGENTS.md`.

---

## 0. TL;DR

Цель Phase 0 — **убрать 812-хардкод из бэкенда** и сделать `SeoCategoryProfile` единственным источником категорийных правил. На выходе — любая категория с активным профилем работает в `matcher_v2` без правки Python-кода.

**Status (2026-04-24): Phase 0 completed.** Steps 1–10 закрыты коммитами `4d3b02a`, `e8a39a2`, `0b6241a`, `740f413`, `8ec4946`, `0bc5a37`, `59fee82`, `e1644c4`, `f4aa78a`, `b299422`; Step 11 обновляет документацию и retro.

Фактические артефакты:
- Step 1 baseline: `tests/seo/phase0/baselines/812_pre_phase0/`
- Step 8 activation: `tests/seo/phase0/activation_reports/812_step8/`
- Step 9 wiring: `tests/seo/phase0/activation_reports/812_step9/`
- Step 10 acceptance: `tests/seo/phase0/activation_reports/812_step10/`
- Step 11 retro: `docs/seo-module/phase0/PHASE_0_RETRO.md`

План разбит на **11 атомарных шагов**. Каждый шаг:
- закрывается одним PR (или последовательностью PR'ов с одинаковым `[phase0-stepN]` префиксом);
- не ломает рантайм (каждый шаг — либо pass-through, либо behind feature flag, либо гарантированный bit-for-bit эквивалент предыдущего поведения);
- имеет чёткие tests-to-pass и DoD.

**Не объединяй шаги.** Каждый шаг — отдельный коммит с указанным сообщением. Это даёт атомарный rollback и чистую историю для ревью.

**Не пропускай шаги.** Step N+1 опирается на DoD Step N.

---

## 1. Предусловия перед стартом Phase 0

Перед Step 1 убедиться:

- [ ] Прочитан `CATEGORY_PROFILE_SPEC.md` целиком.
- [ ] Прочитан `AGENTS.md` (правила работы).
- [ ] Прочитан `CONTEXT_PRIMER.md` (где мы сейчас).
- [ ] Ветка создана от `main`: `git checkout -b phase0-backend-unification`.
- [ ] Docker запущен: `postgres`, `api`, `frontend` подняты из `infra/docker/docker-compose.yml`.
- [ ] База подключена и содержит 812-корпус с enriched-метриками (см. `CONTEXT_PRIMER.md §3`).
- [ ] `pytest -x tests/seo/` зелёный на стартовом коммите. Если нет — **не начинай Phase 0, сначала зафиксируй baseline-зеленоту отдельным PR**.

Если любой пункт не выполнен — остановись и согласуй с оператором.

---

## 2. Глоссарий

| Термин | Значение |
|---|---|
| **baseline** | состояние кода и метрик на стартовом коммите Phase 0 (SHA фиксируется в Step 1) |
| **atomic step** | изменение, которое: (а) можно проревьюить за ≤30 минут; (б) оставляет рантайм работоспособным; (в) имеет свой набор тестов |
| **pass-through** | новый код добавлен, но старый путь ещё активен; поведение системы 1:1 как до шага |
| **behind feature flag** | новый код активен только при `SEO_MATCHER_V2_USE_PROFILE=1` (или аналогичном); дефолт — старое поведение |
| **bit-for-bit эквивалент** | снапшот-тест на реальных данных показывает 0 различий между старым и новым путём для зафиксированного набора SKU |
| **DoD** | Definition of Done — список чекбоксов, всё должно быть `[x]` перед коммитом |
| **ProfileMissingError** | новое исключение, бросается `matcher_v2`/`guards`, когда для категории нет активного профиля |

---

## 3. Шаги

### Step 1 — Заморозка baseline

#### Цель

Зафиксировать поведение системы ДО рефакторинга, чтобы все последующие шаги могли сверяться со снимком.

#### Предусловия

- `pytest -x tests/seo/` зелёный.
- В БД есть активный корпус 812 + 191 eval-labels + ≥5 `SeoMatcherRun` для labeled SKU.

#### Touched files (new)

```
tests/seo/phase0/__init__.py
tests/seo/phase0/baselines/__init__.py
tests/seo/phase0/baselines/README.md
tests/seo/phase0/baselines/812_pre_phase0/
  ├─ eval_summary.json
  ├─ matcher_v2_sku_<nm_id>.json   (×3–5 reference SKU)
  ├─ query_atoms_<query_id>.json   (×10 reference queries)
  ├─ sku_atoms_<nm_id>.json        (×3–5 reference SKU)
  └─ manifest.json                 (git SHA + метаданные)
scripts/phase0/capture_baseline.py
```

#### Touched files (modified)

Нет. Только чтение.

#### Action steps

1. Создать `scripts/phase0/capture_baseline.py`:
   - читает 3–5 reference SKU (список в константе, начать с `291861306`, `535441190` + ещё 2–3 с разным quality-mode);
   - для каждого SKU: загрузить последний `SeoMatcherRun`, сериализовать `results` в JSON;
   - для первых 10 query_id из 812 с наибольшим ranking_value — сохранить результат `apply_query_guards(QueryAtoms(), [primary_query_text])`;
   - для каждого reference SKU — сохранить `apply_sku_guards(SkuAtoms(...))`;
   - прогнать `eval/matcher/run` для всех labeled SKU 812 → записать `eval_summary.json` (accuracy, per-bucket F1, label-scored count).
2. Запустить: `python scripts/phase0/capture_baseline.py --project=1 --category=812 --out=tests/seo/phase0/baselines/812_pre_phase0/`.
3. Заполнить `manifest.json`:
   ```json
   {
     "baseline_git_sha": "<вывод git rev-parse HEAD>",
     "captured_at": "<ISO timestamp>",
     "category_id": 812,
     "project_id": 1,
     "reference_sku_nm_ids": [...],
     "reference_query_ids": [...],
     "eval_accuracy": 0.XX,
     "matcher_runs_referenced": [...]
   }
   ```
4. Написать `README.md` рядом:
   - «Эти файлы — снимок поведения ДО Phase 0».
   - «Любое изменение поведения в Steps 5, 6, 8 обязано быть объяснено или автоматически zero-diff».
   - «Не редактировать руками. Регенерация — только через `capture_baseline.py` после сознательного решения».

#### Tests to pass

- `python scripts/phase0/capture_baseline.py` завершается без ошибок.
- Все файлы в `baselines/812_pre_phase0/` существуют и валидный JSON.
- `manifest.json::eval_accuracy` > 0 (если 0 — значит `matcher_v2`-ранов нет, надо сначала прогнать).

#### DoD

- [ ] `baselines/812_pre_phase0/manifest.json` зафиксирован в git.
- [ ] В манифесте записан `baseline_git_sha`.
- [ ] Скрипт `capture_baseline.py` идемпотентен (повторный запуск даёт тот же результат при неизменных данных).

#### On failure

Если eval accuracy ≈ 0 → сначала прогнать `matcher_v2` для всех 191 labeled SKU (см. `scripts/run_matcher_v2_for_labeled_812.py` из транскрипта), затем повторить Step 1.

#### Commit

```
[phase0-step1] freeze 812 baseline snapshot

- Capture eval summary, matcher_v2 results for 3-5 reference SKUs,
  query/sku atoms for reference queries/SKUs.
- Manifest records git SHA and captured metrics for later regression checks.
- Baselines are read-only; regeneration requires explicit decision.
```

---

### Step 2 — Вынос глобальной лексики в `global_vocabulary.json`

#### Цель

Переместить кросс-категорийную лексику (цвета, получатели, аудитория, выразительность, материалы) в единый конфиг-файл, чтобы не дублировать её в профилях и чтобы Step 5/6 смог читать её централизованно.

#### Предусловия

- Step 1 closed.

#### Touched files (new)

```
config/seo/global_vocabulary.json
src/app/services/seo/vocabulary.py
tests/seo/phase0/test_vocabulary_loader.py
```

#### Touched files (modified)

Нет. Существующие `guards.py` и `matcher.py` продолжают использовать in-code константы. Это pass-through step.

#### Action steps

1. Создать `config/seo/global_vocabulary.json` по следующей структуре (см. `CATEGORY_PROFILE_SPEC.md §4`):
   ```json
   {
     "schema_version": "global_vocabulary_v1",
     "audience_taxonomy": ["женская", "мужская", "школьники", "подростки", "детская", "взрослая", "любимая", "любимый"],
     "audience_synonyms": { ... перенести содержимое _AUDIENCE_GROUPS из matcher.py ... },
     "expressive_taxonomy": ["милая", "уют", "эстетика", "смешная", "праздничная"],
     "expressive_synonyms": { ... перенести _EXPRESSIVE и _EXPRESSIVE_GROUPS из guards.py + matcher.py; канонизировать объединённо ... },
     "recipient_synonyms": { ... перенести _RECIPIENTS из guards.py ... },
     "color_taxonomy": ["белый", "черный", "красный", "синий", "голубой", "розовый", "зеленый", "желтый", "фиолетовый", "бежевый", "кремовый"],
     "color_synonyms": { ... перенести _COLORS из guards.py ... },
     "material_taxonomy": ["glass", "ceramic", "porcelain", "metal", "plastic", "textile", "leather", "polyester", "nylon", "wood"],
     "material_synonyms": { ... перенести _MATERIAL_CONSTRAINTS из matcher.py (разверстав set-синонимы) ... }
   }
   ```

2. Создать `src/app/services/seo/vocabulary.py`:
   ```python
   """Global cross-category vocabulary loader."""
   from __future__ import annotations
   import json
   from dataclasses import dataclass, field
   from functools import lru_cache
   from pathlib import Path
   from typing import Mapping

   _DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "seo" / "global_vocabulary.json"

   @dataclass(frozen=True)
   class GlobalVocabulary:
       schema_version: str
       audience_taxonomy: tuple[str, ...]
       audience_synonyms: Mapping[str, tuple[str, ...]]
       expressive_taxonomy: tuple[str, ...]
       expressive_synonyms: Mapping[str, tuple[str, ...]]
       recipient_synonyms: Mapping[str, str]
       color_taxonomy: tuple[str, ...]
       color_synonyms: Mapping[str, str]
       material_taxonomy: tuple[str, ...]
       material_synonyms: Mapping[str, tuple[str, ...]]

       def canonical_color(self, token: str) -> str | None: ...
       def canonical_recipient(self, token: str) -> str | None: ...
       def audience_group(self, tokens: set[str]) -> set[str]: ...

   @lru_cache(maxsize=1)
   def load_global_vocabulary(path: Path | None = None) -> GlobalVocabulary:
       raw = json.loads((path or _DEFAULT_PATH).read_text(encoding="utf-8"))
       assert raw.get("schema_version") == "global_vocabulary_v1", f"Unknown schema_version: {raw.get('schema_version')!r}"
       return GlobalVocabulary(
           schema_version=raw["schema_version"],
           audience_taxonomy=tuple(raw["audience_taxonomy"]),
           audience_synonyms={k: tuple(v) for k, v in raw["audience_synonyms"].items()},
           expressive_taxonomy=tuple(raw["expressive_taxonomy"]),
           expressive_synonyms={k: tuple(v) for k, v in raw["expressive_synonyms"].items()},
           recipient_synonyms=dict(raw["recipient_synonyms"]),
           color_taxonomy=tuple(raw["color_taxonomy"]),
           color_synonyms=dict(raw["color_synonyms"]),
           material_taxonomy=tuple(raw["material_taxonomy"]),
           material_synonyms={k: tuple(v) for k, v in raw["material_synonyms"].items()},
       )
   ```

3. Написать `tests/seo/phase0/test_vocabulary_loader.py`:
   - Loader успешно грузит файл.
   - `schema_version == "global_vocabulary_v1"`.
   - Размеры коллекций не нулевые.
   - Проверить, что `_RECIPIENTS` из `guards.py` и `recipient_synonyms` из vocabulary.json **совпадают ровно** (snapshot-test).
   - То же для `_COLORS`, `_EXPRESSIVE`, `_AUDIENCE_GROUPS`, `_MATERIAL_CONSTRAINTS`.

#### Tests to pass

```bash
pytest -x tests/seo/phase0/test_vocabulary_loader.py
```

Все тесты зелёные.

#### DoD

- [ ] `config/seo/global_vocabulary.json` существует, валидный JSON.
- [ ] `vocabulary.py` загружает его без warnings.
- [ ] Snapshot-тесты подтверждают побитовое совпадение с in-code константами.
- [ ] Код `guards.py`, `matcher.py` **не изменён**.
- [ ] `pytest -x tests/seo/` остаётся зелёным.

#### On failure

Если snapshot не совпадает — ошибка переноса, править JSON (НЕ код).

#### Commit

```
[phase0-step2] extract cross-category vocabulary to global_vocabulary.json

- Introduce config/seo/global_vocabulary.json (schema v1).
- Add services/seo/vocabulary.py loader (GlobalVocabulary dataclass).
- Snapshot tests prove the JSON is bit-for-bit equivalent to the in-code
  constants in atoms/v1/guards.py and query_meaning_matcher/matcher.py.
- Consumers (guards, matcher) are NOT yet migrated — done in Step 5/6.
```

---

### Step 3 — Таблица `seo_category_profile_derive_runs` + skeleton derive + validator

#### Цель

Поставить инфраструктуру под автогенерацию профиля: таблица для наблюдаемости, skeleton функции `derive_category_profile`, self-check (`category_profile_validator`), CLI.

В этом шаге `derive_category_profile` **возвращает hardcoded-профиль 812** (взят дословно из `CATEGORY_PROFILE_SPEC.md §10.1`). Настоящая эвристика + LLM — Step 8.

#### Предусловия

- Step 2 closed.

#### Touched files (new)

```
alembic/versions/YYYYMMDD_HHMM_seo_category_profile_derive_runs.py
src/app/services/seo/category_profile_derive.py
src/app/services/seo/category_profile_validator.py
src/app/services/seo/category_profile_snapshot.py          (write snapshot to config/seo/category_profiles/...)
src/app/schemas/seo_category_profile.py                    (Pydantic-модели профиля + self-check)
scripts/derive_category_profile.py                         (CLI)
tests/seo/phase0/test_category_profile_validator.py
tests/seo/phase0/test_category_profile_derive_skeleton.py
config/seo/category_profiles/1/812/.gitkeep
```

#### Touched files (modified)

```
src/app/models.py                                          (+ class SeoCategoryProfileDeriveRun)
```

#### Action steps

1. **Миграция Alembic** — создать таблицу `seo_category_profile_derive_runs`:
   ```
   id                  BIGSERIAL PK
   project_id          INT NOT NULL
   category_id         INT NOT NULL
   run_id              UUID UNIQUE NOT NULL
   started_at          TIMESTAMPTZ NOT NULL
   finished_at         TIMESTAMPTZ NULL
   status              VARCHAR(32) NOT NULL  -- running|succeeded|failed
   method              VARCHAR(64) NOT NULL  -- derive_heuristic_plus_llm_v1 | skeleton_v0 | ...
   llm_model           VARCHAR(128) NULL
   prompt_version      VARCHAR(64) NULL
   evidence_hash       VARCHAR(128) NULL
   profile_id          BIGINT NULL           -- FK soft на seo_category_profiles.id
   self_check_json     JSONB NOT NULL DEFAULT '{}'
   eval_baseline_json  JSONB NULL
   eval_new_json       JSONB NULL
   diff_summary        JSONB NULL
   error_message       TEXT NULL
   INDEX (project_id, category_id)
   INDEX (status)
   ```
   Соответствующий ORM в `models.py`: `class SeoCategoryProfileDeriveRun`.

2. **Pydantic-схема профиля** — `src/app/schemas/seo_category_profile.py`:
   - `CategoryProfilePayloadV1` (BaseModel) — строгая валидация payload по `CATEGORY_PROFILE_SPEC.md §3`.
   - `SubjectSpec`, `ProductTypeAlias`, `ConstraintDerivationRule`, `HardConflictRule`, `ScoringSpec`, `SkuGuardsSpec`, `QueryGuardsSpec`, `GeneratedBySpec`, `SelfCheckReport` — вложенные модели.
   - Отклонение при `schema_version != "category_profile_v1"`.
   - Строгий whitelist для `HardConflictRule.requires_sku_any[*]` predicates (см. SPEC §3.5).

3. **Validator** — `category_profile_validator.py`:
   - `validate_profile(payload: dict) → SelfCheckReport` — запускает все проверки из `CATEGORY_PROFILE_SPEC.md §9.1`.
   - Каждая проверка — отдельная функция `check_subject_coverage`, `check_hard_conflicts_cover_related`, `check_bucket_cutoffs_monotonic`, `check_constraint_references`, `check_guards_target_known_fields`, `check_no_cross_category_duplication`, `check_eval_smoke` (optional, если есть labels).
   - Возвращает `SelfCheckReport(status="passed"|"failed", checks=[...])`.

4. **Snapshot writer** — `category_profile_snapshot.py`:
   - `write_snapshot(profile: CategoryProfile, *, project_id: int, category_id: int, version: str) → Path`.
   - Пишет `config/seo/category_profiles/<project_id>/<category_id>/<version>.json` с `sort_keys=True, indent=2`.
   - Создаёт недостающие директории.

5. **Derive skeleton** — `category_profile_derive.py`:
   ```python
   def derive_category_profile(
       session: Session,
       *,
       project_id: int,
       category_id: int,
       dry_run: bool = True,
       method: str = "skeleton_v0",
   ) -> DeriveResult:
       """Skeleton: returns hardcoded 812 profile from CATEGORY_PROFILE_SPEC §10.1.

       Real heuristic + LLM implementation is Step 8. This skeleton exists so
       the surrounding infrastructure (DB row, validator, snapshot, CLI) can be
       tested end-to-end before real derive logic is added.
       """
       # 1. Create derive-run row (status=running)
       # 2. If category_id == 812: payload = hardcoded from SPEC §10.1
       #    else: raise NotImplementedError("derive_category_profile skeleton only supports 812")
       # 3. Validate payload → self_check
       # 4. If dry_run: return DeriveResult(profile=None, self_check=...)
       # 5. Else: insert SeoCategoryProfile (is_active=False, version="v1.<cat>.<date>-skeleton")
       #    write snapshot, update derive-run row (status=succeeded, profile_id=...)
       # 6. Return DeriveResult(profile=..., self_check=...)
   ```
   `DeriveResult` = dataclass(profile, self_check, run_id, dry_run).

6. **CLI** — `scripts/derive_category_profile.py`:
   ```
   python scripts/derive_category_profile.py \
     --project 1 --category 812 \
     [--dry-run | --activate] \
     [--method skeleton_v0]
   ```
   `--dry-run` (default): показывает diff против текущего активного профиля, не пишет.
   `--activate`: пишет `is_active=false` запись; активация — отдельной CLI-командой в Step 7.

7. **Тесты** — `test_category_profile_validator.py`:
   - Валидный payload из SPEC §10.1 → `status=passed`.
   - Невалидный: `schema_version="v2"` → fail.
   - Невалидный: отсутствует `subject.primary` → fail.
   - Невалидный: `related_but_different` содержит subject без соответствующего `hard_conflict` → fail с check_name `hard_conflicts_cover_related`.
   - Невалидный: `bucket_cutoffs.primary < secondary` → fail.
   - Невалидный: `hard_conflicts[].requires_sku_any[].<unknown_predicate>` → fail.
   - `guards.target.field` не из whitelist → fail.

   `test_category_profile_derive_skeleton.py`:
   - `derive_category_profile(project=1, category=812, dry_run=True)` → `self_check.status = passed`, profile не создан в БД.
   - С `dry_run=False` → запись есть, `is_active=False`, snapshot-файл создан.
   - Для `category=99999` → `NotImplementedError` (skeleton).

#### Tests to pass

```bash
alembic upgrade head                                  # миграция прокатывается
pytest -x tests/seo/phase0/test_category_profile_validator.py
pytest -x tests/seo/phase0/test_category_profile_derive_skeleton.py
python scripts/derive_category_profile.py --project 1 --category 812 --dry-run   # output ok, exit 0
```

#### DoD

- [ ] Alembic миграция применима и откатывается (`downgrade`).
- [ ] `seo_category_profile_derive_runs` создана в БД.
- [ ] CLI `--dry-run` для 812 показывает diff без записи.
- [ ] Все тесты зелёные.
- [ ] Snapshot-файл 812 пока **не активен** (is_active=False).

#### On failure

Если валидатор на SPEC-примере падает → ошибка в валидаторе или в SPEC. Согласовать с оператором (обычно — в SPEC).

#### Commit

```
[phase0-step3] add SeoCategoryProfile derive infrastructure (skeleton)

- Alembic migration: seo_category_profile_derive_runs table + ORM.
- Pydantic schemas: CategoryProfilePayloadV1 (strict, per SPEC §3).
- Validator: self-check per SPEC §9.1.
- Snapshot writer: config/seo/category_profiles/<proj>/<cat>/<ver>.json.
- Derive skeleton: returns hardcoded 812 profile for end-to-end wiring.
- CLI: scripts/derive_category_profile.py --dry-run | --activate.
- Tests cover validator cases and skeleton flow.
- Real derive heuristic + LLM = Step 8; no runtime behavior change yet.
```

---

### Step 4 — Расширить `CategoryProfile` dataclass и loader

#### Цель

Сделать так, чтобы загруженный профиль умел отвечать на все вопросы матчера/гардов, которые сейчас он задаёт in-code константам. Всё ещё pass-through: код-консюмер не меняется.

#### Предусловия

- Step 3 closed.

#### Touched files (modified)

```
src/app/services/seo/category_profile.py
tests/seo/phase0/test_category_profile_loader.py          (new)
```

#### Action steps

1. Расширить dataclass `CategoryProfile` (file: `category_profile.py`):
   - новые свойства:
     - `subject_primary: str`
     - `subject_primary_aliases: tuple[str, ...]`
     - `subject_related: tuple[tuple[str, tuple[str, ...]], ...]`  — `((subject, aliases), ...)`
     - `subject_detection_hints: Mapping[str, tuple[str, ...]]`    — `{"token_prefixes": (...), "negative_token_prefixes": (...)}`
     - `product_type_aliases_map: Mapping[str, Mapping[str, Any]]`
     - `constraints_from_query: tuple[ConstraintRule, ...]`
     - `constraints_from_sku: tuple[ConstraintRule, ...]`
     - `hard_conflicts_list: tuple[HardConflictRule, ...]`
     - `scoring_weights: Mapping[str, float]`
     - `bucket_cutoffs_map: Mapping[str, float]`
     - `bucket_caps_map: Mapping[str, int]`
     - `enforce_material_overlap: bool`
     - `materials_relevant: tuple[str, ...]`
     - `query_guards_spec: QueryGuardsSpec`
     - `sku_guards_spec: SkuGuardsSpec`
   - методы-предикаты:
     - `matches_subject_primary(text: str) → bool`  — по `detection_hints`.
     - `find_product_type_alias(token: str) → str | None`  — возвращает canonical из `product_type_aliases`.
     - `evaluate_hard_conflicts(sku_features, query_features) → list[str]`  — возвращает список `messages` сработавших правил.
     - `derive_query_constraints(query_tokens: set[str], query_text: str) → set[str]`.
     - `derive_sku_constraints(sku_meaning: Mapping[str, Any]) → set[str]`.

2. `load_active_profile` теперь:
   - валидирует `schema_version == "category_profile_v1"` через `CategoryProfilePayloadV1` (из Step 3 schemas).
   - при отсутствии активного профиля возвращает `None` (как было), но помечает deprecation-warning, что в Step 9 это станет ошибкой.

3. Ввести исключение:
   ```python
   class ProfileMissingError(CategoryProfileError):
       """Raised when matcher_v2 is started for a category without active profile.

       Activation of this error is gated by feature flag SEO_MATCHER_V2_STRICT_PROFILE
       (Step 4: flag false by default).
       Step 9 flips the flag default to true and removes the fallback branch.
       """
   ```

4. **Тесты** `test_category_profile_loader.py`:
   - Прогнать Step 3 derive (`--activate` с sleight-of-hand: временно пометить is_active=True для SKELETON-профиля в тесте, через session).
   - Загрузить `load_active_profile(project=1, category=812)` → объект.
   - Все новые свойства возвращают ожидаемые значения (из SPEC §10.1 hardcoded payload).
   - `evaluate_hard_conflicts` срабатывает на синтетических features:
     - query=`{product_type: "термокружка"}`, sku=`{product_type: "кружка"}` → `["product_type conflict: термокружка vs SKU product type"]`.
     - query=`{constraints: {"thermal"}}`, sku=`{constraints: set()}` → `["requires thermal/термокружка..."]`.
     - В остальных кейсах — пустой список.
   - Для `category_id = 99999` → `load_active_profile` возвращает None без исключений (backward-compat).

#### Tests to pass

```bash
pytest -x tests/seo/phase0/test_category_profile_loader.py
pytest -x tests/seo/                                     # всё остальное остаётся зелёным
```

#### DoD

- [ ] `CategoryProfile` expose все свойства из SPEC §3.
- [ ] `evaluate_hard_conflicts` покрывает все 4 SPEC-предиката (constraint, product_type, token_prefix, constraint_prefix).
- [ ] Loader валидирует schema_version через Pydantic.
- [ ] Код матчера/гардов **не меняется** (pass-through).

#### On failure

Если `evaluate_hard_conflicts` даёт другой результат, чем hardcoded `_hard_conflicts` в `matcher.py` → воспроизвести кейс в тесте; либо предикат неправильно интерпретирован, либо SPEC неточен. В последнем случае — обновить SPEC + тест, не код.

#### Commit

```
[phase0-step4] extend CategoryProfile dataclass with SPEC §3 properties

- Add subject, constraints, hard_conflicts, scoring, guards accessors.
- Introduce evaluate_hard_conflicts predicate evaluator.
- Loader validates schema_version via CategoryProfilePayloadV1.
- ProfileMissingError added (gated by SEO_MATCHER_V2_STRICT_PROFILE flag,
  default=false until Step 9).
- Consumers (guards.py, matcher_v2 stages) are NOT yet changed.
```

---

### Step 5 — Рефакторинг `atoms/v1/guards.py` под профиль

#### Цель

Переписать `apply_query_guards` и `apply_sku_guards` так, чтобы они читали правила из `CategoryProfile` (секции `query_guards`, `sku_guards`) и глобальный словарь из `vocabulary.py`. Поведение для 812 — **bit-for-bit** такое же, как раньше.

#### Предусловия

- Step 2, 3, 4 closed.
- Активный профиль 812 есть (из Step 3, skeleton).

#### Touched files (modified)

```
src/app/services/seo/atoms/v1/guards.py
```

#### Touched files (new)

```
src/app/services/seo/atoms/v1/guards_profile.py           (новый, profile-driven implementations)
tests/seo/phase0/test_guards_bit_for_bit_812.py           (snapshot)
```

#### Action steps

1. В `guards_profile.py` реализовать новые функции:
   - `apply_query_guards_v2(query, query_texts, *, profile: CategoryProfile, vocabulary: GlobalVocabulary | None = None)`.
   - `apply_sku_guards_v2(sku, *, evidence=None, meaning_payload=None, profile: CategoryProfile, vocabulary: GlobalVocabulary | None = None)`.

   Эти функции:
   - для **категорийных** веток читают `profile.query_guards_spec` / `profile.sku_guards_spec`;
   - для **глобальных** (цвета, получатели, выразительность, аудитория, материалы, volume-regex, quantity-regex) — читают `vocabulary`;
   - `_RECIPIENTS`, `_EXPRESSIVE`, `_COLORS`, `_CUTE_EXACT`, `_MATERIAL_CONSTRAINTS`, `_AUDIENCE_GROUPS` в `guards.py` становятся **мёртвым кодом** (в Step 5 не удаляются, помечаются `# TODO(phase0-step5-cleanup): dead after Step 6`).

2. В `guards.py` сделать старые функции **thin wrappers**:
   ```python
   def apply_query_guards(query, query_texts, *, profile: CategoryProfile | None = None):
       if profile is None:
           # legacy path kept until Step 9
           return _apply_query_guards_legacy(query, query_texts)
       return apply_query_guards_v2(query, query_texts, profile=profile)
   ```
   `_apply_query_guards_legacy` = текущее тело `apply_query_guards` (дословно).

3. **Snapshot-тест** `test_guards_bit_for_bit_812.py`:
   - Для каждого reference SKU/query из Step 1 baseline:
     - Прогнать старый путь: `apply_query_guards(q, texts)` без profile.
     - Прогнать новый путь: `apply_query_guards(q, texts, profile=load_active_profile(session, project=1, category=812))`.
     - Сравнить как `dict()` — должны быть идентичны.
   - То же для `apply_sku_guards`.

4. Аналогично для `apply_sku_guards`.

#### Tests to pass

```bash
pytest -x tests/seo/phase0/test_guards_bit_for_bit_812.py
pytest -x tests/seo/                                 # другие тесты не трогаются
```

#### DoD

- [ ] Для reference набора атомов `legacy == profile-driven` побитово.
- [ ] Старые функции остались как thin wrappers.
- [ ] `guards_profile.py` **не** содержит строковых литералов `"термокруж"`, `"круж"`, `"пивн"`, `"кофемаш"`, `"в машину"`, `"без рисун"`, `"без крыш"` — они читаются из профиля.
- [ ] `global_vocabulary.json` реально используется (колоры, получатели, выразительность читаются оттуда).

#### On failure

Если bit-for-bit тест red — искать причину в порядке apply'а правил: profile-путь должен гарантировать идентичный порядок, что и hardcoded. Добавить `tiebreaker_order` в `query_guards.product_type_detection` если нужно.

#### Commit

```
[phase0-step5] profile-driven atoms/v1/guards.py (812 bit-for-bit)

- Introduce apply_query_guards_v2 / apply_sku_guards_v2 in guards_profile.py.
- Category-specific literals now come from CategoryProfile.query_guards /
  .sku_guards; global vocab (colors, recipients, expressive, audience,
  materials) from config/seo/global_vocabulary.json.
- Old functions become thin wrappers with legacy fallback when no profile.
- Snapshot tests prove profile-driven path is bit-for-bit equivalent to
  legacy for all reference SKUs/queries from Step 1 baseline.
- Legacy constants (_RECIPIENTS, _EXPRESSIVE, _COLORS, etc.) kept for now;
  removed in Step 6 cleanup.
```

---

### Step 6 — Рефакторинг `query_meaning_matcher/matcher.py` + легаси-изоляция

#### Цель

Перевести `_sku_features`, `_query_features`, `_hard_conflicts`, `_product_type_score`, `_bucket_for` на чтение из `CategoryProfile`. Снять `del category_profile` в трёх стадиях `matcher_v2`.

Результат для 812 — **bit-for-bit** такой же, как baseline.

#### Предусловия

- Step 5 closed.
- `matcher_v2` стадии импортируют `_hard_conflicts`, `_sku_features`, `_query_features` из `query_meaning_matcher.matcher` (см. `matcher_v2/api.py:75-85`).

#### Touched files (new)

```
src/app/services/seo/matcher_v2/rules/__init__.py
src/app/services/seo/matcher_v2/rules/features.py            (_sku_features, _query_features profile-driven)
src/app/services/seo/matcher_v2/rules/conflicts.py           (_hard_conflicts profile-driven)
src/app/services/seo/matcher_v2/rules/scoring.py             (_product_type_score etc. profile-driven)
src/app/services/seo/matcher_v2/rules/bucket.py              (_bucket_for profile-driven)
src/app/services/seo/_legacy/__init__.py
src/app/services/seo/_legacy/matcher_v1.py                   (moved from query_meaning_matcher/matcher.py)
tests/seo/phase0/test_matcher_v2_bit_for_bit_812.py          (snapshot)
```

#### Touched files (modified)

```
src/app/services/seo/matcher_v2/stages/eligibility.py      (remove `del category_profile`, call rules.conflicts)
src/app/services/seo/matcher_v2/stages/soft_score.py       (remove `del category_profile`, call rules.scoring)
src/app/services/seo/matcher_v2/stages/bucket_cap.py       (remove `del category_profile`, call rules.bucket)
src/app/services/seo/matcher_v2/api.py                     (import from rules/, no longer from query_meaning_matcher.matcher)
src/app/services/seo/query_meaning_matcher/matcher.py      (becomes thin re-export wrapper for backward-compat)
```

#### Action steps

1. Скопировать содержимое `query_meaning_matcher/matcher.py` в `_legacy/matcher_v1.py`. Не модифицировать.
2. В `rules/features.py` реализовать `sku_features(meaning, *, profile: CategoryProfile) → _FeatureSet`:
   - `product_type` → `profile.find_product_type_alias(token)` вместо hardcoded `"кружка"`.
   - `constraints` → `profile.derive_sku_constraints(meaning)` вместо hardcoded `"термокруж"`, `"набор"`.
   - `materials` → используется `profile.materials_relevant` в качестве whitelist'а.
3. Аналогично `query_features(row, *, profile: CategoryProfile) → _FeatureSet` — читает `profile.derive_query_constraints`.
4. В `rules/conflicts.py` — `hard_conflicts(sku, query, *, profile: CategoryProfile) → list[str]` через `profile.evaluate_hard_conflicts(sku, query)`. Плюс два универсальных: material overlap и negative audience (используют `profile.enforce_material_overlap` и `vocabulary.audience_taxonomy`).
5. В `rules/scoring.py` — `product_type_score(sku, query, *, profile)` через `profile.product_type_aliases_map[query.product_type]["score_bonus"]`. Остальные функции — `use_case_overlap_score`, `attribute_overlap_score` и т. п. — принимают `profile.scoring_weights`.
6. В `rules/bucket.py` — `bucket_for(score, *, profile: CategoryProfile)` через `profile.bucket_cutoffs_map`.
7. Снять `del category_profile` в трёх стадиях `matcher_v2`:
   - `eligibility.py:68` → заменить на `conflicts = hard_conflicts(sku_features, query_features, profile=category_profile)`.
   - `soft_score.py:64` → call `scoring.*(..., profile=category_profile)`.
   - `bucket_cap.py:61` → `bucket = bucket_for(score=score, profile=category_profile)`.
8. В `matcher_v2/api.py` — импорт из `app.services.seo.matcher_v2.rules`, не из `query_meaning_matcher.matcher`.
9. Старый `query_meaning_matcher/matcher.py` превратить в thin re-export: пусть он импортирует из `_legacy.matcher_v1` с deprecation-warning. Все внешние пользователи (`expressive_llm`, `category_bootstrap`) продолжают работать через этот файл без изменений.
10. В `matcher_v2/api.py` — перед запуском стадий:
    ```python
    if category_profile is None:
        strict = os.environ.get("SEO_MATCHER_V2_STRICT_PROFILE", "false").lower() == "true"
        if strict:
            raise ProfileMissingError(f"No active profile for category_id={category_id}")
        # legacy fallback: используем старый путь через rules-wrapper с профилем-заглушкой
        category_profile = _build_legacy_compat_profile(category_id)
    ```
    `_build_legacy_compat_profile` возвращает `CategoryProfile` с payload из SPEC §10.1 (hardcoded 812) — **только для обратной совместимости на категориях без профиля**. В Step 9 эта ветка удаляется.

11. Snapshot-тест `test_matcher_v2_bit_for_bit_812.py`:
    - Прогнать `matcher_v2` для 3 reference SKU из Step 1 baseline с активным профилем 812.
    - Сравнить `SeoMatcherResult.rows` с baseline.
    - Строго равны в `bucket`, `score_total`, `eligibility_verdict`, `matched_atoms`, `conflict_atoms`.
    - `reasons` могут отличаться по формулировке, но их множество — bit-for-bit.

#### Tests to pass

```bash
pytest -x tests/seo/phase0/test_matcher_v2_bit_for_bit_812.py
pytest -x tests/seo/                                        # всё остальное остаётся зелёным
grep -rn "del category_profile" src/                         # 0 результатов в src/
```

#### DoD

- [ ] `grep -rn "del category_profile" src/` → 0 совпадений.
- [ ] `rules/conflicts.py` не содержит литералов `"термокруж"`, `"пив"`, `"рюкзак"` — всё из профиля.
- [ ] `rules/scoring.py` не содержит хардкодных коэффициентов — всё из `profile.scoring_weights`.
- [ ] Snapshot для 812 — bit-for-bit равен baseline.
- [ ] `_legacy/matcher_v1.py` существует, `query_meaning_matcher/matcher.py` — thin re-export.

#### On failure

Если bit-for-bit сломался — скорее всего разошлась обработка `_expand_expressive` / `_expand_audience` (они читают глобальный vocab вместо in-code). Проверить, что JSON-таксономии совпадают с in-code константами (Step 2 snapshot-тест должен был это поймать).

#### Commit

```
[phase0-step6] profile-driven matcher_v2 rules; legacy isolation

- Introduce matcher_v2/rules/{features, conflicts, scoring, bucket}.py,
  all accept `profile: CategoryProfile` as mandatory kw-only arg.
- Remove `del category_profile` from all three matcher_v2 stages.
- Legacy query_meaning_matcher/matcher.py moved to services/seo/_legacy/
  matcher_v1.py; the old path kept as re-export shim with deprecation.
- matcher_v2/api.py: legacy-compat fallback uses a synthesized 812 profile
  when no active profile exists; removed in Step 9 together with the flag.
- Snapshot tests confirm bit-for-bit parity with Step 1 baseline on 812.
```

---

### Step 7 — Admin API + CLI

#### Цель

Дать оператору и агенту инструменты, чтобы смотреть/переключать/откатывать профили без лазания в SQL.

#### Предусловия

- Step 6 closed.

#### Touched files (new)

```
src/app/routers/seo_category_profile.py
src/app/schemas/seo_category_profile_api.py               (API DTO)
scripts/list_category_profiles.py
scripts/show_category_profile.py
scripts/activate_category_profile.py
scripts/rollback_category_profile.py
tests/seo/phase0/test_seo_category_profile_api.py
```

#### Touched files (modified)

```
src/app/main.py                                          (register router)
```

#### Action steps

1. **Router** `src/app/routers/seo_category_profile.py` — endpoints:
   - `GET /api/seo/project/{project_id}/category/{category_id}/profile/active` — вернуть активный профиль (payload + metadata).
   - `GET /api/seo/project/{project_id}/category/{category_id}/profile/history` — список всех версий с `is_active`, `version`, `created_at`, `self_check.status`.
   - `GET /api/seo/project/{project_id}/category/{category_id}/profile/derive-runs` — список derive-ранов.
   - `POST /api/seo/project/{project_id}/category/{category_id}/profile/activate` — body `{ "version": "v1.812.2026-04-24-auto" }` — атомарно переключает `is_active`.
   - `POST /api/seo/project/{project_id}/category/{category_id}/profile/rollback` — откат на предыдущую активную версию.
   - `POST /api/seo/project/{project_id}/category/{category_id}/profile/derive` — запустить `derive_category_profile` (dry-run по умолчанию, принимает `?activate=false`).

2. Все активационные операции (POST) — требуют `SELF_CHECK_STATUS == "passed"`, иначе 409.

3. **CLI скрипты** — wrapper'ы, которые просто дергают те же сервисы. Цель — чтобы в non-GUI-окружении можно было управлять профилями.

4. **Тесты API**:
   - GET active для 812 → 200, payload присутствует, `schema_version == "category_profile_v1"`.
   - GET history → список.
   - POST activate с несуществующей версией → 404.
   - POST activate с версией, у которой `self_check.status == "failed"` → 409.
   - POST rollback → делает предыдущий активным.

#### Tests to pass

```bash
pytest -x tests/seo/phase0/test_seo_category_profile_api.py
python scripts/list_category_profiles.py --project 1 --category 812       # выводит JSON
```

#### DoD

- [ ] Все 5 endpoints работают (return 200 на happy-path, 404/409 на ошибках).
- [ ] CLI-скрипты используют те же сервисные функции, что и API.
- [ ] Активация пишет snapshot-файл в `config/seo/category_profiles/...`.
- [ ] Rollback работает в одной транзакции (atomic).

#### On failure

Тривиальные ошибки — FastAPI router registration / DB lookup. Тяжёлые — пересечения с активацией из derive-run: гарантия «одна is_active=true» должна быть в SQL-транзакции.

#### Commit

```
[phase0-step7] admin API + CLI for category profiles

- Endpoints: GET active / history / derive-runs, POST activate / rollback /
  derive under /api/seo/project/{pid}/category/{cid}/profile/*.
- Activation enforces self_check.status == "passed" (409 otherwise).
- CLI scripts reuse service functions; write snapshots to config/.../.json.
- Tests cover happy-path and self-check gating.
```

---

### Step 8 — Real derive for 812 + активация

#### Цель

Заменить skeleton-derive реальной эвристикой + LLM и активировать сгенерированный профиль для 812.

#### Предусловия

- Step 7 closed.
- LLM доступен через существующий `services/seo/llm/client.py` (тот же, что `expressive_llm`).

#### Touched files (modified)

```
src/app/services/seo/category_profile_derive.py           (replace skeleton with real implementation)
```

#### Touched files (new)

```
src/app/services/seo/category_profile_derive/              (превращаем в package)
  ├─ __init__.py                 (re-export derive_category_profile)
  ├─ corpus_reader.py             (read SeoQueryNormalized + SeoCategoryMeaningAxes + wb_product_snapshots)
  ├─ heuristic.py                 (subject.primary, aliases, detection_hints, product_type_aliases)
  ├─ llm_refine.py                (LLM-pass for subject.related_but_different, hard_conflicts)
  ├─ constraint_builder.py        (derive constraints from query tokens)
  ├─ scoring_defaults.py          (seed scoring.weights / cutoffs / caps)
  └─ prompts/derive_v1.txt        (LLM prompt template)
tests/seo/phase0/test_derive_812_real.py
tests/seo/phase0/test_derive_fixtures/812_corpus_fixture.json   (snapshot корпуса для воспроизводимости)
```

#### Action steps

1. **`corpus_reader.py`**:
   - Считывает `SeoQueryNormalized` для категории. **Поля `sample_source_payload`** — реальные русские ключи (см. `CONTEXT_PRIMER.md §3.1.1`); семантического слоя имён нет.
     - `Заказали товаров`, `Конверсия в заказ` и прочие **экономические** колонки payload **не читать** для derive (ни ranking примеров для LLM, ни scoring). См. `ROADMAP.md` §8.1 и `CONTEXT_PRIMER.md` (контракт после списка ключей).
     - Для отбора примеров запросов в промпт derive: **`frequency_total`** на `SeoQueryNormalized` и/или равномерная стратификация по кластерам — **не** сортировка по заказам/конверсии из CSV.
     - `Больше всего заказов в предмете` → `str` (только как **sanity check** в `corpus_signals.csv_subject_match_share`, **не источник** субджектов).
   - Считывает активные `SeoCategoryMeaningAxes` (v0) — их `axes_payload` служит **основой для primary и related_but_different** (см. `CATEGORY_PROFILE_SPEC.md §3.2.3`).
   - Считывает `wb_product_snapshots` для 10–20 типичных SKU категории → характеристики (для `sku_guards.characteristic_mappings`).
   - Возвращает dataclass `CorpusEvidence(queries, axes, product_characteristics, csv_subject_match_share)`.

2. **`heuristic.py`** (чистая детерминистика):
   - `primary`: топ-1 `product_type` из `CategoryMeaningAxes.axes_payload.product_type_axes`. Если пусто → fallback: топ-1 токен из `query_text` по частоте, длиной ≥4 символов.
   - `primary_aliases`: множество токенов из запросов, начинающихся с корня `primary[:4]`, встречающихся ≥N раз. Морфологические формы — через простой стеммер (pymorphy или kompot) если доступен.
   - `detection_hints.token_prefixes`: общий префикс длины ≥3 среди aliases.
   - `detection_hints.negative_token_prefixes`: префиксы соседних subject'ов из `product_type_axes[1..]` + вручную замеченные (термокружка, стакан для кружек).
   - `product_type_aliases`: `{primary: {"match_any_prefix": [token_prefix], "score_bonus": 0.22}}`. Дополнительные — из `product_type_axes[1..]`, если derive-LLM подтвердит, что это «подвид primary», а не «отдельный subject».
   - `scoring`: дефолтные значения из `CATEGORY_PROFILE_SPEC.md §3.6` (Step 8 их не калибрует).

3. **`llm_refine.py`** (prompt-driven):
   - Prompt `prompts/derive_v1.txt` получает:
     - `primary` (из heuristic);
     - `product_type_axes` (полный список из `CategoryMeaningAxes`, не только `[1..]`);
     - sample queries per `product_type_axis` (top-N по **`frequency_total`** среди запросов, попавших под эвристику оси, либо стратификация по кластерам — **не** по `Заказали товаров`/конверсиям);
     - кандидатов в `related_but_different` (= `product_type_axes[1..]` + соседние токены из heuristic);
     - `CategoryMeaningAxes.conflict_rules`.
   - Выход: финальный `related_but_different` (что из кандидатов — действительно отдельные subject'ы, а что — синонимы primary); `hard_conflicts`; `query_guards.required_atoms`.
   - Валидация выхода: через `CategoryProfilePayloadV1` Pydantic (Step 3).
   - Логирование: full prompt + completion в `SeoLlmCallLog` (если есть) или файл.

4. **`constraint_builder.py`**:
   - Для каждого `constraint_axis` из `CategoryMeaningAxes.constraint_axes` — build rule `{"constraint": axis, "when_query_contains_any": [tokens]}`.
   - Tokens — найденные в запросах категории биграммы/триграммы, сильно коррелирующие с axis.
   - Для `constraint` без triggers — LLM достаёт keywords.

5. **`derive_category_profile` (main)**:
   - 1. corpus_reader → evidence.
   - 2. heuristic → частичный payload.
   - 3. llm_refine → дополняет payload.
   - 4. constraint_builder → `constraints`, `hard_conflicts` финализируется.
   - 5. `sku_guards.characteristic_mappings` → из `wb_product_snapshots` + LLM-маппинг на канонические слоты.
   - 6. validate → self_check.
   - 7. `method = "derive_heuristic_plus_llm_v1"`.
   - 8. write DB + snapshot.

6. **Активация 812**:
   - `python scripts/derive_category_profile.py --project 1 --category 812 --activate`.
   - Посмотреть diff против skeleton-версии из Step 3.
   - Прогнать `eval/matcher/run` для всех labeled SKU 812 через API (с флагом `SEO_MATCHER_V2_STRICT_PROFILE=false` — derive активен, но strict-режим ещё не включён).
   - Сравнить accuracy с `baselines/812_pre_phase0/manifest.json::eval_accuracy`.
   - **Порог**: accuracy новая ≥ baseline − 0.03 (3 п. п. регресс-бюджет).
   - Если порог пройден → `POST /activate` для новой версии.
   - Если нет → не активировать, разбирать причины (скорее всего derive-LLM галлюцинировал `related_but_different` или `hard_conflicts`).

#### Tests to pass

```bash
pytest -x tests/seo/phase0/test_derive_812_real.py         # деривация на фикстуре
python scripts/derive_category_profile.py --project 1 --category 812 --dry-run   # ok
# accuracy check: вручную в CI или через регресс-скрипт:
python scripts/phase0/compare_eval_to_baseline.py --baseline tests/seo/phase0/baselines/812_pre_phase0/eval_summary.json
```

#### DoD

- [ ] Real derive работает на 812.
- [ ] `self_check.status == passed`.
- [ ] Сгенерированный `related_but_different` включает минимум `термокружка`, `стакан` (sanity).
- [ ] `hard_conflicts` включают правила для всех `related_but_different.subject`.
- [ ] Eval accuracy ≥ baseline − 3 п. п.
- [ ] 812-профиль активирован через API.
- [ ] Snapshot `config/seo/category_profiles/1/812/v1.812.<date>-auto.json` закоммичен.

#### On failure

- LLM галлюцинирует → уточнить prompt, задать явный список возможных subject-кандидатов (из `axes.product_type_axes`).
- Accuracy просела > 3 п. п. → не активировать. Исследовать: какие кейсы начали выпадать в `rejected`? Скорее всего `hard_conflicts` слишком строгие. Смягчить: перевести часть конфликтов в soft-penalty (это расширение схемы, согласовать с оператором).

#### Commit

```
[phase0-step8] real derive_category_profile + activate 812

- Replace skeleton with heuristic + LLM implementation.
- Corpus reader, heuristic, llm_refine, constraint_builder modules.
- Prompt prompts/derive_v1.txt logged via SeoLlmCallLog.
- 812 profile regenerated and activated; accuracy vs baseline
  documented in config/seo/category_profiles/1/812/<ver>.json::self_check.
- Snapshot committed for diff visibility on future re-derives.
```

---

### Step 9 — Снос `del category_profile` и legacy-compat fallback

#### Цель

Убрать все оставшиеся следы «работы без профиля». После Step 9 `matcher_v2` категорически требует активный профиль.

#### Предусловия

- Step 8 closed.
- 812 активирован с real derive.

#### Touched files (modified)

```
src/app/services/seo/matcher_v2/api.py                     (remove _build_legacy_compat_profile, remove flag branch)
src/app/services/seo/category_profile.py                   (ProfileMissingError становится дефолтом)
tests/seo/phase0/test_matcher_v2_requires_profile.py       (new)
```

#### Action steps

1. В `matcher_v2/api.py`:
   - Удалить функцию `_build_legacy_compat_profile`.
   - Удалить ветку `if strict: raise else: category_profile = ...`. Заменить на:
     ```python
     if category_profile is None:
         raise ProfileMissingError(
             f"No active SeoCategoryProfile for project_id={project_id}, category_id={category_id}. "
             f"Run derive_category_profile and activate before calling matcher_v2."
         )
     ```

2. В `category_profile.py` обновить docstring `load_active_profile`: теперь вызывающая сторона обязана обрабатывать `None` и, скорее всего, поднять `ProfileMissingError`.

3. Убрать переменную окружения `SEO_MATCHER_V2_STRICT_PROFILE` из всех мест (кроме истории коммитов). Она больше не нужна.

4. **Тест** `test_matcher_v2_requires_profile.py`:
   - Создать категорию-заглушку без активного профиля.
   - Вызвать `matcher_v2/run` API → 400 с сообщением `"No active SeoCategoryProfile"`.
   - Создать категорию с профилем, у которого `self_check.status = "failed"` (искусственно, через фикстуру).
   - Вызвать → тоже 400 (loader должен отфильтровать неудачные профили? — нет, loader пускает; это self-check-gated активация должна предотвратить это на уровне данных. Тест проверяет текущее поведение, фиксирует контракт).

#### Tests to pass

```bash
pytest -x tests/seo/phase0/test_matcher_v2_requires_profile.py
pytest -x tests/seo/                                          # включая 812-specific
grep -rn "SEO_MATCHER_V2_STRICT_PROFILE" src/                 # 0 результатов
grep -rn "_build_legacy_compat_profile" src/                  # 0 результатов
```

#### DoD

- [ ] Любая категория без активного профиля → `matcher_v2` отвечает 400 с понятной ошибкой.
- [ ] 812 продолжает работать (у него активный профиль с Step 8).
- [ ] Переменная окружения и compat-функция удалены.

#### Commit

```
[phase0-step9] matcher_v2 strictly requires active CategoryProfile

- Remove _build_legacy_compat_profile and SEO_MATCHER_V2_STRICT_PROFILE flag.
- matcher_v2.api raises ProfileMissingError when load_active_profile is None.
- Test: API returns 400 with actionable message for categories without profile.
```

---

### Step 10 — Регресс-прогон и полный eval

#### Цель

Убедиться, что после всех рефакторингов система для 812 работает не хуже baseline, и собрать дельту для документации.

#### Предусловия

- Step 9 closed.

#### Action steps

1. Полный прогон `matcher_v2` для всех labeled SKU 812 через API.
2. Прогон `eval/matcher/run` для 812 с всеми `nm_ids`.
3. Сравнить `eval_summary_new.json` с `baselines/812_pre_phase0/eval_summary.json`:
   - accuracy_new vs accuracy_baseline.
   - F1 per bucket (primary, secondary, broad, rejected).
   - Сколько label'ов сменили bucket между путями.
4. Записать `tests/seo/phase0/baselines/812_post_phase0/eval_summary.json` + `manifest.json` с `baseline_git_sha` Step 9.
5. Создать `phase0/RETRO.md` (см. Step 11).

#### Tests to pass

Ручная проверка + сохранение артефакта.

#### DoD

- [ ] `eval_summary_new.json` сохранён.
- [ ] `accuracy_new >= accuracy_baseline - 0.03`.
- [ ] `phase0/RETRO.md` создан с наблюдениями.

#### On failure

Если accuracy просела > 3 п. п. — НЕ мёржить Step 9, откатить на Step 8 (там compat-fallback ещё есть), расследовать, исправлять профиль или правила.

#### Commit

```
[phase0-step10] post-refactor regression snapshot for 812

- Capture eval_summary for 812 after full profile-driven path.
- Compare to Step 1 baseline: accuracy <delta>, F1 drift per bucket.
- Commit baselines/812_post_phase0/ for historical reference.
```

---

### Step 11 — Документация и retrospective

#### Цель

Обновить доки, чтобы следующий агент видел актуальное состояние.

#### Touched files (modified)

```
docs/seo-module/CONTEXT_PRIMER.md                     (update "where we are now")
docs/seo-module/AGENTS.md                             (если контракт поменялся)
docs/seo-module/CATEGORY_PROFILE_SPEC.md              (changelog: что добавили в процессе реализации)
docs/seo-module/ROADMAP.md                            (§2 таблица: Phase 0 = COMPLETED)
```

#### Touched files (new)

```
docs/seo-module/phase0/RETRO.md
```

#### Action steps

1. `RETRO.md`:
   - Что заняло больше, чем ожидалось.
   - Какие полевые open questions (из SPEC §13) закрыты, какие остались.
   - Какие эвристики derive работают плохо и требуют внимания в Phase 1.
   - Какие ошибки в SPEC обнаружены и пофикшены.

2. Обновить `ROADMAP.md §2` — таблица фаз, пометить Phase 0 как `✅ COMPLETED <date>`.
3. Обновить `CONTEXT_PRIMER.md § "Текущее состояние" — зафиксировать новую реальность (любая категория с профилем работает).
4. Changelog в `CATEGORY_PROFILE_SPEC.md`.

#### Tests to pass

Ревью документов.

#### DoD

- [ ] `RETRO.md` отражает реальный ход работы.
- [ ] `ROADMAP.md` обновлён.
- [ ] `CONTEXT_PRIMER.md` не содержит утверждений, противоречащих новой реальности.

#### Commit

```
[phase0-step11] Phase 0 retro + docs refresh

- Retro notes on heuristic quality, open SPEC questions closed, delta.
- Roadmap: Phase 0 → COMPLETED.
- Context primer updated for Phase 1 starting state.
```

---

## 4. Общие правила по всем шагам

### 4.1. PR-strategy

- Один шаг = минимум один PR (можно несколько, если step крупный).
- Title: `[phase0-step<N>] <короткая суть>`.
- Description должен ссылаться на этот документ: `Implements Step <N> from PHASE_0_EXECUTION_PLAN.md`.
- Каждый PR мёржится только при зелёных CI и прохождении tests-to-pass шага.

### 4.2. Rollback-дисциплина

На любом шаге, если DoD не достигается в разумные сроки, rollback — через `git revert`, не через «смягчение критериев». Критерии — норма контракта.

### 4.3. Не ломать зависимые зелёные тесты

Существующие тесты в `tests/seo/` должны оставаться зелёными на каждом шаге. Если падают — Step не закрыт.

### 4.4. Коммуникация с оператором

Шаги 1, 8, 10 требуют валидации оператором (baseline, активация, accuracy). В остальных — агент принимает решения автономно в рамках контракта.

Если шаг требует изменения `CATEGORY_PROFILE_SPEC.md` — это сигнал «что-то идёт не так», обязательно обсуждение с оператором до продолжения.

### 4.5. Зависимости между шагами

```
Step 1 ──▶ 2 ──▶ 3 ──▶ 4 ──▶ 5 ──▶ 6 ──▶ 7 ──▶ 8 ──▶ 9 ──▶ 10 ──▶ 11
                  ╲     ╱
                    (parallelizable: Step 3 and 4 can start in same PR chain,
                     but Step 4 unblocks 5; Step 3 unblocks 7)
```

- Steps 3, 4 частично параллельны (один готовит DB + skeleton, второй — dataclass accessors), но Step 5 требует обоих.
- Step 7 (API) и Step 8 (real derive) параллельны после Step 6.
- Steps 9–11 строго последовательны.

---

## 5. Что **запрещено** делать во всех шагах

- ❌ Менять схему `SeoCategoryProfile` ORM (за пределы того, что уже в базе в Step 3) без breaking-PR и обновления SPEC.
- ❌ Добавлять категорийные литералы в любой файл, кроме `config/seo/category_profiles/<cat>/<ver>.json` и `config/seo/global_vocabulary.json`.
- ❌ Оставлять `TODO`-комменты без ссылки на конкретный следующий шаг/issue.
- ❌ Коммитить напрямую в `main`.
- ❌ Активировать профиль вручную SQL'ом в обход API/CLI.

---

## 6. Checklist финала Phase 0

Когда все 11 шагов закрыты:

- [x] Step commits 1–10 доступны в истории.
- [ ] `pytest -x tests/seo/` зелёный. Known unrelated failure remains: `tests/seo/test_matcher_retention.py::test_keeps_referenced_runs`.
- [x] `grep -rn "del category_profile" src/` = 0 по Step 10 artifact.
- [x] Active matcher/query paths literal-free по Step 10 artifact.
- [x] Активный профиль 812 в БД: `id=1`, `version=v1.812.skeleton.243953b2`, `schema_version=category_profile_v1`, `self_check.status=passed`.
- [x] Eval regression ≤ 3 п. п.: baseline `0.1678`, current `0.2349`, drift `+0.0671`, minimum acceptable `0.1378`, verdict `pass`.
- [x] `PHASE_0_RETRO.md`, `ROADMAP.md`, `CONTEXT_PRIMER.md` обновлены в Step 11.
- [x] `phase0/TEST_PLAN.md` обновлён фактическими результатами.

После этого — Phase 1 может стартовать.

---

## 7. Changelog

- **2026-04-24 v1** — initial. 11 атомарных шагов зафиксированы после согласования Phase 0 scope.
- **2026-04-24 v1.1** — Phase 0 completion status, Step artifact links and final acceptance summary added.

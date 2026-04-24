# Phase 0 — Test Plan

> Статус: **нормативный тестовый контракт Phase 0**.
> Парный документ: `PHASE_0_EXECUTION_PLAN.md` (шаги реализации). Этот документ говорит, что именно должно быть протестировано и как измерить «сделано».

---

## 0. TL;DR

- **Тестов по уровням:** unit, integration, snapshot (bit-for-bit), regression (eval accuracy budget).
- **Жёсткие ворота Phase 0:** snapshot-тесты 812 = bit-for-bit baseline; eval accuracy drift ≤ 3 п. п.; 0 совпадений `del category_profile` в `src/`.
- **Все тесты лежат под `tests/seo/phase0/`.** Не смешивать с корневыми `tests/seo/`.

---

## 1. Уровни тестирования

### 1.1. Unit

Тестируют чистые функции без БД/сети. Используют in-memory фикстуры.

Критерии: быстро (<100 мс на тест), детерминистично, читаемо.

### 1.2. Integration

Тестируют взаимодействие с БД (через `pytest-postgresql` или тестовую сессию), валидаторы с реальными Pydantic-моделями, CLI-скрипты.

Критерии: одна транзакция на тест (rollback в teardown), не ходим во внешние сервисы.

### 1.3. Snapshot (bit-for-bit)

Сравнение вывода профиль-driven пути с зафиксированным baseline (Step 1 манифест).

Критерии: никакие дифы не допускаются, кроме явно согласованных в коде теста через whitelist-поля.

### 1.4. Regression (eval accuracy)

Прогон `matcher_v2 + eval` на 812-labels, сравнение с baseline.

Критерии: accuracy_new ≥ accuracy_baseline − 0.03. Шире — per-bucket F1, отдельные правила не деградируют > 5 п. п.

### 1.5. Negative

Проверка, что система корректно отказывается работать в невалидных условиях (нет профиля, сломанная схема, `self_check.status == failed`).

Критерии: ошибка с понятным сообщением и правильным HTTP-кодом (400/409/422).

---

## 2. Тесты по шагам

Каждый Step имеет свой `tests/seo/phase0/test_*.py`. Ниже — матрица.

### Step 1 — Baseline capture

Файл: `scripts/phase0/capture_baseline.py` (CLI, не pytest).

**Проверки:**
- Скрипт завершается с exit 0.
- `manifest.json` содержит: `baseline_git_sha`, `captured_at`, `eval_accuracy > 0`, ≥3 reference nm_ids.
- Все упомянутые в манифесте файлы физически существуют и валидный JSON.

**Тест:** `tests/seo/phase0/test_baseline_manifest.py`
```python
def test_baseline_manifest_present_and_valid():
    manifest = Path("tests/seo/phase0/baselines/812_pre_phase0/manifest.json")
    assert manifest.exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["eval_accuracy"] > 0
    assert len(data["reference_sku_nm_ids"]) >= 3
    for nm_id in data["reference_sku_nm_ids"]:
        assert (manifest.parent / f"matcher_v2_sku_{nm_id}.json").exists()
```

### Step 2 — Global vocabulary

Файл: `tests/seo/phase0/test_vocabulary_loader.py`.

**Проверки:**
1. `load_global_vocabulary()` возвращает объект, `schema_version == "global_vocabulary_v1"`.
2. Таксономии непусты (audience, expressive, color, material).
3. **Snapshot bit-for-bit**: синхронизировать с `_RECIPIENTS`, `_EXPRESSIVE`, `_COLORS`, `_AUDIENCE_GROUPS`, `_MATERIAL_CONSTRAINTS` из Step 2 source-of-truth (in-code константы на момент Step 2).
4. Повторный вызов `load_global_vocabulary()` быстрее первого (lru_cache работает).
5. Несуществующий путь → explicit FileNotFoundError.
6. Невалидный `schema_version` → explicit AssertionError.

**Критерий pass:** все 6 проверок зелёные.

### Step 3 — Derive skeleton + validator

Файлы:
- `tests/seo/phase0/test_category_profile_validator.py`
- `tests/seo/phase0/test_category_profile_derive_skeleton.py`

**Validator-проверки (≥10 кейсов):**

| # | Вход | Ожидаемый результат |
|---|---|---|
| 1 | Payload из SPEC §10.1 (hardcoded 812) | `status=passed`, все checks pass |
| 2 | `schema_version="category_profile_v2"` | pass fail, `check=schema_version_is_v1` |
| 3 | `subject.primary=""` | fail, `check=subject_non_empty` |
| 4 | `subject.primary_aliases=[]` | fail, `check=subject_non_empty` |
| 5 | `related_but_different=[{subject:"стакан",...}]` без соответствующего `hard_conflict` | fail, `check=hard_conflicts_cover_related` |
| 6 | `bucket_cutoffs={primary:0.3, secondary:0.35, ...}` | fail, `check=bucket_cutoffs_monotonic` |
| 7 | `constraint=thermal` не используется ни в `hard_conflicts` ни в `guards` | fail, `check=constraint_references` |
| 8 | `hard_conflicts[].requires_sku_any[].unknown_predicate: "x"` | fail, `check=hard_conflicts_syntax` |
| 9 | `sku_guards.characteristic_mappings[].target.field="unknown_field_xyz"` | fail, `check=guards_target_known_fields` |
| 10 | Наличие `recipient_synonyms` (что-то из глобального словаря) → fail | fail, `check=no_cross_category_duplication` |
| 11 | Валидный payload + ≥20 labels в БД → eval_smoke runs | check=`eval_smoke` с numeric result |

**Derive skeleton-проверки:**

- `derive_category_profile(project=1, category=812, dry_run=True)` → `DeriveResult(profile=None, self_check.status="passed", run_id: UUID)`.
- `dry_run=False` → запись в `seo_category_profiles` с `is_active=False`, запись в `seo_category_profile_derive_runs` со `status="succeeded"`, snapshot-файл создан.
- Повторный вызов с `dry_run=False` не создаёт дубликаты при том же `evidence_hash` (идемпотентность).
- `derive_category_profile(project=1, category=99999)` → `NotImplementedError("skeleton only supports 812")`.

### Step 4 — Loader accessors

Файл: `tests/seo/phase0/test_category_profile_loader.py`.

**Проверки:**
1. `load_active_profile(project=1, category=812)` возвращает `CategoryProfile` (активный профиль из Step 3).
2. Все свойства возвращают непустые значения:
   - `subject_primary == "кружка"`.
   - `"кружка" in subject_primary_aliases`.
   - `len(subject_related) >= 2` (термокружка, стакан).
   - `len(hard_conflicts_list) >= 2`.
   - `scoring_weights["product_type_match"] > 0`.
   - `bucket_cutoffs_map["primary"] > bucket_cutoffs_map["secondary"]`.
3. **evaluate_hard_conflicts** coverage:
   - Query product_type=термокружка vs SKU product_type=кружка → ≥1 конфликт со словом "термокружка".
   - Query constraint=thermal vs SKU constraint=set() → конфликт.
   - Query constraint=beer_use_case vs SKU без "пив" токена → конфликт.
   - Query product_type=кружка vs SKU product_type=кружка → 0 конфликтов.
4. `load_active_profile(project=1, category=99999)` → None (нет профиля, backward-compat).
5. Payload с неизвестным `schema_version` → `CategoryProfileError`.

### Step 5 — guards profile-driven (bit-for-bit)

Файл: `tests/seo/phase0/test_guards_bit_for_bit_812.py`.

**Проверки (по каждому reference-запросу/SKU из Step 1 baseline):**

```python
@pytest.mark.parametrize("nm_id", REFERENCE_SKU_NM_IDS)
def test_apply_sku_guards_profile_matches_legacy(session, profile_812, nm_id):
    sku_initial, evidence, meaning = load_reference_fixture(nm_id)
    legacy = apply_sku_guards(sku_initial.model_copy(deep=True), evidence=evidence, meaning_payload=meaning)
    new = apply_sku_guards_v2(sku_initial.model_copy(deep=True), evidence=evidence,
                               meaning_payload=meaning, profile=profile_812,
                               vocabulary=load_global_vocabulary())
    assert _normalize_atoms(legacy) == _normalize_atoms(new), _diff_message(legacy, new)
```

`_normalize_atoms` нормализует порядок атомов (сортировка по `(type, field, str(value))`), чтобы `==` не зависел от order.

**Аналогично для queries** (по 10 reference query_id из baseline).

**Pass-критерий:** 100% reference входов дают идентичный вывод.

**Anti-literal assertion (структурный, отдельный тест):**
```python
def test_guards_profile_has_no_hardcoded_category_literals():
    source = Path("src/app/services/seo/atoms/v1/guards_profile.py").read_text("utf-8")
    for literal in ("термокруж", "круж", "пивн", "кофемаш", "в машину", "без крыш", "без рисун", "рюкзак"):
        assert literal not in source, f"{literal!r} found in guards_profile.py — must come from profile/vocabulary"
```

### Step 6 — matcher_v2 profile-driven (bit-for-bit)

Файл: `tests/seo/phase0/test_matcher_v2_bit_for_bit_812.py`.

**Проверки:**

```python
@pytest.mark.parametrize("nm_id", REFERENCE_SKU_NM_IDS)
def test_matcher_v2_result_matches_baseline(session, profile_812_active, nm_id):
    baseline = json.loads(Path(f"tests/seo/phase0/baselines/812_pre_phase0/matcher_v2_sku_{nm_id}.json").read_text("utf-8"))
    result = run_matcher_v2(session, project_id=1, category_id=812, nm_id=nm_id)
    expected_rows = _sort_rows(baseline["results"])
    actual_rows = _sort_rows(result.results)
    assert len(expected_rows) == len(actual_rows)
    for exp, act in zip(expected_rows, actual_rows):
        assert exp["normalized_query_id"] == act["normalized_query_id"]
        assert exp["bucket"] == act["bucket"], f"bucket drift for {exp['normalized_query_id']}"
        assert abs(exp["score_total"] - act["score_total"]) < 1e-6, f"score drift"
        assert exp["eligibility_verdict"] == act["eligibility_verdict"]
        assert set(exp["matched_atoms"]) == set(act["matched_atoms"])
        assert set(exp["conflict_atoms"]) == set(act["conflict_atoms"])
```

**Anti-literal asserts:**
- `grep -r "del category_profile" src/` → 0.
- `rules/conflicts.py`, `rules/scoring.py`, `rules/features.py` не содержат литералов `"термокруж"`, `"круж"`, `"пив"`, `"кофемаш"`, `"рюкзак"`, `"сумка"`.

**Legacy-isolation check:**
- `src/app/services/seo/query_meaning_matcher/matcher.py` — проверить, что теперь это thin re-export (≤50 строк, нет определения `_hard_conflicts` / `_product_type_score` / `_FeatureSet` напрямую, только `from app.services.seo._legacy.matcher_v1 import *`).

### Step 7 — Admin API

Файл: `tests/seo/phase0/test_seo_category_profile_api.py`.

**Happy-path:**
- `GET /api/seo/project/1/category/812/profile/active` → 200, `payload.schema_version == "category_profile_v1"`.
- `GET .../history` → 200, список ≥1.
- `GET .../derive-runs` → 200, список ≥1.
- `POST .../derive?activate=false` → 201, создана новая версия с `is_active=False`.
- `POST .../activate` с `version=<valid>` → 200, `is_active=True` для новой, `False` для старой.
- `POST .../rollback` → возвращает активным предыдущую.

**Negative:**
- `POST .../activate` с несуществующей версией → 404 `{"error": "profile_not_found"}`.
- `POST .../activate` с `self_check.status="failed"` → 409 `{"error": "self_check_not_passed"}`.
- `GET active` для категории без активного → 404 `{"error": "no_active_profile"}`.
- Любой POST без auth → 401 (если auth включен; если нет — прокинуть в WaitingFuture).

### Step 8 — Real derive

Файл: `tests/seo/phase0/test_derive_812_real.py`.

**Проверки:**
1. `derive_category_profile(project=1, category=812, method="derive_heuristic_plus_llm_v1", dry_run=True)` (с замоканным LLM, возвращающим фикстурный ответ):
   - `result.self_check.status == "passed"`.
   - `result.profile_payload.subject.primary == "кружка"`.
   - `"термокружка" in [r.subject for r in result.profile_payload.subject.related_but_different]`.
   - `"стакан" in [r.subject for r in result.profile_payload.subject.related_but_different]`.
   - `len(result.profile_payload.hard_conflicts) >= 3`.
2. LLM-stub: зафиксированная JSON-фикстура в `test_derive_fixtures/llm_response_812.json`, чтобы тест не зависел от реальной LLM.
3. Sanity на `product_type_aliases`: содержит ключ `"кружка"`, `"match_any_prefix"` включает `"круж"`.

**Тест accuracy — отдельно (не в pytest):**
```bash
python scripts/phase0/compare_eval_to_baseline.py \
  --baseline tests/seo/phase0/baselines/812_pre_phase0/eval_summary.json \
  --current  tests/seo/phase0/baselines/812_post_phase0/eval_summary.json \
  --max-drift 0.03
```
Exit 0 = прошли порог, exit 1 = просели больше.

### Step 9 — matcher_v2 requires profile

Файл: `tests/seo/phase0/test_matcher_v2_requires_profile.py`.

**Проверки:**
- Для `category_id=99999` (без активного профиля): POST `/api/seo/matcher/v2/run` → 400, body содержит `"ProfileMissingError"` и подсказку про `derive_category_profile`.
- Для 812 (активный профиль): POST `/api/seo/matcher/v2/run` → 200.
- `load_active_profile(project=1, category=99999)` → None (backward-compat loader).
- Grep: `SEO_MATCHER_V2_STRICT_PROFILE` не встречается в `src/`.

### Step 10 — Regression snapshot

Не pytest. Скрипт `scripts/phase0/compare_eval_to_baseline.py`.

**Проверки:**
- accuracy_new ≥ accuracy_baseline − 0.03.
- F1 ни для одного бакета не просел > 0.05.
- Сколько labels сменили bucket (должно быть <15% от общего числа).

### Step 11 — Docs

Не автоматизируется. Ручное ревью документов.

---

## 3. Meta-уровень: Phase 0 acceptance tests

Эти тесты запускаются **в конце** Phase 0 и являются гейтом на мёрж в `main`.

Файл: `tests/seo/phase0/test_phase0_acceptance.py`.

```python
def test_no_del_category_profile_in_src():
    """Step 6 DoD: ни одного `del category_profile` в исходниках."""
    import subprocess
    result = subprocess.run(["rg", "--count", "del category_profile", "src/"],
                            capture_output=True, text=True)
    assert result.returncode != 0, f"Found occurrences:\n{result.stdout}"

def test_hardcoded_category_literals_isolated_to_config():
    """Steps 5,6 DoD: литералы категории 812 только в config/ и tests/, не в src/app/services/seo/**."""
    forbidden = ["термокруж", "круж", "пивн", "кофемаш", "в машину", "без крыш", "без рисун"]
    paths_to_scan = Path("src/app/services/seo").rglob("*.py")
    violations = []
    for path in paths_to_scan:
        if "/_legacy/" in str(path):
            continue
        src = path.read_text("utf-8")
        for lit in forbidden:
            if lit in src:
                violations.append(f"{path}: {lit!r}")
    assert not violations, "\n".join(violations)

def test_active_profile_for_812_exists_and_valid():
    """Step 8 DoD: активный профиль для 812, self_check=passed."""
    with session_maker() as session:
        profile = load_active_profile(session, project_id=1, category_id=812)
        assert profile is not None, "No active profile for 812"
        assert profile.payload.get("schema_version") == "category_profile_v1"
        self_check = profile.payload.get("self_check") or {}
        assert self_check.get("status") == "passed", f"self_check not passed: {self_check}"

def test_matcher_v2_rejects_unknown_category():
    """Step 9 DoD: API возвращает 400 для категории без профиля."""
    response = client.post("/api/seo/matcher/v2/run",
                           json={"project_id": 1, "category_id": 99999, "nm_id": 123})
    assert response.status_code == 400
    assert "ProfileMissingError" in response.json()["detail"]
    assert "derive_category_profile" in response.json()["detail"].lower()

def test_812_baseline_not_regressed():
    """Step 10 DoD: eval accuracy не хуже baseline - 3 п. п."""
    pre  = json.loads(Path("tests/seo/phase0/baselines/812_pre_phase0/eval_summary.json").read_text("utf-8"))
    post = json.loads(Path("tests/seo/phase0/baselines/812_post_phase0/eval_summary.json").read_text("utf-8"))
    drift = pre["eval_accuracy"] - post["eval_accuracy"]
    assert drift <= 0.03, f"accuracy regressed by {drift:.4f} (> 0.03 budget)"
    for bucket in ["primary", "secondary", "broad", "rejected"]:
        f1_drift = pre["f1_per_bucket"][bucket] - post["f1_per_bucket"][bucket]
        assert f1_drift <= 0.05, f"bucket={bucket} F1 drift {f1_drift:.4f}"
```

**Эти тесты — условие мёржа Phase 0.** Если хоть один red — Phase 0 не закрыта.

---

## 4. Test fixtures

### 4.1. Reference SKU и queries

В `tests/seo/phase0/reference_ids.py`:
```python
REFERENCE_SKU_NM_IDS = [291861306, 535441190, ...]        # заполняется в Step 1
REFERENCE_QUERY_IDS  = [...]                                # top-10 by ranking_value
```

Эти id используются во всех snapshot-тестах (Step 5, 6).

### 4.2. Baseline snapshots

Фиксированы в Step 1, не мутируются до Step 10. В Step 10 добавляется `baselines/812_post_phase0/`.

### 4.3. LLM mock

В `tests/seo/phase0/test_derive_fixtures/llm_response_812.json` — зафиксированный ответ LLM для `derive_v1`. Это делает Step 8 тесты детерминистичными.

Для реального прогона derive (`--activate`) LLM используется настоящий, но это не автоматизируется как pytest-тест — это CLI-процедура.

---

## 5. CI integration

`.github/workflows/seo-phase0.yml` (создаётся в Step 1):

```yaml
name: seo-phase0
on: [pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres: { image: postgres:15, ... }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: alembic upgrade head
      - run: pytest -x tests/seo/phase0/ --tb=short
      - run: rg --count "del category_profile" src/ && exit 1 || exit 0
```

Падение любого шага = PR не мёржится.

---

## 6. Manual smoke tests

После Steps 7, 8 — ручной прогон оператором:

- Открыть `http://localhost:3000/app/project/1/seo/categories/812` — страница грузится.
- Нажать «Eval 812» → prev accuracy ≥ threshold.
- Compare по `nm_id=291861306` → current column заполнен, результаты совпадают с baseline.

Эти smoke-проверки документируются в `phase0/RETRO.md`.

---

## 7. Test coverage

Цель — не процент покрытия, а покрытие **контрактов**. Каждый публичный контракт (SPEC §3 поле) должен иметь ≥1 тест, прямо или косвенно проверяющий его семантику.

Матрица «поле профиля → тест»:

| Поле из SPEC | Покрыто в тесте |
|---|---|
| `subject.primary` | Step 3 validator (non_empty), Step 4 loader |
| `subject.primary_aliases` | Step 3 validator, Step 4 loader, Step 8 derive produces |
| `subject.related_but_different` | Step 3 validator (hard_conflicts_cover_related), Step 8 derive |
| `subject.detection_hints` | Step 5 snapshot (косвенно через matches_subject_primary) |
| `product_type_aliases` | Step 3 validator, Step 6 snapshot (score_bonus применяется) |
| `constraints.derive_from_query_tokens` | Step 3 validator (constraint_references), Step 6 snapshot |
| `constraints.derive_from_sku_meaning` | Step 3 validator, Step 6 snapshot |
| `hard_conflicts` | Step 3 validator (syntax, cover_related), Step 4 evaluate_hard_conflicts, Step 6 snapshot |
| `scoring.weights` | Step 6 snapshot (выходной score совпадает с baseline) |
| `scoring.bucket_cutoffs` | Step 3 validator (monotonic), Step 6 snapshot |
| `scoring.bucket_caps` | Step 6 snapshot (размеры бакетов) |
| `scoring.enforce_material_overlap` | Step 4 evaluate_hard_conflicts |
| `scoring.materials_relevant` | Step 4 loader accessor, Step 6 snapshot |
| `user_bucket_labels` | Step 7 API test (активный профиль отдаёт labels) |
| `sku_guards.characteristic_mappings` | Step 5 snapshot |
| `sku_guards.functional_token_mappings` | Step 5 snapshot |
| `query_guards.product_type_detection` | Step 5 snapshot |
| `query_guards.required_atoms` | Step 5 snapshot |
| `query_guards.excluded_atoms` | Step 5 snapshot |
| `generated_by` | Step 3 snapshot writer (поле заполнено), Step 8 derive |
| `self_check` | Step 3 validator (все кейсы) |

Если появилось поле в SPEC, не покрытое тестом → вернуться и добавить.

---

## 8. Failure modes и что делать

| Симптом | Возможная причина | Действие |
|---|---|---|
| Snapshot-тест Step 5 red | Разошёлся порядок правил в profile-driven path | Проверить, что `profile.query_guards.product_type_detection` применяется в том же порядке, что hardcoded `if/elif` |
| Snapshot-тест Step 6 red по `score_total` | Разошлись веса скоринга | `profile.scoring_weights` должен точно совпадать с `_product_type_score` / остальными hardcoded |
| Snapshot-тест Step 6 red по `matched_atoms` | Гарды генерят разный набор атомов | Значит Step 5 снапшот был пропущен или скрытый diff. Откатить до Step 5, исследовать |
| accuracy drift > 3 п. п. (Step 10) | derive-LLM построил слишком строгие `hard_conflicts` | В Step 8 откатить активацию, сузить `hard_conflicts` или смягчить threshold в промпте |
| Negative-тест Step 9 green при включённой активации для 812 | Логика фолбэка не удалена | Grep `_build_legacy_compat_profile`, убедиться в удалении |

---

## 9. Changelog

- **2026-04-24 v1** — initial. Зафиксирован test plan в парe с PHASE_0_EXECUTION_PLAN.

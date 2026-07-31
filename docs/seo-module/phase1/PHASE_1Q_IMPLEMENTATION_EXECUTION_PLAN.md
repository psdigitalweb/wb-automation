# Phase 1Q - Implementation Execution Plan

> Статус: рабочий execution plan для Phase 1Q.  
> Дата: 2026-04-25.  
> Базовый документ: `docs/seo-module/phase1/PHASE_1Q_PRODUCT_QUALITY_RECOVERY_PLAN.md`.  
> Назначение: дать агентам и оператору пошаговый план реализации, проверки и приемки.

---

## 0. CEO Summary

Phase 1Q нужна, чтобы не масштабировать технически работающий, но продуктово слабый pipeline.

После Phase 1 мы знаем: система умеет запускаться на второй категории. Но мы не доказали, что она стабильно понимает товар так, как его ищет и покупает реальный покупатель.

Phase 1Q закрывает этот риск. Каждый шаг ниже имеет:

- конкретное действие;
- измеримый результат;
- ответственного за приемку;
- критерии pass/fail;
- правила, что делать при провале.

Phase 2 не начинается, пока Phase 1Q не закрыта или оператор явно не принимает риск.

---

## 1. Governance

### 1.1. Decision Roles

| Role | Responsibility |
|---|---|
| Operator / CEO | Принимает бизнес-смысл результата: полезен ли анализ, можно ли идти дальше |
| Lead agent in management chat | Проверяет факты по артефактам, коду, БД и тестам; не принимает отчеты слепо |
| Implementation agent | Выполняет конкретный step в отдельном рабочем чате |
| Tests | Подтверждают только техническую корректность, не бизнес-качество |

### 1.2. Acceptance Rule

Step считается закрытым только если выполнены все три условия:

1. Tests/artifacts pass.
2. Management chat проверил результат по фактам.
3. Operator approval получен, если шаг влияет на продуктовый смысл.

Если tests pass, но продуктовый результат плохой, step получает статус `needs-review` или `blocked`, не `closed`.

### 1.3. Mandatory Report Format

Каждый рабочий чат возвращает:

```text
Статус: <closed | blocked | needs-review>

Измененные файлы:
- ...

Артефакты:
- ...

DB state:
- ...

Тесты:
- command -> result

Product verdict:
- что стало лучше / хуже
- что доказано
- что не доказано

Risks / questions:
- ...

Следующий рекомендуемый шаг:
- ...
```

---

## 2. Global Non-Negotiables

- Не использовать `orders` / `conversion` как scoring или label signal.
- Не добавлять category-specific literals в active Python под `src/app/services/seo/**`.
- Не начинать Phase 2 до финального Phase 1Q gate.
- Не писать в БД в audit/experiment шагах, если это не указано явно.
- Не считать LLM-output успешным без evidence/source trace.
- Не считать vision успешным, если atoms пустые или status не `ready`.
- Не считать matcher smoke успешным только потому, что API вернул run id.
- Не менять `category_profile_v1` schema без escalation.

---

## 3. Step 1 - Reclassify Phase 1 Outcome

### Goal

Зафиксировать, что Phase 1 закрыла backend portability, но не product quality.

### Why It Matters

Без этого команда может начать Phase 2 и масштабировать слабый pipeline на новые категории.

### Actions

1. Обновить `docs/seo-module/phase1/CATEGORY_2841_REPORT.md`.
2. Убрать формулировку `proceed` как общий вердикт.
3. Заменить на:
   - `backend portability passed`;
   - `product-quality blocked pending Phase 1Q`;
   - `Phase 2 blocked unless operator waiver`.
4. Добавить ссылку на `STEP_9D_2841_MATCHER_QUALITY_FAILURE.md`.
5. Обновить `docs/seo-module/CONTEXT_PRIMER.md`.
6. Создать `docs/seo-module/phase1/PHASE_1Q_STATUS.md`.

### Code / Architecture Decisions

- Код не трогать.
- БД не трогать.
- Это governance/documentation step.

### Artifacts

- `docs/seo-module/phase1/CATEGORY_2841_REPORT.md`
- `docs/seo-module/CONTEXT_PRIMER.md`
- `docs/seo-module/phase1/PHASE_1Q_STATUS.md`

### Tests

- Docs path check.
- Verify required phrases exist.

### Pass Criteria

- Ни один актуальный документ не говорит, что 2841 production-proven.
- Phase 2 явно marked blocked by Phase 1Q.

### Approver

- Management chat verifies.
- Operator approves wording.

### If Fail

- Stop. Не начинать кодовые шаги, пока governance не исправлен.

---

## 4. Step 2 - SKU Evidence Audit

### Goal

Понять, почему текущий SKU analysis теряет живой стиль/эмоции и почему отзывы не попали в evidence.

### Target

- Project: `1`
- Category: `812`
- SKU: `535441190`

### Why It Matters

Этот SKU показывает конкретную регрессию: legacy summary богаче, текущий summary суше.

### Actions

1. Read-only проверить БД:
   - `products`;
   - `seo_sku_meaning_annotations`;
   - `seo_meaning_atoms`;
   - `seo_sku_meaning_audit_events`;
   - `wb_feedback_snapshots`.
2. Запустить `build_sku_evidence_pack` read-only.
3. Сравнить:
   - текущий `meaning_payload`;
   - текущий `sku_meaning` atoms;
   - текущий `sku_vision` state;
   - baseline `tests/seo/phase0/baselines/812_pre_phase0/sku_atoms_535441190.json`;
   - cached prompts/responses по evidence hashes `e24...`, `75a...`, `49a...`.
4. Ответить на вопросы:
   - отзывы отсутствуют в source table или не читаются?
   - почему `reviews=[]` в текущем prompt?
   - почему `category_prior.expressive.vibes=[]`?
   - почему `product_projection.expressive.vibes=[]` при наличии слов `милые`, `яркий`, `позитива`, `уюта`?
   - какие exact labels потеряны относительно baseline?

### Code / Architecture Decisions

- Только audit script / artifact.
- Runtime code не менять.
- БД не писать.

### Artifacts

- `tests/seo/phase1q/sku_535441190/evidence_audit.json`
- `tests/seo/phase1q/sku_535441190/evidence_diff_vs_baseline.json`
- `docs/seo-module/phase1/PHASE_1Q_EVIDENCE_AUDIT.md`

### Tests

- JSON validates.
- Audit script exits non-zero if required rows are missing unexpectedly.

### Pass Criteria

- Есть доказанный root cause по каждому:
  - SKU reviews;
  - category expressive prior;
  - product projection expressive;
  - legacy/current expressive delta.

### Product Acceptance

Operator должен понять из отчета простыми словами:

- какие смыслы потерялись;
- почему они потерялись;
- какой слой должен быть исправлен.

### Approver

- Management chat verifies facts.
- Operator approves interpretation.

### If Fail

- Если БД/кеши не позволяют доказать причину, статус `blocked`.
- Не переходить к prompt/code fix без root cause.

---

## 5. Step 3 - Expressive Intent Experiment

### Goal

Доказать, что отдельный expressive-only contract лучше извлекает стиль и эмоциональный контекст, чем общий SKU meaning prompt.

### Why It Matters

Текущий `SkuMeaningPayload` смешивает факты товара и SEO-смыслы. Это делает блок "Стиль и эмоциональный контекст" нестабильным.

### Actions

1. Создать read-only experiment script.
2. Взять evidence по `535441190`.
3. Сформировать отдельный input:
   - title;
   - description;
   - characteristics;
   - reviews if available;
   - category expressive prior if available.
4. Прогнать expressive-only prompt без записи в БД.
5. Сравнить:
   - current annotation;
   - old baseline;
   - expressive-only output.
6. Вывести source/evidence span для каждого label.

### Required Output Shape

Internal artifact `SeoExpressiveIntent`:

```json
{
  "style_labels": [],
  "vibe_labels": [],
  "emotion_labels": [],
  "occasion_labels": [],
  "gift_positioning": [],
  "negative_style_fit": [],
  "evidence_spans": [],
  "source_breakdown": {}
}
```

### Code / Architecture Decisions

- `SeoExpressiveIntent` сначала artifact/internal payload, не миграция.
- Не писать в `seo_sku_meaning_annotations`.
- Не менять UI.
- Не менять matcher.

### Artifacts

- `outputs/seo_model_compare/expressive_prompt_experiment_535441190.json`
- `docs/seo-module/phase1/PHASE_1Q_EXPRESSIVE_PROMPT_REVIEW.md`

### Tests

- Parser validates required keys.
- Every returned label has at least one source/evidence reference.
- No label without source.

### Pass Criteria

For SKU `535441190`, output must include evidence-backed labels covering at least:

- `милый` or equivalent supported by text;
- `яркий` or equivalent supported by text;
- `уют` / `уютный`;
- `позитив` / `позитивный`;
- `радость` or close supported emotion;
- gift/occasion labels where source supports them.

Fail if:

- output is not richer than current summary;
- labels have no evidence;
- model invents unsupported style.

### Approver

- Technical: management chat.
- Product: operator.

### If Fail

- If prompt fails despite evidence, improve prompt once.
- If still fails, problem is input normalization, not model/prompt.

---

## 6. Step 4 - Review Ingestion Fix

### Goal

Сделать отзывы покупателей доступным и проверяемым источником SKU meaning.

### Why It Matters

Отзывы показывают, как покупатель реально воспринимает товар. Без них система пересказывает продавца, а не рынок.

### Actions

1. По результатам Step 2 определить причину:
   - no source reviews;
   - wrong lookup;
   - wrong project/category scope;
   - source table mismatch;
   - truncation/filtering issue.
2. Если reviews есть, но не читаются:
   - исправить reader в `src/app/services/seo/sku_meaning/evidence.py`.
3. Если reviews отсутствуют:
   - добавить явную диагностику, не silent `[]`.
4. Добавить bounded review snippets в evidence pack.
5. Добавить source trace:
   - `reviews_available`;
   - `reviews_used_count`;
   - `reviews_truncated`;
   - `reviews_source_status`.

### Code / Architecture Decisions

- Reviews are evidence, not truth.
- Full raw reviews must not be logged into broad console output.
- LLM input must be bounded.
- No PII leakage.

### Files / Areas

- `src/app/services/seo/sku_meaning/evidence.py`
- `tests/seo/phase1q/`
- possibly schemas if diagnostics object needs typed support.

### Artifacts

- `tests/seo/phase1q/sku_535441190/review_source_status.json`
- updated `evidence_audit.json`

### Tests

- Unit: if reviews exist in fixture, evidence contains bounded reviews.
- Unit: if reviews unavailable, diagnostics explain why.
- Regression: SKU meaning evidence still builds without reviews.

### Pass Criteria

- No silent empty reviews when source status can be known.
- If reviews exist for test SKU, they enter evidence.
- Evidence contains clear `reviews_used_count`.

### Approver

- Technical: tests + management chat.
- Product: operator reviews evidence summary.

### If Fail

- If source data absent, escalate data ingestion gap.
- Do not fake review-backed meaning.

---

## 7. Step 5 - Category Expressive Prior Fix

### Goal

Понять и исправить, почему category-level buyer perception is empty or unused.

### Why It Matters

Category expressive prior должен помогать, когда SKU-specific signals weak, but must not homogenize all SKU.

### Actions

1. Trace `build_category_meaning(project_id=1, category_id=812)`.
2. Trace `build_category_meaning(project_id=1, category_id=2841)`.
3. Проверить:
   - есть ли `SeoCategoryMeaningAxes` expressive axes;
   - есть ли expressive cache;
   - какой loader выбирает source;
   - почему `expressive.vibes=[]`.
4. Если expressive exists but not loaded:
   - fix loader/selection.
5. Если expressive does not exist:
   - output diagnostic and plan build step.

### Code / Architecture Decisions

- Category expressive prior is soft context.
- SKU-specific evidence wins.
- Prior must be traceable.
- Prior must not be copied into every SKU as hard fact.

### Files / Areas

- `src/app/services/seo/meaning_extraction/category_meaning.py`
- `src/app/services/seo/expressive_llm/**`
- tests under `tests/seo/phase1q/`

### Artifacts

- `tests/seo/phase1q/category_812/category_expressive_trace.json`
- `tests/seo/phase1q/category_2841/category_expressive_trace.json`

### Tests

- Loader trace unit/integration.
- No orders/conversion involvement.
- Empty prior has explicit reason.

### Pass Criteria

- For each target category, category expressive state is one of:
  - loaded with source;
  - unavailable with explicit reason;
  - stale with explicit rebuild requirement.

### Approver

- Management chat.
- Operator if rebuild/LLM call is needed.

### If Fail

- If source exists but loader cannot safely select it, block until architecture decision.

---

## 8. Step 6 - AI Vision Recovery

### Goal

Вернуть фото как рабочий evidence layer и убрать противоречие в UI quality.

### Why It Matters

Для товаров вроде кружки с капибарой фото подтверждает визуальный мотив, стиль, упаковку и часть gift/audience signals.

### Current Failure

For SKU `535441190`:

- `sku_vision.status=error`;
- visual block empty;
- UI still shows annotation-level `FULL QUALITY`.

### Actions

1. Audit image extraction:
   - does product have image URLs?
   - does `image_urls_from_evidence` return URLs?
2. Audit provider call:
   - model;
   - timeout;
   - payload format;
   - HTTP error;
   - invalid JSON;
   - cache mismatch.
3. Add diagnostics:
   - `vision_status`;
   - `vision_error_type`;
   - `image_urls_count`;
   - `provider_model`;
   - `prompt_version`;
   - `cache_hit`;
   - `raw_error_class`.
4. Rerun controlled vision for `535441190`.
5. Store ready vision atoms only if response is useful.
6. Update summary quality semantics:
   - text meaning quality;
   - vision quality;
   - no single `FULL QUALITY` if vision failed.

### Code / Architecture Decisions

- Vision hypotheses are soft.
- Vision cannot infer invisible functional properties.
- Vision failure must be visible to operator.
- Vision diagnostics can be added without changing `category_profile_v1`.

### Files / Areas

- `src/app/services/seo/atoms/v1/vision.py`
- `src/app/services/seo/meaning_atoms/storage.py`
- `src/app/services/seo/products.py`
- frontend quality badges only if needed and explicitly scoped.

### Artifacts

- `tests/seo/phase1q/sku_535441190/vision_diagnostics.json`
- `tests/seo/phase1q/sku_535441190/vision_atoms.json`
- `tests/seo/phase1q/sku_535441190/summary_after_vision.json`

### Tests

- Unit: image URL extraction.
- Unit: vision parser accepts expected variants.
- Unit: provider failure records diagnostic.
- Integration: if image URLs exist, controlled run produces `ready` or documented external blocker.

### Pass Criteria

Pass if:

- `sku_vision.status=ready` with useful atoms for a SKU with images;
- or external provider/data blocker is documented and UI no longer claims full quality.

Fail if:

- vision error remains unexplained;
- visual atoms are empty but status says ready;
- UI still implies full quality while vision failed.

### Approver

- Technical: tests + artifacts.
- Product: operator confirms visual block makes sense.

### If Fail

- If provider issue, escalate with exact error and fallback options.
- Do not silently bypass vision.

---

## 9. Step 7 - SKU Atom Coverage Gate

### Goal

Не запускать product-quality matcher smoke, если SKU atoms отсутствуют.

### Why It Matters

Phase 1 showed that missing atoms can turn matcher into "accept almost everything".

### Actions

1. Add preflight artifact/script for selected SKU:
   - annotation exists;
   - sku_meaning atoms exist;
   - query atoms coverage exists;
   - vision status recorded;
   - active category profile exists.
2. For 2841 SKU `10533814` and `893327503`, create sanctioned atom generation path or block.
3. If LLM is required, operator must approve.

### Code / Architecture Decisions

- Atom coverage is a product-quality precondition.
- Waiver allowed only with written reason.
- Missing atoms cannot be treated as green.

### Files / Areas

- Existing matcher smoke scripts/tests or new `scripts/phase1q/`.
- `tests/seo/phase1q/category_2841/`

### Artifacts

- `tests/seo/phase1q/category_2841/sku_atom_coverage.json`

### Tests

- Preflight fails on missing atoms.
- Preflight passes when atoms exist.
- Waiver requires reason.

### Pass Criteria

- All smoke SKU have atoms, or waiver is explicit.
- No product-quality smoke proceeds silently with atoms gate disabled.

### Approver

- Management chat.
- Operator approves any LLM call or waiver.

### If Fail

- Block Step 8.

---

## 10. Step 8 - Matcher Quality Gate

### Goal

Сделать matcher smoke продуктовым gate, а не только runtime gate.

### Why It Matters

`915 primary / 0 rejected` is not a success. It is a quality failure.

### Actions

1. Add quality-gate evaluator over matcher results.
2. Compute:
   - `primary_share`;
   - `secondary_share`;
   - `broad_share`;
   - `rejected_share`;
   - corpus size;
   - top examples per bucket.
3. Fail if:
   - `primary_share > 0.70` on corpus >= 100 without waiver;
   - `rejected_share == 0` on corpus >= 100 without waiver;
   - atoms gate disabled without waiver.
4. Rerun 2841 smoke after Step 7.
5. Run 812 sanity.

### Code / Architecture Decisions

- Gate can be script/test first; no matcher architecture rewrite.
- Thresholds are quality alarms, not final relevance calibration.
- Waiver must be explicit and artifacted.

### Artifacts

- `tests/seo/phase1q/category_2841/matcher_quality_gate.json`
- `tests/seo/phase1q/category_2841/matcher_smoke_after_atoms.json`
- `tests/seo/phase1q/category_812/sanity_matcher_quality_gate.json`

### Tests

- Unit tests for pathological distributions.
- Integration smoke for 2841 and 812 sanity.

### Pass Criteria

- No selected SKU fails pathological distribution rules.
- If fail remains, Phase 2 remains blocked.

### Product Acceptance

Operator reviews per-SKU examples, not just bucket counts.

### Approver

- Technical: tests + management chat.
- Product: operator.

### If Fail

- Determine root:
  - missing atoms;
  - weak profile;
  - scoring threshold;
  - bad query meanings;
  - bad SKU meaning.
- Do not tune global thresholds as first response.

---

## 11. Step 9 - Operator Review Pack

### Goal

Собрать простой review pack, чтобы оператор видел качество без чтения raw JSON.

### Why It Matters

Product quality is approved by human review until strict labels exist.

### Actions

1. Build workbook/report with:
   - SKU meaning facts;
   - expressive labels;
   - review-backed labels;
   - vision labels;
   - bucket distributions;
   - query examples by bucket;
   - evidence/source for key labels.
2. Include:
   - `535441190` expressive regression case;
   - 2841 matcher quality case.
3. Include pass/fail summary.

### Code / Architecture Decisions

- This is operator artifact, not runtime UI.
- No DB writes except if reruns were explicitly part of prior steps.

### Artifacts

- `outputs/seo_phase1q/operator_review_pack.xlsx`
- `docs/seo-module/phase1/PHASE_1Q_OPERATOR_REVIEW.md`

### Tests

- Workbook generated and readable.
- All referenced paths exist.
- Required sheets/sections exist.

### Pass Criteria

- Operator can answer:
  - does the SKU meaning look right?
  - does expressive context look right?
  - does vision help?
  - are matcher buckets useful?

### Approver

- Operator.

### If Fail

- Return to the failed technical step; do not proceed to final gate.

---

## 12. Step 10 - Final Gate Decision

### Goal

Decide whether Phase 2 can begin.

### Possible Outcomes

| Outcome | Meaning |
|---|---|
| `proceed_to_phase2` | Phase 1Q product-quality gates pass |
| `proceed_with_waiver` | Operator accepts explicit known limitations |
| `block_phase2` | Core quality remains insufficient |

### Actions

1. Write final report:
   - what was fixed;
   - what remains risky;
   - whether reviews enter SKU meaning;
   - whether category expressive prior works;
   - whether AI vision works;
   - whether matcher quality gate passes;
   - whether `535441190` expressive regression is fixed.
2. Update `CONTEXT_PRIMER.md`.
3. Update `ROADMAP.md` if Phase 2 remains blocked or waived.

### Artifacts

- `docs/seo-module/phase1/PHASE_1Q_FINAL_REPORT.md`
- updated `docs/seo-module/CONTEXT_PRIMER.md`
- optional updated `docs/seo-module/ROADMAP.md`

### Tests

- Docs validation.
- Required facts present.

### Pass Criteria

- Final decision is explicit.
- Phase 2 status is unambiguous.
- Known limitations are not hidden.

### Approver

- Operator / CEO.

### If Fail

- Continue Phase 1Q; do not open Phase 2.

---

## 13. Implementation Chat Plan

Use separate chats for independent implementation blocks:

1. `SEO Phase 1Q - Step 1-2 Evidence Audit`
2. `SEO Phase 1Q - Step 3 Expressive Intent Experiment`
3. `SEO Phase 1Q - Step 4-5 Reviews And Category Expressive`
4. `SEO Phase 1Q - Step 6 AI Vision Recovery`
5. `SEO Phase 1Q - Step 7-8 Matcher Quality Gate`
6. `SEO Phase 1Q - Step 9-10 Operator Review And Final Gate`

Blocker patches remain inside the same step chat unless they expand scope.

---

## 14. First Chat Prompt

Use this prompt for the first implementation chat:

```text
You are implementing SEO Phase 1Q Step 1-2 Evidence Audit.

Read first:
- AGENTS.md
- docs/seo-module/CONTEXT_PRIMER.md
- docs/seo-module/ROADMAP.md
- docs/seo-module/phase1/PHASE_1Q_PRODUCT_QUALITY_RECOVERY_PLAN.md
- docs/seo-module/phase1/PHASE_1Q_IMPLEMENTATION_EXECUTION_PLAN.md
- docs/seo-module/phase1/STEP_9D_2841_MATCHER_QUALITY_FAILURE.md

Scope:
- Step 1: reclassify Phase 1 outcome in docs.
- Step 2: perform read-only evidence audit for SKU 535441190.

Do not change runtime code.
Do not write to DB.
Do not run LLM.
Do not touch UI.
Do not start Phase 2.

Required Step 1 edits:
- Update CATEGORY_2841_REPORT.md so it says backend portability passed but product-quality is blocked/pending Phase 1Q.
- Update CONTEXT_PRIMER.md to reflect Phase 1Q blocker.
- Create PHASE_1Q_STATUS.md.

Required Step 2 audit:
- Inspect DB read-only for product 535441190:
  products, seo_sku_meaning_annotations, seo_meaning_atoms, seo_sku_meaning_audit_events, wb_feedback_snapshots.
- Inspect cached sku meaning prompts/responses for annotation id 22 if available.
- Compare current meaning/atoms with tests/seo/phase0/baselines/812_pre_phase0/sku_atoms_535441190.json.
- Determine why current reviews are empty, why category expressive prior is empty, and why product_projection expressive vibes are empty.

Artifacts to create:
- tests/seo/phase1q/sku_535441190/evidence_audit.json
- tests/seo/phase1q/sku_535441190/evidence_diff_vs_baseline.json
- docs/seo-module/phase1/PHASE_1Q_EVIDENCE_AUDIT.md

Tests/checks:
- Validate JSON artifacts.
- Docs path check.

Return report:
Статус
Измененные файлы
Артефакты
DB state
Тесты
Product verdict
Risks/questions
Следующий рекомендуемый шаг
```


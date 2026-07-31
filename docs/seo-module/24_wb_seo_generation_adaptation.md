# WB SEO Generation — Adapted Prompt, Rules, And Model Policy

Date: 2026-04-22

## 0. Decision

We do not adopt `docs/seo-module/wb-seo-generator` as a standalone Excel CLI service.

We do adopt its core value:

- WB SEO generation rules;
- production-style system prompt;
- strict output schema;
- validator-driven retry loop;
- two-model policy:
  - primary: `anthropic/claude-haiku-4.5`;
  - fallback: `anthropic/claude-sonnet-4.5`.

In EcomCore this becomes the generation layer after SKU analysis and query selection:

```text
SKU evidence
+ SKU meaning / atoms
+ confirmed SKU query set
+ matcher explanations
+ current WB card content
-> GenerationBrief
-> LLM draft
-> parser + validator
-> SeoContentVersion + SeoGenerationRun
-> human review
```

## 1. What We Keep From `wb-seo-generator`

### 1.1 Prompt as product asset

The prompt is valuable because it encodes practical WB card-writing rules:

- title length and first-query placement;
- distribution of head/mid/tail queries across title, characteristics, and description;
- anti-spam constraints;
- human-readable description structure;
- brand voice control;
- self-check before output.

This should live in versioned markdown prompt assets, not as scattered Python constants.

Initial adapted asset:

- `src/app/services/seo/generation/prompts/wb_card_system_v1.md`

### 1.2 Validator as safety rail

Generation quality must be enforced by code, not trusted to the model.

Keep these validator categories:

- parse format;
- title constraints;
- description length and block structure;
- key overuse;
- unsupported or dangerous claims;
- report consistency;
- human-quality warnings.

### 1.3 Two-model policy

Use a cheap/fast model first, then a stronger fallback only when the validator blocks the result.

Default policy:

| Role | Model | Use |
|---|---|---|
| primary | `anthropic/claude-haiku-4.5` | normal generation |
| fallback | `anthropic/claude-sonnet-4.5` | parse or validation failure after primary attempt |

Both model ids must be settings-driven:

- `SEO_GENERATION_PRIMARY_MODEL`;
- `SEO_GENERATION_FALLBACK_MODEL`.

Do not reuse `OPENROUTER_CHAT_MODEL` as the generation default. That setting is currently used by meaning/atoms work and may point to another model.

## 2. What We Change For EcomCore

### 2.1 Excel brief becomes internal `GenerationBrief`

The original service expects one manually prepared Excel row per SKU. In EcomCore, the brief is built from our existing data:

| Original brief field | EcomCore source |
|---|---|
| `sku` | `products.nm_id` / vendor code |
| `товар` | product title + SKU meaning `functional.product_type` |
| `категория_wb` | `products.subject_name` / `category_id` |
| `ключевые_факты` | product characteristics, dimensions, colors, sizes, selected atoms |
| `комплектация` | product characteristics / description, if present |
| `не_входит` | negative constraints, manual notes, validator-known risky assumptions |
| `главная_боль_покупателя` | reviews, SKU meaning, negative constraints |
| `сценарии_использования` | SKU meaning use cases + selected query intents |
| `целевая_аудитория` | SKU meaning audience + vision audience hypotheses as soft evidence |
| `семантика` | confirmed `SeoSkuQuerySetItem` grouped by bucket/value |
| `голос_бренда` | project/category/store setting; fallback to `экспертный` |
| `доп_бренд_контекст` | future brand settings; optional |

No generation should run from raw imported query CSV alone. It requires a confirmed or explicitly accepted query set.

### 2.2 Query buckets replace manual `вч/сч/нч`

The old prompt uses frequency buckets:

- `вч`;
- `сч`;
- `нч`;
- `околотематика`.

In our flow these should be derived from query selection:

| Prompt group | EcomCore mapping |
|---|---|
| `вч` | top 1-3 `primary` queries by score and ranking value, only if no conflicts |
| `сч` | remaining `primary` + best `secondary` queries |
| `нч` | specific `secondary` queries with concrete use-case/attribute/audience intent |
| `околотематика` | expressive/audience/occasion atoms from `primary`/`secondary`, not raw broad queries |

Rules:

- `rejected` queries are forbidden input.
- `broad` queries are context only and should not be forced into title.
- `pinned` user selections may override inclusion but must still pass validator/conflict checks.
- `excluded` user selections are not included.

### 2.3 Generation is content versioning, not file output

The output target is not Excel. It is:

- `SeoContentVersion.title`;
- `SeoContentVersion.description`;
- `SeoContentVersion.query_snapshot`;
- `SeoContentVersion.score_breakdown`;
- `SeoContentVersion.status`;
- `SeoGenerationRun.request_payload`;
- `SeoGenerationRun.response_payload`;
- `SeoGenerationRun.error_text`.

Excel export may exist later as an operator convenience, but it is not the core architecture.

### 2.4 Human review stays mandatory

Generated content status should start as `draft` or `needs_review`.

The generation layer must not publish to WB Content API in MVP.

## 3. Adapted System Prompt Contract

The EcomCore generation prompt should keep the original Russian WB rules, but the input section changes.

### 3.1 System prompt skeleton

```text
Ты — SEO-копирайтер карточек Wildberries.

Твоя задача: сгенерировать черновик карточки WB на основе проверенного набора запросов и фактов о товаре.

Ты НЕ выбираешь запросы сам. Запросы уже отобраны EcomCore matcher/atoms pipeline.
Ты НЕ добавляешь свойства, которых нет во входных фактах.
Ты НЕ используешь rejected/excluded queries.
Если запрос конфликтует с фактами товара, не используй его, даже если он частотный.

Индексируемые зоны WB:
- название;
- характеристики;
- описание;
- бренд.

Неиндексируемые зоны:
- отзывы;
- вопросы-ответы;
- комплектация как отдельный WB блок.

Жесткие правила названия:
- до 60 символов;
- главный primary query в первых 1-3 словах, если это звучит естественно;
- без слэшей, эмодзи, звездочек, CAPS, восклицательных знаков;
- без слов: купить, цена, скидка, распродажа, лучший, идеальный, элегантный, премиальный, уникальный;
- не дублировать бренд;
- не превращать название в список ключей.

Правила распределения запросов:
- primary: название + 1-2 естественных упоминания в описании/характеристиках;
- secondary: характеристики + описание;
- long-tail/specific: описание и дополнительные характеристики;
- expressive/audience/occasion: доп. поля, сценарии, финальные блоки описания;
- broad: только как контекст, не как обязательный ключ.

Антиспам:
- каждый selected query не более 3 раз во всей карточке;
- главный primary query не более 2 раз в описании;
- не перечислять вариации одного кластера подряд;
- не повторять одно и то же слово в нескольких характеристиках без необходимости;
- не вписывать чужие бренды;
- не обещать свойства без evidence.

Описание:
- до 5000 символов;
- 6 блоков через пустую строку;
- без заголовков блоков;
- первый блок содержит конкретный сценарий;
- один блок закрывает главную боль/возражение;
- один блок честно говорит о комплектации и важных отсутствующих элементах, если они указаны;
- текст звучит как человек, не как список SEO-фраз.

Голоса бренда:
- экспертный;
- тёплый;
- минималистичный;
- игривый.

Выход строго в формате:

===== НАЗВАНИЕ =====
...

===== ХАРАКТЕРИСТИКИ =====
...

===== ОПИСАНИЕ =====
...

===== ОТЧЁТ =====
...
```

### 3.2 User message shape

Use JSON or YAML. JSON is preferable in code because our evidence packs and query sets are already JSON-shaped.

```json
{
  "product": {
    "project_id": 1,
    "category_id": 812,
    "nm_id": 123,
    "vendor_code": "...",
    "brand": "...",
    "current_title": "...",
    "current_description": "...",
    "subject_name": "...",
    "characteristics": {},
    "sizes": [],
    "colors": [],
    "dimensions": {}
  },
  "meaning": {
    "functional": {},
    "expressive": {},
    "audience": [],
    "negative_constraints": []
  },
  "atoms": {
    "hard_facts": [],
    "soft_signals": [],
    "audience_hypotheses": [],
    "negative_intents": []
  },
  "query_set": {
    "status": "confirmed",
    "primary": [],
    "secondary": [],
    "broad_context": [],
    "excluded": []
  },
  "generation_policy": {
    "brand_voice": "экспертный",
    "allow_characteristics_draft": true,
    "max_title_chars": 60,
    "max_description_chars": 5000
  }
}
```

## 4. Adapted Output Schema

Keep the four-section textual format for model output because it is readable and easy to retry.

### 4.1 Sections

```text
===== НАЗВАНИЕ =====
<one line>

===== ХАРАКТЕРИСТИКИ =====
<field>: <value>

===== ОПИСАНИЕ =====
<6 blocks separated by one blank line>

===== ОТЧЁТ =====
охват_запросов:
использованные_запросы:
не_использованные_запросы:
неиспользованные_причины:
заявления_требующие_проверки:
скрытые_зоны_задействованы:
```

### 4.2 EcomCore-specific report rules

The report must reference selected queries, not arbitrary model-invented keywords.

Validator should fail if:

- `использованные_запросы` contains a query that is not in the selected query set;
- a used query is not found in title/characteristics/description;
- an excluded/rejected query appears in output;
- `заявления_требующие_проверки` contains unsupported claims that appear in generated text.

## 5. Validation Policy

### 5.1 Blocking errors

Use blocking validation for:

- missing section delimiter;
- title over 60 chars;
- description over 5000 chars;
- description block count not equal to 6;
- fewer than 8 characteristics when characteristics generation is enabled;
- title forbidden symbols or forbidden commercial words;
- selected query repeated over allowed limit;
- main primary query missing from title first words, unless validator can mark a documented exception;
- generated claim conflicts with hard SKU atoms;
- rejected/excluded query appears in output;
- report says a query was used but it is not present.

### 5.2 Warnings

Use warnings for:

- low query coverage;
- first block lacks a concrete scenario;
- `не_входит` is provided but not mentioned;
- generic adjectives without nearby evidence;
- weak brand voice consistency.

Warnings do not trigger fallback automatically. They should be visible in UI.

### 5.3 Known fix from imported docs

The imported backpack example currently has 7 description paragraphs while the validator spec requires 6 blocks.

For EcomCore, the validator contract wins: exactly 6 blocks.

## 6. Retry And Fallback

Generation attempts:

1. Primary model: `anthropic/claude-haiku-4.5`.
2. Primary model retry with parser/validator feedback.
3. Fallback model: `anthropic/claude-sonnet-4.5`.

Retry message:

```text
Предыдущая генерация не прошла проверку.
Ошибки:
- ...

Исправь только эти ошибки.
Не добавляй новые факты.
Используй только selected queries и product evidence из входа.
Верни полный ответ в том же формате.
```

After fallback failure:

- create `SeoGenerationRun.status = failed`;
- persist `error_text`;
- keep raw response in `response_payload`;
- do not create publishable content version.

## 7. Model Settings

Recommended generation defaults:

```text
SEO_GENERATION_PROVIDER=openrouter
SEO_GENERATION_PRIMARY_MODEL=anthropic/claude-haiku-4.5
SEO_GENERATION_FALLBACK_MODEL=anthropic/claude-sonnet-4.5
SEO_GENERATION_TEMPERATURE=0.35
SEO_GENERATION_TOP_P=0.9
SEO_GENERATION_MAX_TOKENS=2600
SEO_GENERATION_MAX_ATTEMPTS=3
```

Rationale:

- generation benefits from controlled variation, so temperature should not be `0`;
- validation and retry control the risk;
- fallback is expensive and should be validation-triggered only;
- model ids are config, not hardcoded Python constants.

## 8. Persistence Contract

Every generation run stores:

- prompt version;
- rules version;
- validator version;
- primary/fallback model ids;
- source hash:
  - product evidence hash;
  - query set source hash;
  - atoms version;
  - matcher version;
- request payload without secrets;
- raw response;
- parsed output;
- validation report;
- token/cost metadata when OpenRouter returns it.

## 9. API Shape

Recommended MVP endpoints:

```text
POST /api/v1/projects/{project_id}/seo/products/{nm_id}/generation/run
GET  /api/v1/projects/{project_id}/seo/products/{nm_id}/generation/latest
GET  /api/v1/projects/{project_id}/seo/generation-runs/{run_id}
```

Run request:

```json
{
  "category_id": 812,
  "query_set_id": 10,
  "brand_voice": "экспертный",
  "force_refresh": false
}
```

The service should reject generation if:

- there is no SKU meaning/atoms;
- query set is empty;
- query set is not confirmed and request does not explicitly allow draft input;
- category readiness is still building;
- selected queries are all broad or rejected.

## 10. Implementation Order

1. Add generation settings.
2. Add prompt assets under `src/app/services/seo/generation/prompts` or `docs/seo-module/prompts`.
3. Implement `GenerationBrief` builder from product evidence + query set.
4. Implement parser and validator.
5. Implement generation service writing `SeoContentVersion` and `SeoGenerationRun`.
6. Add tests using fixture provider, no real LLM.
7. Wire generation page button only after backend is deterministic under fixture tests.

## 11. Boundary

Do not start mass generation for all categories yet.

This adaptation is the productization path for the prompt and rules. It does not override the current architecture decision that quality depends on reliable query selection and atoms/matcher gates.

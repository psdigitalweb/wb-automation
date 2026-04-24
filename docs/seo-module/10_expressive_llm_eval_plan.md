# Expressive Meaning — LLM Evaluation Spike (WB SEO Module)

Цель: **не внедряя LLM в runtime**, проверить на **реальных данных текущей БД**, даёт ли LLM значимое улучшение **expressive meaning** относительно текущего deterministic/proxy слоя (в Meaning Extraction MVP expressive почти пустой).

Spike = research/evaluation path:
- без изменений текущей архитектуры
- без matcher
- без переписывания scoring
- без generation
- без изменения query pipeline логики
- без “красивых” выводов без фактического прогона

## 1) What we compare

### Baseline (current deterministic/proxy)
- **Category expressive**: `CategoryMeaning.expressive.vibes` (детерминированный whitelist).
- **SKU expressive**: `ProductProjection.expressive.vibes` (детерминированно по SKU evidence).
- **Query expressive**: `QueryMeaning.expressive.vibes` как **MVP proxy** (`language_markers -> vibes`), без LLM.

### LLM candidate (offline only)
LLM извлекает expressive labels + уверенность + rationale + **evidence spans** из входных текстов.

Важно: LLM **не интегрируется** в runtime; результаты используются только для оценки.

## 2) Tasks (3 evaluation tracks)
1) **Category expressive meaning** (vibe / aesthetic / emotional positioning на уровне категории).
2) **SKU expressive projection** (expressive signals конкретного SKU).
3) **Query expressive meaning** (expressive intent на уровне query cluster / representative queries).

## 3) Models (OpenRouter, 3 tiers)
Проверено через OpenRouter `/models`: выбранные model ids доступны.

- Strong/expensive: `openai/gpt-5.4`
- Mid: `openai/gpt-4.1-mini`
- Cheap: `openai/gpt-4o-mini`

## 4) Categories (2–3 with expressive потенциалом)
Выбираем категории, где expressive слой потенциально важен и есть query clusters в БД:
- `812` — **Кружки** (подарок/принты/юмор/имя).
- `745` — **Тетради** (школьное/подростковое/аэстетика/стилистика).
- `821` — **Тарелки** (декор/эстетика/подарок; большой объём query clusters).

## 5) Dataset size
На категорию:
- **SKU**: 20–30 (в spike фиксируем 25).
- **Query clusters**: 30–50 (в spike фиксируем 40).

Dataset фиксируется отдельным manifest-файлом (ids + seed) для воспроизводимости:
- `docs/seo-module/datasets/wb_project_1_expressive_eval_v1.json`

## 6) Evaluation protocol (high-level)
Единый протокол: input → prompt → strict JSON output → parsing → **evidence validation** → metrics → side-by-side report.

Обязательное правило (anti-hallucination):
- Каждый vibe обязан содержать `evidence_spans[]` — подстроки из соответствующего input.
- Если хотя бы один span не найден в input → `hallucinated=true`.

Промпты и схемы фиксируются в:
- `docs/seo-module/10b_expressive_llm_eval_prompts_v1.md`

## 7) Evaluation criteria (report must cover)
1. Осмысленность expressive labels (examples + summary).
2. Стабильность (повторный прогон subset; Jaccard по labels).
3. Discriminability (пары похожих SKU/queries → различаются ли vibes).
4. Functional vs expressive queries (на subset).
5. Полезность результата для продукта (можно ли использовать как слой).
6. Шум/галлюцинации (evidence_valid_rate, hallucinated rate).
7. Latency (p50/p95).
8. Cost (tokens + pricing из OpenRouter `/models`, если доступно).

## 8) Implementation (research-only)
Runner:
- `scripts/expressive_llm_eval.py`

Запуск предполагается **внутри docker-compose `api` контейнера** (есть доступ к DB и настроенный provider abstraction).

## 9) Outputs
Raw + normalized:
- `outputs/expressive_llm_eval/<category_id>/<model>/category.json`
- `outputs/expressive_llm_eval/<category_id>/<model>/sku.json`
- `outputs/expressive_llm_eval/<category_id>/<model>/query.json`
- `outputs/expressive_llm_eval/<category_id>/<model>/*.raw.json` (полный ответ провайдера)
- `outputs/expressive_llm_eval/<category_id>/comparison.normalized.json`

Финальный отчёт:
- `docs/seo-module/12_expressive_llm_eval_report.md`

## 10) Explicit boundaries (out of scope)
- Любая production интеграция LLM в runtime.
- Matcher / scoring redesign / generation.
- Изменения deterministic extraction rules (baseline остаётся как есть).
- Изменения query pipeline логики или схемы БД.


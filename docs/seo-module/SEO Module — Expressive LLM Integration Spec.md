0. Purpose

Этот документ фиксирует, как LLM интегрируется в product-side expressive layer.

Цель интеграции:

извлекать expressive meaning категории и SKU на production-quality уровне
не смешивать expressive extraction с matcher и scoring
не ломать deterministic functional foundation
использовать LLM как отдельный semantic layer, а не как замену всей архитектуры
1. Scope

Интеграция касается только product side:

Category Meaning → expressive
Product Projection → expressive

Не касается:

Query Meaning
Matcher
Scoring
Generation
2. Architectural Role

LLM используется только для expressive extraction.

Итоговая схема:

Product Side

Raw Product Signals
↓
Functional Extraction (deterministic)
↓
Expressive Extraction (LLM-backed)
↓
Category Meaning
↓
Product Projection

LLM не строит:

functional meaning
query meaning
matching
score
3. Core Principle

Functional and expressive layers have different extraction strategies:

Functional extraction = deterministic
Expressive extraction = LLM-backed

Deterministic expressive extraction может существовать только как weak proxy / fallback, но не как основной production mechanism.

4. Source Priority
4.1 Category Expressive Meaning

Primary source:

reviews

Secondary source:

titles

Weak fallback:

empty expressive layer
optional deterministic proxy only if explicitly needed

Queries НЕ используются как источник category expressive meaning.

4.2 SKU Expressive Meaning

Primary sources:

SKU reviews
SKU title

Fallback:

Category expressive prior

Если у SKU нет достаточного expressive signal:

используется category prior
5. LLM Usage Boundary

LLM используется:

offline
precompute mode
controlled batch execution
with caching

LLM не используется:

в горячем runtime на каждый запрос
внутри matcher
внутри scoring
как обязательный synchronous dependency для пользовательского path
6. Category Expressive Extraction
6.1 Input

Для одной категории в LLM подаётся:

category_name
review snippets
optional sample_titles

Приоритет:

reviews = primary
titles = secondary

В input НЕ входят:

queries
query clusters
raw attributes dump
pricing
brand
vendor_code
6.2 Review Selection Rules

Для category-level expressive extraction:

использовать отзывы только с rating >= 4
не отбрасывать короткие отзывы
каждый отзыв технически нормализуется:
trim whitespace
truncate to fixed max length
удаляются дубли по нормализованному тексту
берётся ограниченный набор отзывов на категорию

Recommended default:

up to 100 reviews per category
6.3 Titles Usage

Titles используются только как secondary support.

Titles:

не могут быть единственным основанием для expressive conclusion
не должны перевешивать reviews
используются для слабого дополнительного контекста
6.4 Output

LLM возвращает Category Expressive Profile:

vibes[]
confidence
evidence_spans
summary

Пример shape:

{
"category_name": "...",
"vibes": [
{
"label": "...",
"confidence": 0.0,
"evidence_spans": ["...", "..."]
}
],
"summary": "..."
}

7. Product Projection Expressive Extraction
7.1 Input

Для конкретного SKU в LLM подаётся:

sku title
sku review snippets
optional category expressive prior
7.2 Output

LLM возвращает SKU expressive profile:

vibes[]
confidence
evidence_spans
7.3 Merge Rule

Итоговый expressive profile SKU формируется так:

если есть достаточный SKU-level expressive signal → использовать SKU expressive profile
если сигнал слабый или reviews отсутствуют → fallback к Category expressive prior
8. Prompt Discipline

LLM prompt должен явно фиксировать:

reviews are primary evidence
titles are secondary support
no functional attributes in output
no generic labels like:
positive
good
quality
every vibe must be evidence-backed
output must be strict JSON
9. Model Choice

Текущий baseline model:

openai/gpt-4.1-mini

Reference model:

openai/gpt-4.1

Причина выбора baseline:

лучший баланс cost / latency / evidence discipline по текущему evaluation spike

Смена baseline возможна только после нового controlled comparison.

10. Execution Mode

LLM expressive extraction запускается как отдельный pipeline step.

Recommended modes:

Category-level precompute
batch job per project × category
SKU-level enrichment
batch job for selected SKU
on create/update/reindex events
not on hot path
11. Caching and Persistence

LLM outputs должны:

кэшироваться
быть воспроизводимыми
иметь versioning

Cache key должен учитывать:

entity type
project_id
category_id / sku_id
model
prompt version
input hash

Persistence strategy:

отдельный слой precomputed expressive artifacts
не встраивать raw LLM response в matcher/scoring directly
12. Failure Policy

Если LLM недоступен или extraction не удался:

Category level
expressive layer = empty or previous cached version
SKU level
expressive = category prior
если prior отсутствует → empty expressive

Functional layer при этом продолжает работать.

13. Constraints

LLM expressive layer НЕ должен:

использовать queries как источник product/category expressive meaning
подменять functional extraction
напрямую считать score
напрямую решать релевантность query ↔ SKU
быть обязательным synchronous runtime dependency
14. Minimal Validity Criteria

LLM integration считается валидной, если:

expressive строится из product-side signals
reviews являются primary source
titles являются secondary source
output evidence-backed
category expressive profile пригоден как prior
SKU expressive profile корректно fallback’ится к category prior
система остаётся работоспособной без LLM через empty/fallback behavior
15. Final Invariant

Expressive meaning в product side является LLM-backed layer.

Это означает:

functional meaning извлекается deterministic rules
expressive meaning извлекается через LLM из product-side signals
category expressive profile строится прежде всего из reviews
SKU expressive profile уточняет category prior
queries не используются для построения expressive профиля товара или категории
16. Practical Decision

На текущем этапе фиксируется:

deterministic expressive extraction не является MVP
production-quality expressive extraction требует LLM
baseline integration strategy = offline / precompute
baseline model = openai/gpt-4.1-mini
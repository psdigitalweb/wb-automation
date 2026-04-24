SEO Module — Meaning Extraction Basis
0. Purpose

Этот документ фиксирует:

какие данные и сигналы уже подтверждены текущим кодом
какие ограничения уже известны
каких частей системы ещё нет
какие решения ещё предстоит принять перед meaning extraction plan

Этот документ не описывает финальную extraction-логику.
Он отделяет факты от design decisions.

1. Current Verified Facts
1.1 Query Side

В текущем runtime реализованы:

query ingestion
normalization
unified dataset assembly
pruning
lexical clustering
hybrid annotation
query-side profile extraction
scoring preparation
scoring

Это означает, что query side уже существует как рабочий pipeline, хотя не оформлен как отдельный архитектурный Query Meaning layer.

1.2 Product Side

В текущем runtime product-side semantic layer отсутствует.

Отсутствуют как отдельные слои:

Category Meaning
Product Meaning
Product Projection как полноценная сущность
SKU Clustering как рабочий production-блок

Product side сейчас представлен только сырым product evidence, используемым в scoring preparation.

1.3 Fields Actually Read from products

Текущий SEO runtime реально читает из products через raw SQL:

project_id
nm_id
subject_id
title
description
characteristics
sizes
colors
dimensions

Это фактически подтверждено аудитом. models.py не является полным source of truth для product schema в рамках SEO runtime.

1.4 Reviews

Reviews в SEO runtime сейчас не используются как активный semantic source.

Фактически:

тексты reviews не участвуют в runtime meaning/scoring
есть только placeholder trust-aware logic с review-count thresholds
полноценная review integration отсутствует

Следствие:

система уже сейчас обязана деградировать без reviews
reliance on reviews cannot be part of MVP extraction core
1.5 SKU Clustering

SKU clustering сейчас не готов как production layer.

Фактически:

pre-segmentation placeholder
HDBSCAN hook placeholder
noise handling placeholder
no runtime persistence of real SKU clustering outputs

Следствие:

extraction logic нельзя строить в зависимости от уже существующего SKU clustering
сначала нужен meaning foundation, потом clustering
2. Available Inputs for Meaning Extraction
2.1 Product-Side Inputs
Confirmed available now
title
description
characteristics
sizes
colors
dimensions
Optional but not integrated in runtime
reviews
Not confirmed as active SEO inputs
brand
vendor_code
rating / feedback counters

По аудиту эти поля не читаются текущим SEO scoring preparation flow.

2.2 Query-Side Inputs
Confirmed available now
raw query text
normalized query text
frequency signals
orders signals
cluster membership
hybrid annotation outputs
query-side markers / profiles

Следствие:

Query Meaning можно строить как formalized layer поверх уже существующего query pipeline
Query Meaning MVP не требует нового data source
3. Architectural Constraints Already Fixed

Следующие ограничения уже зафиксированы архитектурой:

Category Meaning строится из товаров категории
Query Meaning строится из запросов
product side и query side не смешиваются
matcher не строит meaning
система должна работать без reviews
expressive meaning является критическим value layer
Product Projection использует category expressive prior
scoring должен быть additive-only как target principle, хотя текущий runtime ему не соответствует
4. What Is Known vs What Is Not Yet Decided
4.1 Known

Подтверждено фактами:

какие product fields реально читаются
что query pipeline уже существует
что product-side meaning отсутствует
что reviews не интегрированы
что SKU clustering пока placeholder
что raw product evidence already exists
что expressive layer нужен как часть product-side model
4.2 Not Yet Decided

Ещё не зафиксировано как design decision:

точный extraction order для product-side meaning
точный extraction order для query meaning formalization
правила извлечения product-type
правила извлечения use-case
правила извлечения vibe
source priority внутри expressive extraction
fallback rules при слабом title
fallback rules при бедных attributes
precise MVP boundary for reviews integration
precise MVP boundary for clustering dependence
5. Required Decisions Before Extraction Plan

Перед написанием meaning extraction plan нужно зафиксировать:

5.1 Product-Type Extraction Rule
из каких источников извлекаем
какой источник имеет приоритет
как обрабатываются конфликты
5.2 Use-Case Extraction Rule
насколько use-case допустимо брать из attributes
когда use-case считается category-level
когда use-case считается SKU-level
5.3 Vibe Extraction Rule
из каких источников vibe извлекается в MVP
допускается ли vibe из description
как отделять expressive signals от noise
5.4 Reviews Policy
где reviews допустимы в MVP
где reviews только усиливают
что делаем, если reviews отсутствуют полностью
5.5 Aggregation Rule
как category meaning строится из множества SKU
какие сигналы считаются выбросами
как отличать category-level vibe от single-SKU vibe
6. MVP Assumptions

Пока не зафиксировано иное, для MVP принимаются следующие рабочие предположения:

extraction is deterministic-first
no LLM required
no embeddings required
reviews are optional enrichment, not foundation
product-side extraction starts from available product fields only
query-side formalization builds on current query pipeline outputs
SKU clustering is downstream of meaning, not prerequisite to meaning

Эти assumptions должны быть либо подтверждены, либо явно изменены в extraction plan.

7. What Must Not Be Assumed

До принятия отдельных design decisions нельзя автоматически считать, что:

description является надёжным semantic source
reviews можно использовать как основной источник product meaning
vibe reliably extracted from any single field
current query profiles are already equivalent to final Query Meaning
current product evidence is already equivalent to Product Projection
existing SKU clustering scaffolding can be treated as available runtime foundation
8. Output of This Basis Document

После этого документа команда должна понимать:

что уже есть в runtime
чего нет
какие inputs доступны реально
какие решения ещё нужно принять
почему extraction plan нельзя писать как будто всё уже известно
9. Next Document

Следующий документ после этого:

07_meaning_extraction_plan.md

Он должен описывать:

extraction order
source priorities
degradation rules
MVP boundaries
expected outputs

Но только после фиксации решений, перечисленных в разделе 5.

10. Final Invariant

Meaning extraction basis — это:

документ, отделяющий подтверждённые факты текущей системы
от ещё не принятых правил extraction,
чтобы дальнейшая разработка meaning layers не строилась на догадках.
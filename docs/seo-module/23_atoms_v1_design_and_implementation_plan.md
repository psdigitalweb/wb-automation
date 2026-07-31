# SEO Atoms v1 — Design And Implementation Plan

Date: 2026-04-22

## Summary

`Atoms v1` becomes the next target architecture for query matching.

The core decision from the shadow experiment:

```text
SKU evidence + reviews + vision -> SKU Atoms
Query clusters + LLM -> Query Atoms
SKU Atoms x Query Atoms -> deterministic eligibility matcher -> buckets
```

Embeddings remain useful for candidate retrieval and clustering support, but not for the final relevance decision. Final bucket assignment must be driven by structured atoms, hard constraints, confidence, and explainable policy.

This plan does not start production SEO generation. It defines the next production-preview layer needed before generation.

## Experiment Evidence

Test scope:

- project: `1`;
- category: `812` / mugs;
- SKU sample:
  - `291861306`;
  - `277132340`;
  - `292541341`;
  - `346647412`;
  - `677255519`;
  - `677255521`;
  - `678529108`;
  - `678529109`;
- manual labels: `191`;
- label distribution:
  - `primary`: `54`;
  - `broad`: `48`;
  - `rejected`: `89`.

Results:

| System | Accuracy | Primary precision | Primary recall | Bad Primary |
|---|---:|---:|---:|---:|
| Current matcher | 15.8% | 21.4% | 61.5% | 88 |
| Atoms v0.1 | 48.7% | 63.2% | 22.2% | 7 |
| Atoms v0.2b | 58.1% | 58.8% | 74.1% | 28 |
| Atoms + vision facts | 58.1% | 59.4% | not separately recomputed | 28 |
| Atoms + Vision Audience v1 | 60.7% | 59.4% | not separately recomputed | 28 |

Main artifact folders:

- `artifacts/meaning_atoms/20260422_110253_project1_category812`;
- `artifacts/meaning_atoms/20260422_112229_project1_category812`;
- `artifacts/meaning_atoms/20260422_113253_project1_category812`.

Conclusion:

- atoms architecture clearly outperforms the current matcher;
- vision adds useful SKU understanding, especially audience, occasion, style, print, motif, and packaging;
- the remaining problem is not "more lexical rules", but a stricter typed atom schema and matcher policy.

## Product Decision

Adopt `Atoms v1` as the next matcher architecture, but first as production preview / shadow mode.

Do not directly promote the current experiment code to production:

- atom fields are still inconsistent;
- confidence handling is primitive;
- negative intents are too string-like;
- query atom extraction needs role normalization;
- vision audience is useful but must not become hard evidence by default.

## Atoms v1 Goals

Atoms v1 must:

- separate hard eligibility from soft relevance;
- store evidence source and confidence for every meaning;
- support visual and audience understanding without uncontrolled hallucination;
- explain every bucket decision;
- allow eval-driven tuning before SEO generation.

Non-goals:

- no pairwise LLM matching;
- no production title/description generation in this phase;
- no all-category batch rollout until preview quality is accepted;
- no pgvector/ANN requirement for MVP.

## Schema v1

### Atom

```json
{
  "type": "product_type | attribute | numeric | visual | recipient | occasion | use_case | compatibility | expressive | exclusion | query_intent",
  "field": "volume_ml | color | design | motif | quantity | material | packaging | audience | recipient | context | ocr_text | negative",
  "value": "милая",
  "operator": "equals | close_to | contains | excludes | compatible_with",
  "role": "hard_fact | hard_requirement | soft_signal | audience_hypothesis | negative_intent | unsupported_if_missing | unknown",
  "polarity": "positive | negative | exclusion",
  "evidence_type": "product_data | review | vision | query_llm | deterministic_guard | sku_meaning | query_meaning",
  "evidence_ref": "product.characteristics[12]",
  "confidence": 0.75,
  "source_version": "vision_audience_v1"
}
```

### SKU Atoms

```json
{
  "schema_version": "sku_atoms_v1",
  "project_id": 1,
  "category_id": 812,
  "nm_id": 292541341,
  "product_identity": {},
  "hard_facts": [],
  "soft_signals": [],
  "audience_hypotheses": [],
  "negative_intents": [],
  "unknowns": [],
  "source_summary": {},
  "confidence": {}
}
```

### Query Atoms

```json
{
  "schema_version": "query_atoms_v1",
  "project_id": 1,
  "category_id": 812,
  "cluster_id": 123,
  "cluster_key": "qcl:v1:...",
  "top_query": "кружка для подруги подарочная",
  "required_atoms": [],
  "preferred_atoms": [],
  "excluded_atoms": [],
  "generic_context_atoms": [],
  "genericness": "specific | broad | generic",
  "confidence": {}
}
```

## Evidence Source Policy

Product data:

- strongest source for volume, quantity, material, color, product type, compatibility, and packaging if structured;
- can create `hard_fact`.

Vision:

- strong source for visible print, visual motif, color, transparency, visible packaging, visible set/single item, OCR;
- medium source for style/aesthetic;
- soft source for audience and occasion hypotheses;
- must not create hard facts for volume, thermal capability, coffee-machine compatibility, dishwasher/microwave suitability, or exact material unless visible text states it.

Reviews:

- useful for buyer language, emotional context, pain points, gift usage, actual use cases;
- mostly soft signals and negative intents;
- should not override product data for hard attributes.

Query LLM:

- extracts buyer intent and requirements at cluster level;
- must distinguish top-query requirements from example-query variants;
- examples may add soft context, but must not create hard requirements unless present in top query or cluster canonical intent.

Deterministic guards:

- normalize obvious hard constraints:
  - volume;
  - quantity/set;
  - `без рисунка`;
  - `термокружка`;
  - `кофемашина`;
  - `в машину`;
  - explicit recipient;
  - visible/structured print conflict.

## Matcher Policy v1

Matcher must be eligibility-first.

Step order:

1. Product type compatibility.
2. Hard requirement check.
3. Exclusion and negative intent check.
4. Bucket cap assignment.
5. Soft score inside eligible bucket.
6. Frequency boost only inside eligible bucket.

Hard reject examples:

- query requires `термокружка`, SKU is ordinary mug;
- query requires `800 мл`, SKU has `325 мл`;
- query requires `без рисунка`, SKU has visible/structured print;
- query requires `кофемашина`, SKU has no supported compatibility;
- query requires `набор 6 штук`, SKU is single item;
- query explicitly targets `папа/мужчина`, SKU has strong conflicting audience and no compatible evidence.

Soft boost examples:

- `милая`, `красивая`, `pinterest`, `эстетичная`;
- `подруга`, `любимая`, `девушка` from vision/reviews;
- `день рождения`, `новый год`, `8 марта`;
- `подарочная` if packaging or gift context exists.

Broad handling:

- product-only query stays `broad`;
- generic gift query without recipient or occasion is at most `secondary/broad`;
- frequency never creates relevance by itself.

Negative intent policy:

- negative intents must be structured, not raw text contains;
- `строгий мужской подарок` blocks male/strict gift intent, but must not block all gift queries;
- `без рисунка` blocks no-print queries if SKU has print;
- `прозрачная кружка` blocks transparent intent only if SKU is not transparent.

## Vision Audience v1 Policy

Vision prompt should ask for:

- visual facts;
- OCR;
- audience hypotheses;
- occasion hypotheses;
- style archetypes;
- supported query intents;
- negative query intents;
- uncertainty.

Use 3-4 SKU photos for extraction when available:

- main product image;
- close-up;
- packaging;
- infographic/lifestyle image.

Vision output policy:

- visual facts can support hard matching only when directly visible;
- audience/occasion from vision are soft signals;
- negative intents from vision require structured interpretation before they can reject;
- every atom must include confidence and evidence type.

## Storage

Add production-preview tables:

`seo_sku_atoms`

- `project_id`;
- `category_id`;
- `nm_id`;
- `schema_version`;
- `source_hash`;
- `atoms_payload`;
- `source_summary`;
- `status`: `draft | ready | error`;
- `created_at`;
- `updated_at`.

`seo_query_atoms`

- `project_id`;
- `category_id`;
- `cluster_id`;
- `cluster_key`;
- `schema_version`;
- `query_meaning_id`;
- `source_hash`;
- `atoms_payload`;
- `status`;
- timestamps.

`seo_matcher_runs`

- `project_id`;
- `category_id`;
- `nm_id`;
- `matcher_version`;
- `sku_atoms_id`;
- `query_atoms_version`;
- `metrics_snapshot`;
- timestamps.

`seo_matcher_results`

- `run_id`;
- `cluster_id`;
- `cluster_key`;
- `query_text`;
- `bucket`;
- `score`;
- `score_components`;
- `matched_atoms`;
- `missing_atoms`;
- `conflict_atoms`;
- `reasons`;
- `ranking_value_used`.

Raw LLM prompts/responses:

- keep in artifact/cache files;
- store only artifact path and hashes in DB.

## Backend Services

Add services:

- `sku_atoms_builder`;
- `query_atoms_builder`;
- `vision_atoms_extractor`;
- `atoms_merge_policy`;
- `atoms_matcher_v1`;
- `matcher_eval_report`.

Expected service flow:

```text
build_sku_atoms(project_id, category_id, nm_id)
  -> product data atoms
  -> review atoms
  -> vision atoms
  -> merge policy
  -> seo_sku_atoms

build_query_atoms(project_id, category_id)
  -> query clusters
  -> query meaning
  -> LLM query atoms
  -> deterministic guards
  -> seo_query_atoms

run_atoms_matcher(project_id, category_id, nm_id)
  -> load latest sku atoms
  -> load query atoms
  -> eligibility matcher
  -> persist run/results
```

## API Preview

Internal/debug endpoints:

- `POST /projects/{project_id}/seo/atoms/sku/build`
  - input: `category_id`, `nm_ids`, `use_vision=true`, `force_refresh=false`;
- `GET /projects/{project_id}/seo/atoms/sku/{nm_id}`
  - returns SKU atoms and source summary;
- `POST /projects/{project_id}/seo/atoms/query/build`
  - input: `category_id`, `limit`, `force_refresh=false`;
- `GET /projects/{project_id}/seo/atoms/query`
  - returns paginated query atoms;
- `POST /projects/{project_id}/seo/atoms/matcher/run`
  - input: `category_id`, `nm_id`, `limit`, `include_rejected`;
- `GET /projects/{project_id}/seo/atoms/matcher/runs/{run_id}`
  - returns buckets, explanations, metrics snapshot.

## UI Preview

Add to SKU Meaning Tool or a new internal page:

- SKU atoms panel:
  - hard facts;
  - soft signals;
  - audience hypotheses;
  - vision facts;
  - negative intents;
  - confidence/source.
- Query atoms panel:
  - required;
  - preferred;
  - excluded;
  - generic context.
- Matcher v1 preview:
  - Primary;
  - Secondary;
  - Broad;
  - Rejected;
  - reason columns.
- Compare mode:
  - current matcher vs atoms v1;
  - bucket delta;
  - bad primary removed;
  - target lifted;
  - regressions.

## Implementation Phases

### Phase A — Stabilize Shadow Code

- move experiment schemas toward v1 naming;
- add role/evidence/polarity fields;
- normalize values in one canonicalization layer;
- keep writing artifacts only.

Done when:

- same 8 SKU run is reproducible;
- `comparison.csv`, `vision_audience_atoms_summary.csv`, and metrics are generated by one command.

### Phase B — Persistent Preview

- add DB tables;
- persist SKU atoms/query atoms/matcher runs;
- keep existing matcher untouched;
- add internal APIs.

Done when:

- user can build atoms for selected SKU/category;
- user can inspect atoms and matcher buckets in UI;
- no production SEO generation depends on this yet.

### Phase C — Eval Expansion

- add 2-3 categories;
- collect at least 500-1000 labels;
- track metrics per category and per error type.

Done when:

- atoms v1 beats current matcher in every test category;
- bad primary reduction is stable;
- primary precision and recall thresholds are met.

### Phase D — Production Candidate

- run atoms matcher as default preview;
- keep old matcher as fallback/compare;
- only then begin SEO generation design.

## Acceptance Gates

Before using atoms v1 for generation:

- accuracy on eval: `>= 70%`;
- primary precision: `>= 70%`;
- primary recall: `>= 65%`;
- bad primary count reduced by at least `70%` vs current matcher;
- no known hard conflict class is systematically promoted to Primary;
- explanations are readable by analyst.

Current status after Vision Audience v1:

- accuracy: `60.7%`;
- primary precision: `59.4%`;
- bad primary: `28` vs current `88`;
- good enough to continue architecture, not enough for generation.

## Known Risks

- LLM may over-infer audience from visual style.
- Query clusters may contain mixed intents; examples can pollute hard requirements.
- Vision may return useful content in inconsistent JSON shapes.
- Negative intent strings can over-block unless structured.
- Labels may be inconsistent across SKU if query appears repeatedly with different product context.
- First-photo-only vision underuses packaging and OCR.

## Next Concrete Work

1. Implement `Atoms Schema v1` in experiment module.
2. Add role/evidence/polarity normalization.
3. Convert negative intents from text into structured atoms.
4. Re-run current 8 SKU + 191 labels.
5. Add 10-20 more SKU labels in mugs.
6. Only after metrics improve, add persistent preview tables and API.

# Gap Report Versus Docs

## Master Context And Architecture Docs

Documented intent:

- `docs/seo-module/00_master_context.md` says explainability and versioning are mandatory, noise handling is critical, reviews should be used carefully, semantic layers must not be mixed.
- `docs/seo-module/01_architecture.md` describes Product Side, Query Side, Matcher, Scoring, and lists generation as a non-goal for the current stage.

Actual code reality:

- Query annotation versioning is implemented through `SeoQueryAnnotationVersion` and `query_pipeline/pruning.py`, `hybrid.py`.
- Some explainability exists through matcher reasons in `SeoSkuQuerySetItem.reasons_payload`, generation validation/relevance reports in `SeoContentVersion.score_breakdown`, and debug APIs.
- Generation is now implemented through `src/app/services/seo/generation/service.py` and `src/app/routers/seo_generation.py`.

Mismatch:

- Older architecture docs still say not to implement final text generation yet, while current working tree has generation implemented.

Likely implication:

- Audit must treat docs as time-layered: `24_wb_seo_generation_adaptation.md` supersedes older non-goal statements for generation, but the contradiction should be resolved in docs.

## Roadmap

Documented intent:

- `docs/seo-module/02_roadmap.md` says current stage is pre-MVP/R&D prototype and lays out phases from SKU meaning to generation and productionization.
- It also says production SEO generation should not start before eval gates in the Atoms v1 section.

Actual code reality:

- Product/SKU analysis, query selection, and generation page/service exist.
- Generation creates `SeoContentVersion(content_kind="llm_draft", status="needs_review")`; it does not publish.

Mismatch:

- Draft generation exists before a clearly documented eval gate completion in current docs.

Likely implication:

- The audit should determine whether current generation is acceptable as preview/draft only, or whether it bypasses the quality gates intended by Atoms v1 docs.

## Atoms v1 Plan

Documented intent:

- `docs/seo-module/23_atoms_v1_design_and_implementation_plan.md` says Atoms v1 should first be production-preview/shadow, not direct promotion of experiment code.
- It proposes separate storage concepts such as `seo_sku_atoms`, `seo_query_atoms`, and matcher run persistence.

Actual code reality:

- Runtime matcher imports `src/app/services/seo/experiments/meaning_atoms/v1.py::match_atoms_v1`.
- Persistent atom storage is generic `SeoMeaningAtom` / `seo_meaning_atoms`, created by `20260422_add_seo_atoms_and_query_sets.py`.
- Query selection persistence is `SeoSkuQuerySet` / `SeoSkuQuerySetItem`; no dedicated matcher run table is evident.

Mismatch:

- Experiment code is now in a runtime path.
- Storage differs from documented separate atom tables.

Likely implication:

- Highest-priority audit item: decide whether experiment code is stable enough to be runtime dependency, or move production policy into non-experiment modules.

## Meaning Extraction Specs And Reports

Documented intent:

- `docs/seo-module/03_category_meaning_spec.md`, `04_product_projection_spec.md`, `05_query_meaning_spec.md`, and `08_meaning_extraction_execution_report.md` describe deterministic MVP meaning extraction with debug exposure.

Actual code reality:

- `meaning_extraction/types.py` defines `CategoryMeaning`, `ProductProjection`, `QueryMeaning`.
- `category_meaning.py`, `product_projection.py`, `query_meaning.py` implement deterministic builders.
- `seo_meaning_extraction_debug.py` exposes debug behavior.

Mismatch:

- Product/query/category meaning MVP exists, but persistent category/query meaning in newer runtime is split across `SeoCategoryMeaningAxes`, `SeoQueryMeaning`, `SeoMeaningAtom`, not the MVP dataclasses directly.

Likely implication:

- Audit should map which meaning representation is authoritative at each stage: MVP dataclasses, axes payload, query meaning rows, atoms payload.

## Expressive LLM Docs

Documented intent:

- `docs/seo-module/10*` through `21*` and `SEO Module - Expressive LLM Integration Spec.md` describe offline expressive extraction and safe integration.

Actual code reality:

- Offline extraction code exists under `src/app/services/seo/expressive_llm/*`.
- `category_extractive_service.py::run_single_category_expressive_extraction` states it must not be used in runtime hot paths.
- `category_meaning.py::_load_llm_expressive_from_cache` reads cached artifacts only.

Mismatch:

- No obvious DB persistence for category expressive artifacts; `expressive_llm/storage.py` explicitly uses file cache and says iteration constraint was to avoid DB migrations.

Likely implication:

- Audit should verify operational cache location/backup/versioning because expressive meaning can affect product-side category meaning without DB trace.

## WB SEO Generator Import

Documented intent:

- `docs/seo-module/wb-seo-generator/AGENTS.md` and `README.md` describe a standalone Excel/CLI batch generator.
- Core assets include `prompts/system_prompt.md`, `prompts/brief_schema.md`, `prompts/output_schema.md`, `prompts/brand_voices.md`, `docs/seo_rules_reference.md`, `docs/validation_rules.md`.
- It recommends primary model `anthropic/claude-haiku-4.5` and fallback `anthropic/claude-sonnet-4.5`.

Actual code reality:

- EcomCore does not use the standalone Excel/CLI architecture.
- It adopts a runtime prompt file `src/app/services/seo/generation/prompts/wb_card_system_v1.md`, settings in `src/app/settings.py`, provider boundary through `OpenRouterProvider`, and DB persistence through `SeoContentVersion` / `SeoGenerationRun`.

Mismatch:

- Standalone generator says SEO rules should not be hardcoded in Python. EcomCore generation service contains many validation/relevance heuristics in code, while the prompt/rules are also in markdown.

Likely implication:

- Audit should separate product rules that belong in prompt/docs from enforcement logic that must remain in code.

## Scoring Docs

Documented intent:

- `docs/seo-module/00_master_context.md` and `01_architecture.md` require scoring to include relevance, demand, competition, penalties, explainability.

Actual code reality:

- `scoring/preparation.py` and `scoring/actual.py` implement diagnostics scoring.
- `scoring/service.py` provides score persistence helper.
- `generation/service.py` has separate SEO relevance v1/v2 scoring for generated content.

Mismatch:

- `SeoScoreRun`, `SeoQueryScore`, and `SeoScoreExplanation` are not evidently used by the actual scoring route/scripts.
- Competition signal is documented as mandatory in master context, but no clear implemented competition component was confirmed in the active scoring/generation path from inspected symbols.

Likely implication:

- Audit should inspect scoring math and persistence carefully; there may be two scoring concepts: query/SKU fit scoring and generated-content SEO relevance scoring.

## Frontend Docs/Reality

Documented intent:

- `docs/seo-module/24_wb_seo_generation_adaptation.md` says wire generation page button only after backend is deterministic under fixture tests.

Actual code reality:

- Frontend generation page exists: `frontend/app/app/project/[projectId]/seo/products/[nmId]/generation/page.tsx`.
- It sets `generationEndpointReady = true`.
- It enables generation when product analyzed, query set confirmed, selected queries exist, primary queries exist, main query selected.

Mismatch:

- The hardcoded frontend readiness flag is not tied to an actual backend fixture-test status.

Likely implication:

- Audit should decide whether this is acceptable MVP UI or a premature enablement.


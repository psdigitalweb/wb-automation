# Task 19.03 — LLM Output Parser + Validation (Category Expressive)

## Purpose

Сделать строгий parser + validator для результата category expressive extraction.

## Scope

Входит:
- JSON parse (строгий)
- schema validation:
  - `version`, `task`, `category_name`, `vibes[]`, `summary`
- vibes constraints:
  - `vibes` list ≤ 5
  - `label` non-empty
  - `confidence` ∈ [0, 1]
  - `evidence_spans`: **строго 2–3** на vibe
  - каждый span ≤ 80 chars, без `\n`
- evidence validation:
  - каждый `evidence_span` должен быть точной подстрокой в `evidence_text` (из input builder)
  - если span не найден → hallucination

Не входит:
- repair/retry через LLM
- “умные” fuzzy matching эвристики (это отдельная итерация, если понадобится)

## Files to touch

- create: `src/app/services/seo/expressive_llm/category_output_parser.py`
- create: `src/app/services/seo/expressive_llm/validation.py`

## Implementation notes

- Parser должен:
  - уметь вырезать JSON из code fences (```json … ```)
  - отказать, если JSON невалиден
- Validator должен возвращать report:
  - evidence_found_count / total
  - per-vibe flags: `evidence_valid`, `hallucinated`

## Tests to run

- `pytest -q tests/test_seo_expressive_llm_category_output_parser.py`

## Expected output

- `ParsedCategoryExpressiveResult`:
  - `parsed` (normalized dict)
  - `validation` (report)

## Done criteria

- Любой невалидный JSON/shape/evidence корректно ловится тестами.


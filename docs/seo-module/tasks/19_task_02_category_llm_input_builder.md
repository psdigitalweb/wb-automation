# Task 19.02 — Category LLM Input Builder (Reviews primary + Titles secondary)

## Purpose

Построить детерминированный builder LLM input payload для category expressive extraction.

## Scope

Входит:
- вход: `category_name`, review snippets, titles
- фильтр reviews: `rating >= 4` (использовать scope из Task 19.01)
- нормализация:
  - trim
  - truncate: reviews ≤ 220 chars, titles ≤ 120 chars
  - dedup (по нормализованному тексту)
  - up to 100 reviews
- titles как secondary support:
  - не сокращать до 5–10; брать весь scope (после dedup)

Не входит:
- любые semantic правила отбора (кроме rating>=4)
- query data
- LLM calls

## Files to touch

- create: `src/app/services/seo/expressive_llm/text_normalization.py`
- create: `src/app/services/seo/expressive_llm/category_input_builder.py`

## Implementation notes

- Dedup key (MVP): lowercase + collapse whitespace + `ё→е`
- Input hash: sha256 от canonical JSON payload (с отсортированными ключами)
- Evidence text для validation (Task 19.03):
  - MVP: evidence_text строится из **reviews** (titles только контекст)

## Tests to run

- `pytest -q tests/test_seo_expressive_llm_category_input_builder.py`

## Expected output

- `CategoryExpressiveInput`:
  - `payload`:
    - `category_name`
    - `reviews[]`
    - `titles[]` (optional)
  - `input_hash`
  - `evidence_text`

## Done criteria

- Builder детерминирован, лимиты соблюдаются, hash стабилен, тесты покрывают dedup/truncate/caps.


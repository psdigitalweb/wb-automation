# Task 19.04 — Expressive Storage / Cache (File-based)

## Purpose

Сделать persistence + cache для category expressive LLM outputs по стабильному ключу:

`project_id + category_id + model + prompt_version + input_hash`

## Scope

Входит:
- file-based store (чтобы избежать DB migrations в iteration 19)
- layout, который легко читать/копировать/архивировать
- сохранение:
  - raw_response (audit)
  - parsed.json
  - validation.json
  - meta.json

Не входит:
- интеграция в runtime meaning extraction
- DB table

## Files to touch

- create: `src/app/services/seo/expressive_llm/storage.py`

## Implementation notes

- Root path:
  - default: `settings.INTERNAL_DATA_DIR/seo_expressive_cache/...`
  - (опционально) override через env var, если нужно
- Cache must be read-before-write:
  - если уже есть artifact по ключу → cache hit, не перезаписывать (по умолчанию)

## Tests to run

- `pytest -q tests/test_seo_expressive_llm_storage_key.py`

## Expected output

- `CategoryExpressiveStore.get(...)` / `put(...)`
- стабильный layout paths + meta info

## Done criteria

- Результаты воспроизводимы: по ключу можно найти ровно один артефакт.


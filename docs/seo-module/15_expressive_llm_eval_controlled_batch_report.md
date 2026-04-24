# Expressive LLM Eval — Controlled Batch Run (Safe Runner)

Date: 2026-04-20

Scope: **controlled-batch only** (not full eval).

Constraints respected:
- no runtime integration
- no matcher/scoring/generation changes
- strict budget/time limits

## 1) Command (exact)

```
docker compose -f infra\docker\docker-compose.yml exec -T api python scripts/expressive_llm_eval.py run --controlled-batch --dataset docs/seo-module/datasets/wb_project_1_expressive_eval_v1.json --models openai/gpt-4o-mini --max-categories 1 --max-models 1 --max-skus-per-category 10 --max-clusters-per-category 15 --max-requests-total 12 --max-cost-usd 0.02 --max-runtime-minutes 10 --timeout-seconds 60 --temperature 0 --sku-chunk-size 8 --query-chunk-size 10 --max-input-chars 20000 --max-tokens-category 250 --max-tokens-sku 500 --max-tokens-query 500
```

## 2) Planned call matrix (from runner stdout)

- `planned_calls_total`: `5`
- `planned_calls_total_worst_with_repair`: `10`
- `planned_calls_by_task`: `category=1`, `sku=2`, `query=2`

Selected:
- category: `812` (first category in dataset, capped by `--max-categories 1`)
- model: `openai/gpt-4o-mini`
- caps: `<=10` SKU, `<=15` clusters

## 3) Actual run summary (from runner stdout)

- `requests_made`: `6`
- `elapsed_min`: `0.64`
- `cost_usd`: `0.002359`
- `cache_hits`: `3`

Repairs (from raw outputs):
- `sku_repaired`: `1` (SKU batch JSON needed a repair pass)
- `query_repaired`: `1` (one query chunk JSON needed a repair pass)
- `category_repaired`: `0`

## 4) Outputs saved

Runner outputs are written inside container volume under:

- `/data/internal_data/expressive_llm_eval/`

Then copied to host repo:

```
docker cp ecomcore-api-1:/data/internal_data/expressive_llm_eval outputs\expressive_llm_eval
```

Host files created/updated:

- `outputs/expressive_llm_eval/run_plan.json`
- `outputs/expressive_llm_eval/812/baseline/baseline.json`
- `outputs/expressive_llm_eval/812/openai__gpt-4o-mini/category.json`
- `outputs/expressive_llm_eval/812/openai__gpt-4o-mini/category.raw.json`
- `outputs/expressive_llm_eval/812/openai__gpt-4o-mini/sku.json`
- `outputs/expressive_llm_eval/812/openai__gpt-4o-mini/sku.raw.json`
- `outputs/expressive_llm_eval/812/openai__gpt-4o-mini/query.json`
- `outputs/expressive_llm_eval/812/openai__gpt-4o-mini/query.raw.json`
- `outputs/expressive_llm_eval/cache/...`

## 5) Coverage check (requested items vs returned items)

Planned (from `outputs/expressive_llm_eval/run_plan.json`):
- SKUs requested: `10`
- clusters requested: `15`

Returned:
- `sku.json` items: `3` (**missing 7**)
- `query.json` items: `5` (**missing 10**)

This indicates **schema/coverage non-compliance** by the model output for batched tasks (it did not return all items for the batch).

## 6) Quick usefulness check (expressive layer)

This is a **very small slice** and also has a coverage gap, so treat as a smoke test only.

### Category
- `category.json`: vibes list is empty (`0`)

### SKU projection (3 returned items)
- Vibes look *plausible* on the returned SKUs (e.g. `comfort`, `aesthetic`)
- Evidence validation (per-vibe) on returned SKU vibes: `6/6` valid (`1.0` rate)

### Query meaning (5 returned items)
- `expressive_intent`: `0/5` true
- returned `vibes`: empty

## 7) Immediate conclusion

- Runner safety/budget visibility is OK (hard limits + plan + cost/runtime reported).
- Expressive usefulness is **not demonstrated** at controlled-batch level yet because:
  - batch outputs are **incomplete** (missing many requested SKU/cluster items),
  - query expressive results are empty in this slice.

Next step (not executed here): add a hard guard that fails the run if a batch response does not return all requested `nm_id` / `cluster_key` items (to prevent “silent partial outputs” and reruns).


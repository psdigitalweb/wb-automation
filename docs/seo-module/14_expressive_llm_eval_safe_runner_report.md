# Expressive LLM Eval — Safe Runner Redesign Report

Date: 2026-04-20

This report covers **orchestration safety** only: staged execution, hard guards, caching/dedup, prompt size control, and pre-run visibility.

No production runtime integration. No matcher/scoring/generation changes.

## A) What was broken (why the old run was unsafe)

See detailed analysis:

- `docs/seo-module/13_expressive_llm_eval_runner_failure_analysis.md`

Key problems that caused “burn money + неизвестно сколько”:

1. **Implicit full run**: `run` effectively launched the whole call matrix by default.
2. **No hard budget/time/request guards**: nothing stopped the run when it got slow/expensive.
3. **Weak pre-run visibility**: no persisted plan, no clear “how many calls are planned”, no progress counters.
4. **Weak caching discipline**:
   - outputs could be lost on container recreate (if written into container FS),
   - no item-level cache keys by `(task, category_id, item_id, model, prompt_version, input_hash)`.

## B) What was fixed (safe staged execution + guard rails)

Code changes:

- `scripts/expressive_llm_eval.py`

### B1. Staged modes (safe by default)

Runner now supports 4 explicit modes:

- `--dry-run`: dataset collection + planned calls + prompt size estimates; **no LLM calls**
- `--micro-run`: **safe minimal sanity** defaults (1 category, 1 model, 3 SKUs, 5 clusters)
- `--controlled-batch`: bounded run defaults (1 category, 1–2 models, 10 SKUs, 15 clusters)
- `--full-eval`: **explicit opt-in** and requires explicit budgets

If no mode flag is provided, runner defaults to **dry-run**.

### B2. Hard guards (hard stop)

Implemented guard knobs (hard stop on violations):

- `--max-categories`
- `--max-models`
- `--max-skus-per-category`
- `--max-clusters-per-category`
- `--max-requests-total` (preflight checks use worst-case “with repair”)
- `--max-input-chars` (per request)
- `--max-runtime-minutes`
- `--max-cost-usd` (enforced via OpenRouter pricing + response token usage)
- `--stop-on-budget-exceeded` (currently always-on safe behavior)

### B3. Dedup + caching discipline

Cache is file-based under `outputs_root/cache/`:

- Category cached by: `(category_id, model, prompt_version, input_hash)`
- SKU cached per item by: `(task=sku_item, category_id, nm_id, model, prompt_version, input_hash)`
- Query cached per item by: `(task=query_item, category_id, cluster_key, model, prompt_version, input_hash)`

Runner logs `cache_hits` and **does not re-call LLM** when cache hit exists.

### B4. Prompt size control

Added explicit prompt limits + truncation knobs (see `--category-*`, `--sku-*`, `--query-*` CLI flags) and enforced `--max-input-chars`.

### B5. Pre-run visibility

Before any non-dry run, runner:

1. computes the run plan (selected categories/models/items, planned calls)
2. writes it to `run_plan.json`
3. prints a short JSON summary to stdout

Run plan path (inside container by default):

- `/data/internal_data/expressive_llm_eval/run_plan.json`

## C) Dry-run results

### Command (exact)

```
docker compose -f infra\docker\docker-compose.yml exec -T api python scripts/expressive_llm_eval.py run --dry-run --dataset docs/seo-module/datasets/wb_project_1_expressive_eval_v1.json --models openai/gpt-5.4,openai/gpt-4.1-mini,openai/gpt-4o-mini --sku-chunk-size 8 --query-chunk-size 10 --max-input-chars 20000
```

### Output (summary)

- Selected categories: `812`, `745`, `821`
- Selected models: `openai/gpt-5.4`, `openai/gpt-4.1-mini`, `openai/gpt-4o-mini`
- Planned calls (base): `81`
  - by task: `category=9`, `sku=36`, `query=36`
- Planned calls (worst with repair): `162`
- Run plan saved to: `/data/internal_data/expressive_llm_eval/run_plan.json`

## D) Micro-run results

Micro-run is the minimal sanity path. It is allowed to make a few LLM calls, but is protected by budgets and hard limits.

### Command (exact)

```
docker compose -f infra\docker\docker-compose.yml exec -T api python scripts/expressive_llm_eval.py run --micro-run --dataset docs/seo-module/datasets/wb_project_1_expressive_eval_v1.json --timeout-seconds 60 --temperature 0 --sku-chunk-size 8 --query-chunk-size 10 --max-input-chars 20000
```

### Output (summary)

- Selected category: `812`
- Selected model: `openai/gpt-4o-mini`
- Planned calls (base): `3` (category=1, sku=1, query=1)
- Planned calls (worst with repair): `6`

Actual execution summary (from runner stdout):

- `requests_made`: `2`
- `cache_hits`: `1` (category call hit cache on rerun)
- `elapsed_min`: `0.21`
- `cost_usd`: `0.00075`

Notes:

- The first micro-run attempt initially failed because pricing fetch used **POST** to `/models` (404). Fixed by using **GET**.
- Micro-run is intentionally small and does not attempt any “full report”.

### Outputs generated (inside container volume)

- `/data/internal_data/expressive_llm_eval/run_plan.json`
- `/data/internal_data/expressive_llm_eval/812/openai__gpt-4o-mini/category.json`
- `/data/internal_data/expressive_llm_eval/812/openai__gpt-4o-mini/category.raw.json`
- `/data/internal_data/expressive_llm_eval/812/openai__gpt-4o-mini/sku.json`
- `/data/internal_data/expressive_llm_eval/812/openai__gpt-4o-mini/sku.raw.json`
- `/data/internal_data/expressive_llm_eval/812/openai__gpt-4o-mini/query.json`
- `/data/internal_data/expressive_llm_eval/812/openai__gpt-4o-mini/query.raw.json`
- `/data/internal_data/expressive_llm_eval/cache/...` (category/sku_item/query_item caches)

### Copy outputs to host repo (exact)

Because `api` container does not bind-mount the repo by default, results are written into the Docker volume.
To make deliverables available in the repo, copy them out:

```
docker cp ecomcore-api-1:/data/internal_data/expressive_llm_eval outputs\expressive_llm_eval
```

After this copy, the required file exists on host:

- `outputs/expressive_llm_eval/run_plan.json`

## E) Recommendation (next safe step)

It is now reasonable to run `--controlled-batch`, but only with:

- 1 category at a time
- max 1–2 models
- explicit `--max-requests-total`, `--max-runtime-minutes`, `--max-cost-usd`
- `--max-input-chars` kept strict

Not recommended:

- any `--full-eval` run without explicit budgets
- running `gpt-5.4` across multiple categories/models without a prior controlled-batch and verified prompt sizes

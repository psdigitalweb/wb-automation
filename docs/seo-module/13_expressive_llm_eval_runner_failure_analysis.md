# Expressive LLM Eval Runner — Failure / Cost Blow-up Analysis

Date: 2026-04-20

Scope: analysis only (no new LLM calls).

## 0) Context / Symptoms

Observed symptoms during the last attempt:

- Eval run duration: **> 60 minutes**
- Spend: **~$2.5** via OpenRouter
- Low visibility: it was **unclear how many calls were planned**, what stage is running, and when it will finish

This document explains why the current orchestration can be unsafe and what must be corrected.

## 1) Runner under analysis

Code:

- `scripts/expressive_llm_eval.py`

Dataset manifest:

- `docs/seo-module/datasets/wb_project_1_expressive_eval_v1.json`

Models (as used in spike plan):

- `openai/gpt-5.4` (strong/expensive)
- `openai/gpt-4.1-mini` (mid)
- `openai/gpt-4o-mini` (cheap)

Tasks per category:

1. category expressive extraction
2. SKU expressive extraction (batched)
3. query cluster expressive extraction (batched)

## 2) Potential call matrix (how many LLM requests it can do)

### 2.1 Base formula (without parse repair)

Let:

- `C` = number of categories
- `M` = number of models
- `S` = SKUs per category
- `Q` = clusters per category
- `sku_chunk` = SKU batch size
- `query_chunk` = query batch size

Then base LLM calls:

- Category calls per `(category, model)` = `1`
- SKU calls per `(category, model)` = `ceil(S / sku_chunk)`
- Query calls per `(category, model)` = `ceil(Q / query_chunk)`

Total base calls:

`calls_base = C * M * (1 + ceil(S/sku_chunk) + ceil(Q/query_chunk))`

### 2.2 Parse repair overhead

Current runner uses JSON parsing + a “repair model” fallback if parsing fails.

Worst-case overhead:

- Each failed call can trigger **one extra** LLM call to repair JSON.

So worst-case:

`calls_total_worst = calls_base + calls_base = 2 * calls_base`

(This is a worst-case upper bound; real overhead depends on parse failure rate.)

### 2.3 Concrete numbers for current dataset

From `wb_project_1_expressive_eval_v1.json`:

- `C = 3` categories: `812`, `745`, `821`
- `S = 25` SKUs per category
- `Q = 40` clusters per category

From runner defaults used in earlier runs:

- `sku_chunk = 8` → `ceil(25/8) = 4` SKU calls per `(category, model)`
- `query_chunk = 10` → `ceil(40/10) = 4` query calls per `(category, model)`

Per `(category, model)`:

- `1 (category) + 4 (sku) + 4 (query) = 9 calls`

Per all categories + all 3 models:

- `calls_base = 3 * 3 * 9 = 81 calls`
- `calls_total_worst ≈ 162 calls` (if every call needs a repair pass)

### 2.4 Why “> 1 hour” is plausible

Even if each call takes ~20–40 seconds end-to-end (routing + model latency + JSON parsing/repair):

- `81 calls * 30s ≈ 40.5 minutes` (base)
- plus repair calls / slow model (`gpt-5.4`) / network jitter → easily **> 60 minutes**

## 3) Which calls are the most expensive (cost drivers)

Primary cost drivers are the tasks with:

- high call multiplicity (many requests)
- large input prompts
- high `max_tokens` (large completions)
- expensive model usage

### 3.1 Category calls

- Calls: `C * M` (small)
- Completion cap previously used: `max_tokens_category ~ 500`
- Typically not the largest part of total cost.

### 3.2 SKU batch calls (most dangerous)

- Calls: `C * M * ceil(S/sku_chunk)` (large)
- Each request includes up to `sku_chunk` items, each with:
  - `title` (<= 220 chars)
  - `description` (<= 600 chars)
  - `attributes_text` (<= 600 chars)
- Completion cap previously used: `max_tokens_sku ~ 1000`

This is the biggest hotspot because it combines:

- many calls
- large prompts
- large completion caps
- repeated across models

### 3.3 Query batch calls (also expensive)

- Calls: `C * M * ceil(Q/query_chunk)` (large)
- Each request includes up to `query_chunk` clusters, each with:
  - label
  - up to 8 member queries
- Completion cap previously used: `max_tokens_query ~ 1000`

Typically cheaper than SKU batches if SKU descriptions are long, but still a significant cost driver.

## 4) Duplication check (category-level extraction)

Within a single `run` execution:

- Category-level extraction is called **once per `(category_id, model)`**.
- It is **not** repeated per SKU or per query chunk.

So the “duplication” is not intra-run category repetition.

However, there is **inter-run duplication**:

- outputs were written to container filesystem (`/app/outputs/...`) which is **not persistent** in the current `api` compose service (no repo bind mount)
- rebuilding/recreating the container wipes outputs
- re-running re-spends budget even if “same dataset, same prompts”

## 5) Missing guards / unsafe defaults (why it burned money)

Current runner (pre-fix) lacks the following hard limits and safety staging:

- No `--dry-run` (plan-only) mode
- No `--micro-run` sanity mode
- No `--controlled-batch` mode
- No explicit `--full-eval` opt-in
- No `--max-requests-total`
- No `--max-runtime-minutes`
- No `--max-cost-usd`
- No enforcement of `--max-categories` / `--max-models` / `--max-skus-per-category` / `--max-clusters-per-category`
- No global `--max-input-chars` enforcement or structured prompt size reporting
- No required “pre-run plan” persisted to disk
- No explicit caching keyed by `(task, category_id, item_id, model, prompt_version, input_hash)`
- Very limited progress output (essentially “silent” while running)

Net result: the script can start a **full** call matrix by default and keep going until completion, regardless of runtime/cost.

## 6) Input size risks (prompt bloat)

Even with truncation on individual SKU fields, SKU batch prompts can be large because:

- up to `sku_chunk` items per request
- each item can contain ~1.4k chars of evidence text + overhead
- JSON schema instructions are repeated in each request

Query batch prompts can also grow due to:

- `query_chunk` clusters per request
- multiple member queries per cluster

The runner currently does not:

- cap total prompt chars per request
- cap sample counts at the dataset level per staged mode
- log prompt size per request (to make hotspots obvious)

## 7) Root-cause hypotheses (most likely)

H1. **Implicit full-eval behavior**
- `run` + dataset defaults effectively trigger the full matrix (81+ calls) without an explicit “full-eval” acknowledgement.

H2. **High completion caps (max_tokens) on the high-multiplicity tasks**
- `max_tokens_sku/query ~ 1000` combined with multiple models → rapid cost growth.

H3. **No cost/runtime/request hard stops**
- even a slow model or increased repair rate cannot stop the run.

H4. **Non-persistent outputs/caching**
- container recreation wipes outputs → reruns re-spend budget.

H5. **Low observability**
- without a printed run plan and progress counters, the run appears “stuck/unknown” even if it is doing expected work.

## 8) Corrective actions (what to implement next)

CA1. **Staged safe execution**

- `dry-run`: dataset + planned calls + prompt size estimates, **no LLM**
- `micro-run`: 1 category, 1 model, 3 SKUs, 5 clusters, strict budgets
- `controlled-batch`: bounded run with strict guards
- `full-eval`: only with explicit `--full-eval`

CA2. **Hard guards (hard stop, not warning)**

- `--max-categories`
- `--max-models`
- `--max-skus-per-category`
- `--max-clusters-per-category`
- `--max-requests-total`
- `--max-input-chars`
- `--max-runtime-minutes`
- `--max-cost-usd`

CA3. **Dedup + cache discipline**

- Category cached by `(category_id, model, prompt_version, input_hash)`
- SKU/query cached by `(task, category_id, item_id, model, prompt_version, input_hash)`
- Cache hit reporting

CA4. **Prompt size control**

- explicit limits (samples, member queries, per-field chars, total prompt chars)
- prompt size logging

CA5. **Pre-run visibility**

- always generate and persist `outputs/expressive_llm_eval/run_plan.json` before any non-dry run
- include planned calls by task type + active guards + budgets

CA6. **Persistent outputs root**

- default outputs should go to a mounted persistent dir inside container (e.g. under `INTERNAL_DATA_DIR`)
  - otherwise every container recreate wipes cache and results


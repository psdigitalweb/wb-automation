# Expressive Meaning — LLM Eval Dataset (WB SEO Module)

Этот документ фиксирует **конкретный воспроизводимый dataset** (категории + SKU nm_id + query cluster_key + seed) для expressive LLM evaluation spike.

## 1) Source of truth (dataset manifest)
- `docs/seo-module/datasets/wb_project_1_expressive_eval_v1.json`

В manifest фиксированы:
- `seed`
- `project_id`
- для каждой категории: `category_id`, `subject_name`, `sku_nm_ids`, `cluster_keys`

## 2) Selected categories
- `812` — Кружки
- `745` — Тетради
- `821` — Тарелки

Причина выбора:
- expressive слой потенциально важен (подарок/принт/эстетика/стилистика)
- в текущей БД есть достаточный объём SKU и query clusters для оценки

## 3) Dataset size (fixed)
Per category:
- `25` SKU (`nm_id`)
- `40` query clusters (`cluster_key`)

## 4) How selection is done (deterministic, seed-based)
Selection rule (фиксируется в runner, чтобы можно было перегенерировать dataset при необходимости):

### SKU selection
1) Берём latest-snapshot строку `products` на каждый `nm_id` в категории.
2) Отмечаем “expressive-leaning” по simple regex в `title + description` (подарок/надпись/принт/мем/прикол/aesthetic/эстет/аниме/минимал и т.п.).
3) Выбираем примерно половину из expressive-hit, остальное добираем random из остальных (seed фиксированный).

### Query cluster selection
1) Берём top-15 кластеров по `query_count` (head-biased).
2) Добираем из top-1000 кластеров те, где `cluster_label_candidate` матчится по expressive regex.
3) Остальное добираем random (seed фиксированный).

## 5) What is sent into LLM (minimal real data)
Данные, которые будут подаваться в модель (минимально необходимые):

### Category task input
- `subject_name`
- 10–15 SKU title examples (по выбранным SKU)
- 10–15 query cluster label examples + 5–8 representative queries для части кластеров

### SKU task input (per SKU)
- `title`
- `description` (truncated)
- flattened text из `characteristics/sizes/colors/dimensions` (truncated)

### Query task input (per cluster)
- `cluster_label_candidate`
- 5–10 member queries (display_query если доступен; иначе normalized)

Не отправляем:
- `brand`, `vendor_code`
- цены/маржинальность
- любые скрытые/внутренние поля, не нужные для expressive extraction


# Category 812 (Кружки) — LLM expressive prompt v1 vs v2 (openai/gpt-4.1-mini)

Цель: обновить только prompt + `prompt_version`, чтобы модель могла возвращать **до 8 vibes** (минимум 3), и сделать **ровно один** прогон на категории `812` (без retries), не затрагивая runtime-интеграцию (CategoryMeaning читает из cache как раньше).

## 1) Exact command (v2 run)

Команда, которой был выполнен **ровно один** LLM-вызов для `prompt_version=v2`:

```bash
docker compose -f infra\docker\docker-compose.yml exec -T api python /app/scripts/run_category_expressive_single_category.py --project-id 1 --category-id 812 --model openai/gpt-4.1-mini --prompt-version v2 --min-rating 4 --max-reviews 100 --include-titles --temperature 0 --top-p 1 --max-tokens 900 --timeout-seconds 60
```

## 2) Cache paths

- v1 cache dir:
  - `D:\Work\EcomCore\outputs\seo_expressive_cache\cat_expr\p1\c812\m_openai__gpt-4.1-mini\pv_v1\h_419343aa7636a1489354a1766726a85c7009b40ad0b87be73a258592d9dc0645\`
- v2 cache dir:
  - `D:\Work\EcomCore\outputs\seo_expressive_cache\cat_expr\p1\c812\m_openai__gpt-4.1-mini\pv_v2\h_419343aa7636a1489354a1766726a85c7009b40ad0b87be73a258592d9dc0645\`

## 3) Prompt changes (v2)

В `prompt_version=v2` зафиксировано:
- max vibes = 8
- min vibes = 3 (инструкция, не hard-guard)
- для каждого vibe: 2–3 evidence_spans (≤80 chars)
- запрет generic labels: `"positive"`, `"good"`, `"quality"`
- запрет объединять разные стили в один vibe
- если сигналов недостаточно: вернуть меньше vibes, не выдумывать

## 4) Results — v1 vibes

Источник: `parsed.json` (v1).

- Милота и уют
- Подарочная привлекательность
- Радость и удовлетворение от покупки
- Красота и эстетика
- Удобство и комфорт использования

## 5) Results — v2 vibes

Источник: `parsed.json` (v2).

- Милая и уютная
- Подарочная
- Большая и удобная
- Красивый дизайн
- Веселая и забавная

Наблюдение: модель **не воспользовалась лимитом до 8 vibes** (вернула 5).

## 6) Diff (v1 -> v2)

Новые/изменённые оси:
- Появилась ось: `Веселая и забавная` (в v1 было ближе к “радости от покупки”, но не про юмор/принты).
- Появилась ось: `Большая и удобная` (частично “size/comfort”, но близко к функциональному сигналу).

Потери/упрощения:
- `Радость и удовлетворение от покупки` (v1) исчезла.
- `Подарочная привлекательность` (v1) → `Подарочная` (v2) (менее выразительно).
- `Красота и эстетика` (v1) → `Красивый дизайн` (v2) (по смыслу близко).
- `Милота и уют` (v1) → `Милая и уютная` (v2) (по смыслу близко).

Мусор/риск:
- В v2 **3 из 5** vibes помечены как hallucinated (есть missing evidence span). См. `validation.json` (v2).

## 7) Validation (evidence match)

Источник: `validation.json`.

### v1
- evidence_found / evidence_total: `13 / 15`
- evidence_quality: `0.8666666666666667`
- hallucinated vibes (missing evidence span):
  - `Милота и уют`
  - `Удобство и комфорт использования`

### v2
- evidence_found / evidence_total: `12 / 15`
- evidence_quality: `0.8`
- hallucinated vibes (missing evidence span):
  - `Милая и уютная`
  - `Большая и удобная`
  - `Веселая и забавная`

## 8) Verdict (quality check)

- Осмысленных осей **не стало больше** (v2 всё ещё вернул 5 vibes).
- Появилась 1 потенциально полезная новая ось (`Веселая и забавная`), но она сейчас **частично не подтверждена evidence**.
- Evidence дисциплина **слегка ухудшилась**: `0.8667` → `0.8`.


# Expressive Meaning — LLM Eval Prompts v1

Правило для всех задач:
- Вернуть **только JSON** (без Markdown).
- Каждый vibe должен содержать `evidence_spans[]` — **точные подстроки** из соответствующего input.
- Если evidence не найден в input → это считается hallucination (валидируется runner’ом).

## Shared schema (v1)
Category/SKU/Query outputs используют единый vibe schema:

```json
{
  "label": "giftable|cute|aesthetic|minimalist|meme|romantic|teen|cozy|premium|retro|anime|eco|handmade|dark|pastel|bright|professional|other",
  "label_raw": "string",
  "confidence": 0.0,
  "evidence_spans": ["string"],
  "notes": "string"
}
```

Runner принимает только:
- `confidence` в диапазоне `[0..1]`
- `evidence_spans` как список строк (0–5)

## 1) Category expressive extraction

### Prompt
System:
```
Ты извлекаешь expressive meaning (вайбы/эстетика/эмоциональное позиционирование) из предоставленного текста.
Правила:
- Не выдумывай. Если сигналов нет — верни пустой список vibes.
- Каждый vibe обязан иметь evidence_spans (точные подстроки из input).
- Верни только JSON, без Markdown.
```

User (template):
```
TASK=category_expressive
Return JSON:
{
  "version": "v1",
  "task": "category",
  "vibes": [<vibe objects>],
  "summary": "1-2 sentences",
  "warnings": ["..."]
}

INPUT:
<subject_name + sku title examples + query examples>
```

## 2) SKU expressive extraction (batch)

### Prompt
System:
```
Ты извлекаешь expressive meaning для SKU.
Правила:
- Не выдумывай.
- Evidence spans должны быть подстроками из полей конкретного SKU (title/description/attributes_text).
- Верни только JSON.
```

User (template):
```
TASK=sku_expressive_batch
Return JSON:
{
  "version": "v1",
  "task": "sku_batch",
  "items": [
    {
      "nm_id": 0,
      "vibes": [<vibe objects>],
      "summary": "short",
      "warnings": ["..."]
    }
  ]
}

INPUT ITEMS:
- nm_id=...
  title=...
  description=...
  attributes_text=...
```

## 3) Query expressive extraction (batch)

### Prompt
System:
```
Ты определяешь expressive intent в запросах.
Правила:
- Разделяй functional vs expressive.
- Evidence spans должны быть подстроками из label/queries конкретного кластера.
- Верни только JSON.
```

User (template):
```
TASK=query_expressive_batch
Return JSON:
{
  "version": "v1",
  "task": "query_batch",
  "items": [
    {
      "cluster_key": "...",
      "expressive_intent": true,
      "vibes": [<vibe objects>],
      "summary": "short",
      "warnings": ["..."]
    }
  ]
}

INPUT CLUSTERS:
- cluster_key=...
  label=...
  queries=[...]
```


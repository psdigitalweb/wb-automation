# Category 812 (Кружки) — LLM Expressive Category Run (Iteration 19)

Дата прогона: 2026-04-21

Ограничения:
- 1 категория (`category_id=812`)
- 1 модель (`openai/gpt-4.1-mini`)
- offline execution path iteration 19
- без retries / repair
- без matcher/scoring/query pipeline/UI

---

## 0. Cache pre-check

Перед запуском был сделан cache-check (без LLM вызова) для ключа `(project_id=1, category_id=812, model=openai/gpt-4.1-mini, prompt_version=v1, input_hash=419343aa...)`.

Результат: `cache_hit=false`, запуск пошёл как fresh run.

Если бы был `cache_hit=true`, то принудительный fresh run можно сделать так:
- изменить `--prompt-version` (например `v1_fresh_20260421`)
- или изменить параметры input (например `--max-reviews`)

---

## 1. Exact command

```bash
docker compose -f infra\docker\docker-compose.yml exec -T api python /app/scripts/run_category_expressive_single_category.py --project-id 1 --category-id 812 --model openai/gpt-4.1-mini --prompt-version v1 --min-rating 4 --max-reviews 100 --include-titles --temperature 0 --top-p 1 --max-tokens 900 --timeout-seconds 60
```

---

## 2. Input summary

- `project_id`: 1
- `category_id`: 812
- `category_name`: Кружки
- `reviews_count selected`: 100 (rating>=4)
- `titles_count selected`: 53 (secondary support, dedup + truncate)
- estimated prompt chars: 11304
- estimated prompt tokens: 2826

Полный payload:
- `D:\Work\EcomCore\outputs\seo_expressive_cache\cat_expr\p1\c812\m_openai__gpt-4.1-mini\pv_v1\h_419343aa7636a1489354a1766726a85c7009b40ad0b87be73a258592d9dc0645\input_payload.json`

---

## 3. Input preview

### 3.1 Sample reviews (10)

1) Очень красивая и хорошая кружка , есть конечно некоторые потёртости рисунка но не заметны  
2) Потрясающая чашка. Пришла целая в коробке и пупырке.\nЦенас качество.  
3) Уже подобного плана кружку заказывали,  решили еще одной обзавестись)  печать хорошая,  все целое.\nХорошо упаковонное,  все целое!  
4) Супер! Покупала в подарок подруге.  
5) Заказываю третью кружку у вас, все приходит в целости и сохранности, спасибо!!!!!!!!  
6) Спасибо получила, купила на подарок очень понравилась кружка.  
7) Хороший, качественный принт. Для подарка - супер.\nПришло со сколом, продавец на следующий день одобрил возврат.  
8) Качество\nНет  
9) прекрасная кружка 🤍  
10) подарок понравился 🤍  

### 3.2 Sample titles (5)

1) Кружка керамическая 370 мл  
2) Кружка керамическая милая с принтом капибара "Воркинг"  
3) Кружка керамическая "Делу время" объём 340 мл.  
4) Кружка для чая керамическая большая "Я котик" 450 мл.  
5) Кружка для чая керамическая большая "Мечты сбудутся" 450 мл.  

---

## 4. LLM result (artifacts)

Артефакты (host copy):
- raw response: `D:\Work\EcomCore\outputs\seo_expressive_cache\cat_expr\p1\c812\m_openai__gpt-4.1-mini\pv_v1\h_419343aa7636a1489354a1766726a85c7009b40ad0b87be73a258592d9dc0645\raw_response.json`
- parsed: `D:\Work\EcomCore\outputs\seo_expressive_cache\cat_expr\p1\c812\m_openai__gpt-4.1-mini\pv_v1\h_419343aa7636a1489354a1766726a85c7009b40ad0b87be73a258592d9dc0645\parsed.json`
- validation: `D:\Work\EcomCore\outputs\seo_expressive_cache\cat_expr\p1\c812\m_openai__gpt-4.1-mini\pv_v1\h_419343aa7636a1489354a1766726a85c7009b40ad0b87be73a258592d9dc0645\validation.json`
- meta: `D:\Work\EcomCore\outputs\seo_expressive_cache\cat_expr\p1\c812\m_openai__gpt-4.1-mini\pv_v1\h_419343aa7636a1489354a1766726a85c7009b40ad0b87be73a258592d9dc0645\meta.json`
- LLM messages (system+user): `D:\Work\EcomCore\outputs\seo_expressive_cache\cat_expr\p1\c812\m_openai__gpt-4.1-mini\pv_v1\h_419343aa7636a1489354a1766726a85c7009b40ad0b87be73a258592d9dc0645\llm_messages.json`

---

## 5. Parsed expressive result

Источник: `parsed.json`

### 5.1 Vibes

1) Милота и уют — `confidence=0.95`
   - "Очень милая кружечка"
   - "Милейшая кружка😍 Объем большой, то что я и хотела!"
   - "Очень милая и эстетичная кружка, в подарок самое то"

2) Подарочная привлекательность — `confidence=0.9`
   - "Покупала в подарок подруге"
   - "Для подарка - супер"
   - "Упакована хорошо не стыдно будет подарить"

3) Радость и удовлетворение от покупки — `confidence=0.9`
   - "Я влюбилась в эти кружки!"
   - "Обожаю этот бред кружек, заказываю 3 раз всем родственникам нравятся"
   - "Очень понравилась, поэтому не стала обращаться внимания на мелкие недочёты"

4) Красота и эстетика — `confidence=0.85`
   - "Очень красивая и хорошая кружка"
   - "Безумно красивая кружка"
   - "Красивая и без браков"

5) Удобство и комфорт использования — `confidence=0.8`
   - "Кружка идеальна. Она удобная по форме"
   - "Удобная, пришла целая не покарябанная"
   - "Отличная , удобная , пользуюсь в машине"

### 5.2 Summary

Отзывы покупателей подчеркивают милоту и уют кружек, их привлекательность как подарков, радость от покупки, красоту дизайна и удобство использования.

---

## 6. Validation summary

Источник: `validation.json`

- JSON валиден: да (response finish_reason = stop)
- evidence exact-match:
  - found: 13
  - total: 15
  - rate: 0.8667
- hallucinations:
  - vibe "Милота и уют": 1 span missing (exact-substring не найден)
  - vibe "Удобство и комфорт использования": 1 span missing (exact-substring не найден)

---

## 7. Cache / storage

### 7.1 Cache key components

- `project_id`: 1
- `category_id`: 812
- `model`: openai/gpt-4.1-mini
- `prompt_version`: v1
- `input_hash`: 419343aa7636a1489354a1766726a85c7009b40ad0b87be73a258592d9dc0645

### 7.2 Output directory

- container store dir:
  - `/data/internal_data/seo_expressive_cache/cat_expr/p1/c812/m_openai__gpt-4.1-mini/pv_v1/h_419343aa7636a1489354a1766726a85c7009b40ad0b87be73a258592d9dc0645`
- host copy dir:
  - `D:\Work\EcomCore\outputs\seo_expressive_cache\cat_expr\p1\c812\m_openai__gpt-4.1-mini\pv_v1\h_419343aa7636a1489354a1766726a85c7009b40ad0b87be73a258592d9dc0645`

### 7.3 Files created

- `meta.json`
- `input_payload.json`
- `llm_messages.json`
- `raw_response.json`
- `parsed.json`
- `validation.json`

---

## 8. Short verdict

Результат выглядит осмысленным для категории “Кружки” (gift / эстетика / милота / эмоции / удобство).

Да, это можно использовать как category expressive prior, но evidence-дисциплину (exact-span) стоит дополнительно усилить/наблюдать: 2 из 15 spans не прошли exact-match (validator их пометил).


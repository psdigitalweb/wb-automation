SEO Module — Product Projection Spec
0. Purpose

Product Projection — это представление конкретного SKU в пространстве Category Meaning.

Задачи:

привести SKU к нормализованной форме
обеспечить сопоставимость с Query Meaning
обеспечить cold-start
отделить raw данные от смысловой репрезентации

Product Projection:

не извлекает смысл категории
не зависит от query side
не содержит scoring логики
1. Scope

Строится:

per project × per SKU

Входные данные:

данные SKU (title, attributes, description)
Category Meaning

Система должна работать:

для новых SKU
без отзывов
без поведенки
2. Role in Architecture

Category Meaning
↓
Product Projection
↓
Matcher

3. Inputs
SKU Data
title
attributes / characteristics
sizes / colors / dimensions
description (weak signal)
reviews (optional)
Category Meaning

Используется как:

структура осей
допустимые значения
expressive baseline
4. Projection Structure

Product Projection состоит из двух частей:

Functional Profile
Expressive Profile
Functional Profile

Отвечает на вопрос:

что это за товар

Содержит:

product_type
use_cases
attributes

Источники (приоритет):

attributes
category constraints
title
description

Свойства:

детерминирован
работает без дополнительных сигналов
не зависит от expressive слоя
Expressive Profile (CRITICAL)

Отвечает на вопрос:

как воспринимается товар

Источники:

category expressive prior (baseline)
SKU signals:
title
reviews
description
Cold Start Logic

если у SKU нет expressive сигналов:
→ используется category prior

если сигналы есть:
→ происходит уточнение или override

Свойства expressive слоя
может быть неполным
может быть слабым
не обязателен для каждого SKU
обязателен как слой системы
5. Projection Logic
Functional Extraction
извлечение product_type из attributes
извлечение use_case из title/attributes
нормализация attributes
Expressive Extraction
извлечение vibe из title
усиление через reviews (если есть)
fallback к category prior
Merge Strategy

финальный expressive профиль:

category prior

SKU signals
6. Canonical Shape

{
"sku_id": "...",
"functional": {
"product_type": "...",
"use_cases": [],
"attributes": []
},
"expressive": {
"vibes": []
}
}

7. Usage in Matcher

Product Projection используется для:

functional matching
expressive matching

Matcher сравнивает:

functional ↔ functional
expressive ↔ expressive
8. Constraints

Product Projection НЕ должен:

зависеть от query side
использовать scoring
использовать LLM
использовать embeddings
9. External Overrides (Optional)

Manual Context

Назначение:

уточнение use-case
уточнение vibe
управление cold-start

Ограничения:

не является частью core projection
не изменяет Category Meaning
применяется как override
10. Minimal Validity Criteria

Product Projection валиден, если:

содержит functional профиль
содержит expressive профиль
работает без reviews
использует category prior
пригоден для matcher
11. Final Invariant

Product Projection — это:

нормализованное представление SKU,
построенное на основе Category Meaning,
содержащее functional и expressive компоненты,
и используемое для сопоставления с query meaning
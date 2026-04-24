0. Purpose

Category Meaning — это product-side semantic layer, построенный из товаров категории.

Задачи:

зафиксировать смысловое пространство категории
дать основу для SKU clustering
дать основу для Product Projection
обеспечить cold-start для новых SKU

Category Meaning:

не зависит от query side
не участвует в scoring напрямую
не содержит логики matching
1. Scope

Строится:

per project × per category

Входные данные:

товары категории
отзывы (опционально)

Система должна работать:

с отзывами
без отзывов
2. Role in Architecture

Category Signals
↓
Category Meaning
↓
SKU Clustering
↓
Product Projection

3. Inputs
Required
title
attributes / characteristics
sizes / colors / dimensions
description (weak signal)
Optional
reviews

Используются для:

усиления сигналов
expressive уточнения
4. Meaning Structure

Category Meaning состоит из двух независимых частей:

Functional Meaning

Отвечает на вопрос:

что это за товар и как он используется

Product-Type
тип товара внутри категории
Use-Case
сценарий использования
Attributes
свойства товара

Источники (приоритет):

attributes
title
description
reviews
Expressive Meaning (CRITICAL)

Отвечает на вопрос:

почему пользователь выбирает товар

Vibe

Содержит:

стиль
эстетика
эмоциональный контекст

Примеры:

minimal
aesthetic
cute
meme
premium
giftable

Источники:

title
reviews
description
5. Build Rules
Aggregation
строится из всех товаров категории
единичные выбросы игнорируются
Reviews
усиливают, но не создают product-type
Degradation

без reviews система остаётся валидной

6. Canonical Shape

{
"category_id": "...",
"version": "...",
"functional": {
"product_types": [],
"use_cases": [],
"attributes": []
},
"expressive": {
"vibes": []
}
}

7. Usage in Clustering

Используется для:

segmentation
clustering features

Не используется:

raw description напрямую
query данные
8. Usage in Product Projection

Каждый SKU получает:

category expressive meaning как baseline

Поведение:

нет сигналов → baseline
есть → override
9. Constraints

НЕ должен:

зависеть от query
использовать matcher
использовать scoring
требовать LLM
10. Final Invariant

Category Meaning — это:

стабильное описание смыслового пространства категории,
построенное из товаров,
содержащее functional и expressive компоненты,
и используемое как база для clustering и product projection
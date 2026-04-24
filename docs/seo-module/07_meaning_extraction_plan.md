SEO Module — Meaning Extraction Plan
0. Goal

Построить рабочий слой извлечения смыслов для:

Category Meaning
Product Projection
Query Meaning

Без:

LLM
embeddings
зависимости от reviews
1. Общий принцип

Extraction идёт в порядке:

Category Meaning
Product Projection
Query Meaning

Не наоборот.

2. Category Meaning Extraction
2.1 Functional Extraction
Step 1 — собрать признаки из всех SKU

Извлекаем:

attributes (primary)
title tokens
description tokens (weak)
Step 2 — выделить Product-Type

Правило:

если есть явный атрибут → берём его
иначе → берём устойчивый паттерн из title
иначе → fallback к category
Step 3 — выделить Use-Case

Источники:

title
attributes

Правило:

use-case должен повторяться у множества SKU
одиночные случаи игнорируем
Step 4 — выделить Attributes
нормализуем значения
группируем по типам (размер, материал и т.д.)
2.2 Expressive Extraction
Step 1 — собрать expressive сигналы

Источники:

title
description (weak)
Step 2 — выделить Vibe

Правило:

фиксируем только повторяющиеся паттерны
одиночные слова не считаем категорией
Step 3 — фильтрация
убираем шум
убираем нерелевантные слова
Step 4 — финальный Category Meaning

Результат:

functional axes
expressive axes
3. Product Projection Extraction
3.1 Functional
Step 1 — извлечение из SKU
product_type ← attributes
use_case ← title/attributes
attributes ← raw
Step 2 — нормализация
привести к значениям из Category Meaning
3.2 Expressive
Step 1 — взять category prior
базовый expressive профиль
Step 2 — извлечь SKU сигналы
title
description
Step 3 — merge
если сигнал слабый → оставить prior
если сильный → override
4. Query Meaning Extraction
4.1 Functional Intent
Step 1 — normalize query
Step 2 — определить product-type
из текста
из cluster
Step 3 — определить use-case
из текста
из cluster
Step 4 — определить attributes
из текста
4.2 Expressive Intent
Step 1 — извлечь vibe
из текста запроса
из cluster
Step 2 — fallback
если нет → пусто
5. Degradation Rules
Без reviews
ничего не ломается
expressive слабее
functional остаётся
Слабый title
reliance на attributes
expressive может отсутствовать
Бедные attributes
reliance на title
use-case может быть слабым
6. MVP Boundaries

Входит:

deterministic extraction
category aggregation
expressive baseline
cold-start logic

Не входит:

embeddings
LLM
semantic search
manual overrides
advanced clustering
7. Deliverables

После реализации должны появиться:

Category Meaning objects
Product Projection objects
Query Meaning objects

Пригодные для matcher.

8. Final Invariant

Meaning extraction — это:

детерминированный процесс,
который превращает raw данные (products и queries)
в структурированные semantic представления,
используемые для сопоставления в системе
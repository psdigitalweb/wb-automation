SEO Module — LLM Expressive Implementation Plan
0. Purpose

Этот документ описывает реализацию LLM expressive слоя в product-side.

Цель:

внедрить LLM как источник expressive meaning
не ломать текущую архитектуру
контролировать стоимость и воспроизводимость
1. Scope

Входит:

Category expressive extraction (LLM)
SKU expressive extraction (LLM)
reviews-based input
caching и batch execution

Не входит:

matcher
scoring
query meaning
UI
2. Общая схема

Category:
reviews → LLM → category expressive → cache

SKU:
reviews + title → LLM → SKU expressive
fallback → category expressive

3. Phase 1 — Category expressive
3.1 Получение отзывов

Функция:
fetch_category_reviews(project_id, category_id)

Возвращает:

отзывы с rating >= 4
связанные SKU
3.2 Подготовка input

Функция:
build_category_llm_input(category_name, reviews, titles)

Логика:

обрезать отзывы до лимита
убрать дубли
ограничить количество
добавить titles как слабый сигнал
3.3 Вызов LLM

Функция:
extract_category_expressive(input_payload, model)

Параметры:

temperature = 0
max_tokens ограничен
один вызов на категорию
3.4 Парсинг ответа

Функция:
parse_llm_output(raw_response)

Проверки:

JSON валиден
есть vibes
evidence_spans присутствуют во входе
3.5 Кэширование

Храним:

category_id
model
prompt_version
input_hash
expressive_result
3.6 Batch запуск

Скрипт:
scripts/run_category_expressive_batch.py

Делает:

обходит категории
вызывает LLM
сохраняет результаты
логирует cost
4. Phase 2 — SKU expressive
4.1 Input

fetch_sku_reviews(nm_id)

4.2 LLM extraction

extract_sku_expressive(payload)

4.3 Merge

если сигнал есть → использовать SKU expressive
если нет → fallback на category

5. Phase 3 — Интеграция

CategoryMeaning.expressive = LLM output

ProductProjection.expressive:

SKU expressive
или category fallback
6. Execution режимы

Offline:

batch job
по категориям

On-demand:

при обновлении данных
7. Контроль стоимости

Добавить лимиты:

max_reviews_per_category
max_input_chars
max_requests
max_cost

Логировать:

tokens
latency
стоимость
8. Обработка ошибок

Если LLM недоступен:

Category:

использовать кеш
или пустой expressive

SKU:

fallback на category
9. Версионирование

Хранить:

prompt_version
model
10. Тестирование

Unit:

input builder
parser

Integration:

один запуск категории
проверка output
11. Внедрение
сначала category expressive
проверить
добавить SKU expressive
интегрировать в projection
12. Ограничения

LLM слой:

не влияет на query pipeline
не влияет на scoring
не блокирует систему
13. Final Invariant

Expressive слой:

строится из reviews
titles — вторичный сигнал
работает offline
используется как prior
не зависит от query side
SEO Module — Query Meaning Spec
0. Purpose

Query Meaning — это semantic-представление поискового запроса.

Задачи:

нормализовать смысл запроса
сделать его сопоставимым с Product Projection
отделить pipeline-артефакты от смысловой модели
обеспечить стабильный вход для matcher

Query Meaning:

строится только из query-side данных
не зависит от product side
не содержит логики scoring
1. Scope

Строится:

per project × per category × per query

Входные данные:

поисковые запросы
статистика (frequency / orders)
clustering результаты
2. Role in Architecture

Query Signals
↓
Query Meaning
↓
Matcher

3. Inputs
Required
raw query text
normalized query
frequency / demand signals
Derived
cluster membership
hybrid annotation
query markers
4. Meaning Structure

Query Meaning состоит из двух частей:

Functional Intent
Expressive Intent
4.1 Functional Intent

Отвечает на вопрос:

что пользователь ищет

Product-Type Intent

Пример:

кружка
тетрадь
ланчбокс
Use-Case Intent

Пример:

для кофе
для школы
для подарка
Attribute Intent

Пример:

200 мл
керамическая
на кольцах
Источники
текст запроса
cluster
статистика
4.2 Expressive Intent (CRITICAL)

Отвечает на вопрос:

как пользователь воспринимает товар

Vibe Intent

Содержит:

стиль
эстетика
эмоциональный контекст
Примеры
aesthetic
cute
meme
premium
минимализм
подарок
Источники
текст запроса
cluster
language patterns
5. Construction Logic
5.1 Normalization
приведение текста к canonical форме
удаление шума
5.2 Clustering
grouping похожих запросов
формирование cluster-level сигналов
5.3 Hybrid Annotation
head queries → индивидуально
tail queries → через cluster
5.4 Marker Extraction
извлечение functional intent
извлечение expressive intent
6. Canonical Shape

{
"query": "...",

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

Query Meaning используется для:

functional matching
expressive matching

Matcher сравнивает:

functional ↔ functional
expressive ↔ expressive
8. Constraints

Query Meaning НЕ должен:

зависеть от product side
использовать Product Projection
использовать scoring
требовать LLM
требовать embeddings
9. Minimal Validity Criteria

Query Meaning валиден, если:

содержит functional intent
содержит expressive intent
не зависит от product side
пригоден для matcher
10. Final Invariant

Query Meaning — это:

стабильное представление поискового запроса,
содержащее functional и expressive intent,
и используемое для сопоставления с Product Projection
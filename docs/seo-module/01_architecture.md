# SEO Module — Architecture

## 0. Scope

SEO module работает:

> **per project × per category**

Цель:
- сопоставить **поисковый спрос (queries)** и **смысл товаров (products)**
- определить релевантные запросы для SKU
- обеспечить explainable scoring

---

## 1. High-Level Architecture

Система состоит из двух независимых semantic веток и слоя соединения:

PRODUCT SIDE                  QUERY SIDE

Category Signals            Query Signals
        │                        │
        ▼                        ▼
Category Meaning            Query Meaning
        │
        ▼
SKU Clustering
        │
        ▼
Product Projection


Product Projection + Query Meaning
                │
                ▼
              MATCHER
                │
                ▼
              Scoring
---

## 2. Core Principles

### 2.1 Separation of Meaning

- Product meaning строится из товаров  
- Query meaning строится из запросов  
- они не смешиваются  

---

### 2.2 Matcher as Connector

Matcher:
- не извлекает смысл  
- не хранит данные  
- только сравнивает две готовые репрезентации  

---

### 2.3 Category-First Product Modeling

- SKU не является источником истины  
- смысл категории формируется до SKU  
- SKU — это проекция в пространство категории  

---

### 2.4 Cold Start Must Work

Система должна работать:
- без отзывов  
- без поведенки  
- для новых SKU  

---

### 2.5 Explainability First

Любое решение:
- должно быть разложено на компоненты  
- не допускается black-box логика  

---

### 2.6 Expressive Meaning as Value Driver

В насыщенных категориях:

> expressive meaning (vibe, эстетика, эмоциональный контекст)  
> является ключевым источником релевантности и конверсии  

Система обязана:
- извлекать expressive сигналы  
- использовать их наравне с functional  

---

## 3. Product Side

### 3.1 Category Signals

Сырой слой данных:

- title  
- description  
- attributes / characteristics  
- sizes / colors / dimensions  
- reviews (optional)  

⚠️ Это не meaning, а входные данные  

---

### 3.2 Category Meaning (CRITICAL LAYER)

Определяет смысловое пространство категории.

Состоит из двух групп:

#### Functional Meaning
- product-type  
- use-case  
- attributes  

#### Expressive Meaning
- vibe / aesthetic / emotional / positioning signals  

---

#### Key Properties

- строится только из product-side данных  
- reviews — усиливают, но не обязательны  
- не зависит от query side  
- является базой для:
  - SKU clustering  
  - product projection  

---

### 3.3 SKU Clustering

Группировка SKU внутри category meaning.

Этапы:
1. pre-segmentation (rule-based)  
2. clustering  
3. noise handling:
   - nearest cluster  
   - other cluster  
   - manual flag  

---

#### Constraint

Clustering происходит в пространстве Category Meaning, а не по сырому тексту.

---

### 3.4 Product Projection

Представление конкретного SKU.

---

#### Functional Component

Формируется из:
- attributes  
- category (product-type)  
- weak signals (title)  

---

#### Expressive Component

Формируется из:

- category expressive prior  
- SKU-level signals (title / reviews / description)  

---

#### Cold Start Logic

- если у SKU слабые expressive сигналы → используется category prior  
- если сигналы есть → они уточняют или переопределяют prior  

---

#### Result

SKU представлен как:

- Functional profile  
- Expressive profile  

---

## 4. Query Side

### 4.1 Query Signals

Источники:
- WB API  
- CSV ingestion  

Pipeline:
- normalization  
- pruning  
- clustering  
- hybrid annotation  

---

### 4.2 Query Meaning

Семантическое представление запросов.

Содержит:
- product-type intent  
- use-case intent  
- attribute intent  
- expressive intent (vibe)  

---

#### Properties

- строится только из queries  
- не зависит от product side  
- использует:
  - cluster priors  
  - individual top queries  

---

## 5. Matcher

Связывает:

> Product Projection ↔ Query Meaning

---

### 5.1 Matching Layers

#### Functional Matching
- product-type match  
- use-case match  
- attribute match  

#### Expressive Matching
- vibe / aesthetic alignment  

#### Penalties
- mismatch  
- conflict  
- missing critical signals  

---

### 5.2 Output

Matcher возвращает:
- структурированный набор сигналов  
- без финального score  

---

## 6. Scoring

Финальный этап.

---

### 6.1 Principles

- additive only  
- без мультипликаторов  
- explainable  

---

### 6.2 Structure

score =  
functional_score  
+ expressive_score  
+ penalties  

---

#### Notes

- веса не фиксируются архитектурно  
- expressive может доминировать  

---

### 6.3 Future Component

- competition signal (обязателен, но пока отсутствует)  

---

## 7. Non-Goals (Current Stage)

Система НЕ включает:

- generation (title/description)  
- LLM в runtime  
- embeddings как обязательный слой  
- UI / monitoring / feedback loop  

---

## 8. Explicit Architectural Gaps (Current State)

- Category Meaning → отсутствует  
- Product Projection → частично (через сырой текст)  
- SKU Clustering → placeholder  
- Reviews → не интегрированы  
- Matcher → не выделен как слой  
- Scoring → нарушает additive rule  
- Competition signal → отсутствует  

---

## 9. Key Invariants

1. Category Meaning строится из товаров  
2. Query Meaning строится из запросов  
3. Matcher соединяет, но не создает смысл  
4. SKU clustering зависит от Category Meaning  
5. система должна работать без reviews  
6. expressive meaning — критический слой  
7. Product Projection использует category prior  
8. manual overrides не входят в core architecture  
# SEO Module — Master Context

## 1. Goal

We are building an SEO module for Wildberries that:

- determines relevant search queries for each SKU
- filters high-frequency but irrelevant queries
- scores queries using semantic + structural signals
- generates improved title/description (later stage)
- provides explainability for each decision
- supports versioning and rollback

The system must work with weak behavioral signals (WB attribution is limited).

---

## 2. Key Constraints

- No LLM provider integrated yet (will use OpenRouter via abstraction)
- No full WB frequency database loaded yet (CSV ingestion needed)
- Behavioral signals (cart/orders) are sparse (<5%)
- Current SKU descriptions are unreliable (SEO noise)
- Reviews are noisy and must be filtered

---

## 3. Core Architecture Principles

### 3.1 Pipeline Scope
Pipeline runs **per project × per category**, not globally.

---

### 3.2 Clustering
- Use HDBSCAN for SKU clustering
- Always apply rule-based pre-segmentation before clustering
- Do NOT mix fundamentally different product types

---

### 3.3 Noise Handling (Critical)
HDBSCAN noise (label = -1) must NOT be ignored.

Each SKU must be assigned via:
- direct cluster
- nearest cluster fallback (cosine similarity)
- "other" cluster
- manual review flag

---

### 3.4 Semantic Layers (DO NOT MIX)
We distinguish 3 layers:

- product-type (what kind of product)
- use-case (how it is used)
- attributes (properties like size, color, etc.)

These are NOT interchangeable.

---

### 3.5 Reviews Usage
Reviews are used for:
- language markers
- anti-patterns (generation constraints)
- cluster enrichment
- SKU enrichment (only if enough data)

Reviews are NOT the source of truth for intent.

---

### 3.6 Trust-aware SKU Representation

If SKU has insufficient reviews:
- use attributes + cluster profile + weak title

If SKU has sufficient reviews:
- add filtered review markers

Threshold:
- ≥15 cleaned reviews
- ≥8 meaningful (attribute-related) reviews

---

### 3.7 Scoring Model
- Additive scoring only (no multiplication)
- No hard filtering (only boosts and penalties)
- Cold start must work without behavioral data

---

### 3.8 Explainability (Mandatory)
Each score must be decomposed into components.

No "black box" outputs allowed.

---

### 3.9 Versioning (Mandatory)
Each generation must store:
- cluster profile version
- scoring weights version
- queries used
- score breakdown

---

### 3.10 Competition Signal
Competition must be included in MVP (not later).

---

## 4. What MUST NOT be done

- Do NOT hardcode OpenRouter into business logic
- Do NOT implement final text generation yet
- Do NOT build UI
- Do NOT rely on description as main semantic source
- Do NOT skip explainability
- Do NOT ignore HDBSCAN noise points
- Do NOT invent missing logic — leave TODOs instead

---

## 5. Current Stage

We are implementing **foundation layer only**:

- database schema
- models
- service structure
- provider abstraction
- query ingestion pipeline (CSV + normalization)
- clustering skeleton
- scoring skeleton

NO full AI pipeline yet.

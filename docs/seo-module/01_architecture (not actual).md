# SEO Module — Architecture

## Full Pipeline

INPUT:
  SKU data
  Query data
  Reviews

↓

NORMALIZATION:
  SKU normalization
  Query normalization
  Review cleaning

↓

SKU PRIORITIZATION:
  prioritize by CTR drop / demand / new SKUs

↓

RULE-BASED PRE-SEGMENTATION:
  split by category / type / material / function

↓

HDBSCAN CLUSTERING:
  cluster SKUs within segment
  + noise handling:
    - nearest cluster fallback
    - "other" cluster
    - manual review

↓

CLUSTER PROFILES:
  product-type
  use-case
  attributes
  language markers
  anti-patterns

  + human validation required

↓

QUERY PIPELINE:
  prune top queries (80%)
  cluster queries
  annotate:
    - top queries individually
    - tail via cluster priors

↓

SKU REPRESENTATION:
  trust-aware:
    if <15 reviews → no review markers
    else → include filtered markers

↓

EMBEDDINGS:
  SKU embeddings
  Query embeddings

↓

MATCHING LAYERS:
  semantic similarity
  product-type match
  attribute match
  use-case match
  mismatch penalties

↓

COMPETITION SIGNAL:
  simple top-30 density / saturation

↓

SCORING (ADDITIVE):
  weighted sum with penalties

↓

EXPLAINABILITY:
  full breakdown per query

↓

FILTERING:
  core / expansion / excluded

↓

GENERATION (LATER):
  title / description

↓

HUMAN REVIEW

↓

VERSIONING SNAPSHOT

↓

MONITORING

↓

FEEDBACK LOOP

# Category B Report — <display_name> (<category_id>)

> Fill this report after Phase 1 is actually run. Do not use this template as permission to start Phase 1.

---

## 1. Summary

- project_id:
- category_id:
- display name:
- CSV source/path:
- profile version:
- matcher SKU count:
- decision: `proceed | fix derive | block Phase 2`

Short conclusion:

```text
<1-3 paragraphs>
```

---

## 2. CSV / Corpus Summary

- CSV source/path/hash:
- import command/API:
- import diagnostics artifact:
- query count before:
- query count after:
- cluster count:
- axes status:
- `product_type_axes` summary:
- suspicious subject notes:
- bootstrap artifacts:
  - `query_counts_before_after.json`
  - `import_result.json`
  - `bootstrap_run.json`
  - `bootstrap_status_final.json`
  - `corpus_health.json`

---

## 3. Profile Summary

- profile_id:
- version:
- snapshot path:
- schema_version:
- source_note:
- is_active:
- subject.primary:
- primary aliases:
- related_but_different:
- hard_conflicts count:
- bucket_cutoffs:
- bucket_caps:

Profile notes:

```text
<what looks right / suspicious>
```

---

## 4. Self-check

- status:
- checks:
- warnings:
- failed checks, if any:

Artifact:

- `profile_self_check.json`

---

## 5. Matcher Run Summaries

### SKU 1

- nm_id:
- run_id:
- profile version:
- category_profile_active:
- bucket counts:
- top primary examples:
- useful secondary examples:
- notable broad examples:
- notable rejected examples:
- reasons/conflicts notes:

### SKU 2

- nm_id:
- run_id:
- profile version:
- category_profile_active:
- bucket counts:
- top primary examples:
- useful secondary examples:
- notable broad examples:
- notable rejected examples:
- reasons/conflicts notes:

### SKU 3

- nm_id:
- run_id:
- profile version:
- category_profile_active:
- bucket counts:
- top primary examples:
- useful secondary examples:
- notable broad examples:
- notable rejected examples:
- reasons/conflicts notes:

Artifact:

- `matcher_runs_summary.json`

---

## 6. Operator Review

- SKU 1 verdict:
- SKU 2 verdict:
- SKU 3 verdict:
- common strengths:
- common issues:
- any category leakage:
- any evidence of orders/conversion scoring:

Artifact:

- `operator_review_notes.md`

---

## 7. Problems Found

- data issues:
- import/bootstrap issues:
- derive issues:
- profile/self-check issues:
- SKU evidence issues:
- matcher issues:
- UX/API issues:
- unresolved `needs verification`:

---

## 8. Decision for Phase 2

Decision:

- `proceed | fix derive | block Phase 2`

Required follow-up:

- item 1:
- item 2:
- item 3:

If blocked, escalation summary:

```text
ESCALATION
Phase: 1
Step:
Issue:
Evidence:
Options I see:
  A)
  B)
Recommendation:
Waiting for your decision.
```


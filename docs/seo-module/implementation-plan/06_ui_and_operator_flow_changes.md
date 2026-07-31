# 06. UI And Operator Flow Changes

Audience: frontend lead / PM
Date: 2026-04-23

Purpose: make the operator see the truth the audits revealed, and make every decision easy to audit, replay, and compare. No cosmetic additions.

---

## 1. Global UI primitives

### 1.1 `QualityBadge`

A single reusable component, four states, one color per state.

| Value | Label | Color guidance | Tooltip |
|---|---|---|---|
| `full` | Full | green | "All inputs real, no proxies." |
| `preview` | Preview | blue | "At least one deterministic proxy in the path. Not production quality." |
| `degraded` | Degraded | yellow | "Some evidence missing. Result may be incomplete." |
| `fallback` | Fallback | red | "Product-data-only fallback. Deep LLM/review evidence unavailable." |

Surfaced everywhere: SKU summary, query selection, matcher compare, generation, generation compare, content-version history, category page, product list row.

### 1.2 `CategoryTierBadge`

Three states, one color per state, always visible on the category page header and on every SKU page.

| Value | Label | Color | Meaning |
|---|---|---|---|
| `preview_only` | Preview only | gray | "No eval yet. No generation promotion allowed." |
| `eligible_for_preview` | Preview eligible | amber | "Reduced eval passed. Generation preview allowed." |
| `acceptance_passed` | Acceptance passed | green | "Full eval passed. Generation may advance to candidate." |

### 1.3 Matcher run reference widget

A compact component shown on the query-selection page and on the SKU summary:

- Run id with a link to a read-only trace viewer.
- `matcher_version`, `policy_version`, `category_profile_version`, `embedding_model`.
- `QualityBadge`.

Clicking the run id opens `/seo/matcher/runs/{run_id}` (read-only page).

---

## 2. SKU summary page

Additions:

- `QualityBadge` next to the existing status label.
- `CategoryTierBadge` on the breadcrumb or page header.
- Matcher run reference widget under "SEO analysis" block.
- Two independent badges for query selection:
  - `Selection: Approved / Draft`
  - `Trust: Validated by eval / Unvalidated`
  (Replacing the single "Confirmed" concept.)
- "Why this status?" expand panel showing `degraded_reasons` for the latest matcher run.

Removed:

- The single "Confirmed" state label. Replaced by `selection_state` + `trust_state`.

---

## 3. Query selection page

Additions:

- `QualityBadge` at the page header.
- Per-query row: `eligibility_verdict` (small chip: Eligible / Ineligible [reason]) + score components expand.
- "Approve selection" button (renamed from "Confirm"). Tooltip: "Records your approval of this list. Matcher quality is shown separately."
- Compare panel toggle (visible when a `SeoMatcherRun` exists from the candidate path for this SKU): opens the matcher compare view.

Operator actions allowed at each state:

| `selection_state` | `trust_state` | Allowed actions |
|---|---|---|
| `draft` | `unvalidated` | Edit list, Approve selection |
| `draft` | `eval_validated` | Edit list, Approve selection (badge shows eval-validated matcher) |
| `approved` | `unvalidated` | Unapprove, Edit list (with warning: will return to draft) |
| `approved` | `eval_validated` | Unapprove, Edit list (with warning) |

Disabled / hidden:

- The existing "Go to generation" CTA is only enabled when `selection_state == approved` AND category tier ≥ `eligible_for_preview`. Hidden otherwise.

---

## 4. Matcher compare panel

New panel on the SKU page and a full-page version at `/seo/compare/matcher?nm_id=...`.

Layout:

- Two columns: **Current path** (left), **Candidate path** (right).
- Column headers: matcher version, `QualityBadge`, `matcher_run_id`.
- Four rows (one per bucket): shows queries in that bucket for each path.
- A "Delta" summary strip at top:
  - `agreement_rate`, `moved_to_primary`, `moved_out_of_primary`, `newly_rejected_on_conflict`.
- Per-query diff row when moved: shows movement direction with the reason from the candidate's `eligibility_verdict` or matched/conflict atoms.

Operator verdict input:

- A "Mark this SKU" radio group per SKU: `candidate_better | same | current_better | uncertain`.
- Notes field.
- Write target: a small `seo_matcher_human_verdict` table (or reuse `seo_generation_human_review` pattern) — keep scope tight.

Use:

- Feeds the promotion decision (human verdict signal).
- Helps prioritize which category profile rules to tune.

---

## 5. Generation page

Additions:

- Persistent "Research preview" banner visible whenever category tier < `acceptance_passed` OR the env flag is off OR `mode_used = candidate` AND `content_kind = preview`.
- `QualityBadge` per content version.
- `matcher_run_id` reference next to the generated card title.
- Relabel the existing SEO relevance score:
  - New label: "Internal lint score"
  - Tooltip: "Diagnostic only. Not a quality gate. Not used for promotion."
- New "Promote to candidate" button — visible only when:
  - category `eligibility_tier >= eligible_for_preview`, AND
  - a saved `seo_generation_human_review.verdict in {accept_with_edits, accept}` exists for this version, AND
  - `quality_mode != fallback`.
- New "Human review" form section:
  - Relevance (1-10), Fidelity (1-10), Unsupported claims (checkbox).
  - Notes field.
  - Verdict (`reject | accept_with_edits | accept`).
- Content version history strip at the bottom with `content_kind` tags: `preview`, `candidate`, `approved`.

Removed / disabled:

- The frontend hardcoded `generationEndpointReady = true` is removed. Readiness is derived from:
  - env flag `SEO_GENERATION_PREVIEW_ENABLED`, AND
  - category tier ≥ `eligible_for_preview`, AND
  - `selection_state == approved` for the SKU.
- The existing hardcoded model names in `briefPreview` are removed; the generation page fetches model info from backend.

---

## 6. Generation compare view

New page at `/seo/compare/generation?nm_id=...`.

Layout:

- Two columns: current-path content version and candidate-path content version.
- Each column: title, characteristics, description, matched/missing/conflict atoms, `QualityBadge`, `matcher_run_id` link.
- Diff highlighting: word-level on title, field-level on characteristics, paragraph-level on description.
- Shared "Human review" form (one verdict captures the comparison).

---

## 7. Category page

Additions:

- `CategoryTierBadge` at top.
- "Active category profile" section:
  - `version`, `activated_at`, `status`.
  - Read-only payload preview (term groups, conflict rules, bucket cutoffs).
- "Eval history" section:
  - Table of recent `seo_eval_runs`: ran_at, verdict, metrics summary.
  - "Run eval" button (triggers eval endpoint; disabled if no labels loaded).
- Clear statement of current tier with its implications:
  - "Preview only — generation preview is not allowed."
  - "Preview eligible — generation preview allowed, promotion disabled."
  - "Acceptance passed — generation may be promoted to candidate."

Removed:

- Ambiguous language like "Category is ready" — replaced with explicit tier + quality info.

---

## 8. Product list page

Additions:

- A column for `QualityBadge` of the latest matcher run on each SKU.
- A column for the two-axis selection state (icon pair: Approved/Draft + Validated/Unvalidated).
- Filters for `quality_mode`, `eligibility_tier`, `selection_state`, `trust_state`.

Use: operators can quickly find SKUs where candidate improved bucketing, where fallbacks happened, where eval validated the matcher, etc.

---

## 9. Matcher run viewer

New read-only page at `/seo/matcher/runs/{run_id}`:

- Header: run id, project/category/nm_id, `matcher_version`, `policy_version`, `category_profile_version`, `embedding_model`, `QualityBadge`, `degraded_reasons` list.
- Inputs section: sku_atoms_id, vision_atoms_id, query_atoms_version (with links).
- Readiness snapshot.
- Buckets: same shape as matcher compare columns.
- Replay button: "Replay this run" — re-executes `run_matcher_v2` with identical inputs and shows a diff. Useful for nondeterminism detection.

---

## 10. Eval page

New page at `/seo/eval?category_id=...`:

- Current tier.
- Latest eval metrics (accuracy / primary precision / recall / bad primary count / hard-conflict primary count / per-error-type).
- History table of `seo_eval_runs`.
- "Run eval" button, with label set selector.
- "What the gates require" info panel describing current thresholds.

Operator actions:

- Run eval (writes `seo_eval_runs`, flips tier if thresholds met).
- Export metrics.
- Explicitly not in scope: editing labels in UI (iteration 2 may add a minimal labeling table editor).

---

## 11. Separation of approved vs validated (explicit)

This is a recurring audit finding. The UI must make it unambiguous:

- "Approved" is always an action performed by an operator on a selection list. Icon: checkmark with a person silhouette.
- "Validated" is always the result of an eval run on the matcher backing that selection. Icon: lab-flask / graph.
- Never combine them into one icon or label.
- The generation CTA requires both. If either is missing, show a concrete reason in the disabled button's tooltip: "Cannot generate: selection not approved" or "Cannot promote: matcher not eval-validated."

---

## 12. Operator actions allowed at each stage (matrix)

| Stage | Operator actions | Disabled / hidden |
|---|---|---|
| SKU analysis | Start analysis, view `QualityBadge`, see fallbacks | Skip human review |
| Query selection (draft) | Edit list, approve selection | Promote, generate (preview allowed via preview flag) |
| Query selection (approved + unvalidated) | Unapprove, generate in preview | Promote generation beyond preview |
| Query selection (approved + eval_validated) | Unapprove, generate, view compare | — |
| Generation preview | View card, run human review, trigger one retry | Promote (unless gates met), publish |
| Generation candidate | View card, move back to preview (with reason) | Publish |
| Generation approved | View card | Edit without creating a new version |
| Category preview_only | Run eval if labels loaded | Generate, promote |
| Category eligible_for_preview | Generate (preview), run eval | Promote beyond candidate |
| Category acceptance_passed | Generate, run eval, promote to candidate/approved | Publish (not enabled in this plan) |

---

## 13. Copy and wording changes

Reword UI strings so ambiguity is gone:

- "Confirm" → "Approve selection."
- "SEO relevance score" → "Internal lint score (diagnostic only)."
- "Готов к подбору" → keep label but do not derive logic from it; logic derives from enum fields. UI label is purely informational.
- "Generation ready" → remove or replace with "Generation available in preview for this category."
- "Matcher version" → always shows `matcher_version + policy_version + category_profile_version` together when surfaced, so "what produced this result" is unambiguous.

---

## 14. Decisions the UI must enable

Each UI addition corresponds to a real decision it enables, stated explicitly:

- `QualityBadge` → "Do I trust this result enough to approve?"
- `CategoryTierBadge` → "Am I allowed to generate / promote in this category?"
- Matcher compare panel → "Is candidate better than current here?"
- Human review form on generation → "Does this card meet our quality bar regardless of the lint score?"
- Matcher run viewer → "Which inputs produced this bucket, and can I replay it?"
- Eval page → "Should this category advance a tier today?"

Everything else is decoration and must be justified against a decision or cut.

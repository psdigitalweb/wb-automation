# AGENTS.md — EcomCore repository instructions

> Status: repository-wide rules for AI agents.
> Version: v2 (2026-05-14).
> Purpose: keep common engineering rules at the repo root and move module-specific contracts into their own scopes.

---

## 0. Scope routing

Start every task by deciding which scope it belongs to. Read only the documents needed for that scope.

### Repository-wide

These rules apply to all work in `D:\Work\EcomCore`.

Always preserve:

- existing authentication and authorization behavior unless the user explicitly asks to change it;
- API contracts and database schemas unless the task is specifically about them;
- user changes already present in the working tree;
- secrets and local environment files.

### SEO module

SEO-specific workflow is not repository-wide. It applies only when the task touches one of these areas:

- `docs/seo-module/`;
- `src/app/services/seo/`;
- `tests/seo/`;
- backend SEO routers/schemas/models;
- frontend SEO pages or SEO-specific components.

For SEO work, read `docs/seo-module/AGENTS.md` first, then follow the active SEO phase documents listed there.

If a task does not touch SEO, do not load SEO Phase 0/Phase 1 instructions and do not block the task on SEO execution plans.

### Frontend redesign / UI v2

Frontend redesign work applies when the task touches application shell, navigation, layout, visual system, dashboards, or non-SEO frontend screens.

For frontend redesign work, read:

1. `docs/design-system/README.md` if it exists.
2. The current external design reference folder, if repo docs have not been migrated yet: `D:\Work\Ecomcore design`.
3. Relevant frontend files under `frontend/app`, `frontend/components`, `frontend/lib`, and `frontend/styles` if present.

Do not migrate SEO pages/components as part of general UI v2 work unless the user explicitly says this is an SEO UI task.

---

## 1. Source of truth hierarchy

When sources conflict, use this order:

1. User's latest explicit instruction in the current chat.
2. Scope-specific specs or workflow documents.
3. Repository-wide `AGENTS.md`.
4. Existing code behavior.
5. Code comments.
6. Agent intuition.

If a spec appears wrong or conflicts with product behavior in a way that would require a product decision, stop and ask the operator before implementing.

---

## 2. Git hygiene

- Do not change git config.
- Do not commit without an explicit user request.
- Do not force push to `main` or `master`.
- Do not skip pre-commit hooks with `--no-verify`.
- Do not use interactive git flows such as `git rebase -i` or `git add -i`.
- Prefer small, scoped changes.
- One logical task should map to one branch/PR unless the user asks otherwise.
- Default branch prefix for new agent branches: `codex/`.

If the working tree contains unrelated changes, assume they belong to the user or another agent. Do not revert them. Work around them, and mention any relevant overlap in the final report.

---

## 3. Secrets and data safety

- Do not commit `.env`, credentials, API keys, dumps, or generated files containing sensitive data.
- Do not print secrets or personally identifiable information into logs, comments, docs, or chat.
- If a task requires external services, prefer existing client modules and configuration patterns.
- Do not send production data to third-party LLMs unless the user explicitly approves it.

---

## 4. Engineering workflow

Before code changes:

- Inspect the relevant files and local patterns.
- For tasks with three or more steps, keep a short task plan.
- Confirm the task belongs to the right scope from §0.

During changes:

- Prefer the repo's existing architecture and naming.
- Keep edits limited to the requested behavior.
- Avoid opportunistic refactors.
- Add or update tests when behavior changes or a new file introduces meaningful logic.
- Use typed, explicit code in Python and TypeScript.

After changes:

- Run the narrowest useful checks first.
- For frontend-only changes, run at least `cd frontend && npx tsc --noEmit` when dependencies are available.
- For backend Python changes, run the relevant `pytest` target.
- For SEO changes, follow `docs/seo-module/AGENTS.md`.

---

## 5. Frontend rules

- Keep auth, redirects, project selection, and API client behavior intact unless the user asks for a product change.
- Prefer local, composable React components over broad rewrites.
- Keep page content and shell/navigation migrations separate unless the task explicitly combines them.
- Namespace new UI v2 CSS to avoid collisions with legacy global classes.
- Do not introduce a new design language if a design-system reference exists.
- Do not add a new global state library unless there is a clear need and user approval.
- For `page.tsx` work, prefer local `_components/` folders for page-specific components.
- Keep TypeScript strict; avoid `any` unless there is an explicit comment explaining the exception.

Frontend redesign source files should generally live under:

- `frontend/components/ui-v2/` for reusable UI v2 shell and primitives;
- `frontend/lib/` for frontend utilities such as feature flags;
- `docs/design-system/` for design references, migration plans, and navigation specs.

---

## 6. Backend rules

- Preserve existing API response shapes unless the task is explicitly an API contract change.
- Do not mutate production-like data through ad hoc SQL in runtime code.
- Use migrations for schema changes.
- Keep external API calls behind service/client modules.
- Prefer explicit exceptions and typed data structures.

---

## 7. Design-system files

The design system should be versioned with the repo under `docs/design-system/`.

Until the migration is complete, the external folder `D:\Work\Ecomcore design` is an accepted reference source for UI redesign work. If a task depends on a design reference that only exists there, either:

- copy the relevant spec/screenshot into `docs/design-system/` as part of a dedicated docs migration task; or
- mention the external file path in the final report.

Do not scatter design references across unrelated folders.

---

## 8. Communication format

For implementation tasks, final reports should include:

```text
Status: closed | blocked | needs-review
Changed files:
- <path>
Tests: pass | fail | skipped
Next step: <what should happen next>
```

If blocked, include the reason, evidence, and the decision needed from the operator.

---

## 9. Escalation

Stop and ask the operator when:

- a spec conflicts with code and the correct behavior is not obvious;
- the task requires deleting or changing existing public API endpoints;
- the task requires a database schema change not mentioned in the request;
- repeated attempts fail with the same class of error;
- the implementation would require exposing secrets, PII, or production data;
- the requested change crosses from one scope into another unexpectedly, especially frontend redesign into SEO or vice versa.

Do not implement speculative product decisions just to keep moving.

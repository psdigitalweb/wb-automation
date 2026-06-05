# EcomCore Design System

> Status: entry point for UI redesign work.
> Version: v1 (2026-05-14).

This folder is the in-repository home for EcomCore design-system references, UI v2 plans, navigation specs, screenshots, and implementation notes.

The original external source folder was:

```text
D:\Work\Ecomcore design
```

Use this repo folder as the primary source for UI redesign tasks. The external folder may still exist as a backup, but agents should not depend on it by default.

## Structure

- `specs/` — written design briefs and navigation specs.
- `components/` — JSX design-system reference implementations.
- `references/html/` — standalone HTML reference screens.
- `screenshots/` — visual screenshots used as implementation references.
- `legal/` — non-UI reference documents.

## Key Files

- `specs/ecomcore-design-brief.md` — main design brief.
- `specs/ecomcore-design-brief-v1.md` — earlier design brief snapshot.
- `specs/ecomcore-navb-compact-spec.md` — Nav B compact shell spec.
- `components/ecomcore-design-system-v1.1.jsx` — latest JSX reference.
- `references/html/Nav B - Rail _ sub-nav _standalone_.html` — standalone Nav B reference.
- `references/html/Project Overview _standalone_.html` — project overview reference.
- `references/html/Project Settings _standalone_.html` — project settings reference.
- `references/html/Projects List _standalone_.html` — projects list reference.
- `references/html/SEO Module _standalone_.html` — SEO module reference; use only for SEO UI tasks.

## Usage

For frontend redesign work, read `specs/ecomcore-design-brief.md` first, then the most relevant screen or navigation reference.

For UI v2 shell work, read:

1. `specs/ecomcore-design-brief.md`
2. `specs/ecomcore-navb-compact-spec.md`
3. `references/html/Nav B - Rail _ sub-nav _standalone_.html` if visual details are needed

Do not treat the SEO standalone reference as permission to migrate SEO pages during general UI v2 work.

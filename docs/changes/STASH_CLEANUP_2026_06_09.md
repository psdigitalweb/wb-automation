# Stash cleanup 2026-06-09

Reason: old stash entries had become opaque release leftovers rather than actionable work.
Decision: clear the stash and stop using stash for anything that must be remembered.

Policy going forward:

- Use `git stash` only for short-lived local interruptions.
- For anything that may matter later, create a branch and commit it with a clear message.
- Do not stash dumps, secrets, local backup files, or generated artifacts.

Stash entries observed before cleanup:

| Ref | Original context | Summary |
|---|---|---|
| `stash@{0}` | `release/reviews-wave` | SEO leftovers cleanup; 21 files, 1593 insertions, 29 deletions. |
| `stash@{1}` | `release/reviews-wave` | SEO foundation tables/OpenRouter provider; 4 files, 535 insertions. |
| `stash@{2}` | `feat/reviews-next` | Tiny SEO provider base change; 1 file, 2 insertions. |
| `stash@{3}` | `feat/reviews-next` | SEO models/settings leftovers; 2 files, 396 insertions, 22 deletions. |
| `stash@{4}` | `feat/reviews-next` | SEO foundation test; 1 file, 166 insertions. |
| `stash@{5}` | `feat/reviews-next` | Large SEO foundation package; 22 files, 1608 insertions. |
| `stash@{6}` | `release/analytics-communications-2026-03-03` | `pre-search-report-2026-04-03`; no files shown by stash stat. |
| `stash@{7}` | `release/analytics-communications-2026-03-03` | `pre-experiments-2026-04-03`; no files shown by stash stat. |
| `stash@{8}` | `release/wave-1` | Wrong-base wave1 attempt; 13 files, 3265 insertions, 191 deletions; included local artifacts. |
| `stash@{9}` | `release/analytics-communications-2026-03-03` | Very large pre-wave1 changes; 70 files, 12458 insertions, 376 deletions. |
| `stash@{10}` | `release/analytics-communications-2026-03-03` | Release docs/scripts/backups; 14 files, 1951 insertions. |
| `stash@{11}` | `fix/wb-finance-pagination` | WIP before origin sync; 25 files, 3451 insertions, 17 deletions. |
| `stash@{12}` | `release-2026-02-15` | SKU resolver change; 1 file, 63 insertions, 1 deletion. |
| `stash@{13}` | `release-2026-02-15` | Debug scripts/docs; 6 files, 528 insertions. |
| `stash@{14}` | `fix/sku-pnl-restore` | Large local release WIP; 55 files, 8769 insertions, 418 deletions. |
| `stash@{15}` | `fix/sku-pnl-unit-metrics` | Pre-release autopilot WIP; 64 files, 3082 insertions, 1419 deletions. |

These entries were not converted to branches because several included stale release
work, local artifacts, backups, or potentially sensitive/generated files. Keeping them
as stash entries created more operational risk than value.

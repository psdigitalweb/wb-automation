# Phase 0 Step 10: 812 Regression Gate

Step 10 validates matcher_v2 after CategoryProfile wiring for project `1`, category `812`.

## Active Profile

- profile id: `1`
- version: `v1.812.skeleton.243953b2`
- schema_version: `category_profile_v1`
- self_check_status: `passed`
- active count: `1`

Source: `active_profile_check.csv`.

## Matcher And Eval

- matcher run ids used by eval: `64`, `63`, `65`, `66`, `67`, `68`, `69`, `70`
- fresh matcher run ids: `63`, `64`, `65`, `66`, `67`, `68`, `69`, `70`
- eval run id: `75`
- labels_used: `149`
- labels_missing: `42`
- nm_ids: `277132340`, `291861306`, `292541341`, `346647412`, `677255519`, `677255521`, `678529108`, `678529109`
- category_profile_version in matcher runs: `v1.812.skeleton.243953b2`
- category_profile_active in matcher runs: `true`

Eval bucket distribution:

- primary: `77`
- secondary: `32`
- broad: `32`
- rejected: `8`

Source: `matcher_runs_summary.json`, `eval_current.json`.

## Regression Verdict

- baseline accuracy: `0.1678`
- current accuracy: `0.2349`
- drift: `+0.0671`
- minimum acceptable accuracy: `0.1378`
- verdict: `pass`

Source: `eval_comparison.json`.

## Grep Invariants

- `del category_profile`: `0`
- active matcher literals: `0`
- matcher_v2 legacy helper imports: compatibility imports are still present in `api.py` and `demand_ordering.py`; no active category literals were found.

`rg` could not be executed in this Windows Codex session because the bundled `rg.exe` returned access/encoding errors. The saved invariant artifact was produced with `git grep` over the same paths and patterns.

## Tests Summary

Completed checks:

- active profile SQL check: pass
- fresh matcher run for all labeled SKU: pass, `8/8`
- grep invariants: pass
- eval regression gate: pass
- Phase 0 suite: `75 passed, 1 skipped`
- targeted matcher/eval suite: `20 passed`

Optional full SEO:

- `pytest -x tests/seo/` failed only on `tests/seo/test_matcher_retention.py::test_keeps_referenced_runs`.
- observed summary before stop: `1 failed, 78 passed, 1 skipped`

Known unrelated failures:

- `tests/seo/test_matcher_retention.py::test_keeps_referenced_runs`

## Safety Confirmations

- runtime matcher logic was not changed
- `guards.py` was not changed
- query matcher logic was not changed
- legacy matcher was not removed
- no migrations were created
- profile was not deactivated
- Step 11 was not started
- `restorepoints/` was not committed

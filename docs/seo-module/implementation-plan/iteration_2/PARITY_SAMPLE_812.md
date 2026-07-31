# Parity Sample — Category 812 (D1)

> **Scaffold.** This file is written by
> [`scripts/parity_matcher_v2_812.py`](../../../../scripts/parity_matcher_v2_812.py)
> at artifact-generation time. The canonical copy must be produced by running
> the script against a real DB snapshot. The values below are placeholders so
> the artifact exists on disk before the live run happens.

- Generated at: _pending live run_
- Project: `1`
- Category: `812`
- SKUs compared: `0 / 10 planned`
- Flip overrides allowed for: `none`
- D1 verdict: **PENDING**

## Thresholds (from pre-kickoff decision D1)

- `<= 10%` bucket changes per SKU
- no `primary <-> rejected` flips (operator may explicitly allow per `nm_id`
  with `--allow-flip`)

## How to generate the real artifact

```bash
# full default run: picks the 10 most recently-annotated SKUs for category 812
python -m scripts.parity_matcher_v2_812 --project-id 1

# explicit SKU list
python -m scripts.parity_matcher_v2_812 --project-id 1 \
    --nm-ids 12345 67890 24680 13579 11111 22222 33333 44444 55555 66666

# with reviewed primary<->rejected overrides
python -m scripts.parity_matcher_v2_812 --project-id 1 \
    --allow-flip 12345 --allow-flip 67890
```

The script writes its output back to this file and prints a JSON summary to
stdout. Exit code is non-zero when the D1 bar is breached.

## Per-SKU results

| nm_id | queries | bucket changes | ratio | flips | verdict |
|---|---|---|---|---|---|
| _pending live run_ |  |  |  |  |  |

## `primary <-> rejected` flips (full list)

_Pending live run._

## Known follow-ups

- If the live run breaches the D1 bar, the operator must either fix the
  candidate matcher to converge on the legacy verdict or record an explicit
  override via `--allow-flip <nm_id>` and note the reason in this file's
  footer.
- Historical generated artifacts should be committed alongside the close-out
  of Iteration 2 in
  [ITERATION_2_IMPLEMENTATION_REPORT.md](ITERATION_2_IMPLEMENTATION_REPORT.md).

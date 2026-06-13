## 3-Agent Evidence Gate

Generated from local repo-forensics scanner output.

### Gate Summary

- Verdict: `FAIL`
- Exit code: `0`
- Report: `docs/repo_forensics/reports/baseline_latest.md`
- Skipped checks: `none`

| Metric | Count |
|---|---:|
| Total files | 1821 |
| Hard failures | 113 |
| Unknowns | 59 |
| Warnings | 135 |
| Missing required entrypoints | 0 |
| Missing critical modules | 0 |
| Runtime flow failures | 5 |
| Runtime flow unknowns | 4 |
| Safety critical | 16 |
| Evidence high | 88 |
| Drift high | 0 |

### Scope Guard

Verdict: `BLOCKED`

- Hard failures: `113`.
- Skipped checks: `none`.
- Scanner output is static/read-only evidence only.

### Grill Me Review

Verdict: `BLOCKED`

- Weakest assumption: Hard failures exist; do not treat this PR as proven.
- Fake-confidence tests: `130`.
- Unknown tests: `11`.
- Runtime flow unknowns: `4`.
- Critical caller unreferenced: `1`.

### Hermes Review

Verdict: `BLOCKED`

- Missing required entrypoints: `0`.
- Missing critical modules: `0`.
- Safety critical: `16`.
- Safety high: `38`.
- Safety unknown: `0`.
- No broker/live/order action was executed by the scanner.

### GSD Review

Verdict: `BLOCKED`

- Report path: `docs/repo_forensics/reports/baseline_latest.md`.
- Hard failures: `113`.
- Unknowns: `59`.
- Warnings: `135`.
- Next action: Fix hard failures or explicitly defer them with evidence before merge.

### Scope Guard

- No target runtime execution.
- No broker calls.
- No live order actions.
- No auto-fix.
- No auto-PR.
- No merge automation.

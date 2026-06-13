## 3-Agent Evidence Gate

Generated from local repo-forensics scanner output.

### Gate Summary

- Verdict: `FAIL`
- Exit code: `0`
- Report: `docs/repo_forensics/reports/baseline_latest.md`
- Skipped checks: `none`

| Metric | Count |
|---|---:|
| Total files | 4433 |
| Hard failures | 141 |
| Unknowns | 98 |
| Warnings | 132 |
| Missing required entrypoints | 0 |
| Missing critical modules | 0 |
| Runtime flow failures | 0 |
| Runtime flow unknowns | 0 |
| Safety critical | 21 |
| Evidence high | 116 |
| Drift high | 0 |

### Scope Guard

Verdict: `BLOCKED`

- Hard failures: `141`.
- Skipped checks: `none`.
- Scanner output is static/read-only evidence only.

### Grill Me Review

Verdict: `BLOCKED`

- Weakest assumption: Hard failures exist; do not treat this PR as proven.
- Fake-confidence tests: `115`.
- Unknown tests: `9`.
- Runtime flow unknowns: `0`.
- Critical caller unreferenced: `1`.

### Hermes Review

Verdict: `BLOCKED`

- Missing required entrypoints: `0`.
- Missing critical modules: `0`.
- Safety critical: `21`.
- Safety high: `81`.
- Safety unknown: `0`.
- No broker/live/order action was executed by the scanner.

### GSD Review

Verdict: `BLOCKED`

- Report path: `docs/repo_forensics/reports/baseline_latest.md`.
- Hard failures: `141`.
- Unknowns: `98`.
- Warnings: `132`.
- Next action: Fix hard failures or explicitly defer them with evidence before merge.

### Scope Guard

- No target runtime execution.
- No broker calls.
- No live order actions.
- No auto-fix.
- No auto-PR.
- No merge automation.

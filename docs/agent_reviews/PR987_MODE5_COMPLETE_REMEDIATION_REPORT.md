# PR #987 Mode 5 Complete Remediation Report

**Current verdict: HOLD**

**PR #987:** OPEN, DRAFT; confirmed head `c9608df0830ef9331fec1c467edd8fa5dc163d6d`

**Candidate:** `ram/pr987-mode5-complete-remediation`, based on the same SHA

**Worktree:** `/private/tmp/tradebot-pr987-mode5-complete-remediation`

## Purpose and scope

This is a review-only candidate. It contains fail-closed corrections and research scaffolding for Sentinel Mode 5. It is not authorized for paper/live execution, merge, or deployment. The normal tick path has no source-authenticated completed-bar producer, and Mode 5 quote evaluation terminalizes before sizing, dispatcher reservation, or APM entry.

The Mode 5 research profile changes candidate eligibility and target scaling: shared Gate 2 abstentions are observations, low-volatility target scaling is forced to 1.0, and confirmation requires consecutive epochs. TD/RP geometry and numeric strategy levels were not changed in the reviewed delta. These profile changes are not behavior-neutral and require separate policy/risk acceptance before any active path.

## Exact candidate identity

| File | SHA-256 |
|---|---|
| `core/sentinel_live_stream_advisor.py` | `510766566f00a42a6f4707d0cccb6b33676c9dbe6bfefd38d03eb9a81bfccfe7` |
| `tests/unit/test_sentinel_advisor_hardening_005.py` | `e9069597d71f5ef2c51af57435f047fe71e06cd77c00de93bc6a0720e82cfcdd` |
| `tests/unit/test_sentinel_optionmate_execution_hardening.py` | `ad033a3d9dced9c43f09bfacede021c354c237fecf5be5f6b473db4748df7c65` |
| `tests/unit/test_mode5_or_causality_policy.py` | `6c9eed225a24a8f2e00555a3beecec6c2b44b507bd08e92364ebd4475ff7696d` |
| `tests/unit/test_mode5_complete_advisor_reproduction.py` | `7944ad5c98340564c5c6cbd3cb91d637c114caa520946f91cc788d32022de22d` |

The two new test modules are included. The local work item, this report, and its evidence JSON are also intended review artifacts. `.qa-sandbox/` and all untracked runtime files (WALs, locks, trace, OR ledger and initialization marker) are excluded. They were preserved and not cleaned.

## Remediation delivered

- Synthetic tick buckets are retained as `UNKNOWN_TICK_BUCKET` diagnostics and excluded from strategy history/candidate generation when completeness cannot be proven.
- Completed-bar availability is checked before strategy-state mutation; replay uses an explicit event clock and fails closed when capture monotonic-clock provenance cannot be mapped.
- OR snapshots are fenced by session/generation/request identity; target and companion evidence is read consistently, with OR diagnostics non-authorizing in the research profile.
- Option quote ordering and freshness are rechecked immediately before APM update.
- Invalid-bar and policy diagnostics use strict JSON handling; the Mode 5 candidate cannot reach sizing or entry dispatch without an approved sizing contract.

## Validation

The exact command below ran from the candidate worktree with network denied and writes confined by `.qa-sandbox/mode5-test.sb`. Environment: macOS sandbox, Python 3.14, pytest 9.0.3.

```sh
sandbox-exec -f .qa-sandbox/mode5-test.sb env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" HOME="$PWD/.qa-sandbox/home" TMPDIR="$PWD/.qa-sandbox/tmp" pytest -q -p no:cacheprovider --basetemp="$PWD/.qa-sandbox/restored-final-510" tests/unit/test_sentinel_advisor_hardening_005.py tests/unit/test_sentinel_optionmate_execution_hardening.py tests/unit/test_mode5_or_causality_policy.py tests/unit/test_mode5_complete_advisor_reproduction.py
```

Result: **286 passed, 1 environment-blocked failure, 0 skipped** (25.94s). The sole failure, `test_independent_processes_reserve_only_one_last_attempt`, occurs before product code when the sandbox denies Python multiprocessing `SemLock` creation (`PermissionError`). It is not counted as a pass. `py_compile` and `git diff --check` passed. Full repository CI and broader required suites were not run.

A temporary unreviewed edit later failed 35 tests; that edit was reverted. The exact hashes above were restored and the coordinator reran the four scoped modules, obtaining 286 passed and the same one environment block.

## Independent review outcomes

- **QA:** exact hashes verified; no new defect found in the bounded OR/replay/quote freshness corrections; HOLD.
- **Technical & Quant:** exact hashes verified; confirms OR snapshot and quote freshness fixes; HOLD. No positive edge/P&L evidence.
- **Senior QA:** BLOCK for acceptance/readiness. A draft-only push is operationally separable if the exact scope is staged and runtime artifacts excluded.
- **UAT:** PASS for package consistency after the report/work-item rewrite. This is not product acceptance; broader validation and the listed blockers remain open.
- **Release Manager:** PASS for push to the existing PR as Draft/HOLD only; no merge/release approval.
- **CodeRabbit:** current-hash review completed with 7 core findings and 5 test-proof/cleanup findings. They remain open. Material unresolved findings include one-sided/stale-spot EOD management, a journal failure that may prevent exit dispatch, late opening-drive eligibility, shared gear/retained-strategy interactions, sanitizer overflow, and policy-observation queue admission. Do not treat this review as approval.

## Remaining blockers

1. No source-authenticated completed-bar/finality/continuity provider; live Mode 5 candidate readiness is unproven.
2. No approved sizing contract; Mode 5 remains blocked before sizing, dispatcher, and APM entry.
3. Stale spot or one-sided option depth can prevent position management. No fallback exit-price contract is authorized.
4. A journal exception may interrupt exit dispatch; changing order/dispatch semantics requires a separately reviewed design.
5. CodeRabbit findings and test-proof/cleanup findings remain open.
6. The 42-case family/index matrix, full historical replay, execution/UNKNOWN-state suite, point-in-time option/fill-cost evaluation, and full repository CI were not run.
7. External task-platform intake remains `UNSATISFIED`.

No brokerage calls, orders, live-process changes, commits, pushes, merges, or deployments have been performed by this report. A review-only push, if made, must keep PR #987 Draft/HOLD, name these blockers, and exclude `.qa-sandbox/` and runtime artifacts. No result here authorizes live trading or claims a profitable edge.

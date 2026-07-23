# PR 689 — Shared Backtest Integrity Production Review

- mode: SHARED_BACKTEST_INTEGRITY_PRODUCTION_FIX
- candidate_id: PR689_SHARED_BACKTEST_INTEGRITY_V1
- decision: DRAFT_FIX_BRANCH_CREATED
- reason: Independently reproduced shared research defects are repaired with fail-closed regression coverage.
- timestamp: 2026-07-22T01:21:16+05:30
- is_order_action: false
- broker_api_called: false
- source: docs/agent_reviews/pr689_shared_backtest_integrity.md

## Agent Work Contract

Repair only shared research/backtest integrity defects that were independently reproduced from repository code. Preserve strategy formulas and all live execution, broker, feed, risk, configuration, and dashboard behavior. Keep the pull request draft and unmerged until repository gates and human review complete.

## Scope Guard

Changed scope is limited to:

- causal daily and higher-timeframe research features;
- mean-reversion research ledger state/accounting;
- research tearsheet OOS metrics;
- elite walk-forward partition and promotion logic;
- mean-reversion Phase 4 audit/validation scripts;
- focused regression tests.

No strategy threshold, production order path, broker integration, live market feed, runtime risk control, or dashboard code is changed.

## Grill Me Review

Adversarial questions applied:

1. Can a future same-session close alter an earlier intraday regime decision? The new mutation tests require it cannot.
2. Can an incomplete HTF bucket influence lower-timeframe rows inside that bucket? The completed-bucket helper shifts HTF aggregates before mapping them back.
3. Can a pending signal execute later than the immediate next bar? The ledger records its signal index, expires stale state, and forbids entry-bar signal discovery.
4. Are underlying-index and option-proxy P&L units mixed? The ledger now declares one gating model and emits separate dimensional fields.
5. Can in-sample expectancy rescue a negative final holdout? Promotion reads final-holdout expectancy and profit factor only.
6. Can missing/empty evidence pass an audit? The Phase 4 truth, integrity, selection, accounting, and ledger audits now fail closed.

## Hermes Review

Contract and interface review:

- Existing `gross_pnl`, `costs`, and `net_pnl` fields remain present and now consistently use the underlying-index proxy lane.
- New explicit fields include `pnl_model`, `underlying_gross_pnl`, `underlying_net_pnl_after_index_cost`, `proxy_option_gross_pnl`, and `proxy_option_net_pnl`.
- Existing tearsheet keys remain; OOS keys are additive.
- `run_walk_forward` still accepts a DataFrame and now returns a structured report instead of relying only on printed output.
- Research-only execution flags remain false.

## GSD Review

The work is decomposed into causal features, ledger state/accounting, OOS/WFA isolation, and downstream fail-closed audits. Each changed contract has a focused test. Historical artifacts are not rewritten in this PR; affected research must be regenerated after merge.

## QA / Safety Review

Verification layers:

- causal mutation tests for daily EMA and HTF SMA;
- real ledger-script fixture covering next-bar execution and dimensional accounting;
- OOS-mask tests with a non-default index;
- explicit walk-forward boundary and final-holdout tests;
- calculated drawdown/RR/PF-state tests;
- downstream audit fail-closed tests;
- repository CI, CodeQL, Code Excellence, portfolio, forensics, and registry gates.

Safety properties:

- no live trading path is enabled;
- no execution permission is promoted;
- missing evidence produces blockers rather than approval;
- no historical strategy verdict is automatically reversed.

## High-Risk Path Review

Although the modified `core/` files are research/backtest utilities rather than live execution/risk modules, they can influence research promotion decisions. The PR therefore treats them as high-impact: causal timestamps, metric units, fold boundaries, and legacy output compatibility are explicitly tested and reviewed.

## Acceptance Proof

Pre-PR focused tests were executed three times with 14 passing tests per run, followed by Python compilation/static checks. Additional downstream fail-closed tests were added after consumer review and are required to pass in repository CI. Acceptance additionally requires:

- no unexpected test failures or XPASS outcomes;
- no changed live execution, risk, feed, broker, or strategy files;
- PR remains mergeable against `main`;
- all required GitHub checks pass;
- draft PR receives human approval before merge.

## Runtime Proof Required After Merge

Regenerate the affected research artifacts from frozen inputs and compare:

- vectorized TrendVWAP/MeanReversion/ORB candidate counts;
- `MEAN_REVERSION_EXTENSION` ledger entries, costs, P&L lanes, and audit reports;
- elite walk-forward fold and final-holdout results;
- Phase 4–6 promotion blockers.

Any affected historical result remains `UNTRUSTED_REQUIRES_RERUN` until this regeneration is completed.

## What This PR Does Not Prove

- It does not prove that any previously rejected strategy has structural edge.
- It does not validate tradable option execution economics.
- It does not repair or certify separate OptionBacktestEngine contract ambiguities.
- It does not authorize paper or live trading.
- It does not prove historical reports are correct without rerunning them.

## Human Approval

Human approval is required before changing this draft PR to ready-for-review or merging it. The PR must remain unmerged while checks or review questions are outstanding.

mode: PRODUCTION_CALCULATION_LIBRARY_WITHOUT_LIVE_WIRING
candidate_id: option_analytics_v1
decision: ACCEPT_PRODUCTION_CALCULATION_LIBRARY_FOR_DRAFT_REVIEW_WITH_LIVE_WIRING_DEFERRED
reason: Mathematical and contract tests pass for the isolated calculation API; live option-chain integration remains excluded until a separate compatibility and replay-validation change proves unchanged strategy and execution behaviour.
timestamp: 2026-07-26T11:58:13+05:30
source: core/option_analytics, tests/core/test_option_analytics.py, tests/core/test_option_analytics_hardening.py, scripts/audit_option_analytics_v1.py, and exact-head GitHub checks
base_sha: 596fff09859afeca292bc3e3e31d4a55db1fd8c6
branch: feature/production-option-analytics-v1
read_only_runtime: true
broker_api_called: false
is_order_action: false
strategy_signal_changed: false
candidate_ranking_changed: false
risk_gate_changed: false

# Option Analytics V1

## Agent Work Contract

- source_agent: ChatGPT
- action: IMPLEMENT_AND_VERIFY
- scope: New `core/option_analytics/` calculation library, focused tests, deterministic audit script, review evidence, and changed-path reporting.
- allowed_paths: `core/option_analytics/`, `tests/core/test_option_analytics.py`, `tests/core/test_option_analytics_hardening.py`, `scripts/audit_option_analytics_v1.py`, this review, and changed-path reporting.
- forbidden_paths: Existing broker, execution, feed, risk, dashboard, strategy, ranking, option-chain, configuration, and live-state files.
- acceptance_proof: Focused mathematical tests, deterministic audit grid, permanent PR gates, exact changed-file inventory, draft PR, and no live activation.

## Scope Guard

This change adds a dependency-light European-option calculation API. It does not modify `core/greeks.py`, `core/option_chain.py`, broker calls, order routing, dashboards, candidate selection, strategy signals, ranking, or risk gates.

Implemented capabilities:

- Black–Scholes–Merton pricing with continuous dividend yield.
- Black–76 pricing with explicit forward/futures input.
- Immutable typed inputs/results and fail-closed statuses.
- Exact timezone-aware time to expiry using elapsed seconds and ACT/365F.
- Analytic delta, gamma, theta, vega, and rho with explicit units.
- Deterministic bracketed implied-volatility inversion with model bounds.
- Strict quote provenance, freshness, crossed-market, and locked-market handling.
- Same-expiry, same-option-type IV-surface diagnostics using log-forward moneyness.
- Immutable candidate enrichment that does not rewrite strategy fields.
- Discrete pathwise Greek P&L attribution with residual and limitations.

## High-Risk Path Review

No existing high-risk runtime file is modified. The new package is calculation-only and has no broker, order, persistence, configuration, or live-state dependency. Live adoption is intentionally excluded from this PR.

## Grill Me Review

The main failure modes are false precision, hidden conventions, and treating model output as market truth. The implementation addresses these by requiring explicit model, option type, rate, dividend/forward convention, exact timestamps, price basis, quote age, and Greek units. Invalid inputs and solver failures return typed statuses rather than fabricated numbers. Surface residuals remain diagnostics and are not converted into recommendations.

The audit also distinguishes IV-identifiable prices from deep ITM/OTM near-expiry prices that are numerically at the zero-volatility lower bound. Those lower-bound cases are recorded rather than falsely claimed as successful recovery of the generating volatility.

Additional hardening proves that invalid enum values cannot be treated as puts, missing IV rows cannot report `OK`, non-finite result fields cannot leak `NaN`, duplicate observation identifiers fail closed, and signed European carry value is preserved rather than dishonestly clamped.

## Hermes Review

Mathematical contracts are centralized in frozen dataclasses and enums. Both models share explicit time and status conventions. The IV solver is bracketed bisection, checks model-consistent no-arbitrage bounds first, and returns no IV for out-of-bounds, unbracketed, or maximum-iteration outcomes. Analytic Greeks are checked against independent central finite differences, including put theta.

## GSD Review

The implementation is deliberately compact: twelve files under one new package, two focused test files, and one audit script. No new service, database, framework, external dependency, configuration key, broker adapter, or dashboard component is introduced.

## QA / Safety Review

Local isolated verification on Python 3.13.5:

- Focused tests: `77 passed` for the exact code and test set published to GitHub.
- Audit grid: `96` pricing/Greeks/IV cases.
- Put-call parity: `48` cases.
- Identifiable IV round trips: `48` cases.
- Numerically lower-bound/zero-time-value cases: `48` explicitly classified.
- Audit failures: `0`.
- Audit semantic SHA-256: `20d762b4bd11cda982c0ef61aa9cdbab585eb8cb3c9a0b2f31e36f07540773b1`.

Safety fields:

- `broker_api_called=false`
- `is_order_action=false`
- `live_execution_changed=false`
- `strategy_signal_changed=false`
- `candidate_ranking_changed=false`
- `risk_gate_changed=false`
- `holdout_read=false`
- `real_or_replay_pnl_read=false`

## Acceptance Proof

Publication requires:

- focused tests passing;
- deterministic audit verdict passing;
- put-call parity and finite-difference checks within frozen tolerances;
- all permanent GitHub checks completing successfully;
- changed files matching the declared scope;
- PR remaining draft and unmerged;
- no auto-merge;
- no live integration in this PR.

## Runtime Proof Required After Merge

No live activation should occur from this PR. After merge, run the calculation library in shadow mode against captured option-chain fixtures and compare its outputs with the legacy path. Required follow-up evidence includes exact timestamp mapping, price-basis provenance, compatibility differences, replay determinism, and zero changes to candidate eligibility or order behaviour.

## What This PR Does Not Prove

This work does not prove strategy edge, profitability, fair value, executable arbitrage, correct live option-chain integration, optimal strike selection, or causal P&L explanation. Greek attribution is a discrete approximation; higher-order and cross-Greek effects remain in the residual. Lower-bound options may have volatility that is numerically non-identifiable from price.

## Human Approval

Human review is required before merging this calculation library and again before any separate PR wires it into `core/option_chain.py`, candidate selection, risk logic, dashboards, or execution. Live activation is not authorized by this PR.

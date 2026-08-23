mode: PRODUCTION_CALCULATION_LIBRARY_WITHOUT_LIVE_WIRING
candidate_id: option_analytics_v1
decision: ACCEPT_PRODUCTION_CALCULATION_LIBRARY_FOR_DRAFT_REVIEW_WITH_LIVE_WIRING_DEFERRED
reason: Production calculation contracts, independent mathematical oracles, deterministic evidence, legacy compatibility audit, and fail-closed publication checks pass; live option-chain integration remains excluded until a separate shadow/replay validation change proves unchanged strategy and execution behaviour.
timestamp: 2026-07-26T12:45:00+05:30
source: core/option_analytics, research/option_analytics_v1, focused production and evidence tests, committed hash-linked evidence, and exact-head GitHub checks
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
- scope: New `core/option_analytics/` production calculation library, independent oracle and legacy compatibility audit, deterministic evidence packaging, focused tests, publication scripts, review evidence, and changed-path reporting.
- allowed_paths: `core/option_analytics/`, `research/option_analytics_v1/`, the narrowly named option-analytics scripts and tests, this review, and changed-path reporting.
- forbidden_paths: Existing broker, execution, feed, risk, dashboard, strategy, ranking, option-chain, configuration, and live-state files.
- acceptance_proof: Focused mathematical tests, independent formulas and finite differences, deterministic two-directory evidence, committed hashes, fail-closed gate, permanent PR checks, exact changed-file inventory, draft PR, and no live activation.

## Scope Guard

This change adds a dependency-light European-option calculation API and its independent evidence system. It does not modify `core/greeks.py`, `core/option_chain.py`, broker calls, order routing, dashboards, candidate selection, strategy signals, ranking, or risk gates.

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
- Independent pricing/parity/finite-difference oracle that does not import the production implementation.
- Executable legacy audit, deterministic evidence serialization, compressed complete case ledger, SHA-256 manifests, tamper-negative tests, and publication gate.

## High-Risk Path Review

No existing high-risk runtime file is modified. The new package is calculation-only and has no broker, order, persistence, configuration, or live-state dependency. Live adoption is intentionally excluded from this PR.

## Grill Me Review

The main failure modes are false precision, hidden conventions, silent numerical clipping, stale-price substitution, and treating model output as market truth. The implementation requires explicit model, option type, rate, dividend/forward convention, exact timestamps, price basis, quote age, and Greek units. Invalid inputs and solver failures return typed statuses rather than fabricated numbers. Surface residuals remain diagnostics and are never converted into recommendations.

The evidence distinguishes IV-identifiable prices from deep ITM/OTM near-expiry prices that are numerically at the zero-volatility lower bound. Those lower-bound cases are recorded rather than falsely claimed as successful recovery of the generating volatility.

Hardening proves that invalid enum values cannot be treated as puts, missing IV rows cannot report `OK`, non-finite result fields cannot leak `NaN`, duplicate observation identifiers fail closed, signed European carry value is preserved rather than dishonestly clamped, and the exact committed evidence bundle must pass its SHA-256 list, compressed-package hash, decoded-ledger hash, and publication gate.

## Hermes Review

Mathematical contracts are centralized in frozen dataclasses and enums. Both models share explicit time and status conventions. The IV solver is bracketed bisection, checks model-consistent no-arbitrage bounds first, and returns no IV for out-of-bounds, unbracketed, or maximum-iteration outcomes. Analytic Greeks are checked against independently coded central finite differences, including put theta. Put-call parity is independently checked across both model families.

## GSD Review

The production implementation remains compact: twelve files under one new package. The evidence layer is isolated under one research package, four narrowly named verification scripts, two production test files, and one evidence test file. No service, database, web framework, external dependency, configuration key, broker adapter, or dashboard component is introduced.

## QA / Safety Review

Exact intended GitHub-focused test inventory:

- Production option-analytics tests: `77`.
- Independent evidence/publication tests: `9`.
- Total focused tests: `86`.
- Independent reference grid: `96` cases with `96` outputs and `0` failures.
- Independent put-call parity checks: `48` with `0` failures.
- IV-identifiable round trips: `48`.
- Numerically lower-bound/non-identifiable IV cases: `48`, explicitly classified.
- Executable legacy audit: `17` cases and `7` confirmed legacy defects.
- Two-directory semantic determinism: `PASS`.
- Exact committed evidence-bundle verification: `PASS`.
- Publication verdict: `PASS_RESEARCH_SIDECAR_GATE`.

Evidence hashes:

- Reference payload semantic SHA-256: `35548e4ea12053eb84373e5a67dd6b0c58c876cda778088ecf80a158a392d2a5`.
- Reference artifact semantic SHA-256: `0ab4f905f84470d0f716dcea9e460af946c67abbc58f8c5ade6d4fbacb21d302`.
- Canonical reference JSON SHA-256: `1b305ed9fb9fa6e21c51ec164be661e5964240d9e489788f5408a9bcc7f8d9ed`.
- Committed reference package SHA-256: `0bb9d38316302141bbb6b7a4a7a69c7c790c9a99d7d69a682c631b7aff1a7de1`.
- Legacy audit semantic SHA-256: `dfb972f9b57195e11223338303b7ff86fa2f14d1630ad2212ca5fb2072fcc7d2`.
- Run-manifest semantic SHA-256: `cf9e7b25e8ab3d2363d36665173618c4f5324140fa3922d5ef2c9579a1a787a3`.
- Bundle-summary semantic SHA-256: `2b79032e6407a69fb0a2561e72e3f045ad92ce4b45e0faf45768178f68e4ba20`.

Legacy defect summary:

- put theta defect: `CONFIRMED`;
- integer-day/one-day-floor expiry defect: `CONFIRMED`;
- IV solver convergence ambiguity: `CONFIRMED`;
- invalid-input numeric-zero ambiguity: `CONFIRMED`;
- hidden global rate: `CONFIRMED`;
- impossible-price clamped IV: `CONFIRMED`;
- mark-price IV without first-class status/provenance: `CONFIRMED`.

Safety fields:

- `broker_api_called=false`
- `is_order_action=false`
- `live_execution_changed=false`
- `strategy_signal_changed=false`
- `candidate_ranking_changed=false`
- `risk_gate_changed=false`
- `outcomes_read=false`
- `holdout_read=false`
- `real_or_replay_pnl_read=false`

## Acceptance Proof

Publication requires:

- all `86` focused tests passing on the exact PR head;
- independent reference grid, finite-difference Greeks, parity, and IV round trips passing within frozen tolerances;
- deterministic audit verdict and packaged-evidence round trip passing;
- the exact committed evidence bundle and all committed SHA-256 manifests verifying;
- all permanent GitHub checks completing successfully;
- changed files matching the declared scope;
- PR remaining draft and unmerged;
- no auto-merge;
- no live integration in this PR.

## Runtime Proof Required After Merge

No live activation should occur from this PR. After merge, run the calculation library in shadow mode against captured option-chain fixtures and compare its outputs with the legacy path. Required follow-up evidence includes exact timestamp mapping, price-basis provenance, compatibility differences, replay determinism, and zero changes to candidate eligibility, ranking, risk, or order behaviour.

## What This PR Does Not Prove

This work does not prove strategy edge, profitability, fair value, executable arbitrage, correct live option-chain integration, optimal strike selection, or causal P&L explanation. Greek attribution is a discrete approximation; higher-order and cross-Greek effects remain in the residual. Lower-bound options may have volatility that is numerically non-identifiable from price.

## Human Approval

Human review is required before merging this calculation library and again before any separate PR wires it into `core/option_chain.py`, candidate selection, risk logic, dashboards, or execution. Live activation is not authorized by this PR.

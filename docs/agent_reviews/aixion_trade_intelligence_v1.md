# Agent Review — Aixion Trade Intelligence V1

## Agent Work Contract

Build a read-only TradeBot intelligence sidecar that captures causal evidence, reconstructs candidate and execution lineage, computes deterministic analytics, validates research integrity, supports evidence retrieval and controlled analyst reporting, and remains isolated from broker and order authority.

## Scope Guard

Allowed changes are limited to the `aixion_trade_intelligence` package, its read-only bridge and sidecar CLI, focused tests, documentation, and the isolated workflow. Production strategy logic, TradeBuilder decisions, ranking decisions, risk limits, broker routing, order placement, and autonomous promotion are excluded.

## Grill Me Review

The implementation is broad but still cannot certify profitability from synthetic or offline fixtures. Queue calibration requires real queue observations. Market-impact calibration requires real participation and impact observations. Drift and OOD require frozen reference distributions. PBO and Deflated Sharpe require a registered experiment corpus. CAS needs multiple real expiry and non-expiry sessions. A valid sidecar session proves evidence integrity, not edge.

## Hermes Review

The package now provides:

- canonical event and timing contracts;
- append-only idempotent evidence publishing;
- deterministic replay and payload integrity;
- PAPER/SHADOW-only sidecar ingestion;
- candidate and runtime truth adapters;
- causal bid/ask outcomes;
- market breadth, futures basis and option microstructure;
- effective-dated cost rules;
- Greek P&L attribution;
- capacity curves, queue calibration and market-impact fitting;
- counterfactual and blocker-value analysis;
- live/replay/backtest feature parity;
- purged/embargoed splits, PBO and Deflated Sharpe;
- drift, OOD and CUSUM metrics;
- empirical block-bootstrap risk simulation;
- configurable CAS accumulation;
- causal Market Event Graph validation;
- deterministic evidence retrieval;
- controlled cited analyst workflow with optional lazy LangGraph integration;
- dashboard read model;
- fail-closed strategy certification.

## GSD Review

The dependency order is preserved:

```text
evidence contract
→ replay integrity
→ sidecar ingestion
→ causal outcomes
→ market and execution analytics
→ research validation
→ retrieval and analyst
→ certification
```

No model or agent may override deterministic evidence gates.

## QA / Safety Review

Focused tests cover:

- future-availability rejection;
- payload tampering;
- duplicate and sequence handling;
- malformed sidecar records;
- live-mode refusal;
- causal ask/bid outcomes;
- point-in-time constituent weights;
- crossed-book rejection;
- cost-rule dependency ordering;
- Greek reconciliation;
- depth capacity and queue calibration;
- feature parity mismatch;
- purging, embargo, PBO and Deflated Sharpe;
- drift and OOD metrics;
- seed-reproducible risk simulation;
- CAS phases;
- MEG future-parent rejection;
- unsupported citations and contradictory analyst claims;
- AST-based absence of broker order calls;
- offline fixture and sidecar-to-report integration.

## Acceptance Proof

The isolated workflow must compile the complete intelligence surface, run all `tests/test_aixion_trade_intelligence_*.py` tests, produce an offline report, produce a report from the JSONL sidecar path, and retain `ready_for_profitability_claim=false` for fixture evidence.

## Runtime Proof Required After Merge

This PR is not ready for merge or live trading authority. A real PAPER/SHADOW session must first pass the local readiness checker, capture authoritative runtime files, complete normally, replay deterministically, and produce a valid session report. Multiple real sessions are required before statistical or profitability certification.

## What This PR Does Not Prove

It does not prove a profitable strategy, calibrated live queue probability, market capacity, acceptable risk of ruin, stable drift, valid holdout performance, or production merge readiness. It does not authorize live order actions.

## Human Approval

The user requested implementation and offline certification. The user did not authorize autonomous live orders, automatic strategy changes, automatic risk changes, or automatic merge.

## Final Review Verdict

```text
IMPLEMENTATION_SCOPE_SUBSTANTIALLY_COMPLETE
OFFLINE_AND_SIDECAR_CERTIFICATION_PENDING_FINAL_HEAD_CI
REAL_SESSION_CERTIFICATION_NOT_YET_AVAILABLE
PAPER_SHADOW_ONLY
NO_LIVE_ORDER_AUTHORITY
KEEP_DRAFT
```

mode: RESEARCH_AND_OBSERVATION
candidate_id: AIXION_TRADE_INTELLIGENCE_V1
decision: CONTINUE_DRAFT_VALIDATION
reason: Code and deterministic test coverage exist, but empirical gates require real future sessions and cannot be truthfully pre-certified.
timestamp: 2026-08-05T01:18:00+05:30
is_order_action: false
broker_api_called: false
source: agent

# Regime Robustness V1

mode: REVIEW
candidate_id: REGIME-ROBUSTNESS-V1
decision: IMPLEMENT_DRAFT_PR
reason: Repair regime probability construction, entropy interpretation, strategy routing, and runtime evidence propagation without modifying feed or execution paths.
timestamp: 2026-07-30T22:04:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/regime_robustness_v1.md

## Agent Work Contract

- source_agent: ChatGPT GPT-5.6 Thinking
- action: IMPLEMENT_AND_CERTIFY_REGIME_ROBUSTNESS_V1
- title: Build structurally discriminative regime truth with canonical strategy routing
- scope: probability construction, entropy truth, model provenance, regime-policy routing, snapshot-to-candidate evidence propagation, deterministic stabilization, tests, and certification evidence
- requested_paths:
  - core/regime_contract_v2.py
  - core/regime_prob_model.py
  - core/regime_entropy_gate.py
  - core/strategy_regime_policy.py
  - core/opportunity_scoring.py
  - core/runtime_snapshot_producer.py
  - strategies/movement/_utils.py
  - tests/test_regime_robustness_v1.py
  - tests/test_strategy_regime_policy_v2.py
  - tests/test_strategy_regime_policy_scoring_v2.py
  - tests/test_regime_policy_context_propagation_v1.py
  - scripts/certify_regime_robustness_v1.py
  - scripts/certify_strategy_regime_policy_v2.py
  - docs/engineering/regime_robustness_v1.md
  - docs/agent_reviews/regime_robustness_v1.md
- allowed_paths:
  - core/regime_contract_v2.py
  - core/regime_prob_model.py
  - core/regime_entropy_gate.py
  - core/strategy_regime_policy.py
  - core/opportunity_scoring.py
  - core/runtime_snapshot_producer.py
  - strategies/movement/_utils.py
  - tests/test_regime_robustness_v1.py
  - tests/test_strategy_regime_policy_v2.py
  - tests/test_strategy_regime_policy_scoring_v2.py
  - tests/test_regime_policy_context_propagation_v1.py
  - scripts/certify_regime_robustness_v1.py
  - scripts/certify_strategy_regime_policy_v2.py
  - docs/engineering/regime_robustness_v1.md
  - docs/agent_reviews/regime_robustness_v1.md
- forbidden_paths:
  - core/kite_depth_ws.py
  - core/feed/*
  - core/tick_store.py
  - core/depth_store.py
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - run_live.sh
- expected_tests:
  - tests/test_regime_robustness_v1.py
  - tests/test_strategy_regime_policy_v2.py
  - tests/test_strategy_regime_policy_scoring_v2.py
  - tests/test_regime_policy_context_propagation_v1.py
  - existing entropy, regime, scoring, ranking, strategy-gate, and candidate-flow tests
  - both deterministic certification runners
- acceptance_proof:
  - unbounded OI cannot dominate regime logits
  - absent or invalid evidence fails closed as UNKNOWN
  - rounded probability vectors are accepted only within the existing 1e-5 contract
  - unexpected non-zero regime labels fail closed
  - raw unscaled slope and acceleration do not create cross-symbol bias
  - low entropy with valid evidence is not rejected
  - clear structural scenarios separate while mixed evidence remains uncertain
  - model calibration and provenance are explicit
  - trained-model schemas fail closed when incomplete
  - actual movement IDs resolve to canonical policy families
  - unknown strategies cannot inherit executable scorer buckets
  - snapshot regime truth reaches StrategyContext, candidate evidence, and scoring policy
  - existing metadata, evidence, and lineage remain preserved
  - feed and execution files remain untouched

## Principal Verdict

`DETERMINISTIC_IMPLEMENTATION_READY_LIVE_CERTIFICATION_PENDING`

## Root Cause

The previous path mixed bounded indicators with unbounded OI, treated absent evidence as meaningful zero, produced near-uniform distributions for clear inputs, used cross-symbol point features, and failed to connect actual strategy IDs and runtime regime truth consistently to scoring policy.

## Implementation

1. Added bounded, validated feature and probability contracts.
2. Replaced additive score pile-up with structural supports for TREND, RANGE, RANGE_VOLATILE, EVENT, and PANIC.
3. Missing or invalid evidence returns uniform probabilities, UNKNOWN, and explicit fail-closed status.
4. Raw point slope and acceleration are ignored until ATR-normalized inputs exist.
5. Model source, hash, errors, feature schema, probability semantics, and calibration status are exposed.
6. Entropy interpretation is centralized; low entropy is not a defect by itself.
7. Legacy raw-only overrides remain compatible, while probability-vector decisions cannot use circular label overrides.
8. Real movement IDs and legacy session names map to canonical policy families and buckets.
9. Session, entropy, stability, trend-confirmation, liquidity, event, no-trade, and unknown-strategy requirements are enforced.
10. Unknown strategies are advisory or blocked and cannot inherit executable scorer state.
11. Existing snapshot truth flows through StrategyContext metadata and candidate evidence into scoring policy without new feed reads.
12. Existing metadata, evidence, lineage, and strict boolean semantics are preserved.

## Scope Guard

In scope: regime truth, model provenance, strategy-policy routing, read-only evidence propagation, deterministic stabilization, tests, and certification.

Out of scope: feed recovery, subscriptions, tick/depth persistence, broker/order/execution/risk logic, strategy formulas, profitability, statistical calibration, and live stabilizer authority.

## High-Risk Path Review

High-risk changed paths:

- `strategies/movement/_utils.py`: candidate evidence construction is changed only to merge existing read-only regime-policy context when present. Strategy-specific evidence retains precedence through `setdefault`. Strategy formulas, signals, entries, stops, targets, and broker behavior are unchanged.
- `core/opportunity_scoring.py`: policy context extraction and downgrade behavior change. This can downgrade candidates to advisory or suppressed; it cannot upgrade a blocked candidate or bypass feed, risk, promotion, or hard-downgrade truth.
- `core/runtime_snapshot_producer.py`: existing regime fields are copied into StrategyContext metadata. No WebSocket, subscription, broker, or network call is added. Existing metadata, evidence, and lineage are preserved.
- `core/strategy_regime_policy.py`: canonical routing authority changes. Unknown, invalid, incompatible-session, and unsupported states are made more conservative, not less.

Primary risks and controls:

1. **Candidate starvation risk:** clear structural scenarios are tested separately from mixed uncertainty; market-hours shadow proof remains required.
2. **False promotion risk:** unknown strategies are explicitly advisory or blocked, and scorer integration proves they cannot inherit executable state.
3. **Feed regression risk:** no feed or subscription file is changed; runtime propagation reads only the already-built snapshot.
4. **Compatibility risk:** legacy raw-only entropy overrides, session aliases, `REGIMES`, `_softmax`, StrategyContext metadata/evidence/lineage, and six-decimal vectors are preserved.
5. **Rollback:** revert this branch/PR; PR #750 and `main` are untouched. The draft remains unmerged.

Verdict: high-risk paths are bounded and fail-closed, but market-hours acceptance is still mandatory.

## Grill Me Review

- Thresholds were not simply widened; evidence construction and routing contracts changed.
- The heuristic is explicitly `HEURISTIC_STRUCTURAL_V2_UNCALIBRATED`; no probability-calibration claim is made.
- Classification may change, but downstream feed, risk, broker, execution, and promotion gates remain authoritative.
- The stabilizer is implemented but not live-authoritative.

## Hermes Review

Existing model entry points remain. Uncertainty ownership is centralized. Actual strategy IDs resolve through a versioned policy. StrategyContext contracts are preserved. No feed module imports the new contract and no broker/order dependency is introduced.

## GSD Review

Completed: probability and entropy repair, canonical routing, scorer downgrade, snapshot-to-candidate propagation, 45 focused tests, 26 certification checks, draft PR, and feed-isolation evidence.

Remaining: final CI, market-hours comparison, current-cycle transition-rate timing repair, ATR-normalized slope/acceleration wiring, and separate stabilizer promotion.

## QA / Safety Review

- is_order_action: false
- broker_api_called: false
- feed_files_modified: false
- tick_store_modified: false
- depth_store_modified: false
- risk_files_modified: false
- execution_files_modified: false
- probability_authority_changed_on_branch: true
- strategy_policy_authority_changed_on_branch: true
- probability_calibrated: false
- stabilizer_authority_enabled: false
- live_market_certified: false
- predictive_edge_certified: false

Fail-closed invariants include missing/invalid evidence, incomplete model schemas, invalid vectors, mixed structural uncertainty, unknown strategy downgrade, invalid propagated regime downgrade, duplicate-bar suppression, and no legacy override for real probability vectors.

## Acceptance Proof

```bash
PYTHONPATH=. pytest -q \
  tests/test_regime_robustness_v1.py \
  tests/test_strategy_regime_policy_v2.py \
  tests/test_strategy_regime_policy_scoring_v2.py \
  tests/test_regime_policy_context_propagation_v1.py

PYTHONPATH=. python scripts/certify_regime_robustness_v1.py
PYTHONPATH=. python scripts/certify_strategy_regime_policy_v2.py
```

The focused suite contains 45 tests and the runners contain 26 checks. Final pass results must come from CI on the current head. Broad repository, security, governance, and market-hours proof remain required.

## Runtime Proof Required After Merge

Do not merge before runtime proof. A market-hours run must cover NIFTY, BANKNIFTY, and SENSEX; expose provenance, feature quality, entropy, margin, and routing; show no feed/orchestrator regression; keep invalid and unknown states non-executable; and leave the stabilizer non-authoritative.

## What This PR Does Not Prove

It does not prove predictive edge, statistical calibration, profitability, market-hours acceptance, PR #750 correctness, or authorization to merge or place live orders.

## Human Approval

The user approved isolated implementation and certification work. That does not authorize merge, live orders, or stabilizer promotion.

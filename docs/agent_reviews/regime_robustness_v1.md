# Regime Robustness V1

mode: REVIEW
candidate_id: REGIME-ROBUSTNESS-V1
decision: IMPLEMENT_DRAFT_PR
reason: Repair regime probability construction, entropy interpretation, canonical strategy routing, scorer policy authority, and runtime evidence propagation without modifying feed or execution paths.
timestamp: 2026-07-30T23:58:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/regime_robustness_v1.md

## Agent Work Contract

- source_agent: ChatGPT GPT-5.6 Thinking
- action: IMPLEMENT_AND_CERTIFY_REGIME_ROBUSTNESS_V1
- title: Build structurally discriminative regime truth with canonical and backward-compatible scoring authority
- scope: probability construction, entropy truth, model provenance, regime-policy routing, runtime evidence propagation, scorer policy authority, deterministic stabilization, tests, and certification evidence
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
  - existing entropy, regime, scorer, ranking, strategy-gate, and candidate-flow tests
  - both deterministic certification runners

## Principal Verdict

`DETERMINISTIC_IMPLEMENTATION_READY_LIVE_CERTIFICATION_PENDING`

Do not merge as live-certified. Repository tests and governance must pass on the final head, followed by market-hours shadow validation.

## Root Causes Repaired

1. Raw OI was mixed with normalized features and could dominate the heuristic distribution.
2. Missing evidence could become numerical zero and fabricate RANGE confidence.
3. Positive score accumulation produced near-uniform probabilities and persistent high entropy.
4. Raw point-based slope and acceleration were not comparable across NIFTY, BANKNIFTY, and SENSEX.
5. Real movement strategy IDs and legacy session names were not consistently mapped to the strategy policy.
6. Runtime regime truth was not reliably propagated into candidate scoring.
7. Applying regime policy unconditionally broke generic scorer-only contracts that contain neither a runtime strategy nor regime evidence.

## Implementation Summary

- bounded and normalized feature inputs;
- explicit missing and invalid feature states;
- structurally discriminative TREND, RANGE, RANGE_VOLATILE, EVENT, and PANIC supports;
- canonical probability-vector validation and entropy diagnostics;
- explicit uncalibrated heuristic provenance;
- trained-model feature-schema enforcement;
- canonical strategy and session aliases;
- strategy-specific entropy, stability, trend, liquidity, event, and no-trade policy;
- snapshot to StrategyContext to candidate to scorer regime-evidence propagation;
- conditional scorer policy authority:
  - canonical strategies are governed;
  - movement-strategy lineage is governed, including unknown future IDs;
  - explicit regime evidence is governed;
  - generic scorer-only fixtures with none of those signals retain the previous scorer contract;
- completed-bar stabilizer with duplicate suppression, confirmation, dwell, and bounded EVENT/PANIC fast path;
- stabilizer remains non-authoritative.

## High-Risk Path Review

High-risk files changed:

- `core/runtime_snapshot_producer.py`
- `core/opportunity_scoring.py`
- `core/strategy_regime_policy.py`
- `strategies/movement/_utils.py`

Risks and controls:

1. **Runtime snapshot propagation risk**
   - Risk: existing metadata, evidence, or lineage could be overwritten.
   - Control: merge-only propagation and regression tests preserve existing fields and strict boolean semantics.

2. **Scorer authority risk**
   - Risk: unknown runtime strategies could inherit executable state, or generic scorer fixtures could be falsely downgraded.
   - Control: policy authority requires a canonical strategy, movement lineage, or explicit regime evidence. Unknown movement candidates remain advisory; generic scorer-only candidates retain compatibility.

3. **Strategy routing risk**
   - Risk: real strategy IDs could fall into unknown-policy behavior.
   - Control: aliases cover the current movement registry and the strategy-registry CI gate remains mandatory.

4. **Candidate evidence risk**
   - Risk: strategy helpers could fabricate Phase-2 execution truth.
   - Control: only regime-policy context is merged; option confirmation, liquidity, freshness, broker, and execution truth ownership is unchanged.

5. **Rollback boundary**
   - Revert this isolated PR. No feed, subscription, broker, order, execution, risk, tick-store, depth-store, or launcher file is changed.

## Fail-Closed Invariants

- missing required regime feature -> `INSUFFICIENT_DATA` and `UNKNOWN`;
- invalid required regime feature -> `INVALID_INPUT` and `UNKNOWN`;
- incomplete trained-model schema -> fail closed;
- malformed or unexpected probability vector -> uncertain and blocked;
- mixed structural evidence -> high entropy;
- low entropy alone -> not blocked when feature truth is valid;
- unknown strategy with explicit context -> advisory or blocked, never executable;
- unknown movement-strategy lineage without regime context -> advisory;
- invalid propagated regime truth -> scorer advisory downgrade;
- generic scorer-only fixture without canonical strategy, movement lineage, or regime evidence -> existing scorer contract retained;
- duplicate completed bar -> no transition confirmation advancement;
- probability-vector decision -> no legacy label-based entropy bypass.

## Deterministic Evidence

Focused suite: 47 tests across four files.

```bash
PYTHONPATH=. pytest -q \
  tests/test_regime_robustness_v1.py \
  tests/test_strategy_regime_policy_v2.py \
  tests/test_strategy_regime_policy_scoring_v2.py \
  tests/test_regime_policy_context_propagation_v1.py
```

Certification runners: 26 checks.

```bash
PYTHONPATH=. python scripts/certify_regime_robustness_v1.py
PYTHONPATH=. python scripts/certify_strategy_regime_policy_v2.py
```

Final pass counts must come from CI on the final commit SHA.

## Safety Truth

- is_order_action: false
- broker_api_called: false
- feed_files_modified: false
- tick_store_modified: false
- depth_store_modified: false
- risk_files_modified: false
- execution_files_modified: false
- probability_authority_changed_on_branch: true
- strategy_policy_authority_changed_on_branch: true
- stabilizer_authority_enabled: false
- probability_calibrated: false
- predictive_edge_certified: false
- live_market_certified: false

## Tomorrow's Live Proof

Market-hours shadow validation must cover NIFTY, BANKNIFTY, and SENSEX and verify:

1. feed callback latency and orchestrator cadence do not regress;
2. model source, probability semantics, feature quality, entropy threshold, and top-two margin are visible;
3. missing or invalid evidence never becomes confident RANGE;
4. clear structural scenarios do not remain permanently high entropy;
5. actual strategy IDs resolve to intended policy families;
6. unknown and invalid policy states remain non-executable;
7. candidate starvation changes only when evidence quality genuinely improves;
8. the stabilizer remains shadow-only unless separately approved.

## What This PR Does Not Prove

- predictive edge;
- statistical calibration;
- profitability;
- market-hours operational acceptance;
- PR #750 feed certification;
- authorization to merge;
- authorization to place live orders.

## Human Approval

The user approved isolated implementation and deterministic certification work. That approval does not authorize merge, live orders, or live authority for the completed-bar stabilizer.

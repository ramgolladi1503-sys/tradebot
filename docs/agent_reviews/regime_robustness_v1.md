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
  - absent or invalid required evidence fails closed as UNKNOWN
  - rounded probability vectors are accepted only within the existing 1e-5 contract
  - unexpected non-zero regime labels fail closed
  - raw unscaled VWAP slope and acceleration do not create cross-symbol bias
  - low entropy with valid evidence is not rejected
  - clear structural scenarios separate while mixed evidence remains uncertain
  - model calibration and provenance are explicit
  - trained-model schemas fail closed when incomplete
  - actual movement strategy IDs resolve to canonical policy families
  - legacy session aliases resolve to canonical session buckets
  - unknown strategies cannot inherit executable scorer buckets
  - market snapshot regime truth reaches StrategyContext, candidate evidence, and scoring policy
  - existing snapshot metadata, evidence, and lineage remain preserved
  - feed and execution files remain untouched

## Principal Verdict

`DETERMINISTIC_IMPLEMENTATION_READY_LIVE_CERTIFICATION_PENDING`

## Root Cause

The previous regime path had four independent failure classes:

1. bounded indicators were mixed with unbounded raw OI;
2. absent evidence became numerical zero and could reward RANGE;
3. positive score accumulation produced near-uniform distributions and persistent high entropy even for clear structural inputs;
4. actual strategy IDs and runtime regime evidence were not consistently connected to the strategy-policy scorer, so real candidates could enter unknown or incomplete policy paths.

Raw VWAP slope and acceleration were also cross-symbol point values, not comparable dimensionless features.

## Implementation

1. Added finite-number validation, OI bounding, IV normalization, full-precision softmax, vector validation, feature-quality states, and completed-bar stabilization.
2. Replaced additive score pile-up with bounded structural supports for TREND, RANGE, RANGE_VOLATILE, EVENT, and PANIC.
3. Clear evidence separates; mixed evidence deliberately stays high entropy and fail-closed.
4. Raw slope and acceleration are ignored until ATR-normalized forms are supplied.
5. Missing or invalid core evidence returns uniform probabilities, UNKNOWN, and explicit status.
6. Model source, hash, load/inference errors, feature schema, probability semantics, and calibration status are exposed.
7. Entropy interpretation is centralized; low entropy is not a defect by itself.
8. Legacy raw-only TREND/RANGE overrides remain compatible, while probability-vector decisions cannot use those circular overrides.
9. Real movement strategy IDs and legacy session names are mapped to canonical policy families and session buckets.
10. Policy requirements for session, entropy, stable-regime status, trend confirmation, liquidity, event handling, no-trade, and unknown strategies are enforced.
11. Unknown strategies resolve to ADVISORY_ONLY or BLOCKED and cannot inherit executable scorer state.
12. Existing snapshot regime truth is preserved in StrategyContext metadata, merged into candidate evidence, and consumed by scoring policy without new feed reads or network calls.
13. Existing snapshot metadata, evidence, lineage, and strict boolean semantics are preserved.

## Scope Guard

In scope:

- regime probability and entropy truth;
- model provenance and feature-quality contracts;
- strategy-policy aliases and routing;
- read-only snapshot-to-candidate-to-scorer evidence propagation;
- deterministic stabilization and certification.

Out of scope:

- WebSocket/feed recovery and subscription state;
- tick/depth persistence;
- broker, order, execution, and risk logic;
- strategy formula changes and profitability claims;
- live authority for the completed-bar stabilizer;
- statistical calibration and predictive-edge certification.

## Grill Me Review

**Does this merely loosen entropy thresholds?**

No. Session thresholds remain. The repair changes evidence validity, probability construction, and routing contracts.

**Could the heuristic overstate confidence?**

Its source is explicitly `HEURISTIC_STRUCTURAL_V2_UNCALIBRATED`; output semantics are `deterministic_structural_pseudo_probability`. No statistical calibration claim is made.

**Could this create more trades?**

It can change regime classifications and policy routing on this branch. It cannot bypass downstream feed, risk, broker, or execution gates. Missing, invalid, unknown, and incompatible states are explicitly downgraded or blocked.

**Could unknown strategies become executable?**

No. Policy returns ADVISORY_ONLY for low/normal unknown strategies and BLOCKED for high/extreme unknown strategies; scorer integration tests prove executable upstream buckets are downgraded.

**Is the stabilizer live-authoritative?**

No. It is implemented and tested but not wired as live routing authority.

## Hermes Review

Contract findings:

- existing `RegimeProbModel`, `REGIMES`, and `_softmax` entry points remain;
- uncertainty ownership is centralized;
- actual movement IDs resolve through a versioned canonical policy;
- existing StrategyContext metadata/evidence/lineage are preserved;
- no feed module imports the new contract;
- no broker or order dependency is introduced;
- incomplete model schemas and invalid probability vectors fail closed;
- read-only regime evidence reaches the scorer without additional feed calls.

Verdict: repository architecture remains isolated from feed and execution paths; live integration proof is still required.

## GSD Review

Completed:

- bounded, discriminative regime contract;
- probability-model and entropy-gate repair;
- model provenance and schema enforcement;
- canonical strategy/session routing policy;
- scorer downgrade for unknown and invalid regime truth;
- runtime snapshot to StrategyContext to candidate to scorer evidence propagation;
- 45 focused deterministic tests across four files;
- 26 independent certification checks across two runners;
- draft PR and evidence documentation;
- feed-path isolation verification;
- legacy compatibility repair after an earlier broad-CI failure.

Remaining:

- final broad CI on the current head;
- market-hours comparison;
- transition-rate timing repair in `core/market_data.py`;
- ATR-normalized slope and acceleration wiring;
- separate stabilizer-authority decision.

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

Fail-closed invariants:

- absent required feature -> INSUFFICIENT_DATA and UNKNOWN;
- invalid required feature -> INVALID_INPUT and UNKNOWN;
- incomplete trained-model schema -> fail closed;
- invalid or unexpected probability vector -> uncertain and blocked;
- low entropy alone -> not blocked;
- mixed structural evidence -> high entropy;
- unknown strategy -> advisory or blocked, never executable;
- invalid propagated regime truth -> scorer advisory downgrade;
- duplicate completed bar -> no transition-count advancement;
- probability-vector decision -> no legacy label-based override.

## Acceptance Proof

Focused deterministic suite:

```bash
PYTHONPATH=. pytest -q \
  tests/test_regime_robustness_v1.py \
  tests/test_strategy_regime_policy_v2.py \
  tests/test_strategy_regime_policy_scoring_v2.py \
  tests/test_regime_policy_context_propagation_v1.py
```

Certification runners:

```bash
PYTHONPATH=. python scripts/certify_regime_robustness_v1.py
PYTHONPATH=. python scripts/certify_strategy_regime_policy_v2.py
```

The focused suite contains 45 tests and the runners contain 26 checks. Final pass results must come from CI on the current branch head.

Required broad proof:

- all repository CI and security/governance checks pass;
- existing entropy/regime/scoring/ranking/candidate tests pass;
- no forbidden path appears in the diff;
- market-hours comparison shows no feed or orchestrator regression.

## Runtime Proof Required After Merge

This branch should not be merged before runtime proof. A market-hours run must cover NIFTY, BANKNIFTY, and SENSEX and verify:

1. model provenance, probability semantics, feature quality, entropy threshold, and top-two margin are visible;
2. missing evidence never becomes confident RANGE;
3. no generic entropy-too-low rejection exists;
4. clear structural conditions do not remain permanently high entropy;
5. strategy IDs resolve to intended policy families;
6. invalid and unknown policy states remain non-executable;
7. feed callback latency, registry truth, and orchestrator cadence are unchanged;
8. candidate starvation changes only when evidence quality genuinely improves;
9. the stabilizer remains non-authoritative unless separately approved.

## What This PR Does Not Prove

- It does not prove predictive edge.
- It does not prove statistical calibration.
- It does not prove market-hours operational acceptance.
- It does not certify PR #750 or any feed repair.
- It does not authorize live orders.
- It does not authorize merge.

## Human Approval

The user explicitly approved implementation work and requested certified evidence. That approval covers this isolated branch and draft PR. It does not authorize merging, enabling live orders, or promoting the completed-bar stabilizer.

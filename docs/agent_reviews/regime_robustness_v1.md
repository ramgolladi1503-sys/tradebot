# Regime Robustness V1

## Agent Work Contract

- source_agent: ChatGPT GPT-5.6 Thinking
- action: IMPLEMENT_AND_CERTIFY_REGIME_ROBUSTNESS_V1
- title: Bound regime probability evidence and correct entropy semantics
- scope: regime probability construction, entropy truth, deterministic transition stabilization, tests, certification evidence
- requested_paths:
  - core/regime_contract_v2.py
  - core/regime_prob_model.py
  - core/regime_entropy_gate.py
  - tests/test_regime_robustness_v1.py
  - scripts/certify_regime_robustness_v1.py
  - docs/engineering/regime_robustness_v1.md
  - docs/agent_reviews/regime_robustness_v1.md
- allowed_paths:
  - core/regime_contract_v2.py
  - core/regime_prob_model.py
  - core/regime_entropy_gate.py
  - tests/test_regime_robustness_v1.py
  - scripts/certify_regime_robustness_v1.py
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
  - existing entropy, regime, strategy-gate, and candidate-flow tests
  - deterministic certification runner
- acceptance_proof:
  - raw OI is mathematically bounded and cannot dominate softmax
  - missing required features fail closed as UNKNOWN
  - non-positive ATR percentage is invalid input
  - IV percentage and decimal scales normalize consistently
  - probability vectors remain full precision and sum to one
  - low entropy with valid evidence is not rejected
  - invalid probability vectors fail closed
  - duplicate completed bars do not advance transition confirmation
  - standard transitions require consecutive completed bars
  - feed and execution files remain untouched

## Principal Verdict

`DETERMINISTIC_IMPLEMENTATION_READY_LIVE_CERTIFICATION_PENDING`

## Root Cause

The previous heuristic mixed bounded normalized indicators with unbounded raw OI. Missing evidence could also collapse to numerical zero, which actively rewarded RANGE scoring. This could produce both artificial low entropy and persistent high-entropy uncertainty without making feature quality explicit.

## Implementation

1. Added a pure regime contract with finite-number validation, OI bounding, IV normalization, full-precision softmax, probability diagnostics, entropy-state classification, feature-quality states, and completed-bar stabilization.
2. Reworked the heuristic model to use bounded evidence and uniform fail-closed probabilities when required inputs are absent or invalid.
3. Added model provenance including source, path, hash, load error, inference error, and ignored inputs.
4. Delegated uncertainty interpretation to the canonical entropy gate.
5. Removed low entropy as an automatic blocker. Low entropy is suspicious only when paired with invalid or insufficient feature truth.
6. Preserved a legacy raw-entropy RANGE compatibility path only for callers without a probability vector. Real probability-vector decisions do not relax entropy based on their own predicted label.

## High-Risk Review

Files affecting regime decisions were changed, so this branch must remain draft until broad CI and market-hours validation pass.

The probability model and entropy gate are authoritative when this branch is run. The completed-bar stabilizer is implemented but is not wired as live routing authority. Missing or malformed required evidence yields `UNKNOWN` and unstable status. Invalid probability vectors remain blocked.

## Feed Isolation Proof

The compare scope contains only:

- `core/regime_contract_v2.py`
- `core/regime_prob_model.py`
- `core/regime_entropy_gate.py`
- regime tests, certification script, and documentation

No WebSocket, subscription, tick-store, depth-store, broker, order, execution, risk, or launcher path is modified.

## Deterministic Evidence

Local focused test result:

```text
9 passed
```

Local certification result:

```text
DETERMINISTIC_CERTIFIED 6/6
```

Required repository commands:

```bash
PYTHONPATH=. pytest -q tests/test_regime_robustness_v1.py
PYTHONPATH=. python scripts/certify_regime_robustness_v1.py
```

## Safety Flags

- read_only_certification: true
- is_order_action: false
- broker_api_called: false
- feed_files_modified: false
- probability_authority_changed_on_branch: true
- stabilizer_authority_enabled: false
- live_market_certified: false

## Runtime Proof Required

Before merge, run a market-hours comparison covering NIFTY, BANKNIFTY, and SENSEX. Confirm model provenance and feature-quality evidence are present, missing inputs fail closed, no generic low-entropy rejection appears, feed latency is unchanged, and candidate starvation changes only when evidence quality improves.

The completed-bar stabilizer must remain non-authoritative until that comparison is sealed.

## What This Does Not Prove

- It does not prove predictive edge.
- It does not prove historical calibration.
- It does not prove live operational acceptance.
- It does not certify the feed-recovery PR.
- It does not authorize merge or live execution.

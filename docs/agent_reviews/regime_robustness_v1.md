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

The previous heuristic mixed bounded normalized indicators with unbounded raw OI. Missing evidence could also collapse to numerical zero, which actively rewarded RANGE scoring. This could create artificial low entropy or persistent high-entropy uncertainty without exposing feature quality.

## Implementation

1. Added finite-number validation, bounded OI, IV scale normalization, full-precision softmax, probability diagnostics, entropy-state classification, feature-quality states, and completed-bar stabilization.
2. Reworked the heuristic model so absent or invalid required inputs produce uniform probabilities, `UNKNOWN`, and fail-closed status rather than fake RANGE confidence.
3. Added model provenance: source, path, SHA-256, load error, inference error, and ignored features.
4. Delegated uncertainty interpretation to the canonical entropy gate.
5. Removed low entropy as an automatic blocker. Low entropy is suspicious only when paired with invalid or insufficient feature truth.
6. Preserved legacy raw-entropy RANGE compatibility only for callers that do not supply a probability vector. Real probability-vector decisions do not relax uncertainty using their own predicted label.

## Scope Guard

In scope:

- probability construction;
- entropy interpretation;
- feature-quality truth;
- deterministic transition-stabilizer implementation;
- focused tests and certification evidence.

Out of scope:

- WebSocket/feed recovery;
- subscriptions, tick persistence, and depth persistence;
- broker, order, execution, and risk logic;
- strategy formulas and profitability claims;
- live authority for the new completed-bar stabilizer.

The branch diff is limited to regime modules, tests, certification script, and documentation.

## Grill Me Review

**Could this silently create more trades?**

It can change regime classifications when this branch is run because the probability model and entropy gate are authoritative. It cannot bypass downstream feed, risk, broker, or execution gates. Missing and invalid evidence now blocks more explicitly.

**Did the implementation merely widen thresholds?**

No. Session thresholds remain. The repair changes feature truth and probability construction. The only RANGE override retained is the legacy raw-entropy-only compatibility path.

**Could low entropy now pass unsafe data?**

No. Low entropy passes only when feature-quality status is valid. Invalid or insufficient feature quality remains uncertain and fail-closed.

**Is the stabilizer already affecting live routing?**

No. It is implemented and tested but not wired as live authority.

## Hermes Review

Contract and architecture findings:

- `RegimeProbModel` remains the existing model entry point.
- `REGIMES` remains exported for backward compatibility.
- `_softmax` remains exported for backward compatibility.
- uncertainty interpretation is centralized in `evaluate_regime_entropy_gate`;
- no feed module imports the new regime contract;
- no new broker or order dependency exists;
- invalid inputs produce explicit status instead of invented values.

Verdict: architecture-compatible, with market-hours validation required because authoritative regime output changes on this branch.

## GSD Review

Delivery completed:

- bounded probability contract added;
- probability model repaired;
- entropy gate repaired;
- focused regression tests added;
- deterministic certification runner added;
- engineering and agent-review evidence added;
- draft PR opened;
- feed-isolation diff verified.

Remaining work:

- broad CI completion;
- market-hours runtime comparison;
- separate decision on whether to promote the completed-bar stabilizer.

## QA / Safety Review

- is_order_action: false
- broker_api_called: false
- feed_files_modified: false
- risk_files_modified: false
- execution_files_modified: false
- probability_authority_changed_on_branch: true
- stabilizer_authority_enabled: false
- live_market_certified: false

Fail-closed invariants:

- missing required feature -> `INSUFFICIENT_DATA` and `UNKNOWN`;
- invalid required feature -> `INVALID_INPUT` and `UNKNOWN`;
- invalid probability vector -> uncertain and blocked;
- impossible entropy -> uncertain and blocked;
- low entropy alone -> not blocked;
- duplicate completed bar -> no transition-count advancement.

## Acceptance Proof

Local focused test result:

```text
9 passed
```

Local deterministic certification result:

```text
DETERMINISTIC_CERTIFIED 6/6
```

Required repository commands:

```bash
PYTHONPATH=. pytest -q tests/test_regime_robustness_v1.py
PYTHONPATH=. python scripts/certify_regime_robustness_v1.py
```

Required broad proof:

- repository CI passes;
- existing entropy/regime/candidate tests pass;
- no forbidden path appears in the diff;
- market-hours comparison shows no feed or orchestrator regression.

## Runtime Proof Required After Merge

This branch should not be merged before the runtime proof, but if merged later the first market-hours run must capture NIFTY, BANKNIFTY, and SENSEX and verify:

1. model provenance and feature-quality fields are present;
2. missing evidence never becomes confident RANGE;
3. no generic `entropy_too_low` rejection exists;
4. high-entropy evidence includes probabilities, normalized entropy, threshold, top-two margin, and feature-quality status;
5. feed callback latency, subscription truth, and orchestrator cadence are unchanged;
6. candidate starvation changes only when evidence quality genuinely improves;
7. the stabilizer remains non-authoritative unless separately approved.

## What This PR Does Not Prove

- It does not prove predictive edge.
- It does not prove historical calibration.
- It does not prove live operational acceptance.
- It does not certify PR #750 or any feed repair.
- It does not authorize live orders.
- It does not authorize merge.

## Human Approval

The user explicitly approved implementation work and asked for a certified implementation. That approval covers creating this isolated branch and draft PR. It does not authorize merging, enabling live orders, or promoting the completed-bar stabilizer to live authority.

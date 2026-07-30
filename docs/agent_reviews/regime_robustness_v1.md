# Regime Robustness V1

mode: REVIEW
candidate_id: REGIME-ROBUSTNESS-V1
decision: IMPLEMENT_DRAFT_PR
reason: Repair regime probability construction and entropy semantics without touching feed or execution paths.
timestamp: 2026-07-30T22:04:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/regime_robustness_v1.md

## Agent Work Contract

- source_agent: ChatGPT GPT-5.6 Thinking
- action: IMPLEMENT_AND_CERTIFY_REGIME_ROBUSTNESS_V1
- title: Build structurally discriminative regime truth with explicit uncertainty
- scope: regime probability construction, entropy truth, model provenance, deterministic transition stabilization, tests, certification evidence
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
  - raw OI is bounded and cannot dominate logits
  - absent required features fail closed as UNKNOWN
  - non-positive ATR percentage is invalid input
  - IV percentage and decimal scales normalize consistently
  - rounded vectors are accepted only within the existing 1e-5 contract
  - unexpected non-zero regime labels fail closed
  - raw unscaled VWAP slope and acceleration do not create cross-symbol bias
  - low entropy with valid evidence is not rejected
  - invalid probability vectors fail closed
  - legacy raw-only entropy overrides remain compatible
  - probability-vector decisions cannot use legacy label overrides
  - clear structural scenarios separate from mixed conditions
  - model calibration and provenance are explicit
  - trained-model feature schemas fail closed when incomplete
  - duplicate completed bars do not advance transition confirmation
  - feed and execution files remain untouched

## Principal Verdict

`DETERMINISTIC_IMPLEMENTATION_READY_LIVE_CERTIFICATION_PENDING`

## Root Cause

The prior heuristic had three fundamental defects:

1. bounded indicators were mixed with unbounded raw OI;
2. absent evidence became numerical zero and could reward RANGE;
3. all regime scores accumulated positive baselines, producing near-uniform distributions and persistent high entropy even for structurally clear inputs.

Raw VWAP slope and raw acceleration were also compared across NIFTY, BANKNIFTY, and SENSEX despite using non-comparable point units.

## Implementation

1. Added finite-number validation, OI bounding, IV normalization, full-precision softmax, probability diagnostics, feature-quality states, and completed-bar stabilization.
2. Replaced positive score pile-up with bounded discriminative structural supports for TREND, RANGE, RANGE_VOLATILE, EVENT, and PANIC.
3. Required clear evidence to separate while deliberately leaving mixed evidence high entropy.
4. Ignored raw VWAP slope and raw acceleration unless ATR-normalized forms are provided.
5. Returned uniform probabilities plus `UNKNOWN` for absent or invalid required evidence.
6. Rejected unexpected non-zero probability labels.
7. Accepted historical six-decimal vectors only inside `1e-5`, then renormalized.
8. Exposed model source, hash, load/inference errors, feature quality, probability semantics, and calibration status.
9. Enforced declared or inferred feature schemas for JSON Gaussian models.
10. Centralized uncertainty interpretation in the entropy gate.
11. Kept raw-only RANGE/TREND compatibility for legacy callers but prohibited those overrides for real probability vectors.
12. Added a completed-bar stabilizer with duplicate suppression, confirmation bars, dwell, and a high-evidence EVENT/PANIC fast path.

## Scope Guard

In scope:

- regime evidence normalization;
- structural pseudo-probability construction;
- entropy interpretation;
- feature-quality and model-schema truth;
- deterministic stabilizer implementation;
- focused tests and certification evidence.

Out of scope:

- WebSocket/feed recovery;
- subscriptions, tick persistence, and depth persistence;
- broker, order, execution, and risk logic;
- strategy formulas and profitability claims;
- live authority for the completed-bar stabilizer;
- historical probability calibration and predictive-edge certification.

The branch diff is limited to regime modules, tests, certification script, and documentation.

## Grill Me Review

**Does this merely loosen entropy thresholds?**

No. Session thresholds remain. The repair changes the evidence scale and probability construction so clear states separate and mixed states remain uncertain.

**Could the new heuristic overstate confidence?**

Its probabilities are explicitly labelled `HEURISTIC_STRUCTURAL_V2_UNCALIBRATED` and `deterministic_structural_pseudo_probability`. No statistical calibration claim is made.

**Could this silently create more trades?**

It can alter regime classifications on this branch. It cannot bypass downstream feed, risk, broker, or execution gates. Absent and invalid evidence now blocks more explicitly.

**Could low entropy pass unsafe data?**

Low entropy passes only when feature quality is valid. Invalid or insufficient feature quality remains fail-closed.

**Is the stabilizer live-authoritative?**

No. It is implemented and tested but not wired as live routing authority.

## Hermes Review

Contract findings:

- `RegimeProbModel`, `REGIMES`, and `_softmax` remain backward-compatible entry points;
- uncertainty ownership is centralized in `evaluate_regime_entropy_gate`;
- no feed module imports the new contract;
- no broker/order dependency exists;
- invalid model schemas and incomplete features return explicit fail-closed states;
- six-decimal legacy vectors remain compatible without accepting materially invalid sums;
- raw point-based slope/acceleration evidence is excluded until normalized.

Verdict: architecture-compatible at the regime boundary, with live integration proof still required.

## GSD Review

Completed:

- bounded regime contract;
- structurally discriminative heuristic;
- entropy-gate repair;
- model provenance and schema enforcement;
- 20 focused deterministic tests;
- 15-check certification runner;
- engineering and agent-review evidence;
- draft PR creation;
- feed-isolation verification;
- diagnosis and repair of the first broad-CI legacy compatibility failure.

Remaining:

- final broad CI on the current head;
- market-hours comparison;
- transition-rate timing repair in `core/market_data.py`;
- runtime propagation of provenance/feature-quality fields;
- ATR-normalized slope and acceleration wiring;
- separate stabilizer authority decision.

## QA / Safety Review

- is_order_action: false
- broker_api_called: false
- feed_files_modified: false
- risk_files_modified: false
- execution_files_modified: false
- probability_authority_changed_on_branch: true
- probability_calibrated: false
- stabilizer_authority_enabled: false
- live_market_certified: false
- predictive_edge_certified: false

Fail-closed invariants:

- absent required feature -> `INSUFFICIENT_DATA` and `UNKNOWN`;
- invalid required feature -> `INVALID_INPUT` and `UNKNOWN`;
- incomplete trained-model schema -> fail closed;
- invalid or unexpected probability vector -> uncertain and blocked;
- impossible entropy -> uncertain and blocked;
- low entropy alone -> not blocked;
- mixed structural evidence -> high entropy;
- duplicate completed bar -> no transition-count advancement;
- probability-vector decision -> no legacy label-based override.

## Acceptance Proof

The focused suite contains 20 deterministic tests. The certification runner contains 15 independent checks. No final pass count is claimed until CI completes on the current branch head.

Required commands:

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

This branch should not be merged before runtime proof. A market-hours run must capture NIFTY, BANKNIFTY, and SENSEX and verify:

1. model provenance, probability semantics, and feature-quality fields are visible;
2. absent evidence never becomes confident RANGE;
3. no generic `entropy_too_low` rejection exists;
4. high-entropy evidence includes probabilities, normalized entropy, threshold, top-two margin, and feature-quality status;
5. clear structural conditions do not remain permanently high entropy;
6. feed callback latency, subscription truth, and orchestrator cadence are unchanged;
7. candidate starvation changes only when evidence quality genuinely improves;
8. the stabilizer remains non-authoritative unless separately approved.

## What This PR Does Not Prove

- It does not prove predictive edge.
- It does not prove statistical calibration.
- It does not prove live operational acceptance.
- It does not certify PR #750 or any feed repair.
- It does not authorize live orders.
- It does not authorize merge.

## Human Approval

The user explicitly approved implementation work and requested certified evidence. That approval covers this isolated branch and draft PR. It does not authorize merging, enabling live orders, or promoting the completed-bar stabilizer.

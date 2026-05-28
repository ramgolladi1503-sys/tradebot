# Agent Review — EDGE-96 Live-Pilot Risk Throttle

## Agent Work Contract

- pr: PR #321 / EDGE-96 Live-Pilot Risk Throttle
- mode: PAPER
- scope: read-only live-pilot review throttle
- base: PR #358 / EDGE-95 Paper-Only Edge Gate merge commit `048cc2484b1769deb8ac1c559cc5f51749df01e4`
- candidate_id: EDGE-96-LIVE-PILOT-RISK-THROTTLE
- decision: LIVE_PILOT_RISK_THROTTLE_EVIDENCE_ONLY
- reason: READ_ONLY_LIVE_PILOT_REVIEW_THROTTLE
- timestamp: 2026-05-28T06:00:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: core/live_pilot_risk_throttle.py

## Scope Guard

EDGE-96 adds a deterministic read-only throttle that consumes EDGE-95 paper gate evidence and emits live-pilot review decisions.

Included files:

- core/live_pilot_risk_throttle.py
- tests/test_live_pilot_risk_throttle.py
- docs/EDGE_96_LIVE_PILOT_RISK_THROTTLE.md
- docs/agent_reviews/EDGE_96_LIVE_PILOT_RISK_THROTTLE.md
- docs/EDGE_TODO.md

Excluded areas:

- broker adapters
- execution engine
- runtime loop
- dashboard/UI
- strategy generation logic
- ranking logic
- order lifecycle logic
- EDGE-97 work

## Grill Me Review

Question: Does this PR enable live execution?

Answer: No. It emits read-only live-pilot review eligibility and keeps execution boundaries untouched.

Question: Can a non-PAPER candidate pass?

Answer: No. The source paper gate mode must be PAPER and the candidate must be paper-allowed.

Question: Can too many candidates pass through review?

Answer: No. The throttle applies max-candidate and max-per-strategy caps deterministically.

## Hermes Review

The module exports a small stable contract:

- build_live_pilot_risk_throttle_report
- LivePilotRiskThrottleReport
- LivePilotCandidateThrottleDecision
- status and reason constants

Payloads are JSON-friendly dictionaries with deterministic ordering and explicit read-only/non-action fields.

## GSD Review

Purpose: add a review-only throttle above EDGE-95 paper gate evidence.

Scope: pure evidence aggregation and deterministic live-pilot review eligibility reporting.

Files changed:

- core/live_pilot_risk_throttle.py
- tests/test_live_pilot_risk_throttle.py
- docs/EDGE_96_LIVE_PILOT_RISK_THROTTLE.md
- docs/agent_reviews/EDGE_96_LIVE_PILOT_RISK_THROTTLE.md
- docs/EDGE_TODO.md

Tests or rationale: tests are required and included.

Evidence: focused tests cover paper-gate pass and fail-closed throttle paths.

Risks: downstream users must not treat this as live execution readiness. It is review-only evidence.

Next PR: EDGE-97 Final Edge Readiness Report after EDGE-96 merges green.

## QA / Safety Review

Focused tests cover:

- paper gate pass allows one candidate for review
- absent paper gate evidence blocks
- non-PAPER mode blocks
- blocked paper gate evidence blocks
- non-paper candidate blocks
- max-candidate throttle blocks overflow
- max-per-strategy throttle blocks overflow
- symbol filters block unsafe scope
- invalid throttle limits block
- boundary-flag evidence blocks

Recommended command:

```bash
pytest tests/test_live_pilot_risk_throttle.py -q
```

Recommended regression:

```bash
pytest tests/test_paper_only_edge_gate.py tests/test_live_pilot_risk_throttle.py -q
```

## Acceptance Proof

The throttle only allows live-pilot review when:

- paper gate evidence exists
- paper gate status passed
- paper gate mode is PAPER
- candidate is paper-allowed
- candidate stays within configured throttle limits
- symbol filters permit the candidate
- boundary flags are non-action and non-broker

Any absent, blocked, rejected, non-PAPER, cap-overflow, symbol-blocked, invalid-limit, or boundary-flag evidence blocks the candidate.

## Runtime Proof Required After Merge

No runtime proof is required for EDGE-96. This PR is a pure read-only review throttle. Final readiness reporting is deferred to EDGE-97.

## What This PR Does Not Prove

- profitability
- slippage truth
- broker readiness
- live action readiness
- market-session runtime correctness
- dashboard accuracy
- final edge readiness

## Human Approval

Required before merge.

## High-Risk Path Review

High-risk paths intentionally unchanged:

- broker adapters
- execution engine
- runtime loop
- Streamlit dashboard
- strategy generation logic
- ranking logic
- order lifecycle logic

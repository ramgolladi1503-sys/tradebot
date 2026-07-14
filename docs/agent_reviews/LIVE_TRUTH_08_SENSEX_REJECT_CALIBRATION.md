# LIVE-TRUTH-08 SENSEX Reject Calibration Agent Review

mode: REVIEW
candidate_id: live_truth_08_sensex_reject_calibration
decision: review_ready
reason: sensex_reject_calibration_tests_docs
timestamp: 2026-05-27T12:55:00Z
source: live_truth_08_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

LIVE-TRUTH-08 adds read-only evidence for SENSEX reject calibration.

It classifies SENSEX reject patterns as balanced, review, overfiltered, or blocked.

## Scope Guard

In scope:

- SENSEX candidate extraction
- reject reason summary
- reject rate calculation
- dominant reason concentration
- near-miss reject classification
- invalid payload evidence
- evidence writer

Out of scope:

- UI changes
- runtime wiring
- ranking changes
- strategy scoring changes
- lifecycle changes
- feed recovery changes

## Grill Me Review

This PR reports SENSEX reject calibration evidence only and does not change strategy behavior.

## Hermes Review

No external integration, UI change, strategy behavior change, or feed recovery change is added.

## GSD Review

Changed files are limited to one core reducer, one focused test file, docs, agent review evidence, and the roadmap.

## QA / Safety Review

Focused tests cover balanced, review, overfiltered, blocked, container, config, writer, and JSON cases.

## Acceptance Proof

`PYTHONPATH=. python -m pytest tests/test_live_truth_08_sensex_reject_calibration.py`

## Runtime Proof Required After Merge

After merge, this proves only the reducer and evidence writer.

## What This PR Does Not Prove

This PR does not prove later LIVE-TRUTH items.

## Human Approval

Human review is required before broader wiring.

## Next Action

After this PR merges green, continue with LIVE-TRUTH-09.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false

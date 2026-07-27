# Option E2E v4.6 Dormant Source Confusion Invalidation

mode: RESEARCH_ONLY_SUPERSESSION
candidate_id: option_e2e_v4_6_dormant_source_confusion_invalidation
decision: INVALID_DORMANT_OPTION_METADATA_AS_SIGNAL_SOURCE_PATH
reason: The v4.6 checkpoint still allowed option metadata and dated authority artifacts to sit on the strategy signal-source path, even though the oracle later rejected the fabricated row. The source-domain model was still wrong.
timestamp: 2026-07-23T00:00:00+05:30
is_order_action: false
broker_api_called: false
source: v4.7 supersession record

## Agent Work Contract

source_agent: primary
action: dormant source-confusion supersession
title: v4.7 real signal recovery scaffolding
scope: Preserve the fail-closed v4.6 checkpoint, invalidate the dormant option-metadata-as-signal-source path, and introduce a v4.7 registry scaffold for real strategy-specific signal recovery without touching live, broker, risk, or production execution paths.
requested_paths: research/option_e2e_recertification_v4/v4_7_supersession/*, research/option_e2e_recertification_v4/signal_ledgers_v4_7/*, tests/research/option_e2e/test_signal_ledgers_v4_7.py
allowed_paths: research/option_e2e_recertification_v4/v4_7_supersession/*, research/option_e2e_recertification_v4/signal_ledgers_v4_7/*, tests/research/option_e2e/test_signal_ledgers_v4_7.py, docs/agent_reviews/option_e2e_v4_6_dormant_source_confusion_invalidation.md
forbidden_paths: broker, live, order, risk, credentials, dashboard, production thresholds, production registration, real-money paths
expected_tests: Focused option-e2e tests, affected suite, CE gate, agent review evidence gate
acceptance_proof: The v4.7 scaffold records strategy-specific source domains without manufacturing signal rows, and the v4.4 builder remains fail-closed with no placeholder ledger construction.

## Scope Guard

This record invalidates the dormant option-metadata-as-signal-source branch. It does not claim any real strategy signal has been recovered yet.

## Grill Me Review

The remaining problem was not certification. The problem was that the source domain still blurred option authority artifacts with strategy signal sources.

## Hermes Review

Source domains must be separated before any signal recovery can be trusted. Option contract authority, quote data, and diagnostic current master artifacts cannot stand in for a strategy signal source.

## GSD Review

The v4.7 scaffold records lane metadata and fail-closed defaults only. It does not create a live, broker, or production path.

## QA / Safety Review

All outputs remain `research_only=true`, `allowed_for_live_execution=false`, `broker_api_called=false`, and `is_order_action=false`.

## Acceptance Proof

The v4.4 builder no longer manufactures signal ledgers from resolved sources, and the new v4.7 registry enumerates strategy lanes without claiming recovered signals.

## Runtime Proof Required After Merge

No runtime proof is required. This remains an offline evidence and registry refinement step.

## What This PR Does Not Prove

This does not prove that real strategy-specific signal ledgers exist, that option coverage is frozen, or that profitability has been validated.

## Human Approval

Human approval is required before any runtime or live-trading interpretation can be derived from this supersession.

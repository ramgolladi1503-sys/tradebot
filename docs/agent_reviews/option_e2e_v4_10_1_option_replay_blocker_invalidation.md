# v4.10.1 Option Replay Blocker Invalidation

mode: RESEARCH_ONLY_SUPERSESSION
candidate_id: option_e2e_v4_10_1_option_replay_blocker_invalidation
decision: INVALID_OPTION_REPLAY_BLOCKER_AS_SIGNAL_SOURCE_BLOCKER
reason: The v4.10.1 blocker split remained a blocker-context distinction and did not prove a VWAP signal source or executed VWAP contract.
timestamp: 2026-07-24T00:00:00+05:30
source: PR #710 v4.10.2 repair
read_only: true
append: false
research_only: true
allowed_for_live_execution: false
broker_api_called: false
is_order_action: false

## Agent Work Contract

source_agent: Codex
action: REPAIR
title: Invalidate option-replay blockers as VWAP signal proof
scope: Invalidate the v4.10.1 blocker-label split as signal-execution proof while preserving the fail-closed research boundary.
requested_paths: docs/agent_reviews/option_e2e_v4_10_1_option_replay_blocker_invalidation.md, research/option_e2e_recertification_v4/v4_10_2_supersession/v4_10_1_option_replay_blocker_invalidation.json, research/option_e2e_recertification_v4/v4_10_2_supersession/v4_10_1_option_replay_blocker_invalidation.json.sha256
allowed_paths: docs/agent_reviews/*, research/option_e2e_recertification_v4/v4_10_2_supersession/*
forbidden_paths: broker, live order, live feed, credentials, risk gates, dashboard, production thresholds, production registration, real-money paths
expected_tests: PYTHONPATH=. pytest -q tests/research/option_e2e/test_signal_ledgers_v4_10_2.py
acceptance_proof: The active path returns zero signal rows, excludes invalidated historical evidence from current signal evidence, and does not use option-replay blockers as signal truth.

## Scope Guard

This change is offline and research-only. It does not alter broker, order, live-feed, credential, risk, dashboard, production-threshold, strategy-registration, or real-money paths.

read_only: true
append: false
research_only: true
allowed_for_live_execution: false
broker_api_called: false
is_order_action: false

## Grill Me Review

The earlier v4.10.1 blocker split was still only a blocker-context distinction. It did not prove a VWAP signal row, import a frozen VWAP signal artifact, or execute a frozen VWAP strategy contract.

## Hermes Review

Legacy option-replay audit records and invalidated historical records must remain separate from strategy signal evidence. A missing option replay cannot establish that the underlying strategy signal source is missing.

## GSD Review

The repair preserves the invalidation record, keeps the package fail-closed, and does not broaden scope into live or broker paths.

## QA / Safety Review

The evidence remains read-only and non-executable. No fake signal rows are emitted. No broker API is called and no order action is created.

## Acceptance Proof

The active research path emits zero signal rows, keeps invalidated historical evidence out of current signal evidence, and disables signal certification until independent oracle evidence exists. Focused tests exercise those boundaries.

## Runtime Proof Required After Merge

No live runtime proof is required for this offline invalidation. CI must rerun the focused evidence tests and verify that no broker, live, order, credential, risk, dashboard, or production paths changed.

## What This PR Does Not Prove

This does not prove that VWAP signals were executed, that a signal ledger was certified, that a historical dataset was accepted, or that profitability, WFA, holdout, paper, or live readiness exists.

## Human Approval

Human approval is required before any move toward runtime, paper, live, broker, or order integration. No such approval is granted by this change.

# PR #984 — Launch Plan Candidate Registration and Live Signal Audit

## Evidence Contract Fields

- mode: LIVE_OBSERVATION_SUBSCRIPTION_SYNCHRONIZATION
- candidate_id: pr984-launch-plan-candidate-registration-top30
- decision: REVIEW_ONLY
- reason: Presession launch plan candidate registration in Kite WebSocket depth feed, unblocking option subscription synchronization and resolving opportunity pipeline candidate suppression.
- source_agent: gsd
- action: GENERATE_PATCH
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- append: false

## Agent Work Contract

- PR: #984
- Branch: `fix/launch-plan-subscription-candidate-top30`
- Scope: Implementation and verification of presession launch plan desired subscription candidate registration:
  - Atomically record desired subscription candidate in `core/kite_depth_ws.py` under `_OPTION_OWNERSHIP_LOCK` when a verified sealed launch plan is ingested.
  - Fail-closed candidate invalidation if the plan is unsealed, not OK, or option metadata resolution is blocked.
  - Comprehensive unit test suite covering Gates G-1 through G-5 in `tests/test_kite_depth_ws_stability.py`.
  - Comprehensive audit document `docs/live_audit_top30_signals.md` detailing the 5 root causes of zero trade emission and Top 30 issues inventory.
- Requested paths:
  - `core/kite_depth_ws.py`
  - `tests/test_kite_depth_ws_stability.py`
  - `docs/tradebot_delivery/live_audit_top30_signals.md`
  - `docs/agent_reviews/pr984_launch_plan_candidate_registration.md`
- Allowed paths: the requested paths above only.
- Forbidden paths/behaviors: broker order placement or modification, secrets, live trading enablement, bypassing risk gates or feed freshness checks, credentials, .env files.
- Expected tests: 87/87 passing unit and stability tests in `tests/test_kite_depth_ws_stability.py`.
- Acceptance proof: passing local test suite, clean syntax compilation, Cerberus and Minerva gate verification.

## Scope Guard

Verdict: PASS

- All modifications strictly adhere to WebSocket subscription candidate tracking, fail-closed metadata checks, and audit documentation.
- No live broker orders are placed, cancelled, or altered (`is_order_action: false`, `broker_api_called: false`).
- Zero changes to broker order routing, risk throttles, or account credentials.

## High-Risk Path Review

Verdict: PASS WITH RUNTIME PROOF REQUIRED

`core/kite_depth_ws.py` touches WebSocket feed subscription state. Changes are strictly confined to:
1. Under `_OPTION_OWNERSHIP_LOCK`, recording the desired subscription candidate when `activate_market_event_graph_launch_plan` validates a presession launch plan with `ok=True` and `verdict="PASS_LIVE_SOURCE_PRESESSION_READINESS"`.
2. Explicitly invalidating the candidate fail-closed if `not ok` or `metadata is None`.
3. Candidate registration does not alter or bypass tick freshness latches (`urgent_max_age_sec`).
All order-execution and risk-gating paths remain un-gated and strictly read-only.

## Grill Me Review

Verdict: PASS

Adversarial critique resolved with empirical constraints:
- Invariant I-1: Atomic lock acquisition ensures candidate recording and staged option contracts remain synchronous without race conditions.
- Invariant I-2: Budget bounds ($\le 250$) are strictly enforced; oversized token requests are rejected.
- Invariant I-3: Zero synchronous network calls inside candidate registration prevents reactor loop deadlocks.
- Invariant I-4: Freshness latches remain fully active; zero fresh ticks still trips staleness gates even if subscription ownership is KNOWN.
- Invariant I-5: Unsealed or tampered launch plans immediately invalidate candidate fail-closed.
- Invariant I-6: Zero order actions, zero credential leaks, strictly read-only telemetry.

## Hermes Review

Verdict: PASS WITH BOUNDED CONTRACT

Architectural invariants I-1 through I-6 formally defined:
- Deterministic candidate registration within `_OPTION_OWNERSHIP_LOCK`.
- Preserves separation between launch plan staging, candidate ownership, and physical WebSocket subscription.
- Fail-closed isolation on plan invalidation or metadata block.

## GSD Review

Verdict: PASS

All scoped work items implemented cleanly with proof-driven tests. Zero shortcuts, zero mock-only tests, and zero bypass of safety gates. 87 tests execute cleanly in under 10 seconds.

## QA / Safety Review

Verdict: PASS

- 87 passed tests locally across `tests/test_kite_depth_ws_stability.py`.
- Dedicated Gate tests G-1 through G-5 verified:
  - `test_audit_top30_gate_g1_valid_launch_plan_registers_candidate`: PASS
  - `test_audit_top30_gate_g2_invalid_or_unsealed_plan_invalidates_candidate`: PASS
  - `test_audit_top30_gate_g3_metadata_blocked_invalidates_candidate`: PASS
  - `test_audit_top30_gate_g4_observation_sync_reconciles_candidate_tokens`: PASS
  - `test_audit_top30_gate_g5_safety_invariants_preserved`: PASS
- Non-negotiables verified:
  - `read_only = True`
  - `is_order_action = False`
  - `broker_api_called = False`
  - `allowed_for_live_execution = False`

## Acceptance Proof

```text
pytest tests/test_kite_depth_ws_stability.py -q
87 passed, 3 warnings in 9.49s
```

## Runtime Proof Required After Merge

During tomorrow morning's governed launcher start:
1. Verify `ownership.state` transitions to `KNOWN` with valid token count (e.g. 123 tokens).
2. Confirm `ranked_pipeline_latest.json` does not trip `OPTION_CONFIRMATION_MISSING` or `desired_subscription_candidate_invalid_or_stale`.

## What This PR Does Not Prove

1. It does not certify algorithmic trading profitability.
2. It does not authorize live automated order placement with capital risk.
3. It does not replace human operator monitoring during market open/close.

## Human Approval

Approved by USER in task prompt: "sure work on it", "open a pr for all these fixes and work until ci is green and then merge it to main and get the morning readninsess".

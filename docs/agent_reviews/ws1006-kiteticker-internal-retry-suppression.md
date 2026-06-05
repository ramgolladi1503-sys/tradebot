# Disable KiteTicker Internal Auto-Retry After Terminal WS1006

mode: REVIEW
candidate_id: PR-WS1006-KITETICKER-INTERNAL-RETRY-SUPPRESSION
decision: disable_kiteticker_internal_retry_after_terminal_ws1006
reason: Add deterministic offline regression coverage and minimal websocket lifecycle guard so terminal WS1006 / unclean websocket close disables KiteTicker/Twisted internal retry in addition to outer restart suppression, preserving recovery-blocked fail-closed behavior and process restart requirement.
timestamp: 2026-06-05T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/ws1006-kiteticker-internal-retry-suppression.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (minimal websocket lifecycle guard + offline regression tests + docs)
title: Disable KiteTicker Internal Auto-Retry After Terminal WS1006
scope: make terminal WS1006 / unclean websocket close disable KiteTicker/Twisted internal retry in addition to outer restart suppression without changing healthy reconnect behavior
requested_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_restart.py
  - tests/test_kite_depth_ws_stability.py
  - docs/ws1006_kiteticker_internal_retry_suppression.md
  - docs/agent_reviews/ws1006-kiteticker-internal-retry-suppression.md
allowed_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_restart.py
  - tests/test_kite_depth_ws_stability.py
  - docs/ws1006_kiteticker_internal_retry_suppression.md
  - docs/agent_reviews/*
forbidden_paths:
  - strategies/*
  - dashboard/*
  - core/orchestrator.py
  - core/runtime_execution_truth.py
  - core/feed_truth_contract.py
  - core/feed_truth_audit.py
  - core/candidate_outcome_truth.py
  - core/candidate_outcome_fixture_loader.py
  - core/candidate_outcome_report_writer.py
  - core/broker*
  - core/order*
  - execution_engine/*
  - runtime/*
  - logs/*
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py -vv
  - PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py tests/test_kite_depth_ws_stability.py tests/test_feed_runtime_states.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_trade_builder_real_candidate_supply.py tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_fixture_loader.py tests/test_candidate_outcome_report_writer.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - git diff --name-status origin/main...HEAD
acceptance_proof:
  - terminal WS1006 / unclean close disables KiteTicker internal retry when supported
  - stop_retry and factory.stopTrying are called when available
  - outer restart suppression remains intact
  - RECOVERY_BLOCKED remains terminal
  - no in-process start/restart is scheduled after terminal WS1006
  - normal non-terminal reconnect behavior remains unchanged
```

## Scope Guard

- This PR is a websocket lifecycle safety regression guard.
- It must not change strategy, ranking, Phase2, broker/order, or dashboard behavior.
- It must fail closed on terminal websocket faults.

## High-Risk Path Review

- `core/kite_depth_ws.py` is a high-risk path because it owns websocket lifecycle and feed recovery behavior.
- The patch is intentionally narrow: it only disables internal KiteTicker retry after terminal WS1006 / unclean close conditions.
- Healthy startup, subscription, and non-terminal reconnect logic remain unchanged.

## Closed-Environment / Off-Market Rule

- All validation is offline and deterministic.
- No live Kite session is required.
- No broker calls are allowed.
- No real websocket connection is opened in tests.

## PR #488 Live Evidence Summary

- Outer restart suppression already worked: terminal WS1006 entered `RECOVERY_BLOCKED` and `process_restart_required` remained true.
- The remaining failure mode is KiteTicker/Twisted internal retry behavior that can still emit `will retry in 2 seconds` / `Starting factory` after the terminal event.

## Remaining Failure Mode

- If internal retry remains enabled, the websocket stack can keep attempting recovery even though the runtime has already declared the feed terminal and blocked.
- That creates repeated noisy retry attempts and can obscure the true process-restart-required state.

## Grill Me Review

- The risk is accidentally suppressing a recoverable reconnect.
- The test suite must prove suppression happens only on terminal WS1006 / unclean close conditions, not on ordinary reconnectable network errors.

## Hermes Review

- The safest boundary is the terminal websocket error/close handler.
- A small helper that disables internal retry when supported is preferable to scattering ad hoc calls.
- Existing healthy reconnect logic should remain unchanged for non-terminal faults.

## GSD Review

- Changes are narrowly scoped to websocket lifecycle code, restart tests, and docs.
- No unrelated runtime, strategy, or execution changes are included.

## QA / Safety Review

- `read_only=true` where applicable.
- `is_order_action=false`.
- `broker_api_called=false`.
- `allowed_for_live_execution=false` for evidence artifacts.
- Internal retry suppression must be explicit in snapshots and logs.

## Acceptance Proof

- WS1006-like on_error/on_close inputs produce recovery-blocked snapshots.
- Terminal faults disable internal KiteTicker retry when supported.
- Restart scheduling while blocked is a no-op.
- The feed/runtime snapshot exposes `process_restart_required=True` and `restart_suppressed=True`.
- Non-terminal reconnect errors still use the existing restart behavior.

## Validation Commands

- `PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py -vv`
- `PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py tests/test_kite_depth_ws_stability.py tests/test_feed_runtime_states.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_trade_builder_real_candidate_supply.py tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_fixture_loader.py tests/test_candidate_outcome_report_writer.py -vv`
- `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- `git diff --check`
- `git diff --name-status origin/main...HEAD`

## Expected Changed Files

- `core/kite_depth_ws.py`
- `tests/test_kite_depth_restart.py`
- `tests/test_kite_depth_ws_stability.py`
- `docs/ws1006_kiteticker_internal_retry_suppression.md`
- `docs/agent_reviews/ws1006-kiteticker-internal-retry-suppression.md`

## Forbidden Scope Not Touched

- `strategies/*`
- `dashboard/*`
- `core/orchestrator.py`
- `core/runtime_execution_truth.py`
- `core/feed_truth_contract.py`
- `core/feed_truth_audit.py`
- `core/candidate_outcome_truth.py`
- `core/candidate_outcome_fixture_loader.py`
- `core/candidate_outcome_report_writer.py`
- `core/broker*`
- `core/order*`
- `runtime/*`
- `logs/*`

## Risk Assessment

- Low to medium risk because the patch changes only websocket lifecycle failure handling.
- The main failure mode would be over-blocking a recoverable reconnect; tests must prove the guard only fires on terminal WS1006 / unclean close / terminal reactor conditions.

## Rollback Plan

- Revert the websocket lifecycle guard and the associated tests/docs if the regression proves too aggressive.
- Restore the previous restart behavior only if a human-reviewed live audit demonstrates the need.

## Runtime Proof Required After Merge

- Run an audit-only live session and confirm terminal WS1006 now disables internal retry in addition to outer restart suppression.
- Confirm no in-process restart storm occurs.

## What This PR Does Not Prove

- It does not prove trading edge or profitability.
- It does not prove live market performance.
- It does not change any ranking or execution logic.

## Why This Does Not Prove Trading Edge

- The PR only prevents unsafe websocket recovery behavior.
- It does not improve candidate quality, execution quality, or market edge.

## Future Work Explicitly Out of Scope

- Any runtime websocket architecture rewrite.
- Any change to candidate generation or execution truth.
- Any feed-truth schema change beyond existing evidence fields.

## Human Approval

This is safe to review as a focused websocket lifecycle regression guard.

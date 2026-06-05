# WS1006 Reactor Restart Suppression Regression Guard

mode: REVIEW
candidate_id: PR-WS1006-REACTOR-RESTART-SUPPRESSION
decision: add_ws1006_reactor_restart_suppression_regression_guard
reason: Add deterministic offline regression coverage and minimal websocket lifecycle guard so WS1006/unclean websocket close or ReactorNotRestartable risk fails closed into recovery-blocked process-restart-required state without in-process Twisted reactor restart attempts.
timestamp: 2026-06-05T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/ws1006-reactor-restart-suppression-regression.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (minimal websocket lifecycle guard + offline regression tests + docs)
title: WS1006 Reactor Restart Suppression Regression Guard
scope: make WS1006 and ReactorNotRestartable fail closed into recovery-blocked process-restart-required state without in-process restart storms
requested_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_restart.py
  - tests/test_kite_depth_ws_stability.py
  - docs/ws1006_reactor_restart_suppression.md
  - docs/agent_reviews/ws1006-reactor-restart-suppression-regression.md
allowed_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_restart.py
  - tests/test_kite_depth_ws_stability.py
  - docs/ws1006_reactor_restart_suppression.md
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
  - PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py tests/test_feed_runtime_states.py tests/test_kite_depth_ws_stability.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_trade_builder_real_candidate_supply.py tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_fixture_loader.py tests/test_candidate_outcome_report_writer.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - git diff --name-status origin/main...HEAD
acceptance_proof:
  - WS1006 / unclean close transitions into recovery-blocked process-restart-required state
  - ReactorNotRestartable does not trigger in-process restart storms
  - restart scheduling becomes a no-op under terminal recovery block
  - feed/runtime truth stays degraded until process restart
```

## Scope Guard

- This PR is a websocket lifecycle safety regression guard.
- It must not change strategy, ranking, Phase2, broker/order, or dashboard behavior.
- It must fail closed on terminal websocket faults.

## Closed-Environment / Off-Market Rule

- All validation is offline and deterministic.
- No live Kite session is required.
- No broker calls are allowed.
- No real websocket connection is opened in tests.

## Live Evidence Summary

- Live audit showed a WS1006 / unclean-close failure followed by repeated `ReactorNotRestartable` restart storms.
- The intended terminal outcome is process restart required, with feed/runtime truth preserved as unhealthy.

## Grill Me Review

- The risk is accidentally preserving a restart path after terminal failure.
- The test suite must prove the restart path is suppressed, not merely renamed.
- The live feed must remain visibly degraded; no silent recovery is allowed.

## Hermes Review

- The safest boundary is at the websocket lifecycle entry points.
- A small helper that marks terminal recovery-blocked state is preferred over scattered special cases.
- Existing healthy startup and subscription logic should remain unchanged.

## GSD Review

- Changes are narrowly scoped to websocket lifecycle code, restart tests, and docs.
- No unrelated runtime, strategy, or execution changes are included.

## QA / Safety Review

- `read_only=true` where applicable.
- `is_order_action=false`.
- `broker_api_called=false`.
- `allowed_for_live_execution=false` for evidence artifacts.
- Restart suppression must be explicit in snapshots and logs.

## Acceptance Proof

- WS1006-like on_error/on_close inputs produce recovery-blocked snapshots.
- ReactorNotRestartable inputs do not trigger in-process restart attempts.
- Restart scheduling while blocked is a no-op.
- The feed/runtime snapshot exposes `process_restart_required=True` and `restart_suppressed=True`.

## Validation Commands

- `PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py -vv`
- `PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py tests/test_feed_runtime_states.py tests/test_kite_depth_ws_stability.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_trade_builder_real_candidate_supply.py tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_fixture_loader.py tests/test_candidate_outcome_report_writer.py -vv`
- `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- `git diff --check`
- `git diff --name-status origin/main...HEAD`

## Expected Changed Files

- `core/kite_depth_ws.py`
- `tests/test_kite_depth_restart.py`
- `tests/test_kite_depth_ws_stability.py`
- `docs/ws1006_reactor_restart_suppression.md`
- `docs/agent_reviews/ws1006-reactor-restart-suppression-regression.md`

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
- The main failure mode would be over-blocking a recoverable reconnect; tests must prove the guard only fires on WS1006 / unclean close / terminal reactor conditions.

## Rollback Plan

- Revert the websocket lifecycle guard and the associated tests/docs if the regression proves too aggressive.
- Restore the previous restart behavior only if a human-reviewed live audit demonstrates the need.

## Runtime Proof Required After Merge

- Run an audit-only live session and confirm WS1006 now enters terminal recovery-blocked state.
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

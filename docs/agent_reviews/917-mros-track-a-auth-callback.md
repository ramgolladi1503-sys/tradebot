# Governed Morning Observer & OAuth Callback Daemon (PR #917)

mode: SIM
candidate_id: 917-mros-track-a-auth-callback
decision: add_governed_morning_observer_and_hardened_callback
reason: Harden Kite OAuth callback daemon with token bounds and replay protection, govern morning observer launcher with dual supervision of raw tick collector and persistent MROS child process, enforce audit recovery provenance binding, and verify scheduler UTC cron authority.
timestamp: 2026-09-17T12:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/917-mros-track-a-auth-callback.md

## Agent Work Contract

PR #917 only. Hardens OAuth callback daemon, governs morning observer launcher with dual supervision of raw tick collector and persistent MROS child process (`run_market_event_graph_live_session_v1.py`), implements line-by-line audit recovery with byte-for-byte immutable archive and provenance binding, verifies scheduler UTC cron authority (`15 3 * * 1-5`), and provides comprehensive mutation and e2e test suites.

## Scope Guard

In scope:
- `core/audit_chain_recovery.py`
- `core/governed_morning_orchestrator.py`
- `scripts/kite_autologin_localhost.py`
- `scripts/run_governed_morning_observer_v1.py`
- `scripts/run_permanent_auth_callback_daemon.py`
- `scripts/scheduler.py`
- `scripts/tick_data_collector.py`
- `tests/test_audit_chain_recovery.py`
- `tests/test_governed_morning_orchestrator.py`
- `tests/test_mros_e2e_dress_rehearsal.py`
- `tests/test_mros_mutation_campaign.py`
- `tests/test_scheduler_authority.py`
- `docs/agent_reviews/917-mros-track-a-auth-callback.md`

Out of scope:
- Live broker order routing, account trading execution, strategy threshold modifications, risk gate weakening, production kill switches.

## Grill Me Review

Verdict: PASS
Blocking issues: NO
Analysis:
- The entire pipeline operates in strictly read-only observation mode (`broker_write_authority = false`, `order_authority = false`).
- Zero broker trade authority: order placement, modification, and cancellation APIs are completely absent and forbidden.
- Callback trust: URL query parameter length strictly bounded (2048 bytes -> 414), token format regex enforced, replay protection returns 409, symlink attacks rejected with 500, atomic fsync writes, and token file permissions restricted to 0600. Server port collision fails closed. Ownership contract enforces 256-bit cryptographic nonce in `.runtime/.callback_server_{port}.json`.
- Audit chain recovery: Line-by-line verification, corrupt audit files quarantined to immutable byte-for-byte archive (mode 0444) with SHA-256 manifest (mode 0444), and bootstrap genesis event explicitly binds `recovered_from_archive` provenance.
- Dual process isolation: Morning orchestrator strictly separates raw tick collector (`tick_data_collector.py`) from persistent MROS observer (`run_market_event_graph_live_session_v1.py`). Collector health alone never signals MROS observer success.
- Scheduler authority: Verified UTC cron `15 3 * * 1-5` matches 08:45 AM Asia/Kolkata. Enforces single runtime ownership and fails closed on drift.

## Hermes Review

Verdict: PASS
Blocking issues: NO
Design Approach:
- Clear contract between morning authentication, raw tick collection, and persistent MROS market graph live session.
- Process supervision monitors both children with hourly telemetry beginning at 09:17 IST and clean orderly shutdown at 15:45 IST cutoff.
- Graceful degradation: If Kite authentication is unavailable or fails, orchestrator cleanly falls back to governed offline observation without blocking boot.

## GSD Review

Verdict: PASS
Blocking issues: NO
Implementation Status:
- All core and script modules implemented, hardened, and compiled cleanly with zero errors.
- Test suites cover audit chain recovery, governed morning orchestrator lifecycle, scheduler authority, mutation campaign (10/10 mutations caught), and full end-to-end dress rehearsal.

## QA / Safety Review

Verdict: PASS
Blocking issues: NO
Testing and Boundaries:
- Unit tests: `tests/test_audit_chain_recovery.py`, `tests/test_governed_morning_orchestrator.py`, `tests/test_scheduler_authority.py`.
- Mutation tests: `tests/test_mros_mutation_campaign.py`.
- E2E tests: `tests/test_mros_e2e_dress_rehearsal.py`.
- Compilation: `python3 -m compileall core scripts tests`.
- Boundaries: `is_order_action = false`, `broker_api_called = false`, `read_only = true`. Zero orders placed, modified, or cancelled.

## Acceptance Proof

```bash
pytest -v tests/test_audit_chain_recovery.py tests/test_governed_morning_orchestrator.py tests/test_scheduler_authority.py tests/test_mros_mutation_campaign.py tests/test_mros_e2e_dress_rehearsal.py
python3 -m compileall core scripts tests
python3 scripts/validate_agent_review_evidence.py --base-ref origin/main --candidate-ref HEAD
```

## Runtime Proof Required After Merge

Run preflight verification:
```bash
python3 scripts/run_governed_morning_observer_v1.py --preflight-only
```
Verify ReleaseStore certified SHA and cron execution at 08:45 AM IST (03:15 UTC).

## What This PR Does Not Prove

This PR does not prove live trading profitability, alpha generation, or order execution fills. It provides hardened, governed, read-only observation and telemetry infrastructure.

## Human Approval

Approved by human operator for merge, data capture automation, and governed read-only observation.

## High-Risk Path Review

N/A - does not modify files under config/, core/execution/, core/risk/, core/broker/, or strategies/.
Modifications to `core/audit_chain_recovery.py`, `core/governed_morning_orchestrator.py`, and `scripts/` maintain strictly read-only execution with fail-closed safety semantics.

## Evidence Contract

- mode: SIM
- candidate_id: 917-mros-track-a-auth-callback
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-09-17T12:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false

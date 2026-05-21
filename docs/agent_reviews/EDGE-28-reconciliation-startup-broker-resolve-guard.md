# EDGE-28 — Reconciliation Startup Broker Resolve Guard

## Evidence Contract Fields

- mode: PAPER_STARTUP_SAFETY_FIX
- candidate_id: EDGE-28-reconciliation-startup-broker-resolve-guard
- decision: SKIP_GLOBAL_BROKER_AUTH_RESOLUTION_FOR_NONLIVE_RECONCILIATION_WITHOUT_INJECTED_BROKER
- reason: EDGE-27 runtime proof showed PAPER startup reconciliation spent about 55 seconds inside broker API resolution before orders/positions/local-state work began.
- timestamp: 2026-05-21T18:55:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-28-reconciliation-startup-broker-resolve-guard.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: EDGE-28 planned
- Branch: edge28-recon-broker-resolve-guard
- Scope: prevent PAPER/SIM/DRY_RUN reconciliation from blocking startup on global broker auth resolution when no broker API is explicitly injected.
- Allowed files:
  - core/order_reconciliation_daemon.py
  - tests/test_order_reconciliation_broker_resolve_guard.py
  - docs/agent_reviews/EDGE-28-reconciliation-startup-broker-resolve-guard.md
- Forbidden files:
  - core/orchestrator.py
  - core/execution_engine.py
  - core/kite_depth_ws.py
  - core/auth.py
  - strategies/
  - dashboard/
  - config/
- Forbidden behaviors:
  - No broker order placement.
  - No strategy behavior changes.
  - No feed/WebSocket changes.
  - No dashboard changes.
  - No scoring/ranking/threshold changes.
  - No weakening of LIVE reconciliation behavior.

## Scope Guard

Verdict: PASS

Checked:

- No order placement code changed.
- No strategy/scoring/threshold logic changed.
- No feed/WebSocket logic changed.
- No dashboard logic changed.
- No direct orchestrator change.
- LIVE mode still attempts global broker auth unless DRY_RUN is explicitly true.
- Injected broker API path still works in PAPER.

Blocking issues: none.

## High-Risk Path Review

Verdict: PASS_WITH_RUNTIME_PROOF_REQUIRED

High-risk area touched:

- `core/order_reconciliation_daemon.py`, specifically broker auth resolution skip logic.

Safety proof:

- The change only expands non-live skip modes to include PAPER-like modes.
- If any runtime mode is LIVE and DRY_RUN is false, broker auth resolution is not skipped.
- If a broker API is explicitly injected, reconciliation still uses it.
- The existing failure-result path remains: `broker_api_unavailable` is logged and reconciliation returns an error result without placing orders.

## Grill Me Review

Verdict: PASS_WITH_TEST_PROOF

Weak assumptions:

1. Assumption: PAPER startup should not call global Kite auth during reconciliation.
   - Evidence: runtime proof showed global broker resolution consumed roughly 55 seconds during PAPER startup.
2. Assumption: LIVE must remain strict.
   - Enforced by tests: LIVE still calls `kite_client.ensure()`.

Failure modes:

1. If environment/config mode values conflict, LIVE wins unless DRY_RUN is true.
2. If a caller injects broker API, the injected broker still gets used in PAPER.
3. If no broker API is injected in PAPER, reconciliation returns a quick unavailable result instead of blocking on auth.

## Hermes Review

Verdict: PASS

Architecture consistency:

- Keeps reconciliation ownership inside `core/order_reconciliation_daemon.py`.
- Does not touch orchestrator constructor.
- Does not touch execution engine wrapper.
- Does not hide LIVE broker failures.

## GSD Review

Verdict: PASS

Execution plan:

1. Extend non-live skip mode handling to PAPER/PAPER_TRADING/BACKTEST/TEST.
2. Add env-aware mode resolution so runtime exports are honored.
3. Add LIVE precedence so mixed LIVE/PAPER env does not silently skip broker auth.
4. Add tests proving PAPER skip, injected broker use, LIVE auth, and DRY_RUN override.
5. Run runtime proof after merge.

## QA / Safety Review

Tests required:

```bash
python -m pytest tests/test_order_reconciliation_broker_resolve_guard.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Runtime proof after merge:

```bash
cd /Users/madhuram/tradebot

git checkout main
git pull --ff-only origin main

rm -f .runtime/locks/kite_session.lock .runtime/locks/live_monitoring.lock .runtime/locks/depth_ws.lock

export TRADING_MODE=PAPER
export EXECUTION_MODE=PAPER
export ALLOW_LIVE_PLACEMENT=false
export DRY_RUN=false
unset ORDER_RECON_DAEMON_ENABLE

nohup python main.py > .runtime/logs/offmarket_after_edge28_recon_guard_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > .runtime/offmarket_after_edge28_recon_guard.pid
sleep 80
kill "$(cat .runtime/offmarket_after_edge28_recon_guard.pid)" 2>/dev/null || true
rm -f .runtime/offmarket_after_edge28_recon_guard.pid

grep -nE "RECON_ONCE|ORCHESTRATOR_RECON|ORCHESTRATOR_INIT|LIVE_MONITORING" .runtime/logs/runtime_startup_lifecycle.jsonl | tail -260
```

Expected proof:

```text
RECON_ONCE_BROKER_RESOLVE_STARTED
RECON_ONCE_BROKER_RESOLVE_FAILED quickly with broker_api_unavailable
ORCHESTRATOR_RECON_ONCE_COMPLETED quickly
ORCHESTRATOR_INIT_COMPLETED
LIVE_MONITORING_ENTERED
```

## What This PR Does Not Do

1. It does not disable reconciliation globally.
2. It does not change broker order placement.
3. It does not change strategy behavior.
4. It does not solve LIVE broker auth latency.
5. It does not build the separate Debug Forensics Agent.

## Human Approval

Approved by: Ram, after CI passes
Date: 2026-05-21

# EDGE-27 — Reconciliation Once Internal Boundary Proof

## Evidence Contract Fields

- mode: PAPER_EVIDENCE_PROOF
- candidate_id: EDGE-27-reconciliation-once-internal-boundary-proof
- decision: ADD_RECONCILIATION_ONCE_INTERNAL_BOUNDARY_PROOF
- reason: EDGE-26 runtime proof showed `ExecutionEngine.reconcile_orders_once()` consumed roughly 58 seconds during startup.
- timestamp: 2026-05-21T18:20:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-27-reconciliation-once-internal-boundary-proof.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: EDGE-27 / PR #180 planned
- Branch: edge27-recon-once-internal-proof
- Scope: add evidence-only internal boundary proof around `OrderReconciliationDaemon.run_cycle_once()` and its critical internal calls.
- Allowed files:
  - core/recon_once_probe.py
  - core/runtime_startup_lifecycle.py
  - tests/test_recon_once_probe.py
  - docs/agent_reviews/EDGE-27-reconciliation-once-internal-boundary-proof.md
- Forbidden files:
  - core/execution_engine.py
  - core/order_reconciliation_daemon.py
  - core/orchestrator.py
  - core/kite_depth_ws.py
  - core/auth.py
  - strategies/
  - dashboard/
  - config/
- Forbidden behaviors:
  - No broker/order behavior changes.
  - No reconciliation behavior changes.
  - No strategy logic changes.
  - No feed/WebSocket behavior changes.
  - No dashboard changes.
  - No threshold/ranking/scoring changes.
- Acceptance tests:
  - Probe emits success events for reconciliation cycle entry/completion.
  - Probe emits broker resolution, broker orders fetch, broker positions fetch, local state load, and write events.
  - Probe emits failure events and re-raises original exceptions.
- Runtime proof required: clean off-market PAPER run after merge with reconciliation enabled must show which internal reconciliation step consumes the startup delay.

## Scope Guard

Verdict: PASS

Checked:

- No broker placement changes.
- No LIVE mode enablement.
- No strategy/scoring/threshold changes.
- No dashboard changes.
- No credential handling changes.
- No direct edits to `core/execution_engine.py`.
- No direct edits to `core/order_reconciliation_daemon.py`.
- No fake runtime proof.

Blocking issues: none.

## High-Risk Path Review

Verdict: PASS_WITH_SCOPE_GUARD

High-risk area touched:

- Runtime startup lifecycle now best-effort installs a reconciliation proof wrapper.

High-risk areas intentionally not touched:

- `core/execution_engine.py` is not edited.
- `core/order_reconciliation_daemon.py` is not edited.
- Broker/feed/auth/strategy/dashboard files are not edited.

Safety proof:

- The probe records start/completion/failure only.
- Return values are preserved.
- Exceptions are re-raised after FAILED evidence is recorded.
- All evidence records remain `is_order_action=false`.

## Grill Me Review

Verdict: PASS_WITH_RUNTIME_PROOF_REQUIRED

Weak assumptions:

1. Assumption: the slow step is inside `OrderReconciliationDaemon.run_cycle_once()`.
   - Evidence: EDGE-26 showed `reconcile_orders_once()` started and completed about 58 seconds later.
2. Assumption: wrapping daemon class methods is enough.
   - Risk: the slow work could happen in unwrapped helper logic between the wrapped methods.

Failure modes:

1. If `RECON_ONCE_BROKER_RESOLVE_STARTED` appears without completion/failure, broker resolution is blocking.
2. If `RECON_ONCE_BROKER_ORDERS_FETCH_STARTED` appears without completion/failure, broker orders fetch is blocking.
3. If `RECON_ONCE_BROKER_POSITIONS_FETCH_STARTED` appears without completion/failure, broker positions fetch is blocking.
4. If local state load is slow, `RECON_ONCE_LOCAL_STATE_LOAD_STARTED` will expose it.

Missing proof:

1. Runtime proof after merge must show internal reconciliation boundary events.
2. This PR does not fix the 58-second startup delay.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. Adds a dedicated probe module instead of editing reconciliation behavior directly.
2. Keeps runtime startup evidence installation best-effort.
3. Preserves method return values and exception behavior.

Files not touched:

1. `core/execution_engine.py`
2. `core/order_reconciliation_daemon.py`
3. `core/orchestrator.py`
4. `strategies/`

Boundary verdict:

- Evidence-only wrapper around existing reconciliation methods.
- No business behavior change intended.

## GSD Review

Verdict: PASS

Execution plan:

1. Add dedicated reconciliation-once probe module.
2. Activate it from runtime startup lifecycle before orchestrator startup probe.
3. Add focused tests for success and failure event emission.
4. Add mandatory agent evidence doc.
5. After merge, run clean PAPER/off-market proof with reconciliation enabled.

Evidence required:

1. CI unit tests pass.
2. Agent Review Evidence Gate passes.
3. Runtime proof after merge shows internal reconciliation boundary events.

Done means:

- The next recon-enabled run tells whether the delay is broker resolution, broker orders fetch, broker positions fetch, local order-state load, reconciliation compare/update, or logging/write.

## QA / Safety Review

Tests required:

```bash
python -m pytest tests/test_recon_once_probe.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Safety checks:

1. No order action fields set true.
2. No broker/order behavior introduced.
3. No feed/WebSocket behavior changed.
4. No strategy behavior changed.

## Acceptance Proof

Commands:

```bash
python -m pytest tests/test_recon_once_probe.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Expected result:

```text
All tests pass.
AGENT REVIEW EVIDENCE GATE: PASSED
```

## Runtime Proof Required After Merge

Command:

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

nohup python main.py > .runtime/logs/offmarket_after_edge27_recon_enabled_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > .runtime/offmarket_after_edge27_recon_enabled.pid
sleep 130
kill "$(cat .runtime/offmarket_after_edge27_recon_enabled.pid)" 2>/dev/null || true
rm -f .runtime/offmarket_after_edge27_recon_enabled.pid

grep -nE "RECON_ONCE|ORCHESTRATOR_RECON|ORCHESTRATOR_GATEKEEPER|ORCHESTRATOR_STRATEGY_TRACKER|ORCHESTRATOR_INIT|LIVE_MONITORING|RUNTIME_STATUS" .runtime/logs/runtime_startup_lifecycle.jsonl | tail -320
```

Expected evidence:

```text
RECON_ONCE_ENTERED
Then the last completed/started internal boundary identifies the delay.
```

## What This PR Does Not Prove

1. It does not prove feed/WebSocket works.
2. It does not prove market-hours behavior.
3. It does not prove strategy quality or profitability.
4. It does not fix reconciliation delay/blocking.
5. It does not build the separate Debug Forensics Agent architecture.

## Human Approval

Approved by: Ram, after CI passes
Date: 2026-05-21

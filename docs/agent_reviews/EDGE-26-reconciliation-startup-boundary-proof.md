# EDGE-26 — Reconciliation Startup Boundary Proof

## Evidence Contract Fields

- mode: PAPER_EVIDENCE_PROOF
- candidate_id: EDGE-26-reconciliation-startup-boundary-proof
- decision: ADD_RECONCILIATION_STARTUP_BOUNDARY_PROOF
- reason: Recon-enabled EDGE-25 proof showed an approximately 34.7 second blind gap after ORCHESTRATOR_GATEKEEPER_INIT_COMPLETED before ORCHESTRATOR_STRATEGY_TRACKER_INIT_STARTED.
- timestamp: 2026-05-21T17:55:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-26-reconciliation-startup-boundary-proof.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: EDGE-26 / PR #179 planned
- Branch: edge26-recon-boundary-proof
- Scope: add evidence-only reconciliation startup boundary proof around `ExecutionEngine.start_reconciliation_daemon()` and `ExecutionEngine.reconcile_orders_once()`.
- Allowed files:
  - core/orchestrator_startup_probe.py
  - tests/test_orchestrator_startup_probe.py
  - docs/agent_reviews/EDGE-26-reconciliation-startup-boundary-proof.md
- Forbidden files:
  - core/orchestrator.py
  - core/execution_engine.py
  - core/market_data.py
  - core/kite_depth_ws.py
  - core/auth.py
  - strategies/
  - dashboard/
  - config/
- Forbidden behaviors:
  - No broker/order behavior changes.
  - No strategy logic changes.
  - No feed/WebSocket behavior changes.
  - No market-data behavior changes.
  - No dashboard changes.
  - No threshold/ranking/scoring changes.
- Acceptance tests:
  - Probe emits reconciliation daemon start/completion events.
  - Probe emits reconciliation once start/completion events.
  - Probe emits reconciliation failure event and re-raises the original exception.
- Runtime proof required: clean off-market PAPER run after merge with reconciliation enabled must show where the post-gatekeeper delay occurs.

## Scope Guard

Verdict: PASS

Checked:

- No broker placement changes.
- No LIVE mode enablement.
- No strategy/scoring/threshold changes.
- No dashboard changes.
- No credential handling changes.
- No direct edits to core/orchestrator.py.
- No direct edits to core/execution_engine.py.
- No fake runtime proof.

Blocking issues: none.

## High-Risk Path Review

Verdict: PASS_WITH_SCOPE_GUARD

High-risk area touched:

- `core/orchestrator_startup_probe.py` is runtime evidence instrumentation around constructor dependencies.

High-risk areas intentionally not touched:

- `core/orchestrator.py` is not edited.
- `core/execution_engine.py` is not edited.
- Broker/feed/auth/strategy/dashboard files are not edited.

Safety proof:

- The wrapper records start/completion/failure only.
- Return values are preserved.
- Exceptions are re-raised after FAILED evidence is recorded.
- All evidence records remain `is_order_action=false`.

## Grill Me Review

Verdict: PASS_WITH_RUNTIME_PROOF_REQUIRED

Weak assumptions:

1. Assumption: the blind gap after gatekeeper is reconciliation startup.
   - Evidence: disabling reconciliation allowed startup to reach live monitoring; enabling reconciliation introduced a ~34.7 second post-gatekeeper gap.
2. Assumption: wrapping class methods on `ExecutionEngine` is enough.
   - Risk: if the constructor calls a different reconciliation helper path, these events may not appear.

Failure modes:

1. If `ORCHESTRATOR_RECON_DAEMON_START_STARTED` appears without completion/failure, daemon startup is blocking.
2. If daemon startup completes but `ORCHESTRATOR_RECON_ONCE_STARTED` appears without completion/failure, one-shot reconciliation is blocking.
3. If neither event appears and the gap remains, the blind zone is between gatekeeper completion and the recon method calls.

Missing proof:

1. Runtime proof after merge must show the reconciliation boundary events.
2. This PR does not fix reconciliation delay/blocking.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. Keeps proof logic isolated in the existing startup probe.
2. Avoids direct changes to orchestrator or execution engine behavior.
3. Preserves method return values and exception behavior.

Files not touched:

1. `core/orchestrator.py`
2. `core/execution_engine.py`
3. `core/kite_depth_ws.py`
4. `strategies/`

Boundary verdict:

- Evidence-only wrapper around existing reconciliation methods.
- No business behavior change intended.

## GSD Review

Verdict: PASS

Execution plan:

1. Add class-method wrapper support to `core/orchestrator_startup_probe.py`.
2. Wrap `ExecutionEngine.start_reconciliation_daemon()`.
3. Wrap `ExecutionEngine.reconcile_orders_once()`.
4. Add tests for success and failure event emission.
5. Add mandatory agent evidence doc.
6. After merge, run clean PAPER/off-market proof with reconciliation enabled.

Evidence required:

1. CI unit tests pass.
2. Agent Review Evidence Gate passes.
3. Runtime proof after merge shows reconciliation boundary events.

Done means:

- The next recon-enabled run tells whether the delay is in daemon startup, one-shot reconciliation, or another gap before those calls.

## QA / Safety Review

Tests required:

```bash
python -m pytest tests/test_orchestrator_startup_probe.py -q
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
python -m pytest tests/test_orchestrator_startup_probe.py -q
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

nohup python main.py > .runtime/logs/offmarket_after_edge26_recon_enabled_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > .runtime/offmarket_after_edge26_recon_enabled.pid
sleep 120
kill "$(cat .runtime/offmarket_after_edge26_recon_enabled.pid)" 2>/dev/null || true
rm -f .runtime/offmarket_after_edge26_recon_enabled.pid

grep -nE "ORCHESTRATOR_RECON|ORCHESTRATOR_GATEKEEPER|ORCHESTRATOR_STRATEGY_TRACKER|ORCHESTRATOR_INIT|LIVE_MONITORING|RUNTIME_STATUS" .runtime/logs/runtime_startup_lifecycle.jsonl | tail -260
```

Expected evidence:

```text
ORCHESTRATOR_RECON_DAEMON_START_STARTED
Then either completion, failure, or no return.
ORCHESTRATOR_RECON_ONCE_STARTED if daemon startup completes.
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
